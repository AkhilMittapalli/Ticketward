"""Generation matrix: spec, plausibility constraints, quotas and the pairwise-coverage sampler.

Spec v1.1 §9.1.1 and A-11 (ERPROT synthetic-data-generation D3). The full factorial has about
1.5M cells, so a plan is drawn instead:

1. per-intent quotas from ``intent_allocation`` (train 3,600; val 450; test_synth 1,045);
2. cells are drawn round-robin across intents; each dimension value comes from the values that
   keep the partial assignment *completable* under the constraints (depth-first lookahead, so a
   draw never dead-ends), preferring intent x value pairs still below their coverage minimum,
   otherwise deficit-weighted by ``target * target / (observed + 0.01)``. (The ERPROT D3 wording,
   ``target / (observed + 0.01)``, has its fixed point at shares proportional to sqrt(target);
   the extra ``target`` factor makes the fixed point the target share itself.);
3. a top-up pass moves values out of over-covered cells until every feasible pair meets
   ``coverage_min_per_pair`` (train 3, test_synth 1) and reports any pair it cannot fill;
4. card flags (lexical avoidance, PII placeholders, legal threat, greeting) get exact per-intent
   counts; entity values, pool entries, templates and seeds are drawn per cell.

The plan is a pure function of the matrix file, the pools, the fact sheet and the seed.
"""

import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tw_ml.datagen.alloc import derive_seed, largest_remainder, rng_for
from tw_ml.datagen.entities import EntityContext, sample_entities, supported_types
from tw_ml.datagen.factsheet import FactSheet
from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.paths import default_paths
from tw_ml.datagen.pools import Pools
from tw_ml.datagen.records import ALLOWED_FAMILIES, SPLIT_CODES, GenerationCell
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.datagen.text import sha256_hex

MATRIX_FILE: Final = "generation_matrix.yaml"
GeneratedSplit = Literal["train", "val", "test_synth"]
GENERATED_SPLITS: Final[tuple[GeneratedSplit, ...]] = ("train", "val", "test_synth")
TAXONOMY_DIMENSIONS: Final[Mapping[str, str]] = {
    "product_area": "ProductArea",
    "plan": "PlanTier",
    "channel": "Channel",
    "sentiment": "Sentiment",
}
HUMAN_REQUEST_KINDS: Final[tuple[str, ...]] = ("none", "direct", "indirect")
PII_PLACEHOLDERS: Final[tuple[str, ...]] = ("<EMAIL_1>", "<PERSON_1>", "<PHONE_1>")
CARD_PLACEHOLDER: Final = "<CARD_LAST4_1>"
MAX_OPTIONAL_ENTITIES: Final = 2
_UNIFORM: Final = "uniform"
_SMOOTHING: Final = 0.01

Dims = dict[str, str]
Demand = Mapping[tuple[str, str, str], int]


class MatrixError(ValueError):
    """Raised when the matrix file is inconsistent or a plan cannot be built."""


# --------------------------------------------------------------------------- spec models


class SpecModel(BaseModel):
    """Strict base for the matrix file models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SplitSpec(SpecModel):
    """How one split is generated."""

    n: int = Field(gt=0)
    family: Literal["A", "B"]
    generator_family: Literal["openai_gpt_oss", "deepseek", "mistral"]
    prompt_family: Literal["P-A", "P-B"]
    prompt_file: str
    templates: tuple[str, ...] = Field(min_length=1)
    pool: Literal["train", "val", "test", "hard"]
    overgeneration: float = Field(ge=1.0)
    coverage_min_per_pair: int = Field(ge=0)


class Allocation(SpecModel):
    """Per-intent quota rule of one split."""

    critical_each: int | None = Field(default=None, ge=0)
    non_critical_each: int | None = Field(default=None, ge=0)
    other_unclear: int | None = Field(default=None, ge=0)
    extra: dict[str, int] = Field(default_factory=dict)
    proportional_to: GeneratedSplit | None = None


class IntentAllocation(SpecModel):
    """Quota rules for every generated split."""

    critical_oversample: float = Field(ge=1.0)
    train: Allocation
    val: Allocation
    test_synth: Allocation


class Flags(SpecModel):
    """Shares of the binary card flags."""

    lexical_avoid: dict[Literal["critical", "other"], float]
    pii_placeholders: float = Field(ge=0, le=1)
    legal_threat_inside_billing: float = Field(ge=0, le=1)
    greeting_allowed: float = Field(ge=0, le=1)
    noise: float = Field(ge=0, le=1)


class ChurnCues(SpecModel):
    """Churn-cue shares for cancellation and other intents."""

    cancellation: dict[str, float]
    other: dict[str, float]


class Constraint(SpecModel):
    """A plausibility rule: when every ``if`` attribute matches, ``require`` must hold."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    id: str
    when: dict[str, tuple[str, ...]] = Field(alias="if")
    require: dict[str, tuple[str, ...]]


