"""Gold and prediction records of the evaluation harness (JSONL in, typed models out).

Gold files may use any of the P1 row formats; only ids, labels, strata and gold decisions are
read, never the ticket text:

* ``DatasetRecord`` rows (``ticket``, ``labels``, ``provenance``, optional ``cell``): train,
  val, test_synth;
* owner-written hard-set rows (``record_id``, ``ticket``, ``labels``, ``strata``,
  ``attestation``); the template row ``th_000`` is skipped;
* evaluation rows (``record_id``, ``labels``, optional ``gold_decision``): the e2e scenarios
  and the smoke fixture carry the gold policy path, queue and reasons.

A prediction file holds one :class:`PredictionRecord` per ticket (``prediction.v1``): the
``TriageModelOutput``-shaped output, the validity tier of the repair ladder (spec §6.6) and,
for systems with a policy stage, the decision. Validation errors report line numbers and field
paths only, so ticket text never reaches a log or a report.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Final, Literal, Self

from pydantic import AfterValidator, Field, ValidationError, model_validator

from tw_ml.datagen.hardset import TEMPLATE_ID
from tw_ml.datagen.records import RecordModel, TriageLabels
from tw_ml.datagen.taxonomy import PriorityValue, QueueValue, member_check

PREDICTION_SCHEMA_VERSION: Final = "prediction.v1"
VALIDITY_TIERS: Final[tuple[str, ...]] = (
    "first_pass",
    "repaired_l1",
    "repaired_l2",
    "failed_fallback",
)
"""Spec §6.6 tiers; the metric label ``failed`` is the DB value ``failed_fallback`` (W-m9)."""
MISSING: Final = "missing"
"""Validity bucket of a gold record without any prediction (counted as a failure)."""

Validity = Literal["first_pass", "repaired_l1", "repaired_l2", "failed_fallback"]
PolicyDecision = Literal[
    "local_draft", "frontier_draft", "human_escalation", "abstain_request_info"
]
HumanRequestKind = Literal["none", "direct", "indirect"]
EscalationReasonValue = Annotated[str, AfterValidator(member_check("EscalationReason"))]


class EvalDataError(ValueError):
    """Raised when a gold or prediction file is malformed (line numbers only, no text)."""


class PolicyOutcome(RecordModel):
    """The policy stage's decision for one ticket (``TriageResult`` fields, spec §6.2, §7.3).

    ``source`` separates the P6 engine from the E1 rules preview, which covers only the
    lexicon and intent part of the forced-review rules.
    """

    policy_decision: PolicyDecision
    needs_human_review: bool
    escalation_reasons: tuple[EscalationReasonValue, ...] = ()
    final_queue: QueueValue | None = None
    final_priority: PriorityValue | None = None
    source: Literal["policy_engine", "rules_preview"] = "policy_engine"


class PredictionRecord(RecordModel):
    """One system's prediction for one ticket (``prediction.v1``).

    ``output`` mirrors ``TriageModelOutput`` (the ml copy is ``TriageLabels``). It may be
    ``None`` only for ``failed_fallback``; a system that applies the rules fallback stores those
    labels in ``output`` instead (spec §6.6 step 5).
    """

    schema_version: Literal["prediction.v1"] = PREDICTION_SCHEMA_VERSION
    record_id: str = Field(min_length=1, max_length=128)
    system_id: str = Field(min_length=1, max_length=200)
    validity: Validity = "first_pass"
    output: TriageLabels | None = None
    decision: PolicyOutcome | None = None
    latency_ms: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _output_matches_validity(self) -> Self:
        if self.output is None and self.validity != "failed_fallback":
            msg = "a prediction without output must have validity failed_fallback"
            raise ValueError(msg)
        return self


class GoldDecision(RecordModel):
    """Gold policy decision of an e2e scenario (spec §9.3 ``e2e_scenarios``)."""

    policy_decision: PolicyDecision | None = None
    queue: QueueValue | None = None
    escalation_reasons: tuple[EscalationReasonValue, ...] = ()


@dataclass(frozen=True, slots=True)
class GoldItem:
    """Gold for one ticket.

    Attributes:
        record_id: Record id.
        labels: Gold labels.
        origin: ``provenance.split`` when the row carries a provenance block.
        human_request_kind: ``direct`` / ``indirect`` / ``none`` from the hard-set strata or the
            generation cell (M-07d explicit vs indirect); ``None`` when unknown.
        needs_info: Hard-set ``needs_info`` tag (or a ``needs_info`` cell).
        legal_threat: A legal threat inside the ticket (hard-set stratum or cell flag).
        decision: Gold policy decision, when the gold file carries one.
    """

    record_id: str
    labels: TriageLabels
    origin: str | None = None
    human_request_kind: HumanRequestKind | None = None
    needs_info: bool = False
    legal_threat: bool = False
    decision: GoldDecision | None = None


@dataclass(frozen=True, slots=True)
class EvalItem:
    """A gold record joined with the system's prediction (``None`` when missing)."""

    gold: GoldItem
    prediction: PredictionRecord | None

    @property
    def record_id(self) -> str:
        """The record id."""
        return self.gold.record_id

    @property
    def output(self) -> TriageLabels | None:
        """The prediction's triage output, if any."""
        return self.prediction.output if self.prediction is not None else None

    @property
    def decision(self) -> PolicyOutcome | None:
        """The prediction's policy decision, if any."""
        return self.prediction.decision if self.prediction is not None else None


