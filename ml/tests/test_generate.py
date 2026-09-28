"""Generation loop with FakeProvider: provenance, resume, quarantine, budget, guards, dry run."""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.generate import (
    CHECKPOINT_FILE,
    COSTS_FILE,
    QUARANTINE_FILE,
    RECORDS_FILE,
    GenerationContext,
    GenerationError,
    OutputParseError,
    RunOptions,
    RunState,
    append_jsonl,
    check_terms_snapshot,
    extract_json,
    ledger_total,
    load_state,
    read_jsonl,
    run_generation,
    scenario_labels,
    select_cells,
)
from tw_ml.datagen.matrix import GenerationPlan
from tw_ml.datagen.providers import FakeProvider, ProviderAuthError, ProviderError
from tw_ml.datagen.records import DatasetRecord, TicketPayload

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
Factory = Callable[..., Any]


def _clock() -> datetime:
    return NOW


def _options(
    tmp_path: Path, split: str = "val", family: str = "A", n: int = 6, **extra: Any
) -> RunOptions:
    return RunOptions(
        split=split,  # type: ignore[arg-type]
        family=family,  # type: ignore[arg-type]
        n=n,
        out_dir=tmp_path / split,
        ledger_dir=tmp_path,
        budget_usd=extra.pop("budget_usd", Decimal("1")),
        **extra,
    )


def _records(folder: Path) -> list[DatasetRecord]:
    return [DatasetRecord.model_validate(row) for row in read_jsonl(folder / RECORDS_FILE)]


def _run(
    ctx: GenerationContext,
    plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
    **kw: Any,
) -> tuple[Any, FakeProvider]:
    family = "B" if ctx.split == "test_synth" else "A"
    responder = card_responder(
        plan,
        ctx.rules,
        broken=kw.pop("broken", None),
        extra=kw.pop("extra", None),
        broken_stage=kw.pop("broken_stage", None),
    )
    provider = fake_provider(responder, family)
    provider.failures.extend(kw.pop("failures", []))
    summary = run_generation(
        ctx, _options(tmp_path, ctx.split, family, **kw), provider, clock=_clock
    )
    return summary, provider


