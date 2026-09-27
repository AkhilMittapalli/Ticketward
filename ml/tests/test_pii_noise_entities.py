"""PII detection and masking, deterministic noise, and entity-value sampling."""

import re
from datetime import UTC, datetime

import pytest

from tw_ml.datagen.alloc import rng_for
from tw_ml.datagen.entities import EntityContext, sample_entities, supported_types
from tw_ml.datagen.factsheet import FactSheet
from tw_ml.datagen.noise import add_noise, protected_spans
from tw_ml.datagen.pii import (
    apply_replacements,
    find_pii,
    iban_valid,
    luhn_valid,
    mask_text,
    placeholder_indexes,
)
from tw_ml.datagen.pools import Company
from tw_ml.datagen.taxonomy import Taxonomy

# --------------------------------------------------------------------------- PII


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("mail ops.team@corp.test now", "email"),
        ("ring +44 20 7946 0958 please", "phone"),
        ("card 4242-4242-4242-4242 charged", "card"),
        ("IBAN GB82 WEST 1234 5698 7654 32 for the refund", "iban"),
        ("ssn 123-45-6789", "ssn"),
        ("see www.corp.test/admin", "url"),
        ("token tm_test_ABCDEFGH12345678", "secret"),
        ("key AKIAABCDEFGHIJKLMNOP", "secret"),
        ("-----BEGIN RSA PRIVATE KEY-----", "secret"),
        ("reply to {{email}} asap", "placeholder"),
        ("my name is <NAME>", "placeholder"),
        ("sign-in from 198.51.100.23", "ip"),
    ],
)
def test_find_pii_true_positives(text: str, kind: str) -> None:
    assert kind in {hit.kind for hit in find_pii(text)}


@pytest.mark.parametrize(
    "text",
    [
        "Invoice INV-A204817 was paid on 2026-09-03 at 09:14 UTC.",
        "Error SAML_ERR_302 and HTTP 503 for 40 users in acct_tr84q99z33.",
        "Workspace ws_b3ad8aa3 lost 1,280 USD; order 1234 5678 9012 3456 is fake.",
        "Reach me at <EMAIL_1> or <PHONE_2>; <PERSON_1> approved.",
        "Version 5.8.2 on iOS 18, Chrome 131.",
    ],
)
def test_find_pii_true_negatives(text: str) -> None:
    assert [hit.kind for hit in find_pii(text) if hit.kind != "ip"] == []


def test_checksums() -> None:
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")
    assert iban_valid("GB82 WEST 1234 5698 7654 32")
    assert not iban_valid("GB00 WEST 1234 5698 7654 32")


def test_known_names_are_flagged_only_as_whole_words() -> None:
    kinds = [h.kind for h in find_pii("Thanks, Priya Larkworth", ["Priya", "Larkworth"])]
    assert kinds.count("known_name") == 2
    assert find_pii("Priyanka wrote this", ["Priya"]) == []


def test_mask_text_numbers_after_existing_placeholders() -> None:
    result = mask_text(
        "Hi, <PERSON_1> here. Priya Larkworth asked; Priya will call. "
        "Mail a@corp.test or a@corp.test.",
        ["Priya Larkworth"],
    )
    assert "Priya" not in result.text
    assert "Larkworth" not in result.text
    assert result.text.count("<PERSON_2>") == 2
    assert result.text.count("<EMAIL_1>") == 2  # same address, one index
    assert set(result.ops) == {"mask:person", "mask:email"}
    assert placeholder_indexes(result.text, "PERSON") == [1, 2, 2]


def test_mask_text_reuses_replacements_and_masks_cards_and_phones() -> None:
    first = mask_text("Priya reported it.", ["Priya Larkworth"])
    second = mask_text(
        "Priya again, card 4111 1111 1111 1111, phone +1 415 555 0134.",
        ["Priya Larkworth"],
        first.replacements,
    )
    assert second.text.startswith(first.replacements["Priya"])
    assert "<CARD_LAST4_1>" in second.text
    assert "<PHONE_1>" in second.text
    assert apply_replacements("asked Priya twice", second.replacements) == "asked <PERSON_1> twice"
    assert mask_text("nothing to mask", ["Priya Larkworth"]).ops == []


# --------------------------------------------------------------------------- noise


def test_noise_is_deterministic_and_protects_values() -> None:
    text = (
        "The automation stopped working after yesterday "
        "and SAML_ERR_302 appears for <EMAIL_1> again"
    )
    keep = ["SAML_ERR_302", "automation stopped"]
    first, ops = add_noise(text, rng_for(1, "noise"), keep)
    second, ops_again = add_noise(text, rng_for(1, "noise"), keep)
    assert (first, ops) == (second, ops_again)
    assert 1 <= len(ops) <= 3
    assert first != text
    for value in (*keep, "<EMAIL_1>"):
        assert value in first
    spans = protected_spans(text, keep)
    assert any(text[s:e] == "<EMAIL_1>" for s, e in spans)


