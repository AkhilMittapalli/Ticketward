"""Generation matrix: quotas, plausibility constraints, pairwise coverage, strata, determinism."""

import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from tw_ml.datagen.generate import GenerationContext
from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.matrix import (
    Constraint,
    ConstraintSet,
    GenerationPlan,
    Matrix,
    MatrixError,
    _Tally,
    _top_up,
    build_plan,
    check_strata,
    coverage_demand,
    intent_quotas,
    load_matrix,
)
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy


def _dims(plan: GenerationPlan) -> list[dict[str, str]]:
    keys = ("intent", "difficulty", "product_area", "plan", "channel", "sentiment", "style")
    rest = ("length_bucket", "subject_style", "human_request")
    return [{k: getattr(c, k) for k in (*keys, *rest)} for c in plan.cells]


# --------------------------------------------------------------------------- quotas


def test_train_quotas_follow_the_v1_1_allocation(
    matrix: Matrix, taxonomy: Taxonomy, rules: LabelRules
) -> None:
    quotas = intent_quotas(matrix, "train", taxonomy, rules)
    assert sum(quotas.values()) == 3600
    critical = {i: q for i, q in quotas.items() if rules.is_critical(i)}
    assert set(critical.values()) == {323}
    assert quotas["other_unclear"] == 248
    assert quotas["how_to_question"] == 249  # the +1 (W-m8)
    others = {q for i, q in quotas.items() if not rules.is_critical(i) and i != "how_to_question"}
    assert others == {248}
    assert pytest.approx(matrix.spec.intent_allocation.critical_oversample, abs=0.01) == 323 / 248


def test_val_quotas_are_proportional_to_train(
    matrix: Matrix, taxonomy: Taxonomy, rules: LabelRules
) -> None:
    quotas = intent_quotas(matrix, "val", taxonomy, rules)
    assert sum(quotas.values()) == 450
    assert {q for i, q in quotas.items() if rules.is_critical(i)} <= {40, 41}
    assert {q for i, q in quotas.items() if not rules.is_critical(i)} == {31}


def test_test_synth_quotas(matrix: Matrix, taxonomy: Taxonomy, rules: LabelRules) -> None:
    quotas = intent_quotas(matrix, "test_synth", taxonomy, rules)
    assert sum(quotas.values()) == 1045
    assert all(q >= 120 for i, q in quotas.items() if rules.is_critical(i))
    assert quotas["other_unclear"] == 60
    assert {q for i, q in quotas.items() if not rules.is_critical(i) and i != "other_unclear"} == {
        55
    }


@pytest.mark.parametrize("plan_name", ["train_plan", "val_plan", "test_plan"])
def test_plan_sizes_match_quotas(plan_name: str, request: pytest.FixtureRequest) -> None:
    plan: GenerationPlan = request.getfixturevalue(plan_name)
    counts = Counter(c.intent for c in plan.cells)
    assert counts == plan.report.quotas
    assert [c.seq for c in plan.cells] == list(range(len(plan.cells)))


# --------------------------------------------------------------------------- coverage


@pytest.mark.parametrize(("plan_name", "minimum"), [("train_plan", 3), ("test_plan", 1)])
def test_every_feasible_pair_is_covered(
    plan_name: str, minimum: int, matrix: Matrix, request: pytest.FixtureRequest
) -> None:
    plan: GenerationPlan = request.getfixturevalue(plan_name)
    constraints = ConstraintSet(matrix.spec.constraints, matrix.domains)
    counts: Counter[tuple[str, str, str]] = Counter()
    for dims in _dims(plan):
        for dim in matrix.spec.coverage.pairwise:
            counts[(dims["intent"], dim, dims[dim])] += 1
    feasible = 0
    for intent in matrix.domains["intent"]:
        for dim in matrix.spec.coverage.pairwise:
            for value in matrix.domains[dim]:
                if constraints.completable({"intent": intent, dim: value}):
                    feasible += 1
                    assert counts[(intent, dim, value)] >= minimum, (intent, dim, value)
                else:
                    assert counts[(intent, dim, value)] == 0, (intent, dim, value)
    assert plan.report.coverage_gaps == ()
    assert feasible == plan.report.feasible_pairs


