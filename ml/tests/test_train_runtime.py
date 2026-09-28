"""Platform guards, MLflow environment and Hub helpers of the training runs (no network)."""

import json
from pathlib import Path

import pytest

from tw_ml.datagen.paths import RepoPaths
from tw_ml.train import hub
from tw_ml.train.runtime import (
    ABSENT,
    GpuFacts,
    RunPaths,
    library_versions,
    mlflow_environment,
    platform_problems,
    run_tags,
    torch_minor,
    tracking_uri,
    write_json,
)

T4 = GpuFacts(
    torch="2.11.0+cu130",
    cuda="13.0",
    cuda_available=True,
    names=("Tesla T4", "Tesla T4"),
    capability=(7, 5),
    memory_gib=14.56,
)


def test_platform_checks() -> None:
    assert torch_minor("2.11.0+cu130") == "2.11"
    assert torch_minor("2.14.1") == "2.14"
    assert platform_problems(T4, expected_torch="2.11", hardware="t4") == []
    newer = GpuFacts("2.12.0+cu130", "13.0", True, ("Tesla T4",), (7, 5), 14.6)
    assert (
        "not the platform torch 2.11"
        in platform_problems(newer, expected_torch="2.11", hardware="t4")[0]
    )
    cpu = GpuFacts("2.11.0", None, False, (), None, None)
    assert platform_problems(cpu, expected_torch="2.11", hardware="t4") == [
        "CUDA is not available (select a GPU accelerator)"
    ]
    l4 = GpuFacts("2.11.0+cu130", "13.0", True, ("NVIDIA L4",), (8, 9), 22.0)
    assert "not the configured t4" in platform_problems(l4, expected_torch="2.11", hardware="t4")[0]


def test_library_versions_never_import() -> None:
    versions = library_versions(("numpy", "torch", "tw-ml"))
    assert versions["torch"] == ABSENT  # the local environment is torch-free (A-03)
    assert versions["numpy"] != ABSENT
    assert versions["tw-ml"] != ABSENT


def test_run_paths_and_tracking(tmp_path: Path) -> None:
    run = RunPaths.for_run(tmp_path, "sft-qwen35-2b", 1337)
    assert run.root == tmp_path / "sft-qwen35-2b-s1337"
    assert (run.checkpoints.name, run.last_checkpoint.name, run.mlruns.name) == (
        "checkpoints",
        "last-checkpoint",
        "mlruns",
    )
    assert (run.epoch_eval.name, run.data_manifest.name, run.summary.name) == (
        "epoch_eval.jsonl",
        "data_manifest.json",
        "run_summary.json",
    )
    assert tracking_uri("file", run.mlruns).startswith("file:")
    assert tracking_uri("sqlite", run.mlruns).endswith("/mlruns/mlflow.db")
    env = mlflow_environment(
        store="file", mlruns=run.mlruns, experiment="tw-triage-sft", tags={"seed": "42"}
    )
    assert env["MLFLOW_EXPERIMENT_NAME"] == "tw-triage-sft"
    assert json.loads(env["MLFLOW_TAGS"]) == {"seed": "42"}
    assert env["HF_MLFLOW_LOG_ARTIFACTS"] == "FALSE"


def test_run_tags_are_strings() -> None:
    tags = run_tags(
        identity={"config_sha": "a" * 64, "seed": 42, "git_sha": None},
        versions={"torch": "2.11.0"},
        gpu=T4,
    )
    assert tags == {
        "config_sha": "a" * 64,
        "seed": "42",
        "git_sha": "unknown",
        "lib.torch": "2.11.0",
        "gpu": "Tesla T4, Tesla T4",
        "torch_cuda": "13.0",
    }
    assert "gpu" not in run_tags(identity={}, versions={}, gpu=None)


def test_write_json(tmp_path: Path) -> None:
    path = write_json(tmp_path / "a" / "b.json", {"z": 1, "a": [1, 2]})
    assert path.read_text(encoding="utf-8") == '{\n  "a": [\n    1,\n    2\n  ],\n  "z": 1\n}\n'


def test_resume_decisions(tmp_path: Path) -> None:
    assert not hub.resume_decision(None).resumed
    empty = hub.resume_decision(tmp_path)
    assert (empty.checkpoint, empty.reason) == (
        None,
        "fresh start: the repo has no last-checkpoint/ yet",
    )
    state = tmp_path / "last-checkpoint" / "trainer_state.json"
    state.parent.mkdir()
    state.write_text(json.dumps({"global_step": 75}), encoding="utf-8")
    decision = hub.resume_decision(tmp_path)
    assert decision.resumed
    assert decision.checkpoint == tmp_path / "last-checkpoint"
    assert decision.reason == "resuming from Hub last-checkpoint (step 75)"


def test_dataset_revision_and_files(tmp_path: Path) -> None:
    assert hub.check_dataset_revision("a" * 40) == "a" * 40
    with pytest.raises(hub.HubError, match="40-hex commit SHA"):
        hub.check_dataset_revision("main")
    assert hub.missing_training_files(tmp_path) == ["train/records.jsonl", "val/records.jsonl"]
    assert all("test" not in name for name in hub.TRAINABLE_FILES)  # sealed splits never downloaded


def test_run_uploads(tmp_path: Path) -> None:
    run = RunPaths(tmp_path)
    (tmp_path / "mlruns").mkdir()
    (tmp_path / "selection.json").write_text("{}", encoding="utf-8")
    (tmp_path / "checkpoints").mkdir()  # the trainer pushes those itself
    assert [p.name for p in hub.run_uploads(run)] == ["mlruns", "selection.json"]


def test_hub_cli_refusals(paths: RepoPaths, capsys: pytest.CaptureFixture[str]) -> None:
    config = str(paths.configs_dir / "sft_qwen35_2b.yaml")
    assert hub.main(["push-run", "--config", config, "--seed", "42"]) == hub.EXIT_USAGE
    assert "<hf_user> placeholder" in capsys.readouterr().err
    assert (
        hub.main(["fetch-data", "--repo", "owner/data", "--revision", "a" * 40]) == hub.EXIT_USAGE
    )
    assert "huggingface_hub is not installed" in capsys.readouterr().err
