"""E3 zero-shot bake-off driver (spec v1.1 §9.5, §9.9; A-02; ERPROT slm-model-selection).

``python -m tw_ml.eval.bakeoff run`` sends every ticket of an open split to each candidate via
Ollama's raw ``POST /api/generate`` and writes, per candidate and split, into
``evals/runs/bakeoff/`` (outputs quote val tickets, so the folder must stay out of git):

* ``<id>_<split>.jsonl`` - ``prediction.v1`` records with the validity tier of
  :mod:`tw_ml.eval.repair` and the per-item wall-clock latency, scored by
  ``python -m tw_ml.eval score --experiment E3`` (``make eval-bakeoff``);
* ``<id>_<split>.timings.jsonl`` - per-item server timings (token counts, durations; no text);
* ``<id>_<split>.summary.json`` - ``bakeoff_summary.v1``: validity counts, latency percentiles,
  prompt and decode token rates and the M-08 risk check.

``--mode cpu-sample`` runs a fixed 50-ticket val sample with ``num_gpu: 0`` and
``num_thread: 8`` (files ``<id>_val.cpu.*``): the early M-08 check on the dev laptop.
``--unconstrained`` repeats a run without the decoding schema (``.free`` files, system id
``+unconstrained``), because §9.4 reports E3 with and without the constraint on val.
``--limit N`` is a smoke run (``*.smoke.*`` files, never matched by ``make eval-bakeoff``), and
``--dry-run`` checks the config, the holdout guard, the inputs, the prompt formats and the
rendering without any HTTP call. ``rank`` (:mod:`tw_ml.eval.bakeoff_rank`) computes the §9.5
score of the complete runs and writes the ranking JSON.

Protocol, identical for every candidate: the ``triage.v1`` prompt assembled with the candidate's
``prompt_format.json`` (:mod:`tw_ml.export.prompt_format`), sent with ``raw: true``,
``stream: false``, ``format`` = the decoding schema, ``truncate: false`` and the options of
``ml/configs/bakeoff.yaml`` (temperature 0, ``num_ctx`` 8192, ``num_predict`` 512, seed 42).
Nonces are derived from the record ids, so a rerun renders byte-identical prompts. A fixed
synthetic warm-up request loads the model first and is not timed.

Guards: sealed splits are refused unconditionally (model selection never sees them; there is no
unseal flag). Unverified candidates run only with ``--allow-unverified``, which every summary
records. The preflight requires the Ollama version of the config, the local
``tw-bakeoff-<id>`` model at ``Q4_K_M`` (and its digest, once pinned) and a prompt format whose
goldens verify. This module never pulls or creates a model: the owner builds the artifacts
(ml/configs/README.md, "Bake-off artifacts"). Nothing here logs ticket or completion text.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal
from uuid import UUID, uuid4

import httpx
import numpy as np
from pydantic import AwareDatetime, BaseModel, ConfigDict

from tw_ml.baselines.rules import read_tickets
from tw_ml.datagen.paths import RepoPaths, default_paths
from tw_ml.datagen.records import TicketPayload
from tw_ml.datagen.taxonomy import Taxonomy, TaxonomyError, load_json_schema, load_taxonomy
from tw_ml.eval.bakeoff_config import (
    VERIFY,
    BakeoffConfig,
    BakeoffConfigError,
    Candidate,
    load_bakeoff_config,
)
from tw_ml.eval.data import EvalDataError, PredictionRecord, file_sha256
from tw_ml.eval.holdout import HoldoutError, authorize, load_subsets
from tw_ml.eval.ollama import LocalModel, OllamaClient, OllamaError, canonical_name
from tw_ml.eval.repair import Classified, classify_output
from tw_ml.eval.report import git_sha, tool_versions
from tw_ml.export.prompt_format import (
    PromptFormat,
    PromptFormatError,
    load_prompt_format,
    runtime_prompt,
    verify_goldens,
)
from tw_ml.prompts import PromptError, TriagePrompt, derive_nonce, load_triage_prompt

SUMMARY_VERSION: Final = "bakeoff_summary.v1"
SYSTEM_PREFIX: Final = "tw-e3-zeroshot"
CONFIG_FILE: Final = "bakeoff.yaml"
EXIT_OK: Final = 0
EXIT_ABORTED: Final = 1
EXIT_USAGE: Final = 2
NS_PER_MS: Final = 1_000_000
MS_PER_S: Final = 1000.0
RunMode = Literal["accuracy", "cpu_sample"]
PHASE: Final = re.compile(r"^P(?:[0-9]|1[01])$")
BASE_URL: Final = re.compile(r"^https?://[^\s/]+(/\S*)?$")
WARMUP_TICKET: Final[Mapping[str, str]] = {
    "customer_tier": "business",
    "channel": "web_form",
    "subject": "Warm-up request",
    "message": "This fixed warm-up request loads the model. It belongs to no split.",
}
M08_NOTE: Final = (
    "early risk check: sequential single-stream triage calls on this machine; the P10 M-08 "
    "benchmark measures E2E latency at concurrency 2 on the reference box"
)


class BakeoffError(ValueError):
    """Raised for unusable inputs, a failed preflight or a refused split (no ticket text)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Stats(_Model):
    """Percentiles of one per-item quantity (``None`` without data)."""

    n: int
    p50: float | None = None
    p95: float | None = None
    mean: float | None = None
    max: float | None = None


class LatencySummary(_Model):
    """Latency and throughput of one run.

    Attributes:
        hardware: ``cpu`` when the CPU options were sent (the M-08 check applies), else
            ``default``.
        wall_ms: Client wall time per triage call (the triage latency).
        latency_term: ``min(1, target / triage P50)`` of the §9.5 score (CPU runs only).
    """

    hardware: Literal["cpu", "default"]
    wall_ms: Stats
    server_total_ms: Stats
    prompt_eval_count: Stats
    eval_count: Stats
    prompt_tokens_per_s: Stats
    decode_tokens_per_s: Stats
    decode_tokens_per_s_aggregate: float | None = None
    triage_p50_s: float | None = None
    triage_p95_s: float | None = None
    m08_p50_ok: bool | None = None
    m08_p95_ok: bool | None = None
    latency_term: float | None = None
    note: str = M08_NOTE


