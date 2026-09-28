"""E4 SFT: the pure argument builders, guards and checkpoint choice (tw_ml.train.sft, P3.6).

Everything here runs without torch, Transformers, PEFT or TRL; the platform code they feed is
exercised by ``python -m tw_ml.train.smoke`` on a T4.
"""

import json
import logging
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.export.prompt_format import TEMPLATE_KWARGS, PromptFormat, derive_prompt_format
from tw_ml.train.config import SFTRunConfig, config_sha, load_run_config
from tw_ml.train.data import IGNORE_INDEX, gold_items, load_training_data
from tw_ml.train.sft import (
    EpochEvaluator,
    EpochRecord,
    LossChoice,
    TokenizationMismatchError,
    TrainingError,
    adapter_saver,
    append_epoch_record,
    batched,
    bnb_kwargs,
    build_with_fallback,
    collator_mask_problems,
    eval_loss_at,
    left_pad,
    lm_head_adapters,
    lora_kwargs,
    loss_choices,
    mismatch_guard,
    model_kwargs,
    prediction_records,
    prepare_data,
    prompt_format_problems,
    read_epoch_records,
    recast_trainable,
    select_final,
    sft_config_kwargs,
    split_completion,
    steps_per_seed,
    stop_token_ids,
    system_id,
    text_only_problems,
    trainable_dtype_problems,
)

SHA = "e" * 64


def _cfg(paths: RepoPaths, name: str = "sft_qwen35_2b.yaml") -> SFTRunConfig:
    config, _ = load_run_config(paths.configs_dir / name)
    assert isinstance(config, SFTRunConfig)
    return config


def test_sft_config_kwargs_write_every_t4_setting(paths: RepoPaths, tmp_path: Path) -> None:
    cfg = _cfg(paths)
    loss = loss_choices(cfg)[0]
    kwargs = sft_config_kwargs(
        cfg, seed=1337, output_dir=tmp_path, run_name="r", hub_repo="owner/ckpt-s1337", loss=loss
    )
    assert kwargs["fp16"] is True
    assert kwargs["bf16"] is False
    assert (kwargs["learning_rate"], kwargs["lr_scheduler_type"], kwargs["warmup_steps"]) == (
        2e-4,
        "cosine",
        0.03,
    )
    assert (kwargs["num_train_epochs"], kwargs["max_length"], kwargs["optim"]) == (
        3,
        2048,
        "adamw_torch",
    )
    assert (kwargs["per_device_train_batch_size"], kwargs["gradient_accumulation_steps"]) == (4, 8)
    assert (kwargs["packing"], kwargs["padding_free"], kwargs["gradient_checkpointing"]) == (
        False,
        False,
        True,
    )
    assert kwargs["gradient_checkpointing_kwargs"] == {"use_reentrant": False}
    assert (kwargs["loss_type"], kwargs["completion_only_loss"]) == ("chunked_nll", True)
    assert (kwargs["eval_steps"], kwargs["save_steps"], kwargs["save_total_limit"]) == (25, 25, 3)
    assert (kwargs["load_best_model_at_end"], kwargs["metric_for_best_model"]) == (
        True,
        "eval_loss",
    )
    assert kwargs["greater_is_better"] is False
    assert kwargs["report_to"] == ["mlflow", "codecarbon"]
    assert (kwargs["seed"], kwargs["data_seed"]) == (1337, 1337)
    assert (kwargs["push_to_hub"], kwargs["hub_model_id"], kwargs["hub_strategy"]) == (
        True,
        "owner/ckpt-s1337",
        "checkpoint",
    )
    assert kwargs["hub_private_repo"] is True
    assert (kwargs["save_only_model"], kwargs["ignore_data_skip"]) == (False, False)
    assert "max_steps" not in kwargs


def test_smoke_and_fallback_kwargs(paths: RepoPaths, tmp_path: Path) -> None:
    cfg = _cfg(paths)
    primary, fallback = loss_choices(cfg)
    assert (fallback.loss_type, fallback.per_device_batch, fallback.grad_accum) == ("nll", 2, 16)
    assert (
        primary.per_device_batch * primary.grad_accum
        == fallback.per_device_batch * fallback.grad_accum
    )
    smoke = sft_config_kwargs(
        cfg,
        seed=42,
        output_dir=tmp_path,
        run_name="s",
        hub_repo=None,
        loss=fallback,
        smoke_steps=20,
    )
    assert (
        smoke["max_steps"],
        smoke["save_steps"],
        smoke["eval_steps"],
        smoke["logging_steps"],
    ) == (
        20,
        10,
        10,
        1,
    )
    assert (smoke["push_to_hub"], smoke["report_to"], smoke["load_best_model_at_end"]) == (
        False,
        "none",
        False,
    )
    assert "hub_model_id" not in smoke
    assert (smoke["loss_type"], smoke["per_device_train_batch_size"]) == ("nll", 2)
    assert (smoke["fp16"], smoke["bf16"]) == (True, False)


