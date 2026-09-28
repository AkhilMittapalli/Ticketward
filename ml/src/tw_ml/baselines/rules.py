"""E1 rules baseline: deterministic keyword, regex and lexicon triage (spec v1.1 §9.7 E1).

The non-LLM floor of the evaluation table. For one ticket it produces a full
``TriageModelOutput``-shaped prediction (the ml copy is ``TriageLabels``):

* **intent**: keyword tables (``ml/configs/rules_baseline.v1.yaml``), error-code votes and the
  policy lexicons (``backend/policy/lexicons/``; forced categories are model OR lexicon); a
  critical intent takes the primary position (guideline R2), plus up to two secondary intents;
* **queue and action**: the §5.8 default of the primary intent (``label_rules.v1.yaml``), then
  the labeling overrides (human request -> ``offer_human_contact``, missing details ->
  ``request_more_information``, guideline R11);
* **priority**: the intent's base or severe level, then the §5.3 floors (rule N3). Floors are on
  by default; ``--no-floors`` emits the pre-floor level that the gold labels use (R4);
* **sentiment and churn**: cue lists for the latest message and the single A-06 churn rule;
* **entities**: literal regexes over the fact-sheet vocabularies (:mod:`tw_ml.baselines.entities`).

Each prediction also carries a *rules preview* of the policy decision: only the forced-review
part of §7.3 (P0 injection lexicon; P1-P5 model OR lexicon, P4 without the incident matcher; P8
for ``other_unclear`` or missing details), the §7.3.2 queue rows and the N3 floors. It lets the
harness report M-07 for E1, i.e. what lexicons and rules alone catch; the P6 engine in the
backend is the real policy. The baseline is deterministic and never reads gold labels.

Run ``python -m tw_ml.baselines.rules --input <jsonl> --out <jsonl>``.
"""

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tw_ml.baselines.entities import EntityExtractor
from tw_ml.baselines.lexicon import (
    LexiconError,
    LexiconScan,
    LexiconSet,
    compile_pattern,
    load_lexicons,
    normalize_for_matching,
)
from tw_ml.datagen.factsheet import FactSheet, load_fact_sheet
from tw_ml.datagen.hardset import TEMPLATE_ID
from tw_ml.datagen.labelrules import PRIORITY_ORDER, LabelRules, load_label_rules
from tw_ml.datagen.paths import RepoPaths, default_paths
from tw_ml.datagen.records import EntityLabel, TicketPayload, TriageLabels
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy
from tw_ml.eval.data import (
    EvalDataError,
    PolicyDecision,
    PolicyOutcome,
    PredictionRecord,
    file_sha256,
    read_jsonl,
)
from tw_ml.eval.holdout import (
    SEALED_SPLITS,
    HoldoutError,
    SealedAccess,
    authorize,
    load_subsets,
    log_sealed_access,
)
from tw_ml.eval.report import git_sha, text_sha256

RULES_CONFIG_FILE: Final = "rules_baseline.v1.yaml"
LABEL_RULES_FILE: Final = "label_rules.v1.yaml"
FACT_SHEET_FILE: Final = "fact_sheet.v1.md"
SYSTEM_NAME: Final = "tw-rules-baseline"
EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
HINT_WEIGHT: Final = 5.0
"""Weight of the ticket's ``product.product_area_hint`` (metadata the customer's form sent)."""
CODE_AREA_WEIGHT: Final = 3.0
STATUS_AREA_WEIGHT: Final = 1.0
REPEATED_CONTACT_PRIOR: Final = 2
"""Prior customer messages in 30 days that, with this one, make >= 3 contacts (§5.5 medium)."""
CONTACT_WINDOW: Final = timedelta(days=30)
P5_INTENTS: Final[frozenset[str]] = frozenset(
    {
        "refund_request",
        "cancellation_request",
        "billing_duplicate_charge",
        "billing_payment_failure",
    }
)
NEGATIVE_SENTIMENTS: Final[frozenset[str]] = frozenset({"frustrated", "angry"})
PRIORITY_RANK: Final[Mapping[str, int]] = {p: rank for rank, p in enumerate(PRIORITY_ORDER)}


