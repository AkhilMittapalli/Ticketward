"""Platform facts and guards shared by the training entry points (spec v1.1 §9.5-§9.6).

* :func:`platform_problems` checks the platform's torch (asserted, never locked; A-03), CUDA and
  the GPU before any weights load;
* :func:`library_versions` records torch/transformers/trl/peft/... for MLflow and the summaries;
* :func:`mlflow_environment` points Transformers' MLflow callback at a local store inside the
  run folder (``file`` or ``sqlite``) and hands it the run tags (``config_sha``, git SHA, data
  manifest hashes, library versions, GPU, seed) through ``MLFLOW_TAGS``. Each seed has its own
  store, so two seeds training in parallel never race on one MLflow directory;
* :class:`RunPaths` lays out one seed's folder.

Nothing here imports torch at module level; :func:`gpu_facts` imports it when called.
"""

import importlib
import importlib.metadata
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

TRACKED_LIBRARIES: Final[tuple[str, ...]] = (
    "torch",
    "transformers",
    "trl",
    "peft",
    "accelerate",
    "datasets",
    "bitsandbytes",
    "huggingface-hub",
    "tokenizers",
    "safetensors",
    "mlflow",
    "codecarbon",
    "numpy",
    "pydantic",
    "tw-ml",
)
"""Versions logged with every run (spec §9.6: torch/transformers/trl/peft/bitsandbytes...)."""
ABSENT: Final = "absent"
T4_CAPABILITY: Final = (7, 5)
GIB: Final = 1024**3


class PlatformError(RuntimeError):
    """Raised when the platform is not the one the config was written for."""


def library_versions(names: Iterable[str] = TRACKED_LIBRARIES) -> dict[str, str]:
    """Installed versions of the tracked libraries.

    Args:
        names: Distribution names.

    Returns:
        Name to version, ``absent`` for libraries that are not installed.
    """
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = ABSENT
    return versions


@dataclass(frozen=True, slots=True)
class GpuFacts:
    """What the platform reports about torch and its GPUs.

    Attributes:
        torch: ``torch.__version__`` (e.g. ``2.11.0+cu130``).
        cuda: ``torch.version.cuda`` (``None`` on a CPU build).
        cuda_available: ``torch.cuda.is_available()``.
        names: Visible GPU names (``CUDA_VISIBLE_DEVICES`` applies).
        capability: Compute capability of GPU 0.
        memory_gib: Total memory of GPU 0.
    """

    torch: str
    cuda: str | None
    cuda_available: bool
    names: tuple[str, ...]
    capability: tuple[int, int] | None
    memory_gib: float | None


def torch_minor(version: str) -> str:
    """``major.minor`` of a torch version string (``2.11.0+cu130`` -> ``2.11``).

    Args:
        version: ``torch.__version__``.

    Returns:
        The major and minor components.
    """
    return ".".join(version.split("+", 1)[0].split(".")[:2])


def platform_problems(
    facts: GpuFacts, *, expected_torch: str, hardware: Literal["t4"]
) -> list[str]:
    """Check the platform against the config (torch pin, CUDA, a T4).

    Args:
        facts: Reported facts.
        expected_torch: ``platform.torch`` of the config (``2.11``).
        hardware: ``platform.hardware`` (``t4``: fp16 AMP, SDPA, no bf16).

    Returns:
        Problems; empty when the platform matches.
    """
    problems: list[str] = []
    if torch_minor(facts.torch) != expected_torch:
        problems.append(
            f"torch {facts.torch} is not the platform torch {expected_torch} the config was "
            "written for (update platform.torch only after a passing smoke test)"
        )
    if not facts.cuda_available or not facts.names:
        problems.append("CUDA is not available (select a GPU accelerator)")
        return problems
    if "T4" not in facts.names[0] or facts.capability != T4_CAPABILITY:
        problems.append(
            f"GPU 0 is {facts.names[0]} (sm {facts.capability}), not the configured {hardware}; "
            "other GPUs need a config with their own precision (bf16 on A10/L4, spec §9.5)"
        )
    return problems


def gpu_facts() -> GpuFacts:  # pragma: no cover - needs the platform's CUDA torch
    """Ask torch about the platform.

    Returns:
        The facts.
    """
    torch = importlib.import_module("torch")
    available = bool(torch.cuda.is_available())
    count = int(torch.cuda.device_count()) if available else 0
    names = tuple(str(torch.cuda.get_device_name(i)) for i in range(count))
    capability = tuple(torch.cuda.get_device_capability(0)) if count else None
    memory = torch.cuda.get_device_properties(0).total_memory / GIB if count else None
    return GpuFacts(
        torch=str(torch.__version__),
        cuda=torch.version.cuda,
        cuda_available=available,
        names=names,
        capability=(int(capability[0]), int(capability[1])) if capability else None,
        memory_gib=round(float(memory), 2) if memory is not None else None,
    )


