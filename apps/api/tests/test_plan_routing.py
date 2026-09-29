"""ADR-016: the stored Stagehand plan routes fields inside map_form_fields, but
never overrides the demographic/consent rail or the deterministic matcher, and
never sends a plan-routed field to the LLM."""
from unittest.mock import patch

from formfill.map_fields import map_form_fields

PROFILE = {"email": "jane@example.com", "city": "San Francisco", "country_code": "US"}
LLM_UNKNOWN = '[{"field_id": "f1", "maps_to": "unknown", "confidence": 0.0, "value": null}]'
FLAGGED = {"field_id": "f1", "maps_to": "unknown", "confidence": 0.0, "value": None}


def _plan(key, fill_from):
    return {"fields": [{"key": key, "label": "x", "fill_from": fill_from}]}


@patch("formfill.map_fields.call_llm", return_value=LLM_UNKNOWN)
def test_plan_none_is_identical_to_no_plan(_llm):
    fields = [{"field_id": "f1", "label_text": "Years of experience", "input_type": "text", "dom_id": "yoe"}]
    assert map_form_fields(fields, PROFILE, plan=None) == map_form_fields(fields, PROFILE)


@patch("formfill.map_fields.call_llm")
def test_plan_routes_profile_key_without_llm(llm):
    fields = [{"field_id": "f1", "label_text": "Current location", "input_type": "text", "dom_id": "loc"}]
    result = map_form_fields(fields, PROFILE, plan=_plan("loc", "city"))
    assert result == [{"field_id": "f1", "maps_to": "plan:profile.city", "confidence": 1.0, "value": "San Francisco"}]
    llm.assert_not_called()


@patch("formfill.map_fields.call_llm", return_value=LLM_UNKNOWN)
def test_plan_never_is_not_trusted(llm):
    # ADR-016 amendment: the plan's "never" is unreliable both ways (it tagged LinkedIn
    # and website fields "never"); the consent/EEO rail decides, so "never" routes nothing.
    fields = [{"field_id": "f1", "label_text": "LinkedIn profile", "input_type": "text", "dom_id": "li"}]
    assert map_form_fields(fields, PROFILE, plan=_plan("li", "never")) == map_form_fields(fields, PROFILE)


@patch("formfill.map_fields.call_llm")
def test_plan_answer_bank_hit_bound_and_miss_takes_todays_path(llm):
    # The measured planner tags most fields answer_bank_question (even Name/Email),
    # so a bank miss must not beat today's path: it falls through, it isn't flagged.
    fields = [{"field_id": "f1", "label_text": "Do you have a notice period?", "input_type": "select",
               "options": ["Yes", "No"], "name": "notice"}]
    hit = map_form_fields(fields, PROFILE, answer_lookup=lambda q: "no",
                          plan=_plan("notice", "answer_bank_question"))
    assert hit == [{"field_id": "f1", "maps_to": "plan:answer_bank", "confidence": 1.0, "value": "No"}]
    llm.assert_not_called()
    llm.return_value = LLM_UNKNOWN
    miss = map_form_fields(fields, PROFILE, answer_lookup=lambda q: None,
                           plan=_plan("notice", "answer_bank_question"))
    llm.assert_called_once()
    assert miss == map_form_fields(fields, PROFILE, answer_lookup=lambda q: None)


@patch("formfill.map_fields.call_llm", return_value=LLM_UNKNOWN)
def test_plan_with_stale_key_is_ignored(llm):
    fields = [{"field_id": "f1", "label_text": "Current location", "input_type": "text", "dom_id": "loc"}]
    stale = {"fields": [{"key": "loc", "fill_from": "city"}, {"key": "gone", "fill_from": "email"}]}
    result = map_form_fields(fields, PROFILE, plan=stale)
    llm.assert_called()
    assert result == map_form_fields(fields, PROFILE)


@patch("formfill.map_fields.call_llm")
def test_plan_cannot_fill_demographic_field(llm):
    fields = [{"field_id": "f1", "label_text": "Gender", "input_type": "select",
               "options": ["Male", "Female", "Decline"], "dom_id": "g"}]
    assert map_form_fields(fields, PROFILE, plan=_plan("g", "email")) == [FLAGGED]
    llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_deterministic_match_beats_plan(llm):
    fields = [{"field_id": "f1", "label_text": "Email", "input_type": "email", "name": "email"}]
    result = map_form_fields(fields, {**PROFILE, "phone": "555"}, plan=_plan("email", "phone"))
    assert result == [{"field_id": "f1", "maps_to": "profile.email", "confidence": 1.0, "value": "jane@example.com"}]
    llm.assert_not_called()


@patch("formfill.map_fields.call_llm", return_value=LLM_UNKNOWN)
def test_plan_skips_radio_and_eligibility_questions(llm):
    radio = [{"field_id": "f1", "label_text": "Country", "input_type": "radio",
              "options": ["United States", "Canada"], "name": "ctry"}]
    question = [{"field_id": "f1", "label_text": "Are you authorized to work in the US?", "input_type": "select",
                 "options": ["Yes", "No", "United States"], "dom_id": "auth"}]
    for fields, key in ((radio, "ctry"), (question, "auth")):
        llm.reset_mock()
        result = map_form_fields(fields, PROFILE, plan=_plan(key, "country_code"))
        assert result == map_form_fields(fields, PROFILE)
        assert not result[0]["maps_to"].startswith("plan:")
        llm.assert_called()


@patch("formfill.map_fields.call_llm")
def test_plan_profile_key_missing_is_flagged(llm):
    fields = [{"field_id": "f1", "label_text": "Contact number", "input_type": "text", "dom_id": "cn"}]
    assert map_form_fields(fields, PROFILE, plan=_plan("cn", "phone")) == [FLAGGED]
    llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_plan_value_not_in_options_is_flagged(llm):
    fields = [{"field_id": "f1", "label_text": "Preferred office", "input_type": "select",
               "options": ["London", "Berlin"], "dom_id": "office"}]
    assert map_form_fields(fields, PROFILE, plan=_plan("office", "city")) == [FLAGGED]
    llm.assert_not_called()
