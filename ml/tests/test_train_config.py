"""Training configs: the §9.5 rules as validators, config_sha, pins (tw_ml.train.config, P3.4)."""

import copy
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from tw_ml.datagen.paths import RepoPaths
from tw_ml.eval.bakeoff_config import load_bakeoff_config
from tw_ml.train.config import (
    SEEDS,
    ConfigError,
    EncoderRunConfig,
    SFTRunConfig,
    canonical_json,
    check_runnable,
    config_sha,
    load_run_config,
    parse_run_config,
    unverified_fields,
)

SFT_FILES = ("sft_qwen35_2b.yaml", "sft_qwen3_1p7b.yaml", "sft_qwen3_4b_2507.yaml")
SHA = "c" * 40


def _document(paths: RepoPaths, name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((paths.configs_dir / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _sft(paths: RepoPaths, name: str = "sft_qwen35_2b.yaml") -> SFTRunConfig:
    config, _ = load_run_config(paths.configs_dir / name)
    assert isinstance(config, SFTRunConfig)
    return config


@pytest.mark.parametrize("name", SFT_FILES)
def test_committed_sft_configs_carry_the_spec_values(paths: RepoPaths, name: str) -> None:
    cfg = _sft(paths, name)
    assert (cfg.precision.fp16, cfg.precision.bf16, cfg.precision.attn_implementation) == (
        True,
        False,
        "sdpa",
    )
    assert (cfg.trust_remote_code, cfg.use_safetensors) == (False, True)
    assert (cfg.lora.r, cfg.lora.alpha, cfg.lora.dropout, cfg.lora.bias) == (16, 32, 0.05, "none")
    assert cfg.lora.target_modules == "all-linear"
    train = cfg.train
    assert (train.lr, train.scheduler, train.warmup_ratio, train.epochs) == (
        2e-4,
        "cosine",
        0.03,
        3,
    )
    assert (train.per_device_batch, train.grad_accum, train.effective_batch) == (4, 8, 32)
    assert train.max_length == 2048
    assert (train.packing, train.padding_free, train.gradient_checkpointing) == (False, False, True)
    assert (train.eval_steps, train.save_steps, train.save_total_limit) == (25, 25, 3)
    assert (train.early_stopping_patience, train.metric_for_best_model) == (4, "eval_loss")
    assert train.loss_type == "chunked_nll"
    assert train.loss_fallback is not None
    assert train.loss_fallback.loss_type == "nll"
    assert (train.generation_eval.max_new_tokens, train.generation_eval.batch_size) == (512, 16)
    assert cfg.seeds == SEEDS == (42, 1337, 2026)
    assert cfg.hub.private
    assert cfg.hub.strategy == "checkpoint"
    assert "{seed}" in cfg.hub.checkpoint_repo
    assert cfg.tracking.report_to == ("mlflow", "codecarbon")
    assert (cfg.platform.hardware, cfg.platform.torch) == ("t4", "2.11")
    assert (cfg.smoke.rows, cfg.smoke.max_peak_memory_gib, cfg.smoke.resume_tolerance) == (
        8,
        13.0,
        1e-3,
    )


def test_method_follows_base_size(paths: RepoPaths) -> None:
    small, fallback, large = (_sft(paths, name) for name in SFT_FILES)
    assert (small.method, small.registry_method, small.quantization) == ("lora_fp16", "lora", None)
    assert small.model_class == "Qwen3_5ForCausalLM"
    assert (fallback.method, fallback.model_class) == ("lora_fp16", "AutoModelForCausalLM")
    assert (large.method, large.registry_method, large.train.optim) == (
        "qlora_nf4",
        "qlora",
        "paged_adamw_8bit",
    )
    assert large.quantization is not None
    quant = large.quantization
    assert (quant.quant_type, quant.double_quant, quant.compute_dtype) == ("nf4", True, "float16")
    assert (small.smoke.max_hours_per_seed, large.smoke.max_hours_per_seed) == (2.0, 4.0)


@pytest.mark.parametrize("name", SFT_FILES)
def test_sft_configs_match_their_bakeoff_candidate(paths: RepoPaths, name: str) -> None:
    cfg = _sft(paths, name)
    bakeoff, _ = load_bakeoff_config(paths.configs_dir / "bakeoff.yaml")
    candidate = next(c for c in bakeoff.candidates if c.hf_repo == cfg.base.repo)
    assert candidate.finetune_method == cfg.method
    assert candidate.params_b == cfg.base.params_b
    assert candidate.license == cfg.base.license
    assert candidate.hf_revision == cfg.base.revision  # one pin, set in both files together
    assert candidate.prompt_format == cfg.data.prompt_format


def test_committed_encoder_config_carries_the_spec_values(paths: RepoPaths) -> None:
    cfg, _ = load_run_config(paths.configs_dir / "encoder_modernbert.yaml")
    assert isinstance(cfg, EncoderRunConfig)
    assert cfg.base.repo == "answerdotai/ModernBERT-base"
    assert cfg.heads == (
        "intent",
        "priority",
        "sentiment",
        "churn_risk",
        "product_area",
        "recommended_queue",
    )
    train = cfg.train
    assert (train.lr, train.per_device_batch, train.epochs, train.max_length) == (3e-5, 32, 5, 512)
    assert (train.warmup_ratio, train.weight_decay) == (0.06, 0.01)
    assert (train.class_weighting, train.best_metric) == ("inverse_sqrt", "intent_macro_f1")
    assert (cfg.precision.fp16, cfg.precision.bf16, cfg.calibration) == (True, False, "temperature")
    assert cfg.seeds == SEEDS
    assert cfg.data.predict_splits == ("val", "hard_dev")


def _mutated(paths: RepoPaths, name: str, change: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(_document(paths, name))
    for dotted, value in change.items():
        *parents, leaf = dotted.split(".")
        target = document
        for key in parents:
            target = target[key]
        if value is DELETE:
            del target[leaf]
        else:
            target[leaf] = value
    return document


DELETE = object()


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"precision.bf16": True}, "precision.bf16"),
        ({"precision.fp16": False}, "precision.fp16"),
        ({"precision.fp16": DELETE}, "precision.fp16"),
        ({"trust_remote_code": True}, "trust_remote_code"),
        ({"use_safetensors": False}, "use_safetensors"),
        ({"seeds": [42, 1337]}, "seeds must be exactly"),
        ({"train.max_length": 1024}, "max_length must be 2048"),
        ({"train.lr": DELETE}, "train.lr"),
        ({"train.warmup_ratio": DELETE}, "train.warmup_ratio"),
        ({"train.save_steps": 30}, "multiple of eval_steps"),
        ({"train.loss_fallback.grad_accum": 8}, "effective batch"),
        ({"train.packing": True}, "train.packing"),
        ({"lora.target_modules": ["q_proj", "lm_head"]}, "never adapt lm_head"),
        ({"lora.target_modules": ["q_proj", "q_proj"]}, "without duplicates"),
        ({"lora.bias": "all"}, "lora.bias"),
        ({"method": "qlora_nf4"}, "trained with lora_fp16"),
        ({"model_class": "AutoModelForCausalLM"}, "loads with Qwen3_5ForCausalLM"),
        ({"precision.attn_implementation": "eager"}, "sdpa"),
        ({"train.optim": "paged_adamw_8bit"}, "uses optim adamw_torch"),
        (
            {
                "quantization": {
                    "load_in_4bit": True,
                    "quant_type": "nf4",
                    "double_quant": True,
                    "compute_dtype": "float16",
                }
            },
            "quantization is set exactly",
        ),
        ({"hub.checkpoint_repo": "<hf_user>/no-seed"}, "{seed} exactly once"),
        ({"hub.checkpoint_repo": "<hf_user>/a-s{seed}-{seed}"}, "{seed} exactly once"),
        ({"hub.checkpoint_repo": "not a repo {seed}"}, "<namespace>/<name>"),
        ({"hub.private": False}, "hub.private"),
        ({"tracking.report_to": ["mlflow"]}, "report_to must be"),
        ({"smoke.max_hours_per_seed": 3.0}, "exceeds the §9.5 budget"),
        ({"base.revision": "main"}, "40-hex commit SHA"),
        ({"unknown_key": 1}, "unknown_key"),
    ],
)
def test_sft_rules_are_validators(paths: RepoPaths, change: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ConfigError, match="is invalid") as caught:
        parse_run_config(_mutated(paths, "sft_qwen35_2b.yaml", change), "sft.yaml")
    assert fragment in str(caught.value)


