"""Validity ladder for raw model outputs: first pass and repair level 1 (spec v1.1 §6.6).

:func:`classify_output` maps one raw completion to a ``prediction.v1`` validity tier:

* ``first_pass``: the text parses strictly against the contract (``TriageLabels``, the ml mirror
  of ``TriageModelOutput``) and obeys the secondary-intent rule (unique, never the primary);
* ``repaired_l1``: the deterministic, model-free repair made it valid. It strips code fences
  and surrounding prose (outermost JSON object), drops trailing commas, maps enum near-misses by
  case-fold, whitespace and hyphen/underscore normalization plus the small :data:`ALIASES`
  table, and dedupes ``secondary_intents`` and removes the primary from it. Unknown values are
  never guessed beyond that, and unknown keys are never dropped;
* ``failed_fallback``: still invalid, or truncated (``done_reason == "length"``). In the product
  truncated JSON goes to level 2 (one model retry); the bake-off has no level 2.

Under a working grammar near-misses cannot occur, so level 1 mainly serves unconstrained runs.
The applied actions are returned so a run can count them; nothing here echoes model text.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from pydantic import ValidationError

from tw_ml.datagen.records import TriageLabels
from tw_ml.datagen.taxonomy import Taxonomy

Tier = Literal["first_pass", "repaired_l1", "failed_fallback"]
ENUM_FIELDS: Final[Mapping[str, str]] = {
    "intent": "Intent",
    "priority": "Priority",
    "sentiment": "Sentiment",
    "churn_risk": "ChurnRisk",
    "product_area": "ProductArea",
    "recommended_queue": "Queue",
    "recommended_action": "RecommendedAction",
}
"""Scalar enum fields of ``TriageModelOutput`` and their vocabularies."""
ALIASES: Final[Mapping[str, Mapping[str, str]]] = {
    "Queue": {
        "tier_1": "general_support_tier_1",
        "tier1": "general_support_tier_1",
        "general_support": "general_support_tier_1",
        "tier_2": "technical_support_tier_2",
        "tier2": "technical_support_tier_2",
        "technical_support": "technical_support_tier_2",
        "billing": "billing_and_accounts",
        "customer_success": "customer_success_retention",
        "retention": "customer_success_retention",
        "security": "security_and_privacy",
        "incident": "incident_response",
        "incidents": "incident_response",
    },
}
"""Alias table of §6.6 (e.g. "Tier 2" -> ``technical_support_tier_2``), keyed by normalized text.

