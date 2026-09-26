import re
from datetime import date, datetime
from typing import Optional, List, Union
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Applicant identity (JSON Resume `basics`) ----------
# The data an application form actually asks for. Field names mirror JSON
# Resume's `basics` block (already this project's export target, see
# parsing/jsonresume_export.py) so the mapping stays lossless.
#
# `email` is deliberately NOT here — it lives on User.email (login identity).
# Revisit only if a user needs a different contact address than their login.
#
# Every field is Optional and defaults to None on purpose: a resume genuinely
# may not state a phone or a website, and if null weren't freely available the
# extraction model would be pushed toward inventing something. The validators
# below enforce "null rather than a plausible guess" — a fabricated name or
# phone number gets typed into a real application sent to a real employer,
# which is direct harm to the user, so this is checked, not merely requested
# in the prompt.

_PLACEHOLDER_NAMES = {
    "john doe", "jane doe", "john smith", "jane smith", "your name", "full name",
    "first last", "firstname lastname", "n/a", "na", "none", "unknown", "candidate name",
}

# 555-0100..555-0199 is the reserved fictional US range (NANP). A model filling
# a gap with a "realistic looking" number lands in it surprisingly often.
_FICTIONAL_PHONE_RE = re.compile(r"555-?01\d{2}")

_MIN_PHONE_DIGITS = 7   # shortest real national number
_MAX_PHONE_DIGITS = 15  # ITU-T E.164 ceiling


def _require_url_scheme(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not value.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} must include an http(s):// scheme, got {value!r}")
    return value


class NetworkProfile(BaseModel):
    """One professional profile link — JSON Resume `basics.profiles[]`."""

    network: str                        # "LinkedIn" | "GitHub" | "Portfolio" | ...
    username: Optional[str] = None
    url: Optional[str] = None

    @field_validator("url")
    @classmethod
    def url_needs_scheme(cls, value: Optional[str]) -> Optional[str]:
        return _require_url_scheme(value, "network profile url")