class CandidateSummary(_Model):
    """``bakeoff_summary.v1``: one candidate on one split in one mode."""

    schema_version: Literal["bakeoff_summary.v1"] = SUMMARY_VERSION
    run_id: UUID
    created_at: AwareDatetime
    status: Literal["complete", "aborted"]
    abort_reason: str | None = None
    candidate_id: str
    system_id: str
    split: str
    mode: RunMode
    constrained: bool = True
    smoke_limit: int | None = None
    n_items: int
    n_predicted: int
    verified: bool
    unverified: tuple[str, ...] = ()
    validity: dict[str, int]
    failures: dict[str, int]
    repair_actions: dict[str, int]
    latency: LatencySummary
    ollama: dict[str, Any]
    request: dict[str, Any]
    prompt: dict[str, Any]
    holdout: dict[str, Any]
    files: dict[str, str]
    provenance: dict[str, Any]
    notes: tuple[str, ...] = ()


def run_tag(
    candidate_id: str, split: str, mode: RunMode, *, smoke: bool, constrained: bool = True
) -> str:
    """File stem of a run: ``<id>_<split>`` plus ``.free``, ``.cpu`` and ``.smoke`` suffixes.

    Args:
        candidate_id: Candidate id.
        split: Split.
        mode: Run mode.
        smoke: A ``--limit`` smoke run.
        constrained: The decoding schema was sent (``.free`` marks unconstrained runs).

    Returns:
        The stem (full constrained runs match ``make eval-bakeoff``'s ``*_val.jsonl`` glob;
        other runs do not).
    """
    tag = f"{candidate_id}_{split}"
    if not constrained:
        tag += ".free"
    if mode == "cpu_sample":
        tag += ".cpu"
    return tag + ".smoke" if smoke else tag


# --------------------------------------------------------------------------- measurements


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    """What one triage call produced (a ``.timings.jsonl`` row; never any text).

    Durations are milliseconds; ``None`` where the call failed or Ollama did not report it.
    """

    record_id: str
    validity: str
    actions: tuple[str, ...]
    error: str | None
    http_status: int | None
    attempts: int
    done_reason: str | None
    wall_ms: float | None
    server_total_ms: float | None
    load_ms: float | None
    prompt_eval_count: int | None
    prompt_eval_ms: float | None
    eval_count: int | None
    eval_ms: float | None
    prompt_chars: int

    def row(self) -> dict[str, Any]:
        """The JSONL row."""
        return {
            "record_id": self.record_id,
            "validity": self.validity,
            "actions": list(self.actions),
            "error": self.error,
            "http_status": self.http_status,
            "attempts": self.attempts,
            "done_reason": self.done_reason,
            "wall_ms": self.wall_ms,
            "server_total_ms": self.server_total_ms,
            "load_ms": self.load_ms,
            "prompt_eval_count": self.prompt_eval_count,
            "prompt_eval_ms": self.prompt_eval_ms,
            "eval_count": self.eval_count,
            "eval_ms": self.eval_ms,
            "prompt_chars": self.prompt_chars,
        }


def stats(values: Sequence[float]) -> Stats:
    """Median, 95th percentile (linear interpolation), mean and maximum.

    Args:
        values: Per-item values.

    Returns:
        The statistics, rounded to 3 decimals (``n = 0`` gives ``None`` values).
    """
    if not values:
        return Stats(n=0)
    array = np.asarray(values, dtype=np.float64)
    return Stats(
        n=len(values),
        p50=round(float(np.percentile(array, 50)), 3),
        p95=round(float(np.percentile(array, 95)), 3),
        mean=round(float(array.mean()), 3),
        max=round(float(array.max()), 3),
    )


def _rate(tokens: int | None, milliseconds: float | None) -> float | None:
    if tokens is None or milliseconds is None or tokens <= 0 or milliseconds <= 0:
        return None
    return tokens / (milliseconds / MS_PER_S)


def _present(values: Sequence[float | int | None]) -> list[float]:
    return [float(v) for v in values if v is not None]


def latency_summary(
    outcomes: Sequence[ItemOutcome], *, cpu: bool, config: BakeoffConfig
) -> LatencySummary:
    """Latency percentiles, token rates and the M-08 check of the answered calls.

    Args:
        outcomes: Per-item outcomes (failed calls without timings are skipped).
        cpu: The CPU options were sent.
        config: Bake-off config (M-08 targets, latency target of the score).

    Returns:
        The summary; the M-08 fields and the latency term are set for CPU runs only.
    """
    answered = [o for o in outcomes if o.wall_ms is not None]
    wall = stats(_present([o.wall_ms for o in answered]))
    eval_tokens = sum(o.eval_count or 0 for o in answered if o.eval_ms)
    eval_ms = sum(o.eval_ms or 0.0 for o in answered if o.eval_count)
    p50_s = wall.p50 / MS_PER_S if cpu and wall.p50 is not None else None
    p95_s = wall.p95 / MS_PER_S if cpu and wall.p95 is not None else None
    target = config.score.latency_target_s
    return LatencySummary(
        hardware="cpu" if cpu else "default",
        wall_ms=wall,
        server_total_ms=stats(_present([o.server_total_ms for o in answered])),
        prompt_eval_count=stats(_present([o.prompt_eval_count for o in answered])),
        eval_count=stats(_present([o.eval_count for o in answered])),
        prompt_tokens_per_s=stats(
            _present([_rate(o.prompt_eval_count, o.prompt_eval_ms) for o in answered])
        ),
        decode_tokens_per_s=stats(_present([_rate(o.eval_count, o.eval_ms) for o in answered])),
        decode_tokens_per_s_aggregate=(
            round(eval_tokens / (eval_ms / MS_PER_S), 3) if eval_tokens and eval_ms else None
        ),
        triage_p50_s=p50_s,
        triage_p95_s=p95_s,
        m08_p50_ok=p50_s <= config.score.m08_p50_s if p50_s is not None else None,
        m08_p95_ok=p95_s <= config.score.m08_p95_s if p95_s is not None else None,
        latency_term=round(min(1.0, target / p50_s), 6) if p50_s else None,
    )


