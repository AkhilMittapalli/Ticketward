"""Training run configs: ``ml/configs/sft_*.yaml`` and ``encoder_*.yaml`` (spec v1.1 §9.5; P3.4).

The models encode the rules the spec makes non-negotiable, so a config that breaks one fails on
load, before any GPU time is spent:

* **method by base size** (§9.5 table): LoRA on an fp16 base up to the ``<= 2B`` class, QLoRA
  above it (4-bit NF4 + double quant, fp16 compute, ``paged_adamw_8bit``);
* **T4 precision**: ``fp16: true`` and ``bf16: false`` written out (TRL turns bf16 on unless fp16
  is set, and a T4 has no bf16 hardware); ``attn_implementation: sdpa`` (no FlashAttention-2 on
  Turing);
* **supply chain**: ``trust_remote_code: false`` and safetensors only; the HF revision is a
  40-hex commit SHA or ``<verify>``, which a run refuses unless ``--allow-unverified``;
* **no silent library defaults**: every §9.5 hyperparameter is required (TRL's own defaults are
  lr 2e-5 and ``max_length`` 1024), ``max_length`` is 2048 and the seeds are 42, 1337, 2026;
* **checkpoints**: the private Hub repo is a template with ``{seed}`` (one repo per seed).

``config_sha`` is the SHA-256 of the canonical JSON of the validated model (sorted keys, no
whitespace): comments and formatting keep it, any value change moves it.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Final, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from tw_ml.eval.bakeoff_config import COMMIT_SHA, LE_2B_MAX_PARAMS_B, VERIFY, FinetuneMethod

HF_USER: Final = "<hf_user>"
"""Placeholder namespace of a Hub repo template; the owner writes their HF user name."""
SEEDS: Final[tuple[int, ...]] = (42, 1337, 2026)
MAX_LENGTH: Final = 2048
ENCODER_HEADS: Final[tuple[str, ...]] = (
    "intent",
    "priority",
    "sentiment",
    "churn_risk",
    "product_area",
    "recommended_queue",
)
"""E2 heads (spec §9.5: intent, priority, sentiment, churn, product_area, queue)."""
QWEN35_PREFIX: Final = "Qwen/Qwen3.5-"
HOURS_BUDGET: Final = {"le_2b": 2.0, "3_4b": 4.0}
"""Smoke-test projection budget per seed (§9.5: <= 2 h for 2B-class, <= 4 h for 4B)."""
_REPO: Final = r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
_REPO_RE: Final = re.compile(_REPO)
_SLUG: Final = r"^[a-z0-9][a-z0-9._-]{1,80}$"
_MODULE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

ModelClass = Literal["Qwen3_5ForCausalLM", "AutoModelForCausalLM"]
HeadName = Literal[
    "intent", "priority", "sentiment", "churn_risk", "product_area", "recommended_queue"
]


class ConfigError(ValueError):
    """Raised when a training config is missing, malformed, breaks a rule or is not runnable."""


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BaseModelRef(_Config):
    """The Hugging Face base model, pinned by commit SHA (or ``<verify>`` until pinned)."""

    repo: str = Field(pattern=_REPO)
    revision: str
    license: Literal["apache-2.0", "mit", "llama3.2"]
    params_b: float = Field(gt=0.0, le=100.0)

    @property
    def pinned(self) -> bool:
        """Whether ``revision`` is a 40-hex commit SHA."""
        return bool(COMMIT_SHA.fullmatch(self.revision))

    @model_validator(mode="after")
    def _revision(self) -> Self:
        if not self.pinned and self.revision != VERIFY:
            msg = f"revision must be a 40-hex commit SHA or {VERIFY}"
            raise ValueError(msg)
        return self


class Precision(_Config):
    """T4 precision: fp16 AMP, never bf16 (both keys are required, so they stay explicit)."""

    fp16: Literal[True]
    bf16: Literal[False]
    attn_implementation: Literal["sdpa", "eager"]


class Quantization(_Config):
    """QLoRA base quantization (3-4B bases): 4-bit NF4, double quant, fp16 compute."""

    load_in_4bit: Literal[True]
    quant_type: Literal["nf4"]
    double_quant: Literal[True]
    compute_dtype: Literal["float16"]


class LoraSettings(_Config):
    """LoRA adapter (§9.5: r 16 / alpha 32 / dropout 0.05, ``bias="none"``, all linear)."""

    r: int = Field(ge=1, le=256)
    alpha: int = Field(ge=1, le=1024)
    dropout: float = Field(ge=0.0, lt=1.0)
    bias: Literal["none"]
    target_modules: Literal["all-linear"] | tuple[str, ...]

    @model_validator(mode="after")
    def _targets(self) -> Self:
        if isinstance(self.target_modules, str):
            return self
        names = self.target_modules
        if not names or len(set(names)) != len(names):
            msg = "target_modules must be 'all-linear' or a non-empty list without duplicates"
            raise ValueError(msg)
        if any(not _MODULE.fullmatch(name) for name in names):
            msg = "target_modules entries must be module names"
            raise ValueError(msg)
        if any(name.split(".")[-1] == "lm_head" for name in names):
            msg = "never adapt lm_head (chunked_nll needs a plain output layer, §9.5)"
            raise ValueError(msg)
        return self


class LossFallback(_Config):
    """The ``nll`` fallback when ``chunked_nll`` does not construct (same effective batch)."""

    loss_type: Literal["nll"]
    per_device_batch: int = Field(ge=1)
    grad_accum: int = Field(ge=1)


class GenerationEvalSettings(_Config):
    """Epoch-end greedy generation on val (macro-F1 picks the final checkpoint)."""

    max_new_tokens: int = Field(ge=1, le=4096)
    batch_size: int = Field(ge=1, le=256)


class SFTTrainSettings(_Config):
    """§9.5 SFT hyperparameters; all required so no library default applies silently."""

    max_length: int
    epochs: int = Field(ge=1, le=20)
    per_device_batch: int = Field(ge=1, le=64)
    grad_accum: int = Field(ge=1, le=256)
    per_device_eval_batch: int = Field(ge=1, le=256)
    lr: float = Field(gt=0.0, lt=1.0)
    scheduler: Literal["cosine"]
    warmup_ratio: float = Field(ge=0.0, lt=1.0)
    optim: Literal["adamw_torch", "paged_adamw_8bit"]
    gradient_checkpointing: Literal[True]
    packing: Literal[False]
    padding_free: Literal[False]
    loss_type: Literal["chunked_nll", "nll"]
    loss_fallback: LossFallback | None
    eval_steps: int = Field(ge=1)
    save_steps: int = Field(ge=1)
    save_total_limit: int = Field(ge=1)
    logging_steps: int = Field(ge=1)
    early_stopping_patience: int = Field(ge=1)
    metric_for_best_model: Literal["eval_loss"]
    max_over_length_fraction: float = Field(ge=0.0, le=1.0)
    generation_eval: GenerationEvalSettings

    @property
    def effective_batch(self) -> int:
        """Rows per optimizer step on one GPU (per-device batch x gradient accumulation)."""
        return self.per_device_batch * self.grad_accum

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.max_length != MAX_LENGTH:
            msg = f"max_length must be {MAX_LENGTH} (spec §9.5; a change needs an ADR)"
            raise ValueError(msg)
        if self.save_steps % self.eval_steps:
            msg = "save_steps must be a multiple of eval_steps (load_best_model_at_end)"
            raise ValueError(msg)
        fallback = self.loss_fallback
        if fallback is not None:
            if self.loss_type != "chunked_nll":
                msg = "loss_fallback applies only to loss_type chunked_nll"
                raise ValueError(msg)
            if fallback.per_device_batch * fallback.grad_accum != self.effective_batch:
                msg = "loss_fallback must keep the effective batch (per_device_batch x grad_accum)"
                raise ValueError(msg)
        return self


class HubSettings(_Config):
    """Private Hub repo per seed; ``hub_strategy="checkpoint"`` also pushes ``last-checkpoint/``."""

    checkpoint_repo: str = Field(min_length=3, max_length=120)
    private: Literal[True]
    strategy: Literal["checkpoint"]

    @property
    def placeholder(self) -> bool:
        """Whether the namespace is still the ``<hf_user>`` placeholder."""
        return self.checkpoint_repo.startswith(f"{HF_USER}/")

    def repo_for(self, seed: int) -> str:
        """The repo id of one seed.

        Args:
            seed: Training seed.

        Returns:
            The template with ``{seed}`` filled in.
        """
        return self.checkpoint_repo.replace("{seed}", str(seed))

    @model_validator(mode="after")
    def _template(self) -> Self:
        template = self.checkpoint_repo
        if template.count("{seed}") != 1 or template.replace("{seed}", "").count("{"):
            msg = "checkpoint_repo must contain {seed} exactly once (one private repo per seed)"
            raise ValueError(msg)
        sample = self.repo_for(SEEDS[0]).replace(f"{HF_USER}/", "owner/", 1)
        if not _REPO_RE.fullmatch(sample):
            msg = f"checkpoint_repo must be '<namespace>/<name>' (namespace or {HF_USER})"
            raise ValueError(msg)
        return self


class TrackingSettings(_Config):
    """MLflow on the platform (a local store synced to the Hub) plus CodeCarbon (§9.6)."""

    experiment: str = Field(pattern=_SLUG)
    store: Literal["file", "sqlite"]
    report_to: tuple[Literal["mlflow", "codecarbon"], ...]

    @model_validator(mode="after")
    def _both(self) -> Self:
        if sorted(self.report_to) != ["codecarbon", "mlflow"]:
            msg = "report_to must be [mlflow, codecarbon] (spec §9.6, P3.24)"
            raise ValueError(msg)
        return self


class PlatformSettings(_Config):
    """The training platform: a T4 with the platform's own torch (never locked, A-03)."""

    hardware: Literal["t4"]
    torch: str = Field(pattern=r"^[0-9]+\.[0-9]+$")


