"""Resumable, budget-capped generation of train/val (Family A) and test_synth (Family B).

``python -m tw_ml.datagen generate --split train --family A --n 50 [--dry-run] [--budget-usd 5]``

* The plan (:mod:`tw_ml.datagen.matrix`) is deterministic; a run processes the next ``n`` cells
  that are neither accepted nor out of attempts, so a crashed or stopped run simply continues.
* Output goes to ``data/generated/<split>/`` (gitignored): ``records.jsonl`` (accepted),
  ``quarantine.jsonl`` (rejected attempts with findings), ``costs.jsonl`` (token ledger) and
  ``checkpoint.json``. The JSONL files are append-only; progress is rebuilt from them.
* Every call is priced from the dated price table first; a call that could exceed the run cap
  (``--budget-usd``) or the total budget (all ledgers, $15) is not made.
* ``--dry-run`` renders the prompts to ``dry_run/`` and estimates the cost; it needs no API key
  and makes no network call.
* Family A records keep the generator's proposed labels (``label_basis=llm_proposal``); Family B
  records get scenario-spec labels (``label_basis=scenario_spec``) because the test generator
  never labels. Both stay ``generator_proposed`` until a human verifies them.
* A real run refuses to start when the terms snapshot is older than 30 days, unless the owner
  passes ``--terms-reviewed`` after re-reading the vendor terms.
"""

import json
import os
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import ValidationError

from tw_ml.datagen.alloc import rng_for
from tw_ml.datagen.factsheet import FactSheet, load_fact_sheet
from tw_ml.datagen.labelrules import LabelRules, load_label_rules
from tw_ml.datagen.matrix import (
    GeneratedSplit,
    GenerationPlan,
    Matrix,
    PlanInputs,
    build_plan,
    load_matrix,
)
from tw_ml.datagen.noise import add_noise
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.pii import apply_replacements, mask_text
from tw_ml.datagen.pools import SPLIT_POOL, Company, Pools, load_pools
from tw_ml.datagen.prompts import (
    PromptContext,
    PromptFamily,
    RenderedPrompt,
    load_prompt_family,
    render_pa,
    render_pb_stage1,
    render_pb_stage2,
)
from tw_ml.datagen.providers import (
    Budget,
    ChatProvider,
    ChatRequest,
    DatagenConfig,
    Family,
    PriceTable,
    ProviderAuthError,
    ProviderError,
    RequestConfig,
    load_datagen_config,
    load_price_table,
)
from tw_ml.datagen.records import (
    SPLIT_CODES,
    AccountMetadata,
    DatasetRecord,
    EntityLabel,
    GenerationCell,
    PreviousMessage,
    ProductMetadata,
    Provenance,
    RecordModel,
    ScenarioFacts,
    SelfCheck,
    TicketPayload,
    TriageLabels,
)
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy
from tw_ml.datagen.text import content_sha256, sha256_hex
from tw_ml.datagen.validate import (
    Finding,
    ValidationContext,
    entity_present,
    has_errors,
    validate_record,
)

SPLIT_FAMILY: Final[Mapping[GeneratedSplit, Family]] = {"train": "A", "val": "A", "test_synth": "B"}
RECORDS_FILE: Final = "records.jsonl"
QUARANTINE_FILE: Final = "quarantine.jsonl"
COSTS_FILE: Final = "costs.jsonl"
CHECKPOINT_FILE: Final = "checkpoint.json"
DRY_RUN_DIR: Final = "dry_run"
TERMS_DATE: Final = re.compile(r"(\d{4}-\d{2}-\d{2})\.md$")
RAW_OUTPUT_LIMIT: Final = 20_000
HISTORY_GAP_HOURS: Final = 6
StopReason = Literal["completed", "budget", "auth", "nothing_to_do"]
Clock = Callable[[], datetime]
LabelBasis = Literal["llm_proposal", "scenario_spec"]

_CHURN_SIGNAL: Final[Mapping[str, str]] = {
    "vague_alternatives": "mentions looking at other tools",
    "repeated_contact": "says they have contacted support about this before",
    "explicit_cancel": "states they will stop using Taskmoor",
    "competitor": "says they are moving to {competitor}",
    "ultimatum": "gives an ultimatum to leave unless it is resolved",
}


def utc_now() -> datetime:
    """Current UTC time (the default clock).

    Returns:
        An aware datetime.
    """
    return datetime.now(UTC)