# --------------------------------------------------------------------------- inputs + preflight


@dataclass(frozen=True, slots=True)
class SplitInput:
    """The tickets of one authorized split (labels are never read)."""

    split: str
    path: Path
    items: tuple[tuple[str, TicketPayload], ...]
    origins: Mapping[str, int]
    notes: tuple[str, ...] = ()


def read_split(paths: RepoPaths, split: str, path: Path, *, phase: str) -> SplitInput:
    """Read a split's tickets and pass the holdout guard (sealed data is always refused).

    Args:
        paths: Repository paths (manifests for the hard_dev / val_dev subsets).
        split: Declared split (``val``, ``val_dev`` or ``hard_dev``).
        path: Input JSONL (any P1 row format).
        phase: Current project phase.

    Returns:
        The authorized input.

    Raises:
        BakeoffError: If the file is unusable or the guard refuses it.
    """
    try:
        tickets = read_tickets(path)
        decision = authorize(
            split,
            [(record_id, origin) for record_id, origin, _ in tickets],
            phase=phase,
            i_understand_sealed=False,
            subsets=load_subsets(paths),
        )
    except (EvalDataError, HoldoutError) as exc:
        msg = f"{split}: {type(exc).__name__}: {exc}"
        raise BakeoffError(msg) from None
    items = tuple((record_id, ticket) for record_id, _, ticket in tickets)
    return SplitInput(split, path, items, dict(decision.origins), decision.notes)


def cpu_sample(items: Sequence[tuple[str, TicketPayload]], n: int, seed: int) -> list[int]:
    """Indices of a fixed pseudo-random sample, independent of the file order.

    Args:
        items: ``(record_id, ticket)`` pairs.
        n: Sample size (all items when larger).
        seed: Sample seed.

    Returns:
        Sorted indices into ``items``.
    """

    def key(index: int) -> str:
        return hashlib.sha256(f"{seed}:{items[index][0]}".encode()).hexdigest()

    return sorted(sorted(range(len(items)), key=key)[:n])


@dataclass(slots=True)
class Prepared:
    """A candidate after the local (no-HTTP) and server checks.

    Attributes:
        blocking: Problems that stop the run.
        unverified: Unverified items; they block unless ``--allow-unverified`` is passed.
        local: The local Ollama model, after the server preflight.
    """

    candidate: Candidate
    fmt: PromptFormat | None = None
    fmt_sha256: str | None = None
    blocking: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    local: LocalModel | None = None


def prepare_candidate(candidate: Candidate, paths: RepoPaths, *, prompt_version: str) -> Prepared:
    """Check what can be checked without a server: verification state and the prompt format.

    Args:
        candidate: Candidate.
        paths: Repository paths (the prompt format path is repository-relative).
        prompt_version: The configured triage prompt version.

    Returns:
        The prepared candidate.
    """
    prepared = Prepared(candidate)
    if candidate.verify_before_run:
        prepared.unverified.append("verify_before_run is true")
    if not candidate.pinned:
        prepared.unverified.append(f"hf_revision is {VERIFY}")
    if candidate.ollama_digest is None:
        prepared.unverified.append("ollama_digest is not pinned")
    fmt_path = paths.root / candidate.prompt_format
    try:
        fmt = load_prompt_format(fmt_path)
        verify_goldens(fmt)
    except PromptFormatError as exc:
        prepared.blocking.append(f"prompt format: {exc}")
        return prepared
    prepared.fmt, prepared.fmt_sha256 = fmt, file_sha256(fmt_path)
    if fmt.base_model != candidate.hf_repo:
        prepared.blocking.append(f"prompt format was derived from {fmt.base_model}")
    if candidate.pinned and fmt.base_revision != candidate.hf_revision:
        prepared.blocking.append("prompt format revision differs from hf_revision")
    if not fmt.goldens:
        prepared.unverified.append("prompt format has no golden renderings")
    elif fmt.golden_prompt_version != prompt_version:
        prepared.unverified.append(
            f"prompt format goldens use {fmt.golden_prompt_version}, not {prompt_version}"
        )
    return prepared


def gate_unverified(prepared: Sequence[Prepared], *, allow_unverified: bool) -> None:
    """Turn unverified items into blocking problems unless explicitly allowed.

    Args:
        prepared: Prepared candidates (updated in place).
        allow_unverified: ``--allow-unverified``.
    """
    if allow_unverified:
        return
    for item in prepared:
        if item.unverified:
            item.blocking.append(
                "unverified (" + "; ".join(item.unverified) + "): verify, pin and set "
                "verify_before_run: false, or pass --allow-unverified"
            )


def _digest(value: str | None) -> str | None:
    return value.removeprefix("sha256:") if value else None