class SmokeBudget(_Config):
    """R-21 smoke-test thresholds (spec §9.5 "Smoke test")."""

    rows: int = Field(ge=1, le=64)
    max_peak_memory_gib: float = Field(gt=0.0, le=16.0)
    max_hours_per_seed: float = Field(gt=0.0, le=12.0)
    resume_tolerance: float = Field(gt=0.0, le=0.1)


class SFTDataSettings(_Config):
    """Training data: train/val files under ``--data-dir`` and the prompt used to render them."""

    train_file: str = Field(min_length=1)
    val_file: str = Field(min_length=1)
    prompt_version: str = Field(pattern=r"^triage\.v[0-9]+$")
    prompt_format: str | None = Field(default=None, min_length=1)


class EncoderTrainSettings(_Config):
    """E2 hyperparameters (spec §9.5: lr 3e-5, batch 32, 5 epochs, max_len 512, ...)."""

    lr: float = Field(gt=0.0, lt=1.0)
    per_device_batch: int = Field(ge=1, le=256)
    epochs: int = Field(ge=1, le=50)
    max_length: int = Field(ge=16, le=8192)
    warmup_ratio: float = Field(ge=0.0, lt=1.0)
    weight_decay: float = Field(ge=0.0, lt=1.0)
    class_weighting: Literal["inverse_sqrt"]
    best_metric: Literal["intent_macro_f1"]


