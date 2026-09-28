"""Training data: guarded train/val loading and Option A SFT rows (spec v1.1 §9.4; P3.6).

Every record becomes one pre-tokenized row (ERPROT qlora-training-on-t4 "Decision" §4)::

    input_ids = encode(prompt) + encode(target + eos)
    labels = [-100] * len(encode(prompt)) + encode(target + eos)

* **prompt**: the base model's chat template rendered with the fixed kwargs of
  :data:`tw_ml.export.prompt_format.TEMPLATE_KWARGS` plus ``add_generation_prompt=True``, i.e.
  exactly what the OllamaProvider sends raw at serving. It must equal ``render_raw`` of the
  prompt format byte for byte (train/serve parity, §9.4).
* **completion**: the minified ``TriageLabels`` JSON (contract key order = decoding-schema order)
  followed by the EOS literal; only these tokens carry loss.
* **boundary**: the joint tokenization of prompt + completion must equal the two tokenizations
  concatenated, and the completion must end with its only EOS token (hard failures: a merge
  across the boundary would shift the loss mask).
* **length**: a row longer than ``max_length`` is rejected with its id, never truncated.

Only ``train`` and ``val`` records are accepted: the holdout guard places every record by its
provenance and id prefix, and a record whose provenance mentions Anthropic or Claude anywhere is
refused (A-01, S-12). Nothing here imports Transformers; a tokenizer is anything with the
:class:`SFTTokenizer` methods, so the whole module is tested offline with a fake one.
"""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tw_ml.datagen.manifest import content_digest, load_manifest, manifest_path
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.records import FORBIDDEN_VENDOR_MARKERS, TRAINABLE_SPLITS, DatasetRecord
from tw_ml.eval.data import EvalDataError, GoldItem, file_sha256, gold_item_from_row, read_jsonl
from tw_ml.eval.holdout import HoldoutError, authorize, load_subsets
from tw_ml.export.prompt_format import TEMPLATE_KWARGS, PromptFormat, render_raw
from tw_ml.prompts import RenderedTriagePrompt, TriagePrompt, derive_nonce

IGNORE_INDEX: Final = -100
"""Label of tokens excluded from the loss (PyTorch cross-entropy ``ignore_index``)."""
TRAINING_PHASE: Final = "P3"
"""Phase declared to the holdout guard; sealed data is refused in every phase anyway."""
DATA_MANIFEST_VERSION: Final = "train_data_manifest.v1"
_SHOWN_IDS: Final = 5
_VENDOR: Final = re.compile(
    "|".join(rf"\b{re.escape(marker)}" for marker in FORBIDDEN_VENDOR_MARKERS), re.IGNORECASE
)

TrainableSplit = Literal["train", "val"]


class TrainingDataError(ValueError):
    """Raised when training data is missing, malformed, sealed or not trainable (ids only)."""


class ProvenanceError(TrainingDataError):
    """Raised for a record whose provenance names Anthropic or Claude (A-01, S-12)."""


class ParityError(TrainingDataError):
    """Raised when the chat template and ``render_raw`` disagree (train/serve parity, §9.4)."""


class TokenizationError(TrainingDataError):
    """Raised when joint and concatenated tokenization differ, or the EOS is misplaced."""


class SFTTokenizer(Protocol):
    """The part of a Hugging Face tokenizer the row builder uses."""

    @property
    def eos_token(self) -> str | None:
        """The EOS literal (``<|im_end|>`` for Qwen chat models)."""

    @property
    def eos_token_id(self) -> int | None:
        """The EOS token id."""

    def apply_chat_template(self, conversation: list[dict[str, str]], **kwargs: object) -> object:
        """Render a conversation (``tokenize=False`` returns text)."""

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        """Token ids of ``text`` (special-token literals map to their ids)."""


# --------------------------------------------------------------------------- loading


