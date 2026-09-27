"""Label rules: routing, action order, the single churn rule (A-06), cue lexicons."""

from pathlib import Path

import pytest
import yaml

from tw_ml.datagen.labelrules import LabelRules, LabelRulesError, load_label_rules
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy


def test_expected_action_order(rules: LabelRules) -> None:
    assert (
        rules.expected_action(
            "bug_report", customer_requested_human=True, information_sufficient=False
        )
        == "offer_human_contact"
    )
    assert (
        rules.expected_action(
            "bug_report", customer_requested_human=False, information_sufficient=False
        )
        == "request_more_information"
    )
    assert (
        rules.expected_action(
            "refund_request", customer_requested_human=False, information_sufficient=False
        )
        == "escalate_to_billing_for_review"
    )
    assert (
        rules.expected_action(
            "sso_login_failure", customer_requested_human=False, information_sufficient=False
        )
        == "request_saml_error_details_and_check_known_incident"
    )
    assert rules.allowed_actions(
        "bug_report", customer_requested_human=True, information_sufficient=True
    ) == ("offer_human_contact",)
    assert "incident_response" in rules.allowed_queues("sso_login_failure")


def test_single_churn_rule(rules: LabelRules) -> None:
    derive = rules.derive_churn
    assert (
        derive("none", sentiment="neutral", plan="business", intents=["cancellation_request"])
        == "high"
    )
    assert derive("ultimatum", sentiment="neutral", plan="free", intents=["bug_report"]) == "high"
    assert (
        derive("vague_alternatives", sentiment="neutral", plan="free", intents=["bug_report"])
        == "medium"
    )
    assert derive("none", sentiment="angry", plan="enterprise", intents=["bug_report"]) == "medium"
    assert derive("none", sentiment="angry", plan="starter", intents=["bug_report"]) == "low"
    assert (
        derive("none", sentiment="neutral", plan="business", intents=["how_to_question"]) == "low"
    )


@pytest.mark.parametrize(
    ("text", "high", "medium"),
    [
        ("We will not be renewing our contract.", True, False),
        ("Please cancel our subscription at the end of the month.", True, False),
        ("We plan to downgrade to the free plan.", True, False),
        ("If this isn't fixed today we will leave.", True, False),
        ("We are evaluating other tools right now.", False, True),
        ("This is the third time I write about this.", False, True),
        ("Please cancel the automation that runs twice.", False, False),
        ("How do I renew an API token?", False, False),
    ],
)
def test_churn_cue_lexicon(rules: LabelRules, text: str, high: bool, medium: bool) -> None:
    assert rules.has_high_cue(text) is high
    assert rules.has_medium_cue(text) is medium


def test_competitor_cue_needs_the_name_after_a_move(rules: LabelRules) -> None:
    assert rules.has_high_cue("We are moving to Vexal Works next month.", ["Vexal Works"])
    assert not rules.has_high_cue("Vexal Works looks nice.", ["Vexal Works"])


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("I want to talk to a real person.", "direct"),
        ("Please transfer me to a manager.", "direct"),
        ("Could someone give me a call tomorrow?", "indirect"),
        ("Just give us a ring when you can.", "indirect"),
        ("The chatbot answered quickly, thanks.", "none"),
    ],
)
def test_human_request_lexicon(rules: LabelRules, text: str, kind: str) -> None:
    assert rules.human_request_kind(text) == kind


def test_label_rules_errors(tmp_path: Path, paths: RepoPaths, taxonomy: Taxonomy) -> None:
    document = yaml.safe_load((paths.spec_dir / "label_rules.v1.yaml").read_text(encoding="utf-8"))
    del document["routing"]["bug_report"]
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(LabelRulesError, match="routing"):
        load_label_rules(path, taxonomy)
    document = yaml.safe_load((paths.spec_dir / "label_rules.v1.yaml").read_text(encoding="utf-8"))
    document["critical_intents"].append("not_an_intent")
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(LabelRulesError, match="not a Intent"):
        load_label_rules(path, taxonomy)
    path.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(LabelRulesError, match="mapping"):
        load_label_rules(path, taxonomy)
    document = yaml.safe_load((paths.spec_dir / "label_rules.v1.yaml").read_text(encoding="utf-8"))
    document["taxonomy_version"] = "old"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(LabelRulesError, match="targets taxonomy"):
        load_label_rules(path, taxonomy)
