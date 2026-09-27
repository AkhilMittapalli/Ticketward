"""Research publishing (D-04): private content never reaches docs/research."""

from pathlib import Path

import pytest

from ticketward.tools.publish_research import (
    MARKER,
    main,
    render_published,
    scan_text,
    sync_research,
)


def _kinds(text: str) -> list[str]:
    return [kind for _, kind, _ in scan_text(text)]


@pytest.mark.parametrize(
    "text",
    [
        r"see C:\Users\someone\notes.md",
        "copied from C:/Users/someone/notes.md",
        "cd /c/Users/someone/project",
        "path `/home/someone/research/`",
        "(/Users/someone/Documents/x)",
        r"synced to OneDrive\Documents",
    ],
)
def test_local_paths_are_flagged(text: str) -> None:
    assert "local-path" in _kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "[spec](../TICKETWARD_SPEC.md)",
        "[root](/etc/passwd)",
        "stored in Core files/ERPROT",
        "Core%20files/x",
    ],
)
def test_links_leaving_research_are_flagged(text: str) -> None:
    assert "private-link" in _kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "key sk-ant-api03-abcdefghijkl",
        "token hf_abcdefghijklmnopqrstuvwxyz",
        "ghp_abcdefghijklmnopqrstuvwx",
        "AKIAABCDEFGHIJKLMNOP",
        "xoxb-1234567890-abcdef",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "tm_live_abcd1234efgh",
    ],
)
def test_secret_like_strings_are_flagged_and_redacted(text: str) -> None:
    hits = scan_text(text)
    assert [kind for _, kind, _ in hits] == ["secret"]
    _, _, excerpt = hits[0]
    assert excerpt.endswith("...")
    assert len(excerpt) <= len("-----") + len("...")


def test_real_emails_are_flagged_but_reserved_domains_are_allowed() -> None:
    assert _kinds("contact dana@acme.example or ops@example.com or a@b.test") == []
    hits = scan_text("write to someone@gmail.com")
    assert [(kind, excerpt) for _, kind, excerpt in hits] == [("email", "...@gmail.com")]


def test_clean_research_prose_has_no_findings() -> None:
    text = (
        "# Hybrid retrieval\n\nSee [bm25s](https://github.com/xhluca/bm25s) and "
        "[embeddings](embedding-model-choice.md). Spec §8.5 applies; pgvector 0.8.6.\n"
    )
    assert scan_text(text) == []


def test_render_puts_banner_after_title_once() -> None:
    rendered = render_published("# Title\r\n\r\nBody\r\n\r\n")
    assert rendered.startswith(f"# Title\n\n{MARKER}\n> **Published research note.**")
    assert rendered.endswith("\nBody\n")
    assert render_published(rendered) == rendered
    assert rendered.count(MARKER) == 1


def test_render_without_title_puts_banner_first() -> None:
    assert render_published("Body").startswith(MARKER)


def _write_notes(src: Path, notes: dict[str, str]) -> None:
    src.mkdir(parents=True, exist_ok=True)
    for name, text in notes.items():
        (src / name).write_text(text, encoding="utf-8")


def test_sync_writes_then_check_detects_staleness(tmp_path: Path) -> None:
    src, dest = tmp_path / "ERPROT", tmp_path / "docs" / "research"
    _write_notes(src, {"a.md": "# A\n\nalpha\n", "README.md": "# Index\n"})

    first = sync_research(src, dest, check=False, prune=False)
    assert sorted(path.name for path in first.stale) == ["README.md", "a.md"]
    assert (dest / "a.md").read_text(encoding="utf-8").count(MARKER) == 1
    assert sync_research(src, dest, check=True, prune=False).stale == []

    (src / "a.md").write_text("# A\n\nalpha v2\n", encoding="utf-8")
    stale = sync_research(src, dest, check=True, prune=False).stale
    assert [path.name for path in stale] == ["a.md"]
    assert "v2" not in (dest / "a.md").read_text(encoding="utf-8")


def test_private_content_blocks_every_write(tmp_path: Path) -> None:
    src, dest = tmp_path / "ERPROT", tmp_path / "docs" / "research"
    _write_notes(src, {"a.md": "# A\n", "b.md": r"# B" + "\n" + r"C:\Users\someone\x" + "\n"})

    report = sync_research(src, dest, check=False, prune=False)
    assert [(f.path.name, f.line, f.kind) for f in report.findings] == [("b.md", 2, "local-path")]
    assert not dest.exists()


def test_prune_removes_only_generated_orphans(tmp_path: Path) -> None:
    src, dest = tmp_path / "ERPROT", tmp_path / "docs" / "research"
    _write_notes(src, {"a.md": "# A\n", "gone.md": "# Gone\n"})
    sync_research(src, dest, check=False, prune=False)
    (src / "gone.md").unlink()
    (dest / "handwritten.md").write_text("# Kept\n", encoding="utf-8")

    assert [p.name for p in sync_research(src, dest, check=True, prune=True).orphans] == ["gone.md"]
    assert (dest / "gone.md").exists()  # --check never deletes

    sync_research(src, dest, check=False, prune=True)
    assert sorted(p.name for p in dest.iterdir()) == ["a.md", "handwritten.md"]


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo, src = tmp_path / "repo", tmp_path / "notes"
    _write_notes(src, {"a.md": "# A\n"})
    args = ["--repo-root", str(repo), "--src", str(src)]

    assert main([*args, "--check"]) == 1
    assert main(args) == 0
    assert main([*args, "--check"]) == 0
    assert main(["--repo-root", str(repo), "--scan-only"]) == 0
    assert main(["--repo-root", str(repo), "--src", str(tmp_path / "missing")]) == 2

    (repo / "docs" / "research" / "a.md").write_text("mail someone@gmail.com\n", encoding="utf-8")
    assert main(["--repo-root", str(repo), "--scan-only"]) == 1
    assert "email" in capsys.readouterr().err
