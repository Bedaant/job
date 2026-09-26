"""Deterministic field matching (PRD: "Known ATS... fills them
deterministically"; SPEC.md §3.7). Zero LLM calls — an ordered rule table
over each field's own attributes, checked before the bounded LLM path in
map_fields.py::map_form_fields, not instead of it.

Deliberately does NOT split full_name into given/family parts: no
structured name-parts field exists on Profile, and guessing a split is
exactly the invention the null-over-guess rule already forbids for identity
data (see the applicant-basics validators). Those fields fall through to
the LLM path unchanged.
"""
from formfill.deterministic import match_field_deterministic


PROFILE = {
    "email": "bedaant@example.com",
    "full_name": "Bedaant Srivastav",
    "phone": "+91 98765 43210",
    "city": "Bengaluru",
    "region": "Karnataka",
    "postal_code": "560001",
    "country_code": "IN",
    "street_address": "123 MG Road",
    "website_url": "https://bedaant.dev",
    "network_profiles": [
        {"network": "LinkedIn", "username": "bedaant", "url": "https://linkedin.com/in/bedaant"},
        {"network": "GitHub", "username": "bedaant", "url": "https://github.com/bedaant"},
    ],
}


def _field(**kwargs):
    base = {"field_id": "f1", "label_text": None, "input_type": "text", "autocomplete": None, "name": None, "dom_id": None}
    return {**base, **kwargs}


# ---------- autocomplete attribute (web standard) wins first ----------

def test_autocomplete_email_resolves_to_profile_email():
    result = match_field_deterministic(_field(autocomplete="email"), PROFILE)
    assert result == {"field_id": "f1", "maps_to": "profile.email", "confidence": 1.0, "value": "bedaant@example.com"}


def test_autocomplete_tel_resolves_to_phone():
    result = match_field_deterministic(_field(autocomplete="tel"), PROFILE)
    assert result["maps_to"] == "profile.phone"
    assert result["value"] == "+91 98765 43210"


def test_autocomplete_name_resolves_to_full_name():
    result = match_field_deterministic(_field(autocomplete="name"), PROFILE)
    assert result["maps_to"] == "profile.full_name"


def test_autocomplete_address_level2_resolves_to_city():
    result = match_field_deterministic(_field(autocomplete="address-level2"), PROFILE)
    assert result["value"] == "Bengaluru"


def test_autocomplete_postal_code_resolves_to_postal_code():
    result = match_field_deterministic(_field(autocomplete="postal-code"), PROFILE)
    assert result["value"] == "560001"


# ---------- name/id/label pattern fallback ----------

def test_name_attribute_email_pattern_matches():
    result = match_field_deterministic(_field(name="applicant_email"), PROFILE)
    assert result["maps_to"] == "profile.email"


def test_dom_id_phone_pattern_matches():
    result = match_field_deterministic(_field(dom_id="phoneNumber"), PROFILE)
    assert result["maps_to"] == "profile.phone"


def test_label_text_full_name_pattern_matches():
    result = match_field_deterministic(_field(label_text="Full Name"), PROFILE)
    assert result["maps_to"] == "profile.full_name"


def test_label_website_pattern_matches():
    result = match_field_deterministic(_field(label_text="Portfolio / personal website"), PROFILE)
    assert result["maps_to"] == "profile.website_url"


# ---------- never splits full_name into first/last ----------

def test_given_name_field_is_not_matched_at_all():
    """No structured given/family name exists on Profile — a field asking
    specifically for a first/given name must fall through to the LLM path,
    not get a guessed split of full_name."""
    result = match_field_deterministic(_field(autocomplete="given-name"), PROFILE)
    assert result is None


def test_family_name_field_is_not_matched_at_all():
    result = match_field_deterministic(_field(autocomplete="family-name"), PROFILE)
    assert result is None


# ---------- network profiles ----------

def test_linkedin_field_resolves_to_linkedin_url():
    result = match_field_deterministic(_field(label_text="LinkedIn profile URL"), PROFILE)
    assert result["maps_to"] == "network_profile:linkedin"
    assert result["value"] == "https://linkedin.com/in/bedaant"


def test_github_field_resolves_to_github_url():
    result = match_field_deterministic(_field(dom_id="githubLink"), PROFILE)
    assert result["value"] == "https://github.com/bedaant"


def test_network_field_with_no_matching_profile_falls_through():
    """The label clearly asks for GitLab; we don't have one — flag, don't guess."""
    result = match_field_deterministic(_field(label_text="GitLab profile"), PROFILE)
    assert result is None


# ---------- structural match but no data ----------

def test_matched_rule_with_missing_profile_value_falls_through():
    sparse_profile = {"email": "a@b.com"}
    result = match_field_deterministic(_field(autocomplete="tel"), sparse_profile)
    assert result is None


# ---------- nothing matches ----------

def test_unrecognized_field_falls_through_to_none():
    result = match_field_deterministic(_field(label_text="Why do you want this job?"), PROFILE)
    assert result is None
