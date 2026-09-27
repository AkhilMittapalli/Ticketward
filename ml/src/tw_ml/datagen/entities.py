"""Entity values for generation cards, sampled by code from the fact sheet and the pools.

ERPROT synthetic-data-generation A4: generators never invent names, amounts, ids or dates;
the card passes exact values and the generator must copy them verbatim. Invoice ids carry the
pool's prefix, so the structural leakage check C4 can see a cross-split reuse.
"""

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from tw_ml.datagen.factsheet import FactSheet
from tw_ml.datagen.pools import SEAT_PRICES, Company
from tw_ml.datagen.records import EntityLabel

CHARGE_SEAT_CAP: Final = 400
"""Charge amounts use at most this many seats (keeps enterprise amounts plausible)."""
_SERVER_ERROR_PREFIX: Final = "HTTP 5"
_MINUTES: Final[tuple[int, ...]] = tuple(range(0, 60, 5))


@dataclass(frozen=True, slots=True)
class EntityContext:
    """Everything an entity value may depend on.

    Attributes:
        intent: Primary intent.
        product_area: Cell product area.
        plan: Cell plan tier.
        company: The card's company.
        received_at: When the ticket arrives (dates are sampled before it).
        facts: Parsed fact sheet.
        values: Fixed value lists from the matrix (browsers, legal references...).
        error_code_prefixes: Allowed error-code prefixes for the intent (empty = the area's).
        competitor: Competitor name when the churn cue names one.
    """

    intent: str
    product_area: str
    plan: str
    company: Company
    received_at: datetime
    facts: FactSheet
    values: Mapping[str, Sequence[str]]
    error_code_prefixes: tuple[str, ...]
    competitor: str | None


@dataclass(frozen=True, slots=True)
class SampledEntity:
    """A sampled entity and the text the ticket must contain for it.

    Attributes:
        label: The label entity (normalized value for ``saml_idp``).
        display: The surface form the generator must write verbatim.
    """

    label: EntityLabel
    display: str


Sampler = Callable[[EntityContext, random.Random], SampledEntity | None]


def sample_entities(
    types: Sequence[str], ctx: EntityContext, rng: random.Random
) -> list[SampledEntity]:
    """Sample one value per requested entity type (unknown or impossible types are skipped).

    Args:
        types: Entity types in card order (duplicates ignored).
        ctx: Sampling context.
        rng: Cell-specific generator.

    Returns:
        Sampled entities in the order requested.
    """
    sampled: list[SampledEntity] = []
    for entity_type in dict.fromkeys(types):
        sampler = _SAMPLERS.get(entity_type)
        entity = sampler(ctx, rng) if sampler else None
        if entity is not None:
            sampled.append(entity)
    return sampled


def supported_types() -> frozenset[str]:
    """Entity types this module can sample.

    Returns:
        Entity type names.
    """
    return frozenset(_SAMPLERS)


def _plain(entity_type: str, value: str) -> SampledEntity:
    return SampledEntity(EntityLabel(type=entity_type, value=value), value)


