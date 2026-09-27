"""Validator and 30/70 split of the owner-written hard set (spec v1.1 §9.1 step 4, A-10, A-11).

The owner writes all 100 cases by hand, without LLM assistance, in ``evals/hard_set.v1.jsonl``
(guide: ``docs/hard_set_guide.md``; template: ``data/hard_set/TEMPLATE.jsonl``). This module:

* validates every row (schema, attestation ``llm_assisted=false``, strata tags consistent with
  the labels, the label rule-checker and the PII scan);
* checks the strata quotas: 100 cases, >= 6 per intent label, >= 25 critical combined,
  >= 10 injection attempts, >= 10 needs-more-info, >= 8 human requests (>= 3 indirect),
  >= 6 legal threats inside billing tickets;
* splits deterministically, stratified by primary intent, into ``hard_dev`` (30, error
  analysis allowed) and ``hard_final`` (70, sealed until P10).
"""

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Literal

from pydantic import AwareDatetime, Field, ValidationError

from tw_ml.datagen.alloc import stratified_split
from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.records import (
    DatasetRecord,
    Provenance,
    RecordModel,
    TicketPayload,
    TriageLabels,
)
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.datagen.text import content_sha256
from tw_ml.datagen.validate import Finding, ValidationContext, validate_labels, validate_text

HARD_SET_SIZE: Final = 100
HARD_DEV_SIZE: Final = 30
HARD_SPLIT_SEED: Final = 20260927
TEMPLATE_ID: Final = "th_000"


@dataclass(frozen=True, slots=True)
class Quotas:
    """Hard-set strata minimums (spec §9.1 step 4 + v1.1).

    Attributes:
        total: Exact number of cases.
        per_intent: Minimum per intent label (all 13, including ``other_unclear``).
        critical_combined: Minimum for the five critical intents together.
        injection: Minimum prompt-injection attempts.
        needs_info: Minimum needs-more-information cases.
        human_request: Minimum human-request phrasings.
        human_request_indirect: Minimum indirect human requests among them.
        legal_threat_in_billing: Minimum legal threats inside billing tickets.
    """

    total: int = HARD_SET_SIZE
    per_intent: int = 6
    critical_combined: int = 25
    injection: int = 10
    needs_info: int = 10
    human_request: int = 8
    human_request_indirect: int = 3
    legal_threat_in_billing: int = 6


class HardSetStrata(RecordModel):
    """Strata tags the owner sets for each case."""

    injection: bool
    needs_info: bool
    human_request: Literal["none", "direct", "indirect"]
    legal_threat_in_billing: bool


class Attestation(RecordModel):
    """Per-case authorship attestation (A-11)."""

    llm_assisted: bool
    author: str = Field(pattern=r"^R-[A-Za-z0-9_-]{1,32}$")
    written_at: AwareDatetime
    statement: str = Field(min_length=1, max_length=300)


class HardSetItem(RecordModel):
    """One hand-written case as the owner writes it."""

    record_id: str = Field(pattern=r"^th_\d{3}$")
    ticket: TicketPayload
    labels: TriageLabels
    strata: HardSetStrata
    persona_id: str | None = None
    company_id: str | None = None
    attestation: Attestation
    notes: str = Field(default="", max_length=1_000)


