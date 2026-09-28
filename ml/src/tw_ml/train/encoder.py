"""E2 encoder baseline: ModernBERT-base with one linear head per label (spec v1.1 §9.5, §9.7).

* **Heads** come from the exported contracts: each head is a ``TriageModelOutput`` field whose
  ``$ref`` names a taxonomy enum in ``schemas/json/triage_model_output.schema.json``, with that
  enum's values in contract order as its classes (intent 13, priority 4, sentiment 5,
  churn_risk 3, product_area 12, recommended_queue 6).
* **Input**: the metadata JSON line, the subject and the latest customer message, then earlier
  messages newest first, so the 512-token truncation drops the oldest history, never the latest
  message. It carries the same information as the SLM prompt, without the instructions.
* **Training** (``AutoModel`` encoder + heads, fp16 AMP over fp32 weights, SDPA; P2.9): the sum
  of the per-head cross-entropies with inverse-square-root class weights from train frequencies;
  lr 3e-5, batch 32, 5 epochs, warmup 6%, weight decay 0.01; the epoch with the best val intent
  macro-F1 (M-01 semantics) is kept, which is early stopping on val macro-F1.
* **Calibration** (``calibrated_softmax``, ADR-0017): one temperature per head, fitted on val by
  minimizing the NLL of ``softmax(z / T)``, the objective of scikit-learn's
  ``CalibratedClassifierCV(method="temperature")`` (the tests cross-check the two).
* **Output**: ``prediction.v1`` JSONL per open split (val, hard_dev), scored by
  ``python -m tw_ml.eval score --experiment E2 --pred s42=... --pred s1337=... ...``, plus a
  confidence sidecar with the calibrated ``FieldConfidence`` values and ``p_critical``. Fields
  without a head are derived deterministically (no secondary intents, churn signals or entities;
  no human request; ``information_sufficient`` false only for ``other_unclear``; the label-rules
  action of the predicted intent), and every rationale says so.

Pure pieces are tested offline; the torch model and loop are imported lazily and run on the
platform (``python -m tw_ml.train --config ml/configs/encoder_modernbert.yaml --seed N``).
"""

import importlib
import json
import math
import os
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp, softmax

from tw_ml.baselines.rules import read_tickets
from tw_ml.datagen.labelrules import LABEL_RULES_FILE, LabelRules, load_label_rules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import TicketPayload, TriageLabels, utc_iso
from tw_ml.datagen.taxonomy import TRIAGE_OUTPUT_SCHEMA, Taxonomy, load_json_schema, load_taxonomy
from tw_ml.eval.data import EvalDataError, PredictionRecord
from tw_ml.eval.holdout import HoldoutError, authorize, load_subsets
from tw_ml.eval.metrics import OTHER_UNCLEAR
from tw_ml.eval.report import git_sha
from tw_ml.eval.stats import macro_f1_rows
from tw_ml.prompts import metadata_line
from tw_ml.train.config import EncoderRunConfig, check_runnable
from tw_ml.train.data import (
    TRAINING_PHASE,
    DataManifest,
    SFTTokenizer,
    SplitData,
    TrainingData,
    load_training_data,
    split_manifest,
    write_data_manifest,
)
from tw_ml.train.hub import download_resume_state, push_run, resume_decision
from tw_ml.train.runtime import (
    RunPaths,
    assert_platform,
    library_versions,
    mlflow_environment,
    run_tags,
    write_json,
)
from tw_ml.train.sft import batched

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
LOG_T_BOUND: Final = 10.0
"""Search bounds of ``log T`` (scikit-learn's temperature scaling uses the same on ``log 1/T``)."""
CONFIDENCE_METHOD: Final = "calibrated_softmax"
CALIBRATOR_VERSION: Final = "calibrator.v1"
CONFIDENCE_VERSION: Final = "confidence.v1"


class EncoderError(ValueError):
    """Raised for inconsistent heads, labels or logits (no ticket text in messages)."""


@dataclass(frozen=True, slots=True)
class HeadSpec:
    """One classification head.

    Attributes:
        name: ``TriageModelOutput`` field (``intent``, ``priority`` ...).
        enum: Taxonomy enum of the field.
        classes: The enum's values in contract order (class index = position).
    """

    name: str
    enum: str
    classes: tuple[str, ...]

    def index(self, value: str) -> int:
        """Class index of a label value.

        Args:
            value: Enum value.

        Returns:
            Its position in ``classes``.

        Raises:
            EncoderError: If the value is not a class of this head.
        """
        try:
            return self.classes.index(value)
        except ValueError:
            msg = f"{value!r} is not a {self.enum} value"
            raise EncoderError(msg) from None