def _error_code(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    codes = [c.code for c in ctx.facts.error_codes]
    if ctx.error_code_prefixes:
        codes = [c for c in codes if c.startswith(ctx.error_code_prefixes)]
    else:
        codes = [c.code for c in ctx.facts.codes_for(ctx.product_area)]
    if not ctx.facts.plans[ctx.plan].scim:
        codes = [c for c in codes if not c.startswith("SCIM_")]
    return _plain("error_code", rng.choice(codes)) if codes else None


def _http_status(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    statuses = [s.code for s in ctx.facts.http_statuses]
    if ctx.intent == "service_outage":
        statuses = [s for s in statuses if s.startswith(_SERVER_ERROR_PREFIX)]
    else:
        area = [s.code for s in ctx.facts.http_statuses if s.product_area == ctx.product_area]
        statuses = area or statuses
    return _plain("http_status", rng.choice(statuses)) if statuses else None


def _saml_idp(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    providers = [p for p in ctx.facts.identity_providers if ctx.plan in p.plans]
    if not providers:
        return None
    provider = rng.choice(providers)
    display = provider.aliases[0] if provider.aliases else provider.display_name
    return SampledEntity(EntityLabel(type="saml_idp", value=provider.value), display)


def _invoice_id(ctx: EntityContext, rng: random.Random) -> SampledEntity:
    return _plain("invoice_id", f"{ctx.company.invoice_prefix}{rng.randint(0, 999_999):06d}")


def _charge_amount(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    price = SEAT_PRICES.get(ctx.plan, 0)
    if price <= 0:
        return None
    months = 12 if rng.random() < 0.3 else 1  # noqa: PLR2004 - annual share of invoices
    amount = min(ctx.company.seats, CHARGE_SEAT_CAP) * price * months
    style = rng.randrange(3)
    formatted = (f"${amount:,.2f}", f"USD {amount:,}", f"{amount:,} USD")[style]
    return _plain("charge_amount", formatted)


def _currency(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    del ctx, rng
    return _plain("currency", "USD")


def _charge_date(ctx: EntityContext, rng: random.Random) -> SampledEntity:
    day = ctx.received_at - timedelta(days=rng.randint(1, 45))
    formats = (f"{day:%Y-%m-%d}", f"{day:%B} {day.day}", f"{day.day} {day:%b}")
    return _plain("charge_date", formats[rng.randrange(len(formats))])


def _workspace_id(ctx: EntityContext, rng: random.Random) -> SampledEntity:
    return _plain("workspace_id", rng.choice(ctx.company.workspace_ids))


def _account_id(ctx: EntityContext, rng: random.Random) -> SampledEntity:
    del rng
    return _plain("account_id", ctx.company.account_id)


def _user_count(ctx: EntityContext, rng: random.Random) -> SampledEntity:
    options = [
        int(v) for v in ctx.values.get("user_count_affected", ()) if int(v) <= ctx.company.seats
    ]
    count = rng.choice(options) if options else ctx.company.seats
    return _plain("user_count_affected", str(count))


def _from_list(entity_type: str) -> Sampler:
    def sample(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
        options = list(ctx.values.get(entity_type, ()))
        return _plain(entity_type, str(rng.choice(options))) if options else None

    return sample


def _app_version(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    platforms = ("ios", "android") if ctx.product_area == "mobile_apps" else ("desktop",)
    versions = [v for p in platforms for v in ctx.facts.app_versions.get(p, ())]
    return _plain("app_version", rng.choice(versions)) if versions else None


def _integration(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    options = [i.name for i in ctx.facts.integrations if ctx.plan in i.plans]
    return _plain("integration_name", rng.choice(options)) if options else None


def _api_endpoint(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    endpoints = list(ctx.facts.api_endpoints)
    return _plain("api_endpoint", rng.choice(endpoints)) if endpoints else None


def _feature(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    if ctx.intent == "plan_pricing_inquiry":
        # Customers ask about features they do not have yet (§3); any area qualifies.
        options = [f.name for f in ctx.facts.features if ctx.plan not in f.plans]
        options = options or [f.name for f in ctx.facts.features]
    else:
        options = [f.name for f in ctx.facts.features_for(ctx.product_area, ctx.plan)]
    return _plain("feature_name", rng.choice(options)) if options else None


def _region(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    del rng
    display = ctx.facts.regions.get(ctx.company.region)
    return _plain("region", display) if display else None


def _timestamp(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    hours = [int(h) for h in ctx.values.get("timestamp_hours", ())]
    if not hours:
        return None
    return _plain("timestamp", f"{rng.choice(hours):02d}:{rng.choice(_MINUTES):02d} UTC")


def _competitor(ctx: EntityContext, rng: random.Random) -> SampledEntity | None:
    del rng
    return _plain("competitor_name", ctx.competitor) if ctx.competitor else None


_SAMPLERS: Final[Mapping[str, Sampler]] = {
    "error_code": _error_code,
    "http_status": _http_status,
    "saml_idp": _saml_idp,
    "invoice_id": _invoice_id,
    "charge_amount": _charge_amount,
    "currency": _currency,
    "charge_date": _charge_date,
    "workspace_id": _workspace_id,
    "account_id": _account_id,
    "user_count_affected": _user_count,
    "browser": _from_list("browser"),
    "os": _from_list("os"),
    "app_version": _app_version,
    "integration_name": _integration,
    "api_endpoint": _api_endpoint,
    "feature_name": _feature,
    "region": _region,
    "timestamp": _timestamp,
    "competitor_name": _competitor,
    "legal_reference": _from_list("legal_reference"),
    "steps_already_tried": _from_list("steps_already_tried"),
}