@dataclass(frozen=True, slots=True)
class SplitData:
    """One validated, guarded split file.

    Attributes:
        split: ``train`` or ``val``.
        file: Display name of the source file.
        file_sha256: SHA-256 of the file bytes.
        records: Records in file order.
        content_digest: Order-independent digest (``record_id:content_sha256`` lines), the same
            value ``data/manifests/<split>.json`` stores.
    """

    split: TrainableSplit
    file: str
    file_sha256: str
    records: tuple[DatasetRecord, ...]
    content_digest: str

    @property
    def record_ids(self) -> tuple[str, ...]:
        """Record ids in file order."""
        return tuple(record.record_id for record in self.records)


def forbidden_vendor_fields(value: object, prefix: str = "provenance") -> list[str]:
    """Paths of string values (at any depth) that mention a forbidden vendor.

    Args:
        value: A parsed provenance block (or any JSON value inside it).
        prefix: Path of ``value``.

    Returns:
        Dotted paths such as ``provenance.provider``; empty when clean.
    """
    if isinstance(value, str):
        return [prefix] if _VENDOR.search(value) else []
    if isinstance(value, Mapping):
        return [p for k, v in value.items() for p in forbidden_vendor_fields(v, f"{prefix}.{k}")]
    if isinstance(value, list | tuple):
        return [p for i, v in enumerate(value) for p in forbidden_vendor_fields(v, f"{prefix}.{i}")]
    return []


def _locations(exc: ValidationError) -> str:
    places = sorted({".".join(str(part) for part in error["loc"]) for error in exc.errors()})
    return ", ".join(places[:5]) or "<root>"


def load_split(path: Path, split: TrainableSplit, paths: RepoPaths) -> SplitData:
    """Load one train or val file through the S-12 check and the holdout guard.

    Args:
        path: JSONL of ``DatasetRecord`` rows.
        split: The split the file must contain (``train`` or ``val``).
        paths: Repository paths (manifest subsets for the guard).

    Returns:
        The validated split.

    Raises:
        TrainingDataError: If the file is missing or malformed, a record is not a ``split``
            record, a record id repeats, or the guard refuses a record.
        ProvenanceError: If any provenance field mentions Anthropic or Claude.
    """
    if split not in TRAINABLE_SPLITS:
        msg = f"only {', '.join(TRAINABLE_SPLITS)} may be trained on, not {split!r}"
        raise TrainingDataError(msg)
    if not path.is_file():
        msg = f"{split} data not found: {path.parent.name}/{path.name} (fetch the dataset first)"
        raise TrainingDataError(msg)
    try:
        rows = read_jsonl(path)
    except EvalDataError as exc:
        raise TrainingDataError(str(exc)) from None
    records: list[DatasetRecord] = []
    refused: list[str] = []
    for number, row in rows:
        vendor = forbidden_vendor_fields(row.get("provenance"))
        if vendor:
            refused.append(f"line {number} ({', '.join(vendor[:3])})")
            continue
        try:
            records.append(DatasetRecord.model_validate(row))
        except ValidationError as exc:
            msg = f"{path.name} line {number}: invalid record at {_locations(exc)}"
            raise TrainingDataError(msg) from None
    if refused:
        msg = (
            f"{path.name}: {len(refused)} records name Anthropic/Claude in their provenance and "
            f"may never be trained on (A-01, S-12): {'; '.join(refused[:5])}"
        )
        raise ProvenanceError(msg)
    if not records:
        msg = f"{path.name} has no records"
        raise TrainingDataError(msg)
    ids = [record.record_id for record in records]
    repeated = sorted(rid for rid, count in Counter(ids).items() if count > 1)
    if repeated:
        msg = f"{path.name}: duplicate record ids: {', '.join(repeated[:5])}"
        raise TrainingDataError(msg)
    try:
        authorize(
            split,
            [(record.record_id, record.split) for record in records],
            phase=TRAINING_PHASE,
            i_understand_sealed=False,
            subsets=load_subsets(paths),
        )
    except HoldoutError as exc:
        msg = f"{path.name}: {exc}"
        raise TrainingDataError(msg) from None
    return SplitData(
        split=split,
        file=path.name,
        file_sha256=file_sha256(path),
        records=tuple(records),
        content_digest=content_digest([record.model_dump(mode="json") for record in records]),
    )