class IntentSpec(SpecModel):
    """Card material for one intent (definitions carry no example tickets)."""

    definition: str
    need_phrase: str
    required_entities: tuple[str, ...]
    error_code_prefixes: tuple[str, ...] = ()
    optional_entities: tuple[str, ...]
    needs_info_omit: tuple[str, ...]
    secondary_candidates: tuple[str, ...]
    banned_words: tuple[str, ...]
    scenario_types: tuple[str, ...]


class EntityValues(SpecModel):
    """Fixed value lists for entity sampling."""

    browser: tuple[str, ...]
    os: tuple[str, ...]
    legal_reference: tuple[str, ...]
    steps_already_tried: tuple[str, ...]
    user_count_affected: tuple[int, ...]
    timestamp_hours: tuple[int, ...]
    received_window: tuple[date, date]


class HistorySpec(SpecModel):
    """How many earlier messages a thread gets."""

    chat_transcript: tuple[int, int]
    email_followup: tuple[int, int]
    email_followup_share: float = Field(ge=0, le=1)


class Descriptions(SpecModel):
    """Card wording for dimension values (no example tickets)."""

    difficulty: dict[str, str]
    style: dict[str, str]
    subject_style: dict[str, str]
    channel: dict[str, str]
    human_request: dict[str, str]
    churn_cue: dict[str, str]
    impact: dict[str, str]


class Coverage(SpecModel):
    """Dimensions paired with the intent for coverage targets."""

    pairwise: tuple[str, ...]


class MatrixSpec(SpecModel):
    """The whole ``generation_matrix.yaml``."""

    matrix_version: str
    taxonomy_version: str
    seed: int = Field(ge=0)
    splits: dict[GeneratedSplit, SplitSpec]
    intent_allocation: IntentAllocation
    dimensions: dict[str, dict[str, float] | Literal["uniform"]]
    draw_order: tuple[str, ...]
    length_words: dict[str, tuple[int, int]]
    flags: Flags
    secondary_count: dict[Literal["one", "two"], float]
    secondary_order: dict[Literal["primary_first", "secondary_first", "interleaved"], float]
    churn_cues: ChurnCues
    constraints: tuple[Constraint, ...]
    coverage: Coverage
    strata_min: dict[GeneratedSplit, dict[str, int]]
    history_len: HistorySpec
    descriptions: Descriptions
    intents: dict[str, IntentSpec]
    entity_values: EntityValues


# --------------------------------------------------------------------------- loading


@dataclass(frozen=True, slots=True)
class Matrix:
    """A validated matrix: the spec plus resolved domains and target shares.

    Attributes:
        spec: Parsed file.
        domains: Dimension (and ``intent``) to ordered values.
        targets: Dimension to value to normalized target share.
        sha256: Hash of the file text (recorded with every plan).
    """

    spec: MatrixSpec
    domains: Mapping[str, tuple[str, ...]]
    targets: Mapping[str, Mapping[str, float]]
    sha256: str


def load_matrix(path: Path | None = None, *, taxonomy: Taxonomy, rules: LabelRules) -> Matrix:
    """Load and validate ``generation_matrix.yaml``.

    Args:
        path: File override (defaults to ``data/spec/generation_matrix.yaml``).
        taxonomy: Taxonomy to validate against.
        rules: Label rules (critical-first check of secondary candidates).

    Returns:
        The validated matrix.

    Raises:
        MatrixError: If the file is malformed or inconsistent with the taxonomy.
    """
    source = path or default_paths().spec_dir / MATRIX_FILE
    text = source.read_text(encoding="utf-8")
    try:
        spec = MatrixSpec.model_validate(yaml.safe_load(text))
    except ValidationError as exc:
        msg = f"{source.name} is malformed: {exc.error_count()} validation error(s)"
        raise MatrixError(msg) from exc
    domains = _domains(spec, taxonomy)
    _validate(spec, taxonomy, rules, domains)
    targets = {dim: _targets(spec, dim, domains[dim]) for dim in spec.draw_order}
    matrix = Matrix(spec=spec, domains=domains, targets=targets, sha256=sha256_hex(text))
    for split in GENERATED_SPLITS:
        intent_quotas(matrix, split, taxonomy, rules)  # raises when a quota does not add up
    return matrix


