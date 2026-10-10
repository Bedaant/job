"""The tailored resume for one application, rendered and verified.

Shared by the download endpoint (main.py) and apply-by-email (apply_email.py), so the
bytes a user downloads and the bytes an employer receives come from one path.
"""
import models
from documents.ats_safety import lint_docx
from documents.generate_docx import generate_resume_docx
from documents.parse_back import parse_back_check

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ResumeNotRenderable(ValueError):
    """The generated document failed the ATS lint or the parse-back check."""


def tailored_facts(db, application: models.Application) -> list[dict]:
    """Only bullets whose every source_fact_id resolves to this profile's facts go in
    (ADR-009); the LLM's free-text summary does not."""
    facts = {
        f.id: f for f in
        db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == application.profile_id)
    }
    facts_list = []
    for i, bullet in enumerate((application.tailored_resume_json or {}).get("bullets") or []):
        ids = bullet.get("source_fact_ids") or []
        text = (bullet.get("text") or "").strip()
        if not text or not ids or any(fid not in facts for fid in ids):
            continue
        cited = [facts[fid] for fid in ids]
        # Dates only when every cited fact agrees — a merged bullet has no one period.
        same_period = len({(f.period_from, f.period_to) for f in cited}) == 1
        facts_list.append({
            "id": f"bullet-{i}", "category": cited[0].category, "achievement": text,
            "period_from": cited[0].period_from if same_period else None,
            "period_to": cited[0].period_to if same_period else None,
        })
    return facts_list


def contact_header(profile: models.Profile) -> tuple[str | None, list[str]]:
    """Name + one contact line from the profile's own basics; never guessed."""
    name = profile.full_name or " ".join(p for p in (profile.given_name, profile.family_name) if p) or None
    place = ", ".join(p for p in (profile.city, profile.region) if p)
    links = [profile.website_url] + [n.get("url") for n in (profile.network_profiles or []) if isinstance(n, dict)]
    contact = [profile.user.email, profile.phone, place, *links]
    return name, list(dict.fromkeys(c for c in contact if c))


def render_verified_resume(profile: models.Profile, facts_list: list[dict]) -> bytes:
    """Render, then lint and parse-back before any bytes leave the server — a document
    that fails either never ships."""
    name, contact = contact_header(profile)
    docx_bytes = generate_resume_docx(profile.headline, facts_list, name=name, contact=contact)

    violations = lint_docx(docx_bytes)
    if violations:
        raise ResumeNotRenderable(f"Generated resume failed ATS-safety checks: {violations}")

    failed_parse_back = [r for r in parse_back_check(docx_bytes, facts_list) if not r["passed"]]
    if failed_parse_back:
        raise ResumeNotRenderable(f"Generated resume failed parse-back check: {failed_parse_back}")
    return docx_bytes