@dataclass(frozen=True, slots=True)
class TrainingData:
    """The train and val splits of one run.

    Attributes:
        train: Train split.
        val: Val split.
        committed_manifests: ``data/manifests/<split>.json`` SHA-256 per split (``None`` when
            the manifest is not committed yet).
    """

    train: SplitData
    val: SplitData
    committed_manifests: Mapping[str, str | None]


def load_training_data(
    data_dir: Path, train_file: str, val_file: str, paths: RepoPaths
) -> TrainingData:
    """Load train and val and check them against each other and the committed manifests.

    Args:
        data_dir: Folder holding the split files (``data/generated`` by default).
        train_file: Train file, relative to ``data_dir``.
        val_file: Val file, relative to ``data_dir``.
        paths: Repository paths.

    Returns:
        The training data.

    Raises:
        TrainingDataError: If a split is invalid, train and val share a record id, or a split
            differs from its committed manifest.
    """
    train = load_split(data_dir / train_file, "train", paths)
    val = load_split(data_dir / val_file, "val", paths)
    shared = sorted(set(train.record_ids) & set(val.record_ids))
    if shared:
        msg = f"train and val share record ids: {', '.join(shared[:5])}"
        raise TrainingDataError(msg)
    committed: dict[str, str | None] = {}
    for data in (train, val):
        manifest_file = manifest_path(paths.manifests_dir, data.split)
        if not manifest_file.is_file():
            committed[data.split] = None
            continue
        try:
            manifest = load_manifest(manifest_file)
        except ValueError:
            msg = f"{manifest_file.name} is unreadable; refusing to guess"
            raise TrainingDataError(msg) from None
        if manifest.content_digest != data.content_digest:
            msg = (
                f"{data.file} differs from data/manifests/{manifest_file.name} "
                f"({manifest.dataset_version}); train only on the committed data version"
            )
            raise TrainingDataError(msg)
        committed[data.split] = file_sha256(manifest_file)
    return TrainingData(train=train, val=val, committed_manifests=committed)


def gold_items(data: SplitData) -> list[GoldItem]:
    """Gold items of a split for the in-training evaluation (``tw_ml.eval`` semantics).

    Args:
        data: A loaded split.

    Returns:
        One item per record.

    Raises:
        TrainingDataError: If a record cannot be read as gold (never expected after loading).
    """
    items: list[GoldItem] = []
    for record in data.records:
        item = gold_item_from_row(record.model_dump(mode="json"))
        if item is None:  # pragma: no cover - only the hard-set template row maps to None
            msg = f"{record.record_id} is not a gold record"
            raise TrainingDataError(msg)
        items.append(item)
    return items


# --------------------------------------------------------------------------- SFT rows (Option A)


def nonce_salt(config_version: str, name: str, seed: int) -> str:
    """Run-level salt of the per-record nonces (``derive_nonce``).

    Reruns of one seed render byte-identical prompts; different seeds see different delimiter
    ids, as the model will at serving, where the nonce is random.

    Args:
        config_version: Config ``version`` (``sft.v1``).
        name: Config ``name``.
        seed: Training seed.

    Returns:
        The salt.
    """
    return f"{config_version}:{name}:seed{seed}"


def render_split(
    data: SplitData, prompt: TriagePrompt, fmt: PromptFormat, salt: str
) -> list[RenderedTriagePrompt]:
    """Render every record of a split with its target (serving neutralization included).

    Args:
        data: A loaded split.
        prompt: The triage prompt (``triage.v1``).
        fmt: Prompt format of the base model (its special tokens are neutralized in tickets).
        salt: Nonce salt (:func:`nonce_salt`).

    Returns:
        One rendering per record, in file order.
    """
    return [
        prompt.render_record(
            record,
            nonce=derive_nonce(record.record_id, salt=salt),
            special_tokens=fmt.special_tokens,
        )
        for record in data.records
    ]