def _domains(spec: MatrixSpec, tax: Taxonomy) -> dict[str, tuple[str, ...]]:
    domains: dict[str, tuple[str, ...]] = {"intent": tax.values("Intent")}
    for dim, shares in spec.dimensions.items():
        if dim in TAXONOMY_DIMENSIONS:
            values = tax.values(TAXONOMY_DIMENSIONS[dim])
            if shares != _UNIFORM and set(shares) != set(values):
                msg = f"dimension {dim} must list exactly the taxonomy values"
                raise MatrixError(msg)
            domains[dim] = values
        elif shares == _UNIFORM:
            msg = f"dimension {dim} is not a taxonomy enum and cannot be uniform"
            raise MatrixError(msg)
        else:
            domains[dim] = tuple(shares)
    return domains


def _targets(spec: MatrixSpec, dim: str, values: tuple[str, ...]) -> dict[str, float]:
    shares = spec.dimensions[dim]
    if shares == _UNIFORM:
        return {v: 1.0 / len(values) for v in values}
    total = sum(shares.values())
    return {v: shares[v] / total for v in values}


def _validate(
    spec: MatrixSpec, tax: Taxonomy, rules: LabelRules, domains: Mapping[str, tuple[str, ...]]
) -> None:
    problems: list[str] = []
    if spec.taxonomy_version != tax.version:
        problems.append(f"taxonomy_version {spec.taxonomy_version} != {tax.version}")
    problems += [  # T-DATA-provenance, checked before any generation
        f"generator_family {split_spec.generator_family} not allowed in {split}"
        for split, split_spec in spec.splits.items()
        if split_spec.generator_family not in ALLOWED_FAMILIES[split]
    ]
    if set(spec.intents) != set(tax.values("Intent")):
        problems.append("intents must list exactly the taxonomy intents")
    if sorted(spec.draw_order) != sorted(spec.dimensions):
        problems.append("draw_order must list every dimension once")
    if tuple(domains.get("human_request", ())) != HUMAN_REQUEST_KINDS:
        problems.append("human_request must be none/direct/indirect in that order")
    if set(spec.length_words) != set(domains.get("length_bucket", ())):
        problems.append("length_words must cover every length bucket")
    problems.extend(
        f"coverage dimension {dim} is not a dimension"
        for dim in spec.coverage.pairwise
        if dim not in spec.dimensions
    )
    for constraint in spec.constraints:
        for attr, values in (*constraint.when.items(), *constraint.require.items()):
            if attr not in domains or set(values) - set(domains[attr]):
                problems.append(f"constraint {constraint.id}: invalid {attr} values")
    problems.extend(_intent_problems(spec, tax, rules))
    problems.extend(_description_problems(spec, domains))
    for split, minimums in spec.strata_min.items():
        if set(minimums) - set(domains.get("difficulty", ())):
            problems.append(f"strata_min.{split} names unknown difficulties")
    if problems:
        raise MatrixError("; ".join(problems))


def _intent_problems(spec: MatrixSpec, tax: Taxonomy, rules: LabelRules) -> list[str]:
    problems: list[str] = []
    entity_types = set(tax.values("EntityType"))
    for intent, card in spec.intents.items():
        types = set(card.required_entities) | set(card.optional_entities)
        if types - entity_types or types - supported_types():
            problems.append(f"{intent}: unknown or unsupported entity types")
        for other in card.secondary_candidates:
            if not tax.has("Intent", other) or other in {intent, "other_unclear"}:
                problems.append(f"{intent}: invalid secondary candidate {other}")
            elif rules.is_critical(other) and not rules.is_critical(intent):
                problems.append(f"{intent}: critical secondary {other} breaks critical-first")
        if intent != "other_unclear" and not card.scenario_types:
            problems.append(f"{intent}: needs scenario_types for P-B")
    return problems


def _description_problems(spec: MatrixSpec, domains: Mapping[str, tuple[str, ...]]) -> list[str]:
    described = spec.descriptions
    expected = {
        "difficulty": (described.difficulty, domains.get("difficulty", ())),
        "style": (described.style, domains.get("style", ())),
        "subject_style": (described.subject_style, domains.get("subject_style", ())),
        "channel": (described.channel, domains.get("channel", ())),
        "human_request": (described.human_request, HUMAN_REQUEST_KINDS),
    }
    return [
        f"descriptions.{name} must describe every value"
        for name, (texts, values) in expected.items()
        if set(texts) != set(values)
    ]