def preflight_server(
    client: OllamaClient, prepared: Sequence[Prepared], config: BakeoffConfig
) -> tuple[str | None, list[str]]:
    """Check the server version and every candidate's local model (never pulls anything).

    Args:
        client: Ollama client.
        prepared: Prepared candidates (``local``, ``blocking`` and ``unverified`` updated).
        config: Bake-off config.

    Returns:
        The server version and run-level blocking problems.
    """
    try:
        version = client.version()
        models = client.local_models()
    except OllamaError as exc:
        return None, [f"Ollama preflight failed ({exc.kind}): {exc}"]
    if version != config.ollama.version:
        mismatch = (
            f"Ollama {version} is running but the config pins {config.ollama.version} "
            f"(llama.cpp {config.ollama.llama_cpp_build} converts the GGUFs)"
        )
        for item in prepared:
            item.unverified.append(mismatch)
    for item in prepared:
        name = canonical_name(item.candidate.ollama_model)
        local = models.get(name)
        if local is None:
            item.blocking.append(
                f"{name} is not available locally; build it (ml/configs/README.md). "
                "This tool never pulls or creates models"
            )
            continue
        item.local = local
        level = (local.quantization_level or "unknown").upper()
        if level != item.candidate.quantization.upper():
            item.blocking.append(f"{name} is {level}, expected {item.candidate.quantization}")
        pinned = item.candidate.ollama_digest
        if pinned is not None and _digest(local.digest) != pinned:
            item.blocking.append(f"{name} digest differs from the pinned ollama_digest")
    return version, []


# --------------------------------------------------------------------------- running


@dataclass(frozen=True, slots=True)
class RunContext:
    """Everything a run shares across candidates and splits."""

    paths: RepoPaths
    config: BakeoffConfig
    config_sha256: str
    config_file: str
    prompt: TriagePrompt
    schema: Mapping[str, Any]
    schema_file: str
    schema_sha256: str
    taxonomy: Taxonomy
    out_dir: Path
    now: datetime
    phase: str
    ollama_version: str | None
    constrained: bool = True


def system_id(
    candidate: Candidate, local: LocalModel | None, prompt: TriagePrompt, *, constrained: bool
) -> str:
    """The ``system_id`` of a candidate's predictions (names the exact model artifact).

    Args:
        candidate: Candidate.
        local: Its local Ollama model (digest).
        prompt: Triage prompt.
        constrained: The decoding schema was sent.

    Returns:
        ``tw-e3-zeroshot-<id>@<digest12>+<prompt version>``, plus ``+unconstrained``.
    """
    digest = (_digest(local.digest) if local is not None else None) or "unpinned"
    suffix = "" if constrained else "+unconstrained"
    return f"{SYSTEM_PREFIX}-{candidate.id}@{digest[:12]}+{prompt.version}{suffix}"


def build_payload(
    ctx: RunContext, candidate: Candidate, fmt: PromptFormat, prompt_text: str, *, cpu: bool
) -> dict[str, Any]:
    """The ``/api/generate`` body (spec §9.5 protocol; no ``format`` for unconstrained runs).

    Args:
        ctx: Run context.
        candidate: Candidate.
        fmt: Its prompt format (stop tokens).
        prompt_text: The raw prompt.
        cpu: Add the CPU options (``num_gpu``, ``num_thread``).

    Returns:
        The request body.
    """
    request = ctx.config.request
    options: dict[str, Any] = dict(request.options)
    if cpu:
        options.update(request.cpu_options)
    options["stop"] = list(fmt.stop)
    body: dict[str, Any] = {
        "model": candidate.ollama_model,
        "prompt": prompt_text,
        "raw": request.raw,
        "stream": request.stream,
    }
    if ctx.constrained:
        body["format"] = dict(ctx.schema)
    body.update(
        {
            "options": options,
            "truncate": request.truncate,
            "shift": request.shift,
            "keep_alive": ctx.config.ollama.keep_alive,
        }
    )
    return body


def nonce_salt(config: BakeoffConfig) -> str:
    """Salt of the per-record nonces (config salt and decoding seed).

    Args:
        config: Bake-off config.

    Returns:
        The salt.
    """
    return f"{config.sampling.nonce_salt}:{config.request.options['seed']}"


def _ms(nanoseconds: int | None) -> float | None:
    return round(nanoseconds / NS_PER_MS, 3) if nanoseconds is not None else None


def failed_outcome(
    record_id: str,
    kind: str,
    *,
    status: int | None = None,
    attempts: int = 0,
    prompt_chars: int = 0,
) -> tuple[ItemOutcome, Classified]:
    """The measurement row and outcome of a call that produced no completion.

    Args:
        record_id: Record id.
        kind: Failure kind (``http_4xx``, ``timeout``, ``prompt_error``...).
        status: HTTP status, if a response arrived.
        attempts: Attempts made.
        prompt_chars: Size of the prompt that was sent.

    Returns:
        A ``failed_fallback`` row without timings, and its outcome.
    """
    outcome = ItemOutcome(
        record_id=record_id,
        validity="failed_fallback",
        actions=(kind,),
        error=kind,
        http_status=status,
        attempts=attempts,
        done_reason=None,
        wall_ms=None,
        server_total_ms=None,
        load_ms=None,
        prompt_eval_count=None,
        prompt_eval_ms=None,
        eval_count=None,
        eval_ms=None,
        prompt_chars=prompt_chars,
    )
    return outcome, Classified("failed_fallback", None, (kind,))


def triage_item(
    ctx: RunContext,
    client: OllamaClient,
    prepared: Prepared,
    record_id: str,
    ticket: TicketPayload,
    *,
    cpu: bool,
) -> tuple[ItemOutcome, Classified]:
    """Render, send and classify one ticket.

    Args:
        ctx: Run context.
        client: Ollama client.
        prepared: Prepared candidate (with its prompt format).
        record_id: Record id (nonce key).
        ticket: Ticket.
        cpu: CPU sample mode.

    Returns:
        The measurement row and the validity outcome.
    """
    fmt = prepared.fmt
    if fmt is None:  # pragma: no cover - the preflight blocks candidates without a format
        msg = "candidate has no prompt format"
        raise BakeoffError(msg)
    nonce = derive_nonce(record_id, salt=nonce_salt(ctx.config))
    try:
        rendered = ctx.prompt.render(ticket, nonce=nonce, special_tokens=fmt.special_tokens)
    except PromptError:
        return failed_outcome(record_id, "prompt_error")
    text = runtime_prompt(fmt, rendered.system, rendered.user)
    try:
        result = client.generate(build_payload(ctx, prepared.candidate, fmt, text, cpu=cpu))
    except OllamaError as exc:
        return failed_outcome(
            record_id, exc.kind, status=exc.status, attempts=exc.attempts, prompt_chars=len(text)
        )
    classified = classify_output(
        result.response, truncated=result.done_reason == "length", taxonomy=ctx.taxonomy
    )
    outcome = ItemOutcome(
        record_id=record_id,
        validity=classified.validity,
        actions=classified.actions,
        error=None,
        http_status=httpx.codes.OK,
        attempts=result.attempts,
        done_reason=result.done_reason,
        wall_ms=round(result.wall_ms, 3),
        server_total_ms=_ms(result.total_ns),
        load_ms=_ms(result.load_ns),
        prompt_eval_count=result.prompt_eval_count,
        prompt_eval_ms=_ms(result.prompt_eval_ns),
        eval_count=result.eval_count,
        eval_ms=_ms(result.eval_ns),
        prompt_chars=len(text),
    )
    return outcome, classified