def head_specs(
    heads: Sequence[str], taxonomy: Taxonomy, schemas_dir: Path | None = None
) -> tuple[HeadSpec, ...]:
    """Head specs of the configured fields, read from the exported output schema.

    Args:
        heads: Field names (``EncoderRunConfig.heads``).
        taxonomy: Taxonomy (enum values).
        schemas_dir: ``schemas/json`` override.

    Returns:
        One spec per field, in the given order.

    Raises:
        EncoderError: If a field is not an enum-valued ``TriageModelOutput`` property.
    """
    properties = load_json_schema(TRIAGE_OUTPUT_SCHEMA, schemas_dir).get("properties", {})
    specs = []
    for name in heads:
        ref = properties.get(name, {}).get("$ref") if isinstance(properties, dict) else None
        enum = ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None
        if enum is None or enum not in taxonomy.enums:
            msg = f"{name} is not an enum field of {TRIAGE_OUTPUT_SCHEMA}"
            raise EncoderError(msg)
        specs.append(HeadSpec(name=name, enum=enum, classes=taxonomy.values(enum)))
    return tuple(specs)


def encoder_text(ticket: TicketPayload) -> str:
    """The encoder input: metadata, subject, latest message, then history newest first.

    Args:
        ticket: The (masked) ticket.

    Returns:
        Newline-joined text; truncation at ``max_length`` cuts the oldest history first.
    """
    lines = [metadata_line(ticket), f"subject: {ticket.subject}", "latest customer message:"]
    lines.append(ticket.message)
    history = ticket.previous_messages
    for back, message in enumerate(reversed(history), start=1):
        lines.append(f"earlier message -{back} ({message.author}, {utc_iso(message.sent_at)}):")
        lines.append(message.body)
    return "\n".join(lines)


def encode_labels(labels: TriageLabels, specs: Sequence[HeadSpec]) -> dict[str, int]:
    """Class indices of one record's labels.

    Args:
        labels: Gold labels.
        specs: Head specs.

    Returns:
        Head name to class index.
    """
    return {spec.name: spec.index(str(getattr(labels, spec.name))) for spec in specs}


def class_weights(targets: Sequence[int], n_classes: int) -> list[float]:
    """Inverse-square-root class weights, normalized to a sample-weighted mean of 1.

    ``w_c = 1 / sqrt(n_c)`` for classes seen in training, scaled so that
    ``sum_c n_c w_c = N``; unseen classes get 0 (they contribute no loss term anyway).

    Args:
        targets: Train class indices of one head.
        n_classes: Classes of the head.

    Returns:
        One weight per class.

    Raises:
        EncoderError: If there are no targets or an index is out of range.
    """
    if not targets:
        msg = "class weights need at least one training label"
        raise EncoderError(msg)
    if min(targets) < 0 or max(targets) >= n_classes:
        msg = "a class index is out of range"
        raise EncoderError(msg)
    counts = Counter(targets)
    raw = [1.0 / math.sqrt(counts[c]) if counts[c] else 0.0 for c in range(n_classes)]
    scale = len(targets) / sum(counts[c] * raw[c] for c in range(n_classes))
    return [weight * scale for weight in raw]


# --------------------------------------------------------------------------- calibration


@dataclass(frozen=True, slots=True)
class TemperatureFit:
    """One head's temperature, fitted on val.

    Attributes:
        temperature: ``T`` of ``softmax(z / T)``.
        nll_before: Mean NLL at ``T = 1``.
        nll_after: Mean NLL at the fitted ``T``.
        n: Val items.
    """

    temperature: float
    nll_before: float
    nll_after: float
    n: int


def _as_logits(logits: Sequence[Sequence[float]] | FloatArray) -> FloatArray:
    array = np.asarray(logits, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] < 2:  # noqa: PLR2004 - 2-D
        msg = "logits must be a non-empty (n, classes >= 2) matrix"
        raise EncoderError(msg)
    return array


def mean_nll(logits: FloatArray, targets: IntArray, temperature: float) -> float:
    """Mean negative log-likelihood of ``softmax(logits / T)`` at the targets.

    Args:
        logits: ``(n, classes)`` logits.
        targets: ``(n,)`` class indices.
        temperature: ``T > 0``.

    Returns:
        The mean NLL.
    """
    scaled = logits / temperature
    picked = scaled[np.arange(targets.size), targets]
    return float(np.mean(logsumexp(scaled, axis=1) - picked))


def fit_temperature(
    logits: Sequence[Sequence[float]] | FloatArray, targets: Sequence[int] | IntArray
) -> TemperatureFit:
    """Fit ``T`` by minimizing the val NLL over ``log T`` in [-10, 10] (bounded Brent).

    Args:
        logits: Val logits of one head.
        targets: Val class indices.

    Returns:
        The fit.

    Raises:
        EncoderError: If the shapes disagree or a target is out of range.
    """
    z = _as_logits(logits)
    y = np.asarray(targets, dtype=np.int64)
    if y.shape != (z.shape[0],) or int(y.min()) < 0 or int(y.max()) >= z.shape[1]:
        msg = "targets must be one in-range class index per logit row"
        raise EncoderError(msg)
    result = minimize_scalar(
        lambda log_t: mean_nll(z, y, math.exp(log_t)),
        bounds=(-LOG_T_BOUND, LOG_T_BOUND),
        method="bounded",
        options={"xatol": 1e-9},
    )
    temperature = math.exp(float(result.x))
    return TemperatureFit(
        temperature=temperature,
        nll_before=mean_nll(z, y, 1.0),
        nll_after=mean_nll(z, y, temperature),
        n=int(y.size),
    )