def test_model_quantization_and_lora_kwargs(paths: RepoPaths) -> None:
    lora_cfg, qlora_cfg = _cfg(paths), _cfg(paths, "sft_qwen3_4b_2507.yaml")
    assert model_kwargs(lora_cfg, None) == {
        "revision": None,
        "attn_implementation": "sdpa",
        "trust_remote_code": False,
        "use_safetensors": True,
        "device_map": {"": 0},
    }
    assert bnb_kwargs(lora_cfg) is None
    assert bnb_kwargs(qlora_cfg) == {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_use_double_quant": True,
        "bnb_4bit_compute_dtype": "float16",
    }
    assert lora_kwargs(lora_cfg) == {
        "r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "bias": "none",
        "task_type": "CAUSAL_LM",
        "target_modules": "all-linear",
    }
    explicit = lora_cfg.model_copy(
        update={"lora": lora_cfg.lora.model_copy(update={"target_modules": ("q_proj", "v_proj")})}
    )
    assert lora_kwargs(explicit)["target_modules"] == ["q_proj", "v_proj"]
    assert steps_per_seed(3600, lora_cfg) == 339  # 3 x ceil(3600 / 32): the spec's ~338


def test_text_only_and_lm_head_guards() -> None:
    names = ["model.layers.0.linear_attn.in_proj_qkv", "lm_head"]
    assert text_only_problems("Qwen3_5ForCausalLM", "Qwen3_5ForCausalLM", names) == []
    assert text_only_problems("AutoModelForCausalLM", "Qwen3ForCausalLM", names) == []
    problems = text_only_problems(
        "Qwen3_5ForCausalLM", "Qwen3_5ForConditionalGeneration", [*names, "model.visual.blocks.0"]
    )
    assert len(problems) == 3
    assert "non-text modules loaded: model.visual.blocks.0" in problems[2]
    peft = ["base_model.model.lm_head", "base_model.model.model.layers.0.q_proj.lora_A.default"]
    assert lm_head_adapters(peft) == []
    assert lm_head_adapters([*peft, "base_model.model.lm_head.lora_A.default"]) == [
        "base_model.model.lm_head.lora_A.default"
    ]


@dataclass
class FakeTensor:
    dtype: str

    def to(self, dtype: object) -> "FakeTensor":
        return FakeTensor(str(dtype))


@dataclass
class FakeParameter:
    requires_grad: bool
    dtype: str
    data: FakeTensor = field(init=False)

    def __post_init__(self) -> None:
        self.data = FakeTensor(self.dtype)


def test_recast_guard_and_dtype_check() -> None:
    parameters: list[Any] = [  # the protocol's attributes are invariant; fakes are duck-typed
        FakeParameter(True, "torch.bfloat16"),
        FakeParameter(False, "torch.float16"),
        FakeParameter(True, "torch.float32"),
    ]
    assert recast_trainable(parameters, "torch.float32") == 1
    assert parameters[0].data.dtype == "torch.float32"
    assert parameters[1].data.dtype == "torch.float16"  # frozen base weights stay fp16
    assert (
        trainable_dtype_problems([("a", True, "torch.float32"), ("b", False, "torch.float16")])
        == []
    )
    assert trainable_dtype_problems([("a", True, "torch.bfloat16")]) == [
        "trainable parameters are not fp32: a (torch.bfloat16)"
    ]
    assert "no trainable parameters" in trainable_dtype_problems([("a", False, "torch.float16")])[0]


def test_trl_mismatch_warning_is_a_hard_failure() -> None:
    logger = logging.getLogger("trl.trainer.sft_trainer")
    with mismatch_guard():
        logger.warning("unrelated warning")  # other records pass through
        with pytest.raises(TokenizationMismatchError):
            logger.warning(
                "Mismatch between tokenized prompt and the start of tokenized prompt+completion."
            )
        with pytest.raises(UserWarning, match="Mismatch between tokenized prompt"):
            warnings.warn("Mismatch between tokenized prompt", UserWarning, stacklevel=1)
    logger.warning("Mismatch between tokenized prompt, outside the guard")  # removed again
    assert not any(type(h).__name__ == "_MismatchHandler" for h in logging.getLogger().handlers)