class RulesConfigError(ValueError):
    """Raised when the rules configuration is malformed or disagrees with the taxonomy."""


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KeywordSet(_Config):
    """Patterns sharing one weight."""

    weight: float = Field(gt=0)
    patterns: tuple[str, ...] = Field(min_length=1)


class LexiconVote(_Config):
    """A lexicon (or lexicon group) hit votes for an intent."""

    lexicon: str
    group: str | None = None
    intent: str
    weight: float = Field(gt=0)
    secondary: bool = True


class CodeVote(_Config):
    """An error code or HTTP status with this prefix votes for an intent."""

    prefix: str = Field(min_length=1)
    intent: str
    weight: float = Field(gt=0)


class Scoring(_Config):
    """Intent selection thresholds."""

    candidate_min: float = Field(gt=0)
    critical_min: float = Field(gt=0)
    secondary_min: float = Field(gt=0)


class PriorityCues(_Config):
    """Severity cues and the §5.3 floor cues."""

    severe: tuple[str, ...]
    suspension: tuple[str, ...]
    org_wide: tuple[str, ...]
    org_wide_user_count: int = Field(ge=1)


class ChurnCues(_Config):
    """Ultimatum cues of the A-06 churn rule (explicit cancel comes from the lexicon)."""

    ultimatum: tuple[str, ...] = Field(min_length=1)


class SentimentCues(_Config):
    """Latest-message sentiment cues (guideline R5)."""

    angry: tuple[str, ...]
    frustrated: tuple[str, ...]
    confused: tuple[str, ...]
    positive: tuple[str, ...]
    caps_ratio_min: float = Field(gt=0, le=1)
    caps_letters_min: int = Field(ge=1)
    exclamations_min: int = Field(ge=1)


class RulesConfig(_Config):
    """``ml/configs/rules_baseline.v<N>.yaml``."""

    version: str = Field(pattern=r"^rules_baseline\.v[1-9]\d*$")
    taxonomy_version: str
    scoring: Scoring
    precedence: tuple[str, ...]
    lexicon_votes: tuple[LexiconVote, ...]
    code_votes: tuple[CodeVote, ...]
    information_requirements: dict[str, tuple[str, ...]]
    intent_keywords: dict[str, tuple[KeywordSet, ...]]
    product_area_fixed: dict[str, str]
    product_area_default: dict[str, str]
    product_area_keywords: dict[str, tuple[KeywordSet, ...]]
    priority: PriorityCues
    churn: ChurnCues
    sentiment: SentimentCues


def validate_config(config: RulesConfig, taxonomy: Taxonomy, lexicons: LexiconSet) -> None:
    """Check every name in the configuration against the taxonomy and the lexicons.

    Args:
        config: Parsed configuration.
        taxonomy: Taxonomy.
        lexicons: Loaded lexicons.

    Raises:
        RulesConfigError: Listing every problem found.
    """
    intents, areas = set(taxonomy.values("Intent")), set(taxonomy.values("ProductArea"))
    entity_types = set(taxonomy.values("EntityType"))
    twelve = intents - {"other_unclear"}
    problems: list[str] = []
    if config.taxonomy_version != taxonomy.version:
        problems.append(f"taxonomy_version {config.taxonomy_version} != {taxonomy.version}")
    if sorted(config.precedence) != sorted(twelve):
        problems.append("precedence must list each of the 12 intents exactly once")
    for vote in config.lexicon_votes:
        lexicon = lexicons.lexicons.get(vote.lexicon)
        if lexicon is None or (vote.group is not None and vote.group not in lexicon.groups):
            problems.append(f"unknown lexicon vote {vote.lexicon}/{vote.group}")
    named = [v.intent for v in config.lexicon_votes] + [v.intent for v in config.code_votes]
    named += [*config.intent_keywords, *config.information_requirements]
    named += [*config.product_area_fixed, *config.product_area_default]
    problems += [f"unknown intent {i!r}" for i in sorted(set(named) - intents)]
    used_areas = {*config.product_area_fixed.values(), *config.product_area_default.values()}
    used_areas |= set(config.product_area_keywords)
    problems += [f"unknown product area {a!r}" for a in sorted(used_areas - areas)]
    required = {t for types in config.information_requirements.values() for t in types}
    problems += [f"unknown entity type {t!r}" for t in sorted(required - entity_types)]
    if problems:
        raise RulesConfigError("; ".join(problems))