def intent_quotas(
    matrix: Matrix, split: GeneratedSplit, taxonomy: Taxonomy, rules: LabelRules
) -> dict[str, int]:
    """Per-intent record quotas of one split (spec §9.3, W-m8, A-10).

    Args:
        matrix: Loaded matrix.
        split: Generated split.
        taxonomy: Taxonomy (intent order).
        rules: Label rules (critical set).

    Returns:
        Intent to quota in taxonomy order; the quotas sum to the split's ``n``.

    Raises:
        MatrixError: If the allocation does not add up to ``n``.
    """
    spec = matrix.spec
    allocation: Allocation = getattr(spec.intent_allocation, split)
    total = spec.splits[split].n
    intents = taxonomy.values("Intent")
    if allocation.proportional_to:
        base = intent_quotas(matrix, allocation.proportional_to, taxonomy, rules)
        return largest_remainder({i: float(base[i]) for i in intents}, total)
    quotas: dict[str, int] = {}
    for intent in intents:
        if rules.is_critical(intent):
            quota = allocation.critical_each
        elif intent == "other_unclear":
            quota = allocation.other_unclear
        else:
            quota = allocation.non_critical_each
        quotas[intent] = (quota or 0) + allocation.extra.get(intent, 0)
    if sum(quotas.values()) != total:
        msg = f"{split}: intent quotas sum to {sum(quotas.values())}, expected {total}"
        raise MatrixError(msg)
    return quotas


# --------------------------------------------------------------------------- constraints


class ConstraintSet:
    """Evaluates plausibility rules on (partial) assignments, with a completability lookahead."""

    def __init__(
        self, constraints: Sequence[Constraint], domains: Mapping[str, tuple[str, ...]]
    ) -> None:
        """Compile the rules.

        Args:
            constraints: Rules from the matrix.
            domains: Attribute to values (including ``intent``).
        """
        self._rules = tuple(
            _Rule(
                c.id,
                {k: frozenset(v) for k, v in c.when.items()},
                {k: frozenset(v) for k, v in c.require.items()},
            )
            for c in constraints
        )
        self._by_attribute: dict[str, tuple[_Rule, ...]] = {
            attribute: tuple(
                r for r in self._rules if attribute in r.when or attribute in r.require
            )
            for attribute in domains
        }
        self._domains = domains
        self._memo: dict[frozenset[tuple[str, str]], bool] = {}

    def violated(self, assignment: Mapping[str, str]) -> str | None:
        """Return the id of the first rule the assignment violates.

        A rule fires only once every ``if`` attribute and a required attribute are assigned.

        Args:
            assignment: Attribute to value.

        Returns:
            The violated rule id, or None.
        """
        return next((r.id for r in self._rules if r.violated_by(assignment)), None)

    def _consistent_with(self, assignment: Mapping[str, str], attribute: str, value: str) -> bool:
        extended = {**assignment, attribute: value}
        return not any(r.violated_by(extended) for r in self._by_attribute.get(attribute, ()))

    def consistent(self, assignment: Mapping[str, str]) -> bool:
        """Return whether no rule is violated.

        Args:
            assignment: Attribute to value.

        Returns:
            True when consistent.
        """
        return self.violated(assignment) is None

    def completable(self, assignment: Mapping[str, str]) -> bool:
        """Return whether the partial assignment extends to a full consistent one.

        Args:
            assignment: Partial assignment.

        Returns:
            True when some completion satisfies every rule.
        """
        key = frozenset(assignment.items())
        cached = self._memo.get(key)
        if cached is None:
            cached = self._search(dict(assignment))
            self._memo[key] = cached
        return cached

    def allowed(self, attribute: str, assignment: Mapping[str, str]) -> list[str]:
        """Values of ``attribute`` that keep the assignment completable.

        Args:
            attribute: Attribute to draw.
            assignment: Current partial assignment.

        Returns:
            Allowed values in domain order.
        """
        return [
            v for v in self._domains[attribute] if self.completable({**assignment, attribute: v})
        ]

    def _search(self, assignment: dict[str, str]) -> bool:
        if not self.consistent(assignment):
            return False
        best: tuple[str, list[str]] | None = None
        for attribute in (a for a in self._domains if a not in assignment):
            values = [
                v
                for v in self._domains[attribute]
                if self._consistent_with(assignment, attribute, v)
            ]
            if not values:
                return False
            if best is None or len(values) < len(best[1]):
                best = (attribute, values)
        if best is None:
            return True
        attribute, values = best
        return any(self.completable({**assignment, attribute: v}) for v in values)


@dataclass(frozen=True, slots=True)
class _Rule:
    id: str
    when: Mapping[str, frozenset[str]]
    require: Mapping[str, frozenset[str]]

    def violated_by(self, assignment: Mapping[str, str]) -> bool:
        return all(assignment.get(k) in v for k, v in self.when.items()) and any(
            k in assignment and assignment[k] not in v for k, v in self.require.items()
        )