def test_collator_mask_check() -> None:
    labels = [[IGNORE_INDEX, IGNORE_INDEX, 7, 8], [IGNORE_INDEX, 9]]
    right = [[IGNORE_INDEX, IGNORE_INDEX, 7, 8], [IGNORE_INDEX, 9, IGNORE_INDEX, IGNORE_INDEX]]
    left = [[IGNORE_INDEX, IGNORE_INDEX, 7, 8], [IGNORE_INDEX, IGNORE_INDEX, IGNORE_INDEX, 9]]
    assert collator_mask_problems(labels, right) == []
    assert collator_mask_problems(labels, left) == []
    unmasked = [[5, 6, 7, 8], [IGNORE_INDEX, 9, IGNORE_INDEX, IGNORE_INDEX]]
    assert collator_mask_problems(labels, unmasked) == [
        "row 0: the collated labels differ from the prompt-masked labels"
    ]


def test_generation_helpers() -> None:
    assert split_completion([5, 6, 2, 3, 3], [2]) == ([5, 6], False)
    assert split_completion([5, 6, 7], [2, 4]) == ([5, 6, 7], True)
    assert left_pad([[1, 2, 3], [4]], 0) == ([[1, 2, 3], [0, 0, 4]], [[1, 1, 1], [0, 0, 1]])
    assert left_pad([], 0) == ([], [])
    assert [list(chunk) for chunk in batched([1, 2, 3, 4, 5], 2)] == [[1, 2], [3, 4], [5]]


def test_prediction_records_use_the_repair_ladder(
    taxonomy: Taxonomy, make_labels: Callable[..., Any]
) -> None:
    valid = make_labels().model_dump_json()
    records = prediction_records(
        ["va_1", "va_2", "va_3", "va_4"],
        [(valid, False), (f"```json\n{valid}\n```", False), (valid[:40], True), (None, False)],
        taxonomy=taxonomy,
        system_id="sys",
    )
    assert [r.validity for r in records] == [
        "first_pass",
        "repaired_l1",
        "failed_fallback",
        "failed_fallback",
    ]
    assert records[0].output == make_labels()
    assert records[2].output is None


