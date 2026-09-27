"""Schema validation plus the deterministic label rule-checker (spec v1.1 §9.1 step 6, R1-R10).

Every finding is structured (rule id, severity, field, content-free detail). ``error`` findings
reject a generated record (it is regenerated, then quarantined); ``warning`` findings are
counted in the quality report. The checks, grouped:

* labels (every source): R2 queue default/alternate, R3 action valid for the intent and the
  human-request / missing-information rules, R4 entities literally present (``saml_idp`` by its
  aliases) and never raw PII, R5 the single churn rule (A-06), R6 human-request lexicon
  agreement, R7 ``other_unclear`` implies insufficient information, R8 secondary intents (at
  most 2, unique, never the primary, never ``other_unclear``) and critical-first, R9 priority
  plausibility;
* text: R10 no raw PII, secrets, URLs or malformed placeholders; meta-text leaks; greetings;
* fact sheet: SSO/SCIM/seat/billing plausibility per plan, unknown codes, features and
  integrations;
* card (generated records): R1 intent matches the card, secondaries, human request,
  information sufficiency, product area, churn, card values present, banned words absent,
  injection and placeholders present, history and length;
* dataset (file level): provenance per split (T-DATA-provenance), exact duplicates, soft-gate
  metrics (greeting rate, critical keyword share).
"""

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, Literal

from pydantic import ValidationError

from tw_ml.datagen.factsheet import FactSheet
from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.pii import ERROR_KINDS, find_pii
from tw_ml.datagen.records import (
    ALLOWED_FAMILIES,
    DatasetRecord,
    EntityLabel,
    GenerationCell,
    TicketPayload,
    TriageLabels,
    provenance_violations,
)

