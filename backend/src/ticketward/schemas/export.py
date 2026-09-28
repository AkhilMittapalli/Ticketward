"""JSON Schema (draft 2020-12) export of the data contracts (spec §5, §6).

The exported files in ``schemas/json/`` are the single source for JSON Schema
consumers (TypeScript codegen, the ml package). Property order follows model field
order on purpose: it is the order the SLM emits keys in. Constrained decoding does
not use these files directly: it uses the derived ``*.decoding.json`` schemas
(``ticketward.ml.decoding_schema``: references inlined, every key required).
"""

import json
from collections.abc import Mapping
from typing import Any, Final

from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaMode

from ticketward.domain.taxonomy import TAXONOMY_ENUMS, TAXONOMY_VERSION
from ticketward.schemas.problem import ProblemDetail
from ticketward.schemas.ticket import TicketCreate
from ticketward.schemas.triage import TriageModelOutput, TriageResult

JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"

MODEL_EXPORTS: Final[tuple[tuple[str, type[BaseModel], JsonSchemaMode], ...]] = (
    ("ticket_create", TicketCreate, "validation"),
    ("triage_model_output", TriageModelOutput, "validation"),
    ("triage_result", TriageResult, "serialization"),
    ("problem_detail", ProblemDetail, "serialization"),
)
"""(file stem, model, mode): inputs we validate use ``validation``, outputs ``serialization``."""


def model_schema(model: type[BaseModel], mode: JsonSchemaMode) -> dict[str, Any]:
    """Return ``model``'s JSON Schema with the draft 2020-12 dialect declared.

    Args:
        model: Contract model.
        mode: ``validation`` for inputs, ``serialization`` for outputs.

    Returns:
        The JSON Schema document.
    """
    return {"$schema": JSON_SCHEMA_DIALECT, **model.model_json_schema(mode=mode)}


def taxonomy_schema() -> dict[str, Any]:
    """Return a JSON Schema document defining every frozen taxonomy enum.

    Returns:
        A document whose ``$defs`` hold one string enum per vocabulary and whose
        ``taxonomy_version`` property is a constant.
    """
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": "TicketwardTaxonomy",
        "description": "Frozen domain taxonomy (spec section 5). Changing it requires an ADR.",
        "type": "object",
        "properties": {"taxonomy_version": {"const": TAXONOMY_VERSION}},
        "required": ["taxonomy_version"],
        "additionalProperties": False,
        "$defs": {
            enum.__name__: {
                "title": enum.__name__,
                "description": (enum.__doc__ or "").strip(),
                "type": "string",
                "enum": [member.value for member in enum],
            }
            for enum in TAXONOMY_ENUMS
        },
    }


def build_json_schemas() -> dict[str, dict[str, Any]]:
    """Build every exported JSON Schema document.

    Returns:
        Mapping of file stem (``ticket_create``) to schema document.
    """
    schemas = {name: model_schema(model, mode) for name, model, mode in MODEL_EXPORTS}
    schemas["taxonomy"] = taxonomy_schema()
    return schemas


def render_json(document: Mapping[str, Any]) -> str:
    """Serialize a JSON document deterministically (2-space indent, LF, final newline).

    Args:
        document: JSON-compatible mapping.

    Returns:
        The rendered text.
    """
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
