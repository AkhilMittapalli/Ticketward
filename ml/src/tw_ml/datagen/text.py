"""Text normalization and stable hashing shared by records, validation and leakage checks.

Normalization follows ERPROT ``leakage-and-dedup`` D1 (spec §9.3): NFKC, then typed PII
placeholders rewritten to lowercase tokens (``<EMAIL_1>`` -> ``<email>``) *before*
lowercasing (the placeholder pattern is uppercase), then lowercase, every digit run -> ``0``,
whitespace collapsed. Hashes are ``sha256`` / ``blake2b``; Python's salted ``hash()`` is never
used, so results are identical across processes and machines.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Final

PLACEHOLDER_KINDS: Final[tuple[str, ...]] = ("EMAIL", "PERSON", "PHONE", "CARD_LAST4")
PLACEHOLDER_RE: Final = re.compile(r"<(EMAIL|PERSON|PHONE|CARD_LAST4)_(\d+)>")
"""Masked-PII placeholders produced by the masker (spec §5.6, §12.5)."""

_DIGITS: Final = re.compile(r"\d+")
_WS: Final = re.compile(r"\s+")
_WORD: Final = re.compile(r"[a-z0-9]+")
_NORMALIZATION_ID: Final = "nfkc|placeholders|lower|digits0|ws"


def normalization_id() -> str:
    """Identify the normalization pipeline (written into every leakage report).

    Returns:
        A short, stable description of the normalization steps.
    """
    return _NORMALIZATION_ID


def normalize(text: str) -> str:
    """Normalize text for hashing and similarity (ERPROT leakage D1).

    Args:
        text: Raw (already masked) text.

    Returns:
        The normalized text; applying the function twice changes nothing.
    """
    value = unicodedata.normalize("NFKC", text)
    value = PLACEHOLDER_RE.sub(lambda m: f"<{m.group(1).lower()}>", value).lower()
    value = _DIGITS.sub("0", value)
    return _WS.sub(" ", value).strip()


def join_customer_text(subject: str, message: str, prior_customer_bodies: Iterable[str]) -> str:
    """Build ``customer_text``: subject, message and customer-authored prior messages.

    Args:
        subject: Ticket subject.
        message: Latest customer message.
        prior_customer_bodies: Bodies of earlier messages whose author is the customer.

    Returns:
        The newline-joined text that every leakage check compares.
    """
    return "\n".join([subject, message, *prior_customer_bodies])


def sha256_hex(data: str) -> str:
    """Hex SHA-256 of a UTF-8 string.

    Args:
        data: Text to hash.

    Returns:
        64 lowercase hex characters.
    """
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def content_sha256(text: str) -> str:
    """SHA-256 of the normalized text (the provenance ``content_sha256``).

    Args:
        text: Customer text.

    Returns:
        Hex digest of :func:`normalize` applied to the text.
    """
    return sha256_hex(normalize(text))


def char_shingles(text: str, n: int = 5) -> frozenset[str]:
    """Character n-grams of the normalized text.

    Args:
        text: Customer text.
        n: Shingle size (5 per A-12).

    Returns:
        The set of shingles; a text shorter than ``n`` yields one shingle (itself).
    """
    value = normalize(text)
    if len(value) <= n:
        return frozenset({value})
    return frozenset(value[i : i + n] for i in range(len(value) - n + 1))


def word_tokens(text: str) -> list[str]:
    """Word tokens (``[a-z0-9]+``) of the normalized text.

    Args:
        text: Any text.

    Returns:
        Tokens in reading order.
    """
    return _WORD.findall(normalize(text))


def h64(parts: Sequence[str]) -> int:
    """Stable 64-bit hash of a token sequence (blake2b, unit-separator joined).

    Args:
        parts: Tokens.

    Returns:
        An unsigned 64-bit integer.
    """
    digest = hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def window_hashes(tokens: Sequence[str], n: int) -> set[int]:
    """Hash every ``n``-token window.

    Args:
        tokens: Token sequence.
        n: Window length.

    Returns:
        Set of window hashes (empty when the sequence is shorter than ``n``).
    """
    return {h64(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Exact Jaccard similarity of two sets.

    Args:
        left: First set.
        right: Second set.

    Returns:
        ``|A & B| / |A | B|``; two empty sets count as identical (1.0).
    """
    union = len(left | right)
    return len(left & right) / union if union else 1.0
