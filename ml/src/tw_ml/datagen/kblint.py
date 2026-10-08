"""KB front-matter validator and body linter (P1.17).

Validates ``data/kb/*.md`` against the schema defined in spec §8.2:

- YAML front-matter required fields and enum values
- ``doc_key`` pattern (``^[a-z][a-z0-9_]{1,127}$``) and filename match
- ``product_areas`` and ``plans_applicable`` against taxonomy enums
- ``approval_status`` lifecycle values
- ``review_due_at`` date format and staleness
- Known-incident metadata (incident_status, dates, regions, error_codes)
- Brand-denylist scan on body text
- Injection / prompt-override patterns in body
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

import yaml

from tw_ml.datagen.taxonomy import Taxonomy

DOC_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9_]{1,127}$")

DOC_TYPES: Final = frozenset({
    "help_article", "policy", "product_doc",
    "known_incident", "escalation_runbook", "reply_template",
})

APPROVAL_STATUSES: Final = frozenset(
    {"draft", "in_review", "approved", "retired"},
)

INCIDENT_STATUSES: Final = frozenset(
    {"investigating", "identified", "monitoring", "resolved"},
)

REGIONS: Final = frozenset({"us", "eu", "apac"})

REQUIRED_FIELDS: Final = (
    "doc_key",
    "doc_type",
    "title",
    "product_areas",
    "plans_applicable",
    "version",
    "approval_status",
    "owner",
    "review_due_at",
    "effective_from",
)

INCIDENT_FIELDS: Final = (
    "incident_status",
    "started_at",
    "affected_regions",
    "error_codes",
    "last_update_at",
)

_SHORT_BRAND_THRESHOLD: Final = 5
_MIN_BODY_LENGTH: Final = 50

_INJECTION_PATTERNS: Final = [
    re.compile(
        r"\b(?:ignore|disregard|override|bypass|forget)\b"
        r".{0,40}"
        r"\b(?:instructions?|rules?|prompts?|policy|policies|guidelines?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\bsystem\s*(?:prompt|message)\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+escalate\b", re.IGNORECASE),
    re.compile(
        r"\bmark\s+(?:this|it)\s+as\s+(?:low|normal)\s+priority\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bpromise\s+(?:a\s+)?(?:full\s+)?refund\b", re.IGNORECASE,
    ),
    re.compile(r"\bautomatically\s+approv", re.IGNORECASE),
]


@dataclass(frozen=True, slots=True)
class Finding:
    """One lint finding."""

    file: str
    field: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        """Serialize to a plain dict."""
        return {
            "file": self.file,
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(slots=True)
class KBLintReport:
    """Aggregated report for one or more KB docs."""

    findings: list[Finding] = field(default_factory=list)
    docs_checked: int = 0
    docs_passed: int = 0

    @property
    def passed(self) -> bool:
        """True when no error-severity findings exist."""
        return not any(
            f.severity == "error" for f in self.findings
        )

    @property
    def error_count(self) -> int:
        """Number of error-severity findings."""
        return sum(
            1 for f in self.findings if f.severity == "error"
        )

    @property
    def warning_count(self) -> int:
        """Number of warning-severity findings."""
        return sum(
            1 for f in self.findings if f.severity == "warning"
        )


def _parse_front_matter(
    text: str,
) -> tuple[dict[str, Any] | None, str]:
    """Split YAML front-matter from the markdown body."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    fm_text = text[3:end].strip()
    body = text[end + 4 :].strip()
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return None, text
    if not isinstance(fm, dict):
        return None, text
    return fm, body


def _check_date_field(
    fm: dict[str, Any], key: str, fname: str,
) -> Finding | None:
    val = fm.get(key)
    if val is None:
        return None
    if isinstance(val, date):
        return None
    if isinstance(val, str):
        try:
            date.fromisoformat(val)
            return None
        except ValueError:
            pass
    return Finding(fname, key, f"invalid date format: {val!r}")