def test_qlora_rules(paths: RepoPaths) -> None:
    for change, fragment in (
        ({"quantization": None}, "quantization is set exactly"),
        ({"method": "lora_fp16"}, "trained with qlora_nf4"),
        ({"train.optim": "adamw_torch"}, "uses optim paged_adamw_8bit"),
        ({"quantization.compute_dtype": "bfloat16"}, "compute_dtype"),
    ):
        with pytest.raises(ConfigError) as caught:
            parse_run_config(_mutated(paths, "sft_qwen3_4b_2507.yaml", change))
        assert fragment in str(caught.value)


def test_encoder_rules(paths: RepoPaths) -> None:
    for change, fragment in (
        ({"heads": ["intent", "priority"]}, "heads must be"),
        ({"precision.bf16": True}, "precision.bf16"),
        ({"train.lr": DELETE}, "train.lr"),
        ({"seeds": [1, 2, 3]}, "seeds must be exactly"),
    ):
        with pytest.raises(ConfigError) as caught:
            parse_run_config(_mutated(paths, "encoder_modernbert.yaml", change))
        assert fragment in str(caught.value)


def test_config_sha_is_canonical_json(paths: RepoPaths, tmp_path: Path) -> None:
    cfg, sha = load_run_config(paths.configs_dir / "sft_qwen35_2b.yaml")
    assert sha == config_sha(cfg) == hashlib.sha256(canonical_json(cfg).encode()).hexdigest()
    reformatted = tmp_path / "reformatted.yaml"
    document = _document(paths, "sft_qwen35_2b.yaml")
    reformatted.write_text(
        "# a comment\n" + yaml.safe_dump(document, sort_keys=True), encoding="utf-8"
    )
    assert load_run_config(reformatted)[1] == sha  # comments, key order and layout do not matter
    changed = tmp_path / "changed.yaml"
    changed.write_text(
        yaml.safe_dump(_mutated(paths, "sft_qwen35_2b.yaml", {"train.lr": 1e-4})), encoding="utf-8"
    )
    assert load_run_config(changed)[1] != sha


