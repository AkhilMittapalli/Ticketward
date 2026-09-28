"""E2 encoder baseline: heads, inputs, class weights, calibration and prediction.v1 output.

The torch model is not needed: logits are numpy arrays, and the written predictions go through
``python -m tw_ml.eval score --experiment E2`` exactly as the Kaggle outputs will.
"""

import json
import math
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import f1_score

from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import TicketPayload
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.eval import __main__ as eval_cli
from tw_ml.eval.data import load_predictions
from tw_ml.train.config import EncoderRunConfig, config_sha, load_run_config
from tw_ml.train.data import load_training_data
from tw_ml.train.encoder import (
    CONFIDENCE_METHOD,
    EncoderError,
    HeadSpec,
    calibrated_probabilities,
    calibrator_document,
    class_weights,
    confidence_row,
    decode_labels,
    encode_labels,
    encoder_system_id,
    encoder_text,
    encoder_training_kwargs,
    examples,
    fit_temperature,
    head_class_weights,
    head_specs,
    heads_document,
    intent_macro_f1,
    label_names,
    mean_nll,
    metrics_function,
    pad_features,
    predict_open_splits,
    prediction_inputs,
    truncated_count,
    write_predictions,
)

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
HEADS = ("intent", "priority", "sentiment", "churn_risk", "product_area", "recommended_queue")


@pytest.fixture
def cfg(paths: RepoPaths) -> EncoderRunConfig:
    config, _ = load_run_config(paths.configs_dir / "encoder_modernbert.yaml")
    assert isinstance(config, EncoderRunConfig)
    return config


@pytest.fixture
def specs(taxonomy: Taxonomy, paths: RepoPaths) -> tuple[HeadSpec, ...]:
    return head_specs(HEADS, taxonomy, paths.schemas_dir)


def test_heads_come_from_the_exported_contract(
    specs: tuple[HeadSpec, ...], taxonomy: Taxonomy
) -> None:
    assert [(s.name, s.enum, len(s.classes)) for s in specs] == [
        ("intent", "Intent", 13),
        ("priority", "Priority", 4),
        ("sentiment", "Sentiment", 5),
        ("churn_risk", "ChurnRisk", 3),
        ("product_area", "ProductArea", 12),
        ("recommended_queue", "Queue", 6),
    ]
    assert specs[0].classes == taxonomy.values("Intent")
    with pytest.raises(EncoderError, match="rationale is not an enum field"):
        head_specs(("rationale",), taxonomy)
    with pytest.raises(EncoderError, match="is not a Intent value"):
        specs[0].index("nope")


def test_encoder_text_keeps_the_latest_message_before_old_history(
    make_ticket: Callable[..., TicketPayload],
) -> None:
    ticket = make_ticket(
        subject="Export stuck",
        message="Still broken today.",
        previous_messages=[
            {"author": "customer", "body": "First report.", "sent_at": "2026-09-01T08:00:00+00:00"},
            {"author": "agent", "body": "Looking.", "sent_at": "2026-09-01T09:00:00+00:00"},
        ],
    )
    lines = encoder_text(ticket).split("\n")
    assert json.loads(lines[0])["customer_tier"] == "business"
    assert lines[1:4] == [
        "subject: Export stuck",
        "latest customer message:",
        "Still broken today.",
    ]
    assert lines[4].startswith("earlier message -1 (agent")
    assert lines[5] == "Looking."
    assert lines[6].startswith("earlier message -2 (customer")


def test_labels_and_inverse_sqrt_weights(
    specs: tuple[HeadSpec, ...], make_labels: Callable[..., Any]
) -> None:
    encoded = encode_labels(make_labels(), specs)
    assert encoded["intent"] == specs[0].classes.index("sso_login_failure")
    weights = class_weights([0, 0, 0, 0, 1], 3)
    assert weights[2] == 0.0  # unseen class
    assert weights[1] / weights[0] == pytest.approx(math.sqrt(4))
    assert 4 * weights[0] + 1 * weights[1] == pytest.approx(5.0)  # sample-weighted mean of 1
    with pytest.raises(EncoderError, match="at least one"):
        class_weights([], 3)
    with pytest.raises(EncoderError, match="out of range"):
        class_weights([3], 3)