Severity = Literal["error", "warning"]
LENGTH_WARN_TOLERANCE: Final = 0.3  # ERPROT A10: accept +/-30% of the target words
LENGTH_ERROR_TOLERANCE: Final = 0.6
LENGTH_WARN_SLACK_WORDS: Final = 8  # short targets get an absolute slack as well
LENGTH_ERROR_SLACK_WORDS: Final = 15
GREETING_RE: Final = re.compile(
    r"(?im)^\s*(?:hi|hello|hey|dear|greetings|good (?:morning|afternoon|evening))\b"
    r"|\bhope (?:this|you) (?:finds|are|is)\b"
    r"|^\s*(?:best regards|kind regards|regards|sincerely|cheers|thanks in advance),?\s*$"
)
META_LEAK_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)\bas an ai\b"),
    re.compile(r"(?i)\bhere(?: is|'s) (?:the|your|a|my) (?:ticket|message|email|json)\b"),
    re.compile(r"```"),
    re.compile(r"(?i)\blorem ipsum\b"),
    re.compile(r"(?i)[\[(]insert [^\])]{1,40}[\])]"),
    re.compile(r"(?i)\bproposed_labels\b|\bself_check\b"),
)
SCIM_RE: Final = re.compile(r"\bSCIM\b", re.IGNORECASE)
CHAT_MIN_HISTORY: Final = 2


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule-checker result.

    Attributes:
        rule: Rule id (e.g. ``R4_entity_not_in_text``).
        severity: ``error`` rejects the record, ``warning`` is reported.
        field: Record field concerned.
        detail: Short, content-free explanation (never ticket text).
    """

    rule: str
    severity: Severity
    field: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        """Plain-dict form for JSON reports.

        Returns:
            The finding as a dictionary.
        """
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationContext:
    """Inputs of the rule-checker.

    Attributes:
        rules: Label rules.
        facts: Fact sheet.
        known_names: Fictional names that must appear only masked (persona names).
    """

    rules: LabelRules
    facts: FactSheet
    known_names: tuple[str, ...] = ()


def has_errors(findings: Iterable[Finding]) -> bool:
    """Return whether any finding is an error.

    Args:
        findings: Findings.

    Returns:
        True when at least one error is present.
    """
    return any(f.severity == "error" for f in findings)


def entity_present(entity: EntityLabel, text: str, facts: FactSheet) -> bool:
    """Whether an entity value literally appears in the text (spec §9.2; A-29 spans).

    ``saml_idp`` values are normalized (``okta``), so any documented alias counts.

    Args:
        entity: Label entity.
        text: Ticket text (subject, message and prior messages).
        facts: Fact sheet (IdP aliases).

    Returns:
        True when present.
    """
    if not entity.value:
        return False
    if entity.type == "saml_idp":
        provider = facts.idp(entity.value)
        aliases = provider.aliases if provider else ()
        return any(re.search(rf"\b{re.escape(a)}\b", text, re.IGNORECASE) for a in aliases)
    return entity.value in text


# --------------------------------------------------------------------------- labels


def validate_labels(
    labels: TriageLabels, ticket: TicketPayload, ctx: ValidationContext
) -> list[Finding]:
    """Rules R2-R9 and the fact-sheet checks for one labelled ticket.

    Args:
        labels: Labels to check.
        ticket: The ticket they describe.
        ctx: Validation context.

    Returns:
        Findings (possibly empty).
    """
    text = ticket.full_text()
    findings = [
        *_routing(labels, ctx.rules),
        *_entities(labels, text, ctx.facts),
        *_churn(labels, ticket, text, ctx.rules),
        *_human_lexicon(labels, text, ctx.rules),
        *_secondaries(labels, ctx.rules),
        *_plausibility(labels, ticket, text, ctx),
    ]
    if labels.intent == "other_unclear" and labels.information_sufficient:
        findings.append(Finding("R7_other_unclear_information", "error", "information_sufficient"))
    if labels.priority not in ctx.rules.priority[labels.intent].plausible:
        findings.append(Finding("R9_priority_implausible", "warning", "priority", labels.priority))
    return findings


def _routing(labels: TriageLabels, rules: LabelRules) -> list[Finding]:
    findings: list[Finding] = []
    if labels.recommended_queue not in rules.allowed_queues(labels.intent):
        findings.append(
            Finding("R2_queue_not_allowed", "error", "recommended_queue", labels.recommended_queue)
        )
    allowed = rules.allowed_actions(
        labels.intent,
        customer_requested_human=labels.customer_requested_human,
        information_sufficient=labels.information_sufficient,
    )
    if labels.recommended_action not in allowed:
        findings.append(
            Finding(
                "R3_action_not_allowed", "error", "recommended_action", labels.recommended_action
            )
        )
    return findings


def _entities(labels: TriageLabels, text: str, facts: FactSheet) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for index, entity in enumerate(labels.entities):
        where = f"entities[{index}]"
        if not entity.value.strip():
            findings.append(Finding("R4_entity_empty", "error", where, entity.type))
            continue
        if (entity.type, entity.value) in seen:
            findings.append(Finding("R4_entity_duplicate", "warning", where, entity.type))
        seen.add((entity.type, entity.value))
        if entity.type == "saml_idp" and facts.idp(entity.value) is None:
            findings.append(
                Finding("R4_saml_idp_value", "error", where, "not a normalized saml_idp value")
            )
        elif not entity_present(entity, text, facts):
            findings.append(Finding("R4_entity_not_in_text", "error", where, entity.type))
        if any(hit.kind in ERROR_KINDS for hit in find_pii(entity.value)):
            findings.append(Finding("R4_entity_raw_pii", "error", where, entity.type))
    return findings


def _churn(
    labels: TriageLabels, ticket: TicketPayload, text: str, rules: LabelRules
) -> list[Finding]:
    intents = {labels.intent, *labels.secondary_intents}
    competitors = [e.value for e in labels.entities if e.type == "competitor_name"]
    high_cue = rules.has_high_cue(text, competitors)
    medium_cue = rules.has_medium_cue(text)
    negative_paid = (
        labels.sentiment in rules.negative_sentiments and ticket.customer_tier in rules.medium_plans
    )
    findings: list[Finding] = []
    if "cancellation_request" in intents and labels.churn_risk != "high":
        findings.append(Finding("R5_churn_cancellation_not_high", "error", "churn_risk"))
    if labels.churn_risk == "high":
        if "cancellation_request" not in intents and not high_cue:
            findings.append(Finding("R5_churn_high_without_cue", "error", "churn_risk"))
        if not labels.churn_signals:
            findings.append(Finding("R5_churn_signals_missing", "error", "churn_signals"))
    if labels.churn_risk == "low" and negative_paid:
        findings.append(Finding("R5_churn_negative_paid_low", "error", "churn_risk"))
    if labels.churn_risk == "low" and (high_cue or medium_cue):
        findings.append(Finding("R5_churn_low_with_cue", "warning", "churn_risk"))
    if labels.churn_risk == "medium" and not (medium_cue or negative_paid or high_cue):
        findings.append(Finding("R5_churn_medium_without_basis", "warning", "churn_risk"))
    return findings


def _human_lexicon(labels: TriageLabels, text: str, rules: LabelRules) -> list[Finding]:
    kind = rules.human_request_kind(text)
    if labels.customer_requested_human == (kind != "none"):
        return []
    detail = f"lexicon={kind}"
    return [Finding("R6_human_request_lexicon", "warning", "customer_requested_human", detail)]


def _secondaries(labels: TriageLabels, rules: LabelRules) -> list[Finding]:
    secondary = labels.secondary_intents
    findings: list[Finding] = []
    if len(set(secondary)) != len(secondary):
        findings.append(Finding("R8_secondary_duplicate", "error", "secondary_intents"))
    if labels.intent in secondary:
        findings.append(Finding("R8_secondary_is_primary", "error", "secondary_intents"))
    if "other_unclear" in secondary:
        findings.append(Finding("R8_secondary_other_unclear", "error", "secondary_intents"))
    if labels.intent == "other_unclear" and secondary:
        findings.append(Finding("R8_unclear_with_secondary", "error", "secondary_intents"))
    if not rules.is_critical(labels.intent) and any(rules.is_critical(s) for s in secondary):
        findings.append(
            Finding("R8_critical_not_primary", "error", "intent", "critical-first rule")
        )
    return findings


def _plausibility(
    labels: TriageLabels, ticket: TicketPayload, text: str, ctx: ValidationContext
) -> list[Finding]:
    facts, rules = ctx.facts, ctx.rules
    plan = facts.plans[ticket.customer_tier]
    intents = {labels.intent, *labels.secondary_intents}
    findings: list[Finding] = []
    if "sso_login_failure" in intents and not plan.sso:
        findings.append(
            Finding("F_sso_plan", "error", "customer_tier", "SSO needs business/enterprise")
        )
    if SCIM_RE.search(text) and not plan.scim and labels.intent != "plan_pricing_inquiry":
        findings.append(
            Finding("F_scim_plan", "warning", "customer_tier", "SCIM is enterprise-only")
        )
    if intents & (rules.billing_intents | {"cancellation_request"}) and plan.price_per_seat == 0:
        findings.append(
            Finding("F_billing_free_plan", "error", "customer_tier", "free plan is never charged")
        )
    seats = ticket.account.seats if ticket.account else None
    if seats is not None and plan.seats_max is not None and seats > plan.seats_max:
        findings.append(Finding("F_seats_exceed_plan", "error", "account.seats"))
    known = {
        "error_code": {c.code for c in facts.error_codes},
        "http_status": {c.code for c in facts.http_statuses},
        "integration_name": {i.name for i in facts.integrations},
        "feature_name": {f.name for f in facts.features},
    }
    for index, entity in enumerate(labels.entities):
        values = known.get(entity.type)
        if values is not None and entity.value not in values:
            findings.append(Finding(f"F_unknown_{entity.type}", "warning", f"entities[{index}]"))
    return findings


# --------------------------------------------------------------------------- text


def validate_text(
    ticket: TicketPayload, labels: TriageLabels, ctx: ValidationContext
) -> list[Finding]:
    """R10 PII, secret and placeholder scan plus meta-text leaks.

    Args:
        ticket: Ticket.
        labels: Labels (free-text fields are scanned too).
        ctx: Validation context.

    Returns:
        Findings.
    """
    findings: list[Finding] = []
    fields = {
        "subject": ticket.subject,
        "message": ticket.message,
        **{f"previous_messages[{i}]": m.body for i, m in enumerate(ticket.previous_messages)},
        "rationale": labels.rationale,
        **{f"churn_signals[{i}]": s for i, s in enumerate(labels.churn_signals)},
    }
    for name, value in fields.items():
        for hit in find_pii(value, ctx.known_names):
            severity: Severity = "error" if hit.kind in ERROR_KINDS else "warning"
            findings.append(Finding(f"R10_pii_{hit.kind}", severity, name))
    for name in ("subject", "message"):
        if any(p.search(fields[name]) for p in META_LEAK_RES):
            findings.append(Finding("A5_meta_leak", "error", name))
    return findings


# --------------------------------------------------------------------------- card


def validate_card(record: DatasetRecord, ctx: ValidationContext) -> list[Finding]:
    """R1 and the other card checks for generated records (no-op without a cell).

    Args:
        record: Generated record.
        ctx: Validation context.

    Returns:
        Findings.
    """
    cell = record.cell
    if cell is None:
        return []
    labels, ticket = record.labels, record.ticket
    findings = _card_labels(cell, labels, ticket, ctx.rules)
    findings.extend(_card_text(cell, ticket, ctx.facts))
    if record.self_check is not None and not record.self_check.card_satisfied:
        findings.append(Finding("self_check_failed", "warning", "self_check"))
    return findings


def _card_labels(
    cell: GenerationCell, labels: TriageLabels, ticket: TicketPayload, rules: LabelRules
) -> list[Finding]:
    findings: list[Finding] = []
    checks = (
        ("R1_intent_mismatch_card", "intent", labels.intent == cell.intent),
        (
            "R1_secondary_mismatch_card",
            "secondary_intents",
            set(labels.secondary_intents) == set(cell.secondary_intents),
        ),
        (
            "R6_human_request_mismatch_card",
            "customer_requested_human",
            labels.customer_requested_human == (cell.human_request != "none"),
        ),
        (
            "R7_information_mismatch_card",
            "information_sufficient",
            labels.information_sufficient == cell.information_sufficient,
        ),
        ("R1_product_area_mismatch_card", "product_area", labels.product_area == cell.product_area),
        (
            "R5_churn_mismatch_card",
            "churn_risk",
            labels.churn_risk
            == rules.derive_churn(
                cell.churn_cue,
                sentiment=labels.sentiment,
                plan=ticket.customer_tier,
                intents=(cell.intent, *cell.secondary_intents),
            ),
        ),
    )
    findings.extend(Finding(rule, "error", name) for rule, name, ok in checks if not ok)
    if labels.sentiment != cell.sentiment:
        findings.append(Finding("sentiment_mismatch_card", "warning", "sentiment"))
    if cell.difficulty == "multi_intent" and not labels.secondary_intents:
        findings.append(Finding("R8_multi_intent_without_secondary", "error", "secondary_intents"))
    return findings


def _card_text(cell: GenerationCell, ticket: TicketPayload, facts: FactSheet) -> list[Finding]:
    text = ticket.full_text()
    customer = f"{ticket.subject}\n{ticket.message}"
    findings: list[Finding] = []
    for entity, display in zip(cell.entities, cell.display_values, strict=True):
        probe = EntityLabel(
            type=entity.type, value=entity.value if entity.type == "saml_idp" else display
        )
        if not entity_present(probe, text, facts):
            findings.append(Finding("card_value_missing", "error", "message", entity.type))
    for word in cell.banned_words:
        if re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", customer, re.IGNORECASE):
            findings.append(Finding("card_banned_word", "error", "message"))
    if cell.injection and cell.injection not in text:
        findings.append(Finding("card_injection_missing", "error", "message"))
    for placeholder in cell.pii_placeholders:
        if placeholder not in text:
            findings.append(Finding("card_placeholder_missing", "error", "message", placeholder))
    history = len(ticket.previous_messages)
    chat_short = cell.channel == "chat_transcript" and history < CHAT_MIN_HISTORY
    if chat_short or (cell.history_len and not history):
        findings.append(Finding("card_history_missing", "error", "previous_messages"))
    words = len(ticket.message.split())
    gap = abs(words - cell.target_words)
    if gap > max(LENGTH_ERROR_TOLERANCE * cell.target_words, LENGTH_ERROR_SLACK_WORDS):
        findings.append(Finding("A10_length_out_of_range", "error", "message", f"{words} words"))
    elif gap > max(LENGTH_WARN_TOLERANCE * cell.target_words, LENGTH_WARN_SLACK_WORDS):
        findings.append(Finding("A10_length_off_target", "warning", "message", f"{words} words"))
    if not cell.greeting_allowed and GREETING_RE.search(customer):
        findings.append(Finding("A1_greeting_not_allowed", "warning", "message"))
    return findings


# --------------------------------------------------------------------------- record + dataset


def validate_record(record: DatasetRecord, ctx: ValidationContext) -> list[Finding]:
    """Run every record-level check.

    Args:
        record: Record (already schema-valid).
        ctx: Validation context.

    Returns:
        All findings.
    """
    findings = [
        Finding("provenance", "error", "provenance", problem)
        for problem in provenance_violations(record.provenance)
    ]
    findings.extend(validate_labels(record.labels, record.ticket, ctx))
    findings.extend(validate_text(record.ticket, record.labels, ctx))
    findings.extend(validate_card(record, ctx))
    return findings


@dataclass
class DatasetReport:
    """File-level validation summary (feeds ``data/manifests/<ver>.quality.json``).

    Attributes:
        split: Expected split.
        records: Lines that parsed as records.
        schema_errors: Line number to error count for lines that failed the schema.
        wrong_split: Record ids whose provenance names another split.
        family_violations: Record ids with a family not allowed in the split.
        exact_duplicates: Groups of record ids sharing one content hash.
        rule_counts: Rule id to count (errors and warnings).
        records_with_errors: Record ids with at least one error finding.
        greeting_rate: Share of records with a formulaic greeting or sign-off (soft gate <= 0.10).
        keyword_share: Critical intent to share of its tickets containing a canonical keyword
            (soft gate <= 0.75 in train).
    """

    split: str
    records: int = 0
    schema_errors: dict[int, int] = field(default_factory=dict)
    wrong_split: list[str] = field(default_factory=list)
    family_violations: list[str] = field(default_factory=list)
    exact_duplicates: list[list[str]] = field(default_factory=list)
    rule_counts: dict[str, int] = field(default_factory=dict)
    records_with_errors: list[str] = field(default_factory=list)
    greeting_rate: float = 0.0
    keyword_share: dict[str, float] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Hard gates: schema, provenance, rules and in-split duplicates all clean."""
        return not (
            self.schema_errors
            or self.wrong_split
            or self.family_violations
            or self.exact_duplicates
            or self.records_with_errors
        )


