"""Agent feedback contract (spec v1.1 §6.5, BR-021).

Feedback is append-only: the ``feedback_events`` table grants ``tw_app`` only
INSERT (no UPDATE/DELETE).  Text columns are scrubbed only by the purge function
(§10 deletion request).

The server computes and stores:

* ``edit_distance_ratio`` — normalized Levenshtein between the draft body and the
  agent-approved ``final_text``.
* ``time_to_decision_ms`` — wall-clock time from draft creation to feedback.

Training-data exports exclude records whose ``model_version_id`` links to
``provider = 'anthropic'`` (A-01).
"""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from ticketward.schemas.common import ContractModel

FeedbackTargetType = Literal[
    "triage_field", "draft", "citation", "handoff", "policy_decision"
]
"""What the feedback is about."""

FeedbackAction = Literal["accept", "edit", "reject", "flag", "override"]
"""What the agent did."""

FeedbackField = Literal[
    "intent",
    "priority",
    "sentiment",
    "churn_risk",
    "product_area",
    "recommended_queue",
    "recommended_action",
]
"""Triage field that was corrected (only when ``target_type="triage_field"``)."""

FlagReason = Literal[
    "hallucination",
    "wrong_citation",
    "unsafe",
    "tone",
    "pii_leak",
    "outdated_source",
    "other",
]
"""Why the agent flagged something (only when ``action="flag"``)."""

COMMENT_MAX_CHARS = 2_000
EDITED_TEXT_MAX_CHARS = 20_000


class FeedbackCreate(ContractModel):
    """Agent feedback on a triage field, draft, citation, handoff or policy decision.

    ``corrected_value`` is validated against the target enum at the service layer
    when ``target_type="triage_field"`` (e.g. a corrected intent must be a valid
    ``Intent`` value).
    """

    target_type: FeedbackTargetType
    target_id: UUID
    field: FeedbackField | None = None
    action: FeedbackAction
    corrected_value: str | None = Field(default=None, max_length=200)
    edited_text: str | None = Field(default=None, max_length=EDITED_TEXT_MAX_CHARS)
    flag_reason: FlagReason | None = None
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_CHARS)

    @model_validator(mode="after")
    def _field_required_for_triage_field(self) -> Self:
        """``field`` must be set when ``target_type`` is ``triage_field``."""
        if self.target_type == "triage_field" and self.field is None:
            msg = "field is required when target_type is 'triage_field'"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _flag_reason_required_for_flag_action(self) -> Self:
        """``flag_reason`` must be set when ``action`` is ``flag``."""
        if self.action == "flag" and self.flag_reason is None:
            msg = "flag_reason is required when action is 'flag'"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _corrected_value_required_for_edit(self) -> Self:
        """``corrected_value`` or ``edited_text`` must be set when ``action`` is ``edit``."""
        if self.action == "edit" and self.corrected_value is None and self.edited_text is None:
            msg = "corrected_value or edited_text is required when action is 'edit'"
            raise ValueError(msg)
        return self
