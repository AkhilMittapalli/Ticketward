"""Bitext OOD builder with an in-memory row source (no network, no dataset download)."""

import json
import re
import sys
import types
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from tw_ml.datagen.bitext import (
    EXPECTED_TOTAL,
    BitextError,
    BitextMapping,
    BitextRow,
    FillRule,
    HFRowSource,
    UnknownPlaceholderError,
    build_ood,
    fill_placeholders,
    load_mapping,
    mapping_problems,
    materialize,
)
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.datagen.text import content_sha256

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
T1_ROWS = {
    ("cs", "recover_password"),
    ("cs", "payment_issue"),
    ("cs", "get_refund"),
    ("tel", "cancel_plan"),
    ("tel", "change_plan"),
}
PROBE_ROWS = {
    ("cs", "contact_human_agent"),
    ("tel", "human_agent"),
    ("cs", "newsletter_subscription"),
}


@pytest.fixture
def mapping(paths: RepoPaths, taxonomy: Taxonomy) -> BitextMapping:
    return load_mapping(paths.spec_dir / "bitext_mapping.v1.yaml", taxonomy)


# --------------------------------------------------------------------------- mapping


def test_committed_mapping_matches_erprot(mapping: BitextMapping) -> None:
    assert (len(mapping.mapping["cs"]), len(mapping.mapping["tel"])) == (27, 26)
    tiers = {(s, i): e.tier for s, table in mapping.mapping.items() for i, e in table.items()}
    assert {k for k, t in tiers.items() if t == "T1"} == T1_ROWS
    assert {k for k, t in tiers.items() if t == "probe"} == PROBE_ROWS
    quotas = {name: sum(m.quota for m in g.sources) for name, g in mapping.groups.items()}
    assert quotas == {"S1": 80, "S2": 80, "S3": 80, "S4": 80, "S5": 80, "P-H": 50, "P-N": 50}
    assert sum(quotas.values()) == EXPECTED_TOTAL
    assert mapping.groups["P-H"].gold.customer_requested_human is True
    assert mapping.groups["P-N"].gold.not_intent == "cancellation_request"
    assert {spec.license for spec in mapping.sources.values()} == {"CDLA-Sharing-1.0"}


def test_mapping_problems(mapping: BitextMapping, taxonomy: Taxonomy) -> None:
    assert mapping_problems(mapping, taxonomy) == []
    raw = mapping.model_dump()
    raw["mapping"]["cs"]["get_refund"]["target"] = "refund_forever"
    raw["mapping"]["cs"]["review"]["target"] = "how_to_question"  # excluded row with a target
    raw["mapping"]["ghost"] = {}
    raw["groups"]["S1"]["sources"][0]["intent"] = "edit_account"  # a T2 row
    raw["groups"]["S2"]["sources"][0]["filter"] = "nope"
    raw["groups"]["S3"]["gold"]["intent"] = "not_an_intent"
    raw["groups"]["S4"]["sources"][0]["quota"] = 79
    problems = mapping_problems(BitextMapping.model_validate(raw), taxonomy)
    assert "mapping source ghost is not a pinned source" in problems
    assert "cs.get_refund: target is not a taxonomy intent" in problems
    assert "cs.review: excluded rows (only) have no target" in problems
    assert "group S1: cs.edit_account is not a T1 row" in problems
    assert "group S2: unknown filter nope" in problems
    assert "group S3: gold not_an_intent is not an intent" in problems
    assert "groups sum to 499, expected 500" in problems


def test_load_mapping_errors(tmp_path: Path, mapping: BitextMapping, taxonomy: Taxonomy) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("version: x\n", encoding="utf-8")
    with pytest.raises(BitextError, match="malformed"):
        load_mapping(broken, taxonomy)
    raw = json.loads(mapping.model_dump_json())
    raw["groups"]["S5"]["sources"][0]["quota"] = 81
    inconsistent = tmp_path / "inconsistent.yaml"
    inconsistent.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(BitextError, match="groups sum to 501"):
        load_mapping(inconsistent, taxonomy)


# --------------------------------------------------------------------------- fills


