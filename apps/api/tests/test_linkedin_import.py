"""LinkedIn data-export ZIP -> unconfirmed fact drafts (NEXT-WORK-PLAN §5.1).

All data here is fake and built in the test. The export's column names are from memory of
LinkedIn's archive format, not from a real export; the parser matches files by partial,
case-insensitive name and tolerates missing files and extra columns for that reason.
"""
import io
import os
import tempfile
import zipfile
from unittest.mock import patch

import pytest

import models
from parsing.linkedin_export import ExportRejected, read_linkedin_export
from tests.test_resume_upload import _create_profile, _signup_and_login, client  # noqa: F401

PROFILE_CSV = "First Name,Last Name,Headline,Summary,Extra Column\nAsha,Kulkarni,Backend dev,Hi,x\n"
POSITIONS_CSV = (
    "Company Name,Title,Description,Location,Started On,Finished On,Unknown\n"
    'Acme Labs,Software Engineer,"Built the billing service in Go\nCut p99 latency to 180ms",'
    "Pune,Jan 2021,,z\n"
)
SKILLS_CSV = "Name\nPython\nPostgreSQL\n"


def _zip(entries: dict[str, bytes | str], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _export(**extra) -> bytes:
    return _zip({
        "Basic_LinkedInDataExport_10-12-2026/Profile.csv": "\ufeff" + PROFILE_CSV,
        "Basic_LinkedInDataExport_10-12-2026/POSITIONS.csv": POSITIONS_CSV,
        "Basic_LinkedInDataExport_10-12-2026/Skills.csv": SKILLS_CSV,
        "Basic_LinkedInDataExport_10-12-2026/Connections.csv": "Notes:\nFirst Name\n",
        **extra,
    })


# ---------- the parser ----------

def test_export_becomes_fact_drafts_and_a_name():
    facts, basics = read_linkedin_export(_export())
    achievements = [f["achievement"] for f in facts]
    assert "Software Engineer at Acme Labs (Jan 2021 to present)" in achievements
    assert "Built the billing service in Go" in achievements
    assert "Cut p99 latency to 180ms" in achievements
    assert {"Python", "PostgreSQL"} <= set(achievements)
    assert all(f["category"] in ("experience", "skill") for f in facts)
    assert basics.full_name == "Asha Kulkarni"


def test_missing_files_are_tolerated():
    facts, basics = read_linkedin_export(_zip({"export/Skills.csv": SKILLS_CSV}))
    assert [f["achievement"] for f in facts] == ["Python", "PostgreSQL"]
    assert basics is None


def test_an_export_with_nothing_usable_is_rejected():
    with pytest.raises(ExportRejected):
        read_linkedin_export(_zip({"export/Connections.csv": "First Name\nX\n"}))


@pytest.mark.parametrize("name", ["../Skills.csv", "/etc/Skills.csv", "a/../../Skills.csv", "C:\\x\\Skills.csv"])
def test_path_traversal_is_rejected(name):
    with pytest.raises(ExportRejected):
        read_linkedin_export(_zip({name: SKILLS_CSV}))


def test_zip_bomb_is_rejected():
    # 50 MB of zeros compresses to ~50 KB: small upload, huge decompressed size.
    bomb = _zip({"export/Skills.csv": b"Name\n" + b"0" * (50 * 1024 * 1024)})
    assert len(bomb) < 1024 * 1024
    with pytest.raises(ExportRejected):
        read_linkedin_export(bomb)


def test_too_many_entries_is_rejected():
    with pytest.raises(ExportRejected):
        read_linkedin_export(_zip({f"export/f{i}.txt": "" for i in range(3000)}))


def test_not_a_zip_is_rejected():
    with pytest.raises(ExportRejected):
        read_linkedin_export(b"not a zip at all")


# ---------- the endpoint ----------

def test_zip_upload_returns_unconfirmed_drafts_and_keeps_no_raw_file(client, tmp_path, monkeypatch):  # noqa: F811
    test_client, SessionLocal = client
    token = _signup_and_login(test_client, "li-zip@example.com")
    profile_id = _create_profile(SessionLocal, "li-zip@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Over Starlette's 1 MB spool threshold, so the upload really is written to a temp
    # file — the place a raw copy could be left behind. A stored (uncompressed) filler
    # entry the parser never reads.
    raw = _export(**{"export/Rich_Media.bin": os.urandom(1_200_000)})
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    # Deterministic import: no model call is allowed on this path.
    with patch("main.extract_facts_from_text", side_effect=AssertionError("LLM called")), \
            patch("main.extract_basics", side_effect=AssertionError("LLM called")):
        resp = test_client.post(
            f"/profiles/{profile_id}/resume", headers=headers,
            files={"file": ("Basic_LinkedInDataExport.zip", raw, "application/zip")},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert any(f["achievement"] == "Python" for f in body["facts"])
    assert body["basics"]["full_name"] == "Asha Kulkarni"

    # Unconfirmed: nothing is in the facts KB until facts:bulk.
    assert test_client.get(f"/resume-facts?profile_id={profile_id}", headers=headers).json() == []
    # No raw file kept: not on disk, and not in the DB row (drafts only).
    assert list(tmp_path.iterdir()) == []
    db = SessionLocal()
    row = db.query(models.ResumeUpload).filter_by(profile_id=profile_id).one()
    stored = " ".join(str(getattr(row, c.name)) for c in models.ResumeUpload.__table__.columns)
    db.close()
    assert "Rich_Media" not in stored and "PK" not in stored


def test_malicious_zip_upload_is_a_422(client):  # noqa: F811
    test_client, SessionLocal = client
    token = _signup_and_login(test_client, "li-bad@example.com")
    profile_id = _create_profile(SessionLocal, "li-bad@example.com")
    resp = test_client.post(
        f"/profiles/{profile_id}/resume", headers={"Authorization": f"Bearer {token}"},
        files={"file": ("export.zip", _zip({"../Skills.csv": SKILLS_CSV}), "application/zip")},
    )
    assert resp.status_code == 422