class ApplicantBasics(BaseModel):
    full_name: Optional[str] = None       # basics.name
    phone: Optional[str] = None           # basics.phone
    website_url: Optional[str] = None     # basics.url
    street_address: Optional[str] = None  # basics.location.address
    city: Optional[str] = None            # basics.location.city
    region: Optional[str] = None          # basics.location.region
    country_code: Optional[str] = None    # basics.location.countryCode, ISO 3166-1 alpha-2
    postal_code: Optional[str] = None     # basics.location.postalCode
    network_profiles: List[NetworkProfile] = []   # basics.profiles[]
    work_auth: List[str] = []             # SPEC.md §1 profiles.work_auth

    @field_validator("full_name")
    @classmethod
    def reject_placeholder_names(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value.strip().lower() in _PLACEHOLDER_NAMES:
            raise ValueError(
                f"full_name looks like a placeholder, not a real name: {value!r} — return null instead"
            )
        return value

    @field_validator("phone")
    @classmethod
    def phone_must_be_plausible(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        digits = re.sub(r"\D", "", value)
        if not _MIN_PHONE_DIGITS <= len(digits) <= _MAX_PHONE_DIGITS:
            raise ValueError(
                f"phone has {len(digits)} digits, expected {_MIN_PHONE_DIGITS}-{_MAX_PHONE_DIGITS} "
                f"— return null instead of a partial number"
            )
        if _FICTIONAL_PHONE_RE.search(value) or _FICTIONAL_PHONE_RE.search(digits):
            raise ValueError(
                f"phone is in the reserved fictional 555-01XX range: {value!r} — return null instead"
            )
        return value

    @field_validator("website_url")
    @classmethod
    def website_needs_scheme(cls, value: Optional[str]) -> Optional[str]:
        return _require_url_scheme(value, "website_url")

    @field_validator("country_code")
    @classmethod
    def country_code_must_be_alpha2(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        candidate = value.strip()
        if not re.fullmatch(r"[A-Za-z]{2}", candidate):
            raise ValueError(
                f"country_code must be ISO 3166-1 alpha-2 (two letters, e.g. US, IN), got {value!r}"
            )
        return candidate.upper()


class ProfileCreate(BaseModel):
    persona: str
    headline: Optional[str] = None
    location: Optional[str] = None
    prefs: dict = {}


class ProfileOut(BaseModel):
    id: str
    persona: str
    headline: Optional[str]
    location: Optional[str]
    prefs: dict

    class Config:
        from_attributes = True


class JobOut(BaseModel):
    id: str
    source: str
    title: str
    company: str
    location: Optional[str]
    remote: bool
    salary: Optional[str]
    description: Optional[str]
    apply_url: str
    tags: List[str] = []
    posted_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApplicationCreate(BaseModel):
    job_id: str
    profile_id: str
    portal: Optional[str] = None
    notes: Optional[str] = None


class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    portal: Optional[str] = None
    notes: Optional[str] = None
    next_follow_up_at: Optional[datetime] = None


class ApplicationOut(BaseModel):
    id: str
    job_id: str
    profile_id: str
    status: str
    portal: Optional[str]
    notes: Optional[str]
    tailored_cover_letter: Optional[str]
    applied_at: Optional[datetime]
    next_follow_up_at: Optional[datetime]

    class Config:
        from_attributes = True


class ResumeFactIn(BaseModel):
    category: str
    achievement: str
    proof: Optional[str] = None
    metric: Optional[str] = None
    tags: List[str] = []
    period_from: Optional[date] = None
    period_to: Optional[date] = None  # null = present


class ResumeFactOut(ResumeFactIn):
    id: str
    profile_id: str

    class Config:
        from_attributes = True


class FactDraft(BaseModel):
    category: str
    achievement: str
    proof: Optional[str] = None
    metric: Optional[str] = None
    tags: List[str] = []


class ResumeUploadOut(BaseModel):
    upload_id: str
    status: str
    facts: List[FactDraft] = []
    # Draft identity extracted alongside the facts. Not persisted here on
    # purpose — the client reviews it and commits via PUT /profiles/{id}/basics,
    # mirroring how draft facts require facts:bulk confirmation (SPEC.md §2.1).
    # None when extraction failed or produced nothing; a failed identity
    # extraction never fails the whole upload.
    basics: Optional[ApplicantBasics] = None
    error: Optional[str] = None


class FactsBulkIn(BaseModel):
    facts: List[ResumeFactIn]


class MatchOut(BaseModel):
    id: str
    job: JobOut
    score: float
    breakdown: dict
    state: str

    class Config:
        from_attributes = True


class KeywordMatchOut(BaseModel):
    keyword: str
    evidence_fact_id_or_index: Union[str, int]
    match_type: str  # exact | fuzzy | synonym
    importance: str  # high | medium | low


class KeywordMissingOut(BaseModel):
    keyword: str
    importance: str


class KeywordWeakOut(BaseModel):
    keyword: str
    evidence_fact_id_or_index: Union[str, int]
    reason: str  # metadata_only | single_mention


class KeywordSuggestionOut(BaseModel):
    action: str  # surface | reword — never "add": a suggestion may only move or
                 # reword a fact the user already has (ADR-009).
    fact_id_or_index: Union[str, int]
    keyword: str
    rationale: str


class KeywordGapOut(BaseModel):
    """matching/keyword_gap.py's output. `missing` is advisory only — nothing in
    `suggestions` ever references a keyword listed there.
    """
    coverage: float
    matched: List[KeywordMatchOut]
    missing: List[KeywordMissingOut]
    weak: List[KeywordWeakOut]
    suggestions: List[KeywordSuggestionOut]


class NotificationOut(BaseModel):
    id: str
    trigger: str
    channel: str
    template: str
    payload: dict
    status: str
    sent_at: Optional[datetime]
    error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationUpdate(BaseModel):
    status: str


class FieldDescriptorIn(BaseModel):
    field_id: str
    label_text: Optional[str] = None
    input_type: str
    options: List[str] = []
    required: bool = False
    # Raw DOM attributes formfill/deterministic.py's rule matcher reads —
    # autocomplete is a real web standard (WHATWG HTML), name/dom_id are the
    # element's own name/id. All optional: older extension builds that don't
    # send them just get None, which the deterministic matcher already
    # treats as "no signal, fall through to the LLM path" — non-breaking.
    autocomplete: Optional[str] = None
    name: Optional[str] = None
    dom_id: Optional[str] = None


class MapFieldsRequest(BaseModel):
    profile_id: str
    url: str
    fields: List[FieldDescriptorIn]


class FieldMappingOut(BaseModel):
    field_id: str
    maps_to: str
    confidence: float
    value: Optional[str] = None


class BulletOut(BaseModel):
    text: str
    source_fact_ids: List[str] = []  # SPEC.md §3.3 — empty only on the nvidia_smoke dev path


class ApplicationReviewOut(BaseModel):
    """Sub-project #2/#3's exact contract — the review-queue frontend
    (apps/web/app/review/page.tsx) was built against this shape before this
    backend existed; keep them in sync deliberately, don't drift.
    """
    id: str
    job: JobOut
    match_score: Optional[float] = None
    match_breakdown: Optional[dict] = None
    status: str
    tailored_summary: Optional[str] = None
    tailored_bullets: List[BulletOut] = []
    tailored_cover_letter: Optional[str] = None
    flagged_unsupported_claims: List[str] = []
    created_at: datetime


class BatchApproveRequest(BaseModel):
    application_ids: List[str]


# ---------- Campaigns (ADR-015 §2) ----------
# The user approves a campaign once — roles/sources/caps/template — and the
# agents discover -> tailor -> apply inside those bounds. Replaces ADR-001's
# per-application gate. Bounds are validated here because they are a real
# trust boundary: daily_cap is ADR-015's non-negotiable rail, and a cap of 0
# or a min_match_score of 1.5 would silently mean "never apply", while a
# negative cap would mean "unbounded" to any naive comparison.


class CampaignBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    roles: List[str] = []       # title keywords
    locations: List[str] = []
    remote_only: bool = True
    sources: List[str] = []     # Job.source values; empty = every enabled source
    min_match_score: float = Field(default=0.7, ge=0.0, le=1.0)
    daily_cap: int = Field(default=10, ge=1, le=200)
    auto_submit: bool = False   # True = skip the optional human review step
    tailoring_notes: Optional[str] = None  # user instructions to the tailor, never a source of facts


class CampaignCreate(CampaignBase):
    profile_id: str


class CampaignUpdate(BaseModel):
    """Every field optional — this is edit/pause/resume in one endpoint.
    `status` is validated against campaigns.ALLOWED_TRANSITIONS, not here.
    """
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[str] = None
    roles: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    remote_only: Optional[bool] = None
    sources: Optional[List[str]] = None
    min_match_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    daily_cap: Optional[int] = Field(default=None, ge=1, le=200)
    auto_submit: Optional[bool] = None
    tailoring_notes: Optional[str] = None


class CampaignOut(CampaignBase):
    id: str
    profile_id: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CampaignStatsOut(BaseModel):
    applied_today: int
    daily_cap: int
    remaining_today: int
    total_applied: int
    last_run_at: Optional[datetime] = None


class BatchApproveResponse(BaseModel):
    approved: List[str]


class TailorRequest(BaseModel):
    job_id: str
    profile_id: str


class TailorResponse(BaseModel):
    summary: str
    bullets: List[BulletOut]
    cover_letter: str
    flagged_unsupported_claims: List[str] = []