def load_config(path: Path) -> RulesConfig:
    """Read and validate the rules configuration file.

    Args:
        path: ``rules_baseline.v<N>.yaml``.

    Returns:
        The configuration.

    Raises:
        RulesConfigError: If the file is missing or does not match the schema.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return RulesConfig.model_validate(raw)
    except FileNotFoundError:
        msg = f"rules configuration not found: {path.name}"
        raise RulesConfigError(msg) from None
    except ValidationError as exc:
        places = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        msg = f"{path.name}: invalid at {', '.join(places[:5])}"
        raise RulesConfigError(msg) from None


@dataclass(frozen=True, slots=True)
class _Weighted:
    weight: float
    regex: re.Pattern[str]


def _compile_sets(sets: Sequence[KeywordSet]) -> tuple[_Weighted, ...]:
    return tuple(_Weighted(s.weight, compile_pattern(p)[1]) for s in sets for p in s.patterns)


def _compile_list(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(compile_pattern(p)[1] for p in patterns)


def _score(patterns: Sequence[_Weighted], normalized: str) -> float:
    return sum(p.weight for p in patterns if p.regex.search(normalized))


def _count(patterns: Sequence[re.Pattern[str]], normalized: str) -> int:
    return sum(1 for p in patterns if p.search(normalized))


def _raise_one(priority: str) -> str:
    return PRIORITY_ORDER[min(PRIORITY_RANK[priority] + 1, len(PRIORITY_ORDER) - 1)]


@dataclass(frozen=True, slots=True)
class RulesPrediction:
    """The baseline's output for one ticket.

    Attributes:
        output: ``TriageModelOutput``-shaped labels.
        decision: Rules preview of the forced-review part of the policy.
        scan: Lexicon hits (pattern ids, never matched text).
        scores: Intent scores behind the choice.
    """

    output: TriageLabels
    decision: PolicyOutcome
    scan: LexiconScan
    scores: Mapping[str, float]


class RulesBaseline:
    """The E1 system (deterministic; it never reads gold labels).

    Args:
        config: Validated rules configuration.
        lexicons: Policy lexicons.
        rules: Label rules (routing, priority bases, churn cues).
        facts: Fact sheet (entity vocabularies, error-code areas).
        taxonomy: Taxonomy.
        apply_floors: Apply the §5.3 floors to the output priority (default, as the E1 system).
        digest: Content digest of the inputs (the loader hashes the files); derived when empty.
    """

    def __init__(
        self,
        config: RulesConfig,
        lexicons: LexiconSet,
        rules: LabelRules,
        facts: FactSheet,
        taxonomy: Taxonomy,
        *,
        apply_floors: bool = True,
        digest: str = "",
    ) -> None:
        validate_config(config, taxonomy, lexicons)
        self.config, self.lexicons, self.rules = config, lexicons, rules
        self.taxonomy, self.apply_floors = taxonomy, apply_floors
        self._keywords = {i: _compile_sets(s) for i, s in config.intent_keywords.items()}
        self._areas = {a: _compile_sets(s) for a, s in config.product_area_keywords.items()}
        self._severe = _compile_list(config.priority.severe)
        self._suspension = _compile_list(config.priority.suspension)
        self._org_wide = _compile_list(config.priority.org_wide)
        self._ultimatum = _compile_list(config.churn.ultimatum)
        cues = config.sentiment
        self._sentiments = {
            name: _compile_list(getattr(cues, name))
            for name in ("angry", "frustrated", "confused", "positive")
        }
        self._extractor = EntityExtractor.from_facts(facts)
        self._code_areas = {c.code: (c.product_area, CODE_AREA_WEIGHT) for c in facts.error_codes}
        self._code_areas |= {
            s.code: (s.product_area, STATUS_AREA_WEIGHT) for s in facts.http_statuses
        }
        self._area_order = {a: rank for rank, a in enumerate(taxonomy.values("ProductArea"))}
        self._order = {intent: rank for rank, intent in enumerate(config.precedence)}
        if not digest:
            payload = "\n".join(
                (config.model_dump_json(), lexicons.digest(), rules.version, facts.prompt_text)
            )
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        suffix = "" if apply_floors else "-prefloor"
        self.system_id = f"{SYSTEM_NAME}@{config.version}+{digest[:12]}{suffix}"

    # ------------------------------------------------------------------ intent
    def intent_scores(
        self, normalized: str, scan: LexiconScan, codes: Sequence[str]
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Score every intent from keywords, lexicon votes and code votes.

        Args:
            normalized: Normalized customer text.
            scan: Lexicon hits.
            codes: Error codes and HTTP statuses found in the ticket.

        Returns:
            ``(total, secondary)``: total scores choose the primary; secondary scores exclude
            votes marked ``secondary: false``.
        """
        total = {intent: _score(p, normalized) for intent, p in self._keywords.items()}
        secondary = dict(total)
        for vote in self.config.lexicon_votes:
            if scan.fired(vote.lexicon, vote.group):
                total[vote.intent] = total.get(vote.intent, 0.0) + vote.weight
                if vote.secondary:
                    secondary[vote.intent] = secondary.get(vote.intent, 0.0) + vote.weight
        for code in dict.fromkeys(codes):
            for code_vote in self.config.code_votes:
                if code.startswith(code_vote.prefix):
                    total[code_vote.intent] = total.get(code_vote.intent, 0.0) + code_vote.weight
                    secondary[code_vote.intent] = (
                        secondary.get(code_vote.intent, 0.0) + code_vote.weight
                    )
        return total, secondary

    def choose(
        self, total: Mapping[str, float], secondary: Mapping[str, float]
    ) -> tuple[str, tuple[str, ...]]:
        """Pick the primary and up to two secondary intents.

        Args:
            total: Total scores.
            secondary: Secondary-eligible scores.

        Returns:
            ``(primary, secondaries)``; ``other_unclear`` when no intent reaches the minimum.
        """
        scoring = self.config.scoring

        def rank(intent: str) -> tuple[float, int]:
            return -total.get(intent, 0.0), self._order[intent]

        critical = [
            i
            for i in self.config.precedence
            if self.rules.is_critical(i) and total.get(i, 0.0) >= scoring.critical_min
        ]
        candidates = [
            i for i in self.config.precedence if total.get(i, 0.0) >= scoring.candidate_min
        ]
        if not critical and not candidates:
            return "other_unclear", ()
        primary = min(critical or candidates, key=rank)
        extra = sorted(
            (
                i
                for i in self.config.precedence
                if i != primary and secondary.get(i, 0.0) >= scoring.secondary_min
            ),
            key=lambda i: (-secondary.get(i, 0.0), self._order[i]),
        )
        return primary, tuple(extra[:2])

    # ------------------------------------------------------------------ priority
    def floor_priority(
        self,
        priority: str,
        intents: Sequence[str],
        *,
        plan: str,
        sentiment: str,
        normalized: str,
        entities: Sequence[EntityLabel],
    ) -> str:
        """Apply the §5.3 floors (rule N3): priorities only ever rise.

        Args:
            priority: Pre-floor priority.
            intents: Primary and secondary intents.
            plan: Customer plan tier.
            sentiment: Predicted sentiment.
            normalized: Normalized customer text.
            entities: Extracted entities (``user_count_affected``).

        Returns:
            The floored priority.
        """
        candidates = [priority]
        if "security_report" in intents:
            candidates.append("high")
        if "service_outage" in intents:
            candidates.append("urgent")
        if "billing_payment_failure" in intents and _count(self._suspension, normalized):
            candidates.append("high")
        counts = [int(e.value) for e in entities if e.type == "user_count_affected"]
        org_wide = bool(_count(self._org_wide, normalized)) or any(
            c >= self.config.priority.org_wide_user_count for c in counts
        )
        if "sso_login_failure" in intents and plan == "enterprise" and org_wide:
            candidates.append("urgent")
        if plan == "enterprise" and sentiment in NEGATIVE_SENTIMENTS:
            candidates.append(_raise_one(priority))
        return max(candidates, key=lambda p: PRIORITY_RANK[p])

    # ------------------------------------------------------------------ sentiment, churn
    def sentiment(self, latest: str) -> str:
        """Sentiment of the latest customer message (guideline R5).

        Args:
            latest: Subject and latest message, original case.

        Returns:
            A Sentiment value; capitals alone mark urgency, not anger.
        """
        cues, normalized = self.config.sentiment, normalize_for_matching(latest)
        hits = {name: _count(p, normalized) for name, p in self._sentiments.items()}
        letters = [c for c in latest if c.isalpha()]
        shouting = len(letters) >= cues.caps_letters_min and (
            sum(c.isupper() for c in letters) / len(letters) >= cues.caps_ratio_min
        )
        loud = latest.count("!") >= cues.exclamations_min
        if hits["angry"] >= 2 or (hits["angry"] and (shouting or loud)):  # noqa: PLR2004
            return "angry"
        if hits["angry"] or hits["frustrated"] or (shouting and loud):
            return "frustrated"
        if hits["confused"]:
            return "confused"
        return "positive" if hits["positive"] else "neutral"

    def churn(
        self,
        normalized: str,
        ticket: TicketPayload,
        *,
        scan: LexiconScan,
        competitor: str | None,
        sentiment: str,
        intents: Sequence[str],
    ) -> tuple[str, tuple[str, ...]]:
        """The single churn rule (§5.5, A-06) with paraphrased cue signals.

        Args:
            normalized: Normalized customer text.
            ticket: Ticket (plan, history).
            scan: Lexicon hits.
            competitor: Named product the customer moves to, if any.
            sentiment: Predicted sentiment.
            intents: Primary and secondary intents.

        Returns:
            ``(churn_risk, churn_signals)``; signals are paraphrases, never ticket text.
        """
        explicit = bool(
            scan.groups("cancellation") & {"cancel_contract", "non_renewal", "downgrade_to_free"}
        )
        moving = scan.fired("cancellation", "competitor_move") or competitor is not None
        ultimatum = bool(_count(self._ultimatum, normalized))
        vague = any(p.search(normalized) for p in self.rules.vague_cues)
        repeated = any(p.search(normalized) for p in self.rules.repeated_contact_cues)
        repeated = repeated or _recent_contacts(ticket) >= REPEATED_CONTACT_PRIOR
        flags = (
            ("explicit_cancel", explicit, "explicit cancellation or non-renewal language"),
            ("competitor", moving, "says they are moving to another product"),
            ("ultimatum", ultimatum, "ultimatum or threat to leave"),
            ("vague_alternatives", vague, "considering alternatives"),
            ("repeated_contact", repeated, "repeated contact about the issue"),
        )
        cue = next((name for name, on, _ in flags if on), "none")
        risk = self.rules.derive_churn(
            cue, sentiment=sentiment, plan=ticket.customer_tier, intents=intents
        )
        if risk == "low":
            return risk, ()
        signals = [text for _, on, text in flags if on]
        if not signals and sentiment in NEGATIVE_SENTIMENTS:
            signals.append(f"{sentiment} customer on the {ticket.customer_tier} plan")
        return risk, tuple(signals[:5])

    # ------------------------------------------------------------------ area, sufficiency
    def product_area(
        self, intent: str, normalized: str, ticket: TicketPayload, entities: Sequence[EntityLabel]
    ) -> str:
        """Where the primary need lives (guideline R12).

        Args:
            intent: Primary intent.
            normalized: Normalized customer text.
            ticket: Ticket (``product_area_hint`` metadata).
            entities: Extracted entities (error-code areas from the fact sheet).

        Returns:
            A ProductArea value.
        """
        fixed = self.config.product_area_fixed.get(intent)
        if fixed is not None:
            return fixed
        scores = {area: _score(p, normalized) for area, p in self._areas.items()}
        hint = ticket.product.product_area_hint if ticket.product is not None else None
        if hint is not None:
            scores[hint] = scores.get(hint, 0.0) + HINT_WEIGHT
        for entity in entities:
            area_weight = self._code_areas.get(entity.value)
            if entity.type in {"error_code", "http_status"} and area_weight is not None:
                scores[area_weight[0]] = scores.get(area_weight[0], 0.0) + area_weight[1]
        best = min(scores, key=lambda a: (-scores[a], self._area_order[a]), default=None)
        if best is not None and scores[best] > 0:
            return best
        return self.config.product_area_default.get(intent, "projects_tasks")

    def information_sufficient(self, intent: str, entities: Sequence[EntityLabel]) -> bool:
        """Guideline R10: can support take the first action?

        Args:
            intent: Primary intent.
            entities: Extracted entities.

        Returns:
            False for ``other_unclear`` or when no required detail is present.
        """
        if intent == "other_unclear":
            return False
        required = self.config.information_requirements.get(intent)
        return required is None or any(e.type in required for e in entities)

    # ------------------------------------------------------------------ prediction
    def predict(self, ticket: TicketPayload) -> RulesPrediction:
        """Triage one ticket.

        Args:
            ticket: Masked ticket (no labels are ever passed in).

        Returns:
            The prediction with its policy preview.
        """
        customer, full = ticket.customer_text(), ticket.full_text()
        normalized = normalize_for_matching(customer)
        scan = self.lexicons.scan(customer)
        total, secondary = self.intent_scores(normalized, scan, self._extractor.codes(full))
        primary, secondaries = self.choose(total, secondary)
        intents = (primary, *secondaries)
        sso_context = total.get("sso_login_failure", 0.0) > 0
        entities = self._extractor.extract(full, intent=primary, sso_context=sso_context)
        human = scan.fired("human_request")
        sufficient = self.information_sufficient(primary, entities)
        sentiment = self.sentiment(f"{ticket.subject}\n{ticket.message}")
        pre_floor = self.rules.derive_priority(
            primary, severe=bool(_count(self._severe, normalized))
        )
        floored = self.floor_priority(
            pre_floor,
            intents,
            plan=ticket.customer_tier,
            sentiment=sentiment,
            normalized=normalized,
            entities=entities,
        )
        competitor = next((e.value for e in entities if e.type == "competitor_name"), None)
        churn, signals = self.churn(
            normalized,
            ticket,
            scan=scan,
            competitor=competitor,
            sentiment=sentiment,
            intents=intents,
        )
        output = TriageLabels(
            intent=primary,
            secondary_intents=secondaries,
            priority=floored if self.apply_floors else pre_floor,
            sentiment=sentiment,
            churn_risk=churn,
            churn_signals=signals,
            product_area=self.product_area(primary, normalized, ticket, entities),
            entities=entities,
            recommended_queue=self.rules.routing[primary].queue,
            recommended_action=self.rules.expected_action(
                primary, customer_requested_human=human, information_sufficient=sufficient
            ),
            customer_requested_human=human,
            information_sufficient=sufficient,
            rationale=self._rationale(primary, total, scan),
        )
        decision = forced_review_preview(output, scan, final_priority=floored, rules=self.rules)
        return RulesPrediction(output, decision, scan, total)

    def prediction_record(self, record_id: str, ticket: TicketPayload) -> PredictionRecord:
        """Predict and wrap the result as a ``prediction.v1`` record.

        Args:
            record_id: Record id.
            ticket: Ticket.

        Returns:
            The record (always ``first_pass``: the rules emit schema-valid output).
        """
        prediction = self.predict(ticket)
        return PredictionRecord(
            record_id=record_id,
            system_id=self.system_id,
            validity="first_pass",
            output=prediction.output,
            decision=prediction.decision,
        )

    def _rationale(self, intent: str, total: Mapping[str, float], scan: LexiconScan) -> str:
        head = f"E1 {self.config.version}: "
        if intent == "other_unclear":
            head += "no intent reached the keyword minimum"
        else:
            head += f"{intent} from rules (score {total.get(intent, 0.0):.1f})"
        fired = scan.lexicons()
        tail = f"; lexicons: {', '.join(fired)}" if fired else ""
        return (head + tail)[:400]


