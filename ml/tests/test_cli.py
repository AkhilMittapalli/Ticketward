"""``python -m tw_ml.datagen`` commands, offline: every write goes to tmp_path."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.__main__ import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main
from tw_ml.datagen.bitext import load_mapping
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import DatasetRecord, TicketPayload
from tw_ml.datagen.taxonomy import load_taxonomy

Writer = Callable[[Path, list[Any]], Path]


@dataclass(frozen=True)
class SandboxPaths(RepoPaths):
    """The real specs, but manifests written to a sandbox folder."""

    sandbox: Path = Path()

    @property
    def manifests_dir(self) -> Path:
        return self.sandbox / "manifests"

    @property
    def hard_dev_gold_file(self) -> Path:
        return self.sandbox / "hard_dev.v1.jsonl"


def _out(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out


def _json_head(text: str) -> dict[str, Any]:
    """The JSON object a command printed first (some commands add a trailing line)."""
    value, _ = json.JSONDecoder().raw_decode(text.lstrip())
    assert isinstance(value, dict)
    return value


@pytest.fixture
def train_rows(
    make_record: Callable[..., DatasetRecord], make_ticket: Callable[..., TicketPayload]
) -> list[dict[str, Any]]:
    rows = []
    teams = ["design", "finance", "support", "legal"]  # words, not numbers: digits normalize to 0
    for index, team in enumerate(teams, start=1):
        ticket = make_ticket(
            message=f"Okta sign-in fails with SAML_ERR_302 for the {team} team since 09:15 UTC."
        )
        rows.append(
            json.loads(make_record(ticket=ticket, record_id=f"tr_{index:05d}").model_dump_json())
        )
    return rows


# --------------------------------------------------------------------------- plan, pools, generate


def test_plan_reports_a_complete_val_plan(
    tmp_path: Path, paths: RepoPaths, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "plan.json"
    assert main(["plan", "--split", "val", "--json", str(target)], paths) == EXIT_OK
    out = _out(capsys)
    assert _json_head(out)["cells"] == 450
    assert "coverage gaps: 0" in out
    assert json.loads(target.read_text(encoding="utf-8"))["coverage_gaps"] == []


def test_pools_check_is_clean(paths: RepoPaths, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pools", "--check"], paths) == EXIT_OK
    assert "Pools up to date." in _out(capsys)


def test_generate_dry_run_needs_no_key(
    tmp_path: Path, paths: RepoPaths, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "generate",
        "--split",
        "train",
        "--family",
        "A",
        "--n",
        "2",
        "--dry-run",
        "--out",
        str(tmp_path),
    ]
    assert main(argv, paths) == EXIT_OK
    summary = _json_head(_out(capsys))
    assert summary["dry_run"] is True
    assert summary["processed"] == 2
    assert float(summary["estimated_usd"]) > 0
    rendered = sorted((tmp_path / "dry_run").glob("*.txt"))
    assert [p.name for p in rendered] == ["tr-c00000.txt", "tr-c00001.txt"]
    assert "### pa.t" in rendered[0].read_text(encoding="utf-8")


def test_family_b_dry_run_prices_deepseek_on_deepinfra(
    tmp_path: Path, paths: RepoPaths, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["generate", "--split", "test_synth", "--family", "B", "--n", "5", "--dry-run"]
    assert main([*argv, "--out", str(tmp_path)], paths) == EXIT_OK
    summary = _json_head(_out(capsys))
    assert (summary["dry_run"], summary["processed"]) == (True, 5)
    # Upper bound: 5 x (900 + 1400) output tokens at $0.38/M = $0.00437, plus the prompts.
    assert Decimal("0.0044") < Decimal(str(summary["estimated_usd"])) < Decimal("0.02")
    rendered = sorted((tmp_path / "dry_run").glob("*.txt"))
    assert len(rendered) == 5
    text = rendered[0].read_text(encoding="utf-8")
    assert text.count("### pb.") == 2  # both P-B stages


def test_generate_without_a_key_is_a_usage_error(
    tmp_path: Path, paths: RepoPaths, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["generate", "--split", "train", "--family", "A", "--n", "1", "--out", str(tmp_path)]
    assert main(argv, paths) == EXIT_USAGE
    assert "provider configuration" in capsys.readouterr().err
    assert not (tmp_path / "records.jsonl").exists()


def test_generate_refuses_a_family_the_split_forbids(
    tmp_path: Path, paths: RepoPaths, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "generate",
        "--split",
        "test_synth",
        "--family",
        "A",
        "--n",
        "1",
        "--dry-run",
        "--out",
        str(tmp_path),
    ]
    assert main(argv, paths) == EXIT_USAGE
    assert "generation refused" in capsys.readouterr().err


def test_arguments_are_required() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == EXIT_USAGE


# --------------------------------------------------------------------------- validate


def test_validate_a_split_file(
    tmp_path: Path,
    paths: RepoPaths,
    train_rows: list[dict[str, Any]],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_jsonl(tmp_path / "train.jsonl", train_rows)
    report = tmp_path / "report.json"
    assert (
        main(
            ["validate", "--split", "train", "--file", str(source), "--report", str(report)], paths
        )
        == EXIT_OK
    )
    assert _json_head(_out(capsys))["records"] == 4
    assert json.loads(report.read_text(encoding="utf-8"))["records"] == 4
    broken = write_jsonl(tmp_path / "broken.jsonl", [*train_rows, "{not json", train_rows[0]])
    assert main(["validate", "--split", "train", "--file", str(broken)], paths) == EXIT_FAILED
    printed = _json_head(_out(capsys))
    assert printed["schema_errors"]
    assert printed["exact_duplicates"]


def test_validate_a_protected_split_uses_the_plain_rules(
    tmp_path: Path,
    paths: RepoPaths,
    train_rows: list[dict[str, Any]],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_jsonl(tmp_path / "train.jsonl", train_rows)
    assert main(["validate", "--split", "test_hard", "--file", str(source)], paths) == EXIT_FAILED
    assert _json_head(_out(capsys))["wrong_split"] == [f"tr_{i:05d}" for i in range(1, 5)]


def test_validate_gates_flag_blocks_on_soft_violation(
    tmp_path: Path,
    paths: RepoPaths,
    train_rows: list[dict[str, Any]],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_jsonl(tmp_path / "train.jsonl", train_rows)
    assert main(["validate", "--split", "train", "--file", str(source)], paths) == EXIT_OK
    report = json.loads(_out(capsys))
    assert report["passed"] is True
    assert report["soft_gate_passed"] is True

    import tw_ml.datagen.validate as val_mod  # noqa: PLC0415

    monkeypatch.setattr(val_mod, "GREETING_RATE_MAX", -1.0)
    assert (
        main(["validate", "--split", "train", "--file", str(source), "--gates"], paths)
        == EXIT_FAILED
    )
    assert "soft gates failed" in capsys.readouterr().err

    monkeypatch.setattr(val_mod, "GREETING_RATE_MAX", 0.10)
    assert main(["validate", "--split", "train", "--file", str(source)], paths) == EXIT_OK
    _ = capsys.readouterr()


# --------------------------------------------------------------------------- leakage


LEAK_TEXTS = [
    "The Gantt board stops loading after we add a fifth swimlane to it.",
    "Exporting the weekly report to CSV leaves every date column empty.",
    "Our calendar sync with the shared inbox duplicates each recurring meeting.",
    "Comment mentions no longer send notifications to the people we tag.",
]


def test_leakage_clean_and_leaking_inputs(
    tmp_path: Path,
    paths: RepoPaths,
    write_jsonl: Writer,
    make_record: Callable[..., DatasetRecord],
    make_ticket: Callable[..., TicketPayload],
    capsys: pytest.CaptureFixture[str],
) -> None:
    def row(text: str, record_id: str, **provenance: Any) -> dict[str, Any]:
        record = make_record(
            ticket=make_ticket(message=text, subject="Question"), record_id=record_id, **provenance
        )
        return dict(json.loads(record.model_dump_json()))

    train_rows = [row(text, f"tr_{i:05d}") for i, text in enumerate(LEAK_TEXTS, start=1)]
    test_meta = {
        "split": "test_synth",
        "generator_family": "deepseek",
        "generator_model": "deepseek-ai/DeepSeek-V3.2",
        "api_model_id": "deepseek-ai/DeepSeek-V3.2",
        "generator_quantization": "fp4",
        "template_id": "pb.t1",
    }
    test_row = row(
        "Two-factor codes arrive by SMS about ten minutes after they expire.",
        "ts_00001",
        **test_meta,
    )
    train = write_jsonl(tmp_path / "train.jsonl", train_rows)
    clean_test = write_jsonl(tmp_path / "test_clean.jsonl", [test_row])
    kb = tmp_path / "kb"
    kb.mkdir()
    out = tmp_path / "leakage.json"
    argv = [
        "leakage",
        "--input",
        f"train={train}",
        "--input",
        f"test_synth={clean_test}",
        "--kb-dir",
        str(kb),
        "--out",
        str(out),
    ]
    assert main([*argv, "--write-filtered", str(tmp_path / "filtered")], paths) == EXIT_OK
    printed = _json_head(_out(capsys))
    assert printed["gate"]["passed"] is True
    assert printed["drops"] == 0
    assert json.loads(out.read_text(encoding="utf-8"))["input_files"].keys() == {
        "train",
        "test_synth",
    }
    assert (
        len((tmp_path / "filtered" / "train.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    )

    leaked = row(LEAK_TEXTS[1], "ts_00002", **test_meta)
    argv[4] = f"test_synth={write_jsonl(tmp_path / 'test_leak.jsonl', [test_row, leaked])}"
    assert main([*argv, "--write-filtered", str(tmp_path / "filtered2")], paths) == EXIT_FAILED
    printed = _json_head(_out(capsys))
    assert printed["gate"]["passed"] is False
    assert printed["drops"] == 1
    kept_lines = (tmp_path / "filtered2" / "train.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["provenance"]["record_id"] for line in kept_lines] == [
        "tr_00001",
        "tr_00003",
        "tr_00004",
    ]


def test_leakage_reads_the_hard_set_format(
    tmp_path: Path,
    paths: RepoPaths,
    hard_cases: list[dict[str, Any]],
    train_rows: list[dict[str, Any]],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    train = write_jsonl(tmp_path / "train.jsonl", train_rows)
    hard = write_jsonl(tmp_path / "hard_set.v1.jsonl", hard_cases[40:60])
    argv = [
        "leakage",
        "--input",
        f"train={train}",
        "--input",
        f"test_hard={hard}",
        "--kb-dir",
        str(tmp_path),
        "--out",
        str(tmp_path / "r.json"),
    ]
    main(argv, paths)
    report = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert "test_hard" in report["input_files"]
    assert _json_head(_out(capsys))["report"] == str(tmp_path / "r.json")


# --------------------------------------------------------------------------- qa


def test_qa_sample_score_and_kappa(
    tmp_path: Path,
    paths: RepoPaths,
    train_rows: list[dict[str, Any]],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_jsonl(tmp_path / "train.jsonl", train_rows)
    folder = tmp_path / "audit"
    assert (
        main(
            [
                "qa",
                "sample",
                "--file",
                str(source),
                "--n",
                "3",
                "--seed",
                "2",
                "--out-dir",
                str(folder),
            ],
            paths,
        )
        == EXIT_OK
    )
    assert "audit sample: 3 records" in _out(capsys)
    blind = [
        json.loads(line)
        for line in (folder / "audit_blind.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    proposals = json.loads((folder / "audit_proposals.json").read_text(encoding="utf-8"))
    assert {row["record_id"] for row in blind} == set(proposals)
    fields = (
        "intent",
        "priority",
        "recommended_queue",
        "customer_requested_human",
        "information_sufficient",
        "sentiment",
        "churn_risk",
    )
    reviews = [
        {"audit_id": row["audit_id"], "record_id": row["record_id"], "reviewer": "R-owner"}
        | {f: proposals[row["record_id"]][f] for f in fields}
        for row in blind
    ]
    reviews_file = write_jsonl(tmp_path / "reviews.jsonl", reviews)
    code = main(
        [
            "qa",
            "score",
            "--proposals",
            str(folder / "audit_proposals.json"),
            "--reviews",
            str(reviews_file),
        ],
        paths,
    )
    scored = _json_head(_out(capsys))
    assert (scored["n"], scored["errors"]) == (3, 0)
    assert code == EXIT_FAILED  # 0/3 cannot show an error rate below 5% (Wilson)

    first = write_jsonl(
        tmp_path / "a.jsonl", [{"intent": i} for i in ["bug_report", "how_to_question"] * 10]
    )
    second = write_jsonl(
        tmp_path / "b.jsonl", [{"intent": i} for i in ["bug_report", "how_to_question"] * 10]
    )
    assert (
        main(["qa", "kappa", "--a", str(first), "--b", str(second), "--n-resamples", "50"], paths)
        == EXIT_OK
    )
    assert _json_head(_out(capsys))["kappa"] == pytest.approx(1.0)
    third = write_jsonl(tmp_path / "c.jsonl", [{"intent": "bug_report"}] * 20)
    assert (
        main(["qa", "kappa", "--a", str(first), "--b", str(third), "--n-resamples", "50"], paths)
        == EXIT_FAILED
    )
    capsys.readouterr()


# --------------------------------------------------------------------------- manifest


def test_manifest_build_verify_freeze_bump(
    tmp_repo: RepoPaths,
    train_rows: list[dict[str, Any]],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_jsonl(tmp_repo.generated_dir / "train" / "records.jsonl", train_rows)
    files = ["--split", "train", "--file", str(source)]
    assert main(["manifest", "build", *files], tmp_repo) == EXIT_OK
    assert "data/manifests/train.json: 4 records, v1, frozen=False" in _out(capsys)
    assert main(["manifest", "verify", "--split", "train"], tmp_repo) == EXIT_OK
    assert "train: OK" in _out(capsys)
    assert main(["manifest", "freeze", *files], tmp_repo) == EXIT_OK
    assert "frozen=True" in _out(capsys)
    source.write_text(
        source.read_text(encoding="utf-8").replace("design team", "sales team"), encoding="utf-8"
    )
    assert main(["manifest", "verify"], tmp_repo) == EXIT_FAILED
    assert "sha256 mismatch" in _out(capsys)
    assert main(["manifest", "freeze", *files], tmp_repo) == EXIT_FAILED
    assert "frozen" in capsys.readouterr().err
    assert main(["manifest", "freeze", *files, "--bump"], tmp_repo) == EXIT_OK
    assert "v2, frozen=True" in _out(capsys)
    assert main(["manifest", "verify"], tmp_repo) == EXIT_OK
    assert (tmp_repo.manifests_dir / "train.v1.json").is_file()
    capsys.readouterr()


def test_manifest_records_the_val_dev_subset(
    tmp_repo: RepoPaths,
    make_record: Callable[..., DatasetRecord],
    make_ticket: Callable[..., TicketPayload],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rows = [
        json.loads(
            make_record(
                ticket=make_ticket(message=f"Okta fails with SAML_ERR_302 for team {i}."),
                record_id=f"va_{i:05d}",
                split="val",
            ).model_dump_json()
        )
        for i in range(450)
    ]
    source = write_jsonl(tmp_repo.generated_dir / "val" / "records.jsonl", rows)
    assert (
        main(["manifest", "build", "--split", "val", "--file", str(source), "--val-dev"], tmp_repo)
        == EXIT_OK
    )
    capsys.readouterr()
    built = json.loads((tmp_repo.manifests_dir / "val.json").read_text(encoding="utf-8"))
    assert len(built["subsets"]["val_dev"]) == 225


# --------------------------------------------------------------------------- hardset, bitext


def test_hardset_validate_and_split(
    tmp_path: Path,
    paths: RepoPaths,
    hard_cases: list[dict[str, Any]],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = write_jsonl(tmp_path / "hard_set.v1.jsonl", hard_cases)
    assert main(["hardset", "validate", "--file", str(source)], paths) == EXIT_OK
    assert _json_head(_out(capsys))["passed"] is True
    sandbox = SandboxPaths(paths.root, sandbox=tmp_path)
    assert main(["hardset", "split", "--file", str(source), "--write-manifest"], sandbox) == EXIT_OK
    printed = _json_head(_out(capsys))
    assert len(printed["hard_dev"]) == 30
    assert printed["hard_final_count"] == 70
    written = json.loads((tmp_path / "manifests" / "test_hard.json").read_text(encoding="utf-8"))
    assert written["subsets"]["hard_dev"] == printed["hard_dev"]
    assert (written["records"], written["generator_families"]) == (100, {"human": 100})
    gold_rows = (tmp_path / "hard_dev.v1.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(row)["record_id"] for row in gold_rows] == printed["hard_dev"]
    assert not {json.loads(row)["record_id"] for row in gold_rows} & set(
        written["subsets"]["hard_final"]
    )
    incomplete = write_jsonl(tmp_path / "short.jsonl", hard_cases[:90])
    assert main(["hardset", "split", "--file", str(incomplete)], paths) == EXIT_FAILED
    assert _json_head(_out(capsys))["quota_shortfalls"]


@pytest.mark.parametrize("command", ["build", "materialize"])
def test_bitext_refuses_to_download_by_default(
    command: str, paths: RepoPaths, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["bitext", command], paths) == EXIT_USAGE
    assert "--allow-download" in capsys.readouterr().err


def test_bitext_build_and_materialize_with_a_fake_source(
    tmp_path: Path,
    paths: RepoPaths,
    monkeypatch: pytest.MonkeyPatch,
    fake_bitext_source: Callable[..., Any],
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mapping = load_mapping(
        paths.spec_dir / "bitext_mapping.v1.yaml", load_taxonomy(paths.schemas_dir)
    )
    monkeypatch.setattr("tw_ml.datagen.__main__.HFRowSource", lambda: fake_bitext_source(mapping))
    pointers, records = tmp_path / "pointers.jsonl", tmp_path / "records.jsonl"
    files = ["--allow-download", "--pointers", str(pointers), "--records-out", str(records)]
    assert main(["bitext", "build", *files], paths) == EXIT_OK
    out = _out(capsys)
    assert _json_head(out)["records"] == 500
    assert "materialized 500 records" in out
    first = json.loads(pointers.read_text(encoding="utf-8").splitlines()[0])
    assert "message" not in first
    decisions = [{"source": first["source"], "row": first["bitext_row"], "decision": "reject"}]
    decisions.append({"source": "cs", "row": 0, "decision": "keep"})
    rejects = write_jsonl(tmp_path / "review_decisions.jsonl", decisions)
    assert main(["bitext", "build", *files, "--rejects", str(rejects)], paths) == EXIT_OK
    assert _json_head(_out(capsys))["skipped"]["rejected"] == 1
    records.unlink()
    assert main(["bitext", "materialize", *files], paths) == EXIT_OK
    assert "materialized 500 records" in _out(capsys)
    assert len(records.read_text(encoding="utf-8").splitlines()) == 500


# --------------------------------------------------------------------------- provenance


def _provenance_sandbox(
    tmp_path: Path, paths: RepoPaths, generator_families: dict[str, int],
) -> RepoPaths:
    import shutil  # noqa: PLC0415

    root = tmp_path / "repo"
    (root / "schemas" / "json").mkdir(parents=True)
    for f in paths.schemas_dir.iterdir():
        if f.is_file():
            shutil.copy(f, root / "schemas" / "json" / f.name)
    (root / "data" / "manifests").mkdir(parents=True)
    (root / "data" / "spec").mkdir(parents=True)
    (root / "evals").mkdir(parents=True)
    file_entry = {
        "path": "data/generated/train/records.jsonl",
        "sha256": "a" * 64, "bytes": 100, "records": 1,
    }
    manifest_data = {
        "manifest_version": "manifest.v1",
        "split": "train",
        "dataset_version": "v1",
        "created_at": "2026-10-08T00:00:00Z",
        "frozen": False,
        "frozen_at": None,
        "taxonomy_version": "2026-09-v1",
        "files": [file_entry],
        "records": 1,
        "content_digest": "b" * 64,
        "generator_families": generator_families,
        "label_sources": {"generator_proposed": 1},
    }
    (root / "data" / "manifests" / "train.json").write_text(
        json.dumps(manifest_data), encoding="utf-8",
    )
    return RepoPaths(root=root)


def test_provenance_passes_on_clean_manifests(
    tmp_path: Path,
    paths: RepoPaths,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sandbox = _provenance_sandbox(tmp_path, paths, {"openai_gpt_oss": 1})
    assert main(["provenance"], sandbox) == EXIT_OK
    report = _json_head(_out(capsys))
    assert report["passed"] is True
    assert report["violations"] == 0


def test_provenance_fails_on_anthropic_generator_family(
    tmp_path: Path,
    paths: RepoPaths,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sandbox = _provenance_sandbox(tmp_path, paths, {"anthropic_claude": 1})
    assert main(["provenance"], sandbox) == EXIT_FAILED
    report = _json_head(_out(capsys))
    assert report["passed"] is False
    assert report["violations"] >= 1
    assert any("anthropic" in d["detail"] for d in report["details"])


def test_provenance_detects_forbidden_vendor_in_committed_jsonl(
    tmp_path: Path,
    paths: RepoPaths,
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import shutil  # noqa: PLC0415

    root = tmp_path / "repo"
    (root / "schemas" / "json").mkdir(parents=True)
    for f in paths.schemas_dir.iterdir():
        if f.is_file():
            shutil.copy(f, root / "schemas" / "json" / f.name)
    (root / "data" / "manifests").mkdir(parents=True)
    (root / "data" / "spec").mkdir(parents=True)
    (root / "evals").mkdir(parents=True)
    poisoned = [{"record_id": "tr_00001", "provenance": {"generator_model": "claude-3-opus"}}]
    write_jsonl(root / "evals" / "bad.jsonl", poisoned)
    sandbox = RepoPaths(root=root)
    assert main(["provenance"], sandbox) == EXIT_FAILED
    report = _json_head(_out(capsys))
    assert report["passed"] is False
    assert any("claude" in d["detail"] for d in report["details"])