def warm_up(
    ctx: RunContext, client: OllamaClient, prepared: Prepared, *, cpu: bool
) -> dict[str, Any]:
    """Load the model with a fixed synthetic ticket (not timed, not recorded as a prediction).

    Args:
        ctx: Run context.
        client: Ollama client.
        prepared: Prepared candidate.
        cpu: CPU sample mode (the model must load with the same options).

    Returns:
        ``ok``, the error kind and the wall and load times.
    """
    ticket = TicketPayload.model_validate(dict(WARMUP_TICKET))
    outcome, _ = triage_item(ctx, client, prepared, "warmup", ticket, cpu=cpu)
    return {
        "ok": outcome.error is None,
        "error": outcome.error,
        "wall_ms": outcome.wall_ms,
        "load_ms": outcome.load_ms,
    }


def loaded_info(client: OllamaClient, candidate: Candidate) -> dict[str, Any]:
    """Where the loaded model runs (``/api/ps``); empty when the server does not say.

    Args:
        client: Ollama client.
        candidate: Candidate.

    Returns:
        ``size``, ``size_vram`` and ``context_length`` of the loaded model.
    """
    try:
        loaded = client.loaded_models().get(canonical_name(candidate.ollama_model))
    except OllamaError:
        return {}
    if loaded is None:
        return {}
    return {
        "size": loaded.size,
        "size_vram": loaded.size_vram,
        "context_length": loaded.context_length,
    }


@dataclass(frozen=True, slots=True)
class RunFiles:
    """The three output files of one run."""

    predictions: Path
    timings: Path
    summary: Path

    @classmethod
    def for_tag(cls, out_dir: Path, tag: str) -> "RunFiles":
        """Files of a run tag.

        Args:
            out_dir: Output folder.
            tag: :func:`run_tag`.

        Returns:
            The paths.
        """
        return cls(
            out_dir / f"{tag}.jsonl",
            out_dir / f"{tag}.timings.jsonl",
            out_dir / f"{tag}.summary.json",
        )


def _display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def select_items(
    split_input: SplitInput, config: BakeoffConfig, *, mode: RunMode, sample_n: int | None,
    limit: int | None,
) -> list[tuple[str, TicketPayload]]:  # fmt: skip
    """The items one run sends: all, or the CPU sample; then the smoke ``limit``.

    Args:
        split_input: Authorized split.
        config: Bake-off config (sample size and seed).
        mode: Run mode.
        sample_n: CPU sample size override.
        limit: Smoke-run limit.

    Returns:
        ``(record_id, ticket)`` pairs in file order.
    """
    items = split_input.items
    if mode == "cpu_sample":
        n = sample_n or config.sampling.cpu_sample_n
        chosen = [items[i] for i in cpu_sample(items, n, config.sampling.sample_seed)]
    else:
        chosen = list(items)
    return chosen[:limit] if limit is not None else chosen


def run_split(
    ctx: RunContext,
    client: OllamaClient,
    prepared: Prepared,
    split_input: SplitInput,
    *,
    mode: RunMode,
    sample_n: int | None = None,
    limit: int | None = None,
) -> CandidateSummary:
    """Run one candidate on one split and write its predictions, timings and summary.

    Files are written as the run goes, so an aborted run keeps what it measured; the summary
    says whether the run is complete.

    Args:
        ctx: Run context.
        client: Ollama client.
        prepared: Prepared candidate (passed the preflight).
        split_input: Authorized split.
        mode: ``accuracy`` (all items, default hardware) or ``cpu_sample``.
        sample_n: CPU sample size override.
        limit: Smoke-run limit (``.smoke`` files).

    Returns:
        The summary (also written to ``<tag>.summary.json``).
    """
    candidate, cpu = prepared.candidate, mode == "cpu_sample"
    items = select_items(split_input, ctx.config, mode=mode, sample_n=sample_n, limit=limit)
    tag = run_tag(
        candidate.id, split_input.split, mode, smoke=limit is not None, constrained=ctx.constrained
    )
    files = RunFiles.for_tag(ctx.out_dir, tag)
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    sid = system_id(candidate, prepared.local, ctx.prompt, constrained=ctx.constrained)
    notes = list(split_input.notes)
    outcomes: list[ItemOutcome] = []
    status: Literal["complete", "aborted"] = "complete"
    abort_reason: str | None = None
    with (
        files.predictions.open("w", encoding="utf-8", newline="\n") as predictions,
        files.timings.open("w", encoding="utf-8", newline="\n") as timings,
    ):
        warm = warm_up(ctx, client, prepared, cpu=cpu)
        loaded = loaded_info(client, candidate)
        notes.extend(_placement_notes(loaded, ctx.config, cpu=cpu))
        if not warm["ok"]:
            status, abort_reason = "aborted", f"warm-up failed ({warm['error']})"
        consecutive = 0
        for record_id, ticket in items if status == "complete" else ():
            outcome, classified = triage_item(ctx, client, prepared, record_id, ticket, cpu=cpu)
            record = PredictionRecord(
                record_id=record_id,
                system_id=sid,
                validity=classified.validity,
                output=classified.labels,
                latency_ms=outcome.wall_ms,
            )
            predictions.write(record.model_dump_json() + "\n")
            timings.write(json.dumps(outcome.row(), sort_keys=True) + "\n")
            outcomes.append(outcome)
            consecutive = consecutive + 1 if outcome.error else 0
            if consecutive >= ctx.config.ollama.max_consecutive_failures:
                status = "aborted"
                abort_reason = f"{consecutive} consecutive failed calls (last: {outcome.error})"
                break
    run_record = RunRecord(
        mode=mode,
        limit=limit,
        system=sid,
        n_items=len(items),
        outcomes=tuple(outcomes),
        status=status,
        abort_reason=abort_reason,
        warm=warm,
        loaded=loaded,
        notes=tuple(notes),
    )
    summary = build_summary(ctx, prepared, split_input, files, run_record)
    text = summary.model_dump_json(indent=2) + "\n"
    files.summary.write_text(text, encoding="utf-8", newline="\n")
    return summary


