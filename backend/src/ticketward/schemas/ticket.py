"""Ticket ingestion contract ``TicketCreate`` (spec §6.1, BR-026).

Field limits are part of the DoS controls (spec §12.2): the request body is capped at
256 KB by middleware, ``message`` at 20,000 characters, history at 50 messages.
"""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, EmailStr, Field

from ticketward.domain.taxonomy import Channel, PlanTier, ProductArea
from ticketward.schemas.common import ArrBand, ContractModel, Platform, Region

MESSAGE_MAX_CHARS = 20_000
SUBJECT_MAX_CHARS = 300
PREVIOUS_MESSAGES_MAX = 50
EXTERNAL_ID_MAX_CHARS = 128


class PreviousMessage(ContractModel):
    """A prior message in the ticket thread."""

    author: Literal["customer", "agent", "system"]
    body: str = Field(max_length=MESSAGE_MAX_CHARS)
    sent_at: AwareDatetime


class AccountMetadata(ContractModel):
    """Optional CRM metadata for the customer account (synthetic in this project)."""

    account_id: str = Field(pattern=r"^acct_[A-Za-z0-9]{4,32}$")
    company_name: str | None = Field(default=None, max_length=200)
    arr_band: ArrBand | None = None
    region: Region | None = None
    seats: int | None = Field(default=None, ge=1, le=1_000_000)
    csm_owner_id: UUID | None = None


class ProductMetadata(ContractModel):
    """Optional product context supplied by the source channel."""

    product_area_hint: ProductArea | None = None
    app_version: str | None = Field(default=None, max_length=50)
    platform: Platform | None = None


class TicketCreate(ContractModel):
    """Inbound ticket from the web form, JSON API or simulated email feed (BR-017)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str | None = Field(
        default=None, max_length=EXTERNAL_ID_MAX_CHARS, description="Dedupe key per source."
    )
    customer_tier: PlanTier
    channel: Channel
    subject: str = Field(min_length=1, max_length=SUBJECT_MAX_CHARS)
    message: str = Field(min_length=1, max_length=MESSAGE_MAX_CHARS)
    previous_messages: list[PreviousMessage] = Field(
        default_factory=list, max_length=PREVIOUS_MESSAGES_MAX
    )
    customer_email: EmailStr | None = Field(
        default=None, description="Stored encrypted; masked before any model call."
    )
    account: AccountMetadata | None = None
    product: ProductMetadata | None = None
    received_at: AwareDatetime | None = None