class EncoderDataSettings(_Config):
    """E2 data: train/val under ``--data-dir``; predictions for open splits only."""

    train_file: str = Field(min_length=1)
    val_file: str = Field(min_length=1)
    predict_splits: tuple[Literal["val", "hard_dev"], ...] = Field(min_length=1)


def _seed_problems(seeds: tuple[int, ...]) -> list[str]:
    return [] if seeds == SEEDS else [f"seeds must be exactly {list(SEEDS)} (spec §9.5, A-10)"]


class SFTRunConfig(_Config):
    """``ml/configs/sft_*.yaml``: one LoRA/QLoRA SFT run definition (E4, P3.5)."""

    kind: Literal["sft"]
    version: str = Field(pattern=r"^sft\.v[0-9]+$")
    name: str = Field(pattern=_SLUG)
    base: BaseModelRef
    model_class: ModelClass
    method: FinetuneMethod
    trust_remote_code: Literal[False]
    use_safetensors: Literal[True]
    precision: Precision
    quantization: Quantization | None
    lora: LoraSettings
    train: SFTTrainSettings
    seeds: tuple[int, ...]
    hub: HubSettings
    tracking: TrackingSettings
    platform: PlatformSettings
    smoke: SmokeBudget
    data: SFTDataSettings

    @property
    def size_class(self) -> Literal["le_2b", "3_4b"]:
        """The §9.5 method-table row of the base (same bound as the bake-off)."""
        return "le_2b" if self.base.params_b <= LE_2B_MAX_PARAMS_B else "3_4b"

    @property
    def registry_method(self) -> Literal["lora", "qlora"]:
        """``lora`` or ``qlora``: the method actually used, as named in the registry (§9.6)."""
        return "lora" if self.method == "lora_fp16" else "qlora"

    @model_validator(mode="after")
    def _rules(self) -> Self:
        problems = _seed_problems(self.seeds)
        expected = "lora_fp16" if self.size_class == "le_2b" else "qlora_nf4"
        if self.method != expected:
            problems.append(f"a {self.base.params_b}B base is trained with {expected} (§9.5)")
        if (self.method == "qlora_nf4") != (self.quantization is not None):
            problems.append("quantization is set exactly when method is qlora_nf4")
        optim = "adamw_torch" if self.method == "lora_fp16" else "paged_adamw_8bit"
        if self.train.optim != optim:
            problems.append(f"{self.method} uses optim {optim} (§9.5)")
        if self.precision.attn_implementation != "sdpa":
            problems.append("SFT on T4 uses attn_implementation sdpa (no FlashAttention-2)")
        qwen35 = self.base.repo.startswith(QWEN35_PREFIX)
        model_class = "Qwen3_5ForCausalLM" if qwen35 else "AutoModelForCausalLM"
        if self.model_class != model_class:
            problems.append(f"{self.base.repo} loads with {model_class} (text-only, §9.5)")
        if self.smoke.max_hours_per_seed > HOURS_BUDGET[self.size_class]:
            budget = HOURS_BUDGET[self.size_class]
            problems.append(f"smoke.max_hours_per_seed exceeds the §9.5 budget of {budget} h")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class EncoderRunConfig(_Config):
    """``ml/configs/encoder_*.yaml``: the E2 multi-head encoder baseline (P2.9)."""

    kind: Literal["encoder"]
    version: str = Field(pattern=r"^encoder\.v[0-9]+$")
    name: str = Field(pattern=_SLUG)
    base: BaseModelRef
    trust_remote_code: Literal[False]
    use_safetensors: Literal[True]
    precision: Precision
    heads: tuple[HeadName, ...]
    pooling: Literal["cls", "mean"]
    head_dropout: float = Field(ge=0.0, lt=1.0)
    train: EncoderTrainSettings
    calibration: Literal["temperature"]
    seeds: tuple[int, ...]
    hub: HubSettings
    tracking: TrackingSettings
    platform: PlatformSettings
    data: EncoderDataSettings

    @model_validator(mode="after")
    def _rules(self) -> Self:
        problems = _seed_problems(self.seeds)
        if self.heads != ENCODER_HEADS:
            problems.append(f"heads must be {list(ENCODER_HEADS)} in this order (spec §9.5)")
        if problems:
            raise ValueError("; ".join(problems))
        return self


