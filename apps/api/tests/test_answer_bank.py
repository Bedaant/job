"""The answer bank's function layer (ADR-015 Phase 2).

The bank exists so that an interruption shrinks over time: the user answers
"what is your notice period?" once, and every later employer asking the same
thing is answered from what they typed. The tests that matter most here are
the ones proving it *refuses* — a wrong answer on a real application is worse
than asking the user again, and a demographic answer is never acceptable at
all.
"""
import pytest
from fastapi import HTTPException

import models
from answer_bank import (
    DEMOGRAPHIC_LABEL_KEYWORDS,
    find_answer,
    is_demographic_label,
    normalize_question,
    save_answer,
    serve_answer,
)


def _profile(db, email):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    db.add(profile)
    db.commit()
    return profile


# ---------- normalization ----------

def test_normalize_lowercases_strips_punctuation_and_collapses_whitespace():
    assert normalize_question("  What   is your NOTICE period?? ") == "what is your notice period"


def test_normalize_is_stable_across_the_punctuation_a_form_actually_varies():
    variants = [
        "Why do you want to work here?",
        "why do you want to work here",
        "Why do you want to work here!",
        "Why  do you want to work here ...",
    ]
    assert len({normalize_question(v) for v in variants}) == 1


def test_normalize_keeps_the_characters_that_are_the_whole_answer():
    """`c++` and `c#` differ only in punctuation. Stripping it would collapse
    them into the same key and serve a C# answer to a C++ question."""
    assert normalize_question("Years of experience with C++?") != normalize_question(
        "Years of experience with C#?"
    )


def test_normalize_handles_none_and_empty():
    assert normalize_question(None) == ""
    assert normalize_question("   ") == ""


# ---------- exact + fuzzy hits ----------

def test_find_answer_exact_normalized_match(db_session):
    profile = _profile(db_session, "bank-exact@example.com")
    save_answer(db_session, profile.id, "What is your notice period?", "30 days")

    hit = find_answer(db_session, profile.id, "  what is your NOTICE period?  ")
    assert hit is not None
    assert hit.answer_text == "30 days"


def test_find_answer_fuzzy_match_on_a_reworded_same_question(db_session):
    """The real payoff: employer B phrases it differently, same question."""
    profile = _profile(db_session, "bank-fuzzy@example.com")
    save_answer(db_session, profile.id, "What is your notice period?", "30 days")

    hit = find_answer(db_session, profile.id, "Notice period")
    assert hit is not None
    assert hit.answer_text == "30 days"


def test_find_answer_tolerates_a_plural(db_session):
    profile = _profile(db_session, "bank-plural@example.com")
    save_answer(db_session, profile.id, "What is your notice period?", "30 days")
    assert find_answer(db_session, profile.id, "What are your notice periods?") is not None


def test_find_answer_returns_none_when_the_bank_is_empty(db_session):
    profile = _profile(db_session, "bank-empty@example.com")
    assert find_answer(db_session, profile.id, "What is your notice period?") is None


# ---------- the non-match rail: lexically close, semantically opposite ----------

def test_motivation_question_does_not_match_departure_question(db_session):
    """"Why do you want to work here" and "why did you leave your last job"
    share their opening words and nothing else. Serving the first as an answer
    to the second files a real application with a nonsense answer."""
    profile = _profile(db_session, "bank-nonmatch1@example.com")
    save_answer(db_session, profile.id, "Why do you want to work here?", "Your mission matches mine.")

    assert find_answer(db_session, profile.id, "Why did you leave your last job?") is None


def test_years_of_experience_does_not_match_across_a_different_technology(db_session):
    """token_set_ratio scores this pair 90.6 — high enough to pass any
    single-scorer threshold that still matches real paraphrases. The
    distinguishing noun has to be checked separately."""
    profile = _profile(db_session, "bank-nonmatch2@example.com")
    save_answer(db_session, profile.id, "Years of experience with Python?", "6")

    assert find_answer(db_session, profile.id, "Years of experience with Java?") is None


def test_a_near_miss_technology_name_does_not_match(db_session):
    """Python/PyTorch score 92.1 on every whole-string scorer rapidfuzz has."""
    profile = _profile(db_session, "bank-nonmatch3@example.com")
    save_answer(db_session, profile.id, "Years of experience with Python?", "6")
    assert find_answer(db_session, profile.id, "Years of experience with PyTorch?") is None


