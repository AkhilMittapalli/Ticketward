"""Literal entity extraction for the E1 rules baseline (spec v1.1 §5.6; guideline R7).

Values are copied exactly as written, so the server can compute spans by exact match; the one
exception is ``saml_idp``, whose value is the normalized provider id (``okta``, ``azure_ad``...).
Vocabularies come from the fact sheet (error codes, identity providers, features,
integrations, API endpoints, app versions); formats follow its identifiers table (``acct_``,
``ws_`` + 8 hex, ``INV-`` + letter + 6 digits). Masked PII placeholders (``<EMAIL_1>``...) are
never extracted. Nothing here depends on a split: the same rules run on every ticket.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Self

from tw_ml.datagen.factsheet import FactSheet
from tw_ml.datagen.records import EntityLabel

MAX_ENTITIES: Final = 20
_AMOUNT_NUMBER: Final = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?"
_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("error_code", re.compile(r"\b[A-Z][A-Z0-9]{1,9}_ERR_[A-Z0-9_]*[A-Z0-9]\b")),
    ("http_status", re.compile(r"\bHTTP [1-5]\d{2}\b")),
    ("invoice_id", re.compile(r"\bINV-[A-Z]\d{6}\b")),
    (
        "charge_amount",
        re.compile(
            rf"\$\s?{_AMOUNT_NUMBER}(?![\d,])|\bUSD\s{_AMOUNT_NUMBER}\b|\b{_AMOUNT_NUMBER}\sUSD\b"
        ),
    ),
    ("currency", re.compile(r"\bUSD\b")),
    ("workspace_id", re.compile(r"\bws_[0-9a-f]{8}\b")),
    ("account_id", re.compile(r"\bacct_[A-Za-z0-9]{4,32}\b")),
    ("browser", re.compile(r"\b(?:Chrome|Firefox|Safari|Edge|Opera|Brave) \d+(?:\.\d+)*\b")),
    (
        "os",
        re.compile(
            r"\b(?:Windows (?:10|11)|macOS \d+(?:\.\d+)*|iOS \d+(?:\.\d+)*|iPadOS \d+(?:\.\d+)*"
            r"|Android \d+(?:\.\d+)*|Ubuntu \d+\.\d+)\b"
        ),
    ),
    ("region", re.compile(r"\b(?:US|EU|APAC)\b")),
    ("timestamp", re.compile(r"\b\d{2}:\d{2} UTC\b")),
    (
        "legal_reference",
        re.compile(r"\b(?:UK )?GDPR (?:Art\.|Article) \d{1,2}\b|\bCCPA\b|\bCPRA\b"),
    ),
)
_DATES: Final = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November"
    r"|December) \d{1,2}\b"
    r"|\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b"
)
_USERS: Final = re.compile(
    r"\b(\d{1,6}) (?:users|people|members|seats|employees|teammates|colleagues|staff|accounts)\b"
)
_VERSION_WORD: Final = re.compile(r"\b(?:version|v|app)\s?(\d+\.\d+\.\d+)(?![\w.])", re.IGNORECASE)
_COMPETITOR: Final = re.compile(
    r"\b(?:moving|switching|migrating|move|switch|migrate|moved|switched|migrated|going)\s+"
    r"(?:(?:over|all|everything|our\s+\w+)\s+)?(?:over\s+)?to\s+"
    r"([A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*){0,2})"
)
_OWN_WORDS: Final = ("taskmoor", "api", "version", "us", "eu", "apac", "i", "the", "a", "an")
_PLAN_WORDS: Final = ("free", "starter", "business", "enterprise", "pro", "premium", "annual")
_IDENTITY_WORDS: Final = ("sso", "saml", "scim", "okta", "azure", "entra", "google", "onelogin")
_VENDOR_WORDS: Final = ("slack", "microsoft", "github", "gitlab", "zapier", "salesforce", "outlook")
_PLATFORM_WORDS: Final = ("windows", "macos", "ios", "android", "linux", "chrome", "firefox")
_DAY_WORDS: Final = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTH_WORDS: Final = ("january", "february", "march", "april", "may", "june", "july", "august")
_MORE_WORDS: Final = ("september", "october", "november", "december", "q1", "q2", "q3", "q4")
_NOT_COMPETITORS: Final[frozenset[str]] = frozenset(
    (
        *_OWN_WORDS,
        *_PLAN_WORDS,
        *_IDENTITY_WORDS,
        *_VENDOR_WORDS,
        *_PLATFORM_WORDS,
        "safari",
        "edge",
        "monthly",
        *_DAY_WORDS,
        *_MONTH_WORDS,
        *_MORE_WORDS,
    )
)
"""First words that name our own product, plans, vendors in the fact sheet or dates."""


@dataclass(frozen=True, slots=True)
class Found:
    """An extracted entity and where it starts (for reading order).

    Attributes:
        start: Character offset in the text.
        entity: The entity.
    """

    start: int
    entity: EntityLabel


def find_competitor(text: str) -> tuple[int, str] | None:
    """A named product the customer says they are moving to (A-06 "named competitor").

    Args:
        text: Original-case ticket text.

    Returns:
        ``(offset, name)`` of the first plausible name, or ``None``.
    """
    for match in _COMPETITOR.finditer(text):
        name = match.group(1).rstrip(".,;:!?&'-")
        first = name.split()[0].casefold() if name else ""
        if name and first not in _NOT_COMPETITORS:
            return match.start(1), name
    return None


BILLING_INTENTS: Final[frozenset[str]] = frozenset(
    {"billing_duplicate_charge", "billing_payment_failure", "refund_request"}
)
"""Charge dates are extracted only here; user counts everywhere else (R7 literal values)."""
FEATURE_INTENTS: Final[frozenset[str]] = frozenset(
    {"bug_report", "how_to_question", "plan_pricing_inquiry", "security_report"}
)
"""Intents whose tickets name a Taskmoor feature (generation matrix required entities)."""


def _literal(name: str, *, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<![\w/]){re.escape(name)}(?![\w/-])", flags)


def _longest_first(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values), key=lambda value: (-len(value), value)))


@dataclass(frozen=True, slots=True)
class EntityExtractor:
    """Fact-sheet-driven literal entity extractor.

    Attributes:
        idp_aliases: ``(alias, saml_idp value)`` pairs, longest alias first.
        features: Feature names, longest first.
        integrations: Integration names, longest first.
        endpoints: API endpoints.
        versions: Known app versions (current and previous per platform).
    """

    idp_aliases: tuple[tuple[str, str], ...]
    features: tuple[str, ...]
    integrations: tuple[str, ...]
    endpoints: tuple[str, ...]
    versions: frozenset[str]

    @classmethod
    def from_facts(cls, facts: FactSheet) -> Self:
        """Build the extractor from the fact sheet.

        Args:
            facts: Parsed fact sheet.

        Returns:
            The extractor.
        """
        aliases = {
            (alias, provider.value)
            for provider in facts.identity_providers
            for alias in (*provider.aliases, provider.display_name)
            if alias
        }
        return cls(
            idp_aliases=tuple(sorted(aliases, key=lambda pair: (-len(pair[0]), pair[0]))),
            features=_longest_first(f.name for f in facts.features),
            integrations=_longest_first(i.name for i in facts.integrations),
            endpoints=_longest_first(facts.api_endpoints),
            versions=frozenset(v for values in facts.app_versions.values() for v in values),
        )

    @staticmethod
    def codes(text: str) -> list[str]:
        """Error codes and HTTP statuses in reading order (they vote for intents).

        Args:
            text: Original-case ticket text.

        Returns:
            The literal codes.
        """
        found = [
            (match.start(), match.group(0))
            for kind, pattern in _PATTERNS
            if kind in {"error_code", "http_status"}
            for match in pattern.finditer(text)
        ]
        return [value for _, value in sorted(found)]

    def extract(self, text: str, *, intent: str, sso_context: bool) -> tuple[EntityLabel, ...]:
        """Extract literal entities in reading order.

        Args:
            text: Original-case ticket text (subject, message, prior messages).
            intent: Predicted primary intent (some types are intent-specific).
            sso_context: Whether identity-provider names may be read as ``saml_idp``.

        Returns:
            Unique ``(type, value)`` entities, at most 20.
        """
        found: list[Found] = []
        spans: dict[str, list[tuple[int, int]]] = {}
        for kind, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                spans.setdefault(kind, []).append(match.span())
                found.append(Found(match.start(), EntityLabel(type=kind, value=match.group(0))))
        found = [f for f in found if not _inside_other(f, spans)]
        if intent in BILLING_INTENTS:
            found += [
                Found(m.start(), _label("charge_date", m.group(0))) for m in _DATES.finditer(text)
            ]
        else:
            found += [
                Found(m.start(1), _label("user_count_affected", m.group(1)))
                for m in _USERS.finditer(text)
            ]
        found += self._versions(text, spans)
        if sso_context:
            found += self._named(text, self.idp_aliases, "saml_idp", case_sensitive=True)
        if intent in FEATURE_INTENTS:
            found += self._named(
                text, ((f, "") for f in self.features), "feature_name", case_sensitive=False
            )
        found += self._named(
            text, ((i, "") for i in self.integrations), "integration_name", case_sensitive=True
        )
        found += self._named(
            text, ((e, "") for e in self.endpoints), "api_endpoint", case_sensitive=True
        )
        competitor = find_competitor(text)
        if competitor is not None:
            found.append(Found(competitor[0], _label("competitor_name", competitor[1])))
        unique: dict[tuple[str, str], Found] = {}
        for item in sorted(found, key=lambda f: (f.start, f.entity.type)):
            unique.setdefault((item.entity.type, item.entity.value), item)
        return tuple(f.entity for f in list(unique.values())[:MAX_ENTITIES])

    def _versions(self, text: str, spans: dict[str, list[tuple[int, int]]]) -> list[Found]:
        taken = [*spans.get("os", []), *spans.get("browser", [])]
        hits = [(m.start(1), m.group(1)) for m in _VERSION_WORD.finditer(text)] + [
            (m.start(), version)
            for version in self.versions
            for m in _literal(version, case_sensitive=True).finditer(text)
        ]
        return [
            Found(start, _label("app_version", value))
            for start, value in hits
            if not any(low <= start < high for low, high in taken)
        ]

    @staticmethod
    def _named(
        text: str, names: Iterable[tuple[str, str]], kind: str, *, case_sensitive: bool
    ) -> list[Found]:
        """Whole-name matches; the value is the normalized id when given, else the text."""
        found: list[Found] = []
        covered: list[tuple[int, int]] = []
        for name, value in names:
            for match in _literal(name, case_sensitive=case_sensitive).finditer(text):
                low, high = match.span()
                if any(a <= low and high <= b for a, b in covered):
                    continue
                covered.append((low, high))
                found.append(Found(low, _label(kind, value or match.group(0))))
        return found


def _label(kind: str, value: str) -> EntityLabel:
    return EntityLabel(type=kind, value=value[:200])


def _inside_other(item: Found, spans: dict[str, list[tuple[int, int]]]) -> bool:
    """A currency inside an amount ("USD 2,400") is part of the amount, not its own entity."""
    if item.entity.type != "currency":
        return False
    return any(low <= item.start < high for low, high in spans.get("charge_amount", []))