def test_test_synth_strata_meet_br_038(test_plan: GenerationPlan, matrix: Matrix) -> None:
    assert test_plan.report.strata_shortfalls == ()
    assert check_strata(test_plan.report.strata, matrix.spec.strata_min["test_synth"]) == []
    assert set(test_plan.report.strata) == set(matrix.domains["difficulty"])


def test_marginals_track_the_targets(train_plan: GenerationPlan, matrix: Matrix) -> None:
    for dim in ("difficulty", "channel", "sentiment", "subject_style"):
        for value, target in matrix.targets[dim].items():
            assert train_plan.report.marginals[dim][value] == pytest.approx(target, abs=0.05), (
                dim,
                value,
            )


# --------------------------------------------------------------------------- constraints and cards


@pytest.mark.parametrize("plan_name", ["train_plan", "val_plan", "test_plan"])
def test_every_cell_is_plausible(
    plan_name: str, matrix: Matrix, rules: LabelRules, request: pytest.FixtureRequest
) -> None:
    plan: GenerationPlan = request.getfixturevalue(plan_name)
    constraints = ConstraintSet(matrix.spec.constraints, matrix.domains)
    for cell, dims in zip(plan.cells, _dims(plan), strict=True):
        assert constraints.violated(dims) is None, cell.cell_id
        if cell.intent == "sso_login_failure":
            assert cell.plan in {"business", "enterprise"}
            assert cell.product_area == "sso_identity"
        if cell.intent in {"billing_duplicate_charge", "billing_payment_failure", "refund_request"}:
            assert cell.product_area == "billing_subscriptions"
            assert cell.plan != "free"
        if cell.style == "forwarded_thread":
            assert cell.channel == "email"
        if cell.style == "angry_caps":
            assert cell.sentiment in {"frustrated", "angry"}
        for secondary in cell.secondary_intents:
            assert constraints.consistent({"intent": secondary, "plan": cell.plan})
            assert secondary not in {cell.intent, "other_unclear"}
            assert rules.is_critical(cell.intent) or not rules.is_critical(secondary)


@pytest.mark.parametrize("plan_name", ["train_plan", "test_plan"])
def test_card_effects(plan_name: str, matrix: Matrix, request: pytest.FixtureRequest) -> None:
    plan: GenerationPlan = request.getfixturevalue(plan_name)
    for cell in plan.cells:
        card = matrix.spec.intents[cell.intent]
        low, high = matrix.spec.length_words[cell.length_bucket]
        assert low <= cell.target_words <= high
        assert len(cell.entities) == len(cell.display_values)
        if cell.difficulty == "needs_info":
            assert not cell.information_sufficient
            assert cell.omissions == card.needs_info_omit
            assert not set(card.required_entities) & {e.type for e in cell.entities}
        elif cell.intent == "other_unclear":
            assert not cell.information_sufficient
        else:
            assert cell.information_sufficient
        assert (cell.difficulty == "multi_intent") == bool(cell.secondary_intents)
        assert len(cell.secondary_intents) <= 2
        assert (cell.difficulty == "adversarial_injection") == (cell.injection is not None)
        if cell.channel == "chat_transcript":
            assert cell.history_len >= 2
        if cell.churn_cue == "competitor":
            assert cell.competitor
            assert cell.competitor in cell.display_values
        if cell.intent == "cancellation_request":
            assert cell.churn_cue in {"explicit_cancel", "competitor"}
        assert set(cell.banned_words) <= (set(card.banned_words) if cell.lexical_avoid else set())
        required = " ".join([*cell.display_values, cell.injection or ""]).lower()
        assert not any(
            re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", required) for w in cell.banned_words
        )


def test_lexical_avoidance_share_is_exact(train_plan: GenerationPlan, rules: LabelRules) -> None:
    per_intent = Counter(c.intent for c in train_plan.cells)
    avoided = Counter(c.intent for c in train_plan.cells if c.lexical_avoid)
    for intent, total in per_intent.items():
        share = 0.30 if rules.is_critical(intent) else 0.10
        assert abs(avoided[intent] - share * total) <= 1, intent