def test_noise_without_eligible_words() -> None:
    assert add_noise("SAML_ERR_302 <EMAIL_1>", rng_for(2), ["SAML_ERR_302"]) == (
        "SAML_ERR_302 <EMAIL_1>",
        [],
    )


@pytest.mark.parametrize("seed", range(12))
def test_noise_ops_stay_small(seed: int) -> None:
    text = "Please check the workload report for our marketing department today"
    noisy, ops = add_noise(text, rng_for(seed), [])
    assert all(
        re.fullmatch(r"(swap_adjacent|drop_letter|double_letter|lowercase)@\d+", op) for op in ops
    )
    assert abs(len(noisy) - len(text)) <= len(ops)


# --------------------------------------------------------------------------- entities


def _context(facts: FactSheet, intent: str, area: str, plan: str, **extra: object) -> EntityContext:
    company = Company(
        company_id="c_tr_0001",
        name="Brenvik Labs",
        industry="Labs",
        plan=plan,
        seats=int(str(extra.pop("seats", 120))),
        region="eu",
        arr_band="10k-50k",
        account_id="acct_tr1234abcd",
        workspace_ids=("ws_0badc0de",),
        invoice_prefix="INV-A",
    )
    return EntityContext(
        intent=intent,
        product_area=area,
        plan=plan,
        company=company,
        received_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        facts=facts,
        values={
            "browser": ("Chrome 131",),
            "os": ("Windows 11",),
            "legal_reference": ("GDPR Art. 15",),
            "steps_already_tried": ("reinstalled the app",),
            "user_count_affected": ("3", "40", "300"),
            "timestamp_hours": ("9",),
        },
        error_code_prefixes=tuple(str(p) for p in extra.pop("prefixes", ())),  # type: ignore[attr-defined]
        competitor=str(extra.pop("competitor")) if "competitor" in extra else None,
    )


def test_every_entity_type_can_be_sampled(facts: FactSheet, taxonomy: Taxonomy) -> None:
    assert supported_types() == set(taxonomy.values("EntityType"))
    ctx = _context(facts, "bug_report", "integrations_api", "business", competitor="Vexal Works")
    sampled = sample_entities(sorted(supported_types()), ctx, rng_for(3))
    types = {e.label.type for e in sampled}
    assert types == supported_types()
    by_type = {e.label.type: e for e in sampled}
    assert re.fullmatch(r"INV-A\d{6}", by_type["invoice_id"].label.value)
    assert by_type["workspace_id"].label.value == "ws_0badc0de"
    assert by_type["region"].label.value == "EU"
    assert by_type["saml_idp"].label.value in {"okta", "azure_ad", "google"}
    assert by_type["saml_idp"].display != by_type["saml_idp"].label.value
    assert by_type["timestamp"].label.value.startswith("09:")


def test_entity_values_respect_plan_and_intent(facts: FactSheet) -> None:
    sso_business = _context(
        facts, "sso_login_failure", "sso_identity", "business", prefixes=("SAML_ERR", "SCIM_ERR")
    )
    codes = {
        sample_entities(["error_code"], sso_business, rng_for(i))[0].label.value for i in range(40)
    }
    assert codes
    assert all(c.startswith("SAML_ERR") for c in codes)  # SCIM only on enterprise
    payment = _context(
        facts, "billing_payment_failure", "billing_subscriptions", "starter", prefixes=("PAY_ERR",)
    )
    assert sample_entities(["error_code"], payment, rng_for(1))[0].label.value.startswith("PAY_ERR")
    outage = _context(facts, "service_outage", "platform_availability", "business")
    assert sample_entities(["http_status"], outage, rng_for(1))[0].label.value.startswith("HTTP 5")
    free = _context(facts, "refund_request", "billing_subscriptions", "free", seats=4)
    assert (
        sample_entities(["charge_amount"], free, rng_for(1)) == []
    )  # the free plan is never charged
    small = _context(facts, "sso_login_failure", "sso_identity", "business", seats=10)
    assert int(sample_entities(["user_count_affected"], small, rng_for(1))[0].label.value) <= 10
    pricing = _context(facts, "plan_pricing_inquiry", "billing_subscriptions", "starter")
    feature = sample_entities(["feature_name"], pricing, rng_for(5))[0].label.value
    assert "starter" not in next(f.plans for f in facts.features if f.name == feature)
    assert sample_entities(["competitor_name", "unknown_type"], free, rng_for(1)) == []
