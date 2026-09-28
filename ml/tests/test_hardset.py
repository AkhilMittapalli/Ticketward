"""Hard-set validator: quotas, attestation, strata consistency, template, deterministic split.

The 100 cases come from the ``hard_cases`` fixture (conftest), generated in code for tests only;
the real hard set is written by the owner by hand (docs/hard_set_guide.md).
"""

import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tw_ml.baselines.rules import read_tickets
from tw_ml.datagen.hardset import (
    TEMPLATE_ID,
    HardSetItem,
    Quotas,
    check_quotas,
    dev_gold_lines,
    split_hard_set,
    split_summary,
    to_record,
    validate_hard_set,
    written_after,
)
from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import TicketPayload, TriageLabels
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.datagen.validate import ValidationContext
from tw_ml.eval.data import load_gold


def _lines(cases: list[dict[str, Any]]) -> list[str]:
    return [json.dumps(case) for case in cases]


@pytest.fixture
def cases(hard_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return hard_cases


# --------------------------------------------------------------------------- validation


def test_a_complete_hard_set_passes(
    cases: list[dict[str, Any]], vctx: ValidationContext, taxonomy: Taxonomy
) -> None:
    report = validate_hard_set(_lines(cases), vctx, taxonomy)
    assert report.findings == {}
    assert report.passed
    assert report.quota_shortfalls == []
    expected = {"total": 100, "critical_combined": 44, "injection": 10, "needs_info": 10}
    expected |= {"human_request": 8, "human_request_indirect": 3, "legal_threat_in_billing": 6}
    assert {k: report.counts[k] for k in expected} == expected
    assert min(v for k, v in report.counts.items() if k.startswith("intent:")) == 7


def test_quota_shortfalls(
    cases: list[dict[str, Any]], rules: LabelRules, taxonomy: Taxonomy
) -> None:
    items = [HardSetItem.model_validate(c) for c in cases]
    counts, shortfalls = check_quotas(items, rules, taxonomy)
    assert shortfalls == []
    assert counts["intent:other_unclear"] == 7
    fewer = [i for i in items if i.labels.intent != "how_to_question"]
    _, shortfalls = check_quotas(fewer, rules, taxonomy)
    assert shortfalls == [
        "total: 93 != 100",
        "intent:how_to_question: 0 < 6",
        "needs_info: 7 < 10",
        "human_request: 5 < 8",
        "human_request_indirect: 0 < 3",
    ]
    strict = Quotas(per_intent=8, critical_combined=45, injection=11, legal_threat_in_billing=7)
    _, shortfalls = check_quotas(items, rules, taxonomy, strict)
    assert {s.split(":")[0] for s in shortfalls} == {
        "intent",
        "critical_combined",
        "injection",
        "legal_threat_in_billing",
    }


def test_an_incomplete_file_fails_on_quotas_only(
    cases: list[dict[str, Any]], vctx: ValidationContext, taxonomy: Taxonomy
) -> None:
    report = validate_hard_set(_lines(cases[:-1]), vctx, taxonomy)
    assert report.findings == {}
    assert report.quota_shortfalls == ["total: 99 != 100"]
    assert not report.passed


@pytest.mark.parametrize(
    ("edit", "rule"),
    [
        (lambda c: c["attestation"].update(llm_assisted=True), "H_llm_assisted"),
        (lambda c: c["strata"].update(needs_info=True), "H_needs_info_tag"),
        (lambda c: c["strata"].update(human_request="direct"), "H_human_request_tag"),
        (lambda c: c["strata"].update(legal_threat_in_billing=True), "H_legal_billing_tag"),
        (
            lambda c: c["labels"].update(recommended_queue="billing_and_accounts"),
            "R2_queue_not_allowed",
        ),
        (lambda c: c["ticket"].update(message="Mail me at someone@corp.test."), "R10_pii_email"),
    ],
)
def test_case_level_findings(
    cases: list[dict[str, Any]], vctx: ValidationContext, taxonomy: Taxonomy, edit: Any, rule: str
) -> None:
    plain = {
        "injection": False,
        "needs_info": False,
        "human_request": "none",
        "legal_threat_in_billing": False,
    }
    target = next(
        c for c in cases if c["labels"]["intent"] == "how_to_question" and c["strata"] == plain
    )
    edit(target)
    report = validate_hard_set(_lines(cases), vctx, taxonomy)
    assert rule in {f.rule for f in report.findings[target["record_id"]]}
    assert not report.passed


def test_missing_needs_info_tag(
    cases: list[dict[str, Any]], vctx: ValidationContext, taxonomy: Taxonomy
) -> None:
    target = next(c for c in cases if c["strata"]["needs_info"])
    target["strata"]["needs_info"] = False
    report = validate_hard_set(_lines(cases), vctx, taxonomy)
    assert "H_needs_info_tag" in {f.rule for f in report.findings[target["record_id"]]}


def test_parse_errors_duplicates_and_the_template(
    cases: list[dict[str, Any]], vctx: ValidationContext, taxonomy: Taxonomy, paths: RepoPaths
) -> None:
    template = (
        (paths.root / "data" / "hard_set" / "TEMPLATE.jsonl").read_text(encoding="utf-8").strip()
    )
    duplicate_id = dict(
        cases[1], ticket={**cases[1]["ticket"], "message": "Completely different text here."}
    )
    duplicate_id["record_id"] = cases[0]["record_id"]
    duplicate_text = dict(cases[2], record_id="th_101")
    lines = [
        template,
        *_lines(cases[1:]),
        json.dumps(duplicate_id),
        json.dumps(duplicate_text),
        "{broken",
        json.dumps({"record_id": "th_102"}),
    ]
    report = validate_hard_set(lines, vctx, taxonomy)
    assert set(report.parse_errors) == {len(lines) - 1, len(lines)}
    assert report.duplicate_ids == []  # th_001 itself was dropped from the lines
    assert any(set(group) == {"th_003", "th_101"} for group in report.duplicate_texts)
    assert all(item.record_id != TEMPLATE_ID for item in report.items)
    again = validate_hard_set([*_lines(cases), json.dumps(cases[0])], vctx, taxonomy)
    assert again.duplicate_ids == ["th_001"]


def test_template_row_lists_every_field(paths: RepoPaths) -> None:
    row = json.loads(
        (paths.root / "data" / "hard_set" / "TEMPLATE.jsonl").read_text(encoding="utf-8")
    )
    assert row["record_id"] == TEMPLATE_ID
    assert set(row) == set(HardSetItem.model_fields)
    assert set(row["ticket"]) == set(TicketPayload.model_fields)
    assert set(row["labels"]) == set(TriageLabels.model_fields)
    for nested in ("strata", "attestation"):
        annotation = HardSetItem.model_fields[nested].annotation
        assert annotation is not None
        assert set(row[nested]) == set(annotation.model_fields)
    assert row["attestation"]["llm_assisted"] is False


# --------------------------------------------------------------------------- split


def test_split_is_deterministic_stratified_and_order_independent(
    cases: list[dict[str, Any]], rules: LabelRules
) -> None:
    items = [HardSetItem.model_validate(c) for c in cases]
    dev, final = split_hard_set(items)
    assert (len(dev), len(final)) == (30, 70)
    assert not set(dev) & set(final)
    shuffled = items[:]
    random.Random(3).shuffle(shuffled)  # noqa: S311 - seeded shuffle of test data, not security
    assert split_hard_set(shuffled) == (dev, final)
    assert split_hard_set(items, seed=1) != (dev, final)
    per_intent = Counter(i.labels.intent for i in items)
    dev_intents = Counter(i.labels.intent for i in items if i.record_id in dev)
    for intent, total in per_intent.items():
        assert abs(dev_intents[intent] - 0.3 * total) <= 1, intent
    summary = split_summary(items, dev, rules)
    assert summary["hard_dev"]["total"] == 30
    assert summary["hard_final"]["total"] == 70
    assert summary["hard_dev"]["critical"] + summary["hard_final"]["critical"] == sum(
        rules.is_critical(i.labels.intent) for i in items
    )


def test_dev_gold_file_holds_only_hard_dev_and_loads_in_the_harness(
    cases: list[dict[str, Any]], tmp_path: Path
) -> None:
    items = [HardSetItem.model_validate(c) for c in cases]
    dev, final = split_hard_set(items)
    lines = dev_gold_lines(list(reversed(items)), list(reversed(dev)))
    assert lines == dev_gold_lines(items, dev)  # independent of input order
    ids = [json.loads(line)["record_id"] for line in lines]
    assert ids == dev
    assert not set(ids) & set(final)
    gold_file = tmp_path / "hard_dev.v1.jsonl"
    gold_file.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    gold = load_gold(gold_file)
    by_id = {i.record_id: i for i in items}
    assert [g.record_id for g in gold] == dev
    for item in gold:
        source = by_id[item.record_id]
        assert item.labels == source.labels
        assert item.human_request_kind == source.strata.human_request  # M-07d needs the kind
        assert item.needs_info == source.strata.needs_info
        assert item.legal_threat == source.strata.legal_threat_in_billing
    assert [record_id for record_id, _, _ in read_tickets(gold_file)] == dev


def test_dev_gold_lines_refuse_unknown_ids(cases: list[dict[str, Any]]) -> None:
    items = [HardSetItem.model_validate(c) for c in cases[:5]]
    with pytest.raises(ValueError, match="th_999"):
        dev_gold_lines(items, ["th_999"])


def test_to_record_carries_the_attestation(cases: list[dict[str, Any]], taxonomy: Taxonomy) -> None:
    item = HardSetItem.model_validate(cases[0])
    record = to_record(item, taxonomy)
    prov = record.provenance
    assert (prov.split, prov.generator_family, prov.label_source, prov.label_basis) == (
        "test_hard",
        "human",
        "human_written",
        "human",
    )
    assert prov.llm_assisted is False
    assert prov.reviewed_by == ("R-test_fixture",)
    assert prov.created_at == datetime.fromisoformat(cases[0]["attestation"]["written_at"])
    assert written_after([item], datetime(2026, 9, 1, tzinfo=UTC)) == ["th_001"]
    assert written_after([item], datetime(2026, 10, 1, tzinfo=UTC)) == []


def test_hard_set_file_location(paths: RepoPaths) -> None:
    assert paths.hard_set_file == paths.root / "evals" / "hard_set.v1.jsonl"
    assert Path(paths.root / "data" / "hard_set" / "TEMPLATE.jsonl").is_file()