def chat_prompt_text(tokenizer: SFTTokenizer, rendered: RenderedTriagePrompt) -> str:
    """The prompt as the chat template renders it, with the fixed template kwargs.

    Args:
        tokenizer: Base-model tokenizer.
        rendered: A rendered triage prompt.

    Returns:
        The prompt text, ending with the generation prefix.

    Raises:
        ParityError: If the template does not return text.
    """
    text = tokenizer.apply_chat_template(
        rendered.chat(), tokenize=False, add_generation_prompt=True, **TEMPLATE_KWARGS
    )
    if not isinstance(text, str):
        msg = "apply_chat_template(tokenize=False) did not return text"
        raise ParityError(msg)
    return text


@dataclass(frozen=True, slots=True)
class SFTRow:
    """One pre-tokenized training row.

    Attributes:
        record_id: Source record.
        input_ids: Prompt tokens followed by completion tokens.
        labels: ``-100`` over the prompt, the completion tokens after it.
        prompt_tokens: Number of prompt tokens.
    """

    record_id: str
    input_ids: tuple[int, ...]
    labels: tuple[int, ...]
    prompt_tokens: int

    @property
    def completion_tokens(self) -> int:
        """Number of completion tokens (target JSON plus EOS)."""
        return len(self.input_ids) - self.prompt_tokens

    def features(self) -> dict[str, list[int]]:
        """Dataset columns: ``input_ids``, ``labels`` and the matching ``completion_mask``.

        TRL uses a ``labels`` column as is; ``completion_mask`` gives the same mask to its
        completion-only path, so either collator path trains on the completion only.

        Returns:
            The row as plain lists.
        """
        mask = [0] * self.prompt_tokens + [1] * self.completion_tokens
        return {
            "input_ids": list(self.input_ids),
            "labels": list(self.labels),
            "completion_mask": mask,
        }


@dataclass(frozen=True, slots=True)
class TokenStats:
    """Token counts of the accepted rows."""

    rows: int
    prompt_max: int
    completion_max: int
    total_max: int
    total_mean: float


@dataclass(frozen=True, slots=True)
class SFTSplit:
    """The tokenized rows of one split.

    Attributes:
        split: ``train`` or ``val``.
        rows: Accepted rows, in file order.
        rejected_over_length: Ids of records longer than ``max_length`` (never truncated).
        prompts: Prompt token ids of every record (the generation eval uses all of val).
        stats: Token statistics of the accepted rows.
    """

    split: str
    rows: tuple[SFTRow, ...]
    rejected_over_length: tuple[str, ...]
    prompts: Mapping[str, tuple[int, ...]]
    stats: TokenStats

    @property
    def rejected_fraction(self) -> float:
        """Rejected share of the split's records."""
        total = len(self.rows) + len(self.rejected_over_length)
        return len(self.rejected_over_length) / total if total else 0.0


def eos_literal(tokenizer: SFTTokenizer, fmt: PromptFormat) -> tuple[str, int]:
    """The EOS literal and id that end every completion.

    Args:
        tokenizer: Base-model tokenizer.
        fmt: Prompt format (serving stops on its ``stop`` strings).

    Returns:
        ``(literal, token_id)``.

    Raises:
        TokenizationError: If the tokenizer has no EOS token.
        ParityError: If the EOS is not a stop string at serving.
    """
    literal, token_id = tokenizer.eos_token, tokenizer.eos_token_id
    if not literal or token_id is None:
        msg = "the tokenizer has no EOS token"
        raise TokenizationError(msg)
    if literal not in fmt.stop:
        msg = f"EOS {literal!r} is not a stop string of the prompt format {list(fmt.stop)}"
        raise ParityError(msg)
    return literal, token_id


def _ids(problems: Sequence[str]) -> str:
    more = len(problems) - _SHOWN_IDS
    return ", ".join(problems[:_SHOWN_IDS]) + (f" (+{more} more)" if more > 0 else "")


