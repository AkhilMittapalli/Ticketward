"""Configuration of the E3 bake-off (``ml/configs/bakeoff.yaml``; spec v1.1 §9.5, A-02).

The models encode the protocol rules, so a config that breaks them fails on load:

* every candidate is served as a local Ollama model named ``tw-bakeoff-<id>``, built from a
  GGUF the owner converts from the official safetensors (``Q4_K_M``, no imatrix); a library
  tag, a ``hf.co/...`` reference or another name is rejected;
* the HF repo is pinned by commit SHA, or carries the ``<verify>`` placeholder together with
  ``verify_before_run: true``;
* the license determines Lic (1.0 Apache-2.0/MIT, 0.5 Llama 3.2); a license outside that table
  is refused, and the dropped non-commercial Qwen2.5-3B-Instruct can never be listed;
* the fine-tune method follows the §9.5 table: LoRA on an fp16 base up to the ``<= 2B`` size
  class, QLoRA (NF4) above it (:data:`LE_2B_MAX_PARAMS_B`);
* the request is the §9.5 protocol: raw prompts, no streaming, ``truncate: false``,
  temperature 0, and explicit ``num_ctx``, ``num_predict`` and ``seed``;
* the score weights sum to 1.
"""

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

VERIFY: Final = "<verify>"
"""Placeholder for a value the owner must verify and pin before a run."""
COMMIT_SHA: Final = re.compile(r"^[0-9a-f]{40}$")
LICENSE_LIC: Final[Mapping[str, float]] = {"apache-2.0": 1.0, "mit": 1.0, "llama3.2": 0.5}
"""Lic term of the score (§9.5); non-commercial licenses are excluded, so they are not listed."""
DROPPED_REPOS: Final[frozenset[str]] = frozenset({"Qwen/Qwen2.5-3B-Instruct"})
"""Dropped at v1.1 (A-02): Qwen Research License, non-commercial."""
LE_2B_MAX_PARAMS_B: Final = 2.5
"""Upper bound (billions of parameters) of the ``<= 2B`` class of the §9.5 method table."""
OPEN_SPLITS: Final[frozenset[str]] = frozenset({"val", "val_dev", "hard_dev"})
"""Splits the bake-off may read (P2: val + hard_dev; val_dev is a val subset)."""
REQUIRED_OPTIONS: Final[tuple[str, ...]] = ("temperature", "num_ctx", "num_predict", "seed")

FinetuneMethod = Literal["lora_fp16", "qlora_nf4"]
SizeClass = Literal["le_2b", "3_4b"]
SIZE_RANK: Final[Mapping[str, int]] = {"le_2b": 0, "3_4b": 1}


