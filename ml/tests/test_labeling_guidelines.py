"""docs/labeling_guidelines.md is complete and its examples are protected by leakage C6."""

import re
from datetime import UTC, datetime

import pytest

from tw_ml.datagen.hardset import Quotas
from tw_ml.datagen.leakage import (
    LeakageInputs,
    LeakItem,
    load_leakage_config,
    read_protected_strings,
    run_leakage,
)
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy

RULE_RE = re.compile(r"^### R(\d+)\. (.+)$", re.MULTILINE)
EXAMPLE_RE = re.compile(r'^\d+\. "(.*?)"(?: \([^)]*\))? -> (.+)$', re.MULTILINE)  # "(context)" note
SECTION_RE = re.compile(r"^# --- (.+)$", re.MULTILINE)
RULE_COUNT = 14


@pytest.fixture(scope="module")
def guide(paths: RepoPaths) -> str:
    return (paths.root / "docs" / "labeling_guidelines.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rules_text(guide: str) -> dict[int, str]:
    body = guide.split("## Rules", 1)[1].split("## Edge cases", 1)[0]
    starts = list(RULE_RE.finditer(body))
    return {
        int(m.group(1)): body[
            m.start() : starts[i + 1].start() if i + 1 < len(starts) else len(body)
        ]
        for i, m in enumerate(starts)
    }


def _examples(section: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    positive, _, negative = section.partition("**Negative examples**")
    return EXAMPLE_RE.findall(positive), EXAMPLE_RE.findall(negative)


@pytest.fixture(scope="module")
def examples(rules_text: dict[int, str]) -> list[str]:
    found = []
    for section in rules_text.values():
        positive, negative = _examples(section)
        found += [text for text, _ in positive + negative]
    return found


@pytest.fixture(scope="module")
def protected(paths: RepoPaths) -> list[str]:
    return read_protected_strings(paths.spec_dir / "protected_strings.txt")


def test_every_rule_has_three_positive_and_three_negative_examples(
    rules_text: dict[int, str],
) -> None:
    assert sorted(rules_text) == list(range(1, RULE_COUNT + 1))
    for number, section in rules_text.items():
        positive, negative = _examples(section)
        assert len(positive) >= 3, f"R{number} positive"
        assert len(negative) >= 3, f"R{number} negative"


def test_examples_are_unique_and_use_taxonomy_labels(
    examples: list[str], rules_text: dict[int, str], taxonomy: Taxonomy
) -> None:
    assert len(examples) == len(set(examples))
    labels = " ".join(
        label for section in rules_text.values() for _, label in EXAMPLE_RE.findall(section)
    )
    for name in re.findall(r"(?:intent|secondary) `([a-z_]+)`", labels):
        assert taxonomy.has("Intent", name), name
    for name in re.findall(r"queue `([a-z_0-9]+)`", labels):
        assert taxonomy.has("Queue", name), name


def test_every_guideline_example_is_a_protected_string(
    examples: list[str], protected: list[str]
) -> None:
    missing = [text for text in examples if text not in protected]
    assert missing == []
    assert len(protected) == len(set(protected))


def test_protected_strings_cover_spec_examples(
    paths: RepoPaths, protected: list[str], examples: list[str]
) -> None:
    text = (paths.spec_dir / "protected_strings.txt").read_text(encoding="utf-8")
    sections = SECTION_RE.findall(text)
    assert [s.split(" ", 1)[0] for s in sections] == [
        "spec",
        "spec",
        "spec",
        "docs/labeling_guidelines.md",
    ]
    spec_entries = [e for e in protected if e not in examples]
    assert len(spec_entries) == 16 + 1 + 3  # §5.1 examples and edge cases, §9.2, §17 demo tickets
    assert "can someone actually call me" in spec_entries


def test_leakage_config_reads_this_file(paths: RepoPaths) -> None:
    cfg = load_leakage_config(paths.configs_dir / "leakage.yaml")
    assert cfg.protected.strings_file == "data/spec/protected_strings.txt"
    assert (paths.root / cfg.protected.strings_file).is_file()


def test_c6_flags_every_guideline_example(
    paths: RepoPaths, examples: list[str], protected: list[str]
) -> None:
    cfg = load_leakage_config(paths.configs_dir / "leakage.yaml")
    items = [LeakItem(f"tr_{i:05d}", "train", text) for i, text in enumerate(examples)]
    wrapped = [
        text for text in examples if len(text.split()) >= cfg.protected.containment_min_words
    ]
    items += [
        LeakItem(f"tr_{i + 1000:05d}", "train", f"Hello there. {text} Thanks a lot.")
        for i, text in enumerate(wrapped)
    ]
    report = run_leakage(
        LeakageInputs(items=items, protected_strings=protected),
        cfg,
        now=datetime(2026, 9, 27, tzinfo=UTC),
    )
    flagged = {f.a for f in report.flags if f.check == "C6"}
    assert {item.record_id for item in items} <= flagged
    assert set(report.drops) >= flagged


def test_decision_tree_and_edge_cases(guide: str, taxonomy: Taxonomy) -> None:
    tree = guide.split("## Decision tree", 1)[1].split("## Rules", 1)[0]
    assert re.findall(r"^\s*(\d+)\. ", tree, re.MULTILINE) == [str(i) for i in range(1, 13)]
    for rule in range(1, RULE_COUNT + 1):
        assert f"(R{rule})" in tree or f"R{rule}," in tree or f", R{rule}" in tree, rule
    edge = guide.split("## Edge cases", 1)[1].split("## Field reference", 1)[0]
    rows = [
        line
        for line in edge.splitlines()
        if line.startswith("| ") and not line.startswith("| Situation")
    ]
    assert len(rows) == 14
    mentioned = set(re.findall(r"`([a-z_]+)`", guide))
    assert set(taxonomy.values("Intent")) <= mentioned


def test_hard_set_guide_matches_the_validator_quotas(paths: RepoPaths) -> None:
    text = (paths.root / "docs" / "hard_set_guide.md").read_text(encoding="utf-8")
    quotas = Quotas()
    table = text.split("## Quotas", 1)[1].split("##", 1)[0]
    assert f"exactly {quotas.total} cases" in table
    assert f">= {quotas.per_intent} each" in table
    assert f">= {quotas.critical_combined} |" in table
    assert f">= {quotas.injection} |" in table
    assert f">= {quotas.needs_info} |" in table
    assert (
        f">= {quotas.human_request}, of which >= {quotas.human_request_indirect} indirect" in table
    )
    assert f">= {quotas.legal_threat_in_billing} |" in table