def calibrated_probabilities(
    logits: Sequence[Sequence[float]] | FloatArray, temperature: float
) -> FloatArray:
    """``softmax(logits / T)`` row-wise.

    Args:
        logits: ``(n, classes)`` logits.
        temperature: Fitted ``T``.

    Returns:
        ``(n, classes)`` probabilities.
    """
    return np.asarray(softmax(_as_logits(logits) / temperature, axis=1), dtype=np.float64)


def intent_macro_f1(gold: Sequence[int], pred: Sequence[int], spec: HeadSpec) -> float:
    """M-01 intent macro-F1: the 12 intents without ``other_unclear``, absent classes score 0.

    Args:
        gold: Gold intent indices.
        pred: Predicted intent indices.
        spec: The intent head.

    Returns:
        The macro-F1 (``best_metric`` of the E2 epochs).
    """
    labels = np.asarray(
        [i for i, c in enumerate(spec.classes) if c != OTHER_UNCLEAR], dtype=np.int64
    )
    value = macro_f1_rows(
        np.asarray(gold, dtype=np.int64),
        np.asarray(pred, dtype=np.int64),
        len(spec.classes),
        labels,
    )
    return float(value[0])


# --------------------------------------------------------------------------- predictions


def decode_labels(
    probabilities: Mapping[str, Sequence[float]],
    specs: Sequence[HeadSpec],
    rules: LabelRules,
    *,
    system_name: str,
) -> TriageLabels:
    """A ``TriageModelOutput``-shaped output from one ticket's head probabilities.

    Args:
        probabilities: Head name to calibrated class probabilities.
        specs: Head specs (must include the intent head).
        rules: Label rules (the R11 action of the predicted intent).
        system_name: Named in the rationale.

    Returns:
        The output; fields without a head follow the module docstring's derivation.
    """
    chosen = {spec.name: spec.classes[int(np.argmax(probabilities[spec.name]))] for spec in specs}
    intent = chosen["intent"]
    sufficient = intent != OTHER_UNCLEAR
    rationale = (
        f"E2 {system_name}: heads {', '.join(chosen)}; secondary intents, churn signals, "
        "entities, human request and information sufficiency are not predicted by this baseline"
    )
    return TriageLabels(
        intent=intent,
        secondary_intents=(),
        priority=chosen["priority"],
        sentiment=chosen["sentiment"],
        churn_risk=chosen["churn_risk"],
        churn_signals=(),
        product_area=chosen["product_area"],
        entities=(),
        recommended_queue=chosen["recommended_queue"],
        recommended_action=rules.expected_action(
            intent, customer_requested_human=False, information_sufficient=sufficient
        ),
        customer_requested_human=False,
        information_sufficient=sufficient,
        rationale=rationale[:400],
    )


def confidence_row(
    record_id: str,
    probabilities: Mapping[str, Sequence[float]],
    specs: Sequence[HeadSpec],
    critical_intents: frozenset[str],
    *,
    system_id: str,
) -> dict[str, object]:
    """The calibrated ``FieldConfidence`` of one prediction (the confidence sidecar row).

    Args:
        record_id: Record id.
        probabilities: Head name to calibrated probabilities.
        specs: Head specs.
        critical_intents: The five critical intents.
        system_id: System id.

    Returns:
        Top-class probability per head plus ``p_critical`` (probability mass on critical intents).
    """
    confidence = {spec.name: round(float(max(probabilities[spec.name])), 6) for spec in specs}
    intent = next(spec for spec in specs if spec.name == "intent")
    confidence["p_critical"] = round(
        float(
            sum(
                p
                for c, p in zip(intent.classes, probabilities["intent"], strict=True)
                if c in critical_intents
            )
        ),
        6,
    )
    return {
        "schema_version": CONFIDENCE_VERSION,
        "record_id": record_id,
        "system_id": system_id,
        "confidence_method": CONFIDENCE_METHOD,
        "calibrator_version": CALIBRATOR_VERSION,
        "confidence": confidence,
    }


def prediction_record(record_id: str, output: TriageLabels, *, system_id: str) -> PredictionRecord:
    """Wrap an encoder output as ``prediction.v1`` (always ``first_pass``: built from classes).

    Args:
        record_id: Record id.
        output: The decoded output.
        system_id: System id.

    Returns:
        The record.
    """
    return PredictionRecord(
        record_id=record_id, system_id=system_id, validity="first_pass", output=output
    )