@dataclass(slots=True)
class HardSetReport:
    """Validation outcome.

    Attributes:
        items: Rows that parsed.
        parse_errors: Line number to error count.
        findings: Record id to error findings.
        duplicate_ids: Record ids used more than once.
        duplicate_texts: Groups of ids with the same normalized text.
        quota_shortfalls: Unmet strata quotas.
        counts: Stratum name to count.
    """

    items: list[HardSetItem] = field(default_factory=list)
    parse_errors: dict[int, int] = field(default_factory=dict)
    findings: dict[str, list[Finding]] = field(default_factory=dict)
    duplicate_ids: list[str] = field(default_factory=list)
    duplicate_texts: list[list[str]] = field(default_factory=list)
    quota_shortfalls: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Every row valid, no duplicates and every quota met."""
        return not (
            self.parse_errors
            or self.findings
            or self.duplicate_ids
            or self.duplicate_texts
            or self.quota_shortfalls
        )


def strata_findings(item: HardSetItem, rules: LabelRules) -> list[Finding]:
    """Consistency between the strata tags, the labels and the attestation.

    Args:
        item: Hard-set case.
        rules: Label rules (billing intents).

    Returns:
        Error findings.
    """
    labels, strata = item.labels, item.strata
    findings: list[Finding] = []
    if item.attestation.llm_assisted is not False:
        findings.append(
            Finding("H_llm_assisted", "error", "attestation.llm_assisted", "must be false")
        )
    if strata.needs_info and labels.information_sufficient:
        findings.append(
            Finding("H_needs_info_tag", "error", "strata.needs_info", "info is sufficient")
        )
    missing_tag = not strata.needs_info and not labels.information_sufficient
    if missing_tag and labels.intent != "other_unclear":
        findings.append(Finding("H_needs_info_tag", "error", "strata.needs_info", "tag missing"))
    if (strata.human_request != "none") != labels.customer_requested_human:
        findings.append(Finding("H_human_request_tag", "error", "strata.human_request"))
    billing = {labels.intent, *labels.secondary_intents} & rules.billing_intents
    if strata.legal_threat_in_billing and not billing:
        findings.append(
            Finding(
                "H_legal_billing_tag",
                "error",
                "strata.legal_threat_in_billing",
                "needs a billing intent",
            )
        )
    return findings


def validate_hard_set(
    lines: Sequence[str], ctx: ValidationContext, taxonomy: Taxonomy, quotas: Quotas | None = None
) -> HardSetReport:
    """Validate the hard-set file.

    The template row (``record_id`` ``th_000``) is ignored, so a copied template never counts.

    Args:
        lines: File lines.
        ctx: Rule-checker context.
        taxonomy: Taxonomy (intent list for quotas).
        quotas: Strata minimums.

    Returns:
        The report.
    """
    report = HardSetReport()
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            if isinstance(raw, dict) and raw.get("record_id") == TEMPLATE_ID:
                continue
            item = HardSetItem.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            report.parse_errors[number] = (
                exc.error_count() if isinstance(exc, ValidationError) else 1
            )
            continue
        report.items.append(item)
        errors = [
            f
            for f in (
                *strata_findings(item, ctx.rules),
                *validate_labels(item.labels, item.ticket, ctx),
                *validate_text(item.ticket, item.labels, ctx),
            )
            if f.severity == "error"
        ]
        if errors:
            report.findings[item.record_id] = errors
    ids = Counter(item.record_id for item in report.items)
    report.duplicate_ids = sorted(i for i, c in ids.items() if c > 1)
    by_text: dict[str, list[str]] = {}
    for item in report.items:
        by_text.setdefault(content_sha256(item.ticket.customer_text()), []).append(item.record_id)
    report.duplicate_texts = [group for group in by_text.values() if len(group) > 1]
    report.counts, report.quota_shortfalls = check_quotas(
        report.items, ctx.rules, taxonomy, quotas or Quotas()
    )
    return report


def check_quotas(
    items: Sequence[HardSetItem],
    rules: LabelRules,
    taxonomy: Taxonomy,
    quotas: Quotas | None = None,
) -> tuple[dict[str, int], list[str]]:
    """Count the strata and list unmet quotas.

    Args:
        items: Valid cases.
        rules: Label rules (critical set).
        taxonomy: Taxonomy (every intent label).
        quotas: Minimums.

    Returns:
        ``(counts, shortfalls)``.
    """
    quotas = quotas or Quotas()
    intents = Counter(item.labels.intent for item in items)
    counts: dict[str, int] = {f"intent:{i}": intents.get(i, 0) for i in taxonomy.values("Intent")}
    counts.update(
        {
            "total": len(items),
            "critical_combined": sum(1 for i in items if rules.is_critical(i.labels.intent)),
            "injection": sum(i.strata.injection for i in items),
            "needs_info": sum(i.strata.needs_info for i in items),
            "human_request": sum(i.strata.human_request != "none" for i in items),
            "human_request_indirect": sum(i.strata.human_request == "indirect" for i in items),
            "legal_threat_in_billing": sum(i.strata.legal_threat_in_billing for i in items),
        }
    )
    shortfalls = (
        [] if counts["total"] == quotas.total else [f"total: {counts['total']} != {quotas.total}"]
    )
    shortfalls += [
        f"{name}: {counts[name]} < {quotas.per_intent}"
        for name in counts
        if name.startswith("intent:") and counts[name] < quotas.per_intent
    ]
    minimums = {
        "critical_combined": quotas.critical_combined,
        "injection": quotas.injection,
        "needs_info": quotas.needs_info,
        "human_request": quotas.human_request,
        "human_request_indirect": quotas.human_request_indirect,
        "legal_threat_in_billing": quotas.legal_threat_in_billing,
    }
    shortfalls += [f"{k}: {counts[k]} < {v}" for k, v in minimums.items() if counts[k] < v]
    return counts, shortfalls


def split_hard_set(
    items: Sequence[HardSetItem], *, seed: int = HARD_SPLIT_SEED, dev_size: int = HARD_DEV_SIZE
) -> tuple[list[str], list[str]]:
    """Deterministic, intent-stratified split into ``hard_dev`` and ``hard_final``.

    The result depends only on the record ids, their labels and the seed, never on file order.

    Args:
        items: Valid cases.
        seed: Split seed (recorded in the manifest).
        dev_size: ``hard_dev`` size (30).

    Returns:
        ``(hard_dev_ids, hard_final_ids)``, each sorted.
    """
    dev, final = stratified_split(
        items,
        key=lambda i: i.labels.intent,
        first_size=dev_size,
        seed=seed,
        sort_key=lambda i: i.record_id,
    )
    return sorted(i.record_id for i in dev), sorted(i.record_id for i in final)


def to_record(
    item: HardSetItem, taxonomy: Taxonomy, *, seed: int = HARD_SPLIT_SEED
) -> DatasetRecord:
    """Convert a case to a ``DatasetRecord`` (``human_written``, ``llm_assisted=false``).

    Args:
        item: Valid case.
        taxonomy: Taxonomy (version).
        seed: Split seed recorded as the record seed.

    Returns:
        The record.
    """
    provenance = Provenance(
        record_id=item.record_id,
        split="test_hard",
        generator_family="human",
        generator_model="human",
        provider="owner",
        seed=seed,
        created_at=item.attestation.written_at,
        label_source="human_written",
        label_basis="human",
        taxonomy_version=taxonomy.version,
        content_sha256=content_sha256(item.ticket.customer_text()),
        persona_id=item.persona_id,
        company_id=item.company_id,
        llm_assisted=item.attestation.llm_assisted,
        reviewed_by=(item.attestation.author,),
        review_round=1,
        label_notes=item.notes or None,
    )
    return DatasetRecord(ticket=item.ticket, labels=item.labels, provenance=provenance)


def split_summary(
    items: Sequence[HardSetItem], dev_ids: Sequence[str], rules: LabelRules
) -> Mapping[str, Mapping[str, int]]:
    """Strata counts of each part (to confirm both parts cover the strata).

    Args:
        items: Valid cases.
        dev_ids: ``hard_dev`` ids.
        rules: Label rules.

    Returns:
        Part name to stratum counts.
    """
    dev = set(dev_ids)
    parts: dict[str, dict[str, int]] = {}
    for name, members in (
        ("hard_dev", [i for i in items if i.record_id in dev]),
        ("hard_final", [i for i in items if i.record_id not in dev]),
    ):
        parts[name] = {
            "total": len(members),
            "critical": sum(1 for i in members if rules.is_critical(i.labels.intent)),
            "injection": sum(i.strata.injection for i in members),
            "needs_info": sum(i.strata.needs_info for i in members),
            "human_request": sum(i.strata.human_request != "none" for i in members),
            "legal_threat_in_billing": sum(i.strata.legal_threat_in_billing for i in members),
        }
    return parts


def written_after(items: Sequence[HardSetItem], moment: datetime) -> list[str]:
    """Cases whose attestation date is after a moment (e.g. the first generation run).

    R-22 asks for the hard set to be written *before* generated data is seen.

    Args:
        items: Cases.
        moment: Reference time.

    Returns:
        Record ids written after ``moment``.
    """
    return sorted(i.record_id for i in items if i.attestation.written_at > moment)
