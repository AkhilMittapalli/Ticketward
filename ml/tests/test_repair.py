"""Validity ladder: first pass, deterministic repair level 1, fail closed (spec v1.1 §6.6)."""

import json
from collections.abc import Callable
from typing import Any

import pytest

from tw_ml.datagen.records import TriageLabels
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.eval.repair import (
    classify_output,
    normalize_enum,
    normalized_key,
    outermost_object,
    remove_trailing_commas,
    repair_l1,
    secondary_rule_holds,
    strip_code_fences,
)


@pytest.fixture
def valid(make_labels: Callable[..., TriageLabels]) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(make_labels().model_dump_json())
    return document


def test_valid_json_passes_first(taxonomy: Taxonomy, valid: dict[str, Any]) -> None:
    outcome = classify_output(json.dumps(valid), truncated=False, taxonomy=taxonomy)
    assert outcome.validity == "first_pass"
    assert outcome.labels is not None
    assert outcome.labels.intent == "sso_login_failure"
    assert outcome.actions == ()


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_output_fails_closed(taxonomy: Taxonomy, raw: str | None) -> None:
    outcome = classify_output(raw, truncated=False, taxonomy=taxonomy)
    assert (outcome.validity, outcome.labels, outcome.actions) == (
        "failed_fallback",
        None,
        ("empty_output",),
    )


def test_truncated_output_fails_even_if_it_parses(
    taxonomy: Taxonomy, valid: dict[str, Any]
) -> None:
    outcome = classify_output(json.dumps(valid), truncated=True, taxonomy=taxonomy)
    assert (outcome.validity, outcome.actions) == ("failed_fallback", ("truncated_length",))


def test_fences_prose_and_trailing_commas_are_repaired(
    taxonomy: Taxonomy, valid: dict[str, Any]
) -> None:
    body = json.dumps(valid, indent=1)[:-1] + ",\n}"  # a trailing comma before the brace
    raw = f"Here you go:\n```json\n{body}\n```"
    outcome = classify_output(raw, truncated=False, taxonomy=taxonomy)
    assert outcome.validity == "repaired_l1"
    assert outcome.actions == ("extract_object", "trailing_commas")
    fenced = classify_output(
        f"```json\n{json.dumps(valid)}\n```", truncated=False, taxonomy=taxonomy
    )
    assert (fenced.validity, fenced.actions) == ("repaired_l1", ("strip_code_fences",))


def test_enum_near_misses_and_aliases_are_mapped(taxonomy: Taxonomy, valid: dict[str, Any]) -> None:
    near = {
        **valid,
        "intent": "SSO Login-Failure",
        "priority": " High ",
        "recommended_queue": "Tier 2",
        "secondary_intents": ["Bug Report"],
        "entities": [{"type": "Error Code", "value": "SAML_ERR_302"}],
    }
    outcome = classify_output(json.dumps(near), truncated=False, taxonomy=taxonomy)
    assert outcome.validity == "repaired_l1"
    assert outcome.labels is not None
    assert outcome.labels.intent == "sso_login_failure"
    assert outcome.labels.recommended_queue == "technical_support_tier_2"
    assert outcome.labels.secondary_intents == ("bug_report",)
    assert outcome.labels.entities[0].type == "error_code"
    assert set(outcome.actions) == {
        "enum:intent",
        "enum:priority",
        "alias:recommended_queue",
        "enum:secondary_intents",
        "enum:entities.type",
    }


def test_unknown_values_are_never_guessed(taxonomy: Taxonomy, valid: dict[str, Any]) -> None:
    unknown = {**valid, "intent": "login_problem", "recommended_queue": "Tier 3"}
    outcome = classify_output(json.dumps(unknown), truncated=False, taxonomy=taxonomy)
    assert (outcome.validity, outcome.labels) == ("failed_fallback", None)
    assert outcome.actions[-1] == "schema_invalid"


def test_unknown_keys_are_never_dropped(taxonomy: Taxonomy, valid: dict[str, Any]) -> None:
    extra = {**valid, "confidence": 0.9}
    outcome = classify_output(json.dumps(extra), truncated=False, taxonomy=taxonomy)
    assert outcome.validity == "failed_fallback"


def test_secondary_intents_are_deduped_and_primary_removed(
    taxonomy: Taxonomy, valid: dict[str, Any]
) -> None:
    repeated = {**valid, "secondary_intents": ["bug_report", "sso_login_failure", "bug_report"]}
    outcome = classify_output(json.dumps(repeated), truncated=False, taxonomy=taxonomy)
    assert outcome.validity == "repaired_l1"
    assert outcome.labels is not None
    assert outcome.labels.secondary_intents == ("bug_report",)
    assert outcome.actions == ("secondary_deduped", "secondary_primary_removed")


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("no json here", "no_json_object"),
        ("{ broken: json }", "invalid_json"),
        ("[1, 2]", "no_json_object"),
        ('{"a": [1, 2,]} {"b": 1}', "invalid_json"),
    ],
)
def test_unrecoverable_text_fails_closed(taxonomy: Taxonomy, raw: str, reason: str) -> None:
    outcome = classify_output(raw, truncated=False, taxonomy=taxonomy)
    assert outcome.validity == "failed_fallback"
    assert outcome.actions[-1] == reason


def test_object_extraction_edges(taxonomy: Taxonomy) -> None:
    document, actions = repair_l1('"x" {"a": 1}', taxonomy)
    assert document == {"a": 1}
    assert actions == ("extract_object",)
    assert repair_l1('{"a": 1', taxonomy) == (None, ("no_json_object",))


def test_trailing_commas_inside_strings_are_kept() -> None:
    text = '{"a": "x, }", "b": [1, 2, ], "c": "\\", ]",}'
    assert remove_trailing_commas(text) == '{"a": "x, }", "b": [1, 2 ], "c": "\\", ]"}'


def test_helpers() -> None:
    assert normalized_key("  Technical-Support  Tier_2 ") == "technical_support_tier_2"
    assert normalize_enum(
        "Tier1", ("general_support_tier_1",), {"tier1": "general_support_tier_1"}
    ) == ("general_support_tier_1")
    assert normalize_enum("nope", ("a",), {}) is None
    assert strip_code_fences("```\n{}\n```") == "{}"
    assert strip_code_fences("{}") == "{}"
    assert outermost_object("x } {") is None


def test_secondary_rule(make_labels: Callable[..., TriageLabels]) -> None:
    assert secondary_rule_holds(make_labels(secondary_intents=["bug_report"]))
    assert not secondary_rule_holds(make_labels(secondary_intents=["sso_login_failure"]))
    assert not secondary_rule_holds(make_labels(secondary_intents=["bug_report", "bug_report"]))