def test_p_a_run_writes_records_with_full_provenance(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    summary, provider = _run(
        easy_val_ctx, easy_val_plan, tmp_path, card_responder, fake_provider, n=13
    )
    assert (summary.processed, summary.accepted, summary.quarantined) == (13, 13, 0)
    assert summary.stop_reason == "completed"
    assert summary.spent_usd > 0
    records = _records(tmp_path / "val")
    assert [r.provenance.cell_id for r in records] == [c.cell_id for c in easy_val_plan.cells[:13]]
    for record, cell in zip(records, easy_val_plan.cells, strict=False):
        prov = record.provenance
        assert prov.record_id == f"va_{cell.seq:05d}"
        assert prov.generator_family == "openai_gpt_oss"
        assert prov.generator_model == prov.api_model_id == "openai/gpt-oss-120b"
        assert prov.provider == "deepinfra"
        assert prov.generator_quantization is None  # the Family A host profile states none
        assert prov.generator_endpoint == "deepinfra|openai/gpt-oss-120b|2026-09-27"
        assert (prov.prompt_family, prov.prompt_version, prov.template_id) == (
            "P-A",
            "pa_persona.v1",
            cell.template_id,
        )
        assert (prov.label_source, prov.label_basis) == ("generator_proposed", "llm_proposal")
        assert prov.terms_snapshot_id == "docs/legal/generator-terms-2026-09-27.md"
        assert prov.created_at == NOW
        assert prov.seed == easy_val_ctx.matrix.spec.seed
        assert (prov.persona_id, prov.company_id, prov.scenario_seed) == (
            cell.persona_id,
            cell.company_id,
            cell.scenario_seed,
        )
        assert record.cell == cell
        assert record.self_check is not None
    costs = list(read_jsonl(tmp_path / "val" / COSTS_FILE))
    assert len(costs) == 13
    assert {c["provider"] for c in costs} == {"deepinfra"}
    assert ledger_total(tmp_path) == summary.spent_usd
    checkpoint = json.loads((tmp_path / "val" / CHECKPOINT_FILE).read_text(encoding="utf-8"))
    assert checkpoint["accepted_total"] == 13
    assert checkpoint["cells_in_plan"] == 450
    assert all(c.tag.endswith(":pa") and c.seed is not None for c in provider.calls)


def test_runs_resume_where_they_stopped(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    _run(easy_val_ctx, easy_val_plan, tmp_path, card_responder, fake_provider, n=4)
    second, _ = _run(easy_val_ctx, easy_val_plan, tmp_path, card_responder, fake_provider, n=4)
    assert second.accepted == 4
    ids = [r.provenance.cell_id for r in _records(tmp_path / "val")]
    assert ids == [c.cell_id for c in easy_val_plan.cells[:8]]
    state = load_state(tmp_path / "val")
    assert len(state.accepted) == 8


def test_bad_output_is_regenerated_then_quarantined(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    first, second = easy_val_plan.cells[0].cell_id, easy_val_plan.cells[1].cell_id
    summary, _ = _run(
        easy_val_ctx,
        easy_val_plan,
        tmp_path,
        card_responder,
        fake_provider,
        n=3,
        broken={first: 1, second: 5},
    )
    assert (summary.accepted, summary.quarantined) == (
        2,
        3,
    )  # first: 1 bad then good; second: 2 bad
    quarantine = list(read_jsonl(tmp_path / "val" / QUARANTINE_FILE))
    assert [q["cell_id"] for q in quarantine] == [first, second, second]
    assert quarantine[0]["findings"][0]["rule"] == "R0_parse"
    assert quarantine[0]["raw_output"]
    assert quarantine[0]["raw_output_sha256"]
    # The exhausted cell is skipped next time.
    again, _ = _run(easy_val_ctx, easy_val_plan, tmp_path, card_responder, fake_provider, n=1)
    assert again.accepted == 1
    assert second not in {r.provenance.cell_id for r in _records(tmp_path / "val")}


def test_budget_stops_before_the_call(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    summary, provider = _run(
        easy_val_ctx,
        easy_val_plan,
        tmp_path,
        card_responder,
        fake_provider,
        n=5,
        budget_usd=Decimal("0.0000001"),
    )
    assert summary.stop_reason == "budget"
    assert provider.calls == []
    assert summary.spent_usd == 0
    assert not (tmp_path / "val" / RECORDS_FILE).exists()


def test_total_budget_counts_earlier_ledgers(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    append_jsonl(tmp_path / "old" / COSTS_FILE, {"cost_usd": "14.9999999"})
    summary, provider = _run(
        easy_val_ctx,
        easy_val_plan,
        tmp_path,
        card_responder,
        fake_provider,
        n=2,
        budget_usd=Decimal("5"),
    )
    assert summary.stop_reason == "budget"
    assert provider.calls == []


def test_auth_failure_stops_the_run(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    summary, _ = _run(
        easy_val_ctx,
        easy_val_plan,
        tmp_path,
        card_responder,
        fake_provider,
        n=5,
        failures=[ProviderAuthError("deepinfra: HTTP 401", status=401)],
    )
    assert summary.stop_reason == "auth"
    assert summary.processed == 1
    quarantine = list(read_jsonl(tmp_path / "val" / QUARANTINE_FILE))
    assert quarantine[0]["stage"] == "auth"


def test_provider_errors_are_quarantined_and_retried(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    summary, _ = _run(
        easy_val_ctx,
        easy_val_plan,
        tmp_path,
        card_responder,
        fake_provider,
        n=1,
        failures=[ProviderError("HTTP 503", status=503, retryable=True)],
    )
    assert (summary.accepted, summary.quarantined) == (1, 1)
    assert next(read_jsonl(tmp_path / "val" / QUARANTINE_FILE))["stage"] == "provider"


def test_dry_run_renders_prompts_without_a_provider(
    easy_test_ctx: GenerationContext, tmp_path: Path
) -> None:
    summary = run_generation(
        easy_test_ctx, _options(tmp_path, "test_synth", "B", n=3, dry_run=True), None, clock=_clock
    )
    assert summary.dry_run
    assert summary.processed == 3
    assert summary.estimated_usd > 0
    files = sorted((tmp_path / "test_synth" / "dry_run").glob("*.txt"))
    assert len(files) == 3
    text = files[0].read_text(encoding="utf-8")
    assert "pb.s" in text
    assert "pb.m" in text
    assert "sha256=" in text
    assert not (tmp_path / "test_synth" / RECORDS_FILE).exists()


def test_guards(easy_val_ctx: GenerationContext, tmp_path: Path, fake_provider: Factory) -> None:
    provider = fake_provider(lambda _: "{}")
    with pytest.raises(GenerationError, match="Family A"):
        run_generation(easy_val_ctx, _options(tmp_path, "val", "B"), provider, clock=_clock)
    with pytest.raises(GenerationError, match="needs a provider"):
        run_generation(easy_val_ctx, _options(tmp_path), None, clock=_clock)
    (tmp_path / "val").mkdir(parents=True)
    (tmp_path / "val" / CHECKPOINT_FILE).write_text(
        json.dumps({"plan_sha256": "0" * 64}), encoding="utf-8"
    )
    with pytest.raises(GenerationError, match="plan changed"):
        run_generation(easy_val_ctx, _options(tmp_path), provider, clock=_clock)


def test_config_and_matrix_must_name_the_same_generator(
    easy_test_ctx: GenerationContext, tmp_path: Path
) -> None:
    """Switching B to the Mistral alternative in the config alone would mislabel provenance."""
    config = easy_test_ctx.config
    mistral = config.families["B"].model_copy(update={"generator_family": "mistral"})
    ctx = replace(
        easy_test_ctx,
        config=config.model_copy(update={"families": {**config.families, "B": mistral}}),
    )
    options = _options(tmp_path, "test_synth", "B", n=1, dry_run=True)
    with pytest.raises(GenerationError, match="change both together"):
        run_generation(ctx, options, None, clock=_clock)
    assert run_generation(easy_test_ctx, options, None, clock=_clock).processed == 1


def test_terms_snapshot_guard(easy_val_ctx: GenerationContext) -> None:
    config, root = easy_val_ctx.config, easy_val_ctx.paths.root
    check_terms_snapshot(config, root, date(2026, 10, 27), reviewed=False)  # 30 days: still fine
    with pytest.raises(GenerationError, match="31 days old"):
        check_terms_snapshot(config, root, date(2026, 10, 28), reviewed=False)
    check_terms_snapshot(config, root, date(2027, 1, 1), reviewed=True)
    with pytest.raises(GenerationError, match="does not exist"):
        check_terms_snapshot(
            config.model_copy(update={"terms_snapshot_id": "docs/legal/missing-2026-01-01.md"}),
            root,
            date(2026, 9, 27),
            reviewed=True,
        )
    with pytest.raises(GenerationError, match="YYYY-MM-DD"):
        check_terms_snapshot(
            config.model_copy(update={"terms_snapshot_id": "docs/legal/README.md"}),
            root,
            date(2026, 9, 27),
            reviewed=True,
        )


def test_stale_terms_block_a_real_run(
    easy_val_ctx: GenerationContext, tmp_path: Path, fake_provider: Factory
) -> None:
    provider = fake_provider(lambda _: "{}")
    with pytest.raises(GenerationError, match="terms snapshot"):
        run_generation(
            easy_val_ctx,
            _options(tmp_path),
            provider,
            clock=lambda: datetime(2026, 12, 1, tzinfo=UTC),
        )
    assert provider.calls == []


def test_p_b_run_uses_scenario_spec_labels(
    easy_test_ctx: GenerationContext,
    easy_test_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    summary, provider = _run(
        easy_test_ctx, easy_test_plan, tmp_path, card_responder, fake_provider, n=13
    )
    assert (summary.accepted, summary.quarantined) == (13, 0)
    assert len(provider.calls) == 26  # two stages per ticket
    for record in _records(tmp_path / "test_synth"):
        prov = record.provenance
        assert (prov.generator_family, prov.label_basis, prov.prompt_family) == (
            "deepseek",
            "scenario_spec",
            "P-B",
        )
        assert prov.generator_model == prov.api_model_id == "deepseek-ai/DeepSeek-V3.2"
        assert (prov.provider, prov.generator_quantization) == ("deepinfra", "fp4")
        assert record.scenario is not None
        assert record.self_check is None
        assert record.cell is not None
        assert record.labels.intent == record.cell.intent
        assert set(record.labels.entities) <= set(record.cell.entities)
        assert record.labels.rationale.startswith("Scenario spec")


def test_p_b_stage_one_failures_are_quarantined(
    easy_test_ctx: GenerationContext,
    easy_test_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    first = easy_test_plan.cells[0].cell_id
    summary, _ = _run(
        easy_test_ctx,
        easy_test_plan,
        tmp_path,
        card_responder,
        fake_provider,
        n=1,
        broken={first: 1},
        broken_stage="pb1",
    )
    assert (summary.accepted, summary.quarantined) == (1, 1)
    assert next(read_jsonl(tmp_path / "test_synth" / QUARANTINE_FILE))["stage"] == "pb1"


def test_persona_names_are_masked(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    cell = easy_val_plan.cells[0]
    persona = easy_val_ctx.pools.persona(cell.persona_id)
    summary, _ = _run(
        easy_val_ctx,
        easy_val_plan,
        tmp_path,
        card_responder,
        fake_provider,
        n=1,
        extra={cell.cell_id: f"Thanks, {persona.full_name}"},
    )
    assert summary.accepted == 1
    record = _records(tmp_path / "val")[0]
    assert persona.first_name not in record.ticket.message
    assert persona.last_name not in record.ticket.message
    assert "<PERSON_" in record.ticket.message
    assert "mask:person" in record.provenance.noise_ops


def test_noise_is_recorded_and_keeps_card_values(
    easy_val_ctx: GenerationContext,
    easy_val_plan: GenerationPlan,
    tmp_path: Path,
    card_responder: Factory,
    fake_provider: Factory,
) -> None:
    position = next(i for i, c in enumerate(easy_val_plan.cells) if c.noise and c.display_values)
    summary, _ = _run(
        easy_val_ctx, easy_val_plan, tmp_path, card_responder, fake_provider, n=position + 1
    )
    assert summary.accepted == position + 1
    record = _records(tmp_path / "val")[position]
    assert any(op.startswith("noise:") for op in record.provenance.noise_ops)
    assert record.cell is not None
    for value in record.cell.display_values:
        assert value in record.ticket.full_text()


# --------------------------------------------------------------------------- helpers


def test_extract_json() -> None:
    assert extract_json('{"a": 1}') == ('{"a": 1}', False)
    assert extract_json('```json\n{"a": 1}\n```') == ('{"a": 1}', True)
    assert extract_json('Here you go: {"a": {"b": 2}} thanks') == ('{"a": {"b": 2}}', True)
    with pytest.raises(OutputParseError):
        extract_json("no json here")


def test_select_cells_and_state(val_plan: GenerationPlan, tmp_path: Path) -> None:
    state = RunState(accepted={val_plan.cells[0].cell_id}, attempts={val_plan.cells[1].cell_id: 2})
    chosen = select_cells(val_plan, state, 2, max_attempts=2)
    assert [c.cell_id for c in chosen] == [val_plan.cells[2].cell_id, val_plan.cells[3].cell_id]
    everything = RunState(accepted={c.cell_id for c in val_plan.cells})
    assert select_cells(val_plan, everything, 5, max_attempts=2) == []
    assert list(read_jsonl(tmp_path / "missing.jsonl")) == []
    assert ledger_total(tmp_path) == 0


def test_nothing_to_do(
    easy_val_ctx: GenerationContext, tmp_path: Path, fake_provider: Factory
) -> None:
    summary = run_generation(
        easy_val_ctx, _options(tmp_path, n=0), fake_provider(lambda _: "{}"), clock=_clock
    )
    assert summary.stop_reason == "nothing_to_do"
    assert summary.processed == 0


def test_scenario_labels_keep_only_present_entities(
    easy_test_plan: GenerationPlan,
    easy_test_ctx: GenerationContext,
    make_ticket: Callable[..., TicketPayload],
) -> None:
    cell = next(c for c in easy_test_plan.cells if c.churn_cue == "competitor" and c.display_values)
    ticket = make_ticket(
        customer_tier=cell.plan,
        subject="Plan question",
        message=f"We are moving to {cell.competitor}.",
    )
    labels = scenario_labels(cell, ticket, easy_test_ctx.rules, easy_test_ctx.facts)
    assert labels.churn_risk == "high"
    assert labels.churn_signals
    assert cell.competitor is not None
    assert cell.competitor in labels.churn_signals[0]
    assert [e.type for e in labels.entities] == ["competitor_name"]
    assert labels.recommended_queue == easy_test_ctx.rules.routing[cell.intent].queue
