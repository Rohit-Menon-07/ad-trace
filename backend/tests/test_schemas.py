from typing import get_args

import pytest

from backend.app import export_types
from backend.app.schemas import RecordDetail, SearchResponse
from backend.tests.fixtures import mock_scenarios as mocks


@pytest.mark.parametrize("key", list(get_args(mocks.ScenarioKey)))
def test_every_mock_scenario_validates_against_search_response(key: str) -> None:
    resp = mocks.MOCK_SCENARIOS[key]
    roundtrip = SearchResponse.model_validate_json(resp.model_dump_json())
    assert roundtrip == resp
    assert roundtrip.mock is True
    assert roundtrip.status == key


def test_all_four_scenarios_exist() -> None:
    assert set(mocks.MOCK_SCENARIOS) == {"answered", "partial", "refused", "needs_clarification"}


@pytest.mark.parametrize("record_id", list(mocks.MOCK_RECORDS))
def test_mock_records_validate_and_offsets_match(record_id: str) -> None:
    detail = RecordDetail.model_validate_json(mocks.MOCK_RECORDS[record_id].model_dump_json())
    assert detail.mock is True
    for s in detail.sentences:
        assert detail.record.summary[s.start : s.end] == s.text


def test_mock_citation_spans_point_at_quotes() -> None:
    for resp in mocks.MOCK_SCENARIOS.values():
        for claim in resp.claims:
            for c in claim.citations:
                summary = mocks.MOCK_RECORDS[c.evidence_id.split("#")[0]].record.summary
                assert c.span_start is not None and c.span_end is not None
                assert summary[c.span_start : c.span_end] == c.quote


def test_mock_cite_rejects_quote_not_in_sentence() -> None:
    with pytest.raises(ValueError):
        mocks.mock_cite("MOCK-R0001#s0", "torque 45 Nm")


def test_refusals_carry_reason_codes_and_no_claims() -> None:
    for key in ("refused", "needs_clarification"):
        resp = mocks.MOCK_SCENARIOS[key]
        assert resp.reason_code is not None
        assert resp.claims == []


def test_exported_typescript_is_up_to_date() -> None:
    expected = export_types.render_ts()
    actual = export_types.TS_PATH.read_text(encoding="utf-8")
    assert actual == expected, "frontend/src/types/api.ts is stale: run `python -m backend.app.export_types`"


def test_exported_json_schema_is_up_to_date() -> None:
    expected = export_types.render_schema_json()
    actual = export_types.SCHEMA_PATH.read_text(encoding="utf-8")
    assert actual == expected, "docs/api.schema.json is stale: run `python -m backend.app.export_types`"


def test_ts_generator_handles_nullable_alias_and_dict() -> None:
    aliases = {"'A' | 'B'": "AB"}
    assert export_types.ts_type({"anyOf": [{"enum": ["A", "B"], "type": "string"}, {"type": "null"}]}, aliases) == (
        "AB | null"
    )
    assert export_types.ts_type({"type": "object", "additionalProperties": {"type": "integer"}}, {}) == (
        "Record<string, number>"
    )
    assert export_types.ts_type({"type": "string", "format": "date"}, {}) == "ISODate"
