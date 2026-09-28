"""Policy lexicon files: format, normalization and matching (spec v1.1 §7.3.3, §12.4).

The seven files in ``backend/policy/lexicons/`` are data shared by the P6 policy engine
(forced categories = model OR lexicon) and the E1 rules baseline. This module is the ml-side
reference implementation of the contract every file header states:

* **Header.** A leading block of ``# key: value`` lines (``#`` plus two or more spaces continues
  the previous value) with the keys ``lexicon`` (the file stem), ``version``
  (``<lexicon>.v<N>``), ``purpose``, ``consumer``, ``matching`` and ``syntax``.
* **Body.** ``[group]`` opens a pattern group; every other non-comment line is one pattern. A
  plain line is a whole-word phrase: its words must appear in order separated by whitespace,
  with no word character directly before the first or after the last word, and a trailing
  ``*`` on a word matches any further word characters. A line starting with ``re:`` is a
  Python regular expression. Duplicate patterns and empty groups are errors.
* **Matching.** Patterns run on the normalized text: invisible characters removed (Unicode
  format characters, category Cf, and variation selectors), NFKC, case-folded, NFKC again,
  typographic apostrophes folded to ``'``, whitespace collapsed. Regexes run with IGNORECASE.
* **Evidence.** A hit records the lexicon, the group and a stable pattern id
  (``<lexicon>.<group>.<8 hex>``, a hash of the pattern, so reordering a file keeps the ids),
  never the matched text (spec §7.3 evidence rule).
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

LEXICON_NAMES: Final[tuple[str, ...]] = (
    "human_request",
    "security",
    "legal",
    "billing_dispute",
    "refund",
    "cancellation",
    "injection",
)
REQUIRED_HEADER_KEYS: Final[tuple[str, ...]] = (
    "lexicon",
    "version",
    "purpose",
    "consumer",
    "matching",
    "syntax",
)
REGEX_PREFIX: Final = "re:"
PatternKind = Literal["phrase", "regex"]

_HEADER_KEY: Final = re.compile(r"^#\s?([a-z_]+):\s*(.*)$")
_HEADER_CONTINUATION: Final = re.compile(r"^#\s{2,}(\S.*)$")
_GROUP: Final = re.compile(r"^\[([a-z][a-z0-9_]*)\]$")
_VERSION: Final = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<number>[1-9]\d*)$")
_WHITESPACE: Final = re.compile(r"\s+")
_APOSTROPHE_CODES: Final = (0x2018, 0x2019, 0x201B, 0x02BC, 0x2032)
"""Typographic apostrophes and primes folded to ``'`` (code points, so no source confusables)."""
_APOSTROPHES: Final = str.maketrans(dict.fromkeys(map(chr, _APOSTROPHE_CODES), "'"))
_VARIATION_SELECTORS: Final[tuple[tuple[int, int], ...]] = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))


class LexiconError(ValueError):
    """Raised when a lexicon file violates the format (message names the line)."""


def is_invisible(char: str) -> bool:
    """Whether a character is removed before matching (§12.4 invisible-Unicode stripping).

    Args:
        char: One character.

    Returns:
        True for Unicode format characters (Cf: zero-width, bidi controls, BOM, soft hyphen,
        tag characters) and variation selectors.
    """
    if unicodedata.category(char) == "Cf":
        return True
    code = ord(char)
    return any(low <= code <= high for low, high in _VARIATION_SELECTORS)


def normalize_for_matching(text: str) -> str:
    """Normalize text exactly as the lexicon headers specify.

    Args:
        text: Sanitized, PII-masked ticket text.

    Returns:
        Invisible characters removed, NFKC, case-folded, NFKC, apostrophes folded, whitespace
        collapsed to single spaces and trimmed. Applying it twice changes nothing.
    """
    visible = "".join(char for char in text if not is_invisible(char))
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", visible).casefold())
    return _WHITESPACE.sub(" ", folded.translate(_APOSTROPHES)).strip()


def _is_word(char: str) -> bool:
    return char.isalnum() or char == "_"


def compile_phrase(phrase: str) -> re.Pattern[str]:
    """Compile a whole-word phrase pattern.

    Args:
        phrase: Words separated by spaces; a trailing ``*`` on a word matches any further word
            characters.

    Returns:
        The compiled regex (IGNORECASE).

    Raises:
        LexiconError: If the phrase is empty or contains a bare ``*``.
    """
    words = normalize_for_matching(phrase).split(" ")
    if not words or not words[0]:
        msg = "empty phrase"
        raise LexiconError(msg)
    parts = []
    for word in words:
        if word.endswith("*"):
            stem = word[:-1]
            if not stem or "*" in stem:
                msg = f"bad wildcard in {phrase!r}"
                raise LexiconError(msg)
            parts.append(re.escape(stem) + r"\w*")
        elif "*" in word:
            msg = f"'*' is only allowed at the end of a word: {phrase!r}"
            raise LexiconError(msg)
        else:
            parts.append(re.escape(word))
    first, last = words[0], words[-1]
    prefix = r"(?<!\w)" if _is_word(first[0]) else ""
    suffix = "" if last.endswith("*") or not _is_word(last[-1]) else r"(?!\w)"
    return re.compile(prefix + r"\s+".join(parts) + suffix, re.IGNORECASE)


