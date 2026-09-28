"""E3 bake-off runner: protocol, guards, outputs and the CLI (fake Ollama, no network)."""

import argparse
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import TicketPayload
from tw_ml.eval import bakeoff
from tw_ml.eval.bakeoff import (
    CandidateSummary,
    ItemOutcome,
    cpu_sample,
    latency_summary,
    plan_splits,
    run_tag,
    select_candidates,
    stats,
)
from tw_ml.eval.bakeoff_config import (
    BakeoffConfig,
    BakeoffConfigError,
    load_bakeoff_config,
)
from tw_ml.eval.data import load_predictions
from tw_ml.prompts import derive_nonce

SPEC_CANDIDATES = {
    "qwen35-2b": ("Qwen/Qwen3.5-2B", "lora_fp16", 1.0, False),
    "qwen3-1.7b": ("Qwen/Qwen3-1.7B", "lora_fp16", 1.0, False),
    "qwen3-4b-2507": ("Qwen/Qwen3-4B-Instruct-2507", "qlora_nf4", 1.0, False),
    "llama32-3b": ("meta-llama/Llama-3.2-3B-Instruct", "qlora_nf4", 0.5, False),
    "phi4-mini": ("microsoft/Phi-4-mini-instruct", "qlora_nf4", 1.0, False),
    "gemma4-e2b": ("google/gemma-4-E2B-it", "qlora_nf4", 1.0, True),
    "qwen35-0.8b": ("Qwen/Qwen3.5-0.8B", "lora_fp16", 1.0, True),
}


def _config(paths: RepoPaths) -> BakeoffConfig:
    config, _ = load_bakeoff_config(paths.configs_dir / "bakeoff.yaml")
    return config


