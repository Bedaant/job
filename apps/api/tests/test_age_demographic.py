"""latest+48: age is demographic (never filled, never stored); legal-age eligibility is not.

Shared spec with apps/extension/src/content/fieldDecision.mjs (fieldDecision.test.mjs
carries the same cases).
"""
import pytest
from fastapi import HTTPException

import models
from answer_bank import is_demographic_field, save_answer
from tests.test_answer_bank import _profile


@pytest.mark.parametrize("label", [
    "Age",
    "Age:",
    "Age (optional)",
    "What is your age?",
    "How old are you?",
    "Age range",
    "Please select your age group",
    "Which age bracket do you fall into?",
    "Date of Birth",
    "Date of birth (MM/DD/YYYY)",
    "Birth date",
    "Birthdate",
    "Year of birth",
    "Birth year",
    "DOB",
])
def test_age_questions_are_demographic(label):
    assert is_demographic_field(label) is True


@pytest.mark.parametrize("label", [
    "Are you 18 years of age or older?",
    "Are you at least 18?",
    "Are you over the age of 21?",
    "Are you of legal working age?",
    "Are you legally authorized to work in the United States?",
    "Will you now or in the future require visa sponsorship?",
    "Are you willing to relocate?",
    "Page 2 of the application",
    "Stage of your career",
    "Manager name",
    "Job title",
    "How many years of experience do you have with Python?",
])
def test_eligibility_and_ordinary_questions_are_not_demographic(label):
    assert is_demographic_field(label, ["Yes", "No"]) is False


@pytest.mark.parametrize("options", [
    ["Under 18", "18-24", "25-34", "35-44", "45-54", "55-64", "65 or older"],
    ["18 - 24", "25 – 34"],  # en dash, spaces
    ["40 or over", "Under 40"],
    ["18-24", "Prefer not to say"],  # decline + one bracket
    ["25 to 34 years", "35 to 44 years"],
])
def test_age_bracket_option_groups_are_demographic(options):
    assert is_demographic_field("Please select", options) is True


@pytest.mark.parametrize("options", [
    ["Yes", "No"],
    ["18 or older", "Under 18"],  # a legal-age check, not a bracket set
    ["21 or over", "Under 21"],
    ["0-2", "3-5", "6-10", "10+"],  # years of experience
    ["Less than 10", "10-20", "20+"],
    ["1-10", "11-50", "51-200", "201-500"],  # company size
    ["$50,000-$75,000", "$75,000-$100,000"],
])
def test_non_age_option_groups_are_not_demographic(options):
    assert is_demographic_field("Please select", options) is False


def test_age_answer_is_refused_on_save(db_session):
    profile = _profile(db_session, "age-save@example.com")
    with pytest.raises(HTTPException) as exc:
        save_answer(db_session, profile.id, "Date of birth", "1990-01-01")
    assert exc.value.status_code == 400
    assert db_session.query(models.AnswerBank).count() == 0


def test_legal_age_answer_is_still_saved(db_session):
    profile = _profile(db_session, "age-legal@example.com")
    save_answer(db_session, profile.id, "Are you 18 years of age or older?", "Yes")
    assert db_session.query(models.AnswerBank).count() == 1