def compile_pattern(source: str) -> tuple[PatternKind, re.Pattern[str]]:
    """Compile one pattern line (a phrase, or ``re:`` followed by a regex).

    Args:
        source: The pattern line without surrounding whitespace.

    Returns:
        ``(kind, regex)``.

    Raises:
        LexiconError: If the regex does not compile or the phrase is malformed.
    """
    if source.startswith(REGEX_PREFIX):
        expression = source[len(REGEX_PREFIX) :].strip()
        if not expression:
            msg = "empty regex"
            raise LexiconError(msg)
        try:
            return "regex", re.compile(expression, re.IGNORECASE)
        except re.error as exc:
            msg = f"invalid regex ({exc.msg})"
            raise LexiconError(msg) from None
    return "phrase", compile_phrase(source)


def pattern_key(kind: PatternKind, source: str) -> str:
    """Duplicate-detection key of a pattern.

    Args:
        kind: Pattern kind.
        source: Pattern line.

    Returns:
        The normalized phrase, or the regex source, prefixed by its kind.
    """
    body = normalize_for_matching(source) if kind == "phrase" else source[len(REGEX_PREFIX) :]
    return f"{kind}:{body.strip()}"


@dataclass(frozen=True, slots=True)
class LexiconPattern:
    """One compiled pattern.

    Attributes:
        pattern_id: Stable id ``<lexicon>.<group>.<8 hex>``.
        group: Group name.
        kind: ``phrase`` or ``regex``.
        source: The pattern line as written.
        line: Line number in the file.
        regex: Compiled pattern.
    """

    pattern_id: str
    group: str
    kind: PatternKind
    source: str
    line: int
    regex: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class LexiconHit:
    """Evidence of one pattern hit (no matched text, spec §7.3)."""

    lexicon: str
    group: str
    pattern_id: str


@dataclass(frozen=True, slots=True)
class Lexicon:
    """A parsed lexicon file.

    Attributes:
        name: Lexicon name (the file stem).
        version: ``<name>.v<N>``.
        header: Header key to value.
        patterns: Patterns in file order.
        sha256: SHA-256 of the file with LF line endings.
    """

    name: str
    version: str
    header: Mapping[str, str]
    patterns: tuple[LexiconPattern, ...]
    sha256: str

    @property
    def groups(self) -> tuple[str, ...]:
        """Group names in file order."""
        return tuple(dict.fromkeys(p.group for p in self.patterns))

    def matches(self, normalized: str) -> tuple[LexiconHit, ...]:
        """Every pattern hit on already-normalized text.

        Args:
            normalized: Output of :func:`normalize_for_matching`.

        Returns:
            One hit per matching pattern, in file order.
        """
        return tuple(
            LexiconHit(self.name, p.group, p.pattern_id)
            for p in self.patterns
            if p.regex.search(normalized)
        )


@dataclass(frozen=True, slots=True)
class LexiconScan:
    """All hits of all lexicons on one text."""

    hits: tuple[LexiconHit, ...]

    def fired(self, lexicon: str, group: str | None = None) -> bool:
        """Whether a lexicon (or one of its groups) matched.

        Args:
            lexicon: Lexicon name.
            group: Optional group.

        Returns:
            True on any hit.
        """
        return any(h.lexicon == lexicon and (group is None or h.group == group) for h in self.hits)

    def groups(self, lexicon: str) -> frozenset[str]:
        """Groups of a lexicon that matched.

        Args:
            lexicon: Lexicon name.

        Returns:
            Group names.
        """
        return frozenset(h.group for h in self.hits if h.lexicon == lexicon)

    def lexicons(self) -> tuple[str, ...]:
        """Lexicons with at least one hit, in hit order."""
        return tuple(dict.fromkeys(h.lexicon for h in self.hits))


