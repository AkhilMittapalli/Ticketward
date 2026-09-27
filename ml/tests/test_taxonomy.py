"""Drift tests: the ml package vs the exported contracts in schemas/json.

The ml package never imports the backend; it loads every enum from the committed JSON Schemas.
These tests fail when the schemas and anything the ml side encodes (label mirrors, routing
tables, matrix values, fact sheet, Bitext targets) drift apart, and when a model-label enum
changes without a new taxonomy_version (spec §5: that needs an ADR, relabeling and retraining).
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tw_ml.datagen.bitext import load_mapping
from tw_ml.datagen.factsheet import FactSheet
from tw_ml.datagen.labelrules import LabelRules
from tw_ml.datagen.matrix import Matrix
from tw_ml.datagen.paths import REPO_ROOT_ENV, RepoNotFoundError, RepoPaths, find_repo_root
from tw_ml.datagen.records import EntityLabel, TicketPayload, TriageLabels
from tw_ml.datagen.taxonomy import (
    MODEL_LABEL_ENUMS,
    TICKET_CREATE_SCHEMA,
    TRIAGE_OUTPUT_SCHEMA,
    Taxonomy,
    TaxonomyError,
    enums_from_schema,
    load_json_schema,
    load_taxonomy,
    member_check,
)

# Independent copy of the model-label enums of taxonomy 2026-09-v1 (spec §5, §6.1). Update it only
# together with a new taxonomy_version, an ADR, relabeling and retraining.
FROZEN_2026_09_V1: dict[str, list[str]] = {
    "Intent": [
        "sso_login_failure", "account_access_issue", "billing_duplicate_charge",
        "billing_payment_failure", "refund_request", "cancellation_request",
        "plan_pricing_inquiry", "service_outage", "bug_report", "how_to_question",
        "security_report", "privacy_legal_request", "other_unclear",
    ],
    "Queue": [
        "general_support_tier_1", "technical_support_tier_2", "billing_and_accounts",
        "customer_success_retention", "security_and_privacy", "incident_response",
    ],
    "Priority": ["urgent", "high", "normal", "low"],
    "Sentiment": ["positive", "neutral", "confused", "frustrated", "angry"],
    "ChurnRisk": ["low", "medium", "high"],
    "ProductArea": [
        "projects_tasks", "boards_timelines", "sso_identity", "user_admin_permissions",
        "billing_subscriptions", "integrations_api", "notifications_email", "mobile_apps",
        "reporting_analytics", "automations", "data_import_export", "platform_availability",
    ],
    "EntityType": [
        "error_code", "http_status", "saml_idp", "invoice_id", "charge_amount", "currency",
        "charge_date", "workspace_id", "account_id", "user_count_affected", "browser", "os",
        "app_version", "integration_name", "api_endpoint", "feature_name", "region",
        "timestamp", "competitor_name", "legal_reference", "steps_already_tried",
    ],
    "SamlIdp": ["okta", "azure_ad", "google", "onelogin", "other"],
    "RecommendedAction": [
        "answer_with_kb_article", "request_more_information",
        "request_saml_error_details_and_check_known_incident",
        "check_known_incident_and_share_status",
        "collect_repro_steps_and_escalate_to_engineering", "escalate_to_engineering",
        "escalate_to_billing_for_review", "escalate_to_csm_retention", "escalate_to_security",
        "escalate_to_privacy_legal", "offer_human_contact", "send_password_reset_guidance",
        "share_pricing_page_reference", "link_to_active_incident", "route_to_tier_2",
        "close_as_duplicate_ticket", "no_action_spam",
    ],
    "PlanTier": ["free", "starter", "business", "enterprise"],
    "Channel": ["web_form", "email", "api", "chat_transcript"],
}  # fmt: skip

# Spec §5.8, written out independently of data/spec/label_rules.v1.yaml.
SPEC_ROUTING = {
    "sso_login_failure": (
        "technical_support_tier_2",
        "request_saml_error_details_and_check_known_incident",
    ),
    "account_access_issue": ("general_support_tier_1", "send_password_reset_guidance"),
    "billing_duplicate_charge": ("billing_and_accounts", "escalate_to_billing_for_review"),
    "billing_payment_failure": ("billing_and_accounts", "escalate_to_billing_for_review"),
    "refund_request": ("billing_and_accounts", "escalate_to_billing_for_review"),
    "cancellation_request": ("customer_success_retention", "escalate_to_csm_retention"),
    "plan_pricing_inquiry": ("general_support_tier_1", "share_pricing_page_reference"),
    "service_outage": ("incident_response", "check_known_incident_and_share_status"),
    "bug_report": ("technical_support_tier_2", "collect_repro_steps_and_escalate_to_engineering"),
    "how_to_question": ("general_support_tier_1", "answer_with_kb_article"),
    "security_report": ("security_and_privacy", "escalate_to_security"),
    "privacy_legal_request": ("security_and_privacy", "escalate_to_privacy_legal"),
    "other_unclear": ("general_support_tier_1", "request_more_information"),
}  # fmt: skip


def _ref_name(prop: dict[str, Any]) -> str | None:
    ref = prop.get("$ref") or prop.get("items", {}).get("$ref")
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def test_taxonomy_version(taxonomy: Taxonomy) -> None:
    assert taxonomy.version == "2026-09-v1"


@pytest.mark.parametrize("name", sorted(FROZEN_2026_09_V1))
def test_model_label_enum_is_frozen_for_this_version(taxonomy: Taxonomy, name: str) -> None:
    # Failing here means a label enum changed: new taxonomy_version + ADR + relabel + retrain.
    assert list(taxonomy.values(name)) == FROZEN_2026_09_V1[name]


def test_every_model_label_enum_is_covered() -> None:
    assert set(MODEL_LABEL_ENUMS) == set(FROZEN_2026_09_V1)


@pytest.mark.parametrize("schema_name", [TRIAGE_OUTPUT_SCHEMA, TICKET_CREATE_SCHEMA])
def test_contract_schemas_reuse_the_taxonomy_enums(
    paths: RepoPaths, taxonomy: Taxonomy, schema_name: str
) -> None:
    enums = enums_from_schema(load_json_schema(schema_name, paths.schemas_dir))
    assert enums
    for name, values in enums.items():
        assert values == taxonomy.values(name), name


def test_triage_labels_mirror_the_contract(paths: RepoPaths) -> None:
    exported = load_json_schema(TRIAGE_OUTPUT_SCHEMA, paths.schemas_dir)
    mirror = TriageLabels.model_json_schema()
    # Same fields in the same order (decoding-schema / training-target key order).
    assert list(mirror["properties"]) == list(exported["properties"])
    assert set(mirror["required"]) == set(exported["required"])
    for name, prop in exported["properties"].items():
        ours = mirror["properties"][name]
        for bound in ("maxItems", "maxLength", "minLength"):
            assert ours.get(bound) == prop.get(bound), (name, bound)
        if "items" in prop and "maxLength" in prop["items"]:
            assert ours["items"].get("maxLength") == prop["items"]["maxLength"], name
    entity = exported["$defs"]["Entity"]
    ours_entity = EntityLabel.model_json_schema()
    assert list(ours_entity["properties"]) == list(entity["properties"])
    assert (
        ours_entity["properties"]["value"]["maxLength"]
        == entity["properties"]["value"]["maxLength"]
    )


def test_label_fields_accept_exactly_the_contract_values(
    paths: RepoPaths, taxonomy: Taxonomy, make_labels: Callable[..., TriageLabels]
) -> None:
    exported = load_json_schema(TRIAGE_OUTPUT_SCHEMA, paths.schemas_dir)
    checked = 0
    for name, prop in exported["properties"].items():
        enum = _ref_name(prop)
        if enum is None or enum not in taxonomy.enums:
            continue
        for value in taxonomy.values(enum):
            if name == "secondary_intents":
                if value not in ("sso_login_failure", "other_unclear"):
                    make_labels(secondary_intents=[value])
            else:
                make_labels(**{name: value})
        bogus: Any = ["not_a_value"] if name == "secondary_intents" else "not_a_value"
        with pytest.raises(ValidationError):
            make_labels(**{name: bogus})
        checked += 1
    assert checked >= 8


def test_ticket_payload_is_a_ticket_create_subset(paths: RepoPaths) -> None:
    exported = load_json_schema(TICKET_CREATE_SCHEMA, paths.schemas_dir)
    mirror = TicketPayload.model_json_schema()
    assert set(mirror["properties"]) <= set(exported["properties"])
    assert set(exported["properties"]) - set(mirror["properties"]) == {"customer_email"}
    for name in ("subject", "message"):
        for bound in ("minLength", "maxLength"):
            assert mirror["properties"][name][bound] == exported["properties"][name][bound]
    assert (
        mirror["properties"]["previous_messages"]["maxItems"]
        == exported["properties"]["previous_messages"]["maxItems"]
    )
    assert set(mirror["required"]) == set(exported["required"])


def test_label_rules_match_spec_routing(rules: LabelRules) -> None:
    assert {i: (r.queue, r.action) for i, r in rules.routing.items()} == SPEC_ROUTING


def test_critical_and_forced_sets_match_spec(rules: LabelRules) -> None:
    assert rules.critical_intents == {
        "security_report", "service_outage", "cancellation_request",
        "billing_duplicate_charge", "billing_payment_failure",
    }  # fmt: skip
    assert rules.critical_intents <= rules.forced_review_intents
    assert rules.forced_review_intents - rules.critical_intents == {
        "refund_request",
        "privacy_legal_request",
    }


def test_matrix_uses_only_taxonomy_values(matrix: Matrix, taxonomy: Taxonomy) -> None:
    assert set(matrix.spec.intents) == set(taxonomy.values("Intent"))
    for dim, enum in (
        ("plan", "PlanTier"),
        ("channel", "Channel"),
        ("sentiment", "Sentiment"),
        ("product_area", "ProductArea"),
    ):
        assert set(matrix.domains[dim]) == set(taxonomy.values(enum))
    entity_types = set(taxonomy.values("EntityType"))
    for card in matrix.spec.intents.values():
        assert set(card.required_entities) | set(card.optional_entities) <= entity_types


def test_fact_sheet_matches_taxonomy(facts: FactSheet, taxonomy: Taxonomy) -> None:
    assert set(facts.plans) == set(taxonomy.values("PlanTier"))
    assert set(facts.area_names) == set(taxonomy.values("ProductArea"))
    assert {p.value for p in facts.identity_providers} <= set(taxonomy.values("SamlIdp"))


def test_bitext_targets_are_taxonomy_intents(paths: RepoPaths, taxonomy: Taxonomy) -> None:
    mapping = load_mapping(paths.spec_dir / "bitext_mapping.v1.yaml", taxonomy)
    targets = {e.target for table in mapping.mapping.values() for e in table.values() if e.target}
    assert targets <= set(taxonomy.values("Intent"))


# --------------------------------------------------------------------------- loader behaviour


def _schema_dir(tmp_path: Path, document: object) -> Path:
    (tmp_path / "taxonomy.schema.json").write_text(json.dumps(document), encoding="utf-8")
    return tmp_path


def test_loader_rejects_a_missing_version(tmp_path: Path) -> None:
    with pytest.raises(TaxonomyError, match="taxonomy_version"):
        load_taxonomy(_schema_dir(tmp_path, {"properties": {}, "$defs": {}}))


def test_loader_rejects_a_missing_label_enum(paths: RepoPaths, tmp_path: Path) -> None:
    document = load_json_schema("taxonomy.schema.json", paths.schemas_dir)
    del document["$defs"]["Intent"]
    with pytest.raises(TaxonomyError, match="Intent"):
        load_taxonomy(_schema_dir(tmp_path, document))


def test_loader_rejects_bad_files(tmp_path: Path) -> None:
    with pytest.raises(TaxonomyError, match="not found"):
        load_json_schema("missing.schema.json", tmp_path)
    (tmp_path / "bad.schema.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="not valid JSON"):
        load_json_schema("bad.schema.json", tmp_path)
    (tmp_path / "list.schema.json").write_text("[]", encoding="utf-8")
    with pytest.raises(TaxonomyError, match="not a JSON object"):
        load_json_schema("list.schema.json", tmp_path)


def test_unknown_enum_and_member_checks(taxonomy: Taxonomy) -> None:
    with pytest.raises(TaxonomyError):
        taxonomy.values("Nope")
    check = member_check("Queue")
    assert check("incident_response") == "incident_response"
    with pytest.raises(ValueError, match="Queue"):
        check("helpdesk")


def test_fingerprint_is_stable_and_sensitive(taxonomy: Taxonomy) -> None:
    changed = Taxonomy(taxonomy.version, {**taxonomy.enums, "Queue": ("only_one",)})
    assert taxonomy.fingerprint() == taxonomy.fingerprint()
    assert changed.fingerprint() != taxonomy.fingerprint()


def test_repo_root_override(
    monkeypatch: pytest.MonkeyPatch, paths: RepoPaths, tmp_path: Path
) -> None:
    monkeypatch.setenv(REPO_ROOT_ENV, str(paths.root))
    assert find_repo_root() == paths.root.resolve()
    monkeypatch.setenv(REPO_ROOT_ENV, str(tmp_path))
    with pytest.raises(RepoNotFoundError):
        find_repo_root()
    monkeypatch.delenv(REPO_ROOT_ENV)
    with pytest.raises(RepoNotFoundError):
        find_repo_root(tmp_path)


def test_repo_paths_point_inside_the_repository(paths: RepoPaths) -> None:
    for location in (
        paths.schemas_dir,
        paths.spec_dir,
        paths.prompts_dir,
        paths.configs_dir,
        paths.pools_dir,
    ):
        assert location.is_dir(), location
    for location in (
        paths.generated_dir,
        paths.manifests_dir,
        paths.kb_dir,
        paths.hard_set_file,
        paths.ood_dir,
        paths.reports_dir,
    ):
        assert paths.root in location.parents
