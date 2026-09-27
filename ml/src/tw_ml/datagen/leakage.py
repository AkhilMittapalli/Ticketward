"""Cross-split leakage and dedup checks C1-C7 (spec v1.1 §9.3, A-12; ERPROT leakage-and-dedup).

All checks compare ``customer_text`` (subject, message and customer-authored history) after
the D1 normalization in :mod:`tw_ml.datagen.text`:

* C1 exact duplicates (normalized SHA-256), across every split pair and within every split;
* C2 lexical near-duplicates: character 5-gram shingles, exact Jaccard >= 0.70 computed for all
  pairs with a sparse matrix product (the CI source of truth at this size), a report-only band
  from 0.50, and MinHash-LSH candidates (threshold 0.5, weights (0.2, 0.8), b=30 and r=4
  asserted) as the scalable path and a recall cross-check;
* C3 embedding near-duplicates (optional): ``bge-small`` cosine >= tau; skipped cleanly when
  sentence-transformers is missing or the model revision is not pinned;
* C4 structural disjointness: template, scenario seed, persona, company and invoice prefix;
* C5 knowledge-base copying: any shared 30-token window (an empty KB directory is fine);
* C6 protected strings (spec examples, demo tickets, guideline examples): char-5 Jaccard >= 0.60,
  a shared 8-word span, or containment of a whole 5+ word entry, in *any* split;
* C7 within-train / within-val near-duplicates (Jaccard >= 0.80), a quality check.

Policy: a flag between a trainable and a protected record drops the trainable one; train x val
drops the train record; within-split duplicates keep the first id. Protected records are never
dropped: protected-protected flags only produce "replace before freeze" recommendations.
The prompt-echo probe (8-grams shared with generator prompts and the fact sheet) is report-only.
"""

import difflib
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import yaml
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from scipy import sparse

from tw_ml.datagen.records import PROTECTED_SPLITS, TRAINABLE_SPLITS, TicketPayload
from tw_ml.datagen.text import (
    char_shingles,
    content_sha256,
    h64,
    normalization_id,
    window_hashes,
    word_tokens,
)

REPORT_VERSION: Final = "leakage.v1"
CROSS_PAIRS: Final[tuple[tuple[str, str], ...]] = (
    *((t, p) for t in TRAINABLE_SPLITS for p in PROTECTED_SPLITS),
    ("train", "val"),
    ("test_synth", "test_hard"),
)
"""Explicit split pairs checked by C1-C3 (spec §9.3), plus every protected split with itself."""
INVOICE_RE: Final = re.compile(r"\b(INV-[A-Z])\d{6}\b")
FRONT_MATTER_RE: Final = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
MARKDOWN_LINK_RE: Final = re.compile(r"\[([^\]]*)\]\([^)]*\)")
PROMPT_PLACEHOLDER_RE: Final = re.compile(r"\{\{[a-z_]+\}\}")
CHUNK_ROWS: Final = 256
PROTECTED_ENTRY_SPLIT: Final = "protected_strings"


class LeakageError(RuntimeError):
    """Raised on a configuration problem (e.g. the LSH optimizer changed)."""


# --------------------------------------------------------------------------- config


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LshConfig(_Cfg):
    """MinHash-LSH candidate settings."""

    num_perm: int = Field(gt=0)
    threshold: float = Field(gt=0, lt=1)
    weights: tuple[float, float]
    expected_b: int
    expected_r: int
    seed: int
    datasketch_version: str
    crosscheck: bool = True


class EmbeddingConfig(_Cfg):
    """C3 settings."""

    enabled: bool = True
    model: str
    revision: str | None = None
    sentence_transformers_version: str
    tau: float = Field(gt=0, le=1)
    batch_size: int = Field(gt=0)


class KbConfig(_Cfg):
    """C5 settings."""

    window_tokens: int = Field(gt=0)
    report_run_tokens: int = Field(gt=0)


class ProtectedConfig(_Cfg):
    """C6 settings."""

    strings_file: str
    jaccard: float = Field(gt=0, le=1)
    span_words: int = Field(gt=0)
    containment_min_words: int = Field(gt=0)


class EchoConfig(_Cfg):
    """Prompt-echo probe settings."""

    sources: tuple[str, ...]
    ngram: int = Field(gt=0)
    intent_rate_limit: float = Field(ge=0, le=1)


