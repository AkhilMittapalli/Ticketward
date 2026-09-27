"""Record models and T-DATA-provenance (spec §9.1 step 8, S-12, A-01)."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from tw_ml.datagen.records import (
    DatasetRecord,
    OODGold,
    OODRecord,
    Provenance,
    TicketPayload,
    TriageLabels,
    provenance_violations,
    utc_iso,
)
from tw_ml.datagen.text import content_sha256

ProvenanceFactory = Callable[..., Provenance]


def test_valid_record_round_trips(make_record: Callable[..., DatasetRecord]) -> None:
    record = make_record()
    again = DatasetRecord.model_validate_json(record.model_dump_json())
    assert again == record
    assert record.record_id == "tr_00001"
    assert record.split == "train"


def test_content_hash_must_match_the_ticket(
    make_ticket: Callable[..., TicketPayload],
    make_labels: Callable[..., TriageLabels],
    make_provenance: ProvenanceFactory,
) -> None:
    ticket = make_ticket()
    wrong = make_provenance(make_ticket(message="A different message entirely."))
    with pytest.raises(ValidationError, match="content_sha256"):
        DatasetRecord(ticket=ticket, labels=make_labels(), provenance=wrong)


@pytest.mark.parametrize(
    ("split", "family", "extra"),
    [
        ("train", "mistral", {}),
        ("val", "public_bitext", {}),
        ("test_synth", "openai_gpt_oss", {}),
        ("test_hard", "mistral", {"llm_assisted": False}),
        ("test_ood", "human", {}),
    ],
)
def test_family_not_allowed_in_split(
    make_provenance: ProvenanceFactory, split: str, family: str, extra: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        make_provenance(split=split, generator_family=family, record_id="tr_00009", **extra)


@pytest.mark.parametrize(
    "overrides",
    [
        {"generator_model": "claude-sonnet-5"},
        {"provider": "anthropic"},
        {"api_model_id": "claude-haiku-4-5"},
        {"generator_endpoint": "api.anthropic.com|claude|2026-09-27"},
    ],
)
def test_anthropic_produced_records_are_rejected(
    make_provenance: ProvenanceFactory, overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError, match="Anthropic"):
        make_provenance(**overrides)


def test_hard_set_needs_the_attestation(make_provenance: ProvenanceFactory) -> None:
    base = {
        "split": "test_hard",
        "generator_family": "human",
        "prompt_family": None,
        "record_id": "th_001",
    }
    with pytest.raises(ValidationError, match="llm_assisted"):
        make_provenance(**base)
    with pytest.raises(ValidationError, match="llm_assisted"):
        make_provenance(**base, llm_assisted=True)
    assert make_provenance(**base, llm_assisted=False).llm_assisted is False


def test_ood_needs_a_row_pointer(make_provenance: ProvenanceFactory) -> None:
    with pytest.raises(ValidationError, match="row pointer"):
        make_provenance(
            split="test_ood",
            generator_family="public_bitext",
            prompt_family=None,
            record_id="to_0001",
        )


def test_other_provenance_rules(make_provenance: ProvenanceFactory) -> None:
    with pytest.raises(ValidationError, match="prompt_family"):
        make_provenance(prompt_family=None)
    with pytest.raises(ValidationError, match="reviewed_by"):
        make_provenance(label_source="human_verified")
    assert make_provenance(label_source="human_verified", reviewed_by=("R-owner",)).reviewed_by
    with pytest.raises(ValidationError, match="taxonomy_version"):
        make_provenance(taxonomy_version="2025-01-v0")
    with pytest.raises(ValidationError):
        make_provenance(record_id="TRAIN-1")
    with pytest.raises(ValidationError):
        make_provenance(created_at=datetime(2026, 9, 27, 12, 0))  # noqa: DTZ001 - naive on purpose


def test_violations_are_listed_without_raising(make_provenance: ProvenanceFactory) -> None:
    valid = make_provenance()
    assert provenance_violations(valid) == []
    broken = valid.model_construct(**{**valid.model_dump(), "generator_family": "mistral"})
    assert any("not allowed" in p for p in provenance_violations(broken))


def test_models_forbid_extra_fields_and_hide_inputs(
    make_labels: Callable[..., TriageLabels],
) -> None:
    with pytest.raises(ValidationError) as caught:
        make_labels(unexpected="SECRET-TICKET-TEXT")
    assert "SECRET-TICKET-TEXT" not in str(caught.value)
    with pytest.raises(ValidationError) as caught_rationale:
        make_labels(rationale="x" * 401)
    assert "xxxx" not in str(caught_rationale.value)


def test_customer_text_skips_agent_messages(make_ticket: Callable[..., TicketPayload]) -> None:
    ticket = make_ticket(
        previous_messages=[
            {
                "author": "customer",
                "body": "first customer note",
                "sent_at": "2026-09-01T08:00:00+00:00",
            },
            {"author": "agent", "body": "agent reply", "sent_at": "2026-09-01T08:30:00+00:00"},
        ]
    )
    assert "first customer note" in ticket.customer_text()
    assert "agent reply" not in ticket.customer_text()
    assert "agent reply" in ticket.full_text()


def test_ticket_limits(make_ticket: Callable[..., TicketPayload]) -> None:
    with pytest.raises(ValidationError):
        make_ticket(subject="")
    with pytest.raises(ValidationError):
        make_ticket(customer_tier="platinum")
    with pytest.raises(ValidationError):
        make_ticket(account={"account_id": "account-1"})
    assert make_ticket(subject="  padded  ").subject == "padded"


def test_ood_record_checks_its_hash(
    make_ticket: Callable[..., TicketPayload], make_provenance: ProvenanceFactory
) -> None:
    ticket = make_ticket(subject="Support request", channel="chat_transcript", account=None)
    provenance = make_provenance(
        ticket,
        record_id="to_0001",
        split="test_ood",
        generator_family="public_bitext",
        generator_model="bitext/Bitext-customer-support-llm-chatbot-training-dataset",
        api_model_id=None,
        provider="huggingface",
        prompt_family=None,
        label_source="public_mapped",
        label_basis="bitext_mapping",
        mapping_tier="T1",
        bitext={
            "dataset": "bitext/Bitext-customer-support-llm-chatbot-training-dataset",
            "revision": "430d1a89bd93bd1fa23c16f29dd53e73f0087443",
            "row": 12,
            "intent": "recover_password",
            "category": "ACCOUNT",
            "fill_seed": 3,
        },
    )
    record = OODRecord(
        ticket=ticket, gold=OODGold(intent="account_access_issue"), provenance=provenance
    )
    assert record.record_id == "to_0001"
    tampered = provenance.model_copy(update={"content_sha256": content_sha256("other text")})
    with pytest.raises(ValidationError, match="content_sha256"):
        OODRecord(ticket=ticket, gold=OODGold(intent="account_access_issue"), provenance=tampered)


def test_utc_iso() -> None:
    assert (
        utc_iso(datetime.fromisoformat("2026-09-27T12:00:00+00:00")) == "2026-09-27T12:00:00+00:00"
    )
    with pytest.raises(ValueError, match="naive"):
        utc_iso(datetime(2026, 9, 27))  # noqa: DTZ001 - naive on purpose


def test_cell_split_must_match(
    make_record: Callable[..., DatasetRecord], make_cell: Callable[..., Any]
) -> None:
    with pytest.raises(ValidationError, match=r"cell\.split"):
        make_record(cell=make_cell(split="val"))
