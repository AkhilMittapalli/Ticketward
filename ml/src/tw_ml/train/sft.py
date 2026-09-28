"""E4 LoRA/QLoRA SFT with TRL on a T4 (spec v1.1 §9.4-§9.6; ERPROT qlora-training-on-t4; P3.6).

:func:`run` is what ``python -m tw_ml.train --config sft_*.yaml --seed N`` executes on the
platform (Kaggle T4 x2 or Colab T4):

1. the pin check and the platform asserts (the platform's torch 2.11, CUDA, a T4);
2. the tokenizer at the pinned revision, the prompt format (the parity reference), then the
   Option A rows of :mod:`tw_ml.train.data` and the data manifest;
3. the base model in fp16 with SDPA through its text-only class (``Qwen3_5ForCausalLM`` for
   Qwen3.5), or 4-bit NF4 + double quant + ``prepare_model_for_kbit_training`` for QLoRA;
4. ``SFTTrainer`` with LoRA r16/alpha32/0.05 (never ``lm_head``), ``chunked_nll`` (``nll`` with
   the same effective batch when it does not construct), the fp32 re-cast guard for adapter
   weights, early stopping on ``eval_loss`` and the epoch-end generation eval;
5. resume from the Hub ``last-checkpoint/`` when present (logged either way), train, choose the
   final adapter by epoch-end val macro-F1 (ties: lower ``eval_loss``), push the run files.

Pure pieces (argument builders, guards, the checkpoint choice, the generation-eval bookkeeping)
are plain functions tested offline. Everything that needs torch, Transformers, PEFT or TRL
imports it inside the function (``# pragma: no cover``) and runs on the platform, where
``python -m tw_ml.train.smoke`` exercises it before any full run.
"""

import hashlib
import importlib
import json
import logging
import os
import shutil
import time
import warnings
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol, cast

from tw_ml.datagen.labelrules import LABEL_RULES_FILE, LabelRules, load_label_rules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy
from tw_ml.eval.data import GoldItem, PredictionRecord, join
from tw_ml.eval.metrics import EvalSettings, evaluate
from tw_ml.eval.repair import classify_output
from tw_ml.eval.report import git_sha
from tw_ml.export.prompt_format import (
    TEMPLATE_KWARGS,
    PromptFormat,
    derive_prompt_format,
    load_prompt_format,
    verify_goldens,
)
from tw_ml.prompts import PROMPTS_SUBDIR, TriagePrompt, load_triage_prompt
from tw_ml.train.config import SFTRunConfig, check_runnable
from tw_ml.train.data import (
    IGNORE_INDEX,
    DataManifest,
    ParityError,
    SFTRow,
    SFTSplit,
    SFTTokenizer,
    TrainingData,
    build_sft_split,
    check_length_budget,
    gold_items,
    load_training_data,
    nonce_salt,
    rows_sha256,
    split_manifest,
    write_data_manifest,
)
from tw_ml.train.hub import download_resume_state, push_run, resume_decision, upload_path
from tw_ml.train.runtime import (
    GIB,
    RunPaths,
    assert_platform,
    library_versions,
    mlflow_environment,
    run_tags,
    write_json,
)

LOG: Final = logging.getLogger("tw_ml.train.sft")
MISMATCH_TEXT: Final = "Mismatch between tokenized prompt"
"""TRL's prompt/prompt+completion prefix warning, promoted to a hard failure (§9.4)."""
LORA_TASK: Final = "CAUSAL_LM"
NON_TEXT_MARKERS: Final[tuple[str, ...]] = (
    "visual",
    "vision",
    "audio",
    "mm_projector",
    "multi_modal_projector",
)
"""Module-name fragments of vision/audio towers; a text-only load contains none of them."""
GEN_EVAL_RESAMPLES: Final = 200
"""Bootstrap resamples of the in-training eval (only point estimates are used)."""


class TrainingError(RuntimeError):
    """Raised when a training run must stop (guard failures, invalid model state)."""


class TokenizationMismatchError(TrainingError):
    """TRL reported a tokenized-prompt mismatch (never tolerated, spec §9.4)."""


@dataclass(frozen=True, slots=True)
class LossChoice:
    """Loss type with the batch geometry it runs at (the fallback keeps the effective batch)."""

    loss_type: str
    per_device_batch: int
    grad_accum: int


def loss_choices(cfg: SFTRunConfig) -> list[LossChoice]:
    """The configured loss, then its fallback.

    Args:
        cfg: SFT config.

    Returns:
        ``chunked_nll`` at the configured batch, then ``nll`` at the fallback batch (if set).
    """
    train = cfg.train
    choices = [LossChoice(train.loss_type, train.per_device_batch, train.grad_accum)]
    if train.loss_fallback is not None:
        fallback = train.loss_fallback
        choices.append(
            LossChoice(fallback.loss_type, fallback.per_device_batch, fallback.grad_accum)
        )
    return choices


def model_kwargs(cfg: SFTRunConfig, revision: str | None) -> dict[str, object]:
    """``from_pretrained`` keyword arguments (dtype and quantization are added lazily).

    Args:
        cfg: SFT config.
        revision: Pinned commit SHA (``None``: default branch, only with ``--allow-unverified``).

    Returns:
        Revision, SDPA, no remote code, safetensors only, and the whole model on the visible GPU.
    """
    return {
        "revision": revision,
        "attn_implementation": cfg.precision.attn_implementation,
        "trust_remote_code": cfg.trust_remote_code,
        "use_safetensors": cfg.use_safetensors,
        "device_map": {"": 0},
    }


def bnb_kwargs(cfg: SFTRunConfig) -> dict[str, object] | None:
    """``BitsAndBytesConfig`` keyword arguments for QLoRA (``None`` for LoRA on fp16).

    Args:
        cfg: SFT config.

    Returns:
        NF4, double quant and the compute dtype name (resolved to ``torch.float16`` lazily).
    """
    quant = cfg.quantization
    if quant is None:
        return None
    return {
        "load_in_4bit": quant.load_in_4bit,
        "bnb_4bit_quant_type": quant.quant_type,
        "bnb_4bit_use_double_quant": quant.double_quant,
        "bnb_4bit_compute_dtype": quant.compute_dtype,
    }


