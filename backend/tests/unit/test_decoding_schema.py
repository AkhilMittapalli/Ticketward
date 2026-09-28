"""Decoding schema (spec v1.1 §6, §6.6; ERPROT constrained-decoding SI-1)."""

import json
from collections.abc import Iterator
from enum import StrEnum
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from ticketward.domain.taxonomy import (
    ChurnRisk,
    EntityType,
    Intent,
    Priority,
    ProductArea,
    Queue,
    RecommendedAction,
    Sentiment,
)
from ticketward.ml.decoding_schema import (
    ANNOTATION_KEYS,
    DECODING_EXPORTS,
    DecodingSchemaError,
    build_decoding_schemas,
    decoding_schema,
    inline_schema,
    schema_problems,
)
from ticketward.schemas.triage import Entity, TriageModelOutput


def _walk(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        for key, value in node.items():
            if key == "properties":
                for sub in value.values():
                    yield from _walk(sub)
            elif key not in {"enum", "required", "const"}:
                yield from _walk(value)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return decoding_schema(TriageModelOutput)


def _full_output() -> TriageModelOutput:
    return TriageModelOutput.model_validate(
        {
            "intent": "billing_duplicate_charge",
            "secondary_intents": ["refund_request"],
            "priority": "high",
            "sentiment": "frustrated",
            "churn_risk": "medium",
            "churn_signals": ["looking at other tools"],
            "product_area": "billing_subscriptions",
            "entities": [{"type": "invoice_id", "value": "INV-1001"}],
            "recommended_queue": "billing_and_accounts",
            "recommended_action": "escalate_to_billing_for_review",
            "customer_requested_human": False,
            "information_sufficient": True,
            "rationale": "Charged twice for one invoice.",
        }
    )


def test_references_are_inlined_and_annotations_stripped(schema: dict[str, Any]) -> None:
    text = json.dumps(schema)
    assert "$ref" not in text
    assert "$defs" not in text
    for node in _walk(schema):
        assert not ANNOTATION_KEYS & node.keys(), node


def test_every_key_is_required_in_declaration_order(schema: dict[str, Any]) -> None:
    names = list(TriageModelOutput.model_fields)
    assert list(schema["properties"]) == names
    assert schema["required"] == names
    entity = schema["properties"]["entities"]["items"]
    assert list(entity["properties"]) == entity["required"] == list(Entity.model_fields)


def test_key_order_equals_the_training_target_order(schema: dict[str, Any]) -> None:
    target = json.loads(_full_output().model_dump_json())
    assert list(target) == schema["required"]
    assert list(target["entities"][0]) == schema["properties"]["entities"]["items"]["required"]


@pytest.mark.parametrize(
    ("field", "enum"),
    [
        ("intent", Intent),
        ("priority", Priority),
        ("sentiment", Sentiment),
        ("churn_risk", ChurnRisk),
        ("product_area", ProductArea),
        ("recommended_queue", Queue),
        ("recommended_action", RecommendedAction),
    ],
)
def test_enums_are_inlined_in_taxonomy_order(
    schema: dict[str, Any], field: str, enum: type[StrEnum]
) -> None:
    assert schema["properties"][field] == {"enum": [m.value for m in enum], "type": "string"}


def test_list_fields_keep_their_bounds(schema: dict[str, Any]) -> None:
    properties = schema["properties"]
    secondary = properties["secondary_intents"]
    assert secondary["maxItems"] == 2
    assert secondary["items"]["enum"] == [m.value for m in Intent]
    assert properties["churn_signals"] == {
        "items": {"maxLength": 200, "type": "string"},
        "maxItems": 5,
        "type": "array",
    }
    entities = properties["entities"]
    assert entities["maxItems"] == 20
    entity = entities["items"]
    assert entity["additionalProperties"] is False
    assert entity["properties"]["type"]["enum"] == [m.value for m in EntityType]
    assert entity["properties"]["value"] == {"maxLength": 200, "type": "string"}
    assert properties["rationale"] == {"maxLength": 400, "type": "string"}
    assert schema["additionalProperties"] is False


def test_schema_has_no_construct_llama_cpp_drops(schema: dict[str, Any]) -> None:
    assert list(schema_problems(schema)) == []


def test_every_export_builds() -> None:
    built = build_decoding_schemas()
    assert list(built) == [name for name, _ in DECODING_EXPORTS] == ["triage_model_output"]
    assert built["triage_model_output"] == decoding_schema(TriageModelOutput)


# --------------------------------------------------------------------------- refusals

_STRICT = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class _UniqueTags(BaseModel):
    model_config = _STRICT
    tags: set[str] = Field(default_factory=set)


class _FloatBound(BaseModel):
    model_config = _STRICT
    score: float = Field(ge=0.0)


class _Unanchored(BaseModel):
    model_config = _STRICT
    code: str = Field(pattern=r"[A-Z]+")


class _LongText(BaseModel):
    model_config = _STRICT
    text: str = Field(max_length=5000)


class _DefaultsOptional(BaseModel):
    model_config = ConfigDict(extra="forbid")  # no serialization flag: defaults stay optional
    first: str
    tags: list[str] = Field(default_factory=list)


class _Open(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)
    name: str


class _IntBound(BaseModel):
    model_config = _STRICT
    count: int = Field(ge=0, le=10)


class _Described(BaseModel):
    model_config = _STRICT
    intent: Intent = Field(description="primary need")


class _Node(BaseModel):
    model_config = _STRICT
    child: "_Node | None" = None


@pytest.mark.parametrize(
    ("model", "fragment"),
    [
        (_UniqueTags, "uniqueItems is not enforced"),
        (_FloatBound, "minimum is enforced for integers only"),
        (_Unanchored, "patterns must be anchored"),
        (_LongText, "maxLength 5000 reaches the llama.cpp repetition limit"),
        (_DefaultsOptional, "every property must be required"),
        (_Open, "objects must be closed"),
        (_Node, "recursive \\$ref"),
    ],
)
def test_models_the_grammar_cannot_enforce_are_refused(
    model: type[BaseModel], fragment: str
) -> None:
    with pytest.raises(DecodingSchemaError, match=fragment):
        decoding_schema(model)


def test_integer_bounds_are_kept() -> None:
    count = decoding_schema(_IntBound)["properties"]["count"]
    assert count == {"maximum": 10, "minimum": 0, "type": "integer"}


def test_reference_siblings_are_merged_without_annotations() -> None:
    intent = decoding_schema(_Described)["properties"]["intent"]
    assert intent == {"enum": [m.value for m in Intent], "type": "string"}


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ({"$ref": "https://example.test/schema"}, "unsupported \\$ref"),
        ({"properties": {"a": {"$ref": "#/$defs/Missing"}}, "$defs": {}}, "unresolved \\$ref"),
        ({"$ref": "#/$defs/A", "$defs": {"A": ["x"]}}, "no schema object in \\$defs"),
        ({"$defs": ["not", "an", "object"]}, "\\$defs is not an object"),
    ],
)
def test_inline_refuses_bad_references(raw: dict[str, Any], fragment: str) -> None:
    with pytest.raises(DecodingSchemaError, match=fragment):
        inline_schema(raw)


def test_inline_keeps_property_names_that_look_like_annotations() -> None:
    raw: dict[str, Any] = {
        "title": "Doc",
        "type": "object",
        "properties": {"title": {"type": "string", "title": "Title"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    before = json.dumps(raw)
    assert inline_schema(raw) == {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    assert json.dumps(raw) == before  # the input is not modified


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        ({"$ref": "#/$defs/X"}, "$: $ref must be inlined"),
        ({"type": "string", "format": "email"}, "$: format 'email' is not supported by llama.cpp"),
        ({"type": "array", "items": {"type": "number", "maximum": 1}}, "$.items: maximum"),
        (
            {
                "type": "object",
                "properties": {"a": {"type": "string"}},
                "required": ["a"],
                "additionalProperties": False,
                "anyOf": [{"type": "object"}],
            },
            "$: properties cannot be mixed with anyOf/oneOf",
        ),
        ({"anyOf": [{"type": "string"}, {"not": {"type": "null"}}]}, "$.anyOf[1]: not is"),
    ],
)
def test_schema_problems_name_the_location(node: dict[str, Any], expected: str) -> None:
    problems = list(schema_problems(node))
    assert any(problem.startswith(expected) for problem in problems), problems