RunConfig = SFTRunConfig | EncoderRunConfig
_ADAPTER: Final[TypeAdapter[RunConfig]] = TypeAdapter(
    Annotated[SFTRunConfig | EncoderRunConfig, Field(discriminator="kind")]
)


def canonical_json(config: RunConfig) -> str:
    """The canonical JSON of a validated config (sorted keys, compact separators).

    Args:
        config: A validated config.

    Returns:
        The JSON text that ``config_sha`` hashes.
    """
    return json.dumps(
        config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def config_sha(config: RunConfig) -> str:
    """``config_sha``: SHA-256 of :func:`canonical_json` (logged to MLflow, spec §9.5).

    Args:
        config: A validated config.

    Returns:
        64 lowercase hex characters.
    """
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def parse_run_config(document: object, source: str = "<config>") -> RunConfig:
    """Validate a parsed YAML document as an SFT or encoder config (by its ``kind``).

    Args:
        document: The parsed YAML.
        source: Name used in error messages.

    Returns:
        The validated config.

    Raises:
        ConfigError: If the document is not a valid config (field paths only, no values).
    """
    try:
        return _ADAPTER.validate_python(document)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}"
            for e in exc.errors()[:8]
        )
        msg = f"{source} is invalid: {details}"
        raise ConfigError(msg) from None