def _recent_contacts(ticket: TicketPayload) -> int:
    """Customer-authored prior messages within 30 days before the ticket."""
    received = ticket.received_at
    prior = [m for m in ticket.previous_messages if m.author == "customer"]
    if received is None:
        return len(prior)
    return sum(1 for m in prior if received - CONTACT_WINDOW <= m.sent_at <= received)


def forced_review_preview(
    output: TriageLabels, scan: LexiconScan, *, final_priority: str, rules: LabelRules
) -> PolicyOutcome:
    """Rules preview of the forced-review part of the policy table (§7.3, §7.3.2).

    Covers P0 (injection lexicon, non-terminal), P1 (human request), P2 (security), P3
    (privacy / legal threat), P4 (``service_outage`` intent; no incident matcher), P5 (refund,
    cancellation, payment dispute), each as rules intent OR lexicon, and P8 (``other_unclear`` or
    missing details). Reasons follow rule order; the path comes from the highest terminal rule.

    Args:
        output: The baseline's triage output.
        scan: Lexicon hits.
        final_priority: Priority after the N3 floors.
        rules: Label rules (default routing).

    Returns:
        The preview decision (``source="rules_preview"``).
    """
    intents = {output.intent, *output.secondary_intents}
    refund = "refund_request" in intents or scan.fired("refund")
    cancel = "cancellation_request" in intents or scan.fired("cancellation")
    dispute = bool(intents & {"billing_duplicate_charge", "billing_payment_failure"})
    dispute = dispute or scan.fired("billing_dispute")
    privacy = "privacy_legal_request" in intents or scan.fired("legal", "privacy")
    fired = {
        "P1": output.customer_requested_human or scan.fired("human_request"),
        "P2": "security_report" in intents or scan.fired("security"),
        "P3": privacy or scan.fired("legal", "threat"),
        "P4": "service_outage" in intents,
        "P5": refund or cancel or dispute,
    }
    reasons = [
        reason
        for reason, on in (
            ("prompt_injection_suspected", scan.fired("injection")),
            ("customer_requested_human", fired["P1"]),
            ("forced_category_security", fired["P2"]),
            ("forced_category_privacy", privacy),
            ("forced_category_legal_threat", scan.fired("legal", "threat")),
            ("active_incident", fired["P4"]),
            ("forced_category_refund", refund),
            ("forced_category_cancellation", cancel),
            ("forced_category_payment_dispute", dispute),
        )
        if on
    ]
    abstain = output.intent == "other_unclear" or not output.information_sufficient
    path: PolicyDecision
    if any(fired.values()):
        path = "human_escalation"
    elif abstain:
        path = "abstain_request_info"
    else:
        path = "local_draft"
    if fired["P2"] or (fired["P3"] and "privacy_legal_request" in intents):
        queue = "security_and_privacy"
    elif fired["P4"]:
        queue = "incident_response"
    elif fired["P5"] and output.intent not in P5_INTENTS:
        queue = "billing_and_accounts" if refund or dispute else "customer_success_retention"
    else:
        queue = rules.routing[output.intent].queue
    return PolicyOutcome(
        policy_decision=path,
        needs_human_review=path == "human_escalation" or abstain,
        escalation_reasons=tuple(reasons),
        final_queue=queue,
        final_priority=final_priority,
        source="rules_preview",
    )


