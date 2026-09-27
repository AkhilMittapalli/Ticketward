"""Taxonomy enums loaded from the exported JSON Schemas (spec §5, §6).

The backend owns the Pydantic contracts and exports them to ``schemas/json/``. The ml
package must not import the backend (ADR-0003), so the enums are read from the committed
schemas at runtime. ``tests/test_taxonomy.py`` fails when the schemas and the ml side
drift apart (enum values, contract field order, routing tables, matrix values).

Label fields in ml models are plain ``str`` annotated with a membership validator, so
mypy stays strict while the value set comes from the contract, never from ml code.
"""

import functools
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Final

from pydantic import AfterValidator

from tw_ml.datagen.paths import find_repo_root

TAXONOMY_SCHEMA: Final = "taxonomy.schema.json"
TRIAGE_OUTPUT_SCHEMA: Final = "triage_model_output.schema.json"
TICKET_CREATE_SCHEMA: Final = "ticket_create.schema.json"

MODEL_LABEL_ENUMS: Final[tuple[str, ...]] = (
    "Intent",
    "Queue",
    "Priority",
    "Sentiment",
    "ChurnRisk",
    "ProductArea",
    "EntityType",
    "SamlIdp",
    "RecommendedAction",
    "PlanTier",
    "Channel",
)
"""Enums that appear in labels or tickets; changing any of them needs a new taxonomy_version."""


class TaxonomyError(ValueError):
    """Raised when the exported schemas are missing, malformed or lack an enum."""


@dataclass(frozen=True, slots=True)
class Taxonomy:
    """The frozen vocabularies of one taxonomy version.

    Attributes:
        version: ``taxonomy_version`` constant from the schema (e.g. ``2026-09-v1``).
        enums: Enum name to ordered member values, exactly as exported.
    """

    version: str
    enums: Mapping[str, tuple[str, ...]]

    def values(self, name: str) -> tuple[str, ...]:
        """Return the ordered values of one enum.

        Args:
            name: Enum name as exported (``Intent``, ``Queue``...).

        Returns:
            The member values in contract order.

        Raises:
            TaxonomyError: If the enum is not part of the schema.
        """
        try:
            return self.enums[name]
        except KeyError:
            msg = f"enum {name!r} is not defined in {TAXONOMY_SCHEMA}"
            raise TaxonomyError(msg) from None

    def has(self, name: str, value: str) -> bool:
        """Return whether ``value`` is a member of enum ``name``.

        Args:
            name: Enum name.
            value: Candidate value.

        Returns:
            True when the value is a member.
        """
        return value in self.values(name)

    def fingerprint(self, names: tuple[str, ...] = MODEL_LABEL_ENUMS) -> str:
        """Hash the given enums (and the version) for drift detection.

        Args:
            names: Enum names to include.

        Returns:
            Hex SHA-256 of a canonical JSON document.
        """
        document = {"version": self.version, "enums": {n: list(self.values(n)) for n in names}}
        payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def schemas_dir_default() -> Path:
    """Return the repository's ``schemas/json`` directory.

    Returns:
        Absolute path of the exported contracts.
    """
    return find_repo_root() / "schemas" / "json"


def load_json_schema(name: str, schemas_dir: Path | None = None) -> dict[str, Any]:
    """Read one exported JSON Schema.

    Args:
        name: File name inside ``schemas/json`` (e.g. ``taxonomy.schema.json``).
        schemas_dir: Directory override (defaults to the repository's).

    Returns:
        The parsed schema document.

    Raises:
        TaxonomyError: If the file is missing or is not a JSON object.
    """
    path = (schemas_dir or schemas_dir_default()) / name
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        msg = f"exported schema not found: {name}"
        raise TaxonomyError(msg) from None
    except json.JSONDecodeError as exc:
        msg = f"exported schema {name} is not valid JSON (line {exc.lineno})"
        raise TaxonomyError(msg) from None
    if not isinstance(document, dict):
        msg = f"exported schema {name} is not a JSON object"
        raise TaxonomyError(msg)
    return document


def enums_from_schema(document: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """Collect every string enum under ``$defs``.

    Args:
        document: A JSON Schema document.

    Returns:
        Enum name to ordered values (definitions without an ``enum`` are skipped).
    """
    definitions = document.get("$defs", {})
    enums: dict[str, tuple[str, ...]] = {}
    for name, definition in definitions.items():
        values = definition.get("enum") if isinstance(definition, dict) else None
        if isinstance(values, list) and all(isinstance(v, str) for v in values):
            enums[name] = tuple(values)
    return enums


@functools.cache
def load_taxonomy(schemas_dir: Path | None = None) -> Taxonomy:
    """Load the taxonomy from ``taxonomy.schema.json`` (cached per directory).

    Args:
        schemas_dir: Directory override (defaults to the repository's).

    Returns:
        The frozen taxonomy.

    Raises:
        TaxonomyError: If the version constant or a label enum is missing.
    """
    document = load_json_schema(TAXONOMY_SCHEMA, schemas_dir)
    version = document.get("properties", {}).get("taxonomy_version", {}).get("const")
    if not isinstance(version, str) or not version:
        msg = f"{TAXONOMY_SCHEMA} has no taxonomy_version const"
        raise TaxonomyError(msg)
    enums = enums_from_schema(document)
    missing = [name for name in MODEL_LABEL_ENUMS if name not in enums]
    if missing:
        msg = f"{TAXONOMY_SCHEMA} lacks enums: {', '.join(missing)}"
        raise TaxonomyError(msg)
    return Taxonomy(version=version, enums=MappingProxyType(enums))


def member_check(enum_name: str) -> Callable[[str], str]:
    """Build a validator that accepts only members of ``enum_name``.

    Args:
        enum_name: Enum to validate against (resolved lazily from the default schemas).

    Returns:
        A function for :class:`pydantic.AfterValidator`.
    """

    def check(value: str) -> str:
        if not load_taxonomy().has(enum_name, value):
            msg = f"not a valid {enum_name} value"
            raise ValueError(msg)
        return value

    check.__name__ = f"is_{enum_name}"
    return check


IntentValue = Annotated[str, AfterValidator(member_check("Intent"))]
QueueValue = Annotated[str, AfterValidator(member_check("Queue"))]
PriorityValue = Annotated[str, AfterValidator(member_check("Priority"))]
SentimentValue = Annotated[str, AfterValidator(member_check("Sentiment"))]
ChurnRiskValue = Annotated[str, AfterValidator(member_check("ChurnRisk"))]
ProductAreaValue = Annotated[str, AfterValidator(member_check("ProductArea"))]
EntityTypeValue = Annotated[str, AfterValidator(member_check("EntityType"))]
RecommendedActionValue = Annotated[str, AfterValidator(member_check("RecommendedAction"))]
PlanTierValue = Annotated[str, AfterValidator(member_check("PlanTier"))]
ChannelValue = Annotated[str, AfterValidator(member_check("Channel"))]