The P4 backend repair must use the same table (parity test with this module).
"""

_FENCE: Final = re.compile(r"^```[A-Za-z0-9_-]*[ \t]*\n?(.*?)\n?```$", re.DOTALL)
_SEPARATORS: Final = re.compile(r"[\s_\-]+")


@dataclass(frozen=True, slots=True)
class Classified:
    """The validity outcome of one raw completion.

    Attributes:
        validity: ``first_pass``, ``repaired_l1`` or ``failed_fallback``.
        labels: The validated output (``None`` when failed).
        actions: Repair steps applied, or the failure reasons (no model text).
    """

    validity: Tier
    labels: TriageLabels | None
    actions: tuple[str, ...] = ()


def normalized_key(value: str) -> str:
    """Case-fold, trim and join words with underscores (``"Tier-2 "`` -> ``tier_2``).

    Args:
        value: Raw enum text.

    Returns:
        The normalized key.
    """
    return _SEPARATORS.sub("_", value.strip().casefold()).strip("_")


def normalize_enum(
    value: str, vocabulary: tuple[str, ...], aliases: Mapping[str, str]
) -> str | None:
    """Map an enum near-miss to its member, or ``None`` when it is not one.

    Args:
        value: Raw value.
        vocabulary: Enum members.
        aliases: Alias table of this vocabulary (normalized keys).

    Returns:
        The member, or ``None`` (never a fuzzy guess).
    """
    key = normalized_key(value)
    if key in vocabulary:
        return key
    return aliases.get(key)


def strip_code_fences(text: str) -> str:
    """Remove one surrounding Markdown code fence (```` ```json ... ``` ````).

    Args:
        text: Stripped completion text.

    Returns:
        The fenced content, or ``text`` unchanged.
    """
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def outermost_object(text: str) -> str | None:
    """The span from the first ``{`` to the last ``}``.

    Args:
        text: Completion text.

    Returns:
        The candidate JSON object text, or ``None`` without braces.
    """
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else None


def remove_trailing_commas(text: str) -> str:
    """Drop commas directly before ``}`` or ``]`` outside JSON strings.

    Args:
        text: JSON-like text.

    Returns:
        The text without trailing commas.
    """
    out: list[str] = []
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "," and text[index + 1 :].lstrip()[:1] in {"}", "]"}:
            continue
        out.append(char)
    return "".join(out)


def _map_enum(value: object, enum: str, taxonomy: Taxonomy) -> tuple[object, str | None]:
    """Map one value; return it with the action taken (``None`` when unchanged)."""
    vocabulary = taxonomy.values(enum)
    if not isinstance(value, str) or value in vocabulary:
        return value, None
    aliases = ALIASES.get(enum, {})
    mapped = normalize_enum(value, vocabulary, aliases)
    if mapped is None:
        return value, None
    return mapped, "alias" if normalized_key(value) in aliases else "enum"


def _normalize_enums(document: dict[str, Any], taxonomy: Taxonomy) -> list[str]:
    actions: list[str] = []
    for field, enum in ENUM_FIELDS.items():
        if field not in document:
            continue
        document[field], action = _map_enum(document[field], enum, taxonomy)
        if action:
            actions.append(f"{action}:{field}")
    secondary = document.get("secondary_intents")
    if isinstance(secondary, list):
        for index, value in enumerate(secondary):
            secondary[index], action = _map_enum(value, "Intent", taxonomy)
            if action:
                actions.append(f"{action}:secondary_intents")
    entities = document.get("entities")
    if isinstance(entities, list):
        for entity in entities:
            if isinstance(entity, dict) and "type" in entity:
                entity["type"], action = _map_enum(entity["type"], "EntityType", taxonomy)
                if action:
                    actions.append(f"{action}:entities.type")
    return actions


def _repair_secondary(document: dict[str, Any]) -> list[str]:
    secondary = document.get("secondary_intents")
    if not isinstance(secondary, list) or not all(isinstance(s, str) for s in secondary):
        return []
    actions: list[str] = []
    unique = list(dict.fromkeys(secondary))
    if len(unique) != len(secondary):
        actions.append("secondary_deduped")
    primary = document.get("intent")
    if primary in unique:
        unique.remove(primary)
        actions.append("secondary_primary_removed")
    document["secondary_intents"] = unique
    return actions


def repair_l1(raw: str, taxonomy: Taxonomy) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    """Apply the deterministic level-1 repair to a raw completion.

    Args:
        raw: Completion text.
        taxonomy: Taxonomy (enum vocabularies).

    Returns:
        The repaired JSON object (not yet validated) or ``None``, and the actions applied (or
        the reason no object could be recovered).
    """
    actions: list[str] = []
    text = raw.strip()
    unfenced = strip_code_fences(text)
    if unfenced != text:
        actions.append("strip_code_fences")
        text = unfenced
    candidate = outermost_object(text)
    if candidate is None:
        return None, (*actions, "no_json_object")
    if candidate != text:
        actions.append("extract_object")
    try:
        document = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            document = json.loads(remove_trailing_commas(candidate))
        except json.JSONDecodeError:
            return None, (*actions, "invalid_json")
        actions.append("trailing_commas")
    if not isinstance(document, dict):  # pragma: no cover - a parsed "{...}" span is an object
        return None, (*actions, "not_an_object")
    actions.extend(_normalize_enums(document, taxonomy))
    actions.extend(_repair_secondary(document))
    return document, tuple(actions)


def _strict(text: str) -> TriageLabels | None:
    try:
        return TriageLabels.model_validate_json(text, strict=True)
    except ValidationError:
        return None


def secondary_rule_holds(labels: TriageLabels) -> bool:
    """Whether ``secondary_intents`` is unique and free of the primary intent (§5.1).

    Args:
        labels: A contract-valid output.

    Returns:
        True when the post-validation rule holds.
    """
    secondary = labels.secondary_intents
    return len(set(secondary)) == len(secondary) and labels.intent not in secondary


def classify_output(raw: str | None, *, truncated: bool, taxonomy: Taxonomy) -> Classified:
    """Classify one raw completion into a validity tier.

    Args:
        raw: Completion text (``None`` when the request failed).
        truncated: The model stopped on the token limit (``done_reason == "length"``).
        taxonomy: Taxonomy (enum vocabularies for level 1).

    Returns:
        The outcome.
    """
    if truncated:
        return Classified("failed_fallback", None, ("truncated_length",))
    if raw is None or not raw.strip():
        return Classified("failed_fallback", None, ("empty_output",))
    labels = _strict(raw)
    if labels is not None and secondary_rule_holds(labels):
        return Classified("first_pass", labels)
    document, actions = repair_l1(raw, taxonomy)
    if document is None:
        return Classified("failed_fallback", None, actions)
    repaired = _strict(json.dumps(document, ensure_ascii=False))
    if repaired is None or not secondary_rule_holds(repaired):
        return Classified("failed_fallback", None, (*actions, "schema_invalid"))
    return Classified("repaired_l1", repaired, actions)
