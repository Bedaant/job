"""Per-ATS field schemas (ADR-015 Phase 2): on a known ATS, a field whose
name/id is a verified system field fills deterministically regardless of how
the label is worded. Unknown/None ats_type = exactly the old behaviour.
"""
from unittest.mock import patch

import pytest

from formfill.ats_schemas import ATS_FIELD_SCHEMAS
from formfill.deterministic import match_field_deterministic
from formfill.map_fields import _BASICS_FIELDS, map_form_fields
from tests.test_deterministic_fields import PROFILE, _field
from tests.test_extension_map_fields import _client, _new_user


@pytest.mark.parametrize("ats_type, attrs, key", [
    ("ashby", {"name": "_systemfield_name", "dom_id": "_systemfield_name"}, "full_name"),
    ("ashby", {"name": "_systemfield_email", "dom_id": "_systemfield_email"}, "email"),
    ("lever", {"name": "phone"}, "phone"),
    ("lever", {"name": "urls[Portfolio]"}, "website_url"),
    ("greenhouse", {"dom_id": "phone"}, "phone"),
])
def test_a_known_ats_system_field_fills_whatever_the_label_says(ats_type, attrs, key):
    field = _field(label_text="What should we call you?", **attrs)
    result = match_field_deterministic(field, PROFILE, ats_type=ats_type)
    assert result == {"field_id": "f1", "maps_to": f"profile.{key}", "confidence": 1.0, "value": PROFILE[key]}


def test_the_same_field_without_an_ats_type_is_not_resolved():
    field = _field(label_text="What should we call you?", name="_systemfield_name", dom_id="_systemfield_name")
    assert match_field_deterministic(field, PROFILE) is None
    assert match_field_deterministic(field, PROFILE, ats_type="workday") is None


def test_a_known_field_with_no_profile_value_falls_through():
    field = _field(name="phone")
    assert match_field_deterministic(field, {"email": "a@b.com"}, ats_type="lever") is None


def test_given_and_family_name_are_never_split_from_full_name():
    # Greenhouse's first_name/last_name are real, verified ids — deliberately
    # absent from the table. Splitting full_name would be a guess.
    for dom_id in ("first_name", "last_name"):
        assert match_field_deterministic(_field(dom_id=dom_id), PROFILE, ats_type="greenhouse") is None


def test_every_schema_target_is_a_key_the_profile_summary_can_hold():
    targets = {key for schema in ATS_FIELD_SCHEMAS.values() for key in schema.values()}
    assert targets <= {"email", *_BASICS_FIELDS}


@patch("formfill.map_fields.call_llm")
def test_the_demographic_rail_still_runs_before_the_ats_table(mock_call_llm):
    fields = [{"field_id": "f1", "label_text": "Gender", "input_type": "text", "name": "name"}]
    result = map_form_fields(fields, PROFILE, ats_type="lever")
    assert result == [{"field_id": "f1", "maps_to": "unknown", "confidence": 0.0, "value": None}]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_uses_the_ats_table_with_zero_llm_calls(mock_call_llm):
    fields = [{"field_id": "f1", "label_text": "Legal name", "input_type": "text", "name": "_systemfield_name"}]
    result = map_form_fields(fields, PROFILE, ats_type="ashby")
    assert result[0]["value"] == PROFILE["full_name"]
    mock_call_llm.assert_not_called()


@patch("main.map_form_fields", return_value=[])
def test_endpoint_forwards_ats_type_and_bounds_it(mock_map):
    client = _client()
    headers = _new_user(client, "ats-schema@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    body = {"profile_id": profile["id"], "url": "https://jobs.lever.co/acme/1/apply",
            "fields": [{"field_id": "f1", "input_type": "text"}]}

    assert client.post("/extension/map-fields", headers=headers, json={**body, "ats_type": "lever"}).status_code == 200
    assert mock_map.call_args.kwargs["ats_type"] == "lever"

    assert client.post("/extension/map-fields", headers=headers, json=body).status_code == 200
    assert mock_map.call_args.kwargs["ats_type"] is None

    too_long = {**body, "ats_type": "x" * 33}
    assert client.post("/extension/map-fields", headers=headers, json=too_long).status_code == 422