# --------------------------------------------------------------------------- plan types


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """A feasible intent x value pair below its coverage minimum.

    Attributes:
        intent: Intent.
        dimension: Paired dimension.
        value: Dimension value.
        count: Cells that have the pair.
        required: Coverage minimum.
    """

    intent: str
    dimension: str
    value: str
    count: int
    required: int


@dataclass(frozen=True, slots=True)
class PlanReport:
    """Diagnostics of one plan.

    Attributes:
        quotas: Intent to quota.
        strata: Difficulty to count.
        strata_shortfalls: ``strata_min`` violations (T-DATA-strata).
        coverage_gaps: Pairs still below the minimum after the top-up.
        feasible_pairs: Number of feasible intent x value pairs with a minimum.
        top_up_swaps: Values moved by the top-up pass.
        marginals: Dimension to value to observed share.
    """

    quotas: Mapping[str, int]
    strata: Mapping[str, int]
    strata_shortfalls: tuple[str, ...]
    coverage_gaps: tuple[CoverageGap, ...]
    feasible_pairs: int
    top_up_swaps: int
    marginals: Mapping[str, Mapping[str, float]]


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    """A deterministic list of cells for one split.

    Attributes:
        split: Split.
        cells: Cells in generation order (``seq`` 0..n-1; ids reveal no label).
        report: Coverage and strata diagnostics.
        matrix_sha256: Hash of the matrix file used.
        plan_sha256: Hash of every cell (checked when a run resumes).
    """

    split: GeneratedSplit
    cells: tuple[GenerationCell, ...]
    report: PlanReport
    matrix_sha256: str
    plan_sha256: str


@dataclass(frozen=True, slots=True)
class PlanInputs:
    """Everything a plan depends on besides the split.

    Attributes:
        matrix: Loaded matrix.
        taxonomy: Taxonomy.
        rules: Label rules.
        facts: Fact sheet.
        pools: Pools of the split's pool group.
    """

    matrix: Matrix
    taxonomy: Taxonomy
    rules: LabelRules
    facts: FactSheet
    pools: Pools


@dataclass(slots=True)
class _Tally:
    split_counts: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    pair_counts: dict[str, dict[str, Counter[str]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(Counter))
    )
    drawn: int = 0

    def add(self, dims: Mapping[str, str]) -> None:
        intent = dims["intent"]
        for dim, value in dims.items():
            if dim != "intent":
                self.split_counts[dim][value] += 1
                self.pair_counts[intent][dim][value] += 1
        self.drawn += 1

    def move(self, intent: str, dim: str, old: str, new: str) -> None:
        self.split_counts[dim][old] -= 1
        self.split_counts[dim][new] += 1
        self.pair_counts[intent][dim][old] -= 1
        self.pair_counts[intent][dim][new] += 1


@dataclass(frozen=True, slots=True)
class _CellFlags:
    lexical_avoid: bool
    pii: bool
    legal_threat: bool
    greeting: bool
    noise: bool


# --------------------------------------------------------------------------- sampler


def build_plan(inputs: PlanInputs, split: GeneratedSplit) -> GenerationPlan:
    """Draw the full, deterministic plan of one split.

    Args:
        inputs: Matrix, taxonomy, rules, fact sheet and pools.
        split: Generated split.

    Returns:
        The plan and its diagnostics.

    Raises:
        MatrixError: If the pools do not match the split or a cell cannot be drawn.
    """
    spec = inputs.matrix.spec
    split_spec = spec.splits[split]
    if inputs.pools.name != split_spec.pool:
        msg = f"{split} uses pool {split_spec.pool!r}, got {inputs.pools.name!r}"
        raise MatrixError(msg)
    constraints = ConstraintSet(spec.constraints, inputs.matrix.domains)
    quotas = intent_quotas(inputs.matrix, split, inputs.taxonomy, inputs.rules)
    demand = coverage_demand(inputs.matrix, constraints, quotas, split_spec.coverage_min_per_pair)
    order = _interleave(quotas, spec.seed, split)
    tally = _Tally()
    drawn: list[Dims] = []
    for intent, k in order:
        rng = rng_for(spec.seed, split, "dims", intent, k)
        dims = _draw(intent, rng, tally, demand, inputs.matrix, constraints)
        tally.add(dims)
        drawn.append(dims)
    swaps = _top_up(drawn, tally, demand, constraints)
    flags = _flags(order, inputs, split)
    cells = tuple(
        _cell(seq, dims, k, flags[seq], inputs, split, constraints)
        for seq, (dims, (_, k)) in enumerate(zip(drawn, order, strict=True))
    )
    payload = json.dumps([c.model_dump(mode="json") for c in cells], sort_keys=True)
    return GenerationPlan(
        split=split,
        cells=cells,
        report=_report(quotas, drawn, tally, demand, swaps, spec.strata_min.get(split, {})),
        matrix_sha256=inputs.matrix.sha256,
        plan_sha256=sha256_hex(payload),
    )


