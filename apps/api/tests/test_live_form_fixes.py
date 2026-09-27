"""Fixes for what docs/LIVE-FORM-TEST.md found on real Greenhouse/Lever/Ashby
forms (2026-09-27). Each test names the live finding it closes.
"""
import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import models
from answer_bank import find_answer, is_demographic_field, normalize_question, save_answer, serve_answer
from formfill.deterministic import match_field_deterministic
from formfill.map_fields import build_profile_summary, map_form_fields
from tests.test_answer_bank import _profile
from tests.test_applicant_basics import _auth, _client
from tests.test_deterministic_fields import PROFILE, _field

FLAGGED = {"maps_to": "unknown", "confidence": 0.0, "value": None}


def _flagged(field_id="f1"):
    return {"field_id": field_id, **FLAGGED}


# ---------- 1. P0 EEO leak (LIVE-FORM-TEST bug #2) ----------

@pytest.mark.parametrize("label", [
    "Are you Hispanic/Latino?", "Race", "Ethnic background", "Latinx", "Sex", "What is your sex?",
    "Pronouns", "Are you transgender?", "Protected veteran", "Do you have a disability?",
    "Are you disabled?", "Sexual orientation", "Gender identity",
])
def test_demographic_labels_are_caught(label):
    assert is_demographic_field(label, None) is True


@pytest.mark.parametrize("label", [
    "Are you 18 or older?",
    "Are you legally authorized to work in the United States?",
    "Will you now or in the future require visa sponsorship?",
    "Sussex office preference",  # question keywords are whole-word only
    "Do you embrace a fast-paced environment?",  # "race" inside "embrace"
    "Are you willing to relocate?",
    "Email", None,
])
def test_non_demographic_labels_are_not_caught(label):
    assert is_demographic_field(label, []) is False


@pytest.mark.parametrize("options", [
    ["Man", "Woman", "Decline to self-identify"],
    ["Man", "Woman"],
    ["White", "Black or African American", "Asian"],
    ["White (Not Hispanic or Latino)", "Asian"],  # starts-with a term, then a space
    ["Yes, I have a disability", "No disability", "I don’t wish to answer"],
    ["Protected veteran", "Decline to self identify"],
])
def test_option_only_eeo_groups_are_caught(options):
    assert is_demographic_field(None, options) is True
    assert is_demographic_field("Select one", options) is True


@pytest.mark.parametrize("options", [
    ["Yes", "No"],
    ["Yes", "No", "Prefer not to say"],
    ["United States", "Canada"],
    ["Grace College", "Horace Mann University"],  # "race" inside a word is not an option match
    # a university list: one distinct term ("asian") and "woman" not at the start
    ["Asian Institute of Technology", "Texas Woman's University", "Aalto University"],
    ["Asian Institute of Technology", "Asian University for Women"],  # terms counted distinct
])
def test_ordinary_option_sets_are_not_caught(options):
    assert is_demographic_field("Please choose", options) is False


def test_hispanic_question_is_refused_on_save(db_session):
    profile = _profile(db_session, "live-hisp-save@example.com")
    with pytest.raises(HTTPException) as exc:
        save_answer(db_session, profile.id, "Are you Hispanic/Latino?", "No")
    assert exc.value.status_code == 400
    assert db_session.query(models.AnswerBank).count() == 0


def test_an_existing_hispanic_row_is_never_served(db_session):
    """The live account already holds this row (stored before the rule)."""
    profile = _profile(db_session, "live-hisp-serve@example.com")
    q = "Are you Hispanic/Latino?"
    db_session.add(models.AnswerBank(
        profile_id=profile.id, question_text=q, question_normalized=normalize_question(q), answer_text="No",
    ))
    db_session.commit()
    assert find_answer(db_session, profile.id, q) is None
    assert serve_answer(db_session, profile.id, q) is None