def check_dataset(
    lines: Sequence[str],
    split: str,
    ctx: ValidationContext,
    keywords: Mapping[str, Sequence[str]] | None = None,
) -> DatasetReport:
    """Validate a JSONL dataset file (T-DATA-provenance + hard and soft gates).

    Args:
        lines: File lines (one ``DatasetRecord`` JSON per line; blank lines ignored).
        split: The split the file claims to be.
        ctx: Validation context.
        keywords: Critical intent to canonical keywords (the matrix ``banned_words``).

    Returns:
        The report.
    """
    report = DatasetReport(split=split)
    by_hash: dict[str, list[str]] = {}
    counts: Counter[str] = Counter()
    greetings = 0
    keyword_hits: Counter[str] = Counter()
    per_intent: Counter[str] = Counter()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = DatasetRecord.model_validate_json(line)
        except ValidationError as exc:
            report.schema_errors[number] = exc.error_count()
            continue
        report.records += 1
        prov = record.provenance
        if prov.split != split:
            report.wrong_split.append(prov.record_id)
        if prov.generator_family not in ALLOWED_FAMILIES.get(prov.split, frozenset()):
            report.family_violations.append(prov.record_id)
        by_hash.setdefault(prov.content_sha256, []).append(prov.record_id)
        findings = validate_record(record, ctx)
        counts.update(f.rule for f in findings)
        if has_errors(findings):
            report.records_with_errors.append(prov.record_id)
        customer = f"{record.ticket.subject}\n{record.ticket.message}"
        greetings += bool(GREETING_RE.search(customer))
        intent = record.labels.intent
        per_intent[intent] += 1
        words = (keywords or {}).get(intent, ())
        if any(re.search(rf"\b{re.escape(w)}\b", customer, re.IGNORECASE) for w in words):
            keyword_hits[intent] += 1
    report.exact_duplicates = [ids for ids in by_hash.values() if len(ids) > 1]
    report.rule_counts = dict(sorted(counts.items()))
    report.greeting_rate = greetings / report.records if report.records else 0.0
    report.keyword_share = {
        intent: keyword_hits[intent] / per_intent[intent]
        for intent in sorted((keywords or {}).keys())
        if per_intent[intent]
    }
    return report


def report_json(report: DatasetReport) -> str:
    """Serialize a dataset report.

    Args:
        report: Report.

    Returns:
        Pretty JSON with a ``passed`` flag.
    """
    payload = asdict(report)
    payload["passed"] = report.passed
    payload["schema_errors"] = {str(k): v for k, v in report.schema_errors.items()}
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def read_lines(path: Path) -> list[str]:
    """Read a JSONL file (UTF-8).

    Args:
        path: File.

    Returns:
        Its lines.
    """
    return path.read_text(encoding="utf-8").splitlines()
