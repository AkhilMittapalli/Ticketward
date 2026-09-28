"""Hugging Face Hub I/O of training runs: data, resume state, uploads (spec v1.1 §9.5-§9.6).

``huggingface_hub`` is imported only when a function needs it (the platform installs it from
``ml/requirements/train.txt``). The token comes from ``HF_TOKEN``, which the notebook copies from
Kaggle Secrets or Colab ``userdata`` into the environment; nothing here reads, prints or logs it.

* Only ``train/`` and ``val/`` of the private dataset are ever downloaded to a training machine,
  at a pinned revision, so sealed splits cannot reach it even if the dataset holds them.
* Resume is idempotent: a missing checkpoint repo or a repo without ``last-checkpoint/`` starts
  fresh (and says so); any other Hub error stops the run instead of silently restarting and
  overwriting the pushed checkpoint.

CLI (the notebooks call these)::

    python -m tw_ml.train.hub fetch-data --repo <user>/<dataset> --revision <sha>
    python -m tw_ml.train.hub push-run --config <yaml> --seed N [--run-root DIR]
"""

import argparse
import importlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

from tw_ml.datagen.paths import find_repo_root
from tw_ml.eval.bakeoff_config import COMMIT_SHA
from tw_ml.train.config import ConfigError, load_run_config
from tw_ml.train.runtime import RunPaths

TRAINABLE_FILES: Final[tuple[str, ...]] = ("train/records.jsonl", "val/records.jsonl")
"""The only dataset files a training machine downloads (never a test split)."""
RESUME_PATTERNS: Final[tuple[str, ...]] = (
    "last-checkpoint/*",
    "epoch_eval.jsonl",
    "epoch_adapters/*",
    "mlruns/*",
)
"""Hub files that restore an interrupted run (fnmatch: ``*`` spans folders)."""
RUN_UPLOADS: Final[tuple[str, ...]] = (
    "mlruns",
    "epoch_adapters",
    "selected_adapter",
    "confusion",
    "epoch_eval.jsonl",
    "selection.json",
    "data_manifest.json",
    "run_summary.json",
    "calibrator.json",
    "final",
)
"""Run-folder entries :func:`push_run` uploads when present (the trainer pushes checkpoints)."""
DEFAULT_RUN_ROOT: Final = Path("ml") / "outputs" / "runs"
"""Run folders under the repository root (gitignored ``/ml/outputs/``); Kaggle passes its own."""
EXIT_OK: Final = 0
EXIT_USAGE: Final = 2


class HubError(RuntimeError):
    """Raised when a Hub operation cannot run (library missing, unpinned revision, bad files)."""


def hub_module() -> ModuleType:
    """Import ``huggingface_hub`` (installed on the platform, not in the local environment).

    Returns:
        The module.

    Raises:
        HubError: If it is not installed.
    """
    try:
        return importlib.import_module("huggingface_hub")
    except ImportError:
        msg = "huggingface_hub is not installed (pip install -r ml/requirements/train.txt)"
        raise HubError(msg) from None


@dataclass(frozen=True, slots=True)
class ResumeDecision:
    """Whether a run resumes, and why (logged and tagged either way).

    Attributes:
        checkpoint: ``last-checkpoint`` folder to resume from, or ``None`` for a fresh start.
        reason: Human-readable reason.
    """

    checkpoint: Path | None
    reason: str

    @property
    def resumed(self) -> bool:
        """Whether training resumes from a checkpoint."""
        return self.checkpoint is not None


def resume_decision(snapshot: Path | None) -> ResumeDecision:
    """Decide from a downloaded snapshot (``None`` when the repo does not exist yet).

    Args:
        snapshot: Local folder the Hub files were downloaded into.

    Returns:
        Resume from ``last-checkpoint/`` when it holds a trainer state, else start fresh.
    """
    if snapshot is None:
        return ResumeDecision(None, "fresh start: the checkpoint repo does not exist yet")
    checkpoint = snapshot / "last-checkpoint"
    if (checkpoint / "trainer_state.json").is_file():
        state = json.loads((checkpoint / "trainer_state.json").read_text(encoding="utf-8"))
        step = state.get("global_step") if isinstance(state, dict) else None
        return ResumeDecision(checkpoint, f"resuming from Hub last-checkpoint (step {step})")
    return ResumeDecision(None, "fresh start: the repo has no last-checkpoint/ yet")


def download_resume_state(repo_id: str, local_dir: Path) -> Path | None:  # pragma: no cover
    """Download the resume files of a checkpoint repo (network; needs ``huggingface_hub``).

    Args:
        repo_id: Private checkpoint repo of one seed.
        local_dir: The run folder (files keep their repo paths below it).

    Returns:
        ``local_dir``, or ``None`` when the repo does not exist (or is not visible).
    """
    hub = hub_module()
    errors = importlib.import_module("huggingface_hub.errors")
    try:
        hub.snapshot_download(
            repo_id=repo_id, allow_patterns=list(RESUME_PATTERNS), local_dir=str(local_dir)
        )
    except errors.RepositoryNotFoundError:
        return None
    return local_dir