def encoder_system_id(cfg: EncoderRunConfig, config_sha: str, seed: int) -> str:
    """System id of E2 predictions (``tw-<name>@<version>+<sha12>-s<seed>``).

    Args:
        cfg: Encoder config.
        config_sha: ``config_sha``.
        seed: Seed.

    Returns:
        The id.
    """
    return f"tw-{cfg.name}@{cfg.version}+{config_sha[:12]}-s{seed}"


# --------------------------------------------------------------------------- examples and inputs


@dataclass(frozen=True, slots=True)
class EncoderExamples:
    """Texts and per-head targets of one split.

    Attributes:
        record_ids: Record ids in file order.
        texts: :func:`encoder_text` of each ticket.
        targets: Head name to class indices, aligned with ``texts``.
    """

    record_ids: tuple[str, ...]
    texts: tuple[str, ...]
    targets: Mapping[str, tuple[int, ...]]


def examples(data: SplitData, specs: Sequence[HeadSpec]) -> EncoderExamples:
    """Encoder examples of a loaded (guarded) train or val split.

    Args:
        data: The split.
        specs: Head specs.

    Returns:
        The examples.
    """
    encoded = [encode_labels(record.labels, specs) for record in data.records]
    return EncoderExamples(
        record_ids=data.record_ids,
        texts=tuple(encoder_text(record.ticket) for record in data.records),
        targets={spec.name: tuple(row[spec.name] for row in encoded) for spec in specs},
    )


def head_class_weights(train: EncoderExamples, specs: Sequence[HeadSpec]) -> dict[str, list[float]]:
    """Inverse-square-root class weights of every head, from the train split.

    Args:
        train: Train examples.
        specs: Head specs.

    Returns:
        Head name to per-class weights.
    """
    return {spec.name: class_weights(train.targets[spec.name], len(spec.classes)) for spec in specs}


def truncated_count(tokenizer: SFTTokenizer, texts: Sequence[str], max_length: int) -> int:
    """How many inputs exceed ``max_length`` tokens (with special tokens) and get truncated.

    Args:
        tokenizer: Encoder tokenizer.
        texts: Inputs.
        max_length: ``train.max_length``.

    Returns:
        The count (recorded in the data manifest).
    """
    return sum(len(tokenizer.encode(text, add_special_tokens=True)) > max_length for text in texts)


def prediction_inputs(
    split: str, data: TrainingData, paths: RepoPaths
) -> list[tuple[str, TicketPayload]] | None:
    """Tickets to predict for one open split, through the holdout guard.

    Args:
        split: ``val`` or ``hard_dev``.
        data: The run's training data (val comes from it).
        paths: Repository paths (``evals/hard_dev.v1.jsonl`` and the manifest subsets).

    Returns:
        ``(record_id, ticket)`` pairs, or ``None`` when the hard_dev gold file does not exist yet.

    Raises:
        EncoderError: If the split is unknown or the guard refuses a record.
    """
    if split == "val":
        return [(record.record_id, record.ticket) for record in data.val.records]
    if split != "hard_dev":
        msg = f"E2 predicts open splits only (val, hard_dev), not {split!r}"
        raise EncoderError(msg)
    if not paths.hard_dev_gold_file.is_file():
        return None
    try:
        tickets = read_tickets(paths.hard_dev_gold_file)
        authorize(
            "hard_dev",
            [(record_id, origin) for record_id, origin, _ in tickets],
            phase=TRAINING_PHASE,
            i_understand_sealed=False,
            subsets=load_subsets(paths),
        )
    except (EvalDataError, HoldoutError) as exc:
        raise EncoderError(str(exc)) from None
    return [(record_id, ticket) for record_id, _, ticket in tickets]


def pad_features(
    features: Sequence[Mapping[str, object]], pad_id: int, label_names: Sequence[str]
) -> dict[str, list[list[int]] | list[int]]:
    """Right-pad token features and gather the head labels (the collator's pure part).

    Args:
        features: Rows with ``input_ids`` (and the label columns).
        pad_id: Padding id.
        label_names: ``labels_<head>`` columns to gather (missing ones are skipped).

    Returns:
        ``input_ids`` and ``attention_mask`` (padded lists) plus one list per label column.
    """
    rows = [list(cast("Sequence[int]", f["input_ids"])) for f in features]
    width = max((len(row) for row in rows), default=0)
    batch: dict[str, list[list[int]] | list[int]] = {
        "input_ids": [row + [pad_id] * (width - len(row)) for row in rows],
        "attention_mask": [[1] * len(row) + [0] * (width - len(row)) for row in rows],
    }
    for name in label_names:
        if features and name in features[0]:
            batch[name] = [int(cast("int", f[name])) for f in features]
    return batch


# --------------------------------------------------------------------------- trainer arguments


def label_names(specs: Sequence[HeadSpec]) -> list[str]:
    """Dataset columns holding the head targets (``labels_<head>``).

    Args:
        specs: Head specs.

    Returns:
        Column names, in head order.
    """
    return [f"labels_{spec.name}" for spec in specs]