class GenerationError(RuntimeError):
    """Raised when a run cannot start (wrong family, stale terms, changed plan...)."""


class OutputParseError(ValueError):
    """The generator's reply contained no JSON object."""


# --------------------------------------------------------------------------- generator outputs


class DraftMessage(RecordModel):
    """A prior thread message as generators return it (timestamps are added by code)."""

    author: Literal["customer", "agent"]
    body: str


class PAOutput(RecordModel):
    """P-A reply: the ticket, the proposed labels and the generator's self-check."""

    subject: str
    message: str
    previous_messages: tuple[DraftMessage, ...] = ()
    proposed_labels: TriageLabels
    self_check: SelfCheck


class PBMessage(RecordModel):
    """P-B stage-2 reply: the customer's ticket only (no labels)."""

    subject: str
    message: str
    previous_messages: tuple[DraftMessage, ...] = ()


# --------------------------------------------------------------------------- context


@dataclass(frozen=True, slots=True)
class GenerationContext:
    """Everything a run of one split needs.

    Attributes:
        paths: Repository paths.
        split: Split generated.
        taxonomy: Taxonomy.
        rules: Label rules.
        matrix: Generation matrix.
        facts: Fact sheet.
        pools: The split's pools.
        family: Prompt family of the split.
        config: Datagen config.
        prices: Dated price table.
    """

    paths: RepoPaths
    split: GeneratedSplit
    taxonomy: Taxonomy
    rules: LabelRules
    matrix: Matrix
    facts: FactSheet
    pools: Pools
    family: PromptFamily
    config: DatagenConfig
    prices: PriceTable

    @property
    def prompt_context(self) -> PromptContext:
        """Prompt rendering context."""
        return PromptContext(self.taxonomy, self.rules, self.matrix, self.facts, self.pools)

    @property
    def validation_context(self) -> ValidationContext:
        """Rule-checker context (persona names may only appear masked)."""
        names = tuple(n for p in self.pools.personas for n in (p.first_name, p.last_name))
        return ValidationContext(self.rules, self.facts, known_names=names)

    @property
    def prompt_family(self) -> Literal["P-A", "P-B"]:
        """The split's prompt family."""
        return self.matrix.spec.splits[self.split].prompt_family

    def plan_inputs(self) -> PlanInputs:
        """Inputs for :func:`tw_ml.datagen.matrix.build_plan`.

        Returns:
            Plan inputs.
        """
        return PlanInputs(self.matrix, self.taxonomy, self.rules, self.facts, self.pools)


def load_context(paths: RepoPaths, split: GeneratedSplit) -> GenerationContext:
    """Load every spec file a run needs.

    Args:
        paths: Repository paths.
        split: Split to generate.

    Returns:
        The context.
    """
    taxonomy = load_taxonomy(paths.schemas_dir)
    rules = load_label_rules(paths.spec_dir / "label_rules.v1.yaml", taxonomy)
    matrix = load_matrix(paths.spec_dir / "generation_matrix.yaml", taxonomy=taxonomy, rules=rules)
    config = load_datagen_config(paths.configs_dir / "datagen.yaml")
    return GenerationContext(
        paths=paths,
        split=split,
        taxonomy=taxonomy,
        rules=rules,
        matrix=matrix,
        facts=load_fact_sheet(paths.spec_dir / "fact_sheet.v1.md", taxonomy),
        pools=load_pools(SPLIT_POOL[split], paths.pools_dir),
        family=load_prompt_family(matrix.spec.splits[split].prompt_file, paths.prompts_dir),
        config=config,
        prices=load_price_table(paths.root / config.price_table),
    )


# --------------------------------------------------------------------------- guards


def check_terms_snapshot(
    config: DatagenConfig, repo_root: Path, today: date, *, reviewed: bool
) -> None:
    """Refuse a real run on a missing or stale vendor-terms snapshot.

    Args:
        config: Datagen config (snapshot path and maximum age).
        repo_root: Repository root.
        today: Current date.
        reviewed: The owner re-read the terms (``--terms-reviewed``).

    Raises:
        GenerationError: If the snapshot is missing or undated, or older than allowed and not
            re-reviewed.
    """
    snapshot = repo_root / config.terms_snapshot_id
    if not snapshot.is_file():
        msg = f"terms snapshot {config.terms_snapshot_id} does not exist"
        raise GenerationError(msg)
    match = TERMS_DATE.search(snapshot.name)
    if match is None:
        msg = f"terms snapshot {snapshot.name} has no YYYY-MM-DD date in its name"
        raise GenerationError(msg)
    age = (today - date.fromisoformat(match.group(1))).days
    if age > config.terms_max_age_days and not reviewed:
        msg = (
            f"terms snapshot is {age} days old (limit {config.terms_max_age_days}); re-verify "
            "the vendor terms (docs/legal/README.md) and pass --terms-reviewed"
        )
        raise GenerationError(msg)