def _summary(env: Any, tag: str) -> CandidateSummary:
    path = env.runs_dir / f"{tag}.summary.json"
    return CandidateSummary.model_validate_json(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- committed config


def test_committed_config_lists_the_a02_candidates(paths: RepoPaths) -> None:
    config = _config(paths)
    assert config.version == "bakeoff.v1"
    assert config.prompt_version == "triage.v1"
    assert config.decoding_schema == "triage_model_output.decoding.json"
    found = {c.id: (c.hf_repo, c.finetune_method, c.lic, c.optional) for c in config.candidates}
    assert found == SPEC_CANDIDATES
    for candidate in config.candidates:
        assert candidate.ollama_model == f"tw-bakeoff-{candidate.id}"
        assert (candidate.quantization, candidate.imatrix) == ("Q4_K_M", False)
        assert candidate.verify_before_run is True
        assert candidate.hf_revision == "<verify>"
        assert candidate.ollama_digest is None
        assert candidate.prompt_format == f"ml/configs/prompt_formats/{candidate.id}.json"
    assert "Qwen/Qwen2.5-3B-Instruct" not in {c.hf_repo for c in config.candidates}


def test_committed_config_encodes_the_request_protocol(paths: RepoPaths) -> None:
    config = _config(paths)
    request = config.request
    assert (request.raw, request.stream, request.truncate) == (True, False, False)
    assert request.options == {
        "temperature": 0,
        "num_ctx": 8192,
        "num_predict": 512,
        "seed": 42,
        "repeat_penalty": 1.0,
    }
    assert request.cpu_options == {"num_gpu": 0, "num_thread": 8}
    assert (config.ollama.version, config.ollama.llama_cpp_build) == ("0.34.4", "b11081")
    assert config.sampling.cpu_sample_n == 50
    score = config.score
    weights = (score.w_macro_f1, score.w_min_critical_recall, score.w_latency, score.w_license)
    assert weights == (0.40, 0.25, 0.20, 0.15)
    assert (score.latency_target_s, score.min_gain_macro_f1) == (5.0, 0.03)
    assert set(config.splits) == {"val", "hard_dev"}


def _broken(paths: RepoPaths, tmp_path: Path, edit: Any) -> Path:
    document = yaml.safe_load((paths.configs_dir / "bakeoff.yaml").read_text(encoding="utf-8"))
    edit(document)
    path = tmp_path / "bakeoff.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def _first(document: dict[str, Any], **changes: Any) -> None:
    document["candidates"][0].update(changes)


@pytest.mark.parametrize(
    ("edit", "fragment"),
    [
        (lambda d: _first(d, ollama_model="qwen3.5:2b-q4_K_M"), "no library tags"),
        (lambda d: _first(d, hf_repo="Qwen/Qwen2.5-3B-Instruct"), "dropped"),
        (lambda d: _first(d, license="qwen-research", lic=0.0), "has no Lic value"),
        (lambda d: _first(d, lic=0.5), "has Lic 1.0"),
        (lambda d: _first(d, finetune_method="qlora_nf4"), "lora_fp16"),
        (lambda d: _first(d, hf_revision="main"), "40-hex commit SHA"),
        (lambda d: _first(d, verify_before_run=False), "requires verify_before_run"),
        (lambda d: _first(d, quantization="Q8_0"), "quantization"),
        (lambda d: d["request"]["options"].update(temperature=0.7), "temperature must be 0"),
        (lambda d: d["request"]["options"].pop("num_ctx"), "num_ctx"),
        (lambda d: d["request"].update(truncate=True), "truncate"),
        (lambda d: d["request"]["cpu_options"].pop("num_thread"), "num_gpu and num_thread"),
        (lambda d: d["score"].update(w_license=0.25), "sum to 1"),
        (lambda d: d["candidates"].append(dict(d["candidates"][0])), "unique"),
        (lambda d: d["splits"].update(test_synth="data/x.jsonl"), "open splits"),
    ],
)
def test_protocol_breaks_are_refused(
    paths: RepoPaths, tmp_path: Path, edit: Any, fragment: str
) -> None:
    with pytest.raises(BakeoffConfigError, match=fragment):
        load_bakeoff_config(_broken(paths, tmp_path, edit))


def test_unreadable_configs_are_refused(tmp_path: Path) -> None:
    with pytest.raises(BakeoffConfigError, match="not found"):
        load_bakeoff_config(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: [unclosed", encoding="utf-8")
    with pytest.raises(BakeoffConfigError, match="not valid YAML"):
        load_bakeoff_config(bad)


def test_candidate_selection(paths: RepoPaths) -> None:
    config = _config(paths)
    default = [c.id for c in select_candidates(config, None, include_optional=False)]
    assert default == ["qwen35-2b", "qwen3-1.7b", "qwen3-4b-2507", "llama32-3b", "phi4-mini"]
    assert len(select_candidates(config, None, include_optional=True)) == 7
    chosen = select_candidates(config, ["phi4-mini", "qwen35-2b"], include_optional=False)
    assert [c.id for c in chosen] == ["qwen35-2b", "phi4-mini"]
    with pytest.raises(BakeoffConfigError, match="unknown candidate"):
        select_candidates(config, ["qwen2.5-3b"], include_optional=False)
    sizes = {c.id: c.size_class for c in config.candidates}
    assert sizes["qwen35-2b"] == sizes["qwen3-1.7b"] == sizes["qwen35-0.8b"] == "le_2b"
    assert sizes["qwen3-4b-2507"] == sizes["gemma4-e2b"] == "3_4b"


# --------------------------------------------------------------------------- runs


def test_run_sends_the_protocol_and_writes_scorable_outputs(
    bakeoff_env: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    env.ollama.answers = {
        "va_00002": "```json\n" + json.dumps(env.gold["va_00002"]) + "\n```",
        "va_00003": "Sorry, no JSON today.",
        "va_00004": ("length", '{"intent": "billing_dup'),
    }
    assert env.run("--candidate", "small-a") == bakeoff.EXIT_OK
    records = load_predictions(env.runs_dir / "small-a_val.jsonl")
    tiers = {r.record_id: r.validity for r in records}
    assert tiers == {
        "va_00001": "first_pass",
        "va_00002": "repaired_l1",
        "va_00003": "failed_fallback",
        "va_00004": "failed_fallback",
        "va_00005": "first_pass",
        "va_00006": "first_pass",
    }
    failed = {r.record_id: r.output for r in records if r.validity == "failed_fallback"}
    assert failed == {"va_00003": None, "va_00004": None}
    assert all(r.latency_ms is not None for r in records)
    assert {r.system_id for r in records} == {"tw-e3-zeroshot-small-a@abababababab+triage.v1"}
    bodies = env.ollama.generate_bodies()
    assert len(bodies) == 7  # warm-up + 6 tickets
    schema = json.loads(
        (env.paths.schemas_dir / "triage_model_output.decoding.json").read_text("utf-8")
    )
    salt = "bakeoff.v1:42"
    for body, record_id in zip(bodies[1:], sorted(env.gold), strict=True):
        assert (body["model"], body["raw"], body["stream"], body["truncate"]) == (
            "tw-bakeoff-small-a",
            True,
            False,
            False,
        )
        assert body["shift"] is False
        assert body["format"] == schema
        assert body["options"] == {
            "temperature": 0,
            "num_ctx": 8192,
            "num_predict": 512,
            "seed": 42,
            "repeat_penalty": 1.0,
            "stop": ["<|im_end|>"],
        }
        assert body["prompt"].startswith("<|im_start|>system\nYou are the triage model")
        assert body["prompt"].endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
        assert f"<ticket-{derive_nonce(record_id, salt=salt)}>" in body["prompt"]
    summary = _summary(env, "small-a_val")
    assert (summary.status, summary.mode, summary.n_items, summary.n_predicted) == (
        "complete",
        "accuracy",
        6,
        6,
    )
    assert summary.validity == {
        "first_pass": 3,
        "repaired_l1": 1,
        "repaired_l2": 0,
        "failed_fallback": 2,
    }
    assert summary.failures == {"no_json_object": 1, "truncated_length": 1}
    assert summary.repair_actions == {"strip_code_fences": 1}
    assert summary.verified is True
    assert summary.latency.hardware == "default"
    assert summary.latency.triage_p50_s is None  # no M-08 claim outside the CPU mode
    assert summary.latency.decode_tokens_per_s.p50 == 150.0
    assert summary.latency.prompt_tokens_per_s.p50 == 700.0
    assert summary.ollama["digest"] == "ab" * 32
    assert summary.ollama["loaded"]["context_length"] == 8192
    assert summary.holdout == {
        "split": "val",
        "origins": {"val": 6},
        "phase": "P2",
        "sealed": False,
    }
    timings = (env.runs_dir / "small-a_val.timings.jsonl").read_text(encoding="utf-8")
    assert "Case va_" not in timings  # no ticket text in the measurements
    assert len(timings.splitlines()) == 6
    printed = json.loads(capsys.readouterr().out)
    assert printed["runs"][0]["validity"]["first_pass"] == 3
    assert "hard_dev skipped" in printed["notes"][0]


def test_cpu_sample_sends_cpu_options_and_checks_m08(bakeoff_env: Any) -> None:
    env = bakeoff_env
    assert env.run("--candidate", "small-a", "--mode", "cpu-sample", "--n", "4") == 0
    bodies = env.ollama.generate_bodies()
    assert len(bodies) == 5
    assert all(b["options"]["num_gpu"] == 0 and b["options"]["num_thread"] == 8 for b in bodies)
    assert len(load_predictions(env.runs_dir / "small-a_val.cpu.jsonl")) == 4
    assert not (env.runs_dir / "small-a_val.jsonl").exists()
    latency = _summary(env, "small-a_val.cpu").latency
    assert latency.hardware == "cpu"
    assert latency.triage_p50_s is not None
    assert latency.triage_p50_s < 5.0
    assert (latency.m08_p50_ok, latency.m08_p95_ok, latency.latency_term) == (True, True, 1.0)


def test_unconstrained_runs_omit_the_schema_and_keep_their_own_files(bakeoff_env: Any) -> None:
    env = bakeoff_env
    env.ollama.answers = {"va_00001": "Sure! " + json.dumps(env.gold["va_00001"])}
    assert env.run("--candidate", "small-a", "--unconstrained") == 0
    assert all("format" not in body for body in env.ollama.generate_bodies())
    records = load_predictions(env.runs_dir / "small-a_val.free.jsonl")
    assert records[0].validity == "repaired_l1"
    assert records[0].system_id.endswith("+triage.v1+unconstrained")
    summary = _summary(env, "small-a_val.free")
    assert summary.constrained is False
    assert summary.request["format_file"] is None
    assert not (env.runs_dir / "small-a_val.jsonl").exists()


def test_limit_is_a_smoke_run_with_its_own_files(bakeoff_env: Any) -> None:
    env = bakeoff_env
    assert env.run("--candidate", "big-b", "--limit", "2") == 0
    assert len(load_predictions(env.runs_dir / "big-b_val.smoke.jsonl")) == 2
    assert _summary(env, "big-b_val.smoke").smoke_limit == 2
    assert not (env.runs_dir / "big-b_val.jsonl").exists()


def test_default_run_covers_every_non_optional_candidate(bakeoff_env: Any) -> None:
    env = bakeoff_env
    assert env.run() == 0
    assert sorted(p.name for p in env.runs_dir.glob("*_val.jsonl")) == [
        "big-b_val.jsonl",
        "small-a_val.jsonl",
    ]
    assert env.run("--candidate", "tiny-c") == 0
    assert (env.runs_dir / "tiny-c_val.jsonl").is_file()


# --------------------------------------------------------------------------- guards


def _write_rows(path: Path, rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def test_sealed_records_are_refused_before_any_call(
    bakeoff_env: Any, make_record: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    sealed = make_record(
        record_id="ts_00001",
        split="test_synth",
        generator_family="deepseek",
        generator_model="deepseek-ai/DeepSeek-V3.2",
        prompt_family="P-B",
    )
    source = _write_rows(env.paths.root / "sealed.jsonl", [sealed.model_dump_json()])
    assert env.run("--split", "val", "--input", str(source)) == bakeoff.EXIT_USAGE
    assert "refusing to evaluate sealed data" in capsys.readouterr().err
    assert env.ollama.requests == []


def test_hard_set_rows_count_as_sealed_without_the_manifest(
    bakeoff_env: Any, hard_cases: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    hard = env.paths.root / "evals" / "hard_dev.v1.jsonl"
    _write_rows(hard, [json.dumps(hard_cases[0])])
    assert env.run() == bakeoff.EXIT_USAGE  # hard_dev is planned because its file exists
    assert "hard_final" in capsys.readouterr().err
    assert env.run("--split", "hard_dev", "--input", str(hard)) == bakeoff.EXIT_USAGE
    assert env.ollama.requests == []


def test_unverified_candidates_need_the_explicit_flag(
    bakeoff_env: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    env.update_candidates(verify_before_run=True, ollama_digest=None)
    assert env.run("--candidate", "small-a") == bakeoff.EXIT_USAGE
    err = capsys.readouterr().err
    assert "verify_before_run is true" in err
    assert "--allow-unverified" in err
    assert env.ollama.generate_bodies() == []
    assert env.run("--candidate", "small-a", "--allow-unverified") == 0
    summary = _summary(env, "small-a_val")
    assert summary.verified is False
    assert summary.unverified == ("verify_before_run is true", "ollama_digest is not pinned")


@pytest.mark.parametrize(
    ("setup", "fragment"),
    [
        (lambda o: o.models.clear(), "is not available locally"),
        (lambda o: o.add_model("tw-bakeoff-small-a", quantization="Q8_0"), "is Q8_0, expected"),
        (lambda o: o.add_model("tw-bakeoff-small-a", digest="cd" * 32), "digest differs"),
        (lambda o: setattr(o, "version", "0.40.0"), "config pins 0.34.4"),
    ],
)
def test_preflight_blocks_mismatched_artifacts(
    bakeoff_env: Any, setup: Any, fragment: str, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    setup(env.ollama)
    assert env.run("--candidate", "small-a") == bakeoff.EXIT_USAGE
    assert fragment in capsys.readouterr().err
    assert env.ollama.generate_bodies() == []


def test_prompt_format_problems_block_the_run(
    bakeoff_env: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    (env.paths.root / "ml/configs/prompt_formats/small-a.json").unlink()
    fmt_b = env.paths.root / "ml/configs/prompt_formats/big-b.json"
    fmt_b.write_text(fmt_b.read_text("utf-8").replace("Qwen3-4B", "Qwen3-8B"), encoding="utf-8")
    assert env.run() == bakeoff.EXIT_USAGE
    err = capsys.readouterr().err
    assert "small-a: prompt format: prompt format not found" in err
    assert "big-b: prompt format was derived from Qwen/Qwen3-8B-Instruct-2507" in err


def test_unreachable_server_fails_the_preflight(
    bakeoff_env: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    env.ollama.handler = refuse
    assert env.run("--candidate", "small-a") == bakeoff.EXIT_USAGE
    assert "Ollama preflight failed (connect)" in capsys.readouterr().err


def test_client_errors_are_recorded_and_not_retried(bakeoff_env: Any) -> None:
    env = bakeoff_env
    env.ollama.answers = {"va_00001": ("status", 400)}
    assert env.run("--candidate", "small-a") == 0
    first = load_predictions(env.runs_dir / "small-a_val.jsonl")[0]
    assert (first.validity, first.output, first.latency_ms) == ("failed_fallback", None, None)
    rows = (env.runs_dir / "small-a_val.timings.jsonl").read_text("utf-8").splitlines()
    assert (json.loads(rows[0])["error"], json.loads(rows[0])["attempts"]) == ("http_4xx", 1)
    assert len(env.ollama.generate_bodies()) == 7
    assert _summary(env, "small-a_val").failures == {"http_4xx": 1}


def test_consecutive_failures_abort_the_candidate(
    bakeoff_env: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    env.ollama.answers = {record_id: ("status", 503) for record_id in env.gold}
    assert env.run("--candidate", "small-a") == bakeoff.EXIT_ABORTED
    summary = _summary(env, "small-a_val")
    assert summary.status == "aborted"
    assert summary.n_predicted == 5  # max_consecutive_failures in the config
    assert "5 consecutive failed calls (last: http_5xx)" in (summary.abort_reason or "")
    assert json.loads(capsys.readouterr().out)["runs"][0]["status"] == "aborted"


def test_a_failed_warm_up_aborts_before_any_ticket(bakeoff_env: Any) -> None:
    env = bakeoff_env
    env.ollama.fail_warmup = True
    assert env.run("--candidate", "small-a") == bakeoff.EXIT_ABORTED
    summary = _summary(env, "small-a_val")
    assert (summary.status, summary.n_predicted) == ("aborted", 0)
    assert summary.abort_reason == "warm-up failed (http_5xx)"
    assert (env.runs_dir / "small-a_val.jsonl").read_text("utf-8") == ""


def test_placement_problems_are_noted(bakeoff_env: Any) -> None:
    env = bakeoff_env
    loaded = {"name": "tw-bakeoff-small-a", "size_vram": 5, "context_length": 4096}
    env.ollama.ps = {"models": [loaded]}
    assert env.run("--candidate", "small-a", "--mode", "cpu-sample", "--n", "1") == 0
    notes = _summary(env, "small-a_val.cpu").notes
    assert "loaded context length 4096 differs from num_ctx 8192" in notes
    assert "the model is (partly) in GPU memory despite num_gpu 0" in notes
    env.ollama.ps = {"models": []}
    assert env.run("--candidate", "small-a", "--limit", "1") == 0
    notes = _summary(env, "small-a_val.smoke").notes
    assert "the server did not report the loaded model (/api/ps)" in notes


def test_dry_run_checks_everything_and_calls_nothing(
    bakeoff_env: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    env = bakeoff_env
    assert env.run("--dry-run") == 0
    report = json.loads(capsys.readouterr().out)
    assert report["prompt"]["rendered"] == 6
    assert report["prompt"]["system_chars"] > 5000
    assert [c["id"] for c in report["candidates"]] == ["small-a", "big-b"]
    assert all(c["blocking"] == [] for c in report["candidates"])
    env.update_candidates(verify_before_run=True)
    assert env.run("--dry-run", "--include-optional") == bakeoff.EXIT_USAGE
    report = json.loads(capsys.readouterr().out)
    assert len(report["candidates"]) == 3
    assert all(c["blocking"] for c in report["candidates"])
    assert env.ollama.requests == []


def test_split_planning_rules(bakeoff_env: Any) -> None:
    env = bakeoff_env
    config, _ = load_bakeoff_config(env.config_path)

    def plan(**overrides: Any) -> Any:
        values = {"mode": "accuracy", "split": None, "input": None, **overrides}
        return plan_splits(argparse.Namespace(**values), config, env.paths)

    planned, notes = plan()
    assert [split for split, _ in planned] == ["val"]
    assert notes == ["hard_dev skipped: evals/hard_dev.v1.jsonl does not exist yet"]
    with pytest.raises(bakeoff.BakeoffError, match="val only"):
        plan(mode="cpu-sample", split=["hard_dev"])
    with pytest.raises(bakeoff.BakeoffError, match="exactly one --split"):
        plan(input="x.jsonl")
    with pytest.raises(bakeoff.BakeoffError, match="no input file configured for val_dev"):
        plan(split=["val_dev"])
    with pytest.raises(bakeoff.BakeoffError, match="input not found"):
        plan(split=["val"], input=str(env.paths.root / "nope.jsonl"))
    _write_rows(env.paths.root / "evals" / "hard_dev.v1.jsonl", ["{}"])
    assert [split for split, _ in plan()[0]] == ["val", "hard_dev"]
    assert [split for split, _ in plan(mode="cpu-sample")[0]] == ["val"]


def test_cli_usage_errors(bakeoff_env: Any, capsys: pytest.CaptureFixture[str]) -> None:
    env = bakeoff_env
    missing = str(env.paths.root / "none.yaml")
    assert bakeoff.main(["run", "--config", missing], paths=env.paths) == bakeoff.EXIT_USAGE
    assert "bake-off config not found" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        bakeoff.main(["run", "--phase", "P99"], paths=env.paths)
    with pytest.raises(SystemExit):
        bakeoff.main(["run", "--n", "0"], paths=env.paths)
    with pytest.raises(SystemExit):
        bakeoff.main(["run", "--base-url", "ollama.local:11434"], paths=env.paths)
    assert env.run("--candidate", "small-a", "--limit", "1", "--base-url", "http://h.test:1") == 0


def test_prepare_candidate_reports_every_verification_gap(bakeoff_env: Any) -> None:
    env = bakeoff_env
    config, _ = load_bakeoff_config(env.config_path)
    small = config.candidate("small-a")
    ready = bakeoff.prepare_candidate(small, env.paths, prompt_version="triage.v1")
    assert (ready.blocking, ready.unverified) == ([], [])
    other = bakeoff.prepare_candidate(small, env.paths, prompt_version="triage.v2")
    assert other.unverified == ["prompt format goldens use triage.v1, not triage.v2"]
    pinned_elsewhere = small.model_copy(update={"hf_revision": "b" * 40})
    moved = bakeoff.prepare_candidate(pinned_elsewhere, env.paths, prompt_version="triage.v1")
    assert moved.blocking == ["prompt format revision differs from hf_revision"]
    unpinned = small.model_copy(update={"hf_revision": "<verify>"})
    gaps = bakeoff.prepare_candidate(unpinned, env.paths, prompt_version="triage.v1")
    assert gaps.unverified == ["hf_revision is <verify>"]
    fmt_path = env.paths.root / small.prompt_format
    document = json.loads(fmt_path.read_text("utf-8"))
    document["goldens"] = []
    fmt_path.write_text(json.dumps(document), encoding="utf-8")
    bare = bakeoff.prepare_candidate(small, env.paths, prompt_version="triage.v1")
    assert bare.unverified == ["prompt format has no golden renderings"]


def test_a_nonce_collision_fails_only_that_ticket(bakeoff_env: Any, make_record: Any) -> None:
    env = bakeoff_env
    nonce = derive_nonce("va_00007", salt="bakeoff.v1:42")
    ticket = {**json.loads(env.val_path.read_text("utf-8").splitlines()[0])["ticket"]}
    ticket["message"] = f"Case va_00007 quotes {nonce} by accident."
    payload = TicketPayload.model_validate(ticket)
    record = make_record(ticket=payload, record_id="va_00007", split="val")
    with env.val_path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json() + "\n")
    env.gold["va_00007"] = env.gold["va_00001"]
    assert env.run("--candidate", "small-a") == 0
    last = load_predictions(env.runs_dir / "small-a_val.jsonl")[-1]
    assert (last.record_id, last.validity) == ("va_00007", "failed_fallback")
    assert _summary(env, "small-a_val").failures == {"prompt_error": 1}


def test_outputs_outside_the_repository_are_named_by_file_only(
    bakeoff_env: Any, tmp_path: Path
) -> None:
    env = bakeoff_env
    serve = env.ollama.handler

    def failing_ps(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(500, json={"error": "ps failed"})
        response: httpx.Response = serve(request)
        return response

    env.ollama.handler = failing_ps
    outside = tmp_path / "elsewhere"
    assert env.run("--candidate", "small-a", "--limit", "1", "--out-dir", str(outside)) == 0
    summary = CandidateSummary.model_validate_json(
        (outside / "small-a_val.smoke.summary.json").read_text("utf-8")
    )
    assert summary.files["predictions"] == "small-a_val.smoke.jsonl"
    assert summary.ollama["loaded"] == {}


# --------------------------------------------------------------------------- measurements


def test_stats_percentiles() -> None:
    assert stats([]).model_dump() == {"n": 0, "p50": None, "p95": None, "mean": None, "max": None}
    values = stats([1.0, 2.0, 3.0, 4.0, 100.0])
    assert (values.n, values.p50, values.p95, values.mean, values.max) == (
        5,
        3.0,
        80.8,
        22.0,
        100.0,
    )


def _outcome(wall: float | None, **extra: Any) -> ItemOutcome:
    base: dict[str, Any] = {
        "record_id": "va_1",
        "validity": "first_pass",
        "actions": (),
        "error": None,
        "http_status": 200,
        "attempts": 1,
        "done_reason": "stop",
        "wall_ms": wall,
        "server_total_ms": wall,
        "load_ms": 1.0,
        "prompt_eval_count": 1000,
        "prompt_eval_ms": 5000.0,
        "eval_count": 100,
        "eval_ms": 4000.0,
        "prompt_chars": 5000,
    }
    return ItemOutcome(**{**base, **extra})


def test_latency_summary_sets_m08_only_for_cpu_runs(bakeoff_env: Any) -> None:
    config, _ = load_bakeoff_config(bakeoff_env.config_path)
    outcomes = [_outcome(8000.0), _outcome(12000.0), _outcome(None, error="timeout")]
    cpu = latency_summary(outcomes, cpu=True, config=config)
    assert (cpu.wall_ms.n, cpu.triage_p50_s, cpu.triage_p95_s) == (2, 10.0, 11.8)
    assert (cpu.m08_p50_ok, cpu.m08_p95_ok, cpu.latency_term) == (False, True, 0.5)
    assert (cpu.decode_tokens_per_s.p50, cpu.decode_tokens_per_s_aggregate) == (25.0, 25.0)
    assert cpu.prompt_tokens_per_s.p50 == 200.0
    other = latency_summary(outcomes, cpu=False, config=config)
    assert (other.triage_p50_s, other.m08_p50_ok, other.latency_term) == (None, None, None)
    silent = latency_summary(
        [_outcome(900.0, eval_count=0, prompt_eval_ms=None)], cpu=True, config=config
    )
    assert (silent.decode_tokens_per_s.n, silent.prompt_tokens_per_s.n) == (0, 0)
    assert silent.decode_tokens_per_s_aggregate is None


def test_cpu_sample_is_fixed_and_order_independent(make_ticket: Any) -> None:
    ticket = make_ticket()
    items = [(f"va_{i:05d}", ticket) for i in range(40)]
    picked = cpu_sample(items, 10, seed=42)
    assert len(picked) == 10
    assert picked == sorted(picked)
    chosen = {items[i][0] for i in picked}
    backwards = list(reversed(items))
    assert {backwards[i][0] for i in cpu_sample(backwards, 10, seed=42)} == chosen
    assert {items[i][0] for i in cpu_sample(items, 10, seed=7)} != chosen
    assert len(cpu_sample(items, 100, seed=42)) == 40


def test_run_tags_keep_smoke_and_cpu_runs_out_of_the_scoring_glob() -> None:
    assert run_tag("qwen35-2b", "val", "accuracy", smoke=False) == "qwen35-2b_val"
    assert run_tag("qwen35-2b", "val", "cpu_sample", smoke=False) == "qwen35-2b_val.cpu"
    assert run_tag("qwen35-2b", "val", "cpu_sample", smoke=True) == "qwen35-2b_val.cpu.smoke"
    assert run_tag("qwen35-2b", "hard_dev", "accuracy", smoke=True) == "qwen35-2b_hard_dev.smoke"
    free = run_tag("qwen35-2b", "val", "accuracy", smoke=False, constrained=False)
    assert free == "qwen35-2b_val.free"