class LeakageConfig(_Cfg):
    """``ml/configs/leakage.yaml``."""

    version: str
    char_ngram: int = Field(gt=0)
    jaccard_flag: float = Field(gt=0, le=1)
    jaccard_report: float = Field(gt=0, le=1)
    within_split_flag: float = Field(gt=0, le=1)
    exact_max_pairs: int = Field(gt=0)
    lsh: LshConfig
    embedding: EmbeddingConfig
    kb: KbConfig
    protected: ProtectedConfig
    prompt_echo: EchoConfig


def load_leakage_config(path: Path) -> LeakageConfig:
    """Load the leakage config.

    Args:
        path: ``ml/configs/leakage.yaml``.

    Returns:
        The validated config.

    Raises:
        LeakageError: If the file is malformed.
    """
    try:
        return LeakageConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        msg = f"{path.name} is malformed: {exc.error_count()} validation error(s)"
        raise LeakageError(msg) from exc


# --------------------------------------------------------------------------- items


@dataclass(frozen=True, slots=True)
class LeakItem:
    """What the checks need from one record.

    Attributes:
        record_id: Record id.
        split: Split.
        text: ``customer_text``.
        template_id: Prompt template id (C4).
        scenario_seed: Scenario seed (C4).
        persona_id: Persona id (C4).
        company_id: Company id (C4).
        intent: Primary intent (prompt-echo rates), when known.
    """

    record_id: str
    split: str
    text: str
    template_id: str | None = None
    scenario_seed: int | None = None
    persona_id: str | None = None
    company_id: str | None = None
    intent: str | None = None

    @property
    def invoice_prefixes(self) -> frozenset[str]:
        """Invoice-id prefixes found in the text (C4)."""
        return frozenset(INVOICE_RE.findall(self.text))


def item_from_row(row: Mapping[str, Any]) -> LeakItem:
    """Build a leakage item from a dataset or OOD record's JSON object.

    Args:
        row: Parsed JSONL row (``DatasetRecord`` or ``OODRecord`` shape).

    Returns:
        The item.
    """
    provenance = row["provenance"]
    ticket = TicketPayload.model_validate(row["ticket"])
    labels = row.get("labels") or row.get("gold") or {}
    return LeakItem(
        record_id=str(provenance["record_id"]),
        split=str(provenance["split"]),
        text=ticket.customer_text(),
        template_id=provenance.get("template_id"),
        scenario_seed=provenance.get("scenario_seed"),
        persona_id=provenance.get("persona_id"),
        company_id=provenance.get("company_id"),
        intent=labels.get("intent"),
    )