@patch("formfill.map_fields.call_llm")
def test_the_live_hispanic_field_is_never_mapped_even_by_a_hostile_bank(mock_call_llm):
    fields = [{"field_id": "f1", "label_text": "Are you Hispanic/Latino?", "input_type": "text",
               "dom_id": "hispanic_ethnicity"}]
    result = map_form_fields(fields, PROFILE, answer_lookup=lambda q: "No", ats_type="greenhouse")
    assert result == [_flagged()]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_option_only_eeo_group_is_never_mapped(mock_call_llm):
    asked = []
    fields = [{"field_id": "f1", "label_text": None, "input_type": "radio",
               "options": ["Man", "Woman", "Decline to self-identify"]}]
    result = map_form_fields(fields, PROFILE, answer_lookup=lambda q: asked.append(q) or "Man")
    assert result == [_flagged()]
    assert asked == []
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_per_option_radios_sharing_a_name_are_seen_as_one_eeo_group(mock_call_llm):
    """What today's extension actually sends for Ashby: one descriptor per radio."""
    fields = [
        {"field_id": f"f{i}", "label_text": label, "input_type": "radio", "name": "q_gender"}
        for i, label in enumerate(["Man", "Woman", "Non-Binary", "I prefer not to answer"])
    ]
    result = map_form_fields(fields, PROFILE, answer_lookup=lambda q: "Man")
    assert result == [_flagged(f"f{i}") for i in range(4)]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm", return_value="[]")
def test_age_and_work_auth_questions_still_reach_the_bank(_mock):
    asked = []
    fields = [
        {"field_id": "f1", "label_text": "Are you 18 or older?", "input_type": "text"},
        {"field_id": "f2", "label_text": "Are you legally authorized to work in the US?", "input_type": "text"},
    ]
    map_form_fields(fields, PROFILE, answer_lookup=lambda q: asked.append(q))
    assert asked == ["Are you 18 or older?", "Are you legally authorized to work in the US?"]


# ---------- 2. P1 deterministic false hits (LIVE-FORM-TEST bug #6) ----------

def test_telugu_checkbox_never_gets_the_phone_number():
    field = _field(label_text="Telugu (TEL)", input_type="checkbox",
                   name="cards[a69a985a-eae9-4c14-90fb-b5a4b891523e][field0]")
    assert match_field_deterministic(field, PROFILE) is None
    # the label alone must not read as "phone" either, whatever the input type
    assert match_field_deterministic(_field(label_text="Telugu (TEL)"), PROFILE) is None


def test_visa_sponsorship_question_is_not_a_country_field():
    label = ("Will you now or will you in the future require employment visa sponsorship to work in the "
             "country in which the job you're applying for is located? *")
    assert match_field_deterministic(_field(label_text=label, dom_id="question_8581811008"), PROFILE) is None


@pytest.mark.parametrize("label", ["Are you authorized to work in this country?", "Country of visa sponsorship"])
def test_country_label_about_authorization_is_not_a_country_field(label):
    assert match_field_deterministic(_field(label_text=label), PROFILE) is None


@pytest.mark.parametrize("kwargs, key", [
    ({"label_text": "Country*"}, "country_code"),
    ({"label_text": "Country of residence"}, "country_code"),
    ({"label_text": "Mobile number"}, "phone"),
    ({"label_text": "Telephone"}, "phone"),
    ({"name": "tel"}, "phone"),
    ({"name": "applicant_phone_number"}, "phone"),
    ({"dom_id": "mobilePhone"}, "phone"),
])
def test_real_contact_fields_still_match(kwargs, key):
    result = match_field_deterministic(_field(**kwargs), PROFILE)
    assert result is not None and result["maps_to"] == f"profile.{key}"


@pytest.mark.parametrize("name", ["hotel_preference", "intel_experience", "telugu"])
def test_tel_inside_a_word_is_not_a_phone(name):
    assert match_field_deterministic(_field(name=name), PROFILE) is None


@pytest.mark.parametrize("input_type", ["checkbox", "radio"])
def test_phone_is_never_mapped_to_a_checkbox_or_radio(input_type):
    assert match_field_deterministic(_field(autocomplete="tel", input_type=input_type), PROFILE) is None
    assert match_field_deterministic(_field(name="phone", input_type=input_type), PROFILE, ats_type="lever") is None