def test_load_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_run_config(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("kind: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_run_config(bad)
    with pytest.raises(ConfigError, match="is invalid"):
        parse_run_config({"kind": "other"})


def test_check_runnable(paths: RepoPaths) -> None:
    cfg = _sft(paths)
    assert unverified_fields(cfg) == ["base.revision", "hub.checkpoint_repo"]
    with pytest.raises(ConfigError, match="not one of the configured seeds"):
        check_runnable(cfg, 7, allow_unverified=True, needs_hub=False)
    with pytest.raises(ConfigError, match="--allow-unverified"):
        check_runnable(cfg, 42, allow_unverified=False, needs_hub=False)
    notes = check_runnable(cfg, 42, allow_unverified=True, needs_hub=False)
    assert len(notes) == 1
    assert notes[0].startswith("UNVERIFIED")
    with pytest.raises(ConfigError, match="HF user name"):
        check_runnable(cfg, 42, allow_unverified=True, needs_hub=True)
    pinned = parse_run_config(
        _mutated(
            paths,
            "sft_qwen35_2b.yaml",
            {"base.revision": SHA, "hub.checkpoint_repo": "owner/tw-triage-s{seed}-ckpt"},
        )
    )
    assert unverified_fields(pinned) == []
    assert check_runnable(pinned, 2026, allow_unverified=False, needs_hub=True) == []
    assert pinned.hub.repo_for(2026) == "owner/tw-triage-s2026-ckpt"