def coverage_demand(
    matrix: Matrix, constraints: ConstraintSet, quotas: Mapping[str, int], minimum: int
) -> dict[tuple[str, str, str], int]:
    """Coverage minimum of every feasible intent x value pair.

    Args:
        matrix: Loaded matrix (coverage dimensions and domains).
        constraints: Constraint set (feasibility).
        quotas: Intent quotas (a minimum never exceeds what the quota can hold).
        minimum: ``coverage_min_per_pair`` of the split.

    Returns:
        ``(intent, dimension, value)`` to required count; infeasible pairs are absent.
    """
    demand: dict[tuple[str, str, str], int] = {}
    if minimum <= 0:
        return demand
    for intent, quota in quotas.items():
        for dim in matrix.spec.coverage.pairwise:
            feasible = [
                v
                for v in matrix.domains[dim]
                if constraints.completable({"intent": intent, dim: v})
            ]
            per_value = min(minimum, quota // max(1, len(feasible)))
            demand.update({(intent, dim, value): per_value for value in feasible})
    return demand


def _interleave(quotas: Mapping[str, int], seed: int, split: str) -> list[tuple[str, int]]:
    order: list[tuple[str, int]] = []
    for round_index in range(max(quotas.values(), default=0)):
        members = [intent for intent, quota in quotas.items() if round_index < quota]
        rng_for(seed, split, "round", round_index).shuffle(members)
        order.extend((intent, round_index) for intent in members)
    return order


def _draw(
    intent: str,
    rng: random.Random,
    tally: _Tally,
    demand: Demand,
    matrix: Matrix,
    constraints: ConstraintSet,
) -> Dims:
    assignment: Dims = {"intent": intent}
    for dim in matrix.spec.draw_order:
        allowed = constraints.allowed(dim, assignment)
        if not allowed:
            msg = f"no feasible {dim} value for intent {intent}"
            raise MatrixError(msg)
        pairs = tally.pair_counts[intent][dim]
        unmet = [v for v in allowed if pairs[v] < demand.get((intent, dim, v), 0)]
        targets = matrix.targets[dim]
        if unmet:
            pool, weights = unmet, [targets[v] for v in unmet]
        else:
            drawn = max(1, tally.drawn)
            pool = allowed
            weights = [
                targets[v] * targets[v] / (tally.split_counts[dim][v] / drawn + _SMOOTHING)
                for v in allowed
            ]
        assignment[dim] = rng.choices(pool, weights=weights)[0]
    return assignment


def _top_up(drawn: list[Dims], tally: _Tally, demand: Demand, constraints: ConstraintSet) -> int:
    swaps = 0
    for (intent, dim, value), required in demand.items():
        while tally.pair_counts[intent][dim][value] < required:
            donor = _donor(drawn, tally, demand, constraints, (intent, dim, value))
            if donor is None:
                break
            tally.move(intent, dim, donor[dim], value)
            donor[dim] = value
            swaps += 1
    return swaps


def _donor(
    drawn: Sequence[Dims],
    tally: _Tally,
    demand: Demand,
    constraints: ConstraintSet,
    pair: tuple[str, str, str],
) -> Dims | None:
    intent, dim, value = pair
    for cell in drawn:
        if cell["intent"] != intent or cell[dim] == value:
            continue
        old = cell[dim]
        if tally.pair_counts[intent][dim][old] <= demand.get((intent, dim, old), 0):
            continue
        if constraints.consistent({**cell, dim: value}):
            return cell
    return None


def _flags(order: Sequence[tuple[str, int]], inputs: PlanInputs, split: str) -> list[_CellFlags]:
    spec = inputs.matrix.spec
    rules = inputs.rules
    by_intent: dict[str, list[int]] = defaultdict(list)
    for seq, (intent, _) in enumerate(order):
        by_intent[intent].append(seq)
    names = ("lexical", "pii", "legal", "greeting", "noise")
    chosen: dict[str, set[int]] = {name: set() for name in names}
    for intent, seqs in by_intent.items():
        shares = {
            "lexical": spec.flags.lexical_avoid[
                "critical" if rules.is_critical(intent) else "other"
            ],
            "pii": spec.flags.pii_placeholders,
            "legal": spec.flags.legal_threat_inside_billing
            if intent in rules.billing_intents
            else 0.0,
            "greeting": spec.flags.greeting_allowed,
            "noise": spec.flags.noise,
        }
        for name, share in shares.items():
            count = largest_remainder({"yes": share, "no": 1.0 - share}, len(seqs))["yes"]
            chosen[name].update(rng_for(spec.seed, split, "flag", name, intent).sample(seqs, count))
    return [
        _CellFlags(
            lexical_avoid=seq in chosen["lexical"],
            pii=seq in chosen["pii"],
            legal_threat=seq in chosen["legal"],
            greeting=seq in chosen["greeting"],
            noise=seq in chosen["noise"],
        )
        for seq in range(len(order))
    ]


def _cell(
    seq: int,
    dims: Mapping[str, str],
    k: int,
    flags: _CellFlags,
    inputs: PlanInputs,
    split: GeneratedSplit,
    constraints: ConstraintSet,
) -> GenerationCell:
    spec = inputs.matrix.spec
    split_spec = spec.splits[split]
    intent, difficulty = dims["intent"], dims["difficulty"]
    card = spec.intents[intent]
    cell_id = f"{SPLIT_CODES[split]}-c{seq:05d}"
    rng = rng_for(spec.seed, split, "cell", cell_id)
    company = rng.choice(inputs.pools.companies_on(dims["plan"]) or list(inputs.pools.companies))
    persona = rng.choice(inputs.pools.personas)
    received_at = _received_at(spec.entity_values.received_window, rng)
    # A secondary intent must be plausible on the cell's plan too (e.g. no refund on free).
    candidates = tuple(
        c
        for c in card.secondary_candidates
        if constraints.consistent({"intent": c, "plan": dims["plan"]})
    )
    if difficulty == "multi_intent" and not candidates:
        msg = f"{intent}: no secondary candidate is plausible on plan {dims['plan']}"
        raise MatrixError(msg)
    secondaries = _secondaries(difficulty, candidates, spec, rng)
    churn_cue = _churn_cue(intent, secondaries, spec, rng)
    competitor = rng.choice(inputs.pools.competitors) if churn_cue == "competitor" else None
    needs_info = difficulty == "needs_info"
    types = [
        *(() if needs_info else card.required_entities),
        *_optional(card.optional_entities, rng),
    ]
    ctx = EntityContext(
        intent=intent,
        product_area=dims["product_area"],
        plan=dims["plan"],
        company=company,
        received_at=received_at,
        facts=inputs.facts,
        values=_value_lists(spec.entity_values),
        error_code_prefixes=card.error_code_prefixes,
        competitor=competitor,
    )
    entities = sample_entities([*types, *(["competitor_name"] if competitor else [])], ctx, rng)
    feature = next((e.label.value for e in entities if e.label.type == "feature_name"), None)
    if feature is None:
        options = inputs.facts.features_for(dims["product_area"], dims["plan"])
        feature = rng.choice(options).name if options else None
    use_scenarios = split_spec.prompt_family == "P-B" and bool(card.scenario_types)
    injection = (
        rng.choice(inputs.pools.injections) if difficulty == "adversarial_injection" else None
    )
    displays = [e.display for e in entities]
    # A card never contradicts itself: a banned word that a required value or the injected text
    # contains (e.g. "GDPR" vs "GDPR Art. 15") is not banned for that cell.
    banned = _compatible_banned_words(
        card.banned_words if flags.lexical_avoid else (), [*displays, injection or ""]
    )
    return GenerationCell.model_validate(
        {
            "cell_id": cell_id,
            "split": split,
            "seq": seq,
            **{d: dims[d] for d in ("intent", "difficulty", "product_area", "plan", "channel")},
            **{d: dims[d] for d in ("sentiment", "style", "length_bucket", "subject_style")},
            "human_request": dims["human_request"],
            "secondary_intents": secondaries,
            "secondary_order": _weighted(spec.secondary_order, rng) if secondaries else None,
            "target_words": rng.randint(*spec.length_words[dims["length_bucket"]]),
            "churn_cue": churn_cue,
            "competitor": competitor,
            "priority_hint": inputs.rules.derive_priority(intent, severe=difficulty == "severe"),
            "information_sufficient": not needs_info and intent != "other_unclear",
            "lexical_avoid": flags.lexical_avoid,
            "banned_words": banned,
            "greeting_allowed": flags.greeting,
            "noise": flags.noise,
            "pii_placeholders": _placeholders(flags.pii, intent, inputs.rules, rng),
            "legal_threat": flags.legal_threat,
            "injection": injection,
            "entities": [e.label for e in entities],
            "display_values": displays,
            "omissions": card.needs_info_omit if needs_info or intent == "other_unclear" else (),
            "history_len": _history_len(dims["channel"], churn_cue, spec.history_len, rng),
            "feature_name": feature,
            "scenario_type": rng.choice(card.scenario_types) if use_scenarios else None,
            "persona_id": persona.persona_id,
            "company_id": company.company_id,
            "template_id": split_spec.templates[
                (k + inputs.taxonomy.values("Intent").index(intent)) % len(split_spec.templates)
            ],
            "scenario_seed": derive_seed(spec.seed, split, cell_id, "scenario"),
            "received_at": received_at,
        }
    )


def _compatible_banned_words(words: Sequence[str], required: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        word
        for word in words
        if not any(
            re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) for text in required
        )
    )


