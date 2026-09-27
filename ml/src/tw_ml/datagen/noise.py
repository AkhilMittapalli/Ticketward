"""Deterministic typo noise applied after generation (spec §9.1.1; ERPROT artifact A6).

LLM tickets are too clean, and a generator asked for typos caricatures them. Instead a seeded
function applies a few keyboard-style edits to ordinary words and records each one in
``noise_ops`` (provenance). Placeholders, entity values, injected text and any other protected
string are never touched, so literal-entity checks still hold after noise.
"""

import random
import re
from collections.abc import Sequence
from typing import Final

NOISE_OPS: Final[tuple[str, ...]] = ("swap_adjacent", "drop_letter", "double_letter", "lowercase")
_WORD: Final = re.compile(r"[A-Za-z]{4,}")
_PLACEHOLDER: Final = re.compile(r"<[A-Z_0-9]+>")
MAX_OPS: Final = 3


def protected_spans(text: str, keep: Sequence[str]) -> list[tuple[int, int]]:
    """Character spans that noise must not touch.

    Args:
        text: Text to be edited.
        keep: Strings that must survive verbatim (entity values, injected text...).

    Returns:
        ``(start, end)`` spans of placeholders and every occurrence of a kept string.
    """
    spans = [(m.start(), m.end()) for m in _PLACEHOLDER.finditer(text)]
    for value in keep:
        if value:
            spans.extend((m.start(), m.end()) for m in re.finditer(re.escape(value), text))
    return spans


def add_noise(text: str, rng: random.Random, keep: Sequence[str] = ()) -> tuple[str, list[str]]:
    """Apply one to three seeded typo edits to unprotected words.

    Args:
        text: Text to edit (the customer's latest message).
        rng: Cell-specific generator (e.g. ``rng_for(seed, cell_id, "noise")``).
        keep: Strings that must survive verbatim.

    Returns:
        The edited text and the operations applied (``op@word_index``).
    """
    spans = protected_spans(text, keep)
    words = [
        m for m in _WORD.finditer(text) if not any(s < m.end() and m.start() < e for s, e in spans)
    ]
    if not words:
        return text, []
    count = min(len(words), rng.randint(1, MAX_OPS))
    chosen = sorted(rng.sample(range(len(words)), count))
    ops: list[str] = []
    result = text
    for index in reversed(chosen):
        match = words[index]
        op = rng.choice(NOISE_OPS)
        edited = _edit(match.group(0), op, rng)
        result = result[: match.start()] + edited + result[match.end() :]
        ops.append(f"{op}@{index}")
    return result, sorted(ops)


def _edit(word: str, op: str, rng: random.Random) -> str:
    position = rng.randint(1, len(word) - 3)
    if op == "swap_adjacent":
        return word[:position] + word[position + 1] + word[position] + word[position + 2 :]
    if op == "drop_letter":
        return word[:position] + word[position + 1 :]
    if op == "double_letter":
        return word[: position + 1] + word[position] + word[position + 1 :]
    return word.lower() if word[0].isupper() else word[:position] + word[position + 1 :]