def test_fill_placeholders(mapping: BitextMapping) -> None:
    rules = mapping.placeholders
    text = (
        "Hi {{Salutation}} {{Client Last Name}}, order {{Order Number}} for "
        "{{Currency Symbol}}{{Refund Amount}} on {{Date}}"
    )
    filled = fill_placeholders(text, rules, seed=5)
    assert filled == fill_placeholders(text, rules, seed=5)
    assert fill_placeholders(text, rules, seed=6) != filled
    assert re.fullmatch(
        r"Hi <PERSON_1>, order #\d{5} for \$\d{2,3}\.\d{2} on 2026-\d{2}-\d{2}", filled
    )
    assert fill_placeholders("{{Account Type}}", rules, seed=1) in rules["Account Type"].choice  # type: ignore[operator]
    assert fill_placeholders("{{ Settings }}", rules, seed=1) == "settings"
    with pytest.raises(UnknownPlaceholderError, match="Shoe Size"):
        fill_placeholders("my {{Shoe Size}}", rules, seed=1)
    with pytest.raises(BitextError, match="sets no value"):
        fill_placeholders("{{Empty}}", {"Empty": FillRule()}, seed=1)


# --------------------------------------------------------------------------- build


@pytest.fixture
def built(
    mapping: BitextMapping, taxonomy: Taxonomy, fake_bitext_source: Callable[..., Any]
) -> tuple[Any, Any]:
    source = fake_bitext_source(mapping)
    return source, build_ood(mapping, source, taxonomy, now=NOW)


def test_build_composition_and_provenance(built: tuple[Any, Any], mapping: BitextMapping) -> None:
    source, build = built
    assert source.calls == ["cs", "tel"]
    assert len(build.records) == len(build.pointers) == EXPECTED_TOTAL
    groups = Counter(p["group"] for p in build.pointers)
    assert groups == {"S1": 80, "S2": 80, "S3": 80, "S4": 80, "S5": 80, "P-H": 50, "P-N": 50}
    assert Counter(p["source"] for p in build.pointers if p["group"] == "P-H") == {
        "cs": 25,
        "tel": 25,
    }
    assert [r.record_id for r in build.records] == [f"to_{i:04d}" for i in range(1, 501)]
    assert build.skipped == {"rejected": 0, "duplicate": 0, "near_duplicate": 0}
    assert build.pii_flags == []
    pattern = re.compile(mapping.filters["pn_cancel"], re.IGNORECASE)
    for record, pointer in zip(build.records, build.pointers, strict=True):
        prov = record.provenance
        assert (prov.split, prov.generator_family, prov.label_source) == (
            "test_ood",
            "public_bitext",
            "public_mapped",
        )
        assert (
            prov.content_sha256
            == pointer["content_sha256"]
            == content_sha256(record.ticket.customer_text())
        )
        assert prov.bitext is not None
        assert prov.bitext.row == pointer["bitext_row"]
        assert "{{" not in record.ticket.message
        assert record.ticket.channel == "chat_transcript"
        if pointer["group"] == "P-N":
            assert pattern.search(record.ticket.message)
            assert (record.gold.intent, record.gold.not_intent) == (
                "how_to_question",
                "cancellation_request",
            )
        tier = "probe" if pointer["group"].startswith("P-") else "T1"
        assert pointer["mapping_tier"] == prov.mapping_tier == tier


def test_pointers_carry_no_text(built: tuple[Any, Any]) -> None:
    _, build = built
    keys = {key for pointer in build.pointers for key in pointer}
    assert not keys & {"message", "text", "instruction", "subject", "ticket"}
    for record, pointer in zip(build.records, build.pointers, strict=True):
        serialized = json.dumps(pointer)
        assert record.ticket.message not in serialized
        assert record.ticket.message.split(" please ", 1)[1][:20] not in serialized


def test_build_is_deterministic(
    built: tuple[Any, Any],
    mapping: BitextMapping,
    taxonomy: Taxonomy,
    fake_bitext_source: Callable[..., Any],
) -> None:
    _, build = built
    again = build_ood(mapping, fake_bitext_source(mapping), taxonomy, now=NOW)
    assert again.pointers == build.pointers


def test_placeholders_collapse_to_one_person(built: tuple[Any, Any]) -> None:
    _, build = built
    signed = [r.ticket.message for r in build.records if " signed " in r.ticket.message]
    assert signed
    assert all(m.endswith("signed <PERSON_1>") for m in signed)