def test_cpp_answer_is_not_served_to_a_csharp_question(db_session):
    """fuzz.ratio scores this pair 94.5."""
    profile = _profile(db_session, "bank-nonmatch4@example.com")
    save_answer(db_session, profile.id, "Years of experience with C++?", "6")
    assert find_answer(db_session, profile.id, "Years of experience with C#?") is None


def test_a_negated_question_does_not_match_its_positive_form(db_session):
    """"do you require sponsorship" vs "do you NOT require sponsorship" score
    100 on token_set_ratio. A yes served to the wrong one is a false legal
    declaration on an application."""
    profile = _profile(db_session, "bank-nonmatch5@example.com")
    save_answer(db_session, profile.id, "Do you require visa sponsorship?", "No")
    assert find_answer(db_session, profile.id, "Do you not require visa sponsorship?") is None


def test_an_all_stopword_question_never_fuzzy_matches_anything(db_session):
    """A question with no content words carries no signal to match on, so it
    must fall back to exact-only rather than matching every stored entry."""
    profile = _profile(db_session, "bank-stopwords@example.com")
    save_answer(db_session, profile.id, "Why do you?", "Because.")
    assert find_answer(db_session, profile.id, "What are you?") is None
    assert find_answer(db_session, profile.id, "Why do you?") is not None


# ---------- rail 1: demographic questions are never served ----------

def test_demographic_keywords_do_not_contain_essay_keywords():
    joined = " ".join(DEMOGRAPHIC_LABEL_KEYWORDS)
    assert "gender" in joined
    assert "race" in joined
    assert "why do you want to work" not in joined
    assert "why are you interested" not in joined


def test_is_demographic_label_matches_case_insensitively():
    assert is_demographic_label("What is your Gender?") is True
    assert is_demographic_label("Veteran Status") is True
    assert is_demographic_label("Email address") is False
    assert is_demographic_label(None) is False
    # an essay question is NOT demographic — it is fillable once the user has
    # written the answer, which is the entire point of this feature
    assert is_demographic_label("Why do you want to work here?") is False


def test_save_answer_refuses_to_store_a_demographic_question(db_session):
    profile = _profile(db_session, "bank-demo-save@example.com")
    with pytest.raises(HTTPException) as exc:
        save_answer(db_session, profile.id, "What is your gender?", "Male")
    assert exc.value.status_code == 400
    assert db_session.query(models.AnswerBank).count() == 0


def test_a_demographic_answer_is_never_served_even_if_a_row_somehow_exists(db_session):
    """Defense in depth. save_answer already refuses, so this row is written
    straight to the ORM to simulate a row that arrived some other way — a
    hand-written INSERT, a restored backup, a future code path. find_answer
    must still refuse it."""
    profile = _profile(db_session, "bank-demo-serve@example.com")
    db_session.add(
        models.AnswerBank(
            profile_id=profile.id,
            question_text="What is your gender?",
            question_normalized=normalize_question("What is your gender?"),
            answer_text="Male",
        )
    )
    db_session.commit()
    assert db_session.query(models.AnswerBank).count() == 1  # the row really is there

    assert find_answer(db_session, profile.id, "What is your gender?") is None
    assert find_answer(db_session, profile.id, "Gender") is None
    assert serve_answer(db_session, profile.id, "What is your gender?") is None


@pytest.mark.parametrize(
    "question",
    [
        "What is your race?",
        "Please select your ethnicity",
        "Gender identity",
        "Are you a protected veteran status?",
        "Disability status",
        "Sexual orientation",
    ],
)
def test_no_demographic_phrasing_is_ever_served(db_session, question):
    profile = _profile(db_session, f"bank-demo-{abs(hash(question))}@example.com")
    db_session.add(
        models.AnswerBank(
            profile_id=profile.id,
            question_text=question,
            question_normalized=normalize_question(question),
            answer_text="something",
        )
    )
    db_session.commit()
    assert find_answer(db_session, profile.id, question) is None


# ---------- rail 2: user-written text only, no LLM anywhere ----------

