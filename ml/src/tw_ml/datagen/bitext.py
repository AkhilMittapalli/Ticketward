"""Bitext OOD set builder (spec v1.1 §9.1 step 5, A-13; ERPROT bitext-ood-dataset).

Two pinned Hugging Face datasets (customer support "cs" and telco "tel", both CDLA-Sharing-1.0)
are filtered through ``data/spec/bitext_mapping.v1.yaml`` into test_ood.v1: 5 strict classes x 80
+ 50 human-request probes (P-H) + 50 cancellation hard negatives (P-N) = 500 items.

License handling: the repository commits only the mapping, this builder and **row pointers**
(``evals/ood/test_ood.v1.pointers.jsonl``: dataset, revision, row, tier, probe, gold, fill seed,
content hash). Materialized text is written only to a gitignored path.

Nothing here downloads on import: :class:`HFRowSource` imports the optional ``datasets`` package
lazily and only the CLI with ``--allow-download`` constructs it. Tests use an in-memory source.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import numpy as np
import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from tw_ml.datagen.alloc import derive_seed, rng_for
from tw_ml.datagen.pii import ERROR_KINDS, find_pii, mask_text
from tw_ml.datagen.records import (
    BitextRef,
    OODGold,
    OODRecord,
    Provenance,
    TicketPayload,
)
from tw_ml.datagen.taxonomy import Taxonomy
from tw_ml.datagen.text import char_shingles, content_sha256, jaccard

MAPPING_FILE: Final = "bitext_mapping.v1.yaml"
PLACEHOLDER: Final = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
EXPECTED_TOTAL: Final = 500


class BitextError(ValueError):
    """Raised for mapping problems, unknown placeholders or unfillable groups."""


class UnknownPlaceholderError(BitextError):
    """A ``{{...}}`` placeholder has no fill rule (ERPROT D6: add it to the mapping)."""


# --------------------------------------------------------------------------- mapping models


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSpec(_Model):
    """A pinned Bitext dataset."""

    hf_id: str
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    tag_column: str
    license: Literal["CDLA-Sharing-1.0"]


class MappingEntry(_Model):
    """How one Bitext intent maps to the Taskmoor taxonomy."""

    category: str
    target: str | None
    tier: Literal["T1", "T2", "probe", "excluded"]
    reason: str


class GroupSource(_Model):
    """One source intent feeding a group."""

    source: str
    intent: str
    quota: int = Field(gt=0)
    filter: str | None = None


class GroupGold(_Model):
    """Gold labels of a group."""

    intent: str
    customer_requested_human: bool | None = None
    not_intent: str | None = None


class GroupSpec(_Model):
    """A test_ood group (S1-S5, P-H, P-N)."""

    tier: Literal["T1", "probe"]
    probe: Literal["P-H", "P-N"] | None = None
    gold: GroupGold
    sources: tuple[GroupSource, ...] = Field(min_length=1)


class FillRule(_Model):
    """One placeholder fill (exactly one field set)."""

    literal: str | None = None
    choice: tuple[str, ...] | None = None
    digits: int | None = Field(default=None, gt=0, le=12)
    prefix: str = ""
    amount: tuple[float, float] | None = None
    date: str | None = None


class WrapSpec(_Model):
    """Constant, neutral ticket metadata."""

    subject: str
    channel: Literal["chat_transcript"]
    customer_tier: Literal["business"]
    received_at: AwareDatetime


class BitextMapping(_Model):
    """``data/spec/bitext_mapping.v1.yaml``."""

    version: str
    seed: int
    sources: dict[str, SourceSpec]
    mapping: dict[str, dict[str, MappingEntry]]
    groups: dict[str, GroupSpec]
    filters: dict[str, str]
    dedup_jaccard: float = Field(gt=0, le=1)
    wrap: WrapSpec
    placeholders: dict[str, FillRule]


def load_mapping(path: Path, taxonomy: Taxonomy) -> BitextMapping:
    """Load and validate the mapping (targets are taxonomy intents; groups use T1/probe rows).

    Args:
        path: Mapping file.
        taxonomy: Taxonomy.

    Returns:
        The mapping.

    Raises:
        BitextError: If the file is malformed or inconsistent.
    """
    try:
        mapping = BitextMapping.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as exc:
        msg = f"{path.name} is malformed: {exc.error_count()} validation error(s)"
        raise BitextError(msg) from exc
    problems = mapping_problems(mapping, taxonomy)
    if problems:
        raise BitextError("; ".join(problems))
    return mapping


def mapping_problems(mapping: BitextMapping, taxonomy: Taxonomy) -> list[str]:
    """Consistency checks of a mapping.

    Args:
        mapping: Parsed mapping.
        taxonomy: Taxonomy.

    Returns:
        Problems (empty when consistent).
    """
    problems: list[str] = []
    for source, table in mapping.mapping.items():
        if source not in mapping.sources:
            problems.append(f"mapping source {source} is not a pinned source")
        for intent, entry in table.items():
            if entry.target is not None and not taxonomy.has("Intent", entry.target):
                problems.append(f"{source}.{intent}: target is not a taxonomy intent")
            if (entry.tier == "excluded") != (entry.target is None):
                problems.append(f"{source}.{intent}: excluded rows (only) have no target")
    for name, group in mapping.groups.items():
        for item in (group.gold.intent, group.gold.not_intent):
            if item is not None and not taxonomy.has("Intent", item):
                problems.append(f"group {name}: gold {item} is not an intent")
        for member in group.sources:
            row_entry = mapping.mapping.get(member.source, {}).get(member.intent)
            if row_entry is None or row_entry.tier != group.tier:
                problems.append(
                    f"group {name}: {member.source}.{member.intent} is not a {group.tier} row"
                )
            if member.filter and member.filter not in mapping.filters:
                problems.append(f"group {name}: unknown filter {member.filter}")
    total = sum(m.quota for g in mapping.groups.values() for m in g.sources)
    if total != EXPECTED_TOTAL:
        problems.append(f"groups sum to {total}, expected {EXPECTED_TOTAL}")
    return problems


# --------------------------------------------------------------------------- rows


@dataclass(frozen=True, slots=True)
class BitextRow:
    """One dataset row (only the fields the build uses; the response column is dropped).

    Attributes:
        source: Source key (``cs`` or ``tel``).
        row: Row index in the pinned revision.
        instruction: User utterance.
        intent: Bitext intent.
        category: Bitext category (data values, not the card's).
        tags: Variation tags (``flags`` / ``tags`` column).
    """

    source: str
    row: int
    instruction: str
    intent: str
    category: str
    tags: str


class RowSource(Protocol):
    """Provides the rows of a pinned source."""

    def rows(self, source: str, spec: SourceSpec) -> Sequence[BitextRow]:
        """Return every row of the source, in dataset order."""
        ...


class HFRowSource:
    """Loads the pinned revisions from the Hugging Face Hub (network; owner-run only)."""

    def rows(self, source: str, spec: SourceSpec) -> Sequence[BitextRow]:
        """Download (or read from the HF cache) the pinned dataset.

        Args:
            source: Source key.
            spec: Pinned dataset.

        Returns:
            Rows in dataset order.
        """
        import datasets  # noqa: PLC0415 - optional dependency, imported only when building

        table = datasets.load_dataset(spec.hf_id, revision=spec.revision, split="train")
        return [
            BitextRow(
                source=source,
                row=index,
                instruction=str(item["instruction"]),
                intent=str(item["intent"]),
                category=str(item["category"]),
                tags=str(item.get(spec.tag_column) or ""),
            )
            for index, item in enumerate(table)
        ]


# --------------------------------------------------------------------------- build


def fill_placeholders(text: str, rules: Mapping[str, FillRule], seed: int) -> str:
    """Fill ``{{Placeholder}}`` tokens with the seeded fill rules; collapse repeated persons.

    Args:
        text: Bitext instruction.
        rules: Placeholder name to fill rule.
        seed: Per-row fill seed.

    Returns:
        Filled text.

    Raises:
        UnknownPlaceholderError: If a placeholder has no rule.
    """
    rng = rng_for(seed, "fill")

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        rule = rules.get(name)
        if rule is None:
            msg = f"unknown Bitext placeholder {name!r}; add a fill rule to the mapping"
            raise UnknownPlaceholderError(msg)
        if rule.literal is not None:
            return rule.literal
        if rule.choice:
            return rng.choice(rule.choice)
        if rule.digits:
            return rule.prefix + "".join(str(rng.randrange(10)) for _ in range(rule.digits))
        if rule.amount:
            cents = rng.randint(int(rule.amount[0] * 100), int(rule.amount[1] * 100))
            return f"{Decimal(cents) / 100:.2f}"
        if rule.date:
            return f"{rule.date}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        msg = f"fill rule for {name!r} sets no value"
        raise BitextError(msg)

    filled = PLACEHOLDER.sub(fill, text)
    return re.sub(r"(<PERSON_1>)(?:\s+<PERSON_1>)+", r"\1", filled)


@dataclass(slots=True)
class BitextBuild:
    """Outcome of a build.

    Attributes:
        pointers: Committable pointer rows (no text).
        records: Materialized records (gitignored).
        skipped: Reason to count (rejected, duplicate, near_duplicate, filtered).
        pii_flags: Record ids whose text still matched a PII pattern after masking.
    """

    pointers: list[dict[str, Any]] = field(default_factory=list)
    records: list[OODRecord] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    pii_flags: list[str] = field(default_factory=list)


def build_ood(
    mapping: BitextMapping,
    source: RowSource,
    taxonomy: Taxonomy,
    *,
    now: datetime,
    rejects: Iterable[tuple[str, int]] = (),
) -> BitextBuild:
    """Sample, fill, wrap and dedup the 500 test_ood items (ERPROT D5-D6).

    Args:
        mapping: Validated mapping.
        source: Row provider (Hugging Face, or a fake in tests).
        taxonomy: Taxonomy (version).
        now: Creation time for provenance.
        rejects: ``(source, row)`` pairs the owner rejected in review (replaced by the next
            candidate, so the build stays deterministic).

    Returns:
        Pointers and records.

    Raises:
        BitextError: If a group cannot reach its quota.
    """
    rejected = set(rejects)
    rows = {key: source.rows(key, spec) for key, spec in mapping.sources.items()}
    rng = np.random.default_rng(mapping.seed)
    build = BitextBuild(skipped={"rejected": 0, "duplicate": 0, "near_duplicate": 0})
    for group_name, group in mapping.groups.items():
        selected_hashes: set[str] = set()
        selected_shingles: list[frozenset[str]] = []
        for member in group.sources:
            candidates = _candidates(rows[member.source], member, mapping)
            order = rng.permutation(len(candidates)).tolist() if candidates else []
            taken = 0
            for position in order:
                row = candidates[position]
                if (row.source, row.row) in rejected:
                    build.skipped["rejected"] += 1
                    continue
                record_id = f"to_{len(build.records) + 1:04d}"
                record, pointer = _materialize(
                    row, group_name, group, mapping, taxonomy, now, record_id
                )
                text = record.ticket.customer_text()
                digest = content_sha256(text)
                shingles = char_shingles(text)
                if digest in selected_hashes:
                    build.skipped["duplicate"] += 1
                    continue
                if any(
                    jaccard(shingles, other) >= mapping.dedup_jaccard for other in selected_shingles
                ):
                    build.skipped["near_duplicate"] += 1
                    continue
                selected_hashes.add(digest)
                selected_shingles.append(shingles)
                build.records.append(record)
                build.pointers.append(pointer)
                if any(hit.kind in ERROR_KINDS for hit in find_pii(record.ticket.message)):
                    build.pii_flags.append(record.record_id)  # owner review: mask or reject
                taken += 1
                if taken == member.quota:
                    break
            if taken < member.quota:
                where = f"{group_name}: {member.source}.{member.intent}"
                msg = f"group {where} has only {taken} of {member.quota} candidates"
                raise BitextError(msg)
    return build


def _candidates(
    rows: Sequence[BitextRow], member: GroupSource, mapping: BitextMapping
) -> list[BitextRow]:
    selected = [r for r in rows if r.intent == member.intent]
    if member.filter:
        pattern = re.compile(mapping.filters[member.filter], re.IGNORECASE)
        selected = [r for r in selected if pattern.search(r.instruction)]
    return selected


def _materialize(
    row: BitextRow,
    group_name: str,
    group: GroupSpec,
    mapping: BitextMapping,
    taxonomy: Taxonomy,
    now: datetime,
    record_id: str,
) -> tuple[OODRecord, dict[str, Any]]:
    spec = mapping.sources[row.source]
    entry = mapping.mapping[row.source][row.intent]
    fill_seed = derive_seed(f"{row.source}:{row.row}")
    message = mask_text(
        fill_placeholders(row.instruction, mapping.placeholders, fill_seed), []
    ).text
    ticket = TicketPayload(
        external_id=f"bitext:{row.source}:{row.row}",
        customer_tier=mapping.wrap.customer_tier,
        channel=mapping.wrap.channel,
        subject=mapping.wrap.subject,
        message=message,
        received_at=mapping.wrap.received_at,
    )
    digest = content_sha256(ticket.customer_text())
    tier: Literal["T1", "T2", "probe"] = "probe" if entry.tier == "probe" else "T1"
    provenance = Provenance(
        record_id=record_id,
        split="test_ood",
        generator_family="public_bitext",
        generator_model=spec.hf_id,
        provider="huggingface",
        generator_endpoint=f"hf:{spec.hf_id}@{spec.revision}",
        seed=mapping.seed,
        created_at=now,
        label_source="public_mapped",
        label_basis="bitext_mapping",
        taxonomy_version=taxonomy.version,
        content_sha256=digest,
        mapping_tier=tier,
        probe=group.probe,
        bitext=BitextRef(
            dataset=spec.hf_id,
            revision=spec.revision,
            row=row.row,
            intent=row.intent,
            category=row.category,
            tags=row.tags,
            fill_seed=fill_seed,
        ),
    )
    gold = OODGold.model_validate(group.gold.model_dump())
    record = OODRecord(ticket=ticket, gold=gold, provenance=provenance)
    pointer = {
        "record_id": record_id,
        "group": group_name,
        "source": row.source,
        "bitext_dataset": spec.hf_id,
        "bitext_revision": spec.revision,
        "bitext_row": row.row,
        "bitext_intent": row.intent,
        "bitext_category": row.category,
        "bitext_tags": row.tags,
        "mapping_tier": tier,
        "probe": group.probe,
        "gold": gold.model_dump(exclude_none=True),
        "fill_seed": fill_seed,
        "content_sha256": digest,
        "label_source": "public_mapped",
        "taxonomy_version": taxonomy.version,
    }
    return record, pointer


def materialize(
    pointers: Sequence[Mapping[str, Any]],
    mapping: BitextMapping,
    source: RowSource,
    taxonomy: Taxonomy,
    *,
    now: datetime,
) -> list[OODRecord]:
    """Rebuild the text of committed pointers and verify every content hash.

    Args:
        pointers: Pointer rows.
        mapping: Mapping (fill rules, wrap).
        source: Row provider.
        taxonomy: Taxonomy.
        now: Creation time.

    Returns:
        Records in pointer order.

    Raises:
        BitextError: If a revision differs or a rebuilt text no longer matches its hash.
    """
    by_source: dict[str, dict[int, BitextRow]] = {}
    for key, spec in mapping.sources.items():
        by_source[key] = {r.row: r for r in source.rows(key, spec)}
    records: list[OODRecord] = []
    for pointer in pointers:
        key = str(pointer["source"])
        if pointer["bitext_revision"] != mapping.sources[key].revision:
            msg = f"{pointer['record_id']}: revision differs from the pinned one"
            raise BitextError(msg)
        row = by_source[key][int(pointer["bitext_row"])]
        group = mapping.groups[str(pointer["group"])]
        record_id = str(pointer["record_id"])
        record, rebuilt = _materialize(
            row, str(pointer["group"]), group, mapping, taxonomy, now, record_id
        )
        if rebuilt["content_sha256"] != pointer["content_sha256"]:
            msg = f"{pointer['record_id']}: rebuilt text does not match its content hash"
            raise BitextError(msg)
        records.append(record)
    return records