def test_rejects_are_replaced(
    built: tuple[Any, Any],
    mapping: BitextMapping,
    taxonomy: Taxonomy,
    fake_bitext_source: Callable[..., Any],
) -> None:
    _, build = built
    first = build.pointers[0]
    rejected = (first["source"], first["bitext_row"])
    rebuilt = build_ood(mapping, fake_bitext_source(mapping), taxonomy, now=NOW, rejects=[rejected])
    assert rebuilt.skipped["rejected"] == 1
    assert rejected not in {(p["source"], p["bitext_row"]) for p in rebuilt.pointers}
    assert Counter(p["group"] for p in rebuilt.pointers)["S1"] == 80


def test_duplicates_and_near_duplicates_are_skipped(
    mapping: BitextMapping, taxonomy: Taxonomy, fake_bitext_source: Callable[..., Any]
) -> None:
    exact = build_ood(
        mapping,
        fake_bitext_source(mapping, per_intent=200, duplicate="recover_password"),
        taxonomy,
        now=NOW,
    )
    assert exact.skipped["duplicate"] > 0
    near = build_ood(
        mapping,
        fake_bitext_source(mapping, per_intent=200, near_duplicate="get_refund"),
        taxonomy,
        now=NOW,
    )
    assert near.skipped["near_duplicate"] > 0
    assert len(near.records) == EXPECTED_TOTAL


def test_unfillable_group_raises(
    mapping: BitextMapping, taxonomy: Taxonomy, fake_bitext_source: Callable[..., Any]
) -> None:
    with pytest.raises(BitextError, match=r"S3: cs.get_refund has only 3 of 80"):
        build_ood(mapping, fake_bitext_source(mapping, short="get_refund"), taxonomy, now=NOW)


def test_remaining_pii_is_flagged_for_review(
    mapping: BitextMapping, taxonomy: Taxonomy, fake_bitext_source: Callable[..., Any]
) -> None:
    build = build_ood(
        mapping, fake_bitext_source(mapping, url_intent="change_plan"), taxonomy, now=NOW
    )
    s5 = {p["record_id"] for p in build.pointers if p["group"] == "S5"}
    assert set(build.pii_flags) == s5


# --------------------------------------------------------------------------- materialize


def test_materialize_round_trip(
    built: tuple[Any, Any],
    mapping: BitextMapping,
    taxonomy: Taxonomy,
    fake_bitext_source: Callable[..., Any],
) -> None:
    _, build = built
    records = materialize(build.pointers, mapping, fake_bitext_source(mapping), taxonomy, now=NOW)
    assert [r.model_dump() for r in records] == [r.model_dump() for r in build.records]


def test_materialize_verifies_hash_and_revision(
    built: tuple[Any, Any],
    mapping: BitextMapping,
    taxonomy: Taxonomy,
    fake_bitext_source: Callable[..., Any],
) -> None:
    _, build = built
    tampered = [dict(build.pointers[0], content_sha256="0" * 64)]
    with pytest.raises(BitextError, match="does not match its content hash"):
        materialize(tampered, mapping, fake_bitext_source(mapping), taxonomy, now=NOW)
    moved = [dict(build.pointers[0], bitext_revision="f" * 40)]
    with pytest.raises(BitextError, match="revision differs"):
        materialize(moved, mapping, fake_bitext_source(mapping), taxonomy, now=NOW)


# --------------------------------------------------------------------------- Hugging Face source


def test_hf_source_loads_the_pinned_revision_lazily(
    monkeypatch: pytest.MonkeyPatch, mapping: BitextMapping
) -> None:
    calls: list[tuple[str, str, str]] = []

    def load_dataset(hf_id: str, *, revision: str, split: str) -> list[dict[str, Any]]:
        calls.append((hf_id, revision, split))
        return [
            {
                "instruction": "reset my password",
                "intent": "recover_password",
                "category": "ACCOUNT",
                "flags": "BL",
            },
            {"instruction": "cancel it", "intent": "cancel_plan", "category": "SUBSCRIPTION"},
        ]

    fake = types.ModuleType("datasets")
    fake.load_dataset = load_dataset  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "datasets", fake)
    spec = mapping.sources["cs"]
    rows = HFRowSource().rows("cs", spec)
    assert calls == [(spec.hf_id, spec.revision, "train")]
    assert rows[0] == BitextRow("cs", 0, "reset my password", "recover_password", "ACCOUNT", "BL")
    assert rows[1].tags == ""
    assert rows[1].row == 1