def lora_kwargs(cfg: SFTRunConfig) -> dict[str, object]:
    """``LoraConfig`` keyword arguments (targets from the config, never ``lm_head``).

    Args:
        cfg: SFT config.

    Returns:
        r, alpha, dropout, bias, task type and target modules.
    """
    lora = cfg.lora
    targets = lora.target_modules
    return {
        "r": lora.r,
        "lora_alpha": lora.alpha,
        "lora_dropout": lora.dropout,
        "bias": lora.bias,
        "task_type": LORA_TASK,
        "target_modules": targets if isinstance(targets, str) else list(targets),
    }


def sft_config_kwargs(
    cfg: SFTRunConfig,
    *,
    seed: int,
    output_dir: Path,
    run_name: str,
    hub_repo: str | None,
    loss: LossChoice,
    smoke_steps: int | None = None,
) -> dict[str, object]:
    """``trl.SFTConfig`` keyword arguments: every §9.5 value set explicitly.

    ``fp16=True, bf16=False`` are always written out (TRL enables bf16 unless fp16 is set, and
    a T4 only emulates bf16). A smoke run (``smoke_steps``) trains that many optimizer steps,
    saves and evaluates halfway, logs every step, and pushes and reports nothing.

    Args:
        cfg: SFT config.
        seed: Seed (also the data-order seed).
        output_dir: Trainer output folder.
        run_name: MLflow run name.
        hub_repo: Private checkpoint repo, or ``None`` for no pushes.
        loss: Loss type and batch geometry.
        smoke_steps: Optimizer steps of a smoke run (``None`` for a full run).

    Returns:
        The keyword arguments.
    """
    train, smoke = cfg.train, smoke_steps is not None
    save_steps = max(1, smoke_steps // 2) if smoke_steps is not None else train.save_steps
    kwargs: dict[str, object] = {
        "output_dir": str(output_dir),
        "run_name": run_name,
        "seed": seed,
        "data_seed": seed,
        "num_train_epochs": train.epochs,
        "per_device_train_batch_size": loss.per_device_batch,
        "per_device_eval_batch_size": train.per_device_eval_batch,
        "gradient_accumulation_steps": loss.grad_accum,
        "learning_rate": train.lr,
        "lr_scheduler_type": train.scheduler,
        "warmup_steps": train.warmup_ratio,
        "optim": train.optim,
        "fp16": cfg.precision.fp16,
        "bf16": cfg.precision.bf16,
        "gradient_checkpointing": train.gradient_checkpointing,
        "gradient_checkpointing_kwargs": {"use_reentrant": False},
        "max_length": train.max_length,
        "packing": train.packing,
        "padding_free": train.padding_free,
        "completion_only_loss": True,
        "assistant_only_loss": False,
        "loss_type": loss.loss_type,
        "eval_strategy": "steps",
        "eval_steps": save_steps if smoke else train.eval_steps,
        "save_strategy": "steps",
        "save_steps": save_steps,
        "save_total_limit": train.save_total_limit,
        "save_only_model": False,
        "load_best_model_at_end": not smoke,
        "metric_for_best_model": train.metric_for_best_model,
        "greater_is_better": False,
        "logging_steps": 1 if smoke else train.logging_steps,
        "report_to": "none" if smoke else list(cfg.tracking.report_to),
        "ignore_data_skip": False,
        "push_to_hub": hub_repo is not None,
    }
    if hub_repo is not None:
        kwargs["hub_model_id"] = hub_repo
        kwargs["hub_strategy"] = cfg.hub.strategy
        kwargs["hub_private_repo"] = cfg.hub.private
    if smoke_steps is not None:
        kwargs["max_steps"] = smoke_steps
    return kwargs


def steps_per_seed(n_rows: int, cfg: SFTRunConfig) -> int:
    """Optimizer steps of one full run on one GPU (~338 for 3,600 rows at batch 32 x 3).

    Args:
        n_rows: Training rows.
        cfg: SFT config.

    Returns:
        ``epochs x ceil(rows / effective batch)``.
    """
    return cfg.train.epochs * -(-n_rows // cfg.train.effective_batch)


# --------------------------------------------------------------------------- model-state guards


def text_only_problems(
    expected_class: str, class_name: str, module_names: Iterable[str]
) -> list[str]:
    """Check that a text-only causal LM was loaded (no vision or audio tower).

    Args:
        expected_class: ``model_class`` of the config.
        class_name: Class of the loaded model.
        module_names: ``named_modules()`` names.

    Returns:
        Problems; empty for a text-only load.
    """
    problems: list[str] = []
    if expected_class not in {"AutoModelForCausalLM", class_name}:
        problems.append(f"loaded {class_name}, expected {expected_class}")
    if not class_name.endswith("ForCausalLM"):
        problems.append(f"{class_name} is not a causal-LM class")
    hits = sorted({n for n in module_names if any(m in n.lower() for m in NON_TEXT_MARKERS)})
    if hits:
        problems.append(f"non-text modules loaded: {', '.join(hits[:3])}")
    return problems


def lm_head_adapters(module_names: Iterable[str]) -> list[str]:
    """LoRA modules attached to ``lm_head`` (must be none: chunked_nll and §9.5).

    Args:
        module_names: ``named_modules()`` names of the PEFT model.

    Returns:
        The offending names.
    """
    return sorted(n for n in module_names if ".lm_head." in f".{n}." and ".lora_" in f".{n}")


class _Tensor(Protocol):
    def to(self, dtype: object) -> "_Tensor": ...


class _Parameter(Protocol):
    requires_grad: bool
    dtype: object
    data: _Tensor


def recast_trainable(parameters: Iterable[_Parameter], dtype: object) -> int:
    """Re-cast trainable parameters to ``dtype`` (fp32) in place.

    TRL >= 0.26 casts the trainable adapter weights of quantized models to bf16, which is unsafe
    on a T4 under fp16 AMP; this runs after trainer init and before the optimizer exists.

    Args:
        parameters: Model parameters.
        dtype: Target dtype (``torch.float32``).

    Returns:
        How many parameters were re-cast.
    """
    changed = 0
    for parameter in parameters:
        if parameter.requires_grad and parameter.dtype != dtype:
            parameter.data = parameter.data.to(dtype)
            changed += 1
    return changed


def trainable_dtype_problems(parameters: Iterable[tuple[str, bool, str]]) -> list[str]:
    """Check that every trainable parameter is fp32 and that some are trainable.

    Args:
        parameters: ``(name, requires_grad, str(dtype))`` triples.

    Returns:
        Problems; empty when the adapter trains in fp32.
    """
    trainable = [(name, dtype) for name, requires_grad, dtype in parameters if requires_grad]
    if not trainable:
        return ["no trainable parameters (the LoRA adapter was not applied)"]
    wrong = [f"{name} ({dtype})" for name, dtype in trainable if dtype != "torch.float32"]
    return [f"trainable parameters are not fp32: {', '.join(wrong[:3])}"] if wrong else []


# --------------------------------------------------------------------------- TRL mismatch guard


class _MismatchHandler(logging.Handler):
    """Raises on TRL's tokenized-prompt mismatch record instead of letting it pass as a log."""

    def emit(self, record: logging.LogRecord) -> None:
        if MISMATCH_TEXT in record.getMessage():
            msg = f"TRL reported a tokenization mismatch ({record.name}); see spec §9.4"
            raise TokenizationMismatchError(msg)


@contextmanager
def mismatch_guard() -> Iterator[None]:
    """Turn TRL's "Mismatch between tokenized prompt" warning into a hard failure.

    The warning is caught as a log record (on the ``trl`` logger and the root logger) and as a
    Python warning. Option A rows are pre-tokenized, so TRL never re-tokenizes them; the guard
    catches a regression that would silently train on misaligned labels.

    Yields:
        Nothing; the guard is active inside the ``with`` block.
    """
    handler = _MismatchHandler(level=logging.WARNING)
    loggers = (logging.getLogger("trl"), logging.getLogger())
    for logger in loggers:
        logger.addHandler(handler)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("error", message=f".*{MISMATCH_TEXT}.*")
            yield
    finally:
        for logger in loggers:
            logger.removeHandler(handler)


def collator_mask_problems(
    expected: Sequence[Sequence[int]], collated: Sequence[Sequence[int]]
) -> list[str]:
    """Check that the trainer's collator kept the Option A loss mask.

    Args:
        expected: The rows' ``labels`` (prompt tokens at -100).
        collated: ``labels`` of the collated batch (padded with -100, either side).

    Returns:
        Problems; empty when every row's labels survive unchanged apart from padding.
    """
    problems = []
    for index, (want, got) in enumerate(zip(expected, collated, strict=True)):
        width, size = len(got), len(want)
        right, left = list(got[:size]), list(got[width - size :])
        pad_right, pad_left = got[size:], got[: width - size]
        kept = (right == list(want) and all(v == IGNORE_INDEX for v in pad_right)) or (
            left == list(want) and all(v == IGNORE_INDEX for v in pad_left)
        )
        if not kept:
            problems.append(
                f"row {index}: the collated labels differ from the prompt-masked labels"
            )
    return problems


# --------------------------------------------------------------------------- generation eval


def split_completion(token_ids: Sequence[int], stop_ids: Iterable[int]) -> tuple[list[int], bool]:
    """Cut generated tokens at the first stop token.

    Args:
        token_ids: New tokens of one row (padding after a stop is ignored).
        stop_ids: EOS and turn-terminator ids.

    Returns:
        ``(tokens before the stop, truncated)``; truncated means no stop token was generated.
    """
    stops = set(stop_ids)
    for index, token in enumerate(token_ids):
        if token in stops:
            return list(token_ids[:index]), False
    return list(token_ids), True


def left_pad(
    batch: Sequence[Sequence[int]], pad_id: int
) -> tuple[list[list[int]], list[list[int]]]:
    """Left-pad prompts for batched decoder-only generation.

    Args:
        batch: Prompt token ids.
        pad_id: Padding token id.

    Returns:
        ``(input_ids, attention_mask)``.
    """
    width = max((len(ids) for ids in batch), default=0)
    ids = [[pad_id] * (width - len(row)) + list(row) for row in batch]
    mask = [[0] * (width - len(row)) + [1] * len(row) for row in batch]
    return ids, mask


def batched[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """Consecutive chunks of ``size`` items (the last may be shorter).

    Args:
        items: A sequence.
        size: Chunk size (>= 1).

    Yields:
        The chunks.
    """
    for start in range(0, len(items), size):
        yield items[start : start + size]


def prediction_records(
    record_ids: Sequence[str],
    completions: Sequence[tuple[str | None, bool]],
    *,
    taxonomy: Taxonomy,
    system_id: str,
) -> list[PredictionRecord]:
    """``prediction.v1`` records of generated completions (strict parse, then repair level 1).

    Args:
        record_ids: Record ids, aligned with ``completions``.
        completions: ``(text, truncated)`` per record.
        taxonomy: Taxonomy (enum vocabularies of the repair).
        system_id: System id of the run.

    Returns:
        One record per completion.
    """
    records = []
    for record_id, (text, truncated) in zip(record_ids, completions, strict=True):
        outcome = classify_output(text, truncated=truncated, taxonomy=taxonomy)
        records.append(
            PredictionRecord(
                record_id=record_id,
                system_id=system_id,
                validity=outcome.validity,
                output=outcome.labels,
            )
        )
    return records


@dataclass(frozen=True, slots=True)
class EpochRecord:
    """The generation eval at one epoch end.

    Attributes:
        epoch: Trainer epoch (float, 1.0 at the end of the first epoch).
        step: Global optimizer step.
        macro_f1: Val intent macro-F1 over the 12 intents (M-01 semantics).
        json_validity: Val JSON validity (first pass + repaired, M-04 semantics).
        critical_recall: Val pooled critical recall, model level (M-03c).
        n: Val records evaluated.
        adapter_dir: Folder of the adapter saved at this epoch end (relative to the run folder).
        confusion_file: Intent confusion matrix of this evaluation (relative to the run folder).
    """

    epoch: float
    step: int
    macro_f1: float | None
    json_validity: float | None
    critical_recall: float | None
    n: int
    adapter_dir: str | None = None
    confusion_file: str | None = None


class GenerateFn(Protocol):
    """Greedy generation over prompt token ids (the platform implementation uses the model)."""

    def __call__(
        self, model: object, prompts: Sequence[Sequence[int]]
    ) -> list[tuple[str | None, bool]]:
        """Return ``(completion text, truncated)`` per prompt."""


@dataclass
class EpochEvaluator:
    """Epoch-end greedy val evaluation with ``tw_ml.eval`` metrics and the repair ladder.

    Attributes:
        gold: Val gold items.
        prompts: Prompt token ids per record id (every val record).
        taxonomy: Taxonomy.
        rules: Label rules (critical set).
        system_id: System id recorded in the predictions.
        generate: Greedy generation.
        save_adapter: Saves the adapter at an epoch end and returns its folder name.
        on_record: Called with each new record (MLflow metrics, JSONL, Hub upload).
        records: Records so far (restored from ``epoch_eval.jsonl`` on resume).
        confusion_dir: Folder for the per-epoch intent confusion matrices (``None``: not kept).
    """

    gold: Sequence[GoldItem]
    prompts: Mapping[str, Sequence[int]]
    taxonomy: Taxonomy
    rules: LabelRules
    system_id: str
    generate: GenerateFn
    save_adapter: Callable[[object, int], str] | None = None
    on_record: Callable[[EpochRecord], None] | None = None
    records: list[EpochRecord] = field(default_factory=list)
    confusion_dir: Path | None = None

    def evaluate(self, model: object, *, epoch: float, step: int) -> EpochRecord:
        """Generate for every val record, score, save the adapter and record the result.

        Args:
            model: The model being trained (switched to eval mode by ``generate``).
            epoch: Trainer epoch.
            step: Global step.

        Returns:
            The new record.
        """
        record_ids = [item.record_id for item in self.gold]
        completions = self.generate(model, [self.prompts[rid] for rid in record_ids])
        predictions = prediction_records(
            record_ids, completions, taxonomy=self.taxonomy, system_id=self.system_id
        )
        suite = evaluate(
            join(self.gold, predictions),
            self.taxonomy,
            self.rules,
            EvalSettings(n_resamples=GEN_EVAL_RESAMPLES),
        )
        adapter = self.save_adapter(model, step) if self.save_adapter is not None else None
        confusion = None
        matrix = suite.confusion.get("intent")
        if self.confusion_dir is not None and matrix is not None:
            target = write_json(self.confusion_dir / f"intent_step-{step}.json", asdict(matrix))
            confusion = f"{self.confusion_dir.name}/{target.name}"
        record = EpochRecord(
            epoch=epoch,
            step=step,
            macro_f1=suite.point("M-01.intent_macro_f1"),
            json_validity=suite.point("M-04.json_validity"),
            critical_recall=suite.point("M-03c.model.pooled_recall"),
            n=len(predictions),
            adapter_dir=adapter,
            confusion_file=confusion,
        )
        self.records.append(record)
        if self.on_record is not None:
            self.on_record(record)
        return record


def read_epoch_records(path: Path) -> list[EpochRecord]:
    """Epoch records of an earlier session (``epoch_eval.jsonl``; empty when absent).

    Args:
        path: The JSONL file.

    Returns:
        The records in file order.
    """
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [EpochRecord(**json.loads(line)) for line in lines if line.strip()]


def append_epoch_record(path: Path, record: EpochRecord) -> None:
    """Append one record to ``epoch_eval.jsonl``.

    Args:
        path: The JSONL file.
        record: The record.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")


@dataclass(frozen=True, slots=True)
class Selection:
    """The final checkpoint: best epoch-end val macro-F1, ties to the lower ``eval_loss``."""

    epoch: float
    step: int
    macro_f1: float
    eval_loss: float | None
    adapter_dir: str | None
    reason: str


def eval_loss_at(log_history: Sequence[Mapping[str, object]], step: int) -> float | None:
    """The ``eval_loss`` logged at a step (the forced epoch-end evaluation).

    Args:
        log_history: ``trainer.state.log_history``.
        step: Global step.

    Returns:
        The loss, or ``None`` when no evaluation was logged at that step.
    """
    for entry in reversed(log_history):
        loss = entry.get("eval_loss")
        if entry.get("step") == step and isinstance(loss, int | float):
            return float(loss)
    return None


def select_final(
    records: Sequence[EpochRecord], log_history: Sequence[Mapping[str, object]]
) -> Selection | None:
    """Pick the final checkpoint among the epoch-end ones (spec §9.5).

    Args:
        records: Epoch-end generation-eval records.
        log_history: ``trainer.state.log_history`` (for the tie-breaking ``eval_loss``).

    Returns:
        The choice, or ``None`` when no epoch produced a macro-F1.
    """
    scored = [
        (record, eval_loss_at(log_history, record.step))
        for record in records
        if record.macro_f1 is not None
    ]
    if not scored:
        return None
    best, loss = min(
        scored,
        key=lambda pair: (
            -(pair[0].macro_f1 or 0.0),
            pair[1] if pair[1] is not None else float("inf"),
            pair[0].step,
        ),
    )
    ties = sum(1 for record, _ in scored if record.macro_f1 == best.macro_f1)
    reason = "best epoch-end val macro-F1" + (
        " (tie broken by lower eval_loss)" if ties > 1 else ""
    )
    return Selection(best.epoch, best.step, best.macro_f1 or 0.0, loss, best.adapter_dir, reason)


def stop_token_ids(tokenizer: SFTTokenizer, stops: Sequence[str]) -> list[int]:
    """Token ids that end a generation: EOS first, then every single-token stop string.

    Args:
        tokenizer: Base-model tokenizer.
        stops: ``PromptFormat.stop``.

    Returns:
        Unique ids (multi-token stop strings cannot stop ``generate`` and are skipped).
    """
    ids = [tokenizer.eos_token_id] if tokenizer.eos_token_id is not None else []
    for stop in stops:
        encoded = tokenizer.encode(stop, add_special_tokens=False)
        if len(encoded) == 1:
            ids.append(encoded[0])
    return list(dict.fromkeys(ids))


def prompt_format_problems(
    fmt: PromptFormat, cfg: SFTRunConfig, *, chat_template_sha256: str | None
) -> list[str]:
    """Check a committed ``prompt_format.json`` against the config and the loaded tokenizer.

    Args:
        fmt: The prompt format (goldens already verified).
        cfg: SFT config.
        chat_template_sha256: SHA-256 of the loaded tokenizer's chat template (``None`` in a
            dry run, which has no tokenizer).

    Returns:
        Problems; empty when the file describes this base model at this revision.
    """
    problems = []
    if fmt.base_model != cfg.base.repo:
        problems.append(f"prompt format is for {fmt.base_model}, not {cfg.base.repo}")
    if cfg.base.pinned and fmt.base_revision != cfg.base.revision:
        problems.append("prompt format revision differs from base.revision")
    if fmt.template_kwargs != {"add_generation_prompt": True, **TEMPLATE_KWARGS}:
        problems.append("prompt format template_kwargs differ from the fixed TEMPLATE_KWARGS")
    if chat_template_sha256 is not None and fmt.chat_template_sha256 != chat_template_sha256:
        problems.append("the tokenizer's chat template differs from the prompt format's")
    return problems


def system_id(cfg: SFTRunConfig, config_sha: str, seed: int) -> str:
    """System id of a training run's predictions (``tw-triage-<name>@<version>+<sha>-s<seed>``).

    Args:
        cfg: SFT config.
        config_sha: ``config_sha``.
        seed: Seed.

    Returns:
        The id.
    """
    base = cfg.name.removeprefix("sft-")
    return f"tw-triage-{base}-{cfg.registry_method}@{cfg.version}+{config_sha[:12]}-s{seed}"


class _Saveable(Protocol):
    def save_pretrained(self, save_directory: str) -> object: ...


def adapter_saver(root: Path, folder: Path) -> Callable[[object, int], str]:
    """Save the adapter at an epoch end (``save_pretrained`` of the PEFT model).

    Args:
        root: The run folder (returned paths are relative to it).
        folder: Parent folder of the epoch adapters.

    Returns:
        ``save(model, step) -> relative folder``.
    """

    def save(model: object, step: int) -> str:
        target = folder / f"step-{step}"
        cast("_Saveable", model).save_pretrained(str(target))
        return target.relative_to(root).as_posix()

    return save


# --------------------------------------------------------------------------- platform (lazy)
# Everything below needs torch/Transformers/PEFT/TRL and runs only on Kaggle/Colab. The smoke
# test (python -m tw_ml.train.smoke) exercises it end to end before any full run.


def load_tokenizer(cfg: SFTRunConfig) -> SFTTokenizer:  # pragma: no cover - needs transformers
    """The base tokenizer at the pinned revision (no remote code; pad = EOS when unset).

    Args:
        cfg: SFT config.

    Returns:
        The tokenizer.
    """
    from transformers import AutoTokenizer  # noqa: PLC0415 - platform-only dependency

    tokenizer: Any = AutoTokenizer.from_pretrained(
        cfg.base.repo, revision=revision_of(cfg), trust_remote_code=cfg.trust_remote_code
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    loaded: SFTTokenizer = tokenizer
    return loaded


def revision_of(cfg: SFTRunConfig) -> str | None:
    """The revision to load: the pinned SHA, or ``None`` (default branch) when unverified.

    Args:
        cfg: SFT config.

    Returns:
        The revision argument.
    """
    return cfg.base.revision if cfg.base.pinned else None


def load_model(cfg: SFTRunConfig) -> object:  # pragma: no cover - needs torch + transformers
    """Load the base model: fp16 + SDPA, or NF4 for QLoRA, through its text-only class.

    Args:
        cfg: SFT config.

    Returns:
        The model (``prepare_model_for_kbit_training`` applied for QLoRA).

    Raises:
        TrainingError: If the loaded model is not a text-only causal LM.
    """
    import torch  # noqa: PLC0415
    import transformers  # noqa: PLC0415

    kwargs: dict[str, object] = {**model_kwargs(cfg, revision_of(cfg)), "dtype": torch.float16}
    quant = bnb_kwargs(cfg)
    if quant is not None:
        quant["bnb_4bit_compute_dtype"] = getattr(torch, str(quant["bnb_4bit_compute_dtype"]))
        kwargs["quantization_config"] = transformers.BitsAndBytesConfig(**quant)
    model: Any = getattr(transformers, cfg.model_class).from_pretrained(cfg.base.repo, **kwargs)
    names = [name for name, _ in model.named_modules()]
    problems = text_only_problems(cfg.model_class, type(model).__name__, names)
    if problems:
        raise TrainingError("; ".join(problems))
    model.config.use_cache = False
    if quant is not None:
        from peft import prepare_model_for_kbit_training  # noqa: PLC0415

        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
        )
    loaded: object = model
    return loaded


def build_trainer(  # noqa: PLR0913 - keyword-only: one argument per trainer input
    cfg: SFTRunConfig,
    *,
    model: object,
    tokenizer: SFTTokenizer,
    train_rows: Sequence[SFTRow],
    val_rows: Sequence[SFTRow],
    seed: int,
    output_dir: Path,
    run_name: str,
    hub_repo: str | None,
    loss: LossChoice,
    callbacks: Sequence[object] = (),
    smoke_steps: int | None = None,
) -> object:  # pragma: no cover - needs trl + peft + datasets
    """Build ``SFTTrainer`` with the LoRA config, then apply and check the fp32 guard.

    Args:
        cfg: SFT config.
        model: Base model from :func:`load_model`.
        tokenizer: Tokenizer.
        train_rows: Option A train rows.
        val_rows: Option A val rows (``eval_loss``).
        seed: Seed.
        output_dir: Trainer output folder.
        run_name: MLflow run name.
        hub_repo: Checkpoint repo, or ``None`` for no pushes.
        loss: Loss choice.
        callbacks: Trainer callbacks.
        smoke_steps: Optimizer steps of a smoke run.

    Returns:
        The trainer.

    Raises:
        TrainingError: If a trainable parameter is not fp32, LoRA sits on ``lm_head`` or the
            collator changed the loss mask.
    """
    import torch  # noqa: PLC0415
    from datasets import Dataset  # noqa: PLC0415
    from peft import LoraConfig  # noqa: PLC0415
    from trl import SFTConfig, SFTTrainer  # noqa: PLC0415

    args = SFTConfig(
        **sft_config_kwargs(
            cfg,
            seed=seed,
            output_dir=output_dir,
            run_name=run_name,
            hub_repo=hub_repo,
            loss=loss,
            smoke_steps=smoke_steps,
        )
    )
    trainer: Any = SFTTrainer(
        model=model,
        args=args,
        train_dataset=Dataset.from_list([row.features() for row in train_rows]),
        eval_dataset=Dataset.from_list([row.features() for row in val_rows]),
        processing_class=tokenizer,
        peft_config=LoraConfig(**lora_kwargs(cfg)),
        callbacks=list(callbacks),
    )
    recast = recast_trainable(trainer.model.parameters(), torch.float32)
    LOG.info("fp32 guard re-cast %d trainable parameters", recast)
    parameters = [(n, p.requires_grad, str(p.dtype)) for n, p in trainer.model.named_parameters()]
    problems = trainable_dtype_problems(parameters)
    modules = [name for name, _ in trainer.model.named_modules()]
    problems += [f"LoRA on lm_head: {name}" for name in lm_head_adapters(modules)]
    count = min(2, len(train_rows))
    collated = trainer.data_collator([trainer.train_dataset[i] for i in range(count)])
    expected = [row.labels for row in train_rows[:count]]
    problems += collator_mask_problems(expected, collated["labels"].tolist())
    if problems:
        raise TrainingError("; ".join(problems))
    built: object = trainer
    return built


def build_with_fallback(
    cfg: SFTRunConfig, *, build: Callable[[LossChoice, object], object], load: Callable[[], object]
) -> tuple[object, LossChoice, list[str]]:
    """Build the trainer with the configured loss, else with its fallback on a fresh model.

    A failed ``SFTTrainer`` init may already have injected LoRA layers into the model, so the
    fallback always starts from a newly loaded base.

    Args:
        cfg: SFT config.
        build: ``build(loss, model) -> trainer``.
        load: Loads a fresh base model.

    Returns:
        ``(trainer, loss used, notes)``.

    Raises:
        TrainingError: If no loss choice constructs.
    """
    notes: list[str] = []
    for index, choice in enumerate(loss_choices(cfg)):
        try:
            return build(choice, load()), choice, notes
        except (TypeError, ValueError, NotImplementedError) as exc:
            notes.append(f"loss_type {choice.loss_type} did not construct ({type(exc).__name__})")
            LOG.warning(notes[-1])
            if index == len(loss_choices(cfg)) - 1:
                raise TrainingError("; ".join(notes)) from exc
    msg = "no loss choice configured"  # pragma: no cover - the config always has one
    raise TrainingError(msg)  # pragma: no cover


def make_generate(
    tokenizer: SFTTokenizer, *, batch_size: int, max_new_tokens: int, stop_ids: Sequence[int]
) -> GenerateFn:  # pragma: no cover - needs torch + transformers
    """Greedy batched generation (left padding, KV cache on, fp16 autocast, T = 0).

    Args:
        tokenizer: Tokenizer (decoding and the pad id).
        batch_size: Prompts per ``generate`` call.
        max_new_tokens: Token budget per completion.
        stop_ids: EOS and turn-terminator ids.

    Returns:
        The generation function used by :class:`EpochEvaluator`.
    """
    import torch  # noqa: PLC0415
    from transformers import GenerationConfig  # noqa: PLC0415

    tok: Any = tokenizer
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else stop_ids[0]
    config = GenerationConfig(
        do_sample=False,
        max_new_tokens=max_new_tokens,
        eos_token_id=list(stop_ids),
        pad_token_id=pad_id,
    )

    def generate(model: object, prompts: Sequence[Sequence[int]]) -> list[tuple[str | None, bool]]:
        net: Any = model
        was_training, use_cache = net.training, net.config.use_cache
        net.eval()
        net.config.use_cache = True
        completions: list[tuple[str | None, bool]] = []
        try:
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
                for chunk in batched(prompts, batch_size):
                    ids, mask = left_pad(chunk, pad_id)
                    input_ids = torch.tensor(ids, device=net.device)
                    output = net.generate(
                        input_ids=input_ids,
                        attention_mask=torch.tensor(mask, device=net.device),
                        generation_config=config,
                    )
                    for row in output[:, input_ids.shape[1] :].tolist():
                        kept, truncated = split_completion(row, stop_ids)
                        completions.append((tok.decode(kept, skip_special_tokens=False), truncated))
        finally:
            net.config.use_cache = use_cache
            if was_training:
                net.train()
        return completions

    return generate


def epoch_callbacks(
    cfg: SFTRunConfig, evaluator: EpochEvaluator
) -> list[object]:  # pragma: no cover - needs transformers
    """Early stopping on ``eval_loss`` (patience 4) and the epoch-end generation eval.

    The generation callback forces an evaluation and a save at every epoch end, so each
    epoch-end state has an ``eval_loss`` (tie-break) and a pushed checkpoint.

    Args:
        cfg: SFT config.
        evaluator: The epoch evaluator.

    Returns:
        The callbacks.
    """
    from transformers import EarlyStoppingCallback, TrainerCallback  # noqa: PLC0415

    class GenerationEvalCallback(TrainerCallback):  # type: ignore[misc] # untyped base (transformers)
        def on_epoch_end(
            self, args: object, state: object, control: object, **kwargs: object
        ) -> object:
            del args
            status: Any = state
            flow: Any = control
            evaluator.evaluate(
                kwargs["model"], epoch=float(status.epoch or 0.0), step=int(status.global_step)
            )
            flow.should_evaluate = True
            flow.should_save = True
            return flow

    patience = cfg.train.early_stopping_patience
    return [EarlyStoppingCallback(early_stopping_patience=patience), GenerationEvalCallback()]


def epoch_hooks(
    run: RunPaths, repo: str | None
) -> Callable[[EpochRecord], None]:  # pragma: no cover
    """Persist, log and upload each epoch record (Hub uploads are best effort mid-run).

    Args:
        run: The run folder.
        repo: The checkpoint repo (``None``: no uploads).

    Returns:
        The ``on_record`` hook.
    """
    mlflow: Any = importlib.import_module("mlflow")

    def hook(record: EpochRecord) -> None:
        append_epoch_record(run.epoch_eval, record)
        metrics = {
            "gen_val_macro_f1": record.macro_f1,
            "gen_val_json_validity": record.json_validity,
            "gen_val_critical_recall": record.critical_recall,
        }
        if mlflow.active_run() is not None:
            mlflow.log_metrics(
                {k: v for k, v in metrics.items() if v is not None}, step=record.step
            )
            if record.confusion_file is not None:
                mlflow.log_artifact(str(run.root / record.confusion_file), "confusion")
        LOG.info("epoch %.2f step %d: %s", record.epoch, record.step, metrics)
        if repo is None:
            return
        paths = [run.epoch_eval, run.mlruns] + (
            [run.root / record.adapter_dir] if record.adapter_dir else []
        )
        for path in paths:
            try:
                upload_path(
                    repo, path, path.relative_to(run.root).as_posix(), f"epoch {record.epoch:.0f}"
                )
            except Exception as exc:
                LOG.warning(
                    "Hub upload of %s failed (%s); the end-of-run push retries",
                    path.name,
                    type(exc).__name__,
                )

    return hook


def resolve_prompt_format(
    cfg: SFTRunConfig, tokenizer: SFTTokenizer, root: Path
) -> PromptFormat:  # pragma: no cover - needs a real tokenizer
    """The parity reference: the committed prompt format (checked), else a fresh derivation.

    Args:
        cfg: SFT config.
        tokenizer: Loaded tokenizer.
        root: Repository root (``data.prompt_format`` is relative to it).

    Returns:
        The prompt format.

    Raises:
        ParityError: If the committed file does not match this base model and tokenizer.
    """
    tok: Any = tokenizer
    if cfg.data.prompt_format is None:
        return derive_prompt_format(tok, base_model=cfg.base.repo, base_revision=cfg.base.revision)
    fmt = load_prompt_format(root / cfg.data.prompt_format)
    verify_goldens(fmt)
    template_sha = hashlib.sha256(str(tok.chat_template).encode("utf-8")).hexdigest()
    problems = prompt_format_problems(fmt, cfg, chat_template_sha256=template_sha)
    if problems:
        raise ParityError("; ".join(problems))
    return fmt


def _manifest(
    cfg: SFTRunConfig,
    config_sha: str,
    *,
    seed: int,
    data: TrainingData,
    splits: Mapping[str, SFTSplit],
    context: tuple[str, TriagePrompt, PromptFormat],
) -> DataManifest:
    salt, prompt, fmt = context
    return DataManifest(
        kind="sft",
        config_sha=config_sha,
        seed=seed,
        base_model=cfg.base.repo,
        base_revision=cfg.base.revision,
        max_length=cfg.train.max_length,
        nonce_salt=salt,
        prompt_version=prompt.version,
        prompt_sha256=prompt.prompt_sha256,
        chat_template_sha256=fmt.chat_template_sha256,
        template_kwargs=dict(fmt.template_kwargs),
        splits={
            part.split: split_manifest(
                part,
                data.committed_manifests.get(part.split),
                rows=len(splits[part.split].rows),
                rejected=splits[part.split].rejected_over_length,
                token_stats=asdict(splits[part.split].stats),
            )
            for part in (data.train, data.val)
        },
        rows_sha256=rows_sha256([*splits["train"].rows, *splits["val"].rows]),
    )


def prepare_data(
    cfg: SFTRunConfig,
    config_sha: str,
    *,
    seed: int,
    data_dir: Path,
    paths: RepoPaths,
    tokenizer: SFTTokenizer,
    fmt: PromptFormat,
) -> tuple[TrainingData, dict[str, SFTSplit], DataManifest]:
    """Load, guard and tokenize train/val, then describe them in a data manifest.

    Args:
        cfg: SFT config.
        config_sha: ``config_sha``.
        seed: Seed (nonce salt).
        data_dir: Folder with ``train/`` and ``val/``.
        paths: Repository paths.
        tokenizer: Tokenizer.
        fmt: Prompt format (parity reference).

    Returns:
        ``(data, splits by name, manifest)``.
    """
    prompt = load_triage_prompt(cfg.data.prompt_version, paths.root / PROMPTS_SUBDIR)
    data = load_training_data(data_dir, cfg.data.train_file, cfg.data.val_file, paths)
    salt = nonce_salt(cfg.version, cfg.name, seed)
    splits: dict[str, SFTSplit] = {
        part.split: build_sft_split(
            part,
            tokenizer=tokenizer,
            prompt=prompt,
            fmt=fmt,
            salt=salt,
            max_length=cfg.train.max_length,
        )
        for part in (data.train, data.val)
    }
    for split in splits.values():
        check_length_budget(split, cfg.train.max_over_length_fraction)
    manifest = _manifest(
        cfg, config_sha, seed=seed, data=data, splits=splits, context=(salt, prompt, fmt)
    )
    return data, splits, manifest


def run(
    cfg: SFTRunConfig,
    config_sha: str,
    *,
    seed: int,
    data_dir: Path,
    run_root: Path,
    paths: RepoPaths,
    allow_unverified: bool,
) -> dict[str, object]:  # pragma: no cover - platform only (Kaggle/Colab T4)
    """Train one seed end to end (see the module docstring for the steps).

    Args:
        cfg: SFT config.
        config_sha: ``config_sha``.
        seed: Seed.
        data_dir: Folder with ``train/`` and ``val/``.
        run_root: Parent of the run folders.
        paths: Repository paths.
        allow_unverified: Allow an unpinned base revision (recorded).

    Returns:
        The run summary (also written to ``run_summary.json`` and pushed).
    """
    torch: Any = importlib.import_module("torch")
    started = datetime.now(UTC)
    notes = check_runnable(cfg, seed, allow_unverified=allow_unverified, needs_hub=True)
    facts = assert_platform(expected_torch=cfg.platform.torch, hardware=cfg.platform.hardware)
    run_paths = RunPaths.for_run(run_root, cfg.name, seed)
    run_paths.root.mkdir(parents=True, exist_ok=True)
    repo = cfg.hub.repo_for(seed)
    resume = resume_decision(download_resume_state(repo, run_paths.root))
    LOG.info("%s: %s", repo, resume.reason)
    if not resume.resumed and run_paths.epoch_eval.is_file():
        run_paths.epoch_eval.unlink()  # a fresh start never inherits epoch records
    tokenizer = load_tokenizer(cfg)
    fmt = resolve_prompt_format(cfg, tokenizer, paths.root)
    data, splits, manifest = prepare_data(
        cfg, config_sha, seed=seed, data_dir=data_dir, paths=paths, tokenizer=tokenizer, fmt=fmt
    )
    manifest_sha = write_data_manifest(run_paths.data_manifest, manifest)
    taxonomy = load_taxonomy(paths.schemas_dir)
    evaluator = EpochEvaluator(
        gold=gold_items(data.val),
        prompts=splits["val"].prompts,
        taxonomy=taxonomy,
        rules=load_label_rules(paths.spec_dir / LABEL_RULES_FILE, taxonomy),
        system_id=system_id(cfg, config_sha, seed),
        generate=make_generate(
            tokenizer,
            batch_size=cfg.train.generation_eval.batch_size,
            max_new_tokens=cfg.train.generation_eval.max_new_tokens,
            stop_ids=stop_token_ids(tokenizer, fmt.stop),
        ),
        save_adapter=adapter_saver(run_paths.root, run_paths.epoch_adapters),
        on_record=epoch_hooks(run_paths, repo),
        records=read_epoch_records(run_paths.epoch_eval),
        confusion_dir=run_paths.root / "confusion",
    )
    identity: dict[str, str | int | None] = {
        "kind": "sft",
        "config_name": cfg.name,
        "config_version": cfg.version,
        "config_sha": config_sha,
        "seed": seed,
        "git_sha": git_sha(paths.root),
        "data_manifest_sha256": manifest_sha,
        "train_manifest_sha256": data.committed_manifests.get("train"),
        "val_manifest_sha256": data.committed_manifests.get("val"),
        "base_model": cfg.base.repo,
        "base_revision": cfg.base.revision,
        "training_method": cfg.registry_method,
        "resume": resume.reason,
        "notes": "; ".join(notes) or None,
    }
    tags = run_tags(identity=identity, versions=library_versions(), gpu=facts)
    os.environ.update(
        mlflow_environment(
            store=cfg.tracking.store,
            mlruns=run_paths.mlruns,
            experiment=cfg.tracking.experiment,
            tags=tags,
        )
    )
    with mismatch_guard():
        trainer, loss, loss_notes = build_with_fallback(
            cfg,
            load=lambda: load_model(cfg),
            build=lambda choice, model: build_trainer(
                cfg,
                model=model,
                tokenizer=tokenizer,
                train_rows=splits["train"].rows,
                val_rows=splits["val"].rows,
                seed=seed,
                output_dir=run_paths.checkpoints,
                run_name=f"{cfg.name}-s{seed}",
                hub_repo=repo,
                loss=choice,
                callbacks=epoch_callbacks(cfg, evaluator),
            ),
        )
        handle: Any = trainer
        clock = time.monotonic()
        handle.train(resume_from_checkpoint=str(resume.checkpoint) if resume.checkpoint else None)
        train_seconds = round(time.monotonic() - clock, 1)
    selection = select_final(evaluator.records, handle.state.log_history)
    if selection is not None and selection.adapter_dir is not None:
        shutil.copytree(
            run_paths.root / selection.adapter_dir,
            run_paths.root / "selected_adapter",
            dirs_exist_ok=True,
        )
    write_json(run_paths.root / "selection.json", asdict(selection) if selection else None)
    handle.push_to_hub(commit_message=f"end of training, seed {seed}")
    summary: dict[str, object] = {
        "config": cfg.name,
        "config_sha": config_sha,
        "seed": seed,
        "system_id": evaluator.system_id,
        "training_method": cfg.registry_method,
        "loss_type": loss.loss_type,
        "per_device_batch": loss.per_device_batch,
        "grad_accum": loss.grad_accum,
        "resume": resume.reason,
        "started_at": started.isoformat(timespec="seconds"),
        "train_seconds": train_seconds,
        "global_step": int(handle.state.global_step),
        "peak_memory_gib": round(torch.cuda.max_memory_allocated() / GIB, 2),
        "epochs": [asdict(record) for record in evaluator.records],
        "selection": asdict(selection) if selection else None,
        "data_manifest_sha256": manifest_sha,
        "gpu": asdict(facts),
        "versions": library_versions(),
        "notes": [*notes, *loss_notes],
    }
    write_json(run_paths.summary, summary)
    summary["uploaded"] = push_run(repo, run_paths, f"run files, seed {seed}")
    return summary