def test_epoch_evaluator_scores_saves_and_records(
    tmp_path: Path,
    write_train_data: Callable[..., Path],
    train_paths: Any,
    taxonomy: Taxonomy,
    rules: LabelRules,
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    gold = gold_items(data.val)
    truth = {item.record_id: item.labels.model_dump_json() for item in gold}
    prompts = {item.record_id: [ord(c) for c in item.record_id] for item in gold}

    def generate(model: object, prompts: Any) -> list[tuple[str | None, bool]]:
        del model
        ids = ["".join(chr(t) for t in row) for row in prompts]
        return [(truth[rid], False) for rid in ids]

    saved: list[int] = []
    seen: list[EpochRecord] = []

    def save(model: object, step: int) -> str:
        del model
        saved.append(step)
        return f"epoch_adapters/step-{step}"

    evaluator = EpochEvaluator(
        gold=gold,
        prompts=prompts,
        taxonomy=taxonomy,
        rules=rules,
        system_id="sys",
        generate=generate,
        save_adapter=save,
        on_record=seen.append,
        confusion_dir=tmp_path / "confusion",
    )
    record = evaluator.evaluate(object(), epoch=1.0, step=113)
    assert record.confusion_file == "confusion/intent_step-113.json"
    matrix = json.loads((tmp_path / record.confusion_file).read_text(encoding="utf-8"))
    assert sum(map(sum, matrix["counts"])) == 4
    assert record.macro_f1 is not None
    assert record.json_validity == 1.0
    assert (record.n, record.adapter_dir, saved) == (4, "epoch_adapters/step-113", [113])
    assert seen == [record] == evaluator.records


def test_epoch_records_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "epoch_eval.jsonl"
    assert read_epoch_records(path) == []
    first = EpochRecord(1.0, 113, 0.8, 1.0, 0.9, 450, "epoch_adapters/step-113")
    append_epoch_record(path, first)
    append_epoch_record(path, EpochRecord(2.0, 226, None, None, None, 450))
    assert read_epoch_records(path) == [first, EpochRecord(2.0, 226, None, None, None, 450)]


def test_final_checkpoint_choice() -> None:
    history = [
        {"step": 113, "eval_loss": 0.40},
        {"step": 226, "eval_loss": 0.35},
        {"step": 339, "loss": 0.2},
    ]
    records = [
        EpochRecord(1.0, 113, 0.80, 1.0, 0.9, 450, "a"),
        EpochRecord(2.0, 226, 0.80, 1.0, 0.9, 450, "b"),
        EpochRecord(3.0, 339, 0.70, 1.0, 0.9, 450, "c"),
    ]
    choice = select_final(records, history)
    assert choice is not None
    assert (choice.step, choice.adapter_dir, choice.eval_loss) == (226, "b", 0.35)
    assert "tie broken by lower eval_loss" in choice.reason
    best = select_final([*records, EpochRecord(4.0, 452, 0.9, 1.0, 1.0, 450, "d")], history)
    assert best is not None
    assert (best.step, best.eval_loss, best.reason) == (452, None, "best epoch-end val macro-F1")
    assert select_final([EpochRecord(1.0, 1, None, None, None, 0)], history) is None
    assert eval_loss_at(history, 339) is None


def test_stop_ids_and_prompt_format_checks(
    paths: RepoPaths, make_sft_tokenizer: Callable[..., Any]
) -> None:
    tokenizer = make_sft_tokenizer()
    assert stop_token_ids(tokenizer, ["<|im_end|>", "<|endoftext|>", "multi token stop"]) == [2, 3]
    cfg = _cfg(paths)
    fmt = derive_prompt_format(tokenizer, base_model=cfg.base.repo, base_revision="<verify>")
    assert fmt.template_kwargs == {"add_generation_prompt": True, **TEMPLATE_KWARGS}
    assert prompt_format_problems(fmt, cfg, chat_template_sha256=None) == []
    assert prompt_format_problems(fmt, cfg, chat_template_sha256=fmt.chat_template_sha256) == []
    other: PromptFormat = fmt.model_copy(
        update={"base_model": "Qwen/Qwen3-1.7B", "template_kwargs": {}}
    )
    problems = prompt_format_problems(other, cfg, chat_template_sha256="0" * 64)
    assert len(problems) == 3
    pinned = cfg.model_copy(update={"base": cfg.base.model_copy(update={"revision": "f" * 40})})
    assert prompt_format_problems(fmt, pinned, chat_template_sha256=None) == [
        "prompt format revision differs from base.revision"
    ]


def test_system_id_and_adapter_saver(paths: RepoPaths, tmp_path: Path) -> None:
    cfg = _cfg(paths)
    assert system_id(cfg, SHA, 42) == f"tw-triage-qwen35-2b-lora@sft.v1+{SHA[:12]}-s42"
    saved: list[str] = []

    class FakePeftModel:
        def save_pretrained(self, save_directory: str) -> None:
            saved.append(save_directory)

    save = adapter_saver(tmp_path, tmp_path / "epoch_adapters")
    assert save(FakePeftModel(), 113) == "epoch_adapters/step-113"
    assert saved == [str(tmp_path / "epoch_adapters" / "step-113")]


def test_fallback_rebuilds_on_a_fresh_model(paths: RepoPaths) -> None:
    cfg = _cfg(paths)
    loads: list[int] = []

    def load() -> object:
        loads.append(len(loads))
        return f"model-{len(loads)}"

    def build(choice: LossChoice, model: object) -> object:
        if choice.loss_type == "chunked_nll":
            msg = "chunked_nll is not compatible"
            raise ValueError(msg)
        return (choice.loss_type, model)

    trainer, used, notes = build_with_fallback(cfg, build=build, load=load)
    assert trainer == ("nll", "model-2")
    assert (used.loss_type, used.per_device_batch, used.grad_accum) == ("nll", 2, 16)
    assert notes == ["loss_type chunked_nll did not construct (ValueError)"]

    def never(choice: LossChoice, model: object) -> object:
        raise TypeError(choice.loss_type)

    with pytest.raises(TrainingError, match="nll did not construct"):
        build_with_fallback(cfg, build=never, load=load)


def test_prepare_data_builds_rows_and_manifest(
    paths: RepoPaths,
    write_train_data: Callable[..., Path],
    train_paths: Any,
    make_sft_tokenizer: Callable[..., Any],
) -> None:
    cfg = _cfg(paths)
    tokenizer = make_sft_tokenizer()
    fmt = derive_prompt_format(tokenizer, base_model=cfg.base.repo, base_revision="<verify>")
    # model_copy skips validation: the character-level fake tokenizer needs a larger budget
    long_budget = cfg.model_copy(
        update={"train": cfg.train.model_copy(update={"max_length": 100_000})}
    )
    data, splits, manifest = prepare_data(
        long_budget,
        config_sha(cfg),
        seed=42,
        data_dir=write_train_data(),
        paths=train_paths,
        tokenizer=tokenizer,
        fmt=fmt,
    )
    assert (len(splits["train"].rows), len(splits["val"].rows)) == (6, 4)
    assert manifest.kind == "sft"
    assert manifest.nonce_salt == "sft.v1:sft-qwen35-2b:seed42"
    assert manifest.splits["train"].rows == 6
    assert manifest.splits["val"].file_sha256 == data.val.file_sha256
    assert manifest.rows_sha256 is not None
    assert json.loads(manifest.model_dump_json())["template_kwargs"]["enable_thinking"] is False
