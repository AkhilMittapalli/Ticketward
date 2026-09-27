"""Label rules as data (``data/spec/label_rules.v1.yaml``) plus the derivations built on them.

The rules encode spec v1.1 §5.1 (critical and forced-review intents), §5.3 (priority before
policy floors), §5.5 (the single churn rule, A-06), §5.8 (routing) and §9.2. They drive the
P-B scenario-spec gold labels, the P-A label rules shown to the generator and the
rule-checker in ``validate.py``. Every value is checked against the exported taxonomy on load.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import yaml

from tw_ml.datagen.paths import default_paths
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy

LABEL_RULES_FILE: Final = "label_rules.v1.yaml"
HumanRequestKind = Literal["none", "direct", "indirect"]
ChurnCue = Literal[
    "none", "vague_alternatives", "repeated_contact", "explicit_cancel", "competitor", "ultimatum"
]
STRONG_CHURN_CUES: Final[frozenset[str]] = frozenset({"explicit_cancel", "competitor", "ultimatum"})
MEDIUM_CHURN_CUES: Final[frozenset[str]] = frozenset({"vague_alternatives", "repeated_contact"})
PRIORITY_ORDER: Final[tuple[str, ...]] = ("low", "normal", "high", "urgent")


class LabelRulesError(ValueError):
    """Raised when the label-rules file is malformed or disagrees with the taxonomy."""


@dataclass(frozen=True, slots=True)
class Routing:
    """Routing entry for one intent (spec §5.8 + ml allow-lists).

    Attributes:
        queue: Default queue.
        action: Default action.
        alternate_queues: Queues also accepted by label QA.
        alternate_actions: Actions also accepted by label QA.
    """

    queue: str
    action: str
    alternate_queues: tuple[str, ...]
    alternate_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PriorityRule:
    """Priority guidance for one intent (§5.3, before policy floors).

    Attributes:
        base: Typical priority.
        severe: Priority for a "severe" cell.
        plausible: Labels that do not raise an R9 warning.
    """

    base: str
    severe: str
    plausible: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LabelRules:
    """Loaded and validated label rules.

    Attributes:
        version: Rules file version.
        critical_intents: §5.1 critical intents.
        forced_review_intents: §5.1 forced-review intents.
        billing_intents: Billing intents (legal-threat-inside-billing stratum).
        self_serve_actions: Actions that imply self-service resolution.
        human_request_action: Action required when the customer asks for a human.
        insufficient_info_action: Action when information is insufficient.
        insufficient_info_keeps_default: Intents whose default action already asks for details.
        routing: Intent to routing entry (every intent present).
        priority: Intent to priority rule (every intent present).
        negative_sentiments: Sentiments that make business/enterprise tickets churn-medium.
        medium_plans: Plans for that rule.
        high_cues: Compiled explicit-cancel / ultimatum patterns.
        competitor_move: Compiled "moving to" pattern (paired with a competitor name).
        vague_cues: Compiled vague-alternatives patterns.
        repeated_contact_cues: Compiled repeated-contact patterns.
        human_direct: Compiled direct human-request patterns.
        human_indirect: Compiled indirect human-request patterns.
    """

    version: str
    critical_intents: frozenset[str]
    forced_review_intents: frozenset[str]
    billing_intents: frozenset[str]
    self_serve_actions: frozenset[str]
    human_request_action: str
    insufficient_info_action: str
    insufficient_info_keeps_default: frozenset[str]
    routing: Mapping[str, Routing]
    priority: Mapping[str, PriorityRule]
    negative_sentiments: frozenset[str]
    medium_plans: frozenset[str]
    high_cues: tuple[re.Pattern[str], ...]
    competitor_move: re.Pattern[str]
    vague_cues: tuple[re.Pattern[str], ...]
    repeated_contact_cues: tuple[re.Pattern[str], ...]
    human_direct: tuple[re.Pattern[str], ...]
    human_indirect: tuple[re.Pattern[str], ...]

    # ------------------------------------------------------------------ routing
    def allowed_queues(self, intent: str) -> tuple[str, ...]:
        """Queues label QA accepts for a primary intent.

        Args:
            intent: Primary intent.

        Returns:
            The default queue followed by the alternates.
        """
        entry = self.routing[intent]
        return (entry.queue, *entry.alternate_queues)

    def allowed_actions(
        self, intent: str, *, customer_requested_human: bool, information_sufficient: bool
    ) -> tuple[str, ...]:
        """Actions label QA accepts for a primary intent and the two flags.

        Args:
            intent: Primary intent.
            customer_requested_human: Human-request flag.
            information_sufficient: Information-sufficient flag.

        Returns:
            Allowed actions; the labeling-rule action comes first.
        """
        expected = self.expected_action(
            intent,
            customer_requested_human=customer_requested_human,
            information_sufficient=information_sufficient,
        )
        entry = self.routing[intent]
        if customer_requested_human:
            return (expected,)
        pool = [expected, entry.action, *entry.alternate_actions]
        return tuple(dict.fromkeys(pool))

    def expected_action(
        self, intent: str, *, customer_requested_human: bool, information_sufficient: bool
    ) -> str:
        """The labeling-rule action (guidelines R11): human request, then missing info, then §5.8.

        Args:
            intent: Primary intent.
            customer_requested_human: Human-request flag.
            information_sufficient: Information-sufficient flag.

        Returns:
            The action a labeler should choose.
        """
        if customer_requested_human:
            return self.human_request_action
        keeps_default = (
            intent in self.forced_review_intents or intent in self.insufficient_info_keeps_default
        )
        if not information_sufficient and not keeps_default:
            return self.insufficient_info_action
        return self.routing[intent].action

    def is_critical(self, intent: str) -> bool:
        """Return whether an intent is one of the five critical categories.

        Args:
            intent: Intent value.

        Returns:
            True for critical intents.
        """
        return intent in self.critical_intents

    # ------------------------------------------------------------------ priority
    def derive_priority(self, intent: str, *, severe: bool) -> str:
        """Priority implied by a scenario (before policy floors).

        Args:
            intent: Primary intent.
            severe: Whether the cell is in the "severe" stratum.

        Returns:
            A Priority value.
        """
        rule = self.priority[intent]
        return rule.severe if severe else rule.base

    # ------------------------------------------------------------------ churn
    def derive_churn(self, cue: str, *, sentiment: str, plan: str, intents: Iterable[str]) -> str:
        """Apply the single churn rule (§5.5, A-06) to a scenario.

        Args:
            cue: The cell's churn cue.
            sentiment: Latest-message sentiment.
            plan: Customer plan tier.
            intents: Primary and secondary intents.

        Returns:
            ``high``, ``medium`` or ``low``.
        """
        if cue in STRONG_CHURN_CUES or "cancellation_request" in set(intents):
            return "high"
        if cue in MEDIUM_CHURN_CUES:
            return "medium"
        if sentiment in self.negative_sentiments and plan in self.medium_plans:
            return "medium"
        return "low"

    def has_high_cue(self, text: str, competitors: Sequence[str] = ()) -> bool:
        """Return whether text contains an explicit churn cue (cancel, competitor, ultimatum).

        Args:
            text: Ticket text.
            competitors: Competitor names that count when preceded by a "moving to" phrase.

        Returns:
            True when a high-churn cue is present.
        """
        if any(p.search(text) for p in self.high_cues):
            return True
        return any(self._competitor_move(text, name) for name in competitors if name)

    def has_medium_cue(self, text: str) -> bool:
        """Return whether text contains a vague-alternatives or repeated-contact cue.

        Args:
            text: Ticket text.

        Returns:
            True when a medium-churn cue is present.
        """
        patterns = (*self.vague_cues, *self.repeated_contact_cues)
        return any(p.search(text) for p in patterns)

    def _competitor_move(self, text: str, name: str) -> bool:
        for match in self.competitor_move.finditer(text):
            if name.lower() in text[match.end() : match.end() + len(name) + 12].lower():
                return True
        return False

    # ------------------------------------------------------------------ human request
    def human_request_kind(self, text: str) -> HumanRequestKind:
        """Classify a text's request for a person with the QA lexicon.

        Args:
            text: Ticket text.

        Returns:
            ``direct``, ``indirect`` or ``none``.
        """
        if any(p.search(text) for p in self.human_direct):
            return "direct"
        if any(p.search(text) for p in self.human_indirect):
            return "indirect"
        return "none"


def load_label_rules(path: Path | None = None, taxonomy: Taxonomy | None = None) -> LabelRules:
    """Load ``label_rules.v1.yaml`` and validate it against the taxonomy.

    Args:
        path: File override (defaults to ``data/spec/label_rules.v1.yaml``).
        taxonomy: Taxonomy to validate against (defaults to the exported one).

    Returns:
        The validated rules.

    Raises:
        LabelRulesError: If a value is not a taxonomy member or an intent is missing.
    """
    tax = taxonomy or load_taxonomy()
    source = path or default_paths().spec_dir / LABEL_RULES_FILE
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"{source.name} must be a mapping"
        raise LabelRulesError(msg)
    if raw.get("taxonomy_version") != tax.version:
        msg = f"{source.name} targets taxonomy {raw.get('taxonomy_version')}, not {tax.version}"
        raise LabelRulesError(msg)
    intents = set(tax.values("Intent"))
    routing = _routing(raw.get("routing", {}), tax)
    priority = _priority(raw.get("priority", {}), tax)
    for name, table in (("routing", routing), ("priority", priority)):
        if set(table) != intents:
            msg = f"{source.name}: {name} must list exactly the taxonomy intents"
            raise LabelRulesError(msg)
    churn = raw.get("churn", {})
    human = raw.get("human_request", {})
    conditional = raw.get("conditional_actions", {})
    return LabelRules(
        version=str(raw.get("version", "")),
        critical_intents=_members(raw, "critical_intents", tax, "Intent"),
        forced_review_intents=_members(raw, "forced_review_intents", tax, "Intent"),
        billing_intents=_members(raw, "billing_intents", tax, "Intent"),
        self_serve_actions=_members(raw, "self_serve_actions", tax, "RecommendedAction"),
        human_request_action=_member(conditional.get("human_request"), tax, "RecommendedAction"),
        insufficient_info_action=_member(
            conditional.get("insufficient_information"), tax, "RecommendedAction"
        ),
        insufficient_info_keeps_default=_members(
            raw, "insufficient_information_keeps_default", tax, "Intent"
        ),
        routing=routing,
        priority=priority,
        negative_sentiments=frozenset(
            _member(v, tax, "Sentiment") for v in churn.get("negative_sentiments", [])
        ),
        medium_plans=frozenset(_member(v, tax, "PlanTier") for v in churn.get("medium_plans", [])),
        high_cues=_compile(churn.get("high_cues", [])),
        competitor_move=re.compile(str(churn.get("competitor_move", r"(?!)")), re.IGNORECASE),
        vague_cues=_compile(churn.get("vague_cues", [])),
        repeated_contact_cues=_compile(churn.get("repeated_contact_cues", [])),
        human_direct=_compile(human.get("direct", [])),
        human_indirect=_compile(human.get("indirect", [])),
    )


def _compile(patterns: Iterable[Any]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(str(p), re.IGNORECASE) for p in patterns)


def _member(value: object, tax: Taxonomy, enum: str) -> str:
    if not isinstance(value, str) or not tax.has(enum, value):
        msg = f"label rules: {value!r} is not a {enum} value"
        raise LabelRulesError(msg)
    return value


def _members(raw: Mapping[str, Any], key: str, tax: Taxonomy, enum: str) -> frozenset[str]:
    return frozenset(_member(v, tax, enum) for v in raw.get(key, []))


def _routing(raw: Mapping[str, Any], tax: Taxonomy) -> dict[str, Routing]:
    table: dict[str, Routing] = {}
    for intent, entry in raw.items():
        table[_member(intent, tax, "Intent")] = Routing(
            queue=_member(entry.get("queue"), tax, "Queue"),
            action=_member(entry.get("action"), tax, "RecommendedAction"),
            alternate_queues=tuple(
                _member(q, tax, "Queue") for q in entry.get("alternate_queues", [])
            ),
            alternate_actions=tuple(
                _member(a, tax, "RecommendedAction") for a in entry.get("alternate_actions", [])
            ),
        )
    return table


def _priority(raw: Mapping[str, Any], tax: Taxonomy) -> dict[str, PriorityRule]:
    table: dict[str, PriorityRule] = {}
    for intent, entry in raw.items():
        table[_member(intent, tax, "Intent")] = PriorityRule(
            base=_member(entry.get("base"), tax, "Priority"),
            severe=_member(entry.get("severe"), tax, "Priority"),
            plausible=tuple(_member(p, tax, "Priority") for p in entry.get("plausible", [])),
        )
    return table
