"""``python -m tw_ml.eval`` end to end: real specs, every write inside tmp_path."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tw_ml.baselines import rules as rules_cli
from tw_ml.datagen.paths import RepoPaths, default_paths
from tw_ml.datagen.records import DatasetRecord, TicketPayload, TriageLabels
from tw_ml.eval.__main__ import EXIT_GATE, EXIT_OK, EXIT_USAGE, main
from tw_ml.eval.report import ComparisonReport, load_report

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
Writer = Callable[[Path, list[Any]], Path]
MESSAGES = {
    "va_00001": (
        "sso_login_failure",
        "Okta sign-in fails with SAML_ERR_302 for 40 users since 09:15 UTC.",
    ),
    "va_00002": ("billing_duplicate_charge", "Invoice INV-V123456 was charged twice this month."),
    "va_00003": ("how_to_question", "How do I set up recurring tasks for my team?"),
    "va_00004": (
        "security_report",
        "Someone logged into our admin account from an unknown location.",
    ),
}


@dataclass(frozen=True)
class Sandbox(RepoPaths):
    """The real repository specs, but evals/ and manifests/ inside a sandbox."""

    sandbox: Path = Path()

    @property
    def evals_dir(self) -> Path:
        return self.sandbox / "evals"

    @property
    def reports_dir(self) -> Path:
        return self.sandbox / "evals" / "reports"

    @property
    def manifests_dir(self) -> Path:
        return self.sandbox / "manifests"


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(default_paths().root, tmp_path)


@pytest.fixture
def gold_file(
    tmp_path: Path,
    write_jsonl: Writer,
    make_ticket: Callable[..., TicketPayload],
    make_labels: Callable[..., TriageLabels],
    make_record: Callable[..., DatasetRecord],
) -> Path:
    rows = []
    for record_id, (intent, message) in MESSAGES.items():
        ticket = make_ticket(message=message)
        record = make_record(
            ticket=ticket, labels=make_labels(intent=intent), record_id=record_id, split="val"
        )
        rows.append(json.loads(record.model_dump_json()))
    return write_jsonl(tmp_path / "gold.jsonl", rows)


@pytest.fixture
def e1_predictions(tmp_path: Path, gold_file: Path, sandbox: Sandbox) -> Path:
    out = tmp_path / "e1.jsonl"
    assert rules_cli.main(["--input", str(gold_file), "--out", str(out)], sandbox, NOW) == 0
    return out


def _oracle(tmp_path: Path, gold_file: Path, write_jsonl: Writer, **extra: Any) -> Path:
    rows = []
    for line in gold_file.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        rows.append(
            {
                "record_id": record["provenance"]["record_id"],
                "system_id": "oracle",
                "output": record["labels"],
                **extra,
            }
        )
    return write_jsonl(tmp_path / f"oracle{len(extra)}.jsonl", rows)


def _score(*argv: str, sandbox: Sandbox) -> int:
    return main(["score", *argv, "--n-resamples", "200"], sandbox, NOW)


def test_score_writes_json_and_markdown(
    gold_file: Path, e1_predictions: Path, sandbox: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _score(
        "--pred",
        str(e1_predictions),
        "--gold",
        str(gold_file),
        "--split",
        "val",
        "--experiment",
        "E1",
        sandbox=sandbox,
    )
    assert code == EXIT_OK
    summary = json.loads(capsys.readouterr().out)
    report = load_report(Path(summary["report"]))
    assert Path(summary["markdown"]).is_file()
    assert Path(summary["report"]).parent == sandbox.reports_dir / "2026-09-27"
    assert report.system.system_id.startswith("tw-rules-baseline@rules_baseline.v1+")
    assert (report.experiment, report.split, report.holdout.sealed) == ("E1", "val", False)
    assert report.counts.n_with_decision == 4  # the rules preview
    assert report.metric("M-07a.forced_escalation") is not None
    assert report.provenance.gold_sha256
    assert report.provenance.analysis_plan_sha is None
    assert summary["gates_failed"] == []


def test_render_and_compare(
    tmp_path: Path,
    gold_file: Path,
    e1_predictions: Path,
    sandbox: Sandbox,
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _score(
        "--pred",
        str(e1_predictions),
        "--gold",
        str(gold_file),
        "--split",
        "val",
        "--experiment",
        "E1",
        sandbox=sandbox,
    )
    report_path = json.loads(capsys.readouterr().out)["report"]
    out = tmp_path / "baselines.md"
    assert (
        main(
            [
                "render",
                "--report",
                report_path,
                "--report",
                report_path,
                "--out",
                str(out),
                "--title",
                "P2",
            ],
            sandbox,
        )
        == 0
    )
    assert out.read_text(encoding="utf-8").startswith("# P2\n")
    capsys.readouterr()
    assert main(["render", "--report", report_path], sandbox) == 0
    assert capsys.readouterr().out.startswith("# E1 on val")
    oracle = _oracle(tmp_path, gold_file, write_jsonl)
    args = [
        "compare",
        "--gold",
        str(gold_file),
        "--split",
        "val",
        "--pred-a",
        str(oracle),
        "--pred-b",
        str(e1_predictions),
        "--n-resamples",
        "200",
    ]
    assert main(args, sandbox, NOW) == EXIT_OK
    comparison = ComparisonReport.model_validate_json(
        Path(json.loads(capsys.readouterr().out)["report"]).read_text(encoding="utf-8")
    )
    assert comparison.family == "exploratory"
    assert comparison.comparisons[0].system_a == "oracle"
    assert main([*args, "--family", "confirmatory"], sandbox, NOW) == EXIT_USAGE  # needs E3, E1, E2


def test_multi_seed_and_gate_failure(
    tmp_path: Path,
    gold_file: Path,
    e1_predictions: Path,
    sandbox: Sandbox,
    write_jsonl: Writer,
    capsys: pytest.CaptureFixture[str],
) -> None:
    oracle = _oracle(tmp_path, gold_file, write_jsonl)
    seeds = [
        "--pred",
        f"s42={e1_predictions}",
        "--pred",
        f"s1337={oracle}",
        "--gold",
        str(gold_file),
        "--split",
        "val",
        "--experiment",
        "E4",
        "--system-id",
        "tw-triage-test@0.0.1",
    ]
    assert _score(*seeds, sandbox=sandbox) == EXIT_USAGE  # --deployed-seed missing
    capsys.readouterr()
    assert _score(*seeds, "--deployed-seed", "s1337", sandbox=sandbox) == EXIT_OK
    report = load_report(Path(json.loads(capsys.readouterr().out)["report"]))
    assert report.system.seeds == ("s42", "s1337")
    macro = next(s for s in report.seeds if s.metric == "M-01.intent_macro_f1")
    assert macro.seed_mean_ci is not None
    assert set(macro.per_seed) == {"s42", "s1337"}
    failing = _oracle(tmp_path, gold_file, write_jsonl, validity="failed_fallback")
    args = [
        "--pred",
        str(failing),
        "--gold",
        str(gold_file),
        "--split",
        "val",
        "--experiment",
        "E4",
    ]
    assert _score(*args, sandbox=sandbox) == EXIT_OK
    assert "G-M04-P3" in json.loads(capsys.readouterr().out)["gates_failed"]
    assert _score(*args, "--fail-on-gate", sandbox=sandbox) == EXIT_GATE


def test_sealed_splits_are_refused_then_logged_in_p10(
    tmp_path: Path,
    sandbox: Sandbox,
    write_jsonl: Writer,
    make_labels: Callable[..., TriageLabels],
    capsys: pytest.CaptureFixture[str],
) -> None:
    labels = json.loads(make_labels().model_dump_json())
    gold = write_jsonl(
        tmp_path / "ts.jsonl", [{"record_id": f"ts_0000{i}", "labels": labels} for i in range(3)]
    )
    preds = write_jsonl(
        tmp_path / "p.jsonl",
        [{"record_id": f"ts_0000{i}", "system_id": "sys", "output": labels} for i in range(3)],
    )
    base = ["--pred", str(preds), "--gold", str(gold), "--experiment", "E4"]
    assert _score(*base, "--split", "test_synth", sandbox=sandbox) == EXIT_USAGE
    assert "refusing to evaluate sealed data" in capsys.readouterr().err
    assert (
        _score(*base, "--split", "val", sandbox=sandbox) == EXIT_USAGE
    )  # sealed records, open name
    assert not sandbox.reports_dir.exists()
    assert not sandbox.sealed_access_log.exists()
    unseal = [*base, "--split", "test_synth", "--phase", "P10", "--i-understand-sealed"]
    assert _score(*unseal, sandbox=sandbox) == EXIT_OK
    first = json.loads(capsys.readouterr().out)
    assert (first["sealed"], first["eval_count_on_split"]) == (True, 1)
    assert _score(*unseal, sandbox=sandbox) == EXIT_OK
    second = json.loads(capsys.readouterr().out)
    assert second["eval_count_on_split"] == 2
    assert second["report"].endswith("_run2.json")  # the first sealed report is kept
    rows = sandbox.sealed_access_log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(r)["action"] for r in rows] == ["score", "score"]
    assert load_report(Path(first["report"])).holdout.eval_count_on_split == 1


def test_usage_errors(tmp_path: Path, sandbox: Sandbox) -> None:
    missing = [
        "--pred",
        str(tmp_path / "p.jsonl"),
        "--gold",
        str(tmp_path / "g.jsonl"),
        "--split",
        "val",
        "--experiment",
        "E1",
    ]
    assert _score(*missing, sandbox=sandbox) == EXIT_USAGE
    with pytest.raises(SystemExit):
        _score(*missing, "--phase", "P99", sandbox=sandbox)
    with pytest.raises(SystemExit):
        _score(*missing, "--date", "27/09/2026", sandbox=sandbox)