def test_free_text_is_never_put_into_a_select_without_an_option_match():
    field = _field(label_text="Country", input_type="select", options=["United States", "Canada"])
    assert match_field_deterministic(field, PROFILE) is None
    field = _field(label_text="Country", input_type="select", options=["IN", "US"])
    assert match_field_deterministic(field, PROFILE)["value"] == "IN"


# ---------- 3. P1 option-bound answers (LIVE-FORM-TEST bug #9) ----------

def _llm_returns(mapping):
    return json.dumps([mapping])


@patch("formfill.map_fields.call_llm")
def test_llm_value_outside_the_options_is_flagged(mock_call_llm):
    """The live bug: "San Francisco" into a Yes/No relocation combobox at 0.8."""
    mock_call_llm.return_value = _llm_returns(
        {"field_id": "f1", "maps_to": "profile.city", "confidence": 0.8, "value": "San Francisco"})
    fields = [{"field_id": "f1", "label_text": "Are you open to relocation?", "input_type": "select",
               "options": ["Yes", "No"]}]
    assert map_form_fields(fields, PROFILE) == [_flagged()]


@pytest.mark.parametrize("value, options, expected", [
    ("yes", ["Yes", "No"], "Yes"),
    ("  NO ", ["Yes", "No"], "No"),
    ("Yes", ["Yes, I will relocate", "No, I will not"], "Yes, I will relocate"),
    ("true", ["Yes", "No"], "Yes"),
])
@patch("formfill.map_fields.call_llm")
def test_llm_value_is_normalised_to_the_option_text(mock_call_llm, value, options, expected):
    mock_call_llm.return_value = _llm_returns(
        {"field_id": "f1", "maps_to": "literal:yes", "confidence": 0.9, "value": value})
    fields = [{"field_id": "f1", "label_text": "Open to relocation?", "input_type": "radio", "options": options}]
    assert map_form_fields(fields, PROFILE)[0]["value"] == expected


@patch("formfill.map_fields.call_llm")
def test_bank_answer_must_match_an_option(mock_call_llm):
    mock_call_llm.return_value = "[]"
    fields = [{"field_id": "f1", "label_text": "Open to relocation?", "input_type": "select",
               "options": ["Yes", "No"]}]
    assert map_form_fields(fields, PROFILE, answer_lookup=lambda q: "no")[0] == {
        "field_id": "f1", "maps_to": "answer_bank", "confidence": 1.0, "value": "No"}
    assert map_form_fields(fields, PROFILE, answer_lookup=lambda q: "Maybe later") == [_flagged()]


@patch("formfill.map_fields.call_llm", return_value="[]")
def test_prompt_lists_the_options_and_demands_one_of_them(mock_call_llm):
    fields = [{"field_id": "f1", "label_text": "Open to relocation?", "input_type": "select",
               "options": ["Yes", "No"]}]
    map_form_fields(fields, PROFILE)
    system_prompt, user_prompt = mock_call_llm.call_args.args
    assert '"options": ["Yes", "No"]' in user_prompt
    assert "exactly one of" in system_prompt


# ---------- 4. P2 latency / payload (LIVE-FORM-TEST #10, #15) ----------

@patch("formfill.map_fields.call_llm", return_value="[]")
def test_captcha_hidden_and_contextless_fields_never_reach_the_model(mock_call_llm):
    fields = [
        {"field_id": "cap", "label_text": None, "input_type": "textarea", "name": "g-recaptcha-response"},
        {"field_id": "hid", "label_text": "token", "input_type": "hidden"},
        {"field_id": "iti", "label_text": "Search", "input_type": "search", "dom_id": "iti-0__search-input"},
        {"field_id": "bare", "label_text": None, "input_type": "text"},
    ]
    result = map_form_fields(fields, PROFILE)
    assert result == [_flagged(i) for i in ("cap", "hid", "iti", "bare")]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm", return_value='[{"field_id": "w", "maps_to": "literal:x", "confidence": 0.9, "value": "x"}]')
def test_a_lone_option_checkbox_is_never_prompted_or_filled(mock_call_llm):
    """Ashby's "White" / Lever's "Telugu (TEL)": the label is an option, not a question."""
    fields = [{"field_id": "w", "label_text": "White", "input_type": "checkbox", "name": "White"}]
    assert map_form_fields(fields, PROFILE) == [_flagged("w")]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm", return_value="[]")