def encoder_training_kwargs(
    cfg: EncoderRunConfig,
    *,
    seed: int,
    output_dir: Path,
    run_name: str,
    hub_repo: str | None,
    specs: Sequence[HeadSpec],
) -> dict[str, object]:
    """``transformers.TrainingArguments`` keyword arguments of E2 (spec §9.5 values explicit).

    Args:
        cfg: Encoder config.
        seed: Seed.
        output_dir: Trainer output folder.
        run_name: MLflow run name.
        hub_repo: Private checkpoint repo (``None``: no pushes).
        specs: Head specs (label columns).

    Returns:
        The keyword arguments.
    """
    train = cfg.train
    kwargs: dict[str, object] = {
        "output_dir": str(output_dir),
        "run_name": run_name,
        "seed": seed,
        "data_seed": seed,
        "num_train_epochs": train.epochs,
        "per_device_train_batch_size": train.per_device_batch,
        "per_device_eval_batch_size": train.per_device_batch,
        "learning_rate": train.lr,
        "lr_scheduler_type": "linear",  # the library default, written out (§9.5 names warmup only)
        "warmup_steps": train.warmup_ratio,
        "weight_decay": train.weight_decay,
        "fp16": cfg.precision.fp16,
        "bf16": cfg.precision.bf16,
        "eval_strategy": "epoch",
        "save_strategy": "epoch",
        "save_total_limit": 2,  # the best epoch and the latest one (resume)
        "save_only_model": False,
        "load_best_model_at_end": True,
        "metric_for_best_model": train.best_metric,
        "greater_is_better": True,
        "logging_steps": 25,
        "label_names": label_names(specs),
        "remove_unused_columns": False,
        "report_to": list(cfg.tracking.report_to),
        "ignore_data_skip": False,
        "push_to_hub": hub_repo is not None,
    }
    if hub_repo is not None:
        kwargs["hub_model_id"] = hub_repo
        kwargs["hub_strategy"] = cfg.hub.strategy
        kwargs["hub_private_repo"] = cfg.hub.private
    return kwargs


def calibrator_document(
    fits: Mapping[str, TemperatureFit], *, system_id: str, config_sha: str
) -> dict[str, object]:
    """``calibrator.json``: one temperature per head, fitted on val.

    Args:
        fits: Head name to its fit.
        system_id: System id.
        config_sha: ``config_sha``.

    Returns:
        The document.
    """
    return {
        "calibrator_version": CALIBRATOR_VERSION,
        "confidence_method": CONFIDENCE_METHOD,
        "method": "temperature",
        "fitted_on": "val",
        "system_id": system_id,
        "config_sha": config_sha,
        "heads": {
            name: {
                "temperature": fit.temperature,
                "nll_before": fit.nll_before,
                "nll_after": fit.nll_after,
                "n": fit.n,
            }
            for name, fit in fits.items()
        },
        "note": "fitted and first evaluated on val; val ECE is in-sample (ADR-0017)",
    }


def metrics_function(specs: Sequence[HeadSpec]) -> Callable[[object], dict[str, float]]:
    """``compute_metrics`` of the E2 trainer: val intent macro-F1 for the best-epoch choice.

    Args:
        specs: Head specs (the model returns one logit matrix per head, in this order).

    Returns:
        ``compute(eval_prediction) -> {"intent_macro_f1": value}``.
    """
    position = [spec.name for spec in specs].index("intent")
    intent = specs[position]

    def compute(prediction: object) -> dict[str, float]:
        result: Any = prediction
        logits = np.asarray(result.predictions[position])
        gold = np.asarray(result.label_ids[position])
        return {
            "intent_macro_f1": intent_macro_f1(gold.tolist(), logits.argmax(-1).tolist(), intent)
        }

    return compute