def check_dataset_revision(revision: str) -> str:
    """Refuse a branch name or tag: the training data is pinned by commit SHA.

    Args:
        revision: Dataset revision.

    Returns:
        The revision.

    Raises:
        HubError: If it is not a 40-hex commit SHA.
    """
    if not COMMIT_SHA.fullmatch(revision):
        msg = "--revision must be the dataset's 40-hex commit SHA (the data version trained on)"
        raise HubError(msg)
    return revision


def missing_training_files(out_dir: Path, files: Sequence[str] = TRAINABLE_FILES) -> list[str]:
    """Expected dataset files that are absent after a download.

    Args:
        out_dir: Download folder.
        files: Expected relative paths.

    Returns:
        The missing ones.
    """
    return [name for name in files if not (out_dir / name).is_file()]


def fetch_training_data(
    repo_id: str, revision: str, out_dir: Path
) -> list[Path]:  # pragma: no cover
    """Download ``train/`` and ``val/`` of the private dataset at a pinned revision (network).

    Args:
        repo_id: Private HF dataset id.
        revision: Commit SHA.
        out_dir: Destination (``data/generated`` of the checkout).

    Returns:
        The downloaded files.

    Raises:
        HubError: If the revision is not pinned or a file is missing afterwards.
    """
    hub = hub_module()
    hub.snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        revision=check_dataset_revision(revision),
        allow_patterns=list(TRAINABLE_FILES),
        local_dir=str(out_dir),
    )
    missing = missing_training_files(out_dir)
    if missing:
        msg = f"the dataset revision lacks {', '.join(missing)}"
        raise HubError(msg)
    return [out_dir / name for name in TRAINABLE_FILES]


def upload_path(
    repo_id: str, path: Path, path_in_repo: str, message: str
) -> None:  # pragma: no cover
    """Upload one file or folder to a private model repo (created when absent; network).

    Args:
        repo_id: Target repo.
        path: Local file or folder.
        path_in_repo: Destination path in the repo.
        message: Commit message.
    """
    api = hub_module().HfApi()
    api.create_repo(repo_id=repo_id, private=True, exist_ok=True)
    if path.is_dir():
        api.upload_folder(
            repo_id=repo_id,
            folder_path=str(path),
            path_in_repo=path_in_repo,
            commit_message=message,
        )
    else:
        api.upload_file(
            repo_id=repo_id,
            path_or_fileobj=str(path),
            path_in_repo=path_in_repo,
            commit_message=message,
        )


def run_uploads(run: RunPaths) -> list[Path]:
    """The run-folder entries :func:`push_run` uploads (those that exist).

    Args:
        run: The run folder.

    Returns:
        Existing entries, in :data:`RUN_UPLOADS` order.
    """
    return [run.root / name for name in RUN_UPLOADS if (run.root / name).exists()]


def push_run(repo_id: str, run: RunPaths, message: str) -> list[str]:  # pragma: no cover
    """Upload a run's MLflow store, adapters, choice and summaries (network).

    Args:
        repo_id: The seed's checkpoint repo.
        run: The run folder.
        message: Commit message.

    Returns:
        The uploaded repo paths.
    """
    uploaded = []
    for path in run_uploads(run):
        upload_path(repo_id, path, path.name, message)
        uploaded.append(path.name)
    return uploaded


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tw_ml.train.hub", description="Hub I/O for Ticketward training runs."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch-data", help="download train/ and val/ of the private dataset")
    fetch.add_argument("--repo", required=True, help="private HF dataset id")
    fetch.add_argument("--revision", required=True, help="dataset commit SHA (40 hex)")
    fetch.add_argument("--out", default="data/generated", help="destination folder")
    push = sub.add_parser("push-run", help="upload one seed's run folder to its checkpoint repo")
    push.add_argument("--config", required=True, help="the run's training config")
    push.add_argument("--seed", required=True, type=int, help="the run's seed")
    push.add_argument("--run-root", help="parent of run folders (default ml/outputs/runs)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code: 0 success, 2 usage, config or Hub error.
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fetch-data":
            files = fetch_training_data(args.repo, args.revision, Path(args.out))
            summary: dict[str, object] = {"files": [f.as_posix() for f in files]}
        else:
            config, _ = load_run_config(Path(args.config))
            if config.hub.placeholder:
                msg = "hub.checkpoint_repo still has the <hf_user> placeholder"
                raise ConfigError(msg)
            root = Path(args.run_root) if args.run_root else find_repo_root() / DEFAULT_RUN_ROOT
            run = RunPaths.for_run(root, config.name, args.seed)
            repo = config.hub.repo_for(args.seed)
            summary = {
                "repo": repo,
                "uploaded": push_run(repo, run, f"run files, seed {args.seed}"),
            }
    except (ConfigError, HubError) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return EXIT_USAGE
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
