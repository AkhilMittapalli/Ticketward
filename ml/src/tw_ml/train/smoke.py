"""R-21 T4 smoke test per finalist: ``python -m tw_ml.train.smoke --config ... --steps 20``.

Runs before any full SFT run (spec v1.1 §9.5 "Smoke test"; ERPROT qlora-training-on-t4 D8;
P2.21) with the exact trainer of :mod:`tw_ml.train.sft`, on real train rows, and asserts:

1. an fp16 forward/backward on ``smoke.rows`` (8) rows has no inf/NaN in the loss or the
   gradients (the logits' max-abs is logged when the loss path returns logits);
2. every trainable parameter is fp32 after trainer init (catches TRL's bf16 cast of QLoRA
   adapters);
3. the loss type constructs (``chunked_nll``, else the ``nll`` fallback, which is reported);
4. peak memory (``torch.cuda.max_memory_allocated``) stays below ``smoke.max_peak_memory_gib``;
5. the measured median s/step projects to at most ``smoke.max_hours_per_seed`` per seed (2 h
   for the <= 2B class, 4 h for 4B; epoch-end generation evals come on top);
6. for Qwen3.5, whether the Gated DeltaNet fast path (``fla`` / ``causal-conv1d``) was used
   (informational: run once with and once without the packages to time both);
7. a checkpoint saved halfway, a fresh trainer resumed from it, and an identical loss at the
   next step (within ``smoke.resume_tolerance``). The round trip uses a local checkpoint
   folder; the first real run exercises the Hub ``last-checkpoint/`` path.

The report goes to ``<run_root>/smoke/<name>-s<seed>/smoke_report.json`` and stdout. Exit codes:
0 every check passed, 1 a check failed, 2 usage, config, data or platform error. The checks are
pure functions tested offline; :func:`run_smoke` needs the platform.
"""

import argparse
import importlib
import importlib.util
import json
import math
import statistics
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

from tw_ml.datagen.paths import RepoPaths, default_paths
from tw_ml.train import sft
from tw_ml.train.config import ConfigError, SFTRunConfig, check_runnable, load_run_config
from tw_ml.train.data import TrainingDataError
from tw_ml.train.hub import DEFAULT_RUN_ROOT
from tw_ml.train.runtime import (
    GIB,
    PlatformError,
    RunPaths,
    assert_platform,
    library_versions,
    write_json,
)
from tw_ml.train.sft import LossChoice, TrainingError

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_USAGE: Final = 2
DEFAULT_STEPS: Final = 20
VAL_ROWS: Final = 32
"""Val rows for the smoke evaluations (the eval path is exercised, not measured)."""
FAST_PATH_PACKAGES: Final[tuple[str, ...]] = ("fla", "causal_conv1d")
FAST_PATH_ATTRIBUTES: Final[tuple[str, ...]] = (
    "chunk_gated_delta_rule",
    "recurrent_gated_delta_rule",
    "causal_conv1d_fn",
    "causal_conv1d_update",
)
"""Gated DeltaNet kernel slots; the torch fallbacks live in ``transformers`` modules."""

Status = Literal["pass", "fail", "info"]


@dataclass(frozen=True, slots=True)
class Check:
    """One smoke assertion.

    Attributes:
        number: Assertion number (1-7, spec §9.5 order).
        name: Short name.
        status: ``pass``, ``fail`` or ``info`` (informational, never fails the run).
        detail: What was measured.
        value: The measured number, when there is one.
    """

    number: int
    name: str
    status: Status
    detail: str
    value: float | None = None


def passed(checks: Iterable[Check]) -> bool:
    """Whether no check failed.

    Args:
        checks: The checks.

    Returns:
        True when every check passed or is informational.
    """
    return all(check.status != "fail" for check in checks)


def forward_check(loss: float, grads_finite: bool, logits_max_abs: float | None) -> Check:
    """Assertion 1: fp16 forward/backward without inf/NaN.

    Args:
        loss: Mean loss over the smoke rows.
        grads_finite: Whether every gradient of a trainable parameter is finite.
        logits_max_abs: Largest absolute logit (``None`` when the loss path returns none).

    Returns:
        The check.
    """
    finite = math.isfinite(loss)
    logits = f"; logits max-abs {logits_max_abs:.1f}" if logits_max_abs is not None else ""
    return Check(
        1,
        "fp16 forward/backward",
        "pass" if finite and grads_finite else "fail",
        f"loss {loss:.4f}, gradients {'finite' if grads_finite else 'NOT finite'}{logits}",
        loss if finite else None,
    )