@dataclass(frozen=True, slots=True)
class RunRecord:
    """What one run did (input of :func:`build_summary`)."""

    mode: RunMode
    limit: int | None
    system: str
    n_items: int
    outcomes: tuple[ItemOutcome, ...]
    status: Literal["complete", "aborted"]
    abort_reason: str | None
    warm: Mapping[str, Any]
    loaded: Mapping[str, Any]
    notes: tuple[str, ...]


def build_summary(
    ctx: RunContext,
    prepared: Prepared,
    split_input: SplitInput,
    files: RunFiles,
    run: RunRecord,
) -> CandidateSummary:
    """Assemble the ``bakeoff_summary.v1`` of a finished (or aborted) run.

    Args:
        ctx: Run context.
        prepared: Prepared candidate.
        split_input: Authorized split.
        files: Output files (already written).
        run: What the run did.

    Returns:
        The summary.
    """
    candidate, local, fmt, root = prepared.candidate, prepared.local, prepared.fmt, ctx.paths.root
    cpu = run.mode == "cpu_sample"
    outcomes = run.outcomes
    validity = Counter(o.validity for o in outcomes)
    failures = Counter(a for o in outcomes if o.validity == "failed_fallback" for a in o.actions)
    repairs = Counter(a for o in outcomes if o.validity == "repaired_l1" for a in o.actions)
    options: dict[str, Any] = dict(ctx.config.request.options)
    if cpu:
        options.update(ctx.config.request.cpu_options)
    options["stop"] = list(fmt.stop) if fmt is not None else []
    request = ctx.config.request
    return CandidateSummary(
        run_id=uuid4(),
        created_at=ctx.now,
        status=run.status,
        abort_reason=run.abort_reason,
        candidate_id=candidate.id,
        system_id=run.system,
        split=split_input.split,
        mode=run.mode,
        constrained=ctx.constrained,
        smoke_limit=run.limit,
        n_items=run.n_items,
        n_predicted=len(outcomes),
        verified=not prepared.unverified,
        unverified=tuple(prepared.unverified),
        validity={
            tier: validity.get(tier, 0)
            for tier in ("first_pass", "repaired_l1", "repaired_l2", "failed_fallback")
        },
        failures=dict(sorted(failures.items())),
        repair_actions=dict(sorted(repairs.items())),
        latency=latency_summary(outcomes, cpu=cpu, config=ctx.config),
        ollama={
            "version": ctx.ollama_version,
            "pinned_version": ctx.config.ollama.version,
            "llama_cpp_build": ctx.config.ollama.llama_cpp_build,
            "model": canonical_name(candidate.ollama_model),
            "digest": _digest(local.digest) if local is not None else None,
            "quantization_level": local.quantization_level if local is not None else None,
            "parameter_size": local.parameter_size if local is not None else None,
            "family": local.family if local is not None else None,
            "loaded": dict(run.loaded),
            "warmup": dict(run.warm),
        },
        request={
            "endpoint": "/api/generate",
            "raw": request.raw,
            "stream": request.stream,
            "truncate": request.truncate,
            "shift": request.shift,
            "keep_alive": ctx.config.ollama.keep_alive,
            "options": options,
            "format_file": ctx.schema_file if ctx.constrained else None,
            "format_sha256": ctx.schema_sha256 if ctx.constrained else None,
        },
        prompt={
            "version": ctx.prompt.version,
            "sha256": ctx.prompt.prompt_sha256,
            "prompt_format_file": candidate.prompt_format,
            "prompt_format_sha256": prepared.fmt_sha256,
            "chat_template_sha256": fmt.chat_template_sha256 if fmt is not None else None,
            "runtime_adds_bos": fmt.runtime_adds_bos if fmt is not None else None,
            "nonce": "derive_nonce(record_id, salt)",
            "nonce_salt": nonce_salt(ctx.config),
        },
        holdout={
            "split": split_input.split,
            "origins": dict(split_input.origins),
            "phase": ctx.phase,
            "sealed": False,
        },
        files={
            "predictions": _display(files.predictions, root),
            "predictions_sha256": file_sha256(files.predictions),
            "timings": _display(files.timings, root),
            "timings_sha256": file_sha256(files.timings),
        },
        provenance={
            "config_file": ctx.config_file,
            "config_version": ctx.config.version,
            "config_sha256": ctx.config_sha256,
            "hf_repo": candidate.hf_repo,
            "hf_revision": candidate.hf_revision,
            "input_file": _display(split_input.path, root),
            "input_sha256": file_sha256(split_input.path),
            "git_sha": git_sha(root),
            "tool_versions": tool_versions(),
        },
        notes=run.notes,
    )