def write_predictions(  # noqa: PLR0913 - keyword-only: one argument per output ingredient
    out_dir: Path,
    split: str,
    *,
    record_ids: Sequence[str],
    logits: Mapping[str, FloatArray],
    fits: Mapping[str, TemperatureFit],
    specs: Sequence[HeadSpec],
    rules: LabelRules,
    system_id: str,
    system_name: str,
) -> tuple[Path, Path]:
    """Write ``<split>.jsonl`` (``prediction.v1``) and ``<split>.confidence.jsonl``.

    Args:
        out_dir: ``<run>/predictions``.
        split: ``val`` or ``hard_dev``.
        record_ids: Records, aligned with the logit rows.
        logits: Head name to ``(n, classes)`` logits.
        fits: Head name to its val temperature.
        specs: Head specs.
        rules: Label rules (default actions, critical intents).
        system_id: System id.
        system_name: Name used in the rationale.

    Returns:
        ``(prediction file, confidence file)``.

    Raises:
        EncoderError: If a head's logits do not have one row per record.
    """
    probabilities = {}
    for spec in specs:
        matrix = calibrated_probabilities(logits[spec.name], fits[spec.name].temperature)
        if matrix.shape != (len(record_ids), len(spec.classes)):
            msg = f"{spec.name} logits have shape {matrix.shape}, expected one row per record"
            raise EncoderError(msg)
        probabilities[spec.name] = matrix
    predictions, confidences = [], []
    for row, record_id in enumerate(record_ids):
        probs = {name: matrix[row] for name, matrix in probabilities.items()}
        output = decode_labels(probs, specs, rules, system_name=system_name)
        predictions.append(
            prediction_record(record_id, output, system_id=system_id).model_dump_json()
        )
        confidence = confidence_row(
            record_id, probs, specs, rules.critical_intents, system_id=system_id
        )
        confidences.append(json.dumps(confidence, sort_keys=True))
    out_dir.mkdir(parents=True, exist_ok=True)
    prediction_file, confidence_file = (
        out_dir / f"{split}.jsonl",
        out_dir / f"{split}.confidence.jsonl",
    )
    prediction_file.write_text(
        "".join(f"{line}\n" for line in predictions), encoding="utf-8", newline="\n"
    )
    confidence_file.write_text(
        "".join(f"{line}\n" for line in confidences), encoding="utf-8", newline="\n"
    )
    return prediction_file, confidence_file


def predict_open_splits(
    splits: Sequence[str],
    *,
    data: TrainingData,
    paths: RepoPaths,
    val_logits: Mapping[str, FloatArray],
    predict: Callable[[Sequence[str]], Mapping[str, FloatArray]],
    write: Callable[[str, Sequence[str], Mapping[str, FloatArray]], Path],
) -> tuple[dict[str, Path], list[str]]:
    """Predict every configured open split (val reuses the logits of the calibration pass).

    Args:
        splits: ``data.predict_splits``.
        data: The run's training data.
        paths: Repository paths.
        val_logits: Val logits (already computed for the temperature fit).
        predict: ``texts -> head logits`` of the trained model.
        write: ``(split, record_ids, logits) -> prediction file``.

    Returns:
        ``(split -> prediction file, notes about skipped splits)``.
    """
    outputs: dict[str, Path] = {}
    notes: list[str] = []
    for split in splits:
        inputs = prediction_inputs(split, data, paths)
        if inputs is None:
            notes.append(f"{split}: evals/hard_dev.v1.jsonl does not exist yet; not predicted")
            continue
        record_ids = [record_id for record_id, _ in inputs]
        texts = [encoder_text(ticket) for _, ticket in inputs]
        outputs[split] = write(split, record_ids, val_logits if split == "val" else predict(texts))
    return outputs, notes


# --------------------------------------------------------------------------- platform (lazy)
# The torch model and loop run only on Kaggle/Colab (platform torch, never in the lock).


def build_model(
    cfg: EncoderRunConfig, specs: Sequence[HeadSpec], weights: Mapping[str, Sequence[float]]
) -> object:  # pragma: no cover - needs torch + transformers
    """The multi-head encoder: ``AutoModel`` in fp32 (fp16 AMP trains it) plus linear heads.

    Args:
        cfg: Encoder config.
        specs: Head specs.
        weights: Per-head class weights (non-persistent buffers, never saved).

    Returns:
        The ``torch.nn.Module``; ``forward`` returns ``{"logits": (one per head), "loss": ...}``.
    """
    import torch  # noqa: PLC0415 - platform-only dependency
    from torch import nn  # noqa: PLC0415
    from torch.nn import functional  # noqa: PLC0415
    from transformers import AutoModel  # noqa: PLC0415

    encoder: Any = AutoModel.from_pretrained(
        cfg.base.repo,
        revision=cfg.base.revision if cfg.base.pinned else None,
        attn_implementation=cfg.precision.attn_implementation,
        trust_remote_code=cfg.trust_remote_code,
        use_safetensors=cfg.use_safetensors,
        dtype=torch.float32,
    )

    class MultiHeadEncoder(nn.Module):  # type: ignore[misc] # untyped base (torch)
        accepts_loss_kwargs = False  # the Trainer must not pass num_items_in_batch

        def __init__(self) -> None:
            super().__init__()
            self.encoder = encoder
            hidden = int(encoder.config.hidden_size)
            self.dropout = nn.Dropout(cfg.head_dropout)
            self.heads = nn.ModuleDict(
                {spec.name: nn.Linear(hidden, len(spec.classes)) for spec in specs}
            )
            for spec in specs:
                weight = torch.tensor(weights[spec.name], dtype=torch.float32)
                self.register_buffer(f"weight_{spec.name}", weight, persistent=False)

        def forward(
            self, input_ids: object, attention_mask: object, **targets: object
        ) -> dict[str, object]:
            mask: Any = attention_mask
            states: Any = self.encoder(input_ids=input_ids, attention_mask=mask).last_hidden_state
            if cfg.pooling == "cls":
                pooled = states[:, 0]
            else:
                keep = mask.unsqueeze(-1).to(states.dtype)
                pooled = (states * keep).sum(1) / keep.sum(1).clamp(min=1.0)
            pooled = self.dropout(pooled)
            logits = tuple(self.heads[spec.name](pooled) for spec in specs)
            output: dict[str, object] = {"logits": logits}
            if all(f"labels_{spec.name}" in targets for spec in specs):
                output["loss"] = sum(
                    functional.cross_entropy(
                        head.float(),
                        targets[f"labels_{spec.name}"],
                        weight=getattr(self, f"weight_{spec.name}"),
                    )
                    for spec, head in zip(specs, logits, strict=True)
                )
            return output

    model: object = MultiHeadEncoder()
    return model