def dtype_check(problems: Sequence[str], trainable: int) -> Check:
    """Assertion 2: trainable parameters are fp32 after trainer init.

    Args:
        problems: :func:`tw_ml.train.sft.trainable_dtype_problems` output.
        trainable: Number of trainable parameter tensors.

    Returns:
        The check.
    """
    detail = "; ".join(problems) or f"{trainable} trainable tensors, all fp32"
    return Check(2, "trainable fp32", "fail" if problems else "pass", detail, float(trainable))


def loss_check(used: LossChoice, configured: str, notes: Sequence[str]) -> Check:
    """Assertion 3: the loss type constructs (the fallback counts, and is reported).

    Args:
        used: The loss the trainer was built with.
        configured: ``train.loss_type``.
        notes: Why a loss did not construct.

    Returns:
        The check.
    """
    fell_back = used.loss_type != configured
    detail = f"{used.loss_type} at batch {used.per_device_batch} x {used.grad_accum}"
    if fell_back:
        detail += f" (fallback: {'; '.join(notes)}; set train.loss_type accordingly)"
    return Check(3, "loss type constructs", "pass", detail)


def memory_check(peak_gib: float, limit_gib: float) -> Check:
    """Assertion 4: peak memory below the limit.

    Args:
        peak_gib: ``torch.cuda.max_memory_allocated()`` in GiB.
        limit_gib: ``smoke.max_peak_memory_gib``.

    Returns:
        The check.
    """
    status: Status = "pass" if peak_gib < limit_gib else "fail"
    return Check(4, "peak memory", status, f"{peak_gib:.2f} GiB (limit {limit_gib} GiB)", peak_gib)


def median_step_seconds(durations: Sequence[float], *, warmup: int = 1) -> float | None:
    """Median optimizer-step time, without the warm-up steps (CUDA init, allocator growth).

    Args:
        durations: Seconds per optimizer step, in order.
        warmup: Leading steps to drop (kept when nothing else is left).

    Returns:
        The median, or ``None`` without measurements.
    """
    kept = list(durations[warmup:]) or list(durations)
    return statistics.median(kept) if kept else None


def time_check(seconds_per_step: float | None, steps: int, budget_hours: float) -> Check:
    """Assertion 5: the measured s/step projects to the per-seed budget.

    Args:
        seconds_per_step: Median s/step.
        steps: Optimizer steps of a full run (:func:`tw_ml.train.sft.steps_per_seed`).
        budget_hours: ``smoke.max_hours_per_seed``.

    Returns:
        The check (the projection excludes the epoch-end generation evals).
    """
    if seconds_per_step is None:
        return Check(5, "time per seed", "fail", "no optimizer step was timed")
    hours = seconds_per_step * steps / 3600
    status: Status = "pass" if hours <= budget_hours else "fail"
    detail = (
        f"{seconds_per_step:.2f} s/step x {steps} steps = {hours:.2f} h (budget {budget_hours} h; "
        "epoch-end generation evals come on top)"
    )
    return Check(5, "time per seed", status, detail, round(hours, 3))


def fast_path_check(
    applicable: bool, available: Mapping[str, bool], kernels: Mapping[str, str]
) -> Check:
    """Assertion 6: whether Qwen3.5's Gated DeltaNet kernels come from ``fla``/``causal-conv1d``.

    Args:
        applicable: Whether the base is Qwen3.5.
        available: Package name to installed.
        kernels: Kernel slot to the ``__module__`` of the function in it (first GDN layer).

    Returns:
        An informational check.
    """
    if not applicable:
        return Check(6, "Qwen3.5 fast path", "info", "not a Qwen3.5 base (no Gated DeltaNet)")
    fast = all(module.split(".", 1)[0] in FAST_PATH_PACKAGES for module in kernels.values())
    packages = ", ".join(f"{name} {'yes' if ok else 'no'}" for name, ok in available.items())
    slots = ", ".join(f"{slot}={module}" for slot, module in sorted(kernels.items())) or "none"
    if not kernels:
        used = "unknown: no Gated DeltaNet kernel slot found (did the module names change?)"
    else:
        used = "fast path" if fast else "torch fallback"
    return Check(
        6, "Qwen3.5 fast path", "info", f"{used} (installed: {packages}; kernels: {slots})"
    )


