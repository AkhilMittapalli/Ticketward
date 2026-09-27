"""PII detection and masking for generated tickets (spec §5.6, §9.1 step 7, §12.5).

Generated tickets must carry personal data only as typed placeholders (``<EMAIL_1>``,
``<PERSON_1>``, ``<PHONE_1>``, ``<CARD_LAST4_1>``), exactly as the SLM sees masked production
text. Generators receive fictional persona names from the pools; :func:`mask_text` replaces
those (and any stray e-mail, phone or card number) with placeholders numbered after the ones
already present, and :func:`find_pii` is the rule-checker's R10 scan. The backend's Presidio
masker remains the production control; this module is a deterministic, dependency-free guard
for the data pipeline and deliberately errs toward flagging.
"""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from tw_ml.datagen.text import PLACEHOLDER_RE

PiiKind = Literal[
    "email", "phone", "card", "iban", "ssn", "secret", "url", "ip", "known_name", "placeholder"
]
ERROR_KINDS: Final[frozenset[str]] = frozenset(
    {"email", "phone", "card", "iban", "ssn", "secret", "url", "known_name", "placeholder"}
)
"""Every kind except ``ip`` blocks a record (``ip`` is reported as a warning)."""

EMAIL_RE: Final = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
PHONE_RE: Final = re.compile(
    r"(?<![\w+])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?\d{2,4}(?:[\s.-]\d{2,4}){1,4}(?!\w)"
)
DATE_START_RE: Final = re.compile(r"^(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}")
CARD_RE: Final = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
IBAN_RE: Final = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
SSN_RE: Final = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
URL_RE: Final = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']+")
IPV4_RE: Final = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)
SECRET_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\btm_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)  # fmt: skip
BAD_PLACEHOLDER_RES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"(?i)\[(?:your|customer|company|first|last|full|my)?[ _]?"
        r"(?:name|email|phone|company|address)\]"
    ),
    re.compile(r"\{\{[^{}]{1,40}\}\}"),
    re.compile(r"<(?:NAME|EMAIL|PHONE|COMPANY|ADDRESS|PERSON|CARD|CARD_LAST4)>"),
    re.compile(r"(?i)<(?:first|last|full|your)[ _]?name>"),
)  # fmt: skip
MIN_PHONE_DIGITS: Final = 9
MAX_PHONE_DIGITS: Final = 15  # E.164; longer digit runs are ids (spec §12.5 hard negatives)
CARD_DIGITS: Final = (13, 19)
IBAN_MOD: Final = 97


@dataclass(frozen=True, slots=True)
class PiiHit:
    """One detected piece of raw PII (the matched text is never stored).

    Attributes:
        kind: Kind of data.
        start: Start offset.
        end: End offset.
    """

    kind: PiiKind
    start: int
    end: int


@dataclass(slots=True)
class MaskResult:
    """Outcome of :func:`mask_text`.

    Attributes:
        text: Masked text.
        replacements: Original string to placeholder (applied to label values too).
        ops: Masking operations performed (``mask:person`` ...), recorded in ``noise_ops``.
    """

    text: str
    replacements: dict[str, str] = field(default_factory=dict)
    ops: list[str] = field(default_factory=list)


def luhn_valid(digits: str) -> bool:
    """Luhn checksum.

    Args:
        digits: Digit string.

    Returns:
        True when the checksum holds.
    """
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2  # noqa: PLR2004 - Luhn doubling
        total += value
    return total % 10 == 0


def iban_valid(candidate: str) -> bool:
    """ISO 13616 mod-97 check.

    Args:
        candidate: IBAN with or without spaces.

    Returns:
        True when the checksum holds.
    """
    compact = candidate.replace(" ", "")
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return numeric.isdigit() and int(numeric) % IBAN_MOD == 1


def find_pii(text: str, known_names: Iterable[str] = ()) -> list[PiiHit]:
    """Scan text for raw PII, secrets, URLs, known pool names and malformed placeholders.

    Args:
        text: Text to scan (typed placeholders are allowed and ignored).
        known_names: Fictional names that must have been masked (persona names).

    Returns:
        Hits in text order.
    """
    hits: list[PiiHit] = []
    hits += [PiiHit("email", m.start(), m.end()) for m in EMAIL_RE.finditer(text)]
    hits += [PiiHit("url", m.start(), m.end()) for m in URL_RE.finditer(text)]
    hits += [PiiHit("ssn", m.start(), m.end()) for m in SSN_RE.finditer(text)]
    hits += [PiiHit("ip", m.start(), m.end()) for m in IPV4_RE.finditer(text)]
    hits += [PiiHit("card", m.start(), m.end()) for m in _cards(text)]
    hits += [PiiHit("phone", m.start(), m.end()) for m in _phones(text)]
    hits += [
        PiiHit("iban", m.start(), m.end()) for m in IBAN_RE.finditer(text) if iban_valid(m.group(0))
    ]
    for pattern in SECRET_RES:
        hits += [PiiHit("secret", m.start(), m.end()) for m in pattern.finditer(text)]
    for pattern in BAD_PLACEHOLDER_RES:
        hits += [PiiHit("placeholder", m.start(), m.end()) for m in pattern.finditer(text)]
    for name in known_names:
        hits += [
            PiiHit("known_name", m.start(), m.end()) for m in _name_pattern(name).finditer(text)
        ]
    return sorted(hits, key=lambda h: (h.start, h.kind))