@dataclass(frozen=True, slots=True)
class LexiconSet:
    """The loaded lexicons."""

    lexicons: Mapping[str, Lexicon]

    def scan(self, text: str) -> LexiconScan:
        """Normalize a text once and run every lexicon on it.

        Args:
            text: Sanitized, PII-masked text.

        Returns:
            The hits.
        """
        normalized = normalize_for_matching(text)
        return LexiconScan(
            tuple(hit for lexicon in self.lexicons.values() for hit in lexicon.matches(normalized))
        )

    def versions(self) -> dict[str, str]:
        """Lexicon name to version (the ``policy_rule_sets.lexicon_versions`` shape)."""
        return {name: lexicon.version for name, lexicon in self.lexicons.items()}

    def digest(self) -> str:
        """SHA-256 over every file's name and hash (part of the E1 system id)."""
        payload = "\n".join(f"{n}:{lx.sha256}" for n, lx in sorted(self.lexicons.items()))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_header(lines: list[str]) -> tuple[dict[str, str], int]:
    """Parse the leading comment block; return the header and the first body line index."""
    header: dict[str, str] = {}
    last: str | None = None
    for index, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.startswith("#"):
            return header, index
        if line == "#":
            last = None
            continue
        key = _HEADER_KEY.match(line)
        if key:
            last = key.group(1)
            if last in header:
                msg = f"line {index + 1}: duplicate header key {last!r}"
                raise LexiconError(msg)
            header[last] = key.group(2).strip()
            continue
        more = _HEADER_CONTINUATION.match(line)
        if more and last is not None:
            header[last] = f"{header[last]} {more.group(1).strip()}".strip()
            continue
        msg = f"line {index + 1}: malformed header line"
        raise LexiconError(msg)
    return header, len(lines)


def parse_lexicon(text: str, *, name: str) -> Lexicon:
    """Parse and validate a lexicon file.

    Args:
        text: File content.
        name: Expected lexicon name (the file stem).

    Returns:
        The lexicon.

    Raises:
        LexiconError: On any format violation (the message names the line).
    """
    lines = text.replace("\r\n", "\n").split("\n")
    header, start = _parse_header(lines)
    missing = [key for key in REQUIRED_HEADER_KEYS if not header.get(key)]
    if missing:
        msg = f"{name}: header lacks {', '.join(missing)}"
        raise LexiconError(msg)
    version = _VERSION.fullmatch(header["version"])
    if header["lexicon"] != name or version is None or version.group("name") != name:
        msg = f"{name}: header lexicon/version must be {name!r} / '{name}.v<N>'"
        raise LexiconError(msg)
    patterns: list[LexiconPattern] = []
    group: str | None = None
    groups: set[str] = set()
    seen: dict[str, int] = {}
    for number, raw in enumerate(lines[start:], start=start + 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        opened = _GROUP.fullmatch(line)
        if opened:
            group = opened.group(1)
            if group in groups:
                msg = f"{name} line {number}: group [{group}] opened twice"
                raise LexiconError(msg)
            groups.add(group)
            continue
        if line.startswith("["):
            msg = f"{name} line {number}: malformed group header"
            raise LexiconError(msg)
        if group is None:
            msg = f"{name} line {number}: pattern before the first [group]"
            raise LexiconError(msg)
        try:
            kind, regex = compile_pattern(line)
        except LexiconError as exc:
            msg = f"{name} line {number}: {exc}"
            raise LexiconError(msg) from None
        key = pattern_key(kind, line)
        if key in seen:
            msg = f"{name} line {number}: duplicate of line {seen[key]}"
            raise LexiconError(msg)
        seen[key] = number
        digest = hashlib.blake2b(key.encode("utf-8"), digest_size=4).hexdigest()
        patterns.append(
            LexiconPattern(f"{name}.{group}.{digest}", group, kind, line, number, regex)
        )
    empty = sorted(groups - {p.group for p in patterns})
    if empty or not patterns:
        msg = f"{name}: empty groups: {', '.join(empty) or '(no patterns at all)'}"
        raise LexiconError(msg)
    body = text.replace("\r\n", "\n")
    return Lexicon(
        name=name,
        version=header["version"],
        header=dict(header),
        patterns=tuple(patterns),
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


def load_lexicon(path: Path) -> Lexicon:
    """Read one lexicon file (its name is the file stem).

    Args:
        path: ``<name>.txt``.

    Returns:
        The lexicon.
    """
    return parse_lexicon(path.read_text(encoding="utf-8"), name=path.stem)


def load_lexicons(directory: Path, names: Iterable[str] = LEXICON_NAMES) -> LexiconSet:
    """Load the policy lexicons.

    Args:
        directory: ``backend/policy/lexicons``.
        names: Lexicons to load.

    Returns:
        The set, keyed by name.

    Raises:
        LexiconError: If a file is missing or invalid.
    """
    loaded: dict[str, Lexicon] = {}
    for name in names:
        path = directory / f"{name}.txt"
        if not path.is_file():
            msg = f"missing lexicon file {name}.txt"
            raise LexiconError(msg)
        loaded[name] = load_lexicon(path)
    return LexiconSet(loaded)
