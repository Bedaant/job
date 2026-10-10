"""Deterministic cleanup of extracted basics, found in the user-zero run (2026-10-10).

The resume header said "BEDAANT SRIVASTAV", the extractor copied it exactly (as its prompt
demands), and the emailed application went out as "BEDAANT SRIVASTAV - Resume.docx". It also
stored network profiles named "LinkedIn" / "Portfolio" with no URL at all.

Only an ALL-CAPS name is recased: that casing carries no information, so nothing is lost.
Any mixed-case name ("McDonald", "DeSouza") is left exactly as written. User-entered basics
(PUT /basics) are never touched — this runs on extraction output only.
"""
from unittest.mock import MagicMock, patch

from parsing.llm_extract import extract_basics, tidy_basics
from schemas import ApplicantBasics


def test_an_all_caps_name_is_recased():
    b = tidy_basics(ApplicantBasics(full_name="BEDAANT SRIVASTAV", given_name="BEDAANT",
                                    family_name="SRIVASTAV"))
    assert (b.full_name, b.given_name, b.family_name) == ("Bedaant Srivastav", "Bedaant", "Srivastav")


def test_a_mixed_case_name_is_left_exactly_as_written():
    assert tidy_basics(ApplicantBasics(full_name="Ana McDonald-DeSouza")).full_name == "Ana McDonald-DeSouza"


def test_an_apostrophe_name_recases_sensibly():
    assert tidy_basics(ApplicantBasics(full_name="SEAN O'BRIEN")).full_name == "Sean O'Brien"


def test_a_network_profile_with_no_url_is_dropped():
    b = tidy_basics(ApplicantBasics(network_profiles=[
        {"network": "LinkedIn", "username": None, "url": None},
        {"network": "GitHub", "username": "bedaant", "url": "https://github.com/bedaant"},
    ]))
    assert [p.network for p in b.network_profiles] == ["GitHub"]


def test_no_name_stays_none():
    assert tidy_basics(ApplicantBasics()).full_name is None


def test_extract_basics_applies_the_tidy():
    client = MagicMock()
    client.messages.create.return_value = ApplicantBasics(full_name="BEDAANT SRIVASTAV")
    with patch("parsing.llm_extract._get_instructor_client", return_value=client), \
         patch("parsing.llm_extract._get_nvidia_instructor_client", return_value=client):
        assert extract_basics("BEDAANT SRIVASTAV\nKolkata").full_name == "Bedaant Srivastav"