def collator(
    pad_id: int, names: Sequence[str]
) -> Callable[[Sequence[Mapping[str, object]]], dict[str, object]]:  # pragma: no cover
    """The trainer's collator: :func:`pad_features`, then tensors.

    Args:
        pad_id: Padding id.
        names: Label columns.

    Returns:
        The collate function.
    """
    import torch  # noqa: PLC0415

    def collate(features: Sequence[Mapping[str, object]]) -> dict[str, object]:
        return {
            key: torch.tensor(value) for key, value in pad_features(features, pad_id, names).items()
        }

    return collate


def predict_logits(
    model: object,
    tokenizer: object,
    texts: Sequence[str],
    specs: Sequence[HeadSpec],
    *,
    max_length: int,
    batch_size: int,
) -> dict[str, FloatArray]:  # pragma: no cover - needs torch
    """Head logits for texts (eval mode, fp16 autocast, truncation at ``max_length``).

    Args:
        model: The trained multi-head encoder.
        tokenizer: Its tokenizer.
        texts: :func:`encoder_text` inputs.
        specs: Head specs.
        max_length: ``train.max_length``.
        batch_size: Texts per forward pass.

    Returns:
        Head name to ``(n, classes)`` float64 logits.
    """
    import torch  # noqa: PLC0415

    net: Any = model
    tok: Any = tokenizer
    device = next(net.parameters()).device
    net.eval()
    parts: dict[str, list[FloatArray]] = {spec.name: [] for spec in specs}
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        for chunk in batched(texts, batch_size):
            encoded = tok(
                list(chunk),
                truncation=True,
                max_length=max_length,
                padding=True,
                return_tensors="pt",
            )
            output = net(
                input_ids=encoded["input_ids"].to(device),
                attention_mask=encoded["attention_mask"].to(device),
            )
            for spec, logits in zip(specs, output["logits"], strict=True):
                parts[spec.name].append(np.asarray(logits.float().cpu().numpy(), dtype=np.float64))
    return {name: np.concatenate(chunks) for name, chunks in parts.items()}


def heads_document(
    cfg: EncoderRunConfig, specs: Sequence[HeadSpec], taxonomy: Taxonomy
) -> dict[str, object]:
    """``heads.json`` of a saved model: what a later (P10) prediction run must rebuild.

    Args:
        cfg: Encoder config.
        specs: Head specs.
        taxonomy: Taxonomy (its version is recorded).

    Returns:
        The document.
    """
    return {
        "base_model": cfg.base.repo,
        "base_revision": cfg.base.revision,
        "pooling": cfg.pooling,
        "head_dropout": cfg.head_dropout,
        "max_length": cfg.train.max_length,
        "taxonomy_version": taxonomy.version,
        "heads": [{"name": s.name, "enum": s.enum, "classes": list(s.classes)} for s in specs],
    }