def build_sft_split(
    data: SplitData,
    *,
    tokenizer: SFTTokenizer,
    prompt: TriagePrompt,
    fmt: PromptFormat,
    salt: str,
    max_length: int,
) -> SFTSplit:
    """Tokenize one split into Option A rows with every parity and boundary check.

    Args:
        data: A loaded split.
        tokenizer: Base-model tokenizer.
        prompt: The triage prompt.
        fmt: Prompt format of the base model (parity reference).
        salt: Nonce salt.
        max_length: Row budget (prompt + completion tokens).

    Returns:
        The rows, rejected ids and statistics.

    Raises:
        ParityError: If any chat-template prompt differs from ``render_raw`` (ids listed).
        TokenizationError: If joint and concatenated tokenization differ, or a completion does
            not end with its only EOS token (ids listed).
    """
    eos, eos_id = eos_literal(tokenizer, fmt)
    parity, boundary, misplaced_eos, over = [], [], [], []
    rows: list[SFTRow] = []
    prompts: dict[str, tuple[int, ...]] = {}
    for record, rendered in zip(data.records, render_split(data, prompt, fmt, salt), strict=True):
        rid, text = record.record_id, chat_prompt_text(tokenizer, rendered)
        if text != render_raw(fmt, rendered.system, rendered.user):
            parity.append(rid)
            continue
        completion = f"{rendered.target}{eos}"
        prompt_ids = tokenizer.encode(text, add_special_tokens=False)
        completion_ids = tokenizer.encode(completion, add_special_tokens=False)
        prompts[rid] = tuple(prompt_ids)
        if tokenizer.encode(text + completion, add_special_tokens=False) != [
            *prompt_ids,
            *completion_ids,
        ]:
            boundary.append(rid)
            continue
        if not completion_ids or completion_ids[-1] != eos_id or completion_ids.count(eos_id) != 1:
            misplaced_eos.append(rid)
            continue
        if len(prompt_ids) + len(completion_ids) > max_length:
            over.append(rid)
            continue
        rows.append(
            SFTRow(
                record_id=rid,
                input_ids=(*prompt_ids, *completion_ids),
                labels=(*([IGNORE_INDEX] * len(prompt_ids)), *completion_ids),
                prompt_tokens=len(prompt_ids),
            )
        )
    if parity:
        msg = f"{data.file}: the chat template differs from render_raw for {_ids(parity)}"
        raise ParityError(msg)
    if boundary:
        msg = f"{data.file}: joint and concatenated tokenization differ for {_ids(boundary)}"
        raise TokenizationError(msg)
    if misplaced_eos:
        msg = f"{data.file}: completion does not end with its only EOS for {_ids(misplaced_eos)}"
        raise TokenizationError(msg)
    totals = [len(row.input_ids) for row in rows]
    stats = TokenStats(
        rows=len(rows),
        prompt_max=max((row.prompt_tokens for row in rows), default=0),
        completion_max=max((row.completion_tokens for row in rows), default=0),
        total_max=max(totals, default=0),
        total_mean=round(sum(totals) / len(totals), 1) if totals else 0.0,
    )
    return SFTSplit(data.split, tuple(rows), tuple(over), prompts, stats)


def check_length_budget(split: SFTSplit, max_fraction: float) -> None:
    """Fail when more rows exceed ``max_length`` than the config tolerates.

    Args:
        split: A tokenized split.
        max_fraction: ``train.max_over_length_fraction``.

    Raises:
        TrainingDataError: If the rejected share is above ``max_fraction`` or nothing is left.
    """
    if not split.rows:
        msg = f"{split.split}: every row exceeds max_length"
        raise TrainingDataError(msg)
    if split.rejected_fraction > max_fraction:
        rejected = split.rejected_over_length
        msg = (
            f"{split.split}: {len(rejected)} rows exceed max_length "
            f"({split.rejected_fraction:.1%} > {max_fraction:.1%}): {_ids(rejected)}"
        )
        raise TrainingDataError(msg)