def loss_at_step(log_history: Sequence[Mapping[str, object]], step: int) -> float | None:
    """The training loss logged at a step (``logging_steps=1`` in a smoke run).

    Args:
        log_history: ``trainer.state.log_history``.
        step: Global step.

    Returns:
        The loss, or ``None`` when that step logged none.
    """
    for entry in log_history:
        loss = entry.get("loss")
        if entry.get("step") == step and isinstance(loss, int | float):
            return float(loss)
    return None


def resume_check(
    first: float | None, resumed: float | None, *, step: int, tolerance: float
) -> Check:
    """Assertion 7: save, restart, resume, and the same loss at the next step.

    Args:
        first: Loss at ``step`` in the uninterrupted run.
        resumed: Loss at ``step`` after resuming from the halfway checkpoint.
        step: The step compared (checkpoint step + 1).
        tolerance: ``smoke.resume_tolerance``.

    Returns:
        The check.
    """
    if first is None or resumed is None:
        return Check(7, "checkpoint resume", "fail", f"no loss logged at step {step} in both runs")
    delta = abs(first - resumed)
    status: Status = "pass" if delta <= tolerance else "fail"
    detail = (
        f"step {step}: {first:.5f} vs {resumed:.5f} after resume (|d| {delta:.2e}, tol {tolerance})"
    )
    return Check(7, "checkpoint resume", status, detail, delta)


@dataclass
class StepClock:
    """Optimizer-step timer (the platform callback calls ``begin``/``end`` around each step)."""

    clock: Callable[[], float] = time.perf_counter
    durations: list[float] = field(default_factory=list)
    _started: float | None = None

    def begin(self) -> None:
        """Mark the start of a step."""
        self._started = self.clock()

    def end(self) -> None:
        """Mark the end of a step (ignored without a matching ``begin``)."""
        if self._started is not None:
            self.durations.append(self.clock() - self._started)
            self._started = None


def should_stop(global_step: int, stop_at: int | None) -> bool:
    """Whether a resumed smoke run has reached the compared step.

    Args:
        global_step: Current step.
        stop_at: Step to stop at (``None``: never).

    Returns:
        True at or after ``stop_at``.
    """
    return stop_at is not None and global_step >= stop_at


def fast_path_packages() -> dict[str, bool]:
    """Whether the Gated DeltaNet kernel packages are importable (no import is executed).

    Returns:
        Package name to installed.
    """
    return {name: importlib.util.find_spec(name) is not None for name in FAST_PATH_PACKAGES}


def kernel_modules(modules: Iterable[object]) -> dict[str, str]:
    """``__module__`` of each Gated DeltaNet kernel slot of the first module that has them.

    Args:
        modules: ``model.modules()``.

    Returns:
        Slot name to the implementing module (empty for non-GDN models).
    """
    for module in modules:
        found = {
            slot: str(getattr(getattr(module, slot), "__module__", "unknown"))
            for slot in FAST_PATH_ATTRIBUTES
            if getattr(module, slot, None) is not None
        }
        if found:
            return found
    return {}


# --------------------------------------------------------------------------- platform (lazy)


def step_callbacks(
    clock: StepClock, stop_at: int | None
) -> list[object]:  # pragma: no cover - needs transformers
    """Trainer callbacks that time optimizer steps and stop a resumed run at ``stop_at``.

    Args:
        clock: The step clock.
        stop_at: Step to stop at (``None``: run to ``max_steps``).

    Returns:
        The callback.
    """
    from transformers import TrainerCallback  # noqa: PLC0415 - platform-only dependency

    class SmokeCallback(TrainerCallback):  # type: ignore[misc] # untyped base (transformers)
        def on_step_begin(
            self, args: object, state: object, control: object, **kwargs: object
        ) -> None:
            del args, state, control, kwargs
            clock.begin()

        def on_step_end(
            self, args: object, state: object, control: object, **kwargs: object
        ) -> object:
            del args, kwargs
            clock.end()
            status: Any = state
            flow: Any = control
            if should_stop(int(status.global_step), stop_at):
                flow.should_training_stop = True
            return flow

    return [SmokeCallback()]