# --------------------------------------------------------------------------- loading


def load_rules_baseline(
    paths: RepoPaths | None = None, *, apply_floors: bool = True, config_path: Path | None = None
) -> RulesBaseline:
    """Load the E1 baseline from the repository's data files.

    The system id hashes the rules configuration, the label rules, the fact sheet and every
    lexicon (LF-normalized), so a published E1 number names the exact rules behind it.

    Args:
        paths: Repository paths.
        apply_floors: Apply the §5.3 floors to the output priority.
        config_path: Configuration override (defaults to ``ml/configs/rules_baseline.v1.yaml``).

    Returns:
        The baseline.
    """
    paths = paths or default_paths()
    taxonomy = load_taxonomy(paths.schemas_dir)
    label_rules_file = paths.spec_dir / LABEL_RULES_FILE
    fact_sheet_file = paths.spec_dir / FACT_SHEET_FILE
    source = config_path or paths.configs_dir / RULES_CONFIG_FILE
    lexicons = load_lexicons(paths.lexicons_dir)
    parts = [text_sha256(p) for p in (source, label_rules_file, fact_sheet_file)]
    digest = hashlib.sha256("\n".join((*parts, lexicons.digest())).encode("utf-8")).hexdigest()
    return RulesBaseline(
        load_config(source),
        lexicons,
        load_label_rules(label_rules_file, taxonomy),
        load_fact_sheet(fact_sheet_file, taxonomy),
        taxonomy,
        apply_floors=apply_floors,
        digest=digest,
    )