def _secondaries(
    difficulty: str, candidates: tuple[str, ...], spec: MatrixSpec, rng: random.Random
) -> tuple[str, ...]:
    if difficulty != "multi_intent" or not candidates:
        return ()
    count = 2 if _weighted(spec.secondary_count, rng) == "two" and len(candidates) > 1 else 1
    return tuple(rng.sample(list(candidates), count))


def _churn_cue(
    intent: str, secondaries: Sequence[str], spec: MatrixSpec, rng: random.Random
) -> str:
    if intent == "cancellation_request":
        return _weighted(spec.churn_cues.cancellation, rng)
    if "cancellation_request" in secondaries:
        return "explicit_cancel"
    return _weighted(spec.churn_cues.other, rng)


def _placeholders(
    flagged: bool, intent: str, rules: LabelRules, rng: random.Random
) -> tuple[str, ...]:
    if not flagged:
        return ()
    options = [*PII_PLACEHOLDERS, *([CARD_PLACEHOLDER] if intent in rules.billing_intents else [])]
    return tuple(sorted(rng.sample(options, rng.randint(1, 2))))


def _history_len(channel: str, churn_cue: str, history: HistorySpec, rng: random.Random) -> int:
    length = 0
    if channel == "chat_transcript":
        length = rng.randint(*history.chat_transcript)
    elif channel == "email" and rng.random() < history.email_followup_share:
        length = rng.randint(*history.email_followup)
    return max(length, 2) if churn_cue == "repeated_contact" else length