def _synthetic(
    n: int, classes: int, scale: float, seed: int = 7
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    rng = np.random.default_rng(seed)
    logits = rng.normal(0.0, 2.0, size=(n, classes))
    shifted = logits - logits.max(axis=1, keepdims=True)
    probs = np.exp(shifted) / np.exp(shifted).sum(axis=1, keepdims=True)
    targets = np.array([rng.choice(classes, p=row) for row in probs])
    return logits * scale, targets


def test_temperature_recovers_the_miscalibration() -> None:
    calibrated_logits, targets = _synthetic(4000, 5, 1.0)
    assert fit_temperature(calibrated_logits, targets).temperature == pytest.approx(1.0, abs=0.08)
    overconfident, targets = _synthetic(4000, 5, 3.0, seed=11)
    fit = fit_temperature(overconfident, targets)
    assert fit.temperature == pytest.approx(3.0, rel=0.08)
    assert fit.nll_after < fit.nll_before
    assert fit.nll_after == pytest.approx(mean_nll(overconfident, targets, fit.temperature))
    probs = calibrated_probabilities(overconfident[:3], fit.temperature)
    assert probs.sum(axis=1) == pytest.approx(np.ones(3))


class _Passthrough(ClassifierMixin, BaseEstimator):  # type: ignore[misc]  # sklearn is untyped
    """Returns its input as decision_function logits (precomputed encoder logits)."""

    def __init__(self, n_classes: int = 2) -> None:
        self.n_classes = n_classes

    def fit(self, features: Any, targets: Any) -> "_Passthrough":
        del features, targets
        self.classes_ = np.arange(self.n_classes)
        return self

    def decision_function(self, features: Any) -> Any:
        return np.asarray(features, dtype=np.float64)

    def predict(self, features: Any) -> Any:
        return np.asarray(features).argmax(axis=1)


def test_temperature_matches_scikit_learn_temperature_scaling() -> None:
    logits, targets = _synthetic(3000, 4, 2.5, seed=3)
    estimator = _Passthrough(4).fit(logits, targets)
    calibrated = CalibratedClassifierCV(FrozenEstimator(estimator), method="temperature")
    calibrated.fit(logits, targets)
    beta = float(calibrated.calibrated_classifiers_[0].calibrators[0].beta_)
    assert fit_temperature(logits, targets).temperature == pytest.approx(1.0 / beta, rel=1e-3)


def test_temperature_input_errors() -> None:
    with pytest.raises(EncoderError, match="non-empty"):
        fit_temperature([], [])
    with pytest.raises(EncoderError, match="one in-range class index"):
        fit_temperature([[0.1, 0.2]], [2])


def test_intent_macro_f1_is_m01(specs: tuple[HeadSpec, ...]) -> None:
    rng = np.random.default_rng(5)
    gold = rng.integers(0, 13, size=300)
    pred = np.where(rng.random(300) < 0.7, gold, rng.integers(0, 13, size=300))
    labels = [i for i, c in enumerate(specs[0].classes) if c != "other_unclear"]
    expected = f1_score(gold, pred, labels=labels, average="macro", zero_division=0)
    assert intent_macro_f1(gold.tolist(), pred.tolist(), specs[0]) == pytest.approx(expected)
    compute = metrics_function(specs)
    logits = np.eye(13)[pred]
    result = compute(SimpleNamespace(predictions=(logits, None), label_ids=(gold, None)))
    assert result == {"intent_macro_f1": pytest.approx(expected)}


def _probabilities(specs: tuple[HeadSpec, ...], choice: dict[str, str]) -> dict[str, list[float]]:
    out = {}
    for spec in specs:
        row = [0.01] * len(spec.classes)
        row[spec.classes.index(choice[spec.name])] = 1.0 - 0.01 * (len(spec.classes) - 1)
        out[spec.name] = row
    return out


def test_decoded_outputs_and_confidence(specs: tuple[HeadSpec, ...], rules: LabelRules) -> None:
    choice = {
        "intent": "billing_duplicate_charge",
        "priority": "high",
        "sentiment": "frustrated",
        "churn_risk": "medium",
        "product_area": "billing_subscriptions",
        "recommended_queue": "billing_and_accounts",
    }
    probs = _probabilities(specs, choice)
    output = decode_labels(probs, specs, rules, system_name="e2-test")
    assert (output.intent, output.priority, output.recommended_queue) == (
        "billing_duplicate_charge",
        "high",
        "billing_and_accounts",
    )
    assert (output.secondary_intents, output.entities, output.churn_signals) == ((), (), ())
    assert (output.customer_requested_human, output.information_sufficient) == (False, True)
    assert output.recommended_action == rules.routing["billing_duplicate_charge"].action
    assert "not predicted by this baseline" in output.rationale
    unclear = decode_labels(
        _probabilities(specs, {**choice, "intent": "other_unclear"}), specs, rules, system_name="x"
    )
    assert unclear.information_sufficient is False
    assert unclear.recommended_action == rules.expected_action(
        "other_unclear", customer_requested_human=False, information_sufficient=False
    )
    row = confidence_row("va_1", probs, specs, rules.critical_intents, system_id="sys")
    assert row["confidence_method"] == CONFIDENCE_METHOD
    confidence = row["confidence"]
    assert isinstance(confidence, dict)
    assert set(confidence) == {*HEADS, "p_critical"}
    assert confidence["intent"] == pytest.approx(1.0 - 0.12)
    critical = sum(1 for c in specs[0].classes if c in rules.critical_intents)
    assert confidence["p_critical"] == pytest.approx(1.0 - 0.12 + 0.01 * (critical - 1))


def _fake_logits(
    specs: tuple[HeadSpec, ...], gold: list[dict[str, str]]
) -> dict[str, np.ndarray[Any, Any]]:
    out = {}
    for spec in specs:
        matrix = np.zeros((len(gold), len(spec.classes)))
        for row, labels in enumerate(gold):
            matrix[row, spec.classes.index(labels[spec.name])] = 5.0
        out[spec.name] = matrix
    return out


def test_written_predictions_are_scorable_as_e2(
    tmp_path: Path,
    cfg: EncoderRunConfig,
    specs: tuple[HeadSpec, ...],
    rules: LabelRules,
    write_train_data: Callable[..., Path],
    train_paths: Any,
) -> None:
    data_dir = write_train_data()
    data = load_training_data(data_dir, "train/records.jsonl", "val/records.jsonl", train_paths)
    gold = [json.loads(r.labels.model_dump_json()) for r in data.val.records]
    logits = _fake_logits(specs, gold)
    fits = {
        spec.name: fit_temperature(logits[spec.name], [spec.index(g[spec.name]) for g in gold])
        for spec in specs
    }
    files = {}
    for seed in (42, 1337):
        system = encoder_system_id(cfg, config_sha(cfg), seed)
        files[seed], sidecar = write_predictions(
            tmp_path / f"s{seed}",
            "val",
            record_ids=list(data.val.record_ids),
            logits=logits,
            fits=fits,
            specs=specs,
            rules=rules,
            system_id=system,
            system_name=cfg.name,
        )
        assert len(load_predictions(files[seed])) == 4
        confidences = [
            json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()
        ]
        assert [c["record_id"] for c in confidences] == list(data.val.record_ids)
    exit_code = eval_cli.main(
        [
            "score",
            "--experiment",
            "E2",
            "--split",
            "val",
            "--gold",
            str(data_dir / "val" / "records.jsonl"),
            "--pred",
            f"s42={files[42]}",
            "--pred",
            f"s1337={files[1337]}",
            "--deployed-seed",
            "s42",
            "--out-dir",
            str(tmp_path / "reports"),
            "--n-resamples",
            "200",
        ],
        paths=train_paths,
        now=NOW,
    )
    assert exit_code == eval_cli.EXIT_OK
    report = json.loads(
        next((tmp_path / "reports").glob("E2_val_*.json")).read_text(encoding="utf-8")
    )
    assert report["experiment"] == "E2"
    assert report["system"]["seeds"] == ["s42", "s1337"]
    with pytest.raises(EncoderError, match="one row per record"):
        write_predictions(
            tmp_path / "bad",
            "val",
            record_ids=["va_00001"],
            logits=logits,
            fits=fits,
            specs=specs,
            rules=rules,
            system_id="sys",
            system_name="x",
        )


def test_prediction_inputs_are_guarded(
    write_train_data: Callable[..., Path],
    train_paths: Any,
    hard_cases: list[dict[str, Any]],
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    val = prediction_inputs("val", data, train_paths)
    assert val is not None
    assert [rid for rid, _ in val] == list(data.val.record_ids)
    assert prediction_inputs("hard_dev", data, train_paths) is None  # no gold file yet
    gold_file = train_paths.hard_dev_gold_file
    gold_file.parent.mkdir(parents=True, exist_ok=True)
    gold_file.write_text(
        "".join(json.dumps(case) + "\n" for case in hard_cases[:2]), encoding="utf-8"
    )
    with pytest.raises(EncoderError, match="refusing to evaluate sealed data"):
        prediction_inputs("hard_dev", data, train_paths)  # no manifest lists them as hard_dev
    with pytest.raises(EncoderError, match="open splits only"):
        prediction_inputs("test_synth", data, train_paths)


def test_open_split_prediction_reuses_val_logits(
    write_train_data: Callable[..., Path], train_paths: Any
) -> None:
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    written: list[tuple[str, list[str]]] = []

    def write(split: str, record_ids: Any, logits: Any) -> Path:
        written.append((split, list(record_ids)))
        assert logits == {"val": "logits"}
        return Path(f"{split}.jsonl")

    outputs, notes = predict_open_splits(
        ("val", "hard_dev"),
        data=data,
        paths=train_paths,
        val_logits={"val": "logits"},  # type: ignore[dict-item]
        predict=lambda texts: pytest.fail("val must not be predicted twice"),
        write=write,
    )
    assert outputs == {"val": Path("val.jsonl")}
    assert notes == ["hard_dev: evals/hard_dev.v1.jsonl does not exist yet; not predicted"]
    assert written == [("val", list(data.val.record_ids))]


def test_training_kwargs_and_documents(
    cfg: EncoderRunConfig,
    specs: tuple[HeadSpec, ...],
    taxonomy: Taxonomy,
    tmp_path: Path,
    write_train_data: Callable[..., Path],
    train_paths: Any,
    make_sft_tokenizer: Callable[..., Any],
) -> None:
    kwargs = encoder_training_kwargs(
        cfg, seed=42, output_dir=tmp_path, run_name="r", hub_repo="o/r-s42", specs=specs
    )
    assert (kwargs["fp16"], kwargs["bf16"]) == (True, False)
    assert (
        kwargs["learning_rate"],
        kwargs["per_device_train_batch_size"],
        kwargs["num_train_epochs"],
    ) == (3e-5, 32, 5)
    assert (kwargs["warmup_steps"], kwargs["weight_decay"]) == (0.06, 0.01)
    assert (kwargs["metric_for_best_model"], kwargs["greater_is_better"]) == (
        "intent_macro_f1",
        True,
    )
    assert kwargs["load_best_model_at_end"] is True
    assert kwargs["label_names"] == label_names(specs) == [f"labels_{h}" for h in HEADS]
    assert (kwargs["hub_model_id"], kwargs["hub_private_repo"]) == ("o/r-s42", True)
    assert "hub_model_id" not in encoder_training_kwargs(
        cfg, seed=42, output_dir=tmp_path, run_name="r", hub_repo=None, specs=specs
    )
    data = load_training_data(
        write_train_data(), "train/records.jsonl", "val/records.jsonl", train_paths
    )
    train = examples(data.train, specs)
    assert len(train.texts) == len(train.targets["intent"]) == 6
    weights = head_class_weights(train, specs)
    assert set(weights) == set(HEADS)
    assert truncated_count(make_sft_tokenizer(), train.texts, 10) == 6
    assert truncated_count(make_sft_tokenizer(), train.texts, 100_000) == 0
    batch = pad_features(
        [{"input_ids": [1, 2, 3], "labels_intent": 4}, {"input_ids": [5], "labels_intent": 0}],
        0,
        ["labels_intent", "labels_priority"],
    )
    assert batch == {
        "input_ids": [[1, 2, 3], [5, 0, 0]],
        "attention_mask": [[1, 1, 1], [1, 0, 0]],
        "labels_intent": [4, 0],
    }
    fits = {"intent": fit_temperature([[2.0, 0.0], [0.0, 2.0]], [0, 1])}
    document = calibrator_document(fits, system_id="sys", config_sha="a" * 64)
    assert document["confidence_method"] == "calibrated_softmax"
    assert document["fitted_on"] == "val"
    heads = heads_document(cfg, specs, taxonomy)
    assert heads["taxonomy_version"] == taxonomy.version
    listed = heads["heads"]
    assert isinstance(listed, list)
    assert [h["name"] for h in listed] == list(HEADS)
    assert (
        encoder_system_id(cfg, "f" * 64, 2026)
        == "tw-e2-modernbert-base@encoder.v1+ffffffffffff-s2026"
    )
