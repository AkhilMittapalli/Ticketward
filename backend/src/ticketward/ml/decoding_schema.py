"""Decoding schema for grammar-constrained generation (spec v1.1 §6, §6.6; ERPROT SI-1).

``decoding_schema(TriageModelOutput)`` is what the local providers send as the Ollama
``format`` (JSON Schema -> llama.cpp grammar) and as the vLLM ``response_format``. The raw
``model_json_schema()`` is never sent, because llama.cpp's converter has three traps for it
(ERPROT ``constrained-decoding`` Q1 and Q5):

* ``$defs``/``$ref`` schemas can fail silently (HTTP 200 with schema-violating JSON,
  llama.cpp #21228 and #8073), so every reference is inlined;
* llama.cpp emits required properties first and optional ones last, as optional, so the
  defaulted lists would move behind ``rationale``. The serialization-mode schema of a model
  with ``json_schema_serialization_defaults_required=True`` makes every key required; the
  grammar then keeps declaration order, which is also the ``model_dump_json()`` key order of
  the training target (spec §9.4);
* unsupported keywords are skipped silently. :data:`UNSUPPORTED_KEYWORDS` and the other
  checks below encode the limits the research note documents. A model that relies on one of
  them is refused instead of exported, because its grammar would not enforce the rule; such
  rules belong in post-validation (e.g. the ``secondary_intents`` uniqueness that repair
  level 1 restores, §6.6).

Annotation keys (``title``, ``description``, ``examples``, ``default``) are stripped: they
do not constrain the grammar. ``scripts/export_schemas.py`` writes the result to
``schemas/json/triage_model_output.decoding.json`` and ``--check`` fails CI when it drifts.
"""

from collections.abc import Iterator, Mapping
from typing import Any, Final

from pydantic import BaseModel

from ticketward.schemas.triage import TriageModelOutput

ANNOTATION_KEYS: Final[frozenset[str]] = frozenset({"title", "description", "examples", "default"})
"""Keywords that only annotate; removed from the decoding schema."""

UNSUPPORTED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "uniqueItems",
        "contains",
        "minContains",
        "maxContains",
        "$anchor",
        "not",
        "if",
        "then",
        "else",
        "dependentSchemas",
        "patternProperties",
        "prefixItems",
    }
)
"""Keywords llama.cpp skips silently or handles incorrectly (ERPROT constrained-decoding Q1)."""

NUMERIC_BOUNDS: Final[frozenset[str]] = frozenset(
    {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}
)
"""Bounds llama.cpp enforces for ``"type": "integer"`` only."""

UNSUPPORTED_FORMATS: Final[frozenset[str]] = frozenset({"uri", "email"})
"""String formats the llama.cpp converter lacks."""

REPETITION_KEYWORDS: Final[tuple[str, ...]] = ("minLength", "maxLength", "minItems", "maxItems")
MAX_REPETITION: Final = 2000
"""llama.cpp ``MAX_REPETITION_THRESHOLD``: bounds at or above it emit unparseable GBNF."""

DECODING_EXPORTS: Final[tuple[tuple[str, type[BaseModel]], ...]] = (
    ("triage_model_output", TriageModelOutput),
)
"""(file stem, model): exported as ``schemas/json/<stem>.decoding.json``."""