def test_entities_come_from_the_split_pools(
    train_plan: GenerationPlan, test_plan: GenerationPlan
) -> None:
    for plan, prefix, code in ((train_plan, "INV-A", "tr"), (test_plan, "INV-T", "te")):
        invoices = [e.value for c in plan.cells for e in c.entities if e.type == "invoice_id"]
        assert invoices
        assert all(re.fullmatch(rf"{prefix}\d{{6}}", v) for v in invoices)
        assert all(c.persona_id.startswith(f"p_{code}_") for c in plan.cells)
        assert all(c.company_id.startswith(f"c_{code}_") for c in plan.cells)


def test_templates_are_split_disjoint_and_balanced(
    train_plan: GenerationPlan, val_plan: GenerationPlan, test_plan: GenerationPlan
) -> None:
    train = Counter(c.template_id for c in train_plan.cells)
    val = {c.template_id for c in val_plan.cells}
    test = {c.template_id for c in test_plan.cells}
    assert set(train) == {"pa.t1", "pa.t2", "pa.t3", "pa.t4"}
    assert val == {"pa.t5", "pa.t6"}
    assert test == {"pb.s1+pb.m1", "pb.s2+pb.m2"}
    assert max(train.values()) - min(train.values()) <= 2


def test_ids_reveal_no_label(train_plan: GenerationPlan, taxonomy: Taxonomy) -> None:
    for cell in train_plan.cells[:200]:
        assert not any(intent in cell.cell_id for intent in taxonomy.values("Intent"))
    first_round = [c.intent for c in train_plan.cells[:13]]
    assert sorted(first_round) == sorted(taxonomy.values("Intent"))
    assert first_round != list(taxonomy.values("Intent"))  # shuffled, not taxonomy order


def test_plans_are_deterministic(val_ctx: GenerationContext, val_plan: GenerationPlan) -> None:
    again = build_plan(val_ctx.plan_inputs(), "val")
    assert again.plan_sha256 == val_plan.plan_sha256
    assert again.cells == val_plan.cells


def test_plan_rejects_the_wrong_pool(
    val_ctx: GenerationContext, train_ctx: GenerationContext
) -> None:
    from dataclasses import replace  # noqa: PLC0415

    with pytest.raises(MatrixError, match="pool"):
        build_plan(replace(val_ctx.plan_inputs(), pools=train_ctx.pools), "val")


def test_p_b_cells_carry_scenarios(test_plan: GenerationPlan, train_plan: GenerationPlan) -> None:
    assert all(c.scenario_type for c in test_plan.cells if c.intent != "other_unclear")
    assert all(c.scenario_type is None for c in train_plan.cells)


# --------------------------------------------------------------------------- constraint engine


def _constraint_set() -> ConstraintSet:
    constraints = [
        Constraint.model_validate({"id": "a_needs_x", "if": {"k": ["a"]}, "require": {"m": ["x"]}}),
        Constraint.model_validate({"id": "x_needs_q", "if": {"m": ["x"]}, "require": {"n": ["q"]}}),
    ]
    domains = {"k": ("a", "b"), "m": ("x", "y"), "n": ("p", "q")}
    return ConstraintSet(constraints, domains)


def test_constraint_engine() -> None:
    engine = _constraint_set()
    assert engine.violated({"k": "a", "m": "y"}) == "a_needs_x"
    assert engine.violated({"k": "a"}) is None  # the required attribute is not assigned yet
    assert engine.consistent({"k": "b", "m": "y", "n": "p"})
    assert engine.allowed("m", {"k": "a"}) == ["x"]
    assert engine.allowed("n", {"k": "a"}) == ["q"]  # lookahead through m
    assert engine.completable({"k": "a", "n": "q"})
    assert not engine.completable({"k": "a", "n": "p"})


def test_top_up_moves_values_into_uncovered_pairs() -> None:
    engine = _constraint_set()
    drawn = [{"intent": "i", "k": "b", "m": "y", "n": "p"} for _ in range(4)]
    tally = _Tally()
    for dims in drawn:
        tally.add(dims)
    demand = {("i", "m", "x"): 1, ("i", "m", "y"): 1}
    swaps = _top_up(drawn, tally, demand, engine)
    # m=x needs n=q, so a plain swap of m is inconsistent: the pair stays uncovered.
    assert swaps == 0
    assert tally.pair_counts["i"]["m"]["x"] == 0
    drawn_ok = [{"intent": "i", "k": "b", "m": "y", "n": "q"} for _ in range(4)]
    tally_ok = _Tally()
    for dims in drawn_ok:
        tally_ok.add(dims)
    assert _top_up(drawn_ok, tally_ok, demand, engine) == 1
    assert tally_ok.pair_counts["i"]["m"]["x"] == 1
    assert sum(d["m"] == "x" for d in drawn_ok) == 1