def assert_platform(
    *, expected_torch: str, hardware: Literal["t4"]
) -> GpuFacts:  # pragma: no cover - needs the platform's CUDA torch
    """Fail fast unless the platform matches the config.

    Args:
        expected_torch: ``platform.torch``.
        hardware: ``platform.hardware``.

    Returns:
        The facts (logged with the run).

    Raises:
        PlatformError: If any check fails.
    """
    facts = gpu_facts()
    problems = platform_problems(facts, expected_torch=expected_torch, hardware=hardware)
    if problems:
        raise PlatformError("; ".join(problems))
    return facts


@dataclass(frozen=True, slots=True)
class RunPaths:
    """One seed's run folder (``<run_root>/<config name>-s<seed>/``).

    Attributes:
        root: The run folder. Hub resume downloads land here too (``last-checkpoint/``,
            ``epoch_eval.jsonl``, ``epoch_adapters/``, ``mlruns/``).
    """

    root: Path

    @classmethod
    def for_run(cls, run_root: Path, name: str, seed: int) -> "RunPaths":
        """The folder of one config and seed.

        Args:
            run_root: Parent folder (``/kaggle/working/tw-runs`` on Kaggle).
            name: Config ``name``.
            seed: Seed.

        Returns:
            The paths (nothing is created).
        """
        return cls(run_root / f"{name}-s{seed}")

    @property
    def checkpoints(self) -> Path:
        """Trainer ``output_dir`` (its root is pushed to the Hub repo root)."""
        return self.root / "checkpoints"

    @property
    def last_checkpoint(self) -> Path:
        """Where a Hub ``last-checkpoint/`` is downloaded for resume."""
        return self.root / "last-checkpoint"

    @property
    def mlruns(self) -> Path:
        """This seed's MLflow store (a file store, or the SQLite database's folder)."""
        return self.root / "mlruns"

    @property
    def epoch_adapters(self) -> Path:
        """Adapters saved at each epoch end (the final choice is one of them)."""
        return self.root / "epoch_adapters"

    @property
    def epoch_eval(self) -> Path:
        """Epoch-end generation-eval records (JSONL)."""
        return self.root / "epoch_eval.jsonl"

    @property
    def data_manifest(self) -> Path:
        """``data_manifest.json`` of the run."""
        return self.root / "data_manifest.json"

    @property
    def summary(self) -> Path:
        """``run_summary.json`` of the run."""
        return self.root / "run_summary.json"


def tracking_uri(store: Literal["file", "sqlite"], mlruns: Path) -> str:
    """The MLflow tracking URI of a local store.

    Args:
        store: ``file`` (spec §9.6 default) or ``sqlite`` (fallback if the pinned MLflow drops
            the file store).
        mlruns: The store folder.

    Returns:
        ``file:///...`` or ``sqlite:///.../mlflow.db`` (absolute).
    """
    folder = mlruns.resolve()
    if store == "file":
        return folder.as_uri()
    return f"sqlite:///{(folder / 'mlflow.db').as_posix()}"


def mlflow_environment(
    *,
    store: Literal["file", "sqlite"],
    mlruns: Path,
    experiment: str,
    tags: Mapping[str, str],
) -> dict[str, str]:
    """Environment variables for Transformers' ``MLflowCallback`` (read at train begin).

    Args:
        store: Store kind.
        mlruns: Store folder.
        experiment: MLflow experiment name.
        tags: Run tags (``config_sha``, git SHA, manifests, versions, GPU, seed).

    Returns:
        The variables to set; no model artifacts are logged (the Hub holds them).
    """
    return {
        "MLFLOW_TRACKING_URI": tracking_uri(store, mlruns),
        "MLFLOW_EXPERIMENT_NAME": experiment,
        "MLFLOW_TAGS": json.dumps(dict(tags), sort_keys=True),
        "HF_MLFLOW_LOG_ARTIFACTS": "FALSE",
        "MLFLOW_FLATTEN_PARAMS": "TRUE",
    }


def run_tags(
    *,
    identity: Mapping[str, str | int | None],
    versions: Mapping[str, str],
    gpu: GpuFacts | None,
) -> dict[str, str]:
    """Flatten the run identity into MLflow tags (strings only; ``None`` becomes ``unknown``).

    Args:
        identity: ``config_sha``, ``config_name``, ``seed``, ``git_sha``, manifest hashes ...
        versions: :func:`library_versions`.
        gpu: Platform facts (``None`` in a dry run).

    Returns:
        Tag name to value; library versions are prefixed ``lib.``.
    """
    tags = {key: "unknown" if value is None else str(value) for key, value in identity.items()}
    tags.update({f"lib.{name}": version for name, version in versions.items()})
    if gpu is not None:
        tags["gpu"] = ", ".join(gpu.names) or "none"
        tags["torch_cuda"] = gpu.cuda or "none"
    return tags


def write_json(path: Path, document: object) -> Path:
    """Write pretty JSON (UTF-8, LF, final newline).

    Args:
        path: Destination (parents are created).
        document: JSON-serializable value.

    Returns:
        The path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