def _optional(types: tuple[str, ...], rng: random.Random) -> list[str]:
    if not types:
        return []
    return rng.sample(list(types), rng.randint(0, min(MAX_OPTIONAL_ENTITIES, len(types))))


def _received_at(window: tuple[date, date], rng: random.Random) -> datetime:
    start = datetime(window[0].year, window[0].month, window[0].day, tzinfo=UTC)
    span_minutes = (window[1] - window[0]).days * 24 * 60
    return start + timedelta(minutes=rng.randint(0, span_minutes))


def _value_lists(values: EntityValues) -> dict[str, tuple[str, ...]]:
    return {
        "browser": values.browser,
        "os": values.os,
        "legal_reference": values.legal_reference,
        "steps_already_tried": values.steps_already_tried,
        "user_count_affected": tuple(str(v) for v in values.user_count_affected),
        "timestamp_hours": tuple(str(v) for v in values.timestamp_hours),
    }


def _weighted[K: str](shares: Mapping[K, float], rng: random.Random) -> K:
    keys = list(shares)
    return rng.choices(keys, weights=[shares[k] for k in keys])[0]


def _report(
    quotas: Mapping[str, int],
    drawn: Sequence[Mapping[str, str]],
    tally: _Tally,
    demand: Demand,
    swaps: int,
    strata_min: Mapping[str, int],
) -> PlanReport:
    strata = Counter(cell["difficulty"] for cell in drawn)
    gaps = tuple(
        CoverageGap(intent, dim, value, tally.pair_counts[intent][dim][value], required)
        for (intent, dim, value), required in demand.items()
        if tally.pair_counts[intent][dim][value] < required
    )
    total = max(1, len(drawn))
    marginals = {
        dim: {value: count / total for value, count in sorted(counts.items())}
        for dim, counts in sorted(tally.split_counts.items())
    }
    return PlanReport(
        quotas=dict(quotas),
        strata=dict(sorted(strata.items())),
        strata_shortfalls=tuple(check_strata(strata, strata_min)),
        coverage_gaps=gaps,
        feasible_pairs=len(demand),
        top_up_swaps=swaps,
        marginals=marginals,
    )


def check_strata(counts: Mapping[str, int], minimums: Mapping[str, int]) -> list[str]:
    """T-DATA-strata (BR-038): compare difficulty counts with the minimums.

    Args:
        counts: Difficulty to observed count.
        minimums: Difficulty to required minimum.

    Returns:
        Shortfall messages; empty when every stratum is met.
    """
    return [
        f"{name}: {counts.get(name, 0)} < {minimum}"
        for name, minimum in minimums.items()
        if counts.get(name, 0) < minimum
    ]