def _load_denylist(
    path: Path,
) -> list[tuple[str, re.Pattern[str]]]:
    """Load the brand denylist and compile patterns."""
    if not path.is_file():
        return []
    entries: list[tuple[str, re.Pattern[str]]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        if len(entry) >= _SHORT_BRAND_THRESHOLD:
            pat = re.compile(re.escape(entry), re.IGNORECASE)
        else:
            pat = re.compile(
                rf"\b{re.escape(entry)}\b", re.IGNORECASE,
            )
        entries.append((entry, pat))
    return entries


def _lint_fields(  # noqa: PLR0912
    fm: dict[str, Any],
    fname: str,
    taxonomy: Taxonomy,
) -> list[Finding]:
    """Validate front-matter field values."""
    findings: list[Finding] = []

    for req in REQUIRED_FIELDS:
        if req not in fm:
            findings.append(Finding(
                fname, req, f"required field '{req}' is missing",
            ))

    doc_key = fm.get("doc_key", "")
    if doc_key and not DOC_KEY_RE.match(str(doc_key)):
        findings.append(Finding(
            fname, "doc_key",
            f"doc_key '{doc_key}' does not match pattern",
        ))

    expected = f"{doc_key}.md"
    if doc_key and fname != expected:
        findings.append(Finding(
            fname, "doc_key",
            f"filename does not match doc_key (expected '{expected}')",
        ))

    doc_type = fm.get("doc_type", "")
    if doc_type and doc_type not in DOC_TYPES:
        findings.append(Finding(
            fname, "doc_type", f"unknown doc_type '{doc_type}'",
        ))

    status = fm.get("approval_status", "")
    if status and status not in APPROVAL_STATUSES:
        findings.append(Finding(
            fname, "approval_status",
            f"unknown approval_status '{status}'",
        ))

    product_areas = fm.get("product_areas", [])
    if isinstance(product_areas, list):
        valid = set(taxonomy.values("ProductArea"))
        for area in product_areas:
            if area not in valid:
                findings.append(Finding(
                    fname, "product_areas",
                    f"unknown product_area '{area}'",
                ))

    plans = fm.get("plans_applicable", [])
    if isinstance(plans, list):
        valid_plans = set(taxonomy.values("PlanTier"))
        for plan in plans:
            if plan not in valid_plans:
                findings.append(Finding(
                    fname, "plans_applicable",
                    f"unknown plan '{plan}'",
                ))

    for date_field in ("review_due_at", "effective_from", "effective_to"):
        f = _check_date_field(fm, date_field, fname)
        if f:
            findings.append(f)

    version = fm.get("version")
    if version is not None and not isinstance(version, int):
        findings.append(Finding(
            fname, "version",
            f"version must be int, got {type(version).__name__}",
        ))

    return findings


def _lint_incident(
    fm: dict[str, Any],
    fname: str,
    error_codes: frozenset[str] | None,
) -> list[Finding]:
    """Validate known_incident-specific metadata."""
    findings: list[Finding] = []

    for inc_field in INCIDENT_FIELDS:
        if inc_field not in fm:
            findings.append(Finding(
                fname, inc_field,
                f"incident field '{inc_field}' required",
            ))

    inc_status = fm.get("incident_status", "")
    if inc_status and inc_status not in INCIDENT_STATUSES:
        findings.append(Finding(
            fname, "incident_status",
            f"unknown incident_status '{inc_status}'",
        ))

    regions = fm.get("affected_regions", [])
    if isinstance(regions, list):
        for region in regions:
            if region not in REGIONS:
                findings.append(Finding(
                    fname, "affected_regions",
                    f"unknown region '{region}'",
                ))

    codes = fm.get("error_codes", [])
    if isinstance(codes, list) and error_codes is not None:
        for code in codes:
            if code not in error_codes:
                findings.append(Finding(
                    fname, "error_codes",
                    f"unknown error_code '{code}'",
                    severity="warning",
                ))

    if inc_status == "resolved" and not fm.get("resolved_at"):
        findings.append(Finding(
            fname, "resolved_at",
            "resolved incidents must have resolved_at",
        ))

    return findings


def _lint_body(
    body: str,
    status: str,
    fname: str,
    denylist: list[tuple[str, re.Pattern[str]]],
) -> list[Finding]:
    """Check the markdown body for content issues."""
    findings: list[Finding] = []

    if not body.strip():
        findings.append(Finding(fname, "body", "document body is empty"))
        return findings

    if len(body.strip()) < _MIN_BODY_LENGTH:
        findings.append(Finding(
            fname, "body",
            "document body is very short (< 50 chars)",
            severity="warning",
        ))

    for brand, pattern in denylist:
        if pattern.search(body) and status != "draft":
            findings.append(Finding(
                fname, "body",
                f"brand-denylist match: '{brand}'",
                severity="warning",
            ))

    if status == "approved":
        for pat in _INJECTION_PATTERNS:
            match = pat.search(body)
            if match:
                findings.append(Finding(
                    fname, "body",
                    f"injection pattern in approved doc: "
                    f"'{match.group()}'",
                ))

    return findings


def lint_doc(
    path: Path,
    taxonomy: Taxonomy,
    denylist: list[tuple[str, re.Pattern[str]]],
    error_codes: frozenset[str] | None = None,
) -> list[Finding]:
    """Lint one KB markdown file."""
    fname = path.name
    text = path.read_text(encoding="utf-8")
    fm, body = _parse_front_matter(text)

    if fm is None:
        return [Finding(
            fname, "front_matter",
            "missing or unparseable YAML front-matter",
        )]

    findings = _lint_fields(fm, fname, taxonomy)

    if fm.get("doc_type") == "known_incident":
        findings.extend(_lint_incident(fm, fname, error_codes))

    status = fm.get("approval_status", "")
    findings.extend(_lint_body(body, status, fname, denylist))

    return findings


def lint_kb_dir(
    kb_dir: Path,
    taxonomy: Taxonomy,
    denylist_path: Path | None = None,
    error_codes: frozenset[str] | None = None,
) -> KBLintReport:
    """Lint all ``*.md`` files in the KB directory."""
    report = KBLintReport()
    denylist = _load_denylist(denylist_path) if denylist_path else []

    if not kb_dir.is_dir():
        report.findings.append(Finding(
            "(dir)", "kb_dir",
            f"KB directory does not exist: {kb_dir}",
        ))
        return report

    files = sorted(kb_dir.glob("*.md"))
    if not files:
        report.findings.append(Finding(
            "(dir)", "kb_dir",
            "no .md files found in KB directory",
        ))
        return report

    doc_keys: dict[str, str] = {}
    for path in files:
        report.docs_checked += 1
        findings = lint_doc(path, taxonomy, denylist, error_codes)
        if not any(f.severity == "error" for f in findings):
            report.docs_passed += 1
        report.findings.extend(findings)

        text = path.read_text(encoding="utf-8")
        fm, _ = _parse_front_matter(text)
        if fm:
            key = fm.get("doc_key", "")
            if key and key in doc_keys:
                report.findings.append(Finding(
                    path.name, "doc_key",
                    f"duplicate doc_key '{key}' "
                    f"(also in '{doc_keys[key]}')",
                ))
            elif key:
                doc_keys[key] = path.name

    return report