def forward_backward(trainer: object, rows: Sequence[Any], batch: int) -> Check:  # pragma: no cover
    """Assertion 1 on the trainer's own loss path (fp16 autocast, no loss scaling).

    Args:
        trainer: The built ``SFTTrainer``.
        rows: Option A rows (``SFTRow``).
        batch: Micro-batch size.

    Returns:
        The check.
    """
    torch: Any = importlib.import_module("torch")
    handle: Any = trainer
    model = handle.model
    model.train()
    device = next(model.parameters()).device
    losses, logits_max = [], None
    for start in range(0, len(rows), batch):
        features = [row.features() for row in rows[start : start + batch]]
        inputs = {k: v.to(device) for k, v in handle.data_collator(features).items()}
        with torch.autocast("cuda", dtype=torch.float16):
            loss, outputs = handle.compute_loss(model, inputs, return_outputs=True)
        logits = getattr(outputs, "logits", None) if outputs is not None else None
        if logits is not None:
            value = float(logits.detach().float().abs().max())
            logits_max = value if logits_max is None else max(logits_max, value)
        (loss / max(1, -(-len(rows) // batch))).backward()
        losses.append(float(loss.detach().float()))
    grads = [p.grad for p in model.parameters() if p.requires_grad and p.grad is not None]
    finite = bool(grads) and all(bool(torch.isfinite(g).all()) for g in grads)
    model.zero_grad(set_to_none=True)
    return forward_check(sum(losses) / len(losses), finite, logits_max)


def run_smoke(
    cfg: SFTRunConfig,
    config_sha: str,
    *,
    seed: int,
    steps: int,
    data_dir: Path,
    run_root: Path,
    paths: RepoPaths,
    allow_unverified: bool,
) -> tuple[list[Check], Path]:  # pragma: no cover - platform only (Kaggle/Colab T4)
    """Run the seven checks on the platform.

    Args:
        cfg: SFT config.
        config_sha: ``config_sha``.
        seed: Seed.
        steps: Optimizer steps of the timed run (checkpoint at ``steps // 2``).
        data_dir: Folder with ``train/`` and ``val/``.
        run_root: Parent of run folders (the smoke run goes to ``<run_root>/smoke/``).
        paths: Repository paths.
        allow_unverified: Allow an unpinned base revision.

    Returns:
        ``(checks, report path)``.
    """
    import gc  # noqa: PLC0415

    torch: Any = importlib.import_module("torch")
    notes = check_runnable(cfg, seed, allow_unverified=allow_unverified, needs_hub=False)
    facts = assert_platform(expected_torch=cfg.platform.torch, hardware=cfg.platform.hardware)
    run = RunPaths.for_run(run_root / "smoke", cfg.name, seed)
    tokenizer = sft.load_tokenizer(cfg)
    fmt = sft.resolve_prompt_format(cfg, tokenizer, paths.root)
    _, splits, _ = sft.prepare_data(
        cfg, config_sha, seed=seed, data_dir=data_dir, paths=paths, tokenizer=tokenizer, fmt=fmt
    )
    train_rows, val_rows = splits["train"].rows, splits["val"].rows[:VAL_ROWS]
    checkpoint_step = max(1, steps // 2)

    def build(clock: StepClock, stop_at: int | None) -> tuple[Any, LossChoice, list[str]]:
        return sft.build_with_fallback(
            cfg,
            load=lambda: sft.load_model(cfg),
            build=lambda choice, model: sft.build_trainer(
                cfg,
                model=model,
                tokenizer=tokenizer,
                train_rows=train_rows,
                val_rows=val_rows,
                seed=seed,
                output_dir=run.checkpoints,
                run_name=f"smoke-{cfg.name}-s{seed}",
                hub_repo=None,
                loss=choice,
                callbacks=step_callbacks(clock, stop_at),
                smoke_steps=steps,
            ),
        )

    torch.cuda.reset_peak_memory_stats()
    clock = StepClock()
    with sft.mismatch_guard():
        trainer, loss, loss_notes = build(clock, None)
        parameters = [
            (n, p.requires_grad, str(p.dtype)) for n, p in trainer.model.named_parameters()
        ]
        checks = [forward_backward(trainer, train_rows[: cfg.smoke.rows], loss.per_device_batch)]
        trainable = sum(1 for _, requires_grad, _ in parameters if requires_grad)
        checks.append(dtype_check(sft.trainable_dtype_problems(parameters), trainable))
        checks.append(loss_check(loss, cfg.train.loss_type, loss_notes))
        trainer.train()
        peak = torch.cuda.max_memory_allocated() / GIB
        checks.append(memory_check(peak, cfg.smoke.max_peak_memory_gib))
        full_steps = sft.steps_per_seed(len(train_rows), cfg)
        checks.append(
            time_check(
                median_step_seconds(clock.durations), full_steps, cfg.smoke.max_hours_per_seed
            )
        )
        is_qwen35 = cfg.model_class == "Qwen3_5ForCausalLM"
        checks.append(
            fast_path_check(
                is_qwen35, fast_path_packages(), kernel_modules(trainer.model.modules())
            )
        )
        first = loss_at_step(trainer.state.log_history, checkpoint_step + 1)
        del trainer
        gc.collect()
        torch.cuda.empty_cache()
        resumed_trainer, _, _ = build(StepClock(), checkpoint_step + 1)
        resumed_trainer.train(
            resume_from_checkpoint=str(run.checkpoints / f"checkpoint-{checkpoint_step}")
        )
        second = loss_at_step(resumed_trainer.state.log_history, checkpoint_step + 1)
    checks.append(
        resume_check(first, second, step=checkpoint_step + 1, tolerance=cfg.smoke.resume_tolerance)
    )
    checks.sort(key=lambda check: check.number)
    report = {
        "config": cfg.name,
        "config_sha": config_sha,
        "seed": seed,
        "steps": steps,
        "passed": passed(checks),
        "checks": [asdict(check) for check in checks],
        "gpu": asdict(facts),
        "versions": library_versions(),
        "notes": notes,
    }
    return checks, write_json(run.root / "smoke_report.json", report)


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tw_ml.train.smoke", description="R-21 T4 smoke test of an SFT config."
    )
    parser.add_argument("--config", required=True, help="ml/configs/sft_*.yaml")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help="timed optimizer steps")
    parser.add_argument("--seed", type=int, help="seed (default: the config's first seed)")
    parser.add_argument("--data-dir", help="folder with train/ and val/ (default data/generated)")
    parser.add_argument("--run-root", help="parent of run folders (default ml/outputs/runs)")
    parser.add_argument("--allow-unverified", action="store_true", help="allow a <verify> revision")
    return parser


def main(argv: Sequence[str] | None = None, paths: RepoPaths | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).
        paths: Repository paths override (tests).

    Returns:
        Exit code: 0 all checks passed, 1 a check failed, 2 usage/config/data/platform error.
    """
    args = build_parser().parse_args(argv)
    paths = paths or default_paths()
    try:
        config, sha = load_run_config(Path(args.config))
        if not isinstance(config, SFTRunConfig):
            msg = "the smoke test is for SFT configs (sft_*.yaml)"
            raise ConfigError(msg)
        if args.steps < 2:  # noqa: PLR2004 - a checkpoint needs a step before and after it
            msg = "--steps must be at least 2 (checkpoint halfway, resume after it)"
            raise ConfigError(msg)
        seed = args.seed if args.seed is not None else config.seeds[0]
        check_runnable(config, seed, allow_unverified=args.allow_unverified, needs_hub=False)
        return _execute(args, config, sha, seed, paths)
    except (ConfigError, TrainingDataError, TrainingError, PlatformError, ImportError) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return EXIT_USAGE


def _execute(
    args: argparse.Namespace, config: SFTRunConfig, sha: str, seed: int, paths: RepoPaths
) -> int:  # pragma: no cover - platform only
    checks, report = run_smoke(
        config,
        sha,
        seed=seed,
        steps=args.steps,
        data_dir=Path(args.data_dir) if args.data_dir else paths.generated_dir,
        run_root=Path(args.run_root) if args.run_root else paths.root / DEFAULT_RUN_ROOT,
        paths=paths,
        allow_unverified=args.allow_unverified,
    )
    summary = {"report": report.as_posix(), "passed": passed(checks)}
    summary["checks"] = [asdict(check) for check in checks]
    sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    return EXIT_OK if passed(checks) else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