def check_family(split: GeneratedSplit, family: Family, matrix: Matrix) -> None:
    """Refuse a family/split mix-up (test_synth must never come from Family A, and so on).

    Args:
        split: Split.
        family: Requested family.
        matrix: Matrix (split specs).

    Raises:
        GenerationError: If the family does not generate this split.
    """
    expected = matrix.spec.splits[split].family
    if expected != family:
        msg = f"split {split} is generated by Family {expected}, not {family}"
        raise GenerationError(msg)


# --------------------------------------------------------------------------- files and state


@dataclass(slots=True)
class RunState:
    """Progress rebuilt from the append-only output files.

    Attributes:
        accepted: Cell ids with an accepted record.
        attempts: Cell id to attempts made so far.
    """

    accepted: set[str] = field(default_factory=set)
    attempts: dict[str, int] = field(default_factory=dict)

    def tries(self, cell_id: str) -> int:
        """Attempts made for a cell.

        Args:
            cell_id: Cell id.

        Returns:
            Attempt count.
        """
        return self.attempts.get(cell_id, 0)


@dataclass(slots=True)
class RunSummary:
    """What a run did.

    Attributes:
        split: Split.
        family: Family.
        out_dir: Output directory.
        processed: Cells attempted (or rendered, in a dry run).
        accepted: Records accepted in this run.
        quarantined: Attempts quarantined in this run.
        spent_usd: Actual spend of this run.
        estimated_usd: Dry-run cost estimate of the selected cells.
        stop_reason: Why the run ended.
        dry_run: Whether nothing was sent.
    """

    split: str
    family: str
    out_dir: Path
    processed: int = 0
    accepted: int = 0
    quarantined: int = 0
    spent_usd: Decimal = Decimal(0)
    estimated_usd: Decimal = Decimal(0)
    stop_reason: StopReason = "completed"
    dry_run: bool = False


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Iterate the JSON objects of a JSONL file (a missing file yields nothing).

    Args:
        path: File.

    Yields:
        One object per non-empty line.
    """
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def append_jsonl(path: Path, row: Mapping[str, object] | str) -> None:
    """Append one JSON line and flush it to disk.

    Args:
        path: File (created with its directory when missing).
        row: Object to serialize, or an already serialized JSON string.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = row if isinstance(row, str) else json.dumps(row, sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_state(out_dir: Path) -> RunState:
    """Rebuild progress from ``records.jsonl`` and ``quarantine.jsonl``.

    Args:
        out_dir: Split output directory.

    Returns:
        The state.
    """
    state = RunState()
    for row in read_jsonl(out_dir / RECORDS_FILE):
        cell_id = (row.get("provenance") or {}).get("cell_id")
        if isinstance(cell_id, str):
            state.accepted.add(cell_id)
            state.attempts[cell_id] = state.tries(cell_id) + 1
    for row in read_jsonl(out_dir / QUARANTINE_FILE):
        cell_id = row.get("cell_id")
        if isinstance(cell_id, str):
            state.attempts[cell_id] = state.tries(cell_id) + 1
    return state


def ledger_total(root: Path) -> Decimal:
    """Sum every ``costs.jsonl`` under a directory (the base of the total budget).

    Args:
        root: ``data/generated``.

    Returns:
        USD spent so far.
    """
    total = Decimal(0)
    for path in sorted(root.glob(f"**/{COSTS_FILE}")):
        for row in read_jsonl(path):
            total += Decimal(str(row.get("cost_usd", "0")))
    return total


def write_checkpoint(out_dir: Path, payload: Mapping[str, object]) -> None:
    """Atomically replace ``checkpoint.json``.

    Args:
        out_dir: Split output directory.
        payload: Checkpoint content.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    temp = out_dir / f"{CHECKPOINT_FILE}.tmp"
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(out_dir / CHECKPOINT_FILE)


def check_plan_matches(out_dir: Path, plan: GenerationPlan) -> None:
    """Refuse to resume onto a different plan (a matrix, pool or seed change).

    Args:
        out_dir: Split output directory.
        plan: Current plan.

    Raises:
        GenerationError: If the checkpoint names another plan.
    """
    path = out_dir / CHECKPOINT_FILE
    if not path.is_file():
        return
    recorded = json.loads(path.read_text(encoding="utf-8")).get("plan_sha256")
    if recorded not in (None, plan.plan_sha256):
        msg = "the plan changed since this output directory was started; use a new --out"
        raise GenerationError(msg)


def select_cells(
    plan: GenerationPlan, state: RunState, n: int, max_attempts: int
) -> list[GenerationCell]:
    """The next ``n`` cells that are neither accepted nor out of attempts.

    Args:
        plan: Plan.
        state: Current progress.
        n: Cells to take.
        max_attempts: Attempts allowed per cell.

    Returns:
        Cells in plan order.
    """
    selected: list[GenerationCell] = []
    for cell in plan.cells:
        if len(selected) >= n:
            break
        if cell.cell_id not in state.accepted and state.tries(cell.cell_id) < max_attempts:
            selected.append(cell)
    return selected


# --------------------------------------------------------------------------- run


@dataclass(frozen=True, slots=True)
class RunOptions:
    """Options of one run.

    Attributes:
        split: Split.
        family: Family (must match the split).
        n: Cells to process.
        dry_run: Render prompts only.
        budget_usd: Run cap (defaults to what is left of the total budget).
        out_dir: Output directory override.
        terms_reviewed: The owner re-reviewed stale terms.
        ledger_dir: Directory whose ``costs.jsonl`` files count toward the total budget
            (defaults to ``data/generated``).
    """

    split: GeneratedSplit
    family: Family
    n: int
    dry_run: bool = False
    budget_usd: Decimal | None = None
    out_dir: Path | None = None
    terms_reviewed: bool = False
    ledger_dir: Path | None = None


@dataclass(slots=True)
class Attempt:
    """Outcome of one generation attempt.

    Attributes:
        record: The accepted record, or None.
        findings: Rule-checker findings (errors explain a rejection).
        stage: Stage that produced the outcome (``pa``, ``pb1``, ``pb2``, ``provider``...).
        raw: Raw generator output of that stage (kept in quarantine for prompt iteration).
        error: Provider error text (content-free).
    """

    record: DatasetRecord | None = None
    findings: list[Finding] = field(default_factory=list)
    stage: str = ""
    raw: str = ""
    error: str = ""


class BudgetStopError(Exception):
    """The next call could exceed the run or total budget."""


@dataclass(frozen=True, slots=True)
class CellJob:
    """Everything needed to generate one cell.

    Attributes:
        ctx: Generation context.
        cell: Plan cell.
        provider: Chat provider.
        budget: Shared budget of the run.
        out_dir: Output directory.
        clock: Current-time function.
    """

    ctx: GenerationContext
    cell: GenerationCell
    provider: ChatProvider
    budget: Budget
    out_dir: Path
    clock: Clock


def run_generation(
    ctx: GenerationContext,
    options: RunOptions,
    provider: ChatProvider | None,
    clock: Clock = utc_now,
) -> RunSummary:
    """Generate (or dry-run) the next ``n`` cells of a split.

    Args:
        ctx: Loaded context.
        options: Run options.
        provider: Chat provider (None only for a dry run).
        clock: Current time (injectable for tests).

    Returns:
        The run summary.

    Raises:
        GenerationError: If the run may not start.
    """
    check_family(options.split, options.family, ctx.matrix)
    out_dir = options.out_dir or ctx.paths.generated_dir / options.split
    summary = RunSummary(
        split=options.split, family=options.family, out_dir=out_dir, dry_run=options.dry_run
    )
    plan = build_plan(ctx.plan_inputs(), options.split)
    state = load_state(out_dir)
    cells = select_cells(plan, state, options.n, ctx.config.max_attempts_per_cell)
    if not cells:
        summary.stop_reason = "nothing_to_do"
        return summary
    if options.dry_run:
        return dry_run(ctx, cells, summary)
    if provider is None:
        msg = "a real run needs a provider"
        raise GenerationError(msg)
    check_terms_snapshot(
        ctx.config, ctx.paths.root, clock().date(), reviewed=options.terms_reviewed
    )
    check_plan_matches(out_dir, plan)
    spent_before = ledger_total(options.ledger_dir or ctx.paths.generated_dir)
    total_cap = ctx.config.budget_usd_total
    budget = Budget(
        run_cap=options.budget_usd or max(Decimal(0), total_cap - spent_before),
        total_cap=total_cap,
        spent_before=spent_before,
    )
    for cell in cells:
        summary.processed += 1
        job = CellJob(ctx, cell, provider, budget, out_dir, clock)
        reason = _generate_cell(job, state, summary)
        write_checkpoint(out_dir, _checkpoint(plan, options, summary, state, budget, clock))
        if reason is not None:
            summary.stop_reason = reason
            break
    summary.spent_usd = budget.spent_run
    return summary


def _generate_cell(job: CellJob, state: RunState, summary: RunSummary) -> StopReason | None:
    cell_id = job.cell.cell_id
    while state.tries(cell_id) < job.ctx.config.max_attempts_per_cell:
        attempt_no = state.tries(cell_id) + 1
        try:
            attempt = attempt_cell(job)
        except BudgetStopError:
            return "budget"
        except ProviderAuthError as exc:
            _quarantine(job.out_dir, job.cell, attempt_no, Attempt(stage="auth", error=str(exc)))
            return "auth"
        except ProviderError as exc:
            attempt = Attempt(stage="provider", error=str(exc))
        state.attempts[cell_id] = attempt_no
        if attempt.record is not None:
            append_jsonl(job.out_dir / RECORDS_FILE, attempt.record.model_dump_json())
            state.accepted.add(cell_id)
            summary.accepted += 1
            return None
        _quarantine(job.out_dir, job.cell, attempt_no, attempt)
        summary.quarantined += 1
    return None


def attempt_cell(job: CellJob) -> Attempt:
    """Run one attempt for a cell (one P-A call, or the two P-B stages).

    Args:
        job: The cell job.

    Returns:
        The outcome.

    Raises:
        BudgetStopError: If a call could exceed the budget.
        ProviderError: If a provider call fails after its retries.
    """
    ctx, cell = job.ctx, job.cell
    pctx = ctx.prompt_context
    if ctx.prompt_family == "P-A":
        params = ctx.config.families["A"].requests["default"]
        raw = _call(job, _request(render_pa(cell, pctx, ctx.family), params, cell, "pa"))
        return build_pa_attempt(job, raw)
    requests = ctx.config.families["B"].requests
    stage1 = _request(render_pb_stage1(cell, pctx, ctx.family), requests["stage1"], cell, "pb1")
    raw1 = _call(job, stage1)
    try:
        scenario = ScenarioFacts.model_validate_json(extract_json(raw1)[0], strict=True)
    except (OutputParseError, ValidationError) as exc:
        return Attempt(findings=[_schema_finding(exc, "scenario")], stage="pb1", raw=raw1)
    prompt2 = render_pb_stage2(cell, pctx, ctx.family, scenario)
    raw2 = _call(job, _request(prompt2, requests["stage2"], cell, "pb2"))
    return build_pb_attempt(job, scenario, raw2)


def _call(job: CellJob, request: ChatRequest) -> str:
    ctx, provider = job.ctx, job.provider
    estimate = ctx.prices.estimate(
        request.prompt_chars(), request.params.max_tokens, provider.host, provider.api_model_id
    )
    if not job.budget.allows(estimate):
        raise BudgetStopError
    result = provider.complete(request)
    cost = ctx.prices.cost(result.usage, provider.host, provider.api_model_id)
    job.budget.charge(cost)
    append_jsonl(
        job.out_dir / COSTS_FILE,
        {
            "at": job.clock().isoformat(timespec="seconds"),
            "tag": request.tag,
            "provider": provider.host,
            "api_model_id": provider.api_model_id,
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "reasoning_tokens": result.usage.reasoning_tokens,
            "usage_estimated": result.usage.estimated,
            "attempts": result.attempts,
            "finish_reason": result.finish_reason,
            "cost_usd": str(cost),
            "price_table": ctx.prices.version,
        },
    )
    return result.text


def _request(
    prompt: RenderedPrompt, params: RequestConfig, cell: GenerationCell, stage: str
) -> ChatRequest:
    return ChatRequest(
        messages=prompt.messages,
        params=params,
        seed=cell.scenario_seed,
        tag=f"{cell.cell_id}:{stage}",
    )


# --------------------------------------------------------------------------- record building


def extract_json(text: str) -> tuple[str, bool]:
    """Extract the JSON object from a generator reply.

    Args:
        text: Raw completion text.

    Returns:
        ``(json_text, wrapped)``; ``wrapped`` is True when fences or prose surrounded it.

    Raises:
        OutputParseError: If the reply holds no ``{...}`` object.
    """
    stripped = text.strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        msg = "no JSON object in the generator output"
        raise OutputParseError(msg)
    return stripped[start : end + 1], (start, end) != (0, len(stripped) - 1)


def build_pa_attempt(job: CellJob, raw: str) -> Attempt:
    """Turn a P-A reply into a validated record (or findings).

    Args:
        job: The cell job.
        raw: Completion text.

    Returns:
        The outcome.
    """
    try:
        payload, wrapped = extract_json(raw)
        output = PAOutput.model_validate_json(payload, strict=True)
    except (OutputParseError, ValidationError) as exc:
        return Attempt(findings=[_schema_finding(exc, "proposed_labels")], stage="pa", raw=raw)
    ticket, mask = _ticket(job, output.subject, output.message, output.previous_messages)
    labels = _mask_labels(output.proposed_labels, mask.replacements)
    attempt = _finish(job, ticket, labels, mask, basis="llm_proposal", self_check=output.self_check)
    if wrapped:
        attempt.findings.append(Finding("A5_json_wrapped", "warning", "output"))
    attempt.stage, attempt.raw = "pa", raw
    return attempt


def build_pb_attempt(job: CellJob, scenario: ScenarioFacts, raw: str) -> Attempt:
    """Turn a P-B stage-2 reply into a record with scenario-spec labels.

    Args:
        job: The cell job.
        scenario: Stage-1 output.
        raw: Stage-2 completion text.

    Returns:
        The outcome.
    """
    try:
        message = PBMessage.model_validate_json(extract_json(raw)[0], strict=True)
    except (OutputParseError, ValidationError) as exc:
        return Attempt(findings=[_schema_finding(exc, "message")], stage="pb2", raw=raw)
    ticket, mask = _ticket(job, message.subject, message.message, message.previous_messages)
    labels = scenario_labels(job.cell, ticket, job.ctx.rules, job.ctx.facts)
    attempt = _finish(job, ticket, labels, mask, basis="scenario_spec", scenario=scenario)
    attempt.stage, attempt.raw = "pb2", raw
    return attempt


def scenario_labels(
    cell: GenerationCell, ticket: TicketPayload, rules: LabelRules, facts: FactSheet
) -> TriageLabels:
    """Gold labels of a P-B ticket, derived from the scenario spec (never from the generator).

    Args:
        cell: Plan cell.
        ticket: The generated ticket (card entities are kept only when literally present).
        rules: Label rules.
        facts: Fact sheet (IdP aliases).

    Returns:
        Labels pending 100% human review.
    """
    text = ticket.full_text()
    intents = (cell.intent, *cell.secondary_intents)
    churn = rules.derive_churn(
        cell.churn_cue, sentiment=cell.sentiment, plan=cell.plan, intents=intents
    )
    signal = _CHURN_SIGNAL.get(cell.churn_cue)
    signals = (
        (signal.format(competitor=cell.competitor or ""),) if signal and churn != "low" else ()
    )
    if churn == "high" and not signals:
        signals = (_CHURN_SIGNAL["explicit_cancel"],)
    human = cell.human_request != "none"
    action = rules.expected_action(
        cell.intent,
        customer_requested_human=human,
        information_sufficient=cell.information_sufficient,
    )
    return TriageLabels(
        intent=cell.intent,
        secondary_intents=cell.secondary_intents,
        priority=cell.priority_hint,
        sentiment=cell.sentiment,
        churn_risk=churn,
        churn_signals=signals,
        product_area=cell.product_area,
        entities=tuple(e for e in cell.entities if entity_present(e, text, facts)),
        recommended_queue=rules.routing[cell.intent].queue,
        recommended_action=action,
        customer_requested_human=human,
        information_sufficient=cell.information_sufficient,
        rationale=f"Scenario spec: {cell.intent} ({cell.difficulty}); pending human review.",
    )


@dataclass(frozen=True, slots=True)
class _Mask:
    replacements: dict[str, str]
    ops: tuple[str, ...]


def _ticket(
    job: CellJob, subject: str, message: str, history: Sequence[DraftMessage]
) -> tuple[TicketPayload, _Mask]:
    cell, ctx = job.cell, job.ctx
    names = [ctx.pools.persona(cell.persona_id).full_name]
    masked_subject = mask_text(subject, names)
    masked_message = mask_text(message, names, masked_subject.replacements)
    replacements = masked_message.replacements
    ops = [*masked_subject.ops, *masked_message.ops]
    prior: list[tuple[str, str]] = []
    for item in history:
        part = mask_text(item.body, names, replacements)
        replacements = part.replacements
        ops += part.ops
        prior.append((item.author, part.text))
    text = masked_message.text
    if cell.noise:
        keep = [*cell.display_values, *cell.pii_placeholders, *filter(None, [cell.injection])]
        text, noise_ops = add_noise(
            text, rng_for(ctx.matrix.spec.seed, cell.cell_id, "noise"), keep
        )
        ops += [f"noise:{op}" for op in noise_ops]
    gap = timedelta(hours=HISTORY_GAP_HOURS)
    ticket = TicketPayload(
        customer_tier=cell.plan,
        channel=cell.channel,
        subject=masked_subject.text.strip() or "(no subject)",
        message=text.strip() or "(empty)",
        previous_messages=tuple(
            PreviousMessage.model_validate(
                {
                    "author": author,
                    "body": body,
                    "sent_at": cell.received_at - gap * (len(prior) - i),
                }
            )
            for i, (author, body) in enumerate(prior)
        ),
        account=_account(ctx.pools.company(cell.company_id)),
        product=_product(cell),
        received_at=cell.received_at,
    )
    return ticket, _Mask(replacements, tuple(sorted(set(ops))))


def _account(company: Company) -> AccountMetadata:
    return AccountMetadata.model_validate(
        {
            "account_id": company.account_id,
            "company_name": company.name,
            "arr_band": company.arr_band,
            "region": company.region,
            "seats": company.seats,
        }
    )


def _product(cell: GenerationCell) -> ProductMetadata:
    if cell.channel == "api":
        return ProductMetadata(platform="api")
    if cell.product_area == "mobile_apps":
        return ProductMetadata(platform="ios" if cell.scenario_seed % 2 else "android")
    return ProductMetadata(platform="web")


def _mask_labels(labels: TriageLabels, replacements: Mapping[str, str]) -> TriageLabels:
    if not replacements:
        return labels
    entities = tuple(
        EntityLabel(type=e.type, value=apply_replacements(e.value, replacements))
        for e in labels.entities
    )
    return labels.model_copy(
        update={
            "entities": entities,
            "churn_signals": tuple(
                apply_replacements(s, replacements) for s in labels.churn_signals
            ),
            "rationale": apply_replacements(labels.rationale, replacements),
        }
    )


def _finish(
    job: CellJob,
    ticket: TicketPayload,
    labels: TriageLabels,
    mask: _Mask,
    *,
    basis: LabelBasis,
    self_check: SelfCheck | None = None,
    scenario: ScenarioFacts | None = None,
) -> Attempt:
    ctx, cell, provider = job.ctx, job.cell, job.provider
    split_spec = ctx.matrix.spec.splits[ctx.split]
    now = job.clock()
    try:
        provenance = Provenance(
            record_id=f"{SPLIT_CODES[ctx.split]}_{cell.seq:05d}",
            split=ctx.split,
            generator_family=split_spec.generator_family,
            generator_model=provider.open_weights_model,
            api_model_id=provider.api_model_id,
            provider=provider.host,
            generator_endpoint=f"{provider.host}|{provider.api_model_id}|{now:%Y-%m-%d}",
            prompt_family=split_spec.prompt_family,
            prompt_version=ctx.family.version,
            template_id=cell.template_id,
            cell_id=cell.cell_id,
            scenario_seed=cell.scenario_seed,
            persona_id=cell.persona_id,
            company_id=cell.company_id,
            noise_ops=mask.ops,
            seed=ctx.matrix.spec.seed,
            created_at=now,
            label_source="generator_proposed",
            label_basis=basis,
            taxonomy_version=ctx.taxonomy.version,
            content_sha256=content_sha256(ticket.customer_text()),
            terms_snapshot_id=ctx.config.terms_snapshot_id,
        )
        record = DatasetRecord(
            ticket=ticket,
            labels=labels,
            provenance=provenance,
            cell=cell,
            self_check=self_check,
            scenario=scenario,
        )
    except ValidationError as exc:
        return Attempt(findings=[_schema_finding(exc, "record")])
    findings = validate_record(record, ctx.validation_context)
    return Attempt(record=None if has_errors(findings) else record, findings=findings)


def _schema_finding(exc: Exception, where: str) -> Finding:
    if isinstance(exc, ValidationError):
        locations = sorted({".".join(str(p) for p in e["loc"]) or "root" for e in exc.errors()})
        detail = f"{exc.error_count()} schema error(s): {', '.join(locations[:8])}"
        return Finding("R0_schema", "error", where, detail)
    return Finding("R0_parse", "error", where, str(exc))


def _quarantine(out_dir: Path, cell: GenerationCell, attempt_no: int, attempt: Attempt) -> None:
    append_jsonl(
        out_dir / QUARANTINE_FILE,
        {
            "cell_id": cell.cell_id,
            "attempt": attempt_no,
            "stage": attempt.stage,
            "error": attempt.error,
            "findings": [f.as_dict() for f in attempt.findings if f.severity == "error"],
            "warnings": [f.as_dict() for f in attempt.findings if f.severity == "warning"],
            "raw_output_sha256": sha256_hex(attempt.raw) if attempt.raw else None,
            "raw_output": attempt.raw[:RAW_OUTPUT_LIMIT] if attempt.raw else None,
        },
    )


def _checkpoint(
    plan: GenerationPlan,
    options: RunOptions,
    summary: RunSummary,
    state: RunState,
    budget: Budget,
    clock: Clock,
) -> dict[str, object]:
    return {
        "split": options.split,
        "family": options.family,
        "plan_sha256": plan.plan_sha256,
        "matrix_sha256": plan.matrix_sha256,
        "cells_in_plan": len(plan.cells),
        "accepted_total": len(state.accepted),
        "run_accepted": summary.accepted,
        "run_quarantined": summary.quarantined,
        "run_spent_usd": str(budget.spent_run),
        "updated_at": clock().isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------- dry run


def dry_run(
    ctx: GenerationContext, cells: Sequence[GenerationCell], summary: RunSummary
) -> RunSummary:
    """Render every prompt of the selected cells to ``dry_run/`` and estimate the cost.

    No provider, key or network is used. P-B stage-2 prompts are rendered with a placeholder
    timeline, because the real one comes from stage 1.

    Args:
        ctx: Context.
        cells: Selected cells.
        summary: Summary to fill.

    Returns:
        The summary (``processed`` = cells rendered, ``estimated_usd`` = cost upper bound).
    """
    folder = summary.out_dir / DRY_RUN_DIR
    folder.mkdir(parents=True, exist_ok=True)
    family_config = ctx.config.families[SPLIT_FAMILY[ctx.split]]
    host = family_config.default_host
    model = family_config.hosts[host].api_model_id
    pctx = ctx.prompt_context
    placeholder = ScenarioFacts(
        timeline=("(stage-1 timeline appears here)",),
        customer_goal="(stage-1 customer goal appears here)",
        facts_customer_knows=("(stage-1 known facts appear here)",),
    )
    for cell in cells:
        if ctx.prompt_family == "P-A":
            prompts = [(render_pa(cell, pctx, ctx.family), family_config.requests["default"])]
        else:
            prompts = [
                (render_pb_stage1(cell, pctx, ctx.family), family_config.requests["stage1"]),
                (
                    render_pb_stage2(cell, pctx, ctx.family, placeholder),
                    family_config.requests["stage2"],
                ),
            ]
        texts = []
        for prompt, params in prompts:
            chars = sum(len(m.content) for m in prompt.messages)
            summary.estimated_usd += ctx.prices.estimate(chars, params.max_tokens, host, model)
            header = f"### {prompt.template_id} ({prompt.prompt_version}) sha256={prompt.sha256}"
            texts.append(f"{header}\n{prompt.text()}")
        (folder / f"{cell.cell_id}.txt").write_text(
            "\n".join(texts), encoding="utf-8", newline="\n"
        )
        summary.processed += 1
    return summary
