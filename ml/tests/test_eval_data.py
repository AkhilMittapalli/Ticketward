"""tw_ml.eval.data: gold rows of every P1 format, prediction records, join, safe errors."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tw_ml.datagen.records import DatasetRecord, TriageLabels
from tw_ml.eval.data import (
    EvalDataError,
    PredictionRecord,
    gold_item_from_row,
    join,
    load_gold,
    load_predictions,
)

Writer = Callable[[Path, list[Any]], Path]
SECRET = "Confidential ticket text 4471"


def test_gold_from_dataset_record(make_record: Callable[..., DatasetRecord]) -> None:
    row = json.loads(make_record(record_id="va_00001", split="val").model_dump_json())
    item = gold_item_from_row(row)
    assert item is not None
    assert (item.record_id, item.origin, item.labels.intent) == (
        "va_00001",
        "val",
        "sso_login_failure",
    )
    assert item.human_request_kind is None


def test_gold_from_hard_set_and_eval_rows(make_labels: Callable[..., TriageLabels]) -> None:
    labels = json.loads(make_labels().model_dump_json())
    hard = {
        "record_id": "th_001",
        "labels": labels,
        "strata": {
            "human_request": "indirect",
            "needs_info": True,
            "legal_threat_in_billing": True,
        },
    }
    item = gold_item_from_row(hard)
    assert item is not None
    assert (item.human_request_kind, item.needs_info, item.legal_threat, item.origin) == (
        "indirect",
        True,
        True,
        None,
    )
    scenario = {
        "record_id": "te_001",
        "labels": labels,
        "gold_decision": {"policy_decision": "human_escalation", "queue": "billing_and_accounts"},
    }
    decided = gold_item_from_row(scenario)
    assert decided is not None
    assert decided.decision is not None
    assert decided.decision.queue == "billing_and_accounts"
    assert gold_item_from_row({"record_id": "th_000", "labels": {}}) is None  # template row
    cell = gold_item_from_row(
        {"record_id": "va_1", "labels": labels, "cell": {"human_request": "odd"}}
    )
    assert cell is not None
    assert cell.human_request_kind is None


def test_gold_errors_name_lines_not_text(
    tmp_path: Path, write_jsonl: Writer, make_labels: Callable[..., TriageLabels]
) -> None:
    labels = json.loads(make_labels().model_dump_json())
    bad_labels = {**labels, "intent": SECRET}
    cases: list[tuple[list[Any], str]] = [
        (["{not json"], "line 1: not valid JSON"),
        (["[1, 2]"], "expected a JSON object"),
        ([{"labels": labels}], "no record_id"),
        ([{"record_id": "va_1", "ticket": {"message": SECRET}}], "no labels"),
        ([{"record_id": "va_1", "labels": bad_labels}], "invalid gold at intent"),
        (
            [{"record_id": "va_1", "labels": labels}, {"record_id": "va_1", "labels": labels}],
            "duplicate",
        ),
    ]
    for index, (rows, message) in enumerate(cases):
        path = write_jsonl(tmp_path / f"gold{index}.jsonl", rows)
        with pytest.raises(EvalDataError, match=message) as info:
            load_gold(path)
        assert SECRET not in str(info.value)
    with pytest.raises(EvalDataError, match="not found"):
        load_gold(tmp_path / "missing.jsonl")


def test_predictions_load_and_validate(
    tmp_path: Path, write_jsonl: Writer, make_labels: Callable[..., TriageLabels]
) -> None:
    output = json.loads(make_labels().model_dump_json())
    good = {"record_id": "va_1", "system_id": "s", "output": output}
    loaded = load_predictions(write_jsonl(tmp_path / "p.jsonl", ["", good]))
    assert loaded[0].validity == "first_pass"
    assert loaded[0].schema_version == "prediction.v1"
    failed = PredictionRecord(record_id="va_2", system_id="s", validity="failed_fallback")
    assert failed.output is None
    with pytest.raises(ValidationError):
        PredictionRecord(record_id="va_3", system_id="s")  # no output and not failed_fallback
    bad = write_jsonl(tmp_path / "bad.jsonl", [{**good, "output": {**output, "priority": SECRET}}])
    with pytest.raises(EvalDataError, match=r"invalid prediction at output.priority") as info:
        load_predictions(bad)
    assert SECRET not in str(info.value)
    reason = {
        **good,
        "decision": {
            "policy_decision": "local_draft",
            "needs_human_review": False,
            "escalation_reasons": ["nope"],
        },
    }
    with pytest.raises(EvalDataError, match="escalation_reasons"):
        load_predictions(write_jsonl(tmp_path / "reason.jsonl", [reason]))
    with pytest.raises(EvalDataError, match="duplicate"):
        load_predictions(write_jsonl(tmp_path / "dup.jsonl", [good, good]))


def test_join_sorts_and_reports_missing_and_extra(make_labels: Callable[..., TriageLabels]) -> None:
    labels = make_labels()
    gold = [
        gold_item_from_row({"record_id": rid, "labels": json.loads(labels.model_dump_json())})
        for rid in ("va_3", "va_1", "va_2")
    ]
    predictions = [
        PredictionRecord(record_id=rid, system_id=f"sys-{rid}", output=labels)
        for rid in ("va_1", "va_9")
    ]
    joined = join([g for g in gold if g is not None], predictions)
    assert [item.record_id for item in joined.items] == ["va_1", "va_2", "va_3"]
    assert (joined.missing, joined.extra) == (("va_2", "va_3"), ("va_9",))
    assert joined.system_ids == ("sys-va_1", "sys-va_9")
    assert joined.items[1].output is None
    assert joined.items[1].decision is None
    assert joined.n_with_decision == 0