def _placement_notes(loaded: Mapping[str, Any], config: BakeoffConfig, *, cpu: bool) -> list[str]:
    notes: list[str] = []
    context = loaded.get("context_length")
    wanted = config.request.options["num_ctx"]
    if context is not None and context != wanted:
        notes.append(f"loaded context length {context} differs from num_ctx {wanted}")
    vram = loaded.get("size_vram")
    if cpu and vram:
        notes.append("the model is (partly) in GPU memory despite num_gpu 0")
    if not loaded:
        notes.append("the server did not report the loaded model (/api/ps)")
    return notes


# --------------------------------------------------------------------------- CLI


def select_candidates(
    config: BakeoffConfig, ids: Sequence[str] | None, *, include_optional: bool
) -> list[Candidate]:
    """The candidates of a run: the named ones, or every non-optional one (plus optional).

    Args:
        config: Bake-off config.
        ids: ``--candidate`` values.
        include_optional: ``--include-optional``.

    Returns:
        Candidates in config order.
    """
    if ids:
        for candidate_id in ids:
            config.candidate(candidate_id)  # unknown ids fail loudly
        return [c for c in config.candidates if c.id in set(ids)]
    return [c for c in config.candidates if include_optional or not c.optional]


def plan_splits(
    args: argparse.Namespace, config: BakeoffConfig, paths: RepoPaths
) -> tuple[list[tuple[str, Path]], list[str]]:
    """Which splits to read from which files.

    Default: val, plus hard_dev when its gold file exists; the CPU sample reads val only.

    Args:
        args: Parsed arguments.
        config: Bake-off config.
        paths: Repository paths.

    Returns:
        ``(split, file)`` pairs and notes about skipped splits.

    Raises:
        BakeoffError: If the arguments are inconsistent or a named input is missing.
    """
    cpu = args.mode == "cpu-sample"
    requested: list[str] = list(dict.fromkeys(args.split or ()))
    if cpu and requested not in ([], ["val"]):
        msg = "--mode cpu-sample runs on val only (spec §9.5 latency sample)"
        raise BakeoffError(msg)
    if args.input and len(requested) != 1:
        msg = "--input needs exactly one --split"
        raise BakeoffError(msg)
    notes: list[str] = []
    if not requested:
        requested = ["val"]
        hard_dev = config.splits.get("hard_dev")
        if not cpu and hard_dev is not None:
            if (paths.root / hard_dev).is_file():
                requested.append("hard_dev")
            else:
                notes.append(f"hard_dev skipped: {hard_dev} does not exist yet")
    planned: list[tuple[str, Path]] = []
    for split in requested:
        if args.input:
            path = Path(args.input)
        elif split in config.splits:
            path = paths.root / config.splits[split]
        else:
            msg = f"no input file configured for {split}; pass --input"
            raise BakeoffError(msg)
        if not path.is_file():
            msg = f"{split} input not found: {_display(path, paths.root)}"
            raise BakeoffError(msg)
        planned.append((split, path))
    return planned, notes


def _positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        msg = "must be a positive integer"
        raise argparse.ArgumentTypeError(msg)
    return number


def _phase(value: str) -> str:
    if not PHASE.fullmatch(value):
        msg = "phase must be P0..P11"
        raise argparse.ArgumentTypeError(msg)
    return value


def _url(value: str) -> str:
    if not BASE_URL.fullmatch(value):
        msg = "must be an http(s) URL such as http://127.0.0.1:11434"
        raise argparse.ArgumentTypeError(msg)
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m tw_ml.eval.bakeoff",
        description="E3 zero-shot bake-off: run candidates through Ollama, then rank them.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run candidates on open splits (val, hard_dev)")
    run.add_argument("--config", help="bake-off config (default ml/configs/bakeoff.yaml)")
    run.add_argument("--candidate", action="append", help="candidate id (repeatable)")
    run.add_argument("--include-optional", action="store_true", help="add optional candidates")
    run.add_argument("--split", action="append", choices=("val", "val_dev", "hard_dev"))
    run.add_argument("--input", help="input JSONL for a single --split")
    run.add_argument("--mode", choices=("accuracy", "cpu-sample"), default="accuracy")
    run.add_argument("--n", type=_positive, help="CPU sample size (default from the config)")
    run.add_argument("--limit", type=_positive, help="smoke run: only the first N items")
    run.add_argument("--out-dir", help="output folder (default from the config)")
    run.add_argument("--base-url", type=_url, help="Ollama URL (default from the config)")
    run.add_argument("--phase", type=_phase, default="P2", help="current project phase")
    run.add_argument("--allow-unverified", action="store_true", help="run unverified candidates")
    run.add_argument("--dry-run", action="store_true", help="check everything, call nothing")
    run.add_argument(
        "--unconstrained",
        action="store_true",
        help="E3 without the decoding schema (spec §9.4: also reported on val)",
    )
    rank = sub.add_parser("rank", help="score complete val runs and write the ranking JSON")
    rank.add_argument("--config", help="bake-off config (default ml/configs/bakeoff.yaml)")
    rank.add_argument("--gold", help="val gold JSONL (default from the config)")
    rank.add_argument("--runs-dir", help="run folder (default from the config)")
    rank.add_argument("--out", help="ranking JSON (default evals/reports/<date>/)")
    rank.add_argument("--date", help="report date folder (default today, UTC)")
    rank.add_argument("--n-resamples", type=_positive, default=10_000, help="bootstrap B")
    rank.add_argument("--phase", type=_phase, default="P2", help="current project phase")
    return parser