def rows_sha256(rows: Iterable[SFTRow]) -> str:
    """Digest of the exact training tensors (ids, input ids and labels, in order).

    Args:
        rows: Tokenized rows.

    Returns:
        SHA-256 hex digest.
    """
    digest = hashlib.sha256()
    for row in rows:
        line = json.dumps([row.record_id, row.input_ids, row.labels], separators=(",", ":"))
        digest.update(line.encode("utf-8") + b"\n")
    return digest.hexdigest()


# --------------------------------------------------------------------------- data manifest


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SplitManifest(_Manifest):
    """One split of a run's data manifest."""

    file: str
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: int = Field(ge=0)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_manifest_sha256: str | None = None
    generator_families: dict[str, int]
    label_sources: dict[str, int]
    rows: int | None = None
    rejected_over_max_length: tuple[str, ...] = ()
    truncated: int | None = None
    token_stats: dict[str, float] = Field(default_factory=dict)


class DataManifest(_Manifest):
    """``data_manifest.json``: what one run trained on, logged to MLflow by its hash."""

    schema_version: Literal["train_data_manifest.v1"] = DATA_MANIFEST_VERSION
    kind: Literal["sft", "encoder"]
    config_sha: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int
    base_model: str
    base_revision: str
    tokenizer_revision: str | None = None
    max_length: int
    nonce_salt: str | None = None
    prompt_version: str | None = None
    prompt_sha256: str | None = None
    chat_template_sha256: str | None = None
    template_kwargs: dict[str, bool | str] = Field(default_factory=dict)
    splits: dict[str, SplitManifest]
    rows_sha256: str | None = None


def split_manifest(
    data: SplitData,
    committed: str | None,
    *,
    rows: int | None = None,
    rejected: Sequence[str] = (),
    truncated: int | None = None,
    token_stats: Mapping[str, float] | None = None,
) -> SplitManifest:
    """The manifest entry of one split.

    Args:
        data: The loaded split.
        committed: SHA-256 of ``data/manifests/<split>.json``, when committed.
        rows: Accepted training rows.
        rejected: Record ids rejected for length.
        truncated: Inputs truncated to the encoder's ``max_length``.
        token_stats: Token statistics.

    Returns:
        The entry.
    """
    provenance = [record.provenance for record in data.records]
    return SplitManifest(
        file=data.file,
        file_sha256=data.file_sha256,
        records=len(data.records),
        content_digest=data.content_digest,
        committed_manifest_sha256=committed,
        generator_families=dict(sorted(Counter(p.generator_family for p in provenance).items())),
        label_sources=dict(sorted(Counter(p.label_source for p in provenance).items())),
        rows=rows,
        rejected_over_max_length=tuple(rejected),
        truncated=truncated,
        token_stats=dict(token_stats or {}),
    )


def write_data_manifest(path: Path, manifest: DataManifest) -> str:
    """Write the manifest (pretty JSON, LF) and return the SHA-256 of the written bytes.

    Args:
        path: Destination (``<run>/data_manifest.json``).
        manifest: The manifest.

    Returns:
        The file's SHA-256 (logged to MLflow as ``data_manifest_sha256``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = manifest.model_dump_json(indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_summary(data: SplitData) -> dict[str, Any]:
    """A dry-run summary of one split (counts only; never ticket text).

    Args:
        data: The loaded split.

    Returns:
        Records, per-intent counts, generator families, label sources and the digest.
    """
    return {
        "file": data.file,
        "records": len(data.records),
        "content_digest": data.content_digest,
        "intents": dict(sorted(Counter(r.labels.intent for r in data.records).items())),
        "generator_families": dict(
            sorted(Counter(r.provenance.generator_family for r in data.records).items())
        ),
        "label_sources": dict(
            sorted(Counter(r.provenance.label_source for r in data.records).items())
        ),
    }
