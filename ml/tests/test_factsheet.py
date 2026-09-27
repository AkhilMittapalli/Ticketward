"""Fact sheet parsing: the only product facts generator prompts may contain."""

from pathlib import Path

import pytest

from tw_ml.datagen.factsheet import FactSheet, FactSheetError, load_fact_sheet, parse_tables
from tw_ml.datagen.paths import RepoPaths
from tw_ml.datagen.taxonomy import Taxonomy


def test_fact_sheet_parses(facts: FactSheet) -> None:
    assert facts.plans["business"].seats_max == 500
    assert facts.plans["enterprise"].seats_max is None
    assert facts.plans["enterprise"].scim
    assert not facts.plans["starter"].sso
    assert facts.plans["free"].price_per_seat == 0
    assert "SAML_ERR_302" in facts.known_codes()
    assert "HTTP 429" in facts.known_codes()
    assert facts.idp("azure_ad") is not None
    assert facts.idp("nope") is None
    assert facts.features_for("sso_identity", "business")
    assert all("SCIM" not in f.name for f in facts.features_for("sso_identity", "business"))
    assert facts.codes_for("automations")
    assert facts.api_endpoints[0] == "/v2/tasks"
    assert facts.app_versions["ios"] == ("5.8.2", "5.7.4")
    assert "<!--" not in facts.prompt_text


def test_fact_sheet_has_no_kb_prose_or_example_tickets(paths: RepoPaths) -> None:
    text = (paths.spec_dir / "fact_sheet.v1.md").read_text(encoding="utf-8")
    body = [line for line in text.splitlines() if line and not line.startswith(("|", "#", "<!--"))]
    # Outside tables and headings only a disclaimer and one instruction sentence remain.
    assert len(body) <= 12
    assert '"' not in text  # no quoted customer utterances


def test_fact_sheet_errors(tmp_path: Path, taxonomy: Taxonomy) -> None:
    sheet = tmp_path / "fact_sheet.md"
    sheet.write_text("## Plans\n\n| plan |\n|---|\n| free |\n", encoding="utf-8")
    with pytest.raises(FactSheetError):
        load_fact_sheet(sheet, taxonomy)
    tables = parse_tables("## A\n\ntext\n\n| x | y |\n|---|---|\n| `1` | 2 |\n")
    assert tables == {"A": [{"x": "1", "y": "2"}]}
