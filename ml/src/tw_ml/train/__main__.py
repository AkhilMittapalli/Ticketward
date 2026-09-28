"""``python -m tw_ml.train``: train one seed of an SFT or encoder config, or dry-run it.

    python -m tw_ml.train --config ml/configs/sft_qwen35_2b.yaml --seed 42
        [--data-dir data/generated] [--run-root ml/outputs/runs] [--allow-unverified] [--dry-run]

``--dry-run`` checks everything that needs neither a GPU nor a model download, on any machine
(torch and Transformers are never imported): the config (``config_sha``, pins, the seed), the
train/val data through the S-12 refusal and the holdout guard, the committed data manifests, the
prompt-format file (goldens re-verified) and the rendering of every SFT prompt and target, or,
for the encoder, the head classes of every label and the class weights. It prints a JSON summary
and never writes a file. Tokenization, chat-template parity and the boundary checks need the
tokenizer: they run at the start of every real run and in the smoke test.

Exit codes: 0 success, 2 usage, config, pin, data or platform error (a dry run with blockers,
e.g. a missing prompt-format file, also exits 2).
"""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from tw_ml.datagen.labelrules import LABEL_RULES_FILE, load_label_rules
from tw_ml.datagen.paths import RepoPaths, default_paths
from tw_ml.datagen.taxonomy import TaxonomyError, load_taxonomy
from tw_ml.export.prompt_format import PromptFormatError, load_prompt_format, verify_goldens
from tw_ml.prompts import (
    PROMPTS_SUBDIR,
    PromptError,
    TriagePrompt,
    derive_nonce,
    load_triage_prompt,
)
from tw_ml.train.config import (
    ConfigError,
    EncoderRunConfig,
    RunConfig,
    SFTRunConfig,
    check_runnable,
    load_run_config,
    unverified_fields,
)
from tw_ml.train.data import (
    SplitData,
    TrainingData,
    TrainingDataError,
    load_training_data,
    nonce_salt,
    split_summary,
)
from tw_ml.train.encoder import EncoderError, examples, head_class_weights, head_specs
from tw_ml.train.hub import DEFAULT_RUN_ROOT
from tw_ml.train.runtime import PlatformError
from tw_ml.train.sft import TrainingError, prompt_format_problems, steps_per_seed

EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
DEFERRED_SFT: Final[tuple[str, ...]] = (
    "tokenization and the max_length rejection (needs the tokenizer)",
    "chat-template parity with render_raw and the joint/concatenated boundary check",
    "platform torch, CUDA and T4 asserts",
)


def _render_stats(
    data: SplitData, prompt: TriagePrompt, salt: str, special: Sequence[str]
) -> dict[str, object]:
    """Render every record's prompt and target (checks nonces, labels and prompt placeholders)."""
    rendered = [
        prompt.render_record(
            record, nonce=derive_nonce(record.record_id, salt=salt), special_tokens=special
        )
        for record in data.records
    ]
    return {
        "rendered": len(rendered),
        "user_chars_max": max(len(r.user) for r in rendered),
        "target_chars_max": max(len(r.target or "") for r in rendered),
        "system_chars": len(prompt.system),
    }


def _prompt_format(
    cfg: SFTRunConfig, paths: RepoPaths
) -> tuple[dict[str, object], list[str], tuple[str, ...]]:
    """Check the configured prompt format; return (summary, blockers, special tokens)."""
    if cfg.data.prompt_format is None:
        return {"status": "derived from the tokenizer at run time"}, [], ()
    path = paths.root / cfg.data.prompt_format
    if not path.is_file():
        blocker = (
            f"prompt format {cfg.data.prompt_format} does not exist: generate it with "
            f"python -m tw_ml.export.prompt_format --model {cfg.base.repo} --revision <sha> "
            "--out <file> (ml/configs/README.md, bake-off step 4)"
        )
        return {"status": "missing", "file": cfg.data.prompt_format}, [blocker], ()
    fmt = load_prompt_format(path)
    verify_goldens(fmt)
    problems = prompt_format_problems(fmt, cfg, chat_template_sha256=None)
    summary: dict[str, object] = {
        "status": "verified" if not problems else "mismatch",
        "file": cfg.data.prompt_format,
        "goldens": len(fmt.goldens),
        "chat_template_sha256": fmt.chat_template_sha256,
    }
    return summary, problems, fmt.special_tokens


def dry_run_sft(
    cfg: SFTRunConfig, seed: int, data: TrainingData, paths: RepoPaths
) -> tuple[dict[str, object], list[str]]:
    """The SFT part of a dry run.

    Args:
        cfg: SFT config.
        seed: Seed.
        data: Loaded train/val.
        paths: Repository paths.

    Returns:
        ``(summary, blockers)``.
    """
    fmt_summary, blockers, special = _prompt_format(cfg, paths)
    prompt = load_triage_prompt(cfg.data.prompt_version, paths.root / PROMPTS_SUBDIR)
    salt = nonce_salt(cfg.version, cfg.name, seed)
    summary: dict[str, object] = {
        "method": cfg.method,
        "training_method": cfg.registry_method,
        "effective_batch": cfg.train.effective_batch,
        "optimizer_steps_per_seed": steps_per_seed(len(data.train.records), cfg),
        "prompt": {"version": prompt.version, "sha256": prompt.prompt_sha256},
        "prompt_format": fmt_summary,
        "nonce_salt": salt,
        "rendering": {
            part.split: _render_stats(part, prompt, salt, special)
            for part in (data.train, data.val)
        },
        "deferred_to_platform": list(DEFERRED_SFT),
    }
    return summary, blockers