def read_tickets(path: Path) -> list[tuple[str, str | None, TicketPayload]]:
    """Read tickets from any P1 row format (only the ``ticket`` part is used, never labels).

    Args:
        path: JSONL file (``DatasetRecord``, hard-set, OOD or ``{record_id, ticket}`` rows).

    Returns:
        ``(record_id, provenance_split, ticket)`` per row; the hard-set template is skipped.

    Raises:
        EvalDataError: If a row lacks an id or a valid ticket, or an id repeats.
    """
    tickets: list[tuple[str, str | None, TicketPayload]] = []
    for number, row in read_jsonl(path):
        raw = row.get("provenance")
        provenance: dict[str, Any] = raw if isinstance(raw, dict) else {}
        record_id = provenance.get("record_id", row.get("record_id"))
        if not isinstance(record_id, str) or not record_id:
            msg = f"{path.name} line {number}: row has no record_id"
            raise EvalDataError(msg)
        if record_id == TEMPLATE_ID and not provenance:
            continue
        try:
            ticket = TicketPayload.model_validate(row.get("ticket"))
        except ValidationError:
            msg = f"{path.name} line {number}: missing or invalid ticket"
            raise EvalDataError(msg) from None
        split = provenance.get("split")
        tickets.append((record_id, split if isinstance(split, str) else None, ticket))
    ids = [record_id for record_id, _, _ in tickets]
    if len(set(ids)) != len(ids):
        msg = f"{path.name}: duplicate record ids"
        raise EvalDataError(msg)
    return tickets


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tw_ml.baselines.rules",
        description="E1 rules baseline: write prediction.v1 JSONL for a ticket file.",
    )
    parser.add_argument("--input", required=True, help="JSONL with a ticket per row")
    parser.add_argument("--out", required=True, help="prediction JSONL to write")
    parser.add_argument("--no-floors", action="store_true", help="emit pre-floor priorities")
    parser.add_argument("--phase", default="P2", help="current project phase (P0..P11)")
    parser.add_argument(
        "--i-understand-sealed",
        action="store_true",
        help="with --phase P10 only: allow tickets from sealed splits (logged)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    paths: RepoPaths | None = None,
    now: datetime | None = None,
) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).
        paths: Repository paths override (tests).
        now: Clock override (tests).

    Returns:
        Exit code: 0 success, 2 usage, data, configuration or holdout error.
    """
    args = build_parser().parse_args(argv)
    paths = paths or default_paths()
    source = Path(args.input)
    try:
        tickets = read_tickets(source)
        decision = authorize(
            None,
            [(record_id, split) for record_id, split, _ in tickets],
            phase=args.phase,
            i_understand_sealed=args.i_understand_sealed,
            subsets=load_subsets(paths),
        )
        baseline = load_rules_baseline(paths, apply_floors=not args.no_floors)
    except (EvalDataError, HoldoutError, LexiconError, RulesConfigError) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return EXIT_USAGE
    if decision.sealed:
        sealed = sorted(k for k in decision.origins if k in SEALED_SPLITS)
        log_sealed_access(
            paths.sealed_access_log,
            SealedAccess(
                at=now or datetime.now(UTC),
                action="predict",
                split=",".join(sealed),
                system_id=baseline.system_id,
                experiment="E1",
                phase=decision.phase,
                gold_sha256=file_sha256(source),
                predictions_sha256=(),
                git_sha=git_sha(paths.root),
                n_records=len(tickets),
            ),
        )
    records = [baseline.prediction_record(record_id, ticket) for record_id, _, ticket in tickets]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8", newline="\n"
    )
    summary = {
        "system_id": baseline.system_id,
        "records": len(records),
        "out": out.as_posix(),
        "lexicon_versions": baseline.lexicons.versions(),
        "sealed": decision.sealed,
    }
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