def run(
    cfg: EncoderRunConfig,
    config_sha: str,
    *,
    seed: int,
    data_dir: Path,
    run_root: Path,
    paths: RepoPaths,
    allow_unverified: bool,
) -> dict[str, object]:  # pragma: no cover - platform only (Kaggle/Colab T4)
    """Train, calibrate and predict one E2 seed (see the module docstring).

    Args:
        cfg: Encoder config.
        config_sha: ``config_sha``.
        seed: Seed.
        data_dir: Folder with ``train/`` and ``val/``.
        run_root: Parent of the run folders.
        paths: Repository paths.
        allow_unverified: Allow an unpinned base revision (recorded).

    Returns:
        The run summary (also written to ``run_summary.json`` and pushed).
    """
    from datasets import Dataset  # noqa: PLC0415 - platform-only dependency
    from transformers import AutoTokenizer, Trainer, TrainingArguments  # noqa: PLC0415

    save_file = importlib.import_module("safetensors.torch").save_file
    notes = check_runnable(cfg, seed, allow_unverified=allow_unverified, needs_hub=True)
    facts = assert_platform(expected_torch=cfg.platform.torch, hardware=cfg.platform.hardware)
    run_paths = RunPaths.for_run(run_root, cfg.name, seed)
    run_paths.root.mkdir(parents=True, exist_ok=True)
    repo = cfg.hub.repo_for(seed)
    resume = resume_decision(download_resume_state(repo, run_paths.root))
    taxonomy = load_taxonomy(paths.schemas_dir)
    rules = load_label_rules(paths.spec_dir / LABEL_RULES_FILE, taxonomy)
    specs = head_specs(cfg.heads, taxonomy, paths.schemas_dir)
    data = load_training_data(data_dir, cfg.data.train_file, cfg.data.val_file, paths)
    train_ex, val_ex = examples(data.train, specs), examples(data.val, specs)
    weights = head_class_weights(train_ex, specs)
    tokenizer: Any = AutoTokenizer.from_pretrained(
        cfg.base.repo,
        revision=cfg.base.revision if cfg.base.pinned else None,
        trust_remote_code=cfg.trust_remote_code,
    )
    max_length = cfg.train.max_length

    def rows(ex: EncoderExamples) -> list[dict[str, object]]:
        ids = tokenizer(list(ex.texts), truncation=True, max_length=max_length)["input_ids"]
        return [
            {"input_ids": row, **{f"labels_{s.name}": ex.targets[s.name][i] for s in specs}}
            for i, row in enumerate(ids)
        ]

    manifest = DataManifest(
        kind="encoder",
        config_sha=config_sha,
        seed=seed,
        base_model=cfg.base.repo,
        base_revision=cfg.base.revision,
        max_length=max_length,
        splits={
            part.split: split_manifest(
                part,
                data.committed_manifests.get(part.split),
                rows=len(ex.texts),
                truncated=truncated_count(tokenizer, ex.texts, max_length),
            )
            for part, ex in ((data.train, train_ex), (data.val, val_ex))
        },
    )
    manifest_sha = write_data_manifest(run_paths.data_manifest, manifest)
    identity: dict[str, str | int | None] = {
        "kind": "encoder",
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
    system = encoder_system_id(cfg, config_sha, seed)
    args = TrainingArguments(
        **encoder_training_kwargs(
            cfg,
            seed=seed,
            output_dir=run_paths.checkpoints,
            run_name=f"{cfg.name}-s{seed}",
            hub_repo=repo,
            specs=specs,
        )
    )
    trainer: Any = Trainer(
        model=build_model(cfg, specs, weights),
        args=args,
        train_dataset=Dataset.from_list(rows(train_ex)),
        eval_dataset=Dataset.from_list(rows(val_ex)),
        data_collator=collator(int(tokenizer.pad_token_id), label_names(specs)),
        compute_metrics=metrics_function(specs),
        processing_class=tokenizer,
    )
    trainer.train(resume_from_checkpoint=str(resume.checkpoint) if resume.checkpoint else None)
    batch = cfg.train.per_device_batch
    val_logits = predict_logits(
        trainer.model, tokenizer, val_ex.texts, specs, max_length=max_length, batch_size=batch
    )
    fits = {s.name: fit_temperature(val_logits[s.name], val_ex.targets[s.name]) for s in specs}
    calibrator = calibrator_document(fits, system_id=system, config_sha=config_sha)
    write_json(run_paths.root / "calibrator.json", calibrator)
    outputs, skipped = predict_open_splits(
        cfg.data.predict_splits,
        data=data,
        paths=paths,
        val_logits=val_logits,
        predict=lambda texts: predict_logits(
            trainer.model, tokenizer, texts, specs, max_length=max_length, batch_size=batch
        ),
        write=lambda split, record_ids, logits: write_predictions(
            run_paths.root / "predictions",
            split,
            record_ids=record_ids,
            logits=logits,
            fits=fits,
            specs=specs,
            rules=rules,
            system_id=system,
            system_name=cfg.name,
        )[0],
    )
    notes.extend(skipped)
    final = run_paths.root / "final"
    final.mkdir(parents=True, exist_ok=True)
    save_file(dict(trainer.model.state_dict()), str(final / "model.safetensors"))
    tokenizer.save_pretrained(str(final))
    write_json(final / "heads.json", heads_document(cfg, specs, taxonomy))
    write_json(final / "calibrator.json", calibrator)
    summary: dict[str, object] = {
        "config": cfg.name,
        "config_sha": config_sha,
        "seed": seed,
        "system_id": system,
        "best_val_intent_macro_f1": trainer.state.best_metric,
        "global_step": int(trainer.state.global_step),
        "resume": resume.reason,
        "temperatures": {name: fit.temperature for name, fit in fits.items()},
        "predictions": {s: f.relative_to(run_paths.root).as_posix() for s, f in outputs.items()},
        "data_manifest_sha256": manifest_sha,
        "gpu": asdict(facts),
        "versions": library_versions(),
        "notes": notes,
    }
    write_json(run_paths.summary, summary)
    summary["uploaded"] = push_run(repo, run_paths, f"run files, seed {seed}")
    return summary