class BakeoffConfigError(ValueError):
    """Raised when ``bakeoff.yaml`` is missing, malformed or breaks the protocol."""


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Candidate(_Config):
    """One bake-off candidate (§9.5 table)."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,40}$")
    role: str = Field(min_length=1, max_length=80)
    optional: bool = False
    hf_repo: str = Field(pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
    hf_revision: str
    license: str
    lic: float = Field(ge=0.0, le=1.0)
    params_b: float = Field(gt=0.0, le=100.0)
    finetune_method: FinetuneMethod
    ollama_model: str
    ollama_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    quantization: Literal["Q4_K_M"] = "Q4_K_M"
    imatrix: Literal[False] = False
    prompt_format: str = Field(min_length=1)
    verify_before_run: bool = True
    notes: str = ""

    @property
    def size_class(self) -> SizeClass:
        """``le_2b`` or ``3_4b`` (the §9.5 method-table row)."""
        return "le_2b" if self.params_b <= LE_2B_MAX_PARAMS_B else "3_4b"

    @property
    def pinned(self) -> bool:
        """Whether ``hf_revision`` is a commit SHA."""
        return bool(COMMIT_SHA.fullmatch(self.hf_revision))

    @model_validator(mode="after")
    def _protocol(self) -> Self:
        problems: list[str] = []
        if self.ollama_model != f"tw-bakeoff-{self.id}":
            problems.append(f"ollama_model must be tw-bakeoff-{self.id} (no library tags)")
        if not self.pinned and self.hf_revision != VERIFY:
            problems.append(f"hf_revision must be a 40-hex commit SHA or {VERIFY}")
        if self.hf_revision == VERIFY and not self.verify_before_run:
            problems.append(f"hf_revision {VERIFY} requires verify_before_run: true")
        if self.hf_repo in DROPPED_REPOS:
            problems.append(f"{self.hf_repo} was dropped (non-commercial license, A-02)")
        expected = LICENSE_LIC.get(self.license)
        if expected is None:
            problems.append(f"license {self.license!r} has no Lic value (§9.5)")
        elif self.lic != expected:
            problems.append(f"license {self.license} has Lic {expected}, not {self.lic}")
        method = "lora_fp16" if self.size_class == "le_2b" else "qlora_nf4"
        if self.finetune_method != method:
            problems.append(f"a {self.params_b}B base is fine-tuned with {method} (§9.5)")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class OllamaSettings(_Config):
    """Server, pinned versions, timeouts and the retry policy."""

    base_url: str = Field(default="http://127.0.0.1:11434", pattern=r"^https?://[^\s/]+(/.*)?$")
    version: str = Field(min_length=1)
    llama_cpp_build: str = Field(pattern=r"^b[0-9]+$")
    timeout_s: float = Field(gt=0.0, le=3600.0)
    connect_timeout_s: float = Field(default=5.0, gt=0.0, le=60.0)
    retries: int = Field(default=1, ge=0, le=5)
    backoff_s: float = Field(default=2.0, ge=0.0, le=60.0)
    keep_alive: str = "30m"
    max_consecutive_failures: int = Field(default=5, ge=1)


class RequestSettings(_Config):
    """The ``/api/generate`` body shared by every candidate (§9.5)."""

    raw: Literal[True] = True
    stream: Literal[False] = False
    truncate: Literal[False] = False
    shift: bool = False
    options: dict[str, int | float]
    cpu_options: dict[str, int]

    @model_validator(mode="after")
    def _protocol(self) -> Self:
        missing = [key for key in REQUIRED_OPTIONS if key not in self.options]
        if missing:
            msg = f"options must set {', '.join(missing)} explicitly"
            raise ValueError(msg)
        if self.options["temperature"] != 0:
            msg = "temperature must be 0 (deterministic triage, §6.6)"
            raise ValueError(msg)
        if "num_gpu" not in self.cpu_options or "num_thread" not in self.cpu_options:
            msg = "cpu_options must set num_gpu and num_thread"
            raise ValueError(msg)
        return self


class SamplingSettings(_Config):
    """The CPU latency sample and the nonce derivation."""

    cpu_sample_n: int = Field(default=50, ge=1)
    sample_seed: int = Field(default=42, ge=0)
    nonce_salt: str = Field(min_length=1)


class ScoreSettings(_Config):
    """``S = w1 macroF1 + w2 min_critical_recall + w3 min(1, target / P50) + w4 Lic`` (§9.5)."""

    w_macro_f1: float = Field(ge=0.0, le=1.0)
    w_min_critical_recall: float = Field(ge=0.0, le=1.0)
    w_latency: float = Field(ge=0.0, le=1.0)
    w_license: float = Field(ge=0.0, le=1.0)
    latency_target_s: float = Field(gt=0.0)
    min_gain_macro_f1: float = Field(ge=0.0, le=1.0)
    m08_p50_s: float = Field(gt=0.0)
    m08_p95_s: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> Self:
        total = self.w_macro_f1 + self.w_min_critical_recall + self.w_latency + self.w_license
        if abs(total - 1.0) > 1e-9:  # noqa: PLR2004 - float tolerance
            msg = f"score weights must sum to 1 (got {total:.6f})"
            raise ValueError(msg)
        return self


class BakeoffConfig(_Config):
    """``ml/configs/bakeoff.yaml``."""

    version: str = Field(pattern=r"^bakeoff\.v[0-9]+$")
    prompt_version: str = Field(pattern=r"^triage\.v[0-9]+$")
    decoding_schema: str = Field(pattern=r"^[a-z0-9_]+\.decoding\.json$")
    output_dir: str = Field(min_length=1)
    splits: dict[str, str]
    ollama: OllamaSettings
    request: RequestSettings
    sampling: SamplingSettings
    score: ScoreSettings
    candidates: tuple[Candidate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [candidate.id for candidate in self.candidates]
        if len(set(ids)) != len(ids):
            msg = "candidate ids must be unique"
            raise ValueError(msg)
        unknown = sorted(set(self.splits) - OPEN_SPLITS)
        if unknown:
            msg = f"splits may only name open splits {sorted(OPEN_SPLITS)}, not {unknown}"
            raise ValueError(msg)
        return self

    def candidate(self, candidate_id: str) -> Candidate:
        """Return one candidate.

        Args:
            candidate_id: Candidate id.

        Returns:
            The candidate.

        Raises:
            BakeoffConfigError: If no candidate has this id.
        """
        for candidate in self.candidates:
            if candidate.id == candidate_id:
                return candidate
        msg = (
            f"unknown candidate {candidate_id!r}; known: {', '.join(c.id for c in self.candidates)}"
        )
        raise BakeoffConfigError(msg)


def load_bakeoff_config(path: Path) -> tuple[BakeoffConfig, str]:
    """Load and validate ``bakeoff.yaml``.

    Args:
        path: Config file.

    Returns:
        The config and the SHA-256 of its LF-normalized text (``config_sha`` in summaries).

    Raises:
        BakeoffConfigError: If the file is missing, not YAML or breaks the protocol.
    """
    try:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except FileNotFoundError:
        msg = f"bake-off config not found: {path.name}"
        raise BakeoffConfigError(msg) from None
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        msg = f"{path.name} is not valid YAML"
        raise BakeoffConfigError(msg) from None
    try:
        config = BakeoffConfig.model_validate(document)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}"
            for e in exc.errors()[:8]
        )
        msg = f"{path.name} is invalid: {details}"
        raise BakeoffConfigError(msg) from None
    return config, hashlib.sha256(text.encode("utf-8")).hexdigest()
