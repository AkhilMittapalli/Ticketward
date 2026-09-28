"""Newsletter-safe high-churn cues (spec errata 6, D6-10).

A high-churn cue must mean leaving the product, not unsubscribing from e-mails.
"""

import pytest

from tw_ml.datagen.labelrules import LabelRules


@pytest.mark.parametrize(
    "text",
    [
        "Please cancel my newsletter subscription.",
        "How do I cancel the email notifications for our account?",
        "Can you cancel the weekly digest subscription for my workspace?",
        "Cancel the marketing emails on our account, they are too frequent.",
        "I want to cancel the alert subscription on this plan.",
    ],
)
def test_email_and_notification_cancellations_are_not_churn(rules: LabelRules, text: str) -> None:
    assert not rules.has_high_cue(text)


@pytest.mark.parametrize(
    "text",
    [
        "We will cancel our subscription at the end of the term.",
        "Please cancel our account, and stop the marketing emails too.",
        "Our contract will not be renewed.",
        "This is your last chance before we move on.",
        "We're switching to another tool next month.",
    ],
)
def test_real_departure_cues_still_count(rules: LabelRules, text: str) -> None:
    assert rules.has_high_cue(text)


def test_exclusions_are_loaded_from_the_rules_file(rules: LabelRules) -> None:
    assert rules.high_cue_exclusions
    assert all(p.flags & 2 for p in rules.high_cue_exclusions)  # re.IGNORECASE
