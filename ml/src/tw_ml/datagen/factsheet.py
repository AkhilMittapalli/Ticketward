"""Parse ``data/spec/fact_sheet.v1.md``: the only product facts a generator prompt may contain.

The sheet is Markdown so that it can be pasted into a prompt as is. Its tables are also the
machine-readable source for the sampler (features and error codes per product area, plan
limits) and for the rule-checker's fact-sheet plausibility checks.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tw_ml.datagen.paths import default_paths
from tw_ml.datagen.taxonomy import Taxonomy, load_taxonomy

FACT_SHEET_FILE: Final = "fact_sheet.v1.md"
_COMMENT: Final = re.compile(r"<!--.*?-->\s*", re.DOTALL)
_HEADING: Final = re.compile(r"^## (.+?)\s*$")
_ALL_PLANS: Final = "all"


class FactSheetError(ValueError):
    """Raised when the fact sheet lacks a section, a column or a valid value."""


Table = list[dict[str, str]]


@dataclass(frozen=True, slots=True)
class PlanFacts:
    """Facts about one plan.

    Attributes:
        name: Plan tier value.
        price_per_seat: Monthly USD price per seat, or None for custom contracts.
        seats_max: Seat limit, or None for unlimited.
        sso: Whether SAML SSO is available.
        scim: Whether SCIM provisioning is available.
    """

    name: str
    price_per_seat: int | None
    seats_max: int | None
    sso: bool
    scim: bool


@dataclass(frozen=True, slots=True)
class Offering:
    """A feature or integration and the plans that include it.

    Attributes:
        name: Display name (entity value when used verbatim).
        product_area: Product area value.
        plans: Plan tiers that include it.
    """

    name: str
    product_area: str
    plans: frozenset[str]


@dataclass(frozen=True, slots=True)
class CodeFact:
    """An error code or HTTP status.

    Attributes:
        code: Code as shown to users (``SAML_ERR_302``, ``HTTP 429``).
        product_area: Product area it belongs to.
        message: Shown message or meaning.
    """

    code: str
    product_area: str
    message: str


@dataclass(frozen=True, slots=True)
class IdentityProvider:
    """A SAML identity provider.

    Attributes:
        display_name: Name customers write.
        value: ``saml_idp`` entity value.
        aliases: Surface forms that count as a literal mention.
        plans: Plans that support it.
    """

    display_name: str
    value: str
    aliases: tuple[str, ...]
    plans: frozenset[str]


@dataclass(frozen=True, slots=True)
class FactSheet:
    """Parsed fact sheet.

    Attributes:
        prompt_text: The sheet as placed in prompts (header comment removed).
        plans: Plan facts by tier.
        area_names: Product area value to display name.
        features: Features.
        integrations: Integrations.
        error_codes: Product error codes.
        http_statuses: HTTP statuses.
        identity_providers: SAML identity providers.
        regions: Region value to display name.
        app_versions: Platform to known app versions (current first).
        api_endpoints: Documented API endpoint paths.
    """

    prompt_text: str
    plans: Mapping[str, PlanFacts]
    area_names: Mapping[str, str]
    features: tuple[Offering, ...]
    integrations: tuple[Offering, ...]
    error_codes: tuple[CodeFact, ...]
    http_statuses: tuple[CodeFact, ...]
    identity_providers: tuple[IdentityProvider, ...]
    regions: Mapping[str, str]
    app_versions: Mapping[str, tuple[str, ...]]
    api_endpoints: tuple[str, ...]

    def features_for(self, product_area: str, plan: str | None = None) -> list[Offering]:
        """Features of one product area, optionally only those included in ``plan``.

        Args:
            product_area: Product area value.
            plan: Plan tier filter (None = any plan).

        Returns:
            Matching features in sheet order.
        """
        return [
            f
            for f in self.features
            if f.product_area == product_area and (plan is None or plan in f.plans)
        ]

    def codes_for(self, product_area: str) -> list[CodeFact]:
        """Error codes of one product area.

        Args:
            product_area: Product area value.

        Returns:
            Codes in sheet order.
        """
        return [c for c in self.error_codes if c.product_area == product_area]

    def known_codes(self) -> frozenset[str]:
        """Every error code and HTTP status in the sheet.

        Returns:
            Code strings.
        """
        return frozenset(c.code for c in (*self.error_codes, *self.http_statuses))

    def idp(self, value: str) -> IdentityProvider | None:
        """Look up an identity provider by its ``saml_idp`` value.

        Args:
            value: ``saml_idp`` entity value.

        Returns:
            The provider, or None when unknown.
        """
        return next((p for p in self.identity_providers if p.value == value), None)


def parse_tables(markdown: str) -> dict[str, Table]:
    """Parse the first pipe table under every ``## `` heading.

    Args:
        markdown: Fact-sheet Markdown.

    Returns:
        Heading text to rows (header cell -> value, backticks and padding removed).
    """
    tables: dict[str, Table] = {}
    heading: str | None = None
    header: list[str] | None = None
    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match:
            heading, header = match.group(1), None
            tables.setdefault(heading, [])
            continue
        if heading is None or not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [cell.strip().strip("`").strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            header = [cell.lower() for cell in cells]
        elif not all(set(cell) <= {"-", ":"} for cell in cells):
            tables[heading].append(dict(zip(header, cells, strict=False)))
    return tables


def load_fact_sheet(path: Path | None = None, taxonomy: Taxonomy | None = None) -> FactSheet:
    """Load and validate the fact sheet.

    Args:
        path: File override (defaults to ``data/spec/fact_sheet.v1.md``).
        taxonomy: Taxonomy to validate product areas, plans and IdP values against.

    Returns:
        The parsed fact sheet.

    Raises:
        FactSheetError: If a required section or value is missing or invalid.
    """
    tax = taxonomy or load_taxonomy()
    source = path or default_paths().spec_dir / FACT_SHEET_FILE
    markdown = source.read_text(encoding="utf-8")
    tables = parse_tables(markdown)
    plans = {row["plan"]: _plan(row, tax) for row in _section(tables, "Plans", ("plan",))}
    if set(plans) != set(tax.values("PlanTier")):
        msg = "fact sheet Plans must list exactly the PlanTier values"
        raise FactSheetError(msg)
    areas = {
        _check(row["product_area"], tax, "ProductArea"): row["display_name"]
        for row in _section(tables, "Product areas", ("product_area", "display_name"))
    }
    if set(areas) != set(tax.values("ProductArea")):
        msg = "fact sheet Product areas must list exactly the ProductArea values"
        raise FactSheetError(msg)
    return FactSheet(
        prompt_text=_COMMENT.sub("", markdown).strip() + "\n",
        plans=plans,
        area_names=areas,
        features=_offerings(tables, "Features", "feature", tax),
        integrations=_offerings(tables, "Integrations", "integration", tax),
        error_codes=_codes(tables, "Error codes", "code", "shown_message", tax),
        http_statuses=_codes(tables, "HTTP statuses", "status", "meaning", tax),
        identity_providers=tuple(
            IdentityProvider(
                display_name=row["idp"],
                value=_check(row["saml_idp_value"], tax, "SamlIdp"),
                aliases=tuple(a.strip() for a in row["aliases"].split(";") if a.strip()),
                plans=_plans(row["plans"], tax),
            )
            for row in _section(tables, "Identity providers", ("idp", "saml_idp_value", "aliases"))
        ),
        regions={
            row["region"]: row["display_name"]
            for row in _section(tables, "Regions", ("region", "display_name"))
        },
        app_versions={
            row["platform"]: tuple(
                v for v in (row["current_version"], row["previous_version"]) if _is_version(v)
            )
            for row in _section(tables, "Apps", ("platform", "current_version"))
        },
        api_endpoints=_endpoints(_section(tables, "API", ("item", "value"))),
    )


def _section(tables: Mapping[str, Table], name: str, columns: Sequence[str]) -> Table:
    rows = tables.get(name)
    if not rows:
        msg = f"fact sheet section {name!r} is missing or empty"
        raise FactSheetError(msg)
    missing = [c for c in columns if c not in rows[0]]
    if missing:
        msg = f"fact sheet section {name!r} lacks columns: {', '.join(missing)}"
        raise FactSheetError(msg)
    return rows


def _check(value: str, tax: Taxonomy, enum: str) -> str:
    if not tax.has(enum, value):
        msg = f"fact sheet value {value!r} is not a {enum}"
        raise FactSheetError(msg)
    return value


def _plans(cell: str, tax: Taxonomy) -> frozenset[str]:
    if cell.strip().lower() == _ALL_PLANS:
        return frozenset(tax.values("PlanTier"))
    return frozenset(_check(p.strip(), tax, "PlanTier") for p in cell.split(",") if p.strip())


def _plan(row: Mapping[str, str], tax: Taxonomy) -> PlanFacts:
    price = row.get("price_per_seat_month", "").lstrip("$").strip()
    seats = row.get("seats_max", "").strip()
    return PlanFacts(
        name=_check(row["plan"], tax, "PlanTier"),
        price_per_seat=int(price) if price.isdigit() else None,
        seats_max=int(seats) if seats.isdigit() else None,
        sso=row.get("sso", "no").strip().lower() != "no",
        scim=row.get("scim", "no").strip().lower() == "yes",
    )


def _offerings(
    tables: Mapping[str, Table], name: str, key: str, tax: Taxonomy
) -> tuple[Offering, ...]:
    return tuple(
        Offering(
            name=row[key],
            product_area=_check(row["product_area"], tax, "ProductArea"),
            plans=_plans(row["plans"], tax),
        )
        for row in _section(tables, name, (key, "product_area", "plans"))
    )


def _codes(
    tables: Mapping[str, Table], name: str, key: str, message: str, tax: Taxonomy
) -> tuple[CodeFact, ...]:
    return tuple(
        CodeFact(
            code=row[key],
            product_area=_check(row["product_area"], tax, "ProductArea"),
            message=row[message],
        )
        for row in _section(tables, name, (key, "product_area", message))
    )


def _is_version(value: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+){1,3}", value.strip()))


def _endpoints(rows: Table) -> tuple[str, ...]:
    values = next((row["value"] for row in rows if row["item"] == "endpoints"), "")
    return tuple(p.strip() for p in values.split(",") if p.strip().startswith("/"))