_SCHEMA_MAPS: Final = frozenset({"properties", "$defs", "definitions", "dependentSchemas"})
_SCHEMA_LISTS: Final = frozenset({"anyOf", "oneOf", "allOf", "prefixItems"})
_SCHEMA_VALUES: Final = frozenset(
    {
        "items",
        "additionalProperties",
        "not",
        "if",
        "then",
        "else",
        "contains",
        "propertyNames",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
_REF_PREFIX: Final = "#/$defs/"


class DecodingSchemaError(ValueError):
    """Raised when a model cannot be expressed as a faithful decoding schema."""


def decoding_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Derive the grammar-safe JSON Schema of a contract model.

    The model (and every nested model) needs ``extra="forbid"`` and
    ``json_schema_serialization_defaults_required=True``.

    Args:
        model: Contract model, e.g. ``TriageModelOutput``.

    Returns:
        A schema with every ``$ref`` inlined, annotation keys stripped, every property
        required and properties in declaration order.

    Raises:
        DecodingSchemaError: If a reference cannot be resolved or is recursive, or the schema
            uses a construct the llama.cpp converter would drop or mis-handle.
    """
    schema = inline_schema(model.model_json_schema(mode="serialization"))
    problems = sorted(set(schema_problems(schema)))
    if problems:
        raise DecodingSchemaError("; ".join(problems))
    return schema


def inline_schema(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Inline every local ``$ref`` of a schema and strip the annotation keys.

    Args:
        raw: A schema whose references point into its top-level ``$defs``.

    Returns:
        A new schema without ``$defs`` (the input is not modified).

    Raises:
        DecodingSchemaError: If a reference is not local, unresolved or recursive.
    """
    definitions = raw.get("$defs", {})
    if not isinstance(definitions, dict):
        msg = "$defs is not an object"
        raise DecodingSchemaError(msg)
    body = {key: value for key, value in raw.items() if key != "$defs"}
    return _inline_object(body, definitions, ())


def build_decoding_schemas() -> dict[str, dict[str, Any]]:
    """Build every exported decoding schema.

    Returns:
        Mapping of file stem (``triage_model_output``) to decoding schema.
    """
    return {name: decoding_schema(model) for name, model in DECODING_EXPORTS}


def _inline(node: object, definitions: Mapping[str, Any], stack: tuple[str, ...]) -> object:
    """Copy ``node`` with every ``$ref`` replaced by its definition and annotations removed."""
    if isinstance(node, list):
        return [_inline(item, definitions, stack) for item in node]
    if isinstance(node, dict):
        return _inline_object(node, definitions, stack)
    return node


def _inline_object(
    node: Mapping[str, Any], definitions: Mapping[str, Any], stack: tuple[str, ...]
) -> dict[str, Any]:
    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith(_REF_PREFIX):
            msg = f"unsupported $ref {ref!r}"
            raise DecodingSchemaError(msg)
        name = ref.removeprefix(_REF_PREFIX)
        if name in stack:
            msg = f"recursive $ref {name!r} cannot be inlined"
            raise DecodingSchemaError(msg)
        target = definitions.get(name)
        if not isinstance(target, dict):
            msg = f"unresolved $ref {name!r} (no schema object in $defs)"
            raise DecodingSchemaError(msg)
        resolved = _inline_object(target, definitions, (*stack, name))
        siblings = _inline_object(
            {k: v for k, v in node.items() if k != "$ref"}, definitions, stack
        )
        return {**resolved, **siblings}
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in ANNOTATION_KEYS:
            continue
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            # Property names may equal annotation keywords ("title"): keep every name.
            out[key] = {name: _inline(sub, definitions, stack) for name, sub in value.items()}
        elif key in _SCHEMA_LISTS or key in _SCHEMA_VALUES:
            out[key] = _inline(value, definitions, stack)
        else:
            out[key] = value  # data keywords (type, enum, const, required, bounds) verbatim
    return out


def schema_problems(node: object, path: str = "$") -> Iterator[str]:
    """Yield every construct the llama.cpp converter would drop or mis-handle.

    Args:
        node: A (sub-)schema.
        path: Location of ``node``, for the messages.

    Yields:
        One message per problem, with its location.
    """
    if isinstance(node, list):
        for index, item in enumerate(node):
            yield from schema_problems(item, f"{path}[{index}]")
        return
    if not isinstance(node, dict):
        return
    yield from _keyword_problems(node, path)
    if "properties" in node:
        yield from _object_problems(node, path)
    for key, value in node.items():
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            for name, sub in value.items():
                yield from schema_problems(sub, f"{path}.{key}.{name}")
        elif key in _SCHEMA_LISTS or key in _SCHEMA_VALUES:
            yield from schema_problems(value, f"{path}.{key}")


def _keyword_problems(node: Mapping[str, Any], path: str) -> Iterator[str]:
    for key in ("$ref", "$defs", "definitions"):
        if key in node:
            yield f"{path}: {key} must be inlined"
    for key in sorted(UNSUPPORTED_KEYWORDS & node.keys()):
        yield f"{path}: {key} is not enforced by llama.cpp"
    if node.get("type") != "integer":
        for key in sorted(NUMERIC_BOUNDS & node.keys()):
            yield f"{path}: {key} is enforced for integers only"
    if node.get("format") in UNSUPPORTED_FORMATS:
        yield f"{path}: format {node['format']!r} is not supported by llama.cpp"
    pattern = node.get("pattern")
    if isinstance(pattern, str) and not (pattern.startswith("^") and pattern.endswith("$")):
        yield f"{path}: patterns must be anchored with ^ and $"
    for key in REPETITION_KEYWORDS:
        value = node.get(key)
        if isinstance(value, int) and value >= MAX_REPETITION:
            yield f"{path}: {key} {value} reaches the llama.cpp repetition limit {MAX_REPETITION}"


def _object_problems(node: Mapping[str, Any], path: str) -> Iterator[str]:
    properties = node["properties"]
    if "anyOf" in node or "oneOf" in node:
        yield f"{path}: properties cannot be mixed with anyOf/oneOf"
    if node.get("additionalProperties") is not False:
        yield f"{path}: objects must be closed (additionalProperties false)"
    if not isinstance(properties, dict) or node.get("required") != list(properties):
        yield f"{path}: every property must be required, in declaration order"
