"""Publish the ERPROT research notes to ``docs/research/`` (owner decision D-04).

The owner's private knowledge base (``Core files/ERPROT``) is the working copy. This tool copies
each note into the public repository with a provenance banner, and refuses to publish private
material: local filesystem paths, links that leave the research folder, real e-mail addresses
or secret-like strings. Nothing is written while any finding remains.

Usage (from the repository root)::

    make sync-research    # publish (and prune orphaned generated notes)
    make check-research   # fail if docs/research is stale (local: needs the private notes)
    make scan-research    # privacy scan of docs/research (what CI runs)

Without make, ``scripts/uv_backend.py`` keeps the virtualenv outside the OneDrive checkout::

    python scripts/uv_backend.py run python ../scripts/sync_research.py --check
"""

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

MARKER = "<!-- published-by: scripts/sync_research.py -->"
BANNER = (
    f"{MARKER}\n"
    "> **Published research note.** Copied from the owner's working research log by\n"
    "> `scripts/sync_research.py`. Section references (§) point to the project's private\n"
    "> specification, which is not part of this repository.\n"
)

EXIT_BLOCKED = 1
EXIT_USAGE = 2
_MARKER_SEARCH_LINES = 10
_EXCERPT_CHARS = 4

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
_RESERVED_EMAIL_DOMAIN = re.compile(
    r"(?i)(?:^|\.)(?:example\.(?:com|org|net)|example|test|invalid|localhost)$"
)
_PRIVATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("local-path", re.compile(r"(?i)\b[a-z]:[\\/](?:users|documents and settings)[\\/]")),
    ("local-path", re.compile(r"(?:^|[\s(`'\"])/(?:mnt/)?(?:[a-z]/)?(?:Users|home)/[\w.-]+/")),
    ("local-path", re.compile(r"(?i)\bonedrive[\\/]")),
    ("private-link", re.compile(r"\]\((?:\.\./|/)")),
    ("private-link", re.compile(r"(?i)\bcore(?: |%20)files[\\/]")),
    ("secret", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}")),
    ("secret", re.compile(r"\bhf_[A-Za-z0-9]{20,}")),
    ("secret", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("secret", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("secret", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("secret", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("secret", re.compile(r"\btm_(?:live|test)_[A-Za-z0-9]{8,}")),
)


@dataclass(frozen=True, slots=True)
class Finding:
    """Private content that blocks publication.

    Attributes:
        path: File containing the match.
        line: 1-based line number.
        kind: ``local-path``, ``private-link``, ``email`` or ``secret``.
        excerpt: A redacted hint (never the full secret or address).
    """

    path: Path
    line: int
    kind: str
    excerpt: str


@dataclass(slots=True)
class SyncReport:
    """Outcome of a publish run.

    Attributes:
        stale: Published files whose content differed from the rendered source.
        orphans: Generated files whose source note no longer exists.
        findings: Private-content hits; when present nothing was written.
    """

    stale: list[Path] = field(default_factory=list)
    orphans: list[Path] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def scan_text(text: str) -> list[tuple[int, str, str]]:
    """Find private content in one document.

    Args:
        text: Markdown source.

    Returns:
        ``(line, kind, redacted excerpt)`` for every hit, in line order.
    """
    hits: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PRIVATE_PATTERNS:
            for match in pattern.finditer(line):
                hits.append((number, kind, _redact(kind, match.group(0).strip())))
        for match in _EMAIL.finditer(line):
            domain = match.group(1)
            if not _RESERVED_EMAIL_DOMAIN.search(domain):
                hits.append((number, "email", f"...@{domain}"))
    return hits


def render_published(text: str) -> str:
    """Render a source note as its published form.

    The banner goes right after the H1 title (or at the top when there is none). Rendering an
    already-published document returns it unchanged apart from newline normalization.

    Args:
        text: Markdown source.

    Returns:
        The published Markdown with LF newlines and one trailing newline.
    """
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    if MARKER in body:
        return body.rstrip("\n") + "\n"
    lines = body.split("\n")
    if lines[0].startswith("# "):
        rendered = "\n".join([lines[0], "", BANNER.rstrip("\n"), *lines[1:]])
    else:
        rendered = f"{BANNER}\n{body}"
    return rendered.rstrip("\n") + "\n"


def scan_directory(folder: Path) -> list[Finding]:
    """Scan every Markdown file in a folder for private content.

    Args:
        folder: Directory to scan (non-recursive).

    Returns:
        All findings, ordered by file then line.
    """
    findings: list[Finding] = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        findings.extend(
            Finding(path, line, kind, excerpt) for line, kind, excerpt in scan_text(text)
        )
    return findings


def sync_research(src: Path, dest: Path, *, check: bool, prune: bool) -> SyncReport:
    """Publish (or, with ``check``, only compare) the research notes.

    Args:
        src: Folder holding the working copies (``Core files/ERPROT``).
        dest: Public folder (``docs/research``).
        check: Do not write; only report what would change.
        prune: Delete generated files whose source note was removed (ignored with ``check``).

    Returns:
        The run report. When ``findings`` is non-empty nothing was written or deleted.
    """
    report = SyncReport(findings=scan_directory(src))
    if report.findings:
        return report
    outputs = {
        dest / source.name: render_published(source.read_text(encoding="utf-8"))
        for source in sorted(src.glob("*.md"))
    }
    for path, content in outputs.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        report.stale.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if dest.is_dir():
        report.orphans = [
            path
            for path in sorted(dest.glob("*.md"))
            if path not in outputs and _is_generated(path)
        ]
    if prune and not check:
        for path in report.orphans:
            path.unlink()
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 on success; 1 when private content blocks publication or ``--check`` finds stale or
        orphaned files; 2 when the source folder is missing.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--src", type=Path, help="working notes (default: ../Core files/ERPROT)")
    parser.add_argument("--dest", type=Path, help="published folder (default: docs/research)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if docs/research is stale")
    mode.add_argument("--scan-only", action="store_true", help="privacy-scan docs/research")
    parser.add_argument("--prune", action="store_true", help="delete orphaned generated notes")
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root.resolve()
    dest: Path = (args.dest or repo_root / "docs" / "research").resolve()
    if args.scan_only:
        findings = scan_directory(dest) if dest.is_dir() else []
        _write_findings(findings, repo_root)
        if not findings:
            sys.stdout.write("docs/research: no private content found.\n")
        return EXIT_BLOCKED if findings else 0

    src: Path = (args.src or repo_root.parent / "Core files" / "ERPROT").resolve()
    if not src.is_dir():
        sys.stderr.write("Research source folder not found (pass --src).\n")
        return EXIT_USAGE
    report = sync_research(src, dest, check=args.check, prune=args.prune)
    if report.findings:
        _write_findings(report.findings, src)
        return EXIT_BLOCKED
    changed = [_display(path, repo_root) for path in report.stale]
    orphans = [_display(path, repo_root) for path in report.orphans]
    if args.check and (changed or orphans):
        sys.stderr.write(
            "docs/research is out of date; run scripts/sync_research.py:\n  "
            + "\n  ".join(changed + [f"{name} (orphan)" for name in orphans])
            + "\n"
        )
        return EXIT_BLOCKED
    if changed:
        sys.stdout.write("Published:\n  " + "\n  ".join(changed) + "\n")
    else:
        sys.stdout.write("docs/research up to date.\n")
    if orphans:
        verb = "Removed" if args.prune else "Orphaned (use --prune)"
        sys.stdout.write(f"{verb}:\n  " + "\n  ".join(orphans) + "\n")
    return 0


def _redact(kind: str, text: str) -> str:
    return f"{text[:_EXCERPT_CHARS]}..." if kind == "secret" else text


def _is_generated(path: Path) -> bool:
    head = path.read_text(encoding="utf-8").splitlines()[:_MARKER_SEARCH_LINES]
    return MARKER in head


def _display(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name


def _write_findings(findings: Sequence[Finding], root: Path) -> None:
    if not findings:
        return
    sys.stderr.write("Private content blocks publication:\n")
    for finding in findings:
        sys.stderr.write(
            f"  {_display(finding.path, root)}:{finding.line}: {finding.kind}: {finding.excerpt}\n"
        )