def test_coverage_demand_is_capped_by_the_quota(matrix: Matrix) -> None:
    engine = ConstraintSet(matrix.spec.constraints, matrix.domains)
    demand = coverage_demand(matrix, engine, {"bug_report": 4}, minimum=3)
    per_area = [v for (i, d, _), v in demand.items() if d == "product_area"]
    assert per_area
    assert max(per_area) == 0
    assert coverage_demand(matrix, engine, {"bug_report": 400}, minimum=0) == {}


# --------------------------------------------------------------------------- loader errors


def _write_matrix(tmp_path: Path, paths: RepoPaths, edit: dict[str, object]) -> Path:
    document = yaml.safe_load(
        (paths.spec_dir / "generation_matrix.yaml").read_text(encoding="utf-8")
    )
    document.update(edit)
    path = tmp_path / "generation_matrix.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_loader_rejects_inconsistent_files(
    tmp_path: Path, paths: RepoPaths, taxonomy: Taxonomy, rules: LabelRules
) -> None:
    good = yaml.safe_load((paths.spec_dir / "generation_matrix.yaml").read_text(encoding="utf-8"))
    bad_dims = dict(good["dimensions"], plan={"free": 1.0, "gold": 1.0})
    with pytest.raises(MatrixError, match="taxonomy values"):
        load_matrix(
            _write_matrix(tmp_path, paths, {"dimensions": bad_dims}), taxonomy=taxonomy, rules=rules
        )
    bad_alloc = dict(
        good["intent_allocation"],
        train={"critical_each": 1, "non_critical_each": 1, "other_unclear": 1},
    )
    with pytest.raises(MatrixError, match="sum to"):
        load_matrix(
            _write_matrix(tmp_path, paths, {"intent_allocation": bad_alloc}),
            taxonomy=taxonomy,
            rules=rules,
        )
    bad_constraint = [
        *good["constraints"],
        {"id": "x", "if": {"style": ["nope"]}, "require": {"plan": ["free"]}},
    ]
    with pytest.raises(MatrixError, match="constraint x"):
        load_matrix(
            _write_matrix(tmp_path, paths, {"constraints": bad_constraint}),
            taxonomy=taxonomy,
            rules=rules,
        )
    with pytest.raises(MatrixError, match="malformed"):
        load_matrix(
            _write_matrix(tmp_path, paths, {"unexpected": 1}), taxonomy=taxonomy, rules=rules
        )
    intents = dict(good["intents"])
    intents["bug_report"] = dict(intents["bug_report"], secondary_candidates=["security_report"])
    with pytest.raises(MatrixError, match="critical-first"):
        load_matrix(
            _write_matrix(tmp_path, paths, {"intents": intents}), taxonomy=taxonomy, rules=rules
        )
    with pytest.raises(MatrixError, match="taxonomy_version"):
        load_matrix(
            _write_matrix(tmp_path, paths, {"taxonomy_version": "1999-01-v0"}),
            taxonomy=taxonomy,
            rules=rules,
        )
    swapped = dict(good["splits"])
    swapped["test_synth"] = dict(swapped["test_synth"], generator_family="openai_gpt_oss")
    with pytest.raises(MatrixError, match="openai_gpt_oss not allowed in test_synth"):
        load_matrix(
            _write_matrix(tmp_path, paths, {"splits": swapped}), taxonomy=taxonomy, rules=rules
        )


def test_test_synth_is_generated_by_deepseek(matrix: Matrix) -> None:
    """D-07: Family B is DeepSeek-V3.2; the matrix provenance value must say so."""
    spec = matrix.spec.splits["test_synth"]
    assert (spec.family, spec.generator_family, spec.prompt_family) == ("B", "deepseek", "P-B")
    assert {matrix.spec.splits[s].generator_family for s in ("train", "val")} == {"openai_gpt_oss"}