def mask_text(
    text: str,
    person_names: Sequence[str],
    replacements: Mapping[str, str] | None = None,
) -> MaskResult:
    """Replace fictional person names and stray contact data with typed placeholders.

    Full names are replaced before surnames and first names, each person keeps one index, and
    new indexes continue after the highest index already present (so a card-requested
    ``<PERSON_1>`` and the persona's own name stay distinct).

    Args:
        text: Generated text.
        person_names: Names to mask, grouped per person as ``"First Last"``.
        replacements: Existing original-to-placeholder map to reuse (for a second field).

    Returns:
        Masked text, the replacement map and the operations performed.
    """
    result = MaskResult(text=text, replacements=dict(replacements or {}))
    for full in person_names:
        parts = [full, *full.split()]
        placeholder = next(
            (result.replacements[p] for p in parts if p in result.replacements), None
        )
        for part in parts:
            pattern = _name_pattern(part)
            if not pattern.search(result.text):
                continue
            placeholder = placeholder or _next_placeholder("PERSON", result)
            result.text = pattern.sub(placeholder, result.text)
            result.replacements[part] = placeholder
            result.ops.append("mask:person")
    _mask_pattern(result, EMAIL_RE.finditer, "EMAIL", "mask:email")
    _mask_pattern(result, _cards, "CARD_LAST4", "mask:card")
    _mask_pattern(result, _phones, "PHONE", "mask:phone")
    result.ops = sorted(set(result.ops))
    return result


def apply_replacements(value: str, replacements: Mapping[str, str]) -> str:
    """Apply a mask map to another string (label values must match the masked text).

    Args:
        value: Label value.
        replacements: Map from :func:`mask_text`.

    Returns:
        The value with every original replaced (longest originals first).
    """
    for original in sorted(replacements, key=len, reverse=True):
        value = _name_pattern(original).sub(replacements[original], value)
    return value


def placeholder_indexes(text: str, kind: str) -> list[int]:
    """Indexes already used by placeholders of one kind.

    Args:
        text: Text.
        kind: Placeholder kind (``EMAIL``, ``PERSON``...).

    Returns:
        Sorted indexes.
    """
    return sorted(int(m.group(2)) for m in PLACEHOLDER_RE.finditer(text) if m.group(1) == kind)


def _next_placeholder(kind: str, result: MaskResult) -> str:
    used = placeholder_indexes(result.text, kind)
    for value in result.replacements.values():
        match = PLACEHOLDER_RE.fullmatch(value)
        if match and match.group(1) == kind:
            used.append(int(match.group(2)))
    return f"<{kind}_{max(used, default=0) + 1}>"


Finder = Callable[[str], Iterable[re.Match[str]]]


def _mask_pattern(result: MaskResult, finder: Finder, kind: str, op: str) -> None:
    matches = list(finder(result.text))
    placeholders: list[str] = []
    for match in matches:  # number in reading order, reusing one index per value
        original = match.group(0)
        if original not in result.replacements:
            result.replacements[original] = _next_placeholder(kind, result)
        placeholders.append(result.replacements[original])
    for match, placeholder in reversed(list(zip(matches, placeholders, strict=True))):
        result.text = result.text[: match.start()] + placeholder + result.text[match.end() :]
        result.ops.append(op)


def _name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w<]){re.escape(name)}(?![\w>])")


def _cards(text: str) -> list[re.Match[str]]:
    matches = []
    for match in CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if CARD_DIGITS[0] <= len(digits) <= CARD_DIGITS[1] and luhn_valid(digits):
            matches.append(match)
    return matches


def _phones(text: str) -> list[re.Match[str]]:
    card_spans = [(m.start(), m.end()) for m in _cards(text)]
    matches = []
    for match in PHONE_RE.finditer(text):
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        inside_card = any(s <= match.start() and match.end() <= e for s, e in card_spans)
        plausible = MIN_PHONE_DIGITS <= len(digits) <= MAX_PHONE_DIGITS
        if plausible and not DATE_START_RE.match(candidate) and not inside_card:
            matches.append(match)
    return matches
