"""R-21 smoke test: the seven checks as pure functions, plus CLI refusals (tw_ml.train.smoke)."""

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from tw_ml.datagen.paths import RepoPaths
from tw_ml.train.sft import LossChoice
from tw_ml.train.smoke import (
    EXIT_USAGE,
    Check,
    StepClock,
    dtype_check,
    fast_path_check,
    fast_path_packages,
    forward_check,
    kernel_modules,
    loss_at_step,
    loss_check,
    main,
    median_step_seconds,
    memory_check,
    passed,
    resume_check,
    should_stop,
    time_check,
)


def test_forward_backward_check() -> None:
    ok = forward_check(1.234, grads_finite=True, logits_max_abs=31.5)
    assert (ok.number, ok.status, ok.value) == (1, "pass", 1.234)
    assert "logits max-abs 31.5" in ok.detail
    assert forward_check(math.nan, grads_finite=True, logits_max_abs=None).status == "fail"
    assert forward_check(math.inf, grads_finite=True, logits_max_abs=None).status == "fail"
    assert forward_check(1.0, grads_finite=False, logits_max_abs=None).status == "fail"


def test_dtype_loss_and_memory_checks() -> None:
    assert dtype_check([], 392).status == "pass"
    assert (
        dtype_check(["trainable parameters are not fp32: a (torch.bfloat16)"], 1).status == "fail"
    )
    used = loss_check(LossChoice("chunked_nll", 4, 8), "chunked_nll", [])
    assert (used.status, used.detail) == ("pass", "chunked_nll at batch 4 x 8")
    fallback = loss_check(
        LossChoice("nll", 2, 16), "chunked_nll", ["chunked_nll did not construct"]
    )
    assert fallback.status == "pass"
    assert "fallback" in fallback.detail
    assert memory_check(6.3, 13.0).status == "pass"
    assert memory_check(13.0, 13.0).status == "fail"


def test_time_projection() -> None:
    assert median_step_seconds([30.0, 10.0, 12.0, 11.0]) == 11.0  # the warm-up step is dropped
    assert median_step_seconds([9.0]) == 9.0
    assert median_step_seconds([]) is None
    within = time_check(20.0, 339, 2.0)
    assert within.status == "pass"
    assert within.value == pytest.approx(1.883, abs=1e-3)
    assert time_check(25.0, 339, 2.0).status == "fail"
    assert time_check(None, 339, 2.0).status == "fail"


def test_fast_path_report_is_informational() -> None:
    assert fast_path_check(False, {}, {}).detail.startswith("not a Qwen3.5 base")
    fast = fast_path_check(
        True,
        {"fla": True, "causal_conv1d": True},
        {
            "chunk_gated_delta_rule": "fla.ops.gated_delta_rule",
            "causal_conv1d_fn": "causal_conv1d.cpp",
        },
    )
    assert (fast.status, fast.detail.split(" (")[0]) == ("info", "fast path")
    slow = fast_path_check(
        True, {"fla": False}, {"chunk_gated_delta_rule": "transformers.models.qwen3_5.modeling"}
    )
    assert (slow.status, slow.detail.split(" (")[0]) == ("info", "torch fallback")
    unknown = fast_path_check(True, {"fla": True}, {})
    assert unknown.detail.startswith("unknown: no Gated DeltaNet kernel slot found")
    assert set(fast_path_packages()) == {"fla", "causal_conv1d"}


def test_kernel_modules_reads_the_first_gated_deltanet_layer() -> None:
    def torch_chunk() -> None: ...

    torch_chunk.__module__ = "transformers.models.qwen3_5.modeling_qwen3_5"
    layer = SimpleNamespace(chunk_gated_delta_rule=torch_chunk, causal_conv1d_fn=None)
    assert kernel_modules([SimpleNamespace(), layer]) == {
        "chunk_gated_delta_rule": "transformers.models.qwen3_5.modeling_qwen3_5"
    }
    assert kernel_modules([SimpleNamespace()]) == {}


def test_resume_round_trip_check() -> None:
    history = [
        {"step": 10, "loss": 1.5},
        {"step": 11, "loss": 1.25},
        {"step": 11, "eval_loss": 9.0},
    ]
    assert loss_at_step(history, 11) == 1.25
    assert loss_at_step(history, 12) is None
    assert resume_check(1.25, 1.2504, step=11, tolerance=1e-3).status == "pass"
    assert resume_check(1.25, 1.26, step=11, tolerance=1e-3).status == "fail"
    assert resume_check(None, 1.25, step=11, tolerance=1e-3).status == "fail"


def test_step_clock_and_stop() -> None:
    ticks = iter([1.0, 3.5, 4.0, 7.0])
    clock = StepClock(clock=lambda: next(ticks))
    clock.end()  # an end without a begin is ignored
    clock.begin()
    clock.end()
    clock.begin()
    clock.end()
    assert clock.durations == [2.5, 3.0]
    assert should_stop(11, 11)
    assert not should_stop(10, 11)
    assert not should_stop(10, None)


def test_verdict() -> None:
    checks = [Check(1, "a", "pass", ""), Check(6, "b", "info", "")]
    assert passed(checks)
    assert not passed([*checks, Check(7, "c", "fail", "")])


@pytest.mark.parametrize(
    ("argv", "fragment"),
    [
        (["--config", "encoder_modernbert.yaml"], "for SFT configs"),
        (["--config", "sft_qwen35_2b.yaml", "--steps", "1"], "at least 2"),
        (["--config", "sft_qwen35_2b.yaml"], "--allow-unverified"),
        (
            ["--config", "sft_qwen35_2b.yaml", "--seed", "7", "--allow-unverified"],
            "configured seeds",
        ),
        (["--config", "missing.yaml"], "not found"),
    ],
)
def test_cli_refusals(
    paths: RepoPaths, capsys: pytest.CaptureFixture[str], argv: list[str], fragment: str
) -> None:
    argv = [
        str(paths.configs_dir / argv[1]) if a == argv[1] and i == 1 else a
        for i, a in enumerate(argv)
    ]
    assert main(argv, paths=paths) == EXIT_USAGE
    assert fragment in capsys.readouterr().err


def test_cli_stops_before_the_platform(
    paths: RepoPaths, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A valid request reaches the platform part, which needs torch (absent here)."""
    code = main(
        [
            "--config",
            str(paths.configs_dir / "sft_qwen35_2b.yaml"),
            "--allow-unverified",
            "--run-root",
            str(tmp_path),
        ],
        paths=paths,
    )
    assert code == EXIT_USAGE
    assert "ModuleNotFoundError" in capsys.readouterr().err
