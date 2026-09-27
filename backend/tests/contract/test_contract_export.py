"""Contract stability: committed JSON Schemas and OpenAPI must match the code."""

import json
from pathlib import Path
from typing import Any

import pytest

from ticketward.schemas.export import JSON_SCHEMA_DIALECT, build_json_schemas, render_json
from ticketward.schemas.triage import TriageModelOutput
from ticketward.tools.export_contracts import build_openapi, main, sync_contract_files

EXPECTED_FILES = {
    "schemas/json/ticket_create.schema.json",
    "schemas/json/triage_model_output.schema.json",
    "schemas/json/triage_result.schema.json",
    "schemas/json/problem_detail.schema.json",
    "schemas/json/taxonomy.schema.json",
    "docs/openapi.json",
}


def test_committed_contracts_are_up_to_date(repo_root: Path) -> None:
    stale = sync_contract_files(repo_root, check=True)
    assert stale == [], "run `uv run python ../scripts/export_schemas.py` and commit the result"


def test_export_is_deterministic() -> None:
    first = {name: render_json(schema) for name, schema in build_json_schemas().items()}
    second = {name: render_json(schema) for name, schema in build_json_schemas().items()}
    assert first == second
    assert render_json(build_openapi()) == render_json(build_openapi())


def test_every_schema_declares_draft_2020_12() -> None:
    for schema in build_json_schemas().values():
        assert schema["$schema"] == JSON_SCHEMA_DIALECT


def test_model_output_schema_is_closed_and_ordered() -> None:
    schema = build_json_schemas()["triage_model_output"]
    assert schema["additionalProperties"] is False
    assert list(schema["properties"]) == list(TriageModelOutput.model_fields)
    assert set(schema["required"]) == {
        "intent",
        "priority",
        "sentiment",
        "churn_risk",
        "product_area",
        "recommended_queue",
        "recommended_action",
        "customer_requested_human",
        "information_sufficient",
        "rationale",
    }


def test_model_output_schema_is_span_free_but_result_schema_has_spans() -> None:
    # v1.1 A-29: the SLM contract never contains spans; the enriched envelope does.
    schemas = build_json_schemas()
    assert "source_span" not in json.dumps(schemas["triage_model_output"])
    result = schemas["triage_result"]
    resolved = result["$defs"]["ResolvedEntity"]
    assert set(resolved["properties"]) == {"type", "value", "source_span"}
    assert set(resolved["required"]) == {"type", "value", "source_span"}
    assert result["properties"]["entities"]["items"] == {"$ref": "#/$defs/ResolvedEntity"}
    span = result["$defs"]["Span"]["properties"]
    assert span["start"]["minimum"] == 0
    assert span["end"]["minimum"] == 0


def test_result_schema_bounds_every_confidence_and_carries_calibration_meta() -> None:
    result = build_json_schemas()["triage_result"]
    confidence = result["$defs"]["FieldConfidence"]
    assert "p_critical" in confidence["required"]
    for field in confidence["properties"].values():
        assert (field["minimum"], field["maximum"]) == (0.0, 1.0)
    meta = result["$defs"]["ModelMeta"]
    for field in (
        "calibrator_version",
        "calibration_fit_run_id",
        "decoding_backend",
        "logprobs_mode",
    ):
        assert field in meta["required"]


def test_problem_detail_schema_documents_every_code() -> None:
    codes = build_json_schemas()["problem_detail"]["$defs"]["ErrorCode"]["enum"]
    assert {"UNSUPPORTED_MEDIA_TYPE", "DEMO_LOCKED", "REFRESH_SUPERSEDED", "MAINTENANCE"} <= set(
        codes
    )


def test_openapi_documents_errors_as_problem_json() -> None:
    document = build_openapi()
    assert "HTTPValidationError" not in document["components"]["schemas"]
    ready = document["paths"]["/api/v1/health/ready"]["get"]
    assert ready["operationId"] == "health_ready"
    for status in ("4XX", "5XX", "503"):
        content = ready["responses"][status]["content"]
        assert list(content) == ["application/problem+json"]
        assert content["application/problem+json"]["schema"]["$ref"].endswith("/ProblemDetail")
    live = document["paths"]["/api/v1/health/live"]["get"]
    assert list(live["responses"]["200"]["content"]) == ["application/json"]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_writes_then_checks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo-root", str(tmp_path), "--check"]) == 1
    assert "out of date" in capsys.readouterr().err

    assert main(["--repo-root", str(tmp_path)]) == 0
    written = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.json")}
    assert written == EXPECTED_FILES
    assert "Updated" in capsys.readouterr().out

    assert main(["--repo-root", str(tmp_path), "--check"]) == 0
    assert "up to date" in capsys.readouterr().out

    raw = (tmp_path / "docs/openapi.json").read_bytes()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    assert (
        _read_json(tmp_path / "schemas/json/taxonomy.schema.json")["title"] == "TicketwardTaxonomy"
    )


def test_cli_detects_drift(tmp_path: Path) -> None:
    assert main(["--repo-root", str(tmp_path)]) == 0
    target = tmp_path / "schemas/json/ticket_create.schema.json"
    target.write_text("{}\n", encoding="utf-8")
    assert main(["--repo-root", str(tmp_path), "--check"]) == 1