def _write(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def config_path(args: argparse.Namespace, paths: RepoPaths) -> Path:
    """The config file of a command (``--config`` or ``ml/configs/bakeoff.yaml``).

    Args:
        args: Parsed arguments.
        paths: Repository paths.

    Returns:
        The path.
    """
    return Path(args.config) if args.config else paths.configs_dir / CONFIG_FILE


def dry_run(
    prepared: Sequence[Prepared],
    inputs: Sequence[SplitInput],
    prompt: TriagePrompt,
    config: BakeoffConfig,
    notes: Sequence[str],
) -> int:
    """Report what a run would do; render every prompt but call nothing.

    Args:
        prepared: Prepared candidates (after the unverified gate).
        inputs: Authorized splits.
        prompt: Triage prompt.
        config: Bake-off config.
        notes: Planning notes.

    Returns:
        0 when a real run could start (server checks aside), 2 when something blocks it.
    """
    rendered, longest = 0, 0
    for split_input in inputs:
        for record_id, ticket in split_input.items:
            nonce = derive_nonce(record_id, salt=nonce_salt(config))
            longest = max(longest, len(prompt.render(ticket, nonce=nonce).user))
            rendered += 1
    report = {
        "dry_run": True,
        "config": config.version,
        "prompt": {
            "version": prompt.version,
            "sha256": prompt.prompt_sha256,
            "system_chars": len(prompt.system),
            "max_user_chars": longest,
            "rendered": rendered,
        },
        "splits": [
            {"split": s.split, "n_items": len(s.items), "origins": dict(s.origins)} for s in inputs
        ],
        "candidates": [
            {
                "id": p.candidate.id,
                "ollama_model": p.candidate.ollama_model,
                "unverified": p.unverified,
                "blocking": p.blocking,
            }
            for p in prepared
        ],
        "notes": [*notes, "server checks (version, local models) run without --dry-run only"],
    }
    _write(json.dumps(report, indent=2))
    return EXIT_USAGE if any(p.blocking for p in prepared) else EXIT_OK


def cmd_run(
    args: argparse.Namespace,
    paths: RepoPaths,
    now: datetime,
    transport: httpx.BaseTransport | None,
    sleep: Callable[[float], None],
) -> int:
    """``run``: preflight everything, then run each candidate on each split."""
    path = config_path(args, paths)
    config, config_sha = load_bakeoff_config(path)
    candidates = select_candidates(config, args.candidate, include_optional=args.include_optional)
    planned, notes = plan_splits(args, config, paths)
    inputs = [read_split(paths, split, file, phase=args.phase) for split, file in planned]
    prompt = load_triage_prompt(config.prompt_version)
    taxonomy = load_taxonomy(paths.schemas_dir)
    schema = load_json_schema(config.decoding_schema, paths.schemas_dir)
    prepared = [prepare_candidate(c, paths, prompt_version=prompt.version) for c in candidates]
    if args.dry_run:
        gate_unverified(prepared, allow_unverified=args.allow_unverified)
        return dry_run(prepared, inputs, prompt, config, notes)
    settings = config.ollama
    with OllamaClient(
        args.base_url or settings.base_url,
        timeout_s=settings.timeout_s,
        connect_timeout_s=settings.connect_timeout_s,
        retries=settings.retries,
        backoff_s=settings.backoff_s,
        transport=transport,
        sleep=sleep,
    ) as client:
        version, problems = preflight_server(client, prepared, config)
        gate_unverified(prepared, allow_unverified=args.allow_unverified)
        blocking = problems + [f"{p.candidate.id}: {b}" for p in prepared for b in p.blocking]
        if blocking:
            sys.stderr.write("Preflight failed:\n  " + "\n  ".join(blocking) + "\n")
            return EXIT_USAGE
        ctx = RunContext(
            paths=paths,
            config=config,
            config_sha256=config_sha,
            config_file=_display(path, paths.root),
            prompt=prompt,
            schema=schema,
            schema_file=f"schemas/json/{config.decoding_schema}",
            schema_sha256=file_sha256(paths.schemas_dir / config.decoding_schema),
            taxonomy=taxonomy,
            out_dir=Path(args.out_dir) if args.out_dir else paths.root / config.output_dir,
            now=now,
            phase=args.phase,
            ollama_version=version,
            constrained=not args.unconstrained,
        )
        mode: RunMode = "cpu_sample" if args.mode == "cpu-sample" else "accuracy"
        summaries = [
            run_split(ctx, client, item, split_input, mode=mode, sample_n=args.n, limit=args.limit)
            for item in prepared
            for split_input in inputs
        ]
    runs = [
        {
            "candidate": s.candidate_id,
            "split": s.split,
            "mode": s.mode,
            "status": s.status,
            "abort_reason": s.abort_reason,
            "n_predicted": s.n_predicted,
            "validity": s.validity,
            "triage_p50_s": s.latency.triage_p50_s,
            "decode_tokens_per_s": s.latency.decode_tokens_per_s.p50,
            "verified": s.verified,
            "predictions": s.files["predictions"],
        }
        for s in summaries
    ]
    _write(json.dumps({"runs": runs, "notes": notes}, indent=2))
    return EXIT_ABORTED if any(s.status == "aborted" for s in summaries) else EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    paths: RepoPaths | None = None,
    now: datetime | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """CLI entry point.

    Args:
        argv: Arguments (defaults to ``sys.argv[1:]``).
        paths: Repository paths override (tests).
        now: Clock override (tests).
        transport: ``httpx`` transport override (tests: ``httpx.MockTransport``).
        sleep: Retry pause (tests: a no-op).

    Returns:
        Exit code: 0 success, 1 a run aborted, 2 usage, data, config, holdout or preflight
        error.
    """
    args = build_parser().parse_args(argv)
    paths = paths or default_paths()
    moment = now or datetime.now(UTC)
    try:
        if args.command == "rank":
            from tw_ml.eval import bakeoff_rank  # noqa: PLC0415 - bakeoff_rank imports this module

            return bakeoff_rank.cmd_rank(args, paths, moment)
        return cmd_run(args, paths, moment, transport, sleep)
    except (
        BakeoffConfigError,
        BakeoffError,
        EvalDataError,
        HoldoutError,
        PromptError,
        PromptFormatError,
        TaxonomyError,
    ) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