def test_no_llm_call_exists_anywhere_in_the_answer_bank_import_graph():
    """The bank may only ever contain what the user typed (ADR-006/ADR-009).
    Structural proof rather than a promise: if `call_llm` were reachable from
    this module at all, someone could generate an entry."""
    import subprocess
    import sys
    from pathlib import Path

    api_dir = Path(__file__).resolve().parent.parent
    # A fresh interpreter, because this test session has already imported
    # half the app — `"tailoring.engine" in sys.modules` would be true here
    # no matter what answer_bank does.
    probe = (
        "import sys, answer_bank;"
        "bad=[m for m in sys.modules if m=='tailoring.engine' or m.startswith('anthropic')];"
        "print(','.join(sorted(bad)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], cwd=api_dir, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "", (
        "importing answer_bank pulled in an LLM module "
        f"({out.stdout.strip()}) — a generated answer is not a user answer."
    )


def test_save_answer_is_the_only_write_path_in_the_module():
    """Any other function that constructs an AnswerBank row is a second door
    into the bank that bypasses save_answer's demographic refusal."""
    import inspect

    import answer_bank

    source_by_function = {
        name: inspect.getsource(fn)
        for name, fn in vars(answer_bank).items()
        if inspect.isfunction(fn) and fn.__module__ == "answer_bank"
    }
    writers = [name for name, src in source_by_function.items() if "AnswerBank(" in src]
    assert writers == ["save_answer"], f"unexpected write path(s): {writers}"


# ---------- upsert, usage counters ----------

def test_save_answer_upserts_rather_than_duplicating(db_session):
    profile = _profile(db_session, "bank-upsert@example.com")
    save_answer(db_session, profile.id, "What is your notice period?", "30 days")
    save_answer(db_session, profile.id, "what is your notice period??", "60 days")

    rows = db_session.query(models.AnswerBank).filter_by(profile_id=profile.id).all()
    assert len(rows) == 1
    assert rows[0].answer_text == "60 days"
    # the verbatim text is refreshed to how it was most recently asked
    assert rows[0].question_text == "what is your notice period??"


def test_serve_answer_increments_times_used_and_stamps_last_used_at(db_session):
    profile = _profile(db_session, "bank-used@example.com")
    row = save_answer(db_session, profile.id, "What is your notice period?", "30 days")
    assert row.times_used == 0
    assert row.last_used_at is None

    assert serve_answer(db_session, profile.id, "Notice period") == "30 days"
    db_session.refresh(row)
    assert row.times_used == 1
    assert row.last_used_at is not None

    serve_answer(db_session, profile.id, "What is your notice period?")
    db_session.refresh(row)
    assert row.times_used == 2


def test_find_answer_does_not_increment_on_its_own(db_session):
    """find_answer is a read. Only an answer actually served counts."""
    profile = _profile(db_session, "bank-noinc@example.com")
    row = save_answer(db_session, profile.id, "What is your notice period?", "30 days")
    find_answer(db_session, profile.id, "Notice period")
    db_session.refresh(row)
    assert row.times_used == 0


def test_serve_answer_returns_none_on_a_miss_and_counts_nothing(db_session):
    profile = _profile(db_session, "bank-miss@example.com")
    row = save_answer(db_session, profile.id, "Years of experience with Python?", "6")
    assert serve_answer(db_session, profile.id, "Years of experience with Java?") is None
    db_session.refresh(row)
    assert row.times_used == 0


# ---------- tenancy ----------

def test_one_profiles_answer_is_never_visible_to_another(db_session):
    mine = _profile(db_session, "bank-mine@example.com")
    theirs = _profile(db_session, "bank-theirs@example.com")
    save_answer(db_session, mine.id, "What is your notice period?", "30 days")

    assert find_answer(db_session, theirs.id, "What is your notice period?") is None
    assert find_answer(db_session, mine.id, "What is your notice period?") is not None


def test_the_same_question_can_be_stored_once_per_profile(db_session):
    mine = _profile(db_session, "bank-same-a@example.com")
    theirs = _profile(db_session, "bank-same-b@example.com")
    save_answer(db_session, mine.id, "What is your notice period?", "30 days")
    save_answer(db_session, theirs.id, "What is your notice period?", "immediate")

    assert db_session.query(models.AnswerBank).count() == 2
    assert find_answer(db_session, mine.id, "Notice period").answer_text == "30 days"
    assert find_answer(db_session, theirs.id, "Notice period").answer_text == "immediate"