def dry_run_encoder(
    cfg: EncoderRunConfig, data: TrainingData, paths: RepoPaths
) -> tuple[dict[str, object], list[str]]:
    """The encoder part of a dry run.

    Args:
        cfg: Encoder config.
        data: Loaded train/val.
        paths: Repository paths.

    Returns:
        ``(summary, blockers)``.
    """
    taxonomy = load_taxonomy(paths.schemas_dir)
    load_label_rules(paths.spec_dir / LABEL_RULES_FILE, taxonomy)
    specs = head_specs(cfg.heads, taxonomy, paths.schemas_dir)
    train, val = examples(data.train, specs), examples(data.val, specs)
    weights = head_class_weights(train, specs)
    heads = {
        spec.name: {
            "classes": len(spec.classes),
            "train_classes_seen": sum(1 for w in weights[spec.name] if w > 0),
            "val_records": len(val.targets[spec.name]),
            "class_weight_range": [
                round(min(w for w in weights[spec.name] if w > 0), 4),
                round(max(weights[spec.name]), 4),
            ],
        }
        for spec in specs
    }
    predict = {
        split: "ready"
        if split == "val" or paths.hard_dev_gold_file.is_file()
        else "no gold file yet"
        for split in cfg.data.predict_splits
    }
    return {"heads": heads, "pooling": cfg.pooling, "predict_splits": predict}, []


def dry_run(
    config: RunConfig, sha: str, seed: int, data_dir: Path, paths: RepoPaths, notes: Sequence[str]
) -> tuple[dict[str, object], list[str]]:
    """Validate config and data without torch (see the module docstring).

    Args:
        config: Validated config.
        sha: ``config_sha``.
        seed: Seed.
        data_dir: Folder with ``train/`` and ``val/``.
        paths: Repository paths.
        notes: Notes from the pin check.

    Returns:
        ``(summary, blockers)``.
    """
    data = load_training_data(data_dir, config.data.train_file, config.data.val_file, paths)
    summary: dict[str, object] = {
        "dry_run": True,
        "kind": config.kind,
        "config": config.name,
        "version": config.version,
        "config_sha": sha,
        "seed": seed,
        "base": {
            "repo": config.base.repo,
            "revision": config.base.revision,
            "pinned": config.base.pinned,
            "license": config.base.license,
        },
        "unverified": unverified_fields(config),
        "hub_repo": config.hub.repo_for(seed),
        "notes": list(notes),
        "data": {
            "train": split_summary(data.train),
            "val": split_summary(data.val),
            "committed_manifests": dict(data.committed_manifests),
        },
    }
    if isinstance(config, SFTRunConfig):
        details, blockers = dry_run_sft(config, seed, data, paths)
    else:
        details, blockers = dry_run_encoder(config, data, paths)
    summary[config.kind] = details
    summary["blockers"] = blockers
    return summary, blockers


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tw_ml.train",
        description="Train one seed of an SFT (E4) or encoder (E2) config on a T4, or dry-run it.",
    )
    parser.add_argument("--config", required=True, help="ml/configs/sft_*.yaml or encoder_*.yaml")
    parser.add_argument("--seed", required=True, type=int, help="one of the config's seeds")
    parser.add_argument("--data-dir", help="folder with train/ and val/ (default data/generated)")
    parser.add_argument("--run-root", help="parent of run folders (default ml/outputs/runs)")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="allow a <verify> base revision (the default branch is loaded and recorded)",
    )
    parser.add_argument("--dry-run", action="store_true", help="validate config and data; no torch")
    return parser


def _train(
    config: RunConfig, sha: str, args: argparse.Namespace, data_dir: Path, paths: RepoPaths
) -> dict[str, object]:  # pragma: no cover - platform only
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    options = {
        "seed": args.seed,
        "data_dir": data_dir,
        "run_root": Path(args.run_root) if args.run_root else paths.root / DEFAULT_RUN_ROOT,
        "paths": paths,
        "allow_unverified": args.allow_unverified,
    }
    if isinstance(config, SFTRunConfig):
        from tw_ml.train import sft  # noqa: PLC0415 - the chosen trainer only

        return sft.run(config, sha, **options)
    from tw_ml.train import encoder  # noqa: PLC0415

    return encoder.run(config, sha, **options)


def main(argv: Sequence[str] | None = None, paths: RepoPaths | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).
        paths: Repository paths override (tests).

    Returns:
        Exit code: 0 success, 2 usage/config/pin/data/platform error or dry-run blockers.
    """
    args = build_parser().parse_args(argv)
    paths = paths or default_paths()
    data_dir = Path(args.data_dir) if args.data_dir else paths.generated_dir
    try:
        config, sha = load_run_config(Path(args.config))
        notes = check_runnable(
            config, args.seed, allow_unverified=args.allow_unverified, needs_hub=not args.dry_run
        )
        if args.dry_run:
            summary, blockers = dry_run(config, sha, args.seed, data_dir, paths, notes)
        else:
            summary, blockers = _train(config, sha, args, data_dir, paths), []  # pragma: no cover
    except (
        ConfigError,
        TrainingDataError,
        TrainingError,
        PlatformError,
        EncoderError,
        PromptError,
        PromptFormatError,
        TaxonomyError,
    ) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return EXIT_USAGE
    sys.stdout.write(json.dumps(summary, indent=2, default=str) + "\n")
    return EXIT_USAGE if blockers else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