@dataclass(frozen=True, slots=True)
class EvalSet:
    """Gold joined with one system's predictions, in ``record_id`` order.

    Attributes:
        items: One item per gold record (sorted by record id, so every system sees the same
            order and therefore the same bootstrap indices).
        missing: Gold ids without a prediction.
        extra: Prediction ids without gold (reported, never scored).
        system_ids: Distinct ``system_id`` values in the prediction file.
    """

    items: tuple[EvalItem, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    system_ids: tuple[str, ...]

    @property
    def n_with_decision(self) -> int:
        """Items whose prediction carries a policy decision."""
        return sum(item.decision is not None for item in self.items)


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes.

    Args:
        path: File.

    Returns:
        Hex digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """Read a JSONL file of objects.

    Args:
        path: File (UTF-8).

    Returns:
        ``(line_number, row)`` pairs; blank lines are skipped.

    Raises:
        EvalDataError: If the file is missing, a line is not JSON, or a row is not an object.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        msg = f"file not found: {path.name}"
        raise EvalDataError(msg) from None
    rows: list[tuple[int, dict[str, Any]]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            msg = f"{path.name} line {number}: not valid JSON"
            raise EvalDataError(msg) from None
        if not isinstance(row, dict):
            msg = f"{path.name} line {number}: expected a JSON object"
            raise EvalDataError(msg)
        rows.append((number, row))
    return rows


def _locations(exc: ValidationError) -> str:
    places = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
    return ", ".join(places[:5]) or "<root>"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _human_kind(value: object) -> HumanRequestKind | None:
    kinds: dict[object, HumanRequestKind] = {
        "none": "none",
        "direct": "direct",
        "indirect": "indirect",
    }
    return kinds.get(value)


def gold_item_from_row(row: Mapping[str, Any]) -> GoldItem | None:
    """Build a gold item from one row of any supported format.

    Args:
        row: Parsed JSONL row.

    Returns:
        The item, or ``None`` for the hard-set template row.

    Raises:
        EvalDataError: If the row has no record id or no labels.
        ValidationError: If the labels or the gold decision are invalid.
    """
    provenance = _mapping(row.get("provenance"))
    record_id = provenance.get("record_id", row.get("record_id"))
    if not isinstance(record_id, str) or not record_id:
        msg = "row has no record_id"
        raise EvalDataError(msg)
    if record_id == TEMPLATE_ID and not provenance:
        return None
    if "labels" not in row:
        msg = "row has no labels (Bitext OOD rows are scored by the P10 OOD scorer)"
        raise EvalDataError(msg)
    labels = TriageLabels.model_validate(row["labels"])
    strata, cell = _mapping(row.get("strata")), _mapping(row.get("cell"))
    raw_decision = row.get("gold_decision")
    origin = provenance.get("split")
    return GoldItem(
        record_id=record_id,
        labels=labels,
        origin=origin if isinstance(origin, str) else None,
        human_request_kind=_human_kind(strata.get("human_request", cell.get("human_request"))),
        needs_info=bool(strata.get("needs_info")) or cell.get("difficulty") == "needs_info",
        legal_threat=bool(strata.get("legal_threat_in_billing")) or bool(cell.get("legal_threat")),
        decision=GoldDecision.model_validate(raw_decision) if raw_decision is not None else None,
    )


def load_gold(path: Path) -> list[GoldItem]:
    """Load a gold file.

    Args:
        path: JSONL gold file.

    Returns:
        Gold items in file order.

    Raises:
        EvalDataError: If a row is malformed or a record id repeats.
    """
    items: list[GoldItem] = []
    for number, row in read_jsonl(path):
        try:
            item = gold_item_from_row(row)
        except ValidationError as exc:
            msg = f"{path.name} line {number}: invalid gold at {_locations(exc)}"
            raise EvalDataError(msg) from None
        except EvalDataError as exc:
            msg = f"{path.name} line {number}: {exc}"
            raise EvalDataError(msg) from None
        if item is not None:
            items.append(item)
    _reject_duplicates([item.record_id for item in items], path.name)
    return items


def load_predictions(path: Path) -> list[PredictionRecord]:
    """Load a prediction file (``prediction.v1`` rows).

    Args:
        path: JSONL prediction file.

    Returns:
        Predictions in file order.

    Raises:
        EvalDataError: If a row is invalid or a record id repeats.
    """
    records: list[PredictionRecord] = []
    for number, row in read_jsonl(path):
        try:
            records.append(PredictionRecord.model_validate(row))
        except ValidationError as exc:
            msg = f"{path.name} line {number}: invalid prediction at {_locations(exc)}"
            raise EvalDataError(msg) from None
    _reject_duplicates([record.record_id for record in records], path.name)
    return records


def _reject_duplicates(ids: Sequence[str], source: str) -> None:
    repeated = sorted(record_id for record_id, count in Counter(ids).items() if count > 1)
    if repeated:
        msg = f"{source}: duplicate record ids: {', '.join(repeated[:5])}"
        raise EvalDataError(msg)


def join(gold: Sequence[GoldItem], predictions: Sequence[PredictionRecord]) -> EvalSet:
    """Join gold with one system's predictions.

    Args:
        gold: Gold items (unique ids).
        predictions: Predictions (unique ids).

    Returns:
        The joined set, sorted by record id.
    """
    by_id = {record.record_id: record for record in predictions}
    gold_ids = {item.record_id for item in gold}
    ordered = sorted(gold, key=lambda item: item.record_id)
    return EvalSet(
        items=tuple(EvalItem(item, by_id.get(item.record_id)) for item in ordered),
        missing=tuple(sorted(gold_ids - set(by_id))),
        extra=tuple(sorted(set(by_id) - gold_ids)),
        system_ids=tuple(sorted({record.system_id for record in predictions})),
    )
