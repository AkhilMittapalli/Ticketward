"""The ml copies of the frozen taxonomy tables agree with the backend (P1.5).

The ml package cannot import the backend (ADR-0003), so ``data/spec/`` keeps its own copies:

* ``label_rules.v1.yaml``: §5.8 routing defaults and allow-lists, the critical, forced-review and
  self-service sets, and the P1 human-request action (label QA and the E1 rules baseline);
* ``fact_sheet.v1.md``: the §5.3 response targets and §3 plan multipliers (generator prompts).

A change on either side must be made on both; these tests fail on any drift.
"""

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from ticketward.domain.taxonomy import (
    BASE_SLA_TARGETS,
    CRITICAL_INTENTS,
    DEFAULT_ROUTING,
    FORCED_REVIEW_INTENTS,
    HUMAN_REQUEST_ACTION,
    PLAN_FRT_MULTIPLIER,
    SELF_SERVE_ACTIONS,
    SLA_BASE_PLAN,
    TAXONOMY_VERSION,
    Intent,
    PlanTier,
    Priority,
    SlaDuration,
    SlaTargets,
    SlaUnit,
    allowed_overrides,
)

LABEL_RULES = "data/spec/label_rules.v1.yaml"
FACT_SHEET = "data/spec/fact_sheet.v1.md"
DURATION = re.compile(r"(?P<amount>\d+(?:\.\d+)?) (?P<unit>hours?|business days?)")
UNITS = {"hour": SlaUnit.hours, "business day": SlaUnit.business_days}


@pytest.fixture
def label_rules(repo_root: Path) -> dict[str, Any]:
    loaded: object = yaml.safe_load((repo_root / LABEL_RULES).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def fact_sheet(repo_root: Path) -> str:
    return (repo_root / FACT_SHEET).read_text(encoding="utf-8")


def markdown_table(document: str, heading: str) -> list[dict[str, str]]:
    """Rows of the first pipe table under ``## <heading>`` (header row = keys)."""
    lines = document.splitlines()
    assert f"## {heading}" in lines, f"missing section: {heading}"
    rows: list[list[str]] = []
    for line in lines[lines.index(f"## {heading}") + 1 :]:
        if line.startswith("## ") or (rows and not line.startswith("|")):
            break
        if line.startswith("|") and not set(line) <= set("|-: "):  # skip the delimiter row
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    assert rows, f"no table under: {heading}"
    header, *body = rows
    return [dict(zip(header, row, strict=True)) for row in body]


def duration(text: str) -> SlaDuration:
    match = DURATION.fullmatch(text)
    assert match is not None, f"unparseable duration: {text!r}"
    unit = match["unit"].removesuffix("s")
    return SlaDuration(Decimal(match["amount"]), UNITS[unit])


def members(values: list[str]) -> set[str]:
    assert len(values) == len(set(values)), f"duplicate entries: {values}"
    return set(values)


# --------------------------------------------------------------------------- label_rules.v1.yaml


def test_label_rules_target_this_taxonomy_version(label_rules: dict[str, Any]) -> None:
    assert label_rules["taxonomy_version"] == TAXONOMY_VERSION


def test_routing_defaults_match(label_rules: dict[str, Any]) -> None:
    routing = label_rules["routing"]
    assert set(routing) == set(Intent)
    for intent, default in DEFAULT_ROUTING.items():
        assert (routing[intent]["queue"], routing[intent]["action"]) == (
            default.queue,
            default.action,
        ), intent


@pytest.mark.parametrize("intent", list(Intent), ids=str)
def test_allow_lists_match(label_rules: dict[str, Any], intent: Intent) -> None:
    entry, overrides = label_rules["routing"][intent], allowed_overrides(intent)
    assert members(entry["alternate_queues"]) == overrides.queues
    assert members(entry["alternate_actions"]) == overrides.actions


def test_intent_sets_match(label_rules: dict[str, Any]) -> None:
    assert members(label_rules["critical_intents"]) == CRITICAL_INTENTS
    assert members(label_rules["forced_review_intents"]) == FORCED_REVIEW_INTENTS


def test_self_serve_actions_and_the_human_request_action_match(
    label_rules: dict[str, Any],
) -> None:
    assert members(label_rules["self_serve_actions"]) == SELF_SERVE_ACTIONS
    assert label_rules["conditional_actions"]["human_request"] == HUMAN_REQUEST_ACTION


# --------------------------------------------------------------------------- fact_sheet.v1.md


def test_response_targets_match(fact_sheet: str) -> None:
    rows = markdown_table(fact_sheet, "Response targets")
    targets = {
        row["priority"]: SlaTargets(
            duration(row["first_response"]), duration(row["resolution_target"])
        )
        for row in rows
    }
    assert len(targets) == len(rows)
    assert targets == {priority.value: BASE_SLA_TARGETS[priority] for priority in Priority}
    assert "Business plan base" in fact_sheet
    assert SLA_BASE_PLAN is PlanTier.business


def test_plan_multipliers_match(fact_sheet: str) -> None:
    rows = markdown_table(fact_sheet, "Plans")
    multipliers = {row["plan"]: Decimal(row["frt_multiplier"]) for row in rows}
    assert len(multipliers) == len(rows)
    assert multipliers == {plan.value: value for plan, value in PLAN_FRT_MULTIPLIER.items()}
