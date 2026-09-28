"""``python -m tw_ml.train``: the torch-free dry run and the refusals before any platform work."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tw_ml.datagen.paths import RepoPaths
from tw_ml.export.prompt_format import derive_prompt_format, write_prompt_format
from tw_ml.train.__main__ import EXIT_OK, EXIT_USAGE, main
from tw_ml.train.config import load_run_config

FORMAT_FILE = "ml/configs/prompt_formats/qwen35-2b.json"


@pytest.fixture
def repo(tmp_path: Path, paths: RepoPaths, train_paths: Any) -> Any:
    """A repository copy with schemas, specs and prompts (prompt formats can be written)."""
    root = tmp_path / "repo"
    shutil.copytree(paths.schemas_dir, root / "schemas" / "json")
    shutil.copytree(paths.spec_dir, root / "data" / "spec")
    shutil.copytree(paths.root / "ml" / "prompts", root / "ml" / "prompts")
    return type(train_paths)(root, train_paths.sandbox)


def _config(tmp_path: Path, paths: RepoPaths, name: str, **data: Any) -> Path:
    document = yaml.safe_load((paths.configs_dir / name).read_text(encoding="utf-8"))
    document["data"].update(data)
    target = tmp_path / name
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return target


def _run(
    argv: list[str], repo_paths: Any, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, Any], str]:
    code = main(argv, paths=repo_paths)
    out, err = capsys.readouterr()
    return code, json.loads(out) if out.strip() else {}, err


def test_sft_dry_run_validates_config_and_data_without_torch(
    tmp_path: Path,
    paths: RepoPaths,
    repo: Any,
    write_train_data: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path, paths, "sft_qwen35_2b.yaml", prompt_format=None)
    argv = [
        "--config",
        str(config),
        "--seed",
        "1337",
        "--data-dir",
        str(write_train_data()),
        "--dry-run",
        "--allow-unverified",
    ]
    code, summary, _ = _run(argv, repo, capsys)
    assert code == EXIT_OK
    assert summary["config_sha"] == load_run_config(config)[1]
    assert (summary["kind"], summary["seed"], summary["blockers"]) == ("sft", 1337, [])
    assert summary["unverified"] == ["base.revision", "hub.checkpoint_repo"]
    assert summary["hub_repo"] == "<hf_user>/tw-triage-qwen35-2b-lora-s1337-ckpt"
    assert summary["notes"][0].startswith("UNVERIFIED")
    sft = summary["sft"]
    assert (sft["training_method"], sft["effective_batch"], sft["optimizer_steps_per_seed"]) == (
        "lora",
        32,
        3,
    )
    assert sft["rendering"]["train"]["rendered"] == 6
    assert sft["rendering"]["val"]["rendered"] == 4
    assert sft["prompt_format"]["status"] == "derived from the tokenizer at run time"
    assert sft["nonce_salt"] == "sft.v1:sft-qwen35-2b:seed1337"
    assert summary["data"]["train"]["generator_families"] == {"openai_gpt_oss": 6}
    assert not (repo.root / "ml" / "outputs").exists()  # a dry run writes nothing


def test_sft_dry_run_checks_the_prompt_format_file(
    tmp_path: Path,
    paths: RepoPaths,
    repo: Any,
    write_train_data: Callable[..., Path],
    make_sft_tokenizer: Callable[..., Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = str(write_train_data())
    config = str(paths.configs_dir / "sft_qwen35_2b.yaml")
    base = [
        "--config",
        config,
        "--seed",
        "42",
        "--data-dir",
        data,
        "--dry-run",
        "--allow-unverified",
    ]
    code, summary, _ = _run(base, repo, capsys)
    assert (
        code == EXIT_USAGE
    )  # the committed config names a prompt format that is not generated yet
    assert summary["sft"]["prompt_format"]["status"] == "missing"
    assert "does not exist" in summary["blockers"][0]
    fmt = derive_prompt_format(
        make_sft_tokenizer(), base_model="Qwen/Qwen3.5-2B", base_revision="<verify>"
    )
    write_prompt_format(repo.root / FORMAT_FILE, fmt)
    code, summary, _ = _run(base, repo, capsys)
    assert code == EXIT_OK
    assert summary["sft"]["prompt_format"]["status"] == "verified"
    write_prompt_format(
        repo.root / FORMAT_FILE, fmt.model_copy(update={"base_model": "Qwen/Qwen3-1.7B"})
    )
    code, summary, _ = _run(base, repo, capsys)
    assert code == EXIT_USAGE
    assert summary["blockers"] == ["prompt format is for Qwen/Qwen3-1.7B, not Qwen/Qwen3.5-2B"]


def test_encoder_dry_run(
    paths: RepoPaths,
    repo: Any,
    write_train_data: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = str(paths.configs_dir / "encoder_modernbert.yaml")
    argv = [
        "--config",
        config,
        "--seed",
        "42",
        "--data-dir",
        str(write_train_data()),
        "--dry-run",
        "--allow-unverified",
    ]
    code, summary, _ = _run(argv, repo, capsys)
    assert code == EXIT_OK
    encoder = summary["encoder"]
    assert list(encoder["heads"]) == [
        "intent",
        "priority",
        "sentiment",
        "churn_risk",
        "product_area",
        "recommended_queue",
    ]
    assert encoder["heads"]["intent"]["classes"] == 13
    assert encoder["predict_splits"] == {"val": "ready", "hard_dev": "no gold file yet"}


def test_refusals_happen_before_any_platform_work(
    tmp_path: Path,
    paths: RepoPaths,
    repo: Any,
    write_train_data: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = str(_config(tmp_path, paths, "sft_qwen35_2b.yaml", prompt_format=None))
    data = str(write_train_data())
    code, _, err = _run(["--config", config, "--seed", "42", "--allow-unverified"], repo, capsys)
    assert code == EXIT_USAGE
    assert "set your HF user name" in err  # a real run never pushes to a placeholder repo
    code, _, err = _run(
        ["--config", config, "--seed", "42", "--data-dir", data, "--dry-run"], repo, capsys
    )
    assert (code, "pass --allow-unverified" in err) == (EXIT_USAGE, True)
    code, _, err = _run(
        ["--config", config, "--seed", "5", "--dry-run", "--allow-unverified"], repo, capsys
    )
    assert (code, "configured seeds" in err) == (EXIT_USAGE, True)
    missing = str(tmp_path / "nothing")
    code, _, err = _run(
        [
            "--config",
            config,
            "--seed",
            "42",
            "--data-dir",
            missing,
            "--dry-run",
            "--allow-unverified",
        ],
        repo,
        capsys,
    )
    assert (code, "train data not found" in err) == (EXIT_USAGE, True)


def test_anthropic_provenance_fails_the_dry_run(
    tmp_path: Path,
    paths: RepoPaths,
    repo: Any,
    write_train_data: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = write_train_data()
    val = root / "val" / "records.jsonl"
    rows = [json.loads(line) for line in val.read_text(encoding="utf-8").splitlines()]
    rows[0]["provenance"]["provider"] = "anthropic"
    val.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    config = str(_config(tmp_path, paths, "sft_qwen35_2b.yaml", prompt_format=None))
    code, _, err = _run(
        [
            "--config",
            config,
            "--seed",
            "42",
            "--data-dir",
            str(root),
            "--dry-run",
            "--allow-unverified",
        ],
        repo,
        capsys,
    )
    assert code == EXIT_USAGE
    assert err.startswith("ProvenanceError")