def load_items(path: Path) -> list[LeakItem]:
    """Read leakage items from a JSONL file of records.

    Args:
        path: File.

    Returns:
        Items in file order.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return [item_from_row(json.loads(line)) for line in lines if line.strip()]


def read_protected_strings(path: Path) -> list[str]:
    """Read the protected-strings list (one entry per line; ``#`` comments).

    Args:
        path: ``data/spec/protected_strings.txt``.

    Returns:
        Entries in file order.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def kb_texts(kb_dir: Path) -> dict[str, str]:
    """Markdown bodies of every KB document (front matter and link targets stripped).

    Args:
        kb_dir: ``data/kb`` (may be empty or missing).

    Returns:
        Relative path to text.
    """
    if not kb_dir.is_dir():
        return {}
    texts: dict[str, str] = {}
    for path in sorted(kb_dir.rglob("*.md")):
        body = FRONT_MATTER_RE.sub("", path.read_text(encoding="utf-8").replace("\r\n", "\n"))
        texts[path.relative_to(kb_dir).as_posix()] = MARKDOWN_LINK_RE.sub(r"\1", body)
    return texts


def prompt_source_text(path: Path) -> str:
    """Static text of a prompt or fact-sheet file (placeholders removed).

    Args:
        path: Source file.

    Returns:
        Text with ``{{placeholders}}`` replaced by line breaks.
    """
    return PROMPT_PLACEHOLDER_RE.sub("\n", path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- similarity kernels


class ShingleIndex:
    """Character shingles of every item in one sparse matrix (shared vocabulary)."""

    def __init__(self, texts: Sequence[str], n: int) -> None:
        """Shingle and index the texts.

        Args:
            texts: Texts (row order).
            n: Shingle size.
        """
        self.sets = [char_shingles(text, n) for text in texts]
        vocab: dict[str, int] = {}
        rows: list[int] = []
        cols: list[int] = []
        for row, shingles in enumerate(self.sets):
            for shingle in shingles:
                cols.append(vocab.setdefault(shingle, len(vocab)))
                rows.append(row)
        data = np.ones(len(rows), dtype=np.int32)
        shape = (len(self.sets), max(1, len(vocab)))
        self.matrix = sparse.csr_array((data, (rows, cols)), shape=shape)
        self.sizes = np.asarray([len(s) for s in self.sets], dtype=np.float64)


@dataclass(slots=True)
class JaccardScan:
    """Pairs at or above a threshold and the row-wise maximum similarity.

    Attributes:
        pairs: ``(row_index, col_index, jaccard)`` in global item indexes.
        row_max: For each row index, the best Jaccard against any column (nearest neighbour).
    """

    pairs: list[tuple[int, int, float]] = field(default_factory=list)
    row_max: dict[int, float] = field(default_factory=dict)


def exact_jaccard(
    index: ShingleIndex,
    rows: Sequence[int],
    cols: Sequence[int],
    threshold: float,
    *,
    same: bool = False,
) -> JaccardScan:
    """Exact Jaccard for every row x column pair via a chunked sparse product.

    Args:
        index: Shingle index over all items.
        rows: Global row indexes.
        cols: Global column indexes.
        threshold: Minimum Jaccard to keep a pair.
        same: Rows and columns are the same set; keep each unordered pair once (i < j).

    Returns:
        Kept pairs and nearest-neighbour similarities.
    """
    scan = JaccardScan()
    if not rows or not cols:
        return scan
    col_array = np.asarray(cols, dtype=np.int64)
    right = index.matrix[col_array].T.tocsc()
    for start in range(0, len(rows), CHUNK_ROWS):
        row_array = np.asarray(rows[start : start + CHUNK_ROWS], dtype=np.int64)
        product = (index.matrix[row_array] @ right).tocoo()
        g_rows, g_cols = row_array[product.row], col_array[product.col]
        inter = product.data.astype(np.float64)
        union = index.sizes[g_rows] + index.sizes[g_cols] - inter
        jaccard = inter / np.maximum(union, 1.0)
        valid = g_rows != g_cols if same else np.ones(jaccard.shape, dtype=bool)
        for row, value in zip(g_rows[valid].tolist(), jaccard[valid].tolist(), strict=True):
            if value > scan.row_max.get(row, 0.0):
                scan.row_max[row] = value
        keep = valid & (jaccard >= threshold) & ((g_rows < g_cols) if same else True)
        scan.pairs.extend(
            zip(g_rows[keep].tolist(), g_cols[keep].tolist(), jaccard[keep].tolist(), strict=True)
        )
    return scan


def check_lsh_params(cfg: LshConfig) -> tuple[int, int]:
    """Build the LSH index and assert its (b, r) (ERPROT D3).

    Args:
        cfg: LSH settings.

    Returns:
        ``(b, r)``.

    Raises:
        LeakageError: If datasketch picks other parameters (optimizer or version change).
    """
    from datasketch import MinHashLSH  # noqa: PLC0415 - heavy import, only when LSH runs

    lsh = MinHashLSH(threshold=cfg.threshold, num_perm=cfg.num_perm, weights=cfg.weights)
    got = (int(lsh.b), int(lsh.r))
    if got != (cfg.expected_b, cfg.expected_r):
        msg = f"datasketch chose b,r={got}, expected {(cfg.expected_b, cfg.expected_r)}"
        raise LeakageError(msg)
    return got


def lsh_candidates(
    left: Sequence[frozenset[str]], right: Sequence[frozenset[str]], cfg: LshConfig
) -> set[tuple[int, int]]:
    """MinHash-LSH candidate pairs (local indexes into ``left`` and ``right``).

    Args:
        left: Shingle sets inserted into the index.
        right: Shingle sets used as queries.
        cfg: LSH settings.

    Returns:
        Candidate ``(left_index, right_index)`` pairs; verify them with exact Jaccard.
    """
    from datasketch import MinHash, MinHashLSH  # noqa: PLC0415 - heavy import

    check_lsh_params(cfg)
    lsh = MinHashLSH(threshold=cfg.threshold, num_perm=cfg.num_perm, weights=cfg.weights)

    def encode(sets: Sequence[frozenset[str]]) -> list[list[bytes]]:
        return [[s.encode("utf-8") for s in sorted(shingles)] for shingles in sets]

    for i, minhash in enumerate(MinHash.bulk(encode(left), num_perm=cfg.num_perm, seed=cfg.seed)):
        lsh.insert(f"l{i}", minhash)
    pairs: set[tuple[int, int]] = set()
    for j, minhash in enumerate(MinHash.bulk(encode(right), num_perm=cfg.num_perm, seed=cfg.seed)):
        pairs.update((int(key[1:]), j) for key in lsh.query(minhash))
    return pairs


Embedder = Callable[[Sequence[str]], NDArray[np.float32]]


def load_embedder(cfg: EmbeddingConfig) -> tuple[Embedder | None, dict[str, Any]]:
    """Load the C3 embedder, or explain why C3 is skipped.

    Args:
        cfg: Embedding settings.

    Returns:
        ``(embedder or None, status)``; the status goes into the report.
    """
    status: dict[str, Any] = {"model": cfg.model, "revision": cfg.revision, "tau": cfg.tau}
    if not cfg.enabled:
        return None, {**status, "status": "skipped", "reason": "disabled in config"}
    if not cfg.revision:
        return None, {**status, "status": "skipped", "reason": "model revision not pinned"}
    try:
        import sentence_transformers  # noqa: PLC0415 - optional dependency
    except ImportError:
        return None, {
            **status,
            "status": "skipped",
            "reason": "sentence-transformers not installed",
        }
    installed = str(getattr(sentence_transformers, "__version__", "unknown"))
    model = sentence_transformers.SentenceTransformer(
        cfg.model, revision=cfg.revision, device="cpu"
    )

    def embed(texts: Sequence[str]) -> NDArray[np.float32]:
        vectors = np.asarray(model.encode(list(texts), batch_size=cfg.batch_size), dtype=np.float32)
        norms = np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
        return np.asarray(vectors / norms, dtype=np.float32)

    return embed, {**status, "status": "ran", "sentence_transformers": installed}


# --------------------------------------------------------------------------- report model


@dataclass(frozen=True, slots=True)
class Flag:
    """A flagged pair and the action the policy takes.

    Attributes:
        check: C1..C7.
        a: First record id (the one acted on when it is trainable).
        b: Second record id, protected-string entry id or KB document.
        split_a: Split of ``a``.
        split_b: Split of ``b``.
        score: Similarity score (1.0 for exact matches).
        action: ``drop_a``, ``drop_b``, ``replace_a``, ``replace_b`` or ``report``.
    """

    check: str
    a: str
    b: str
    split_a: str
    split_b: str
    score: float
    action: str


@dataclass(slots=True)
class LeakageReport:
    """The committed leakage report (ERPROT D9 format)."""

    created_at: str
    config: dict[str, Any]
    inputs: dict[str, int]
    input_files: dict[str, str] = field(default_factory=dict)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    report_only: dict[str, Any] = field(default_factory=dict)
    drops: list[str] = field(default_factory=list)
    replacements: list[dict[str, Any]] = field(default_factory=list)
    disjointness: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    kb: dict[str, Any] = field(default_factory=dict)
    embedding: dict[str, Any] = field(default_factory=dict)
    lsh: dict[str, Any] = field(default_factory=dict)
    nn_similarity_quantiles: dict[str, dict[str, float]] = field(default_factory=dict)
    prompt_echo: dict[str, Any] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize the report.

        Returns:
            Pretty JSON.
        """
        payload = {"report_version": REPORT_VERSION, **asdict(self)}
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- policy


def decide(check: str, a: LeakItem, b: LeakItem, score: float) -> Flag:
    """Apply the handling policy to one flagged record pair (never drops a protected record).

    Args:
        check: Check id.
        a: First item.
        b: Second item.
        score: Similarity.

    Returns:
        The flag with its action.
    """
    trainable = set(TRAINABLE_SPLITS)
    protected = set(PROTECTED_SPLITS)
    if a.split in protected and b.split in trainable:
        a, b = b, a
    action = "report"
    if a.split in trainable and b.split in protected:
        action = "drop_a"
    elif {a.split, b.split} == {"train", "val"}:
        if a.split == "val":
            a, b = b, a
        action = "drop_a"  # train x val: drop the train record
    elif a.split == b.split and a.split in trainable:
        a, b = sorted((a, b), key=lambda item: item.record_id)
        action = "drop_b"  # within train/val: keep the first id
    elif a.split in protected and b.split in protected:
        if {a.split, b.split} == {"test_synth", "test_hard"} and a.split == "test_synth":
            a, b = b, a  # keep the human-written record
        elif a.split == b.split:
            a, b = sorted((a, b), key=lambda item: item.record_id)
        action = "replace_b"
    return Flag(check, a.record_id, b.record_id, a.split, b.split, round(score, 4), action)


# --------------------------------------------------------------------------- checks


@dataclass(frozen=True, slots=True)
class LeakageInputs:
    """Everything one run checks.

    Attributes:
        items: Records of every split.
        protected_strings: C6 entries.
        kb: KB document id to text (C5).
        echo_sources: Source name to static text (prompt-echo probe).
    """

    items: Sequence[LeakItem]
    protected_strings: Sequence[str] = ()
    kb: Mapping[str, str] = field(default_factory=dict)
    echo_sources: Mapping[str, str] = field(default_factory=dict)


def run_leakage(
    inputs: LeakageInputs,
    cfg: LeakageConfig,
    *,
    embedder: Embedder | None = None,
    embedding_status: Mapping[str, Any] | None = None,
    now: datetime,
) -> LeakageReport:
    """Run C1-C7, the probes, the policy and the gate.

    Args:
        inputs: Records, protected strings, KB and prompt sources.
        cfg: Leakage config.
        embedder: C3 embedder (None skips C3).
        embedding_status: Status block for the report.
        now: Report timestamp.

    Returns:
        The report.
    """
    items = list(inputs.items)
    by_split: dict[str, list[int]] = defaultdict(list)
    for position, item in enumerate(items):
        by_split[item.split].append(position)
    report = LeakageReport(
        created_at=now.isoformat(timespec="seconds"),
        config={"normalization": normalization_id(), **cfg.model_dump(mode="json")},
        inputs={split: len(positions) for split, positions in sorted(by_split.items())},
    )
    flags: list[Flag] = []
    flags += _exact_duplicates(items)
    # One shingle index for records and protected entries (entries follow the records).
    entries = list(inputs.protected_strings)
    index = ShingleIndex([*(item.text for item in items), *entries], cfg.char_ngram)
    flags += _lexical(items, index, by_split, cfg, report)
    flags += _within_trainable(items, index, by_split, cfg)
    flags += _embedding(items, by_split, cfg, embedder, report)
    report.embedding = dict(embedding_status or {"status": "skipped", "reason": "no embedder"})
    flags += _protected(items, entries, index, cfg, report)
    flags += _kb(items, inputs.kb, cfg, report)
    report.disjointness = structural_overlap(items)
    report.prompt_echo = prompt_echo(items, inputs.echo_sources, cfg.prompt_echo)
    _finalize(report, flags, items)
    return report


def _exact_duplicates(items: Sequence[LeakItem]) -> list[Flag]:
    groups: dict[str, list[LeakItem]] = defaultdict(list)
    for item in items:
        groups[content_sha256(item.text)].append(item)
    flags: list[Flag] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda i: (i.split, i.record_id))
        for position, first in enumerate(ordered):
            flags.extend(decide("C1", first, other, 1.0) for other in ordered[position + 1 :])
    return flags


def _pair_scans(by_split: Mapping[str, list[int]]) -> list[tuple[str, str, bool]]:
    scans = [(a, b, False) for a, b in CROSS_PAIRS if by_split.get(a) and by_split.get(b)]
    scans += [(p, p, True) for p in PROTECTED_SPLITS if by_split.get(p)]
    return scans


def _lexical(
    items: Sequence[LeakItem],
    index: ShingleIndex,
    by_split: Mapping[str, list[int]],
    cfg: LeakageConfig,
    report: LeakageReport,
) -> list[Flag]:
    flags: list[Flag] = []
    band = 0
    lsh_rows: list[tuple[int, int]] = []
    for split_a, split_b, same in _pair_scans(by_split):
        scan = exact_jaccard(
            index, by_split[split_a], by_split[split_b], cfg.jaccard_report, same=same
        )
        for i, j, score in scan.pairs:
            if score >= cfg.jaccard_flag:
                flags.append(decide("C2", items[i], items[j], score))
                lsh_rows.append((i, j))
            else:
                band += 1
    for protected in PROTECTED_SPLITS:
        rows, cols = by_split.get(protected, []), by_split.get("train", [])
        if rows and cols:
            nearest = exact_jaccard(index, rows, cols, 1.1).row_max
            values = [nearest.get(r, 0.0) for r in rows]
            report.nn_similarity_quantiles[f"{protected}->train"] = _quantiles(values)
    report.report_only["C2_band_pairs"] = band
    if cfg.lsh.crosscheck and lsh_rows:
        report.lsh = _lsh_crosscheck(index, lsh_rows, cfg.lsh)
    else:
        b, r = check_lsh_params(cfg.lsh)
        report.lsh = {"b": b, "r": r, "crosscheck": "no exact C2 flags to cross-check"}
    return flags


def _lsh_crosscheck(
    index: ShingleIndex, flagged: Sequence[tuple[int, int]], cfg: LshConfig
) -> dict[str, Any]:
    rows = sorted({i for i, _ in flagged})
    cols = sorted({j for _, j in flagged})
    candidates = lsh_candidates([index.sets[i] for i in rows], [index.sets[j] for j in cols], cfg)
    found = {(rows[a], cols[b]) for a, b in candidates}
    missed = [pair for pair in flagged if pair not in found and pair[::-1] not in found]
    b, r = check_lsh_params(cfg)
    return {"b": b, "r": r, "exact_flags": len(flagged), "lsh_missed": len(missed)}


def _within_trainable(
    items: Sequence[LeakItem],
    index: ShingleIndex,
    by_split: Mapping[str, list[int]],
    cfg: LeakageConfig,
) -> list[Flag]:
    flags: list[Flag] = []
    for split in TRAINABLE_SPLITS:
        positions = by_split.get(split, [])
        scan = exact_jaccard(index, positions, positions, cfg.within_split_flag, same=True)
        for i, j, score in scan.pairs:
            if content_sha256(items[i].text) == content_sha256(items[j].text):
                continue  # exact duplicates are already C1 flags
            flags.append(decide("C7", items[i], items[j], score))
    return flags


def _embedding(
    items: Sequence[LeakItem],
    by_split: Mapping[str, list[int]],
    cfg: LeakageConfig,
    embedder: Embedder | None,
    report: LeakageReport,
) -> list[Flag]:
    if embedder is None:
        return []
    vectors = embedder([item.text for item in items])
    flags: list[Flag] = []
    for split_a, split_b, same in _pair_scans(by_split):
        left, right = by_split[split_a], by_split[split_b]
        scores = vectors[np.asarray(left)] @ vectors[np.asarray(right)].T
        for li, rj in zip(*np.nonzero(scores >= cfg.embedding.tau), strict=True):
            i, j = left[int(li)], right[int(rj)]
            if same and i >= j:
                continue
            flags.append(decide("C3", items[i], items[j], float(scores[li, rj])))
        if split_a == "train" and split_b in PROTECTED_SPLITS:
            nearest = scores.max(axis=0).tolist()  # best train match per protected record
            report.nn_similarity_quantiles[f"{split_b}->train(cos)"] = _quantiles(nearest)
    return flags


def _protected(
    items: Sequence[LeakItem],
    entries: Sequence[str],
    index: ShingleIndex,
    cfg: LeakageConfig,
    report: LeakageReport,
) -> list[Flag]:
    if not entries:
        report.report_only["C6_entries"] = 0
        return []
    settings = cfg.protected
    pseudo = [
        LeakItem(f"ps_{k:04d}", PROTECTED_ENTRY_SPLIT, text) for k, text in enumerate(entries)
    ]
    rows = list(range(len(items)))
    cols = list(range(len(items), len(items) + len(entries)))
    hits: dict[tuple[int, int], float] = {}
    for i, j, score in exact_jaccard(index, rows, cols, settings.jaccard).pairs:
        hits[(i, j - len(items))] = score
    span_index: dict[int, int] = {}
    whole: dict[int, dict[int, int]] = defaultdict(dict)
    for k, entry in enumerate(entries):
        tokens = word_tokens(entry)
        for value in window_hashes(tokens, settings.span_words):
            span_index.setdefault(value, k)
        if len(tokens) >= settings.containment_min_words:
            whole[len(tokens)][h64(tokens)] = k
    for i, item in enumerate(items):
        tokens = word_tokens(item.text)
        for value in window_hashes(tokens, settings.span_words):
            if value in span_index:
                hits.setdefault((i, span_index[value]), 1.0)
        for length, table in whole.items():
            for value in window_hashes(tokens, length) & table.keys():
                hits.setdefault((i, table[value]), 1.0)
    report.report_only["C6_entries"] = len(entries)
    flags = []
    for (i, k), score in sorted(hits.items()):
        item = items[i]
        action = "drop_a" if item.split in TRAINABLE_SPLITS else "replace_a"
        flags.append(
            Flag(
                "C6",
                item.record_id,
                pseudo[k].record_id,
                item.split,
                PROTECTED_ENTRY_SPLIT,
                round(score, 4),
                action,
            )
        )
    return flags


def _kb(
    items: Sequence[LeakItem], kb: Mapping[str, str], cfg: LeakageConfig, report: LeakageReport
) -> list[Flag]:
    if not kb:
        report.kb = {"documents": 0, "windows": 0, "status": "no_kb_documents"}
        return []
    settings = cfg.kb
    doc_tokens = {doc: word_tokens(text) for doc, text in kb.items()}
    windows: dict[int, str] = {}
    short: dict[int, set[str]] = defaultdict(set)
    for doc, tokens in doc_tokens.items():
        for value in window_hashes(tokens, settings.window_tokens):
            windows.setdefault(value, doc)
        for value in window_hashes(tokens, settings.report_run_tokens):
            short[value].add(doc)
    flags: list[Flag] = []
    long_runs: list[dict[str, Any]] = []
    for item in items:
        tokens = word_tokens(item.text)
        hit = next(
            (windows[v] for v in window_hashes(tokens, settings.window_tokens) if v in windows),
            None,
        )
        if hit is not None:
            action = "drop_a" if item.split in TRAINABLE_SPLITS else "replace_a"
            run = _longest_run(tokens, doc_tokens[hit])
            flags.append(Flag("C5", item.record_id, hit, item.split, "kb", float(run), action))
            continue
        docs = {
            d for v in window_hashes(tokens, settings.report_run_tokens) for d in short.get(v, ())
        }
        for doc in sorted(docs):
            long_runs.append(
                {
                    "record_id": item.record_id,
                    "doc": doc,
                    "run": _longest_run(tokens, doc_tokens[doc]),
                }
            )
    report.kb = {"documents": len(kb), "windows": len(windows), "status": "ok"}
    report.report_only["C5_long_runs"] = long_runs
    return flags


def _longest_run(left: Sequence[str], right: Sequence[str]) -> int:
    matcher = difflib.SequenceMatcher(None, list(left), list(right), autojunk=False)
    return matcher.find_longest_match(0, len(left), 0, len(right)).size


def structural_overlap(items: Sequence[LeakItem]) -> dict[str, dict[str, list[str]]]:
    """C4: shared templates, scenario seeds, personas, companies or invoice prefixes.

    Args:
        items: Records of every split.

    Returns:
        Key to ``"<trainable>~<protected>"`` (or ``train~val``) to up to 20 shared values.
    """
    values: dict[str, dict[str, set[str]]] = {
        key: defaultdict(set)
        for key in ("template_id", "scenario_seed", "persona_id", "company_id", "invoice_prefix")
    }
    for item in items:
        for key in ("template_id", "scenario_seed", "persona_id", "company_id"):
            value = getattr(item, key)
            if value is not None:
                values[key][item.split].add(str(value))
        values["invoice_prefix"][item.split].update(item.invoice_prefixes)
    result: dict[str, dict[str, list[str]]] = {}
    for key, per_split in values.items():
        overlaps: dict[str, list[str]] = {}
        for trainable in TRAINABLE_SPLITS:
            for protected in PROTECTED_SPLITS:
                shared = per_split[trainable] & per_split[protected]
                if shared:
                    overlaps[f"{trainable}~{protected}"] = sorted(shared)[:20]
        if key in ("template_id", "scenario_seed"):
            shared = per_split["train"] & per_split["val"]
            if shared:
                overlaps["train~val"] = sorted(shared)[:20]
        result[key] = overlaps
    return result


def prompt_echo(
    items: Sequence[LeakItem], sources: Mapping[str, str], cfg: EchoConfig
) -> dict[str, Any]:
    """Report-only probe: tickets sharing an 8-gram with a generator prompt or the fact sheet.

    Args:
        items: Records.
        sources: Source name to static text.
        cfg: Probe settings.

    Returns:
        Totals, per-intent rates and the intents above the limit.
    """
    index = {v for text in sources.values() for v in window_hashes(word_tokens(text), cfg.ngram)}
    per_intent: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    echoed = 0
    for item in items:
        hit = bool(window_hashes(word_tokens(item.text), cfg.ngram) & index)
        echoed += hit
        counts = per_intent[item.intent or "unknown"]
        counts[0] += hit
        counts[1] += 1
    rates = {intent: round(c[0] / c[1], 4) for intent, c in sorted(per_intent.items()) if c[1]}
    return {
        "sources": sorted(sources),
        "records_with_echo": echoed,
        "intent_rates": rates,
        "intents_over_limit": [i for i, rate in rates.items() if rate > cfg.intent_rate_limit],
    }


def _quantiles(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {}
    array = np.asarray(values, dtype=np.float64)
    return {f"p{q}": round(float(np.quantile(array, q / 100)), 4) for q in (50, 95, 99)}


def _finalize(report: LeakageReport, flags: Iterable[Flag], items: Sequence[LeakItem]) -> None:
    unique: dict[tuple[str, str, str], Flag] = {}
    for flag in flags:
        unique.setdefault((flag.check, flag.a, flag.b), flag)
    report.flags = sorted(unique.values(), key=lambda f: (f.check, f.split_a, f.a, f.b))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    drops: set[str] = set()
    for flag in report.flags:
        counts[f"{flag.split_a}~{flag.split_b}"][flag.check] += 1
        if flag.action == "drop_a":
            drops.add(flag.a)
        elif flag.action == "drop_b":
            drops.add(flag.b)
        elif flag.action in ("replace_a", "replace_b"):
            old = flag.a if flag.action == "replace_a" else flag.b
            report.replacements.append(
                {
                    "old_id": old,
                    "new_id": None,
                    "check": flag.check,
                    "reason": f"{flag.check} score {flag.score}; replace before freeze",
                }
            )
    protected_ids = {i.record_id for i in items if i.split in PROTECTED_SPLITS}
    if drops & protected_ids:  # the policy never drops test data; fail loudly if code regresses
        msg = "leakage policy tried to drop a protected record"
        raise LeakageError(msg)
    report.drops = sorted(drops)
    report.counts = {pair: dict(checks) for pair, checks in sorted(counts.items())}
    failures = []
    cross = [
        f
        for f in report.flags
        if f.check in ("C1", "C2", "C3", "C6")
        and f.split_a in TRAINABLE_SPLITS
        and (f.split_b in PROTECTED_SPLITS or f.split_b == PROTECTED_ENTRY_SPLIT)
    ]
    if cross:
        failures.append(
            f"{len(cross)} C1-C3/C6 flags between trainable and protected data (drop them)"
        )
    if any(report.disjointness.get(key) for key in report.disjointness):
        failures.append("C4 structural overlap")
    if any(f.check == "C5" and f.split_a in PROTECTED_SPLITS for f in report.flags):
        failures.append("C5 KB copying in a protected split")
    if report.replacements:
        failures.append(f"{len(report.replacements)} protected records to replace before freeze")
    report.gate = {"passed": not failures, "failures": failures}


def apply_drops(rows: Iterable[Mapping[str, Any]], drops: Iterable[str]) -> list[Mapping[str, Any]]:
    """Filter records by the report's drop list (trainable splits only).

    Args:
        rows: Parsed JSONL rows.
        drops: Record ids to drop.

    Returns:
        Rows whose ``provenance.record_id`` is not dropped.
    """
    dropped = set(drops)
    return [row for row in rows if row["provenance"]["record_id"] not in dropped]


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes.

    Args:
        path: File.

    Returns:
        Hex digest.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()