def test_unresolved_fields_go_to_the_model_in_one_call_with_options_truncated(mock_call_llm):
    universities = [f"University number {i}" for i in range(3302)]  # Lever's live select
    fields = [
        {"field_id": "uni", "label_text": "School", "input_type": "select", "options": universities},
        {"field_id": "q1", "label_text": "When could you start?", "input_type": "text"},
        {"field_id": "q2", "label_text": "Deadlines we should know about?", "input_type": "text"},
        {"field_id": "em", "label_text": "Email", "input_type": "email"},  # deterministic, not sent
    ]
    map_form_fields(fields, PROFILE)
    assert mock_call_llm.call_count == 1
    user_prompt = mock_call_llm.call_args.args[1]
    assert "University number 49" in user_prompt and "University number 50" not in user_prompt
    assert '"em"' not in user_prompt
    # Before: ~150 KB for this one select (the live Lever payload was 122 KB).
    assert len(user_prompt) < 5_000


# ---------- 5. P2 empty resume (LIVE-FORM-TEST #12) ----------

def test_resume_docx_with_no_facts_is_409_not_an_empty_document():
    client = _client()
    headers = _auth(client, "live-empty-resume@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    resp = client.get(f"/profiles/{profile['id']}/resume.docx", headers=headers)
    assert resp.status_code == 409
    assert "no resume facts" in resp.json()["detail"].lower()


# ---------- 6. P2 first/last name (LIVE-FORM-TEST #11) ----------

def test_basics_round_trip_given_and_family_name():
    client = _client()
    headers = _auth(client, "live-names@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    payload = {"full_name": "Priya Raman", "given_name": "Priya", "family_name": "Raman"}
    assert client.put(f"/profiles/{profile['id']}/basics", headers=headers, json=payload).status_code == 200
    got = client.get(f"/profiles/{profile['id']}/basics", headers=headers).json()
    assert (got["given_name"], got["family_name"]) == ("Priya", "Raman")


NAMED = {**PROFILE, "given_name": "Bedaant", "family_name": "Srivastav"}


@pytest.mark.parametrize("kwargs, key", [
    ({"autocomplete": "given-name"}, "given_name"),
    ({"autocomplete": "family-name"}, "family_name"),
    ({"name": "first_name"}, "given_name"),
    ({"dom_id": "lastname"}, "family_name"),
    ({"name": "firstName"}, "given_name"),
    ({"label_text": "First Name"}, "given_name"),
    ({"label_text": "Last name*"}, "family_name"),
])
def test_given_and_family_name_map_when_the_user_gave_them(kwargs, key):
    result = match_field_deterministic(_field(**kwargs), NAMED)
    assert result["maps_to"] == f"profile.{key}"
    assert result["value"] == NAMED[key]


def test_greenhouse_first_last_name_fill_from_the_schema():
    for dom_id, key in (("first_name", "given_name"), ("last_name", "family_name")):
        field = _field(label_text="What should we call you?", dom_id=dom_id)
        assert match_field_deterministic(field, NAMED, ats_type="greenhouse")["value"] == NAMED[key]


def test_first_name_without_a_given_name_is_still_never_split():
    assert match_field_deterministic(_field(dom_id="first_name", label_text="First Name"), PROFILE) is None


def test_profile_summary_carries_given_and_family_name():
    class P:
        full_name, given_name, family_name = "Priya Raman", "Priya", "Raman"
    summary = build_profile_summary(P(), "p@example.com")
    assert summary["given_name"] == "Priya" and summary["family_name"] == "Raman"


def test_a_recognised_first_name_field_never_falls_through_to_the_llm():
    """Found by the browser-use harness on the real Greenhouse form: First Name
    and Last Name (autocomplete given-name/family-name) both got the FULL name.
    The rule recognised them, the profile had no given/family name, so they fell
    through to the model, which guessed full_name. Recognised-but-missing must be
    flagged, not guessed."""
    fields = [
        {"field_id": "f", "label_text": "First Name", "input_type": "text", "options": [], "required": True,
         "autocomplete": "given-name", "name": None, "dom_id": "first_name"},
        {"field_id": "l", "label_text": "Last Name", "input_type": "text", "options": [], "required": True,
         "autocomplete": "family-name", "name": None, "dom_id": "last_name"},
    ]
    summary = {"full_name": "Morgan Ellery", "email": "morgan@example.com"}
    with patch("formfill.map_fields.call_llm") as llm:
        llm.return_value = json.dumps([
            {"field_id": "f", "maps_to": "profile.full_name", "confidence": 0.9, "value": "Morgan Ellery"},
            {"field_id": "l", "maps_to": "profile.full_name", "confidence": 0.9, "value": "Morgan Ellery"},
        ])
        result = {m["field_id"]: m for m in map_form_fields(fields, summary)}

    llm.assert_not_called()
    assert result["f"]["value"] is None and result["l"]["value"] is None


# ---------- legal consent is the user's own act (found by the combobox harness run) ----------

from answer_bank import is_consent_field  # noqa: E402


@pytest.mark.parametrize("label,options", [
    ("Agreement to Arbitrate", ["I understand and agree to the terms of the arbitration agreement"]),
    ("Please read the arbitration agreement below", ["Yes"]),
    ("I certify that the information I have provided is true and complete", []),
    ("Do you consent to our privacy policy?", ["Yes", "No"]),
    ("Electronic signature", []),
    ("Acknowledgement", ["I have read and accept the Terms and Conditions"]),
])
def test_legal_consent_questions_are_recognised(label, options):
    assert is_consent_field(label, options)


@pytest.mark.parametrize("label,options", [
    ("Are you legally authorized to work in the United States?", ["Yes", "No"]),
    ("Will you require visa sponsorship?", ["Yes", "No"]),
    ("Are you willing to relocate?", ["Yes", "No"]),
    ("How did you hear about us?", []),
])
def test_ordinary_questions_are_not_consent(label, options):
    assert not is_consent_field(label, options)


def test_the_llm_never_accepts_legal_terms_for_the_user():
    """Live: the model returned the arbitration agreement's single option with
    high confidence and the extension clicked it. Agreeing to legal terms is the
    user's act — never automated, never from the answer bank."""
    fields = [{"field_id": "arb", "label_text": "Agreement to Arbitrate", "input_type": "select",
               "options": ["I understand and agree to the terms of the arbitration agreement"],
               "required": True, "autocomplete": None, "name": None, "dom_id": "question_arb"}]
    with patch("formfill.map_fields.call_llm") as llm:
        llm.return_value = json.dumps([{"field_id": "arb", "maps_to": "profile.consent", "confidence": 0.95,
                                        "value": "I understand and agree to the terms of the arbitration agreement"}])
        result = map_form_fields(fields, {"full_name": "Morgan Ellery"},
                                 answer_lookup=lambda q: "I understand and agree to the terms of the arbitration agreement")
    llm.assert_not_called()
    assert result[0]["value"] is None


def test_a_consent_answer_is_never_saved_to_the_bank(db_session):
    profile = _profile(db_session, "live-consent-save@example.com")
    with pytest.raises(HTTPException):
        save_answer(db_session, profile.id, "Agreement to Arbitrate", "I agree")
    assert db_session.query(models.AnswerBank).count() == 0


def test_country_code_binds_to_a_country_name_option():
    """Live (combobox harness run): Greenhouse's Country options read
    "United States +1"; the profile holds the ISO code "US", so it stayed empty."""
    field = {"field_id": "c", "label_text": "Country", "input_type": "select", "required": True,
             "options": ["Afghanistan +93", "India +91", "United Kingdom +44", "United States +1"],
             "autocomplete": None, "name": None, "dom_id": "country"}
    mapping = match_field_deterministic(field, {"country_code": "US"})
    assert mapping["value"] == "United States +1"
    assert match_field_deterministic(field, {"country_code": "IN"})["value"] == "India +91"
    # No guessing: a code with no matching option stays unfilled.
    assert match_field_deterministic(field, {"country_code": "DE"}) is None