def load_run_config(path: Path) -> tuple[RunConfig, str]:
    """Load and validate a training config.

    Args:
        path: YAML file (``ml/configs/sft_*.yaml`` or ``encoder_*.yaml``).

    Returns:
        The config and its ``config_sha``.

    Raises:
        ConfigError: If the file is missing, not YAML or not a valid config.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        msg = f"training config not found: {path.name}"
        raise ConfigError(msg) from None
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        msg = f"{path.name} is not valid YAML"
        raise ConfigError(msg) from None
    config = parse_run_config(document, path.name)
    return config, config_sha(config)


def unverified_fields(config: RunConfig) -> list[str]:
    """Placeholders the owner still has to replace.

    Args:
        config: A validated config.

    Returns:
        Dotted field paths (``base.revision``, ``hub.checkpoint_repo``).
    """
    fields = [] if config.base.pinned else ["base.revision"]
    if config.hub.placeholder:
        fields.append("hub.checkpoint_repo")
    return fields


def check_runnable(
    config: RunConfig, seed: int, *, allow_unverified: bool, needs_hub: bool
) -> list[str]:
    """Refuse a run that would use an unknown seed, an unpinned model or a placeholder repo.

    Args:
        config: A validated config.
        seed: Requested seed.
        allow_unverified: The explicit ``--allow-unverified`` acknowledgement: an unpinned
            ``<verify>`` revision then loads the repo's default branch (recorded in every
            summary).
        needs_hub: Whether this run pushes to the checkpoint repo (a training run does, the
            smoke test and a dry run do not). A placeholder namespace is never runnable there.

    Returns:
        Notes to record (e.g. the unverified revision that was allowed).

    Raises:
        ConfigError: If the run must not start.
    """
    if seed not in config.seeds:
        msg = f"seed {seed} is not one of the configured seeds {list(config.seeds)}"
        raise ConfigError(msg)
    notes: list[str] = []
    if not config.base.pinned:
        if not allow_unverified:
            msg = (
                f"base.revision is {VERIFY}: pin {config.base.repo} to a commit SHA (the one in "
                "ml/configs/bakeoff.yaml) or pass --allow-unverified"
            )
            raise ConfigError(msg)
        notes.append(f"UNVERIFIED: {config.base.repo} at its default branch (--allow-unverified)")
    if needs_hub and config.hub.placeholder:
        msg = f"hub.checkpoint_repo still starts with {HF_USER}/: set your HF user name"
        raise ConfigError(msg)
    return notes
