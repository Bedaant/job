import uuid
import enum
from datetime import datetime

import sqlalchemy
from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, ForeignKey, Enum, JSON, UniqueConstraint, Numeric, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from database import Base

EMBEDDING_DIM = 512  # voyage-3-lite — smaller/cheaper, good enough for matching at this scale


def gen_uuid():
    return str(uuid.uuid4())


class ApplicationStatus(str, enum.Enum):
    saved = "saved"
    ready_for_review = "ready_for_review"  # batch-prepared (tailored + truth-checked), awaiting human approval
    approved = "approved"    # cleared to send: a human approved it, or it fell inside an approved campaign's bounds (ADR-015)
    dismissed = "dismissed"  # user declined during review — distinct from `rejected` (employer rejected)
    # The window between claiming a submission and knowing whether the form
    # actually went through. Claim used to flip straight to `applied`, before
    # the native submit fired — so a form that then failed left the user
    # believing they had applied when they had not. This names that window;
    # POST /applications/{id}/submission-result is the only thing that closes it.
    submitting = "submitting"
    applied = "applied"
    oa = "oa"                # online assessment
    recruiter = "recruiter"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    archived = "archived"  # DELETE /campaigns/{id} lands here — never a hard delete


class Persona(str, enum.Enum):
    developer = "developer"
    product_manager = "product_manager"
    marketing = "marketing"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)  # null when Google-only (later)
    created_at = Column(DateTime, default=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
    # Last time the browser extension called in (work-queue / map-fields). Under
    # ADR-015 nothing is submitted without it, so the web app shows it (0016).
    extension_last_seen_at = Column(DateTime, nullable=True)

    profiles = relationship("Profile", back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    persona = Column(Enum(Persona), nullable=False, default=Persona.developer)
    headline = Column(String, nullable=True)
    location = Column(String, nullable=True)
    prefs = Column(JSON, default=dict)

    # Applicant identity — the data an application form actually asks for.
    # Field names mirror JSON Resume's `basics` block (this project's existing
    # export target, parsing/jsonresume_export.py) so the mapping is lossless.
    # Validated on the way in by schemas.ApplicantBasics.
    #
    # `location` above is kept deliberately: it's the freeform preference/display
    # string already exposed by ProfileOut, whereas city/region/country_code are
    # the structured fields a form needs. Removing it would break existing
    # serialization for no gain.
    #
    # No email column: login identity is User.email and there is no case yet for
    # a separate contact address.
    full_name = Column(String, nullable=True)        # basics.name
    phone = Column(String, nullable=True)            # basics.phone
    website_url = Column(String, nullable=True)      # basics.url
    street_address = Column(String, nullable=True)   # basics.location.address
    city = Column(String, nullable=True)             # basics.location.city
    region = Column(String, nullable=True)           # basics.location.region
    country_code = Column(String(2), nullable=True)  # basics.location.countryCode, ISO 3166-1 alpha-2
    postal_code = Column(String, nullable=True)      # basics.location.postalCode
    network_profiles = Column(JSON, default=list)    # basics.profiles[] -> [{network, username, url}]
    work_auth = Column(JSON, default=list)           # SPEC.md §1 profiles.work_auth
    fact_centroid = Column(Vector(EMBEDDING_DIM), nullable=True)  # mean of fact embeddings, F6 matching
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="profiles")
    resume_facts = relationship("ResumeFact", back_populates="profile", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="profile", cascade="all, delete-orphan")
    matches = relationship("Match", back_populates="profile", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="profile", cascade="all, delete-orphan")
    answers = relationship("AnswerBank", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "persona", name="uq_profile_user_persona"),)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    source = Column(String, nullable=False)          # remotive | greenhouse | lever | ashby
    external_id = Column(String, nullable=False)      # id from the source, for dedupe
    canonical_hash = Column(String, nullable=False, unique=True)   # cross-source dedupe key, SPEC.md §3.1
    title = Column(String, nullable=False)
    company = Column(String, nullable=False)
    location = Column(String, nullable=True)
    remote = Column(Boolean, default=True)
    salary = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    apply_url = Column(String, nullable=False)
    tags = Column(JSON, default=list)
    skills = Column(JSON, default=list)  # extracted keywords, for skill_coverage scoring
    seniority = Column(String, nullable=True)  # intern|junior|mid|senior|staff|lead, inferred from title
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    posted_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)

    applications = relationship("Application", back_populates="job")
    matches = relationship("Match", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_job_source_external_id"),)


class Campaign(Base):
    """ADR-015 §2 — the unit of approval. The user approves a campaign once
    (which roles/sources, the caps, the tailoring instructions) and the agents
    discover -> tailor -> apply autonomously inside those bounds. This replaces
    ADR-001's per-application gate (superseded).

    `daily_cap` is ADR-015's non-negotiable rail. There is deliberately NO
    counter column and no campaign_runs table: the cap is derived from this
    campaign's `applications` rows created today (campaigns.py::
    remaining_quota), which is the only number that can't drift out of sync
    with what actually went out.
    """
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    profile_id = Column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(Enum(CampaignStatus), nullable=False, default=CampaignStatus.draft)

    # Bounds the user approved. Empty list = no restriction on that axis
    # (empty `sources` means every enabled source, per the campaign contract).
    roles = Column(JSON, default=list)        # title keywords
    locations = Column(JSON, default=list)
    remote_only = Column(Boolean, nullable=False, default=True)
    sources = Column(JSON, default=list)      # Job.source values

    # 0..1 fraction. Match.score is stored 0..100 (matching/scoring.py), so the
    # comparison in campaigns.py scales by 100 — kept as a fraction here because
    # that is the contract the campaign UI was built against.
    min_match_score = Column(Numeric(4, 3), nullable=False, default=0.7)
    daily_cap = Column(sqlalchemy.Integer, nullable=False, default=10)
    auto_submit = Column(Boolean, nullable=False, default=False)
    # The user's own instructions to the tailor. Never a source of facts —
    # ADR-006/ADR-009 stand: only ResumeFacts can ground a claim.
    tailoring_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run_at = Column(DateTime, nullable=True)

    profile = relationship("Profile", back_populates="campaigns")
    applications = relationship("Application", back_populates="campaign")


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    profile_id = Column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id"), nullable=False)
    # Nullable + SET NULL on purpose: applications created by hand have no
    # campaign, and a deleted campaign must not take the user's real
    # application history with it. This column is the daily-cap source of truth.
    campaign_id = Column(
        UUID(as_uuid=False), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.saved)
    portal = Column(String, nullable=True)  # e.g. "Wellfound", "Turing", "Direct"
    notes = Column(Text, nullable=True)
    tailored_resume_json = Column(JSON, nullable=True)
    tailored_cover_letter = Column(Text, nullable=True)
    # ADR-006's truth-check pass already computes this (tailoring/engine.py
    # ::tailor_application returns flagged_unsupported_claims) but /tailor
    # never persisted it before sub-project #2 — silently dropped on every
    # call. Surfaced, not silently kept, is the whole point of the check.
    flagged_unsupported_claims = Column(JSON, default=list)
    # ADR-015: questions a driver run stopped on, verbatim as the form asked them.
    # Never demographic. The review queue shows only the ones the answer bank still
    # can't answer, so saving an answer is what clears them.
    pending_questions = Column(JSON, default=list)
    applied_at = Column(DateTime, nullable=True)
    next_follow_up_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="applications")
    job = relationship("Job", back_populates="applications")
    campaign = relationship("Campaign", back_populates="applications")

    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_application_profile_job"),)


class ResumeFact(Base):
    """
    Atomic, verifiable facts about the candidate. The tailoring engine may only
    rewrite/reorder/select from these — never invent new ones.
    """
    __tablename__ = "resume_facts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    profile_id = Column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    category = Column(String, nullable=False)   # experience | project | skill | certification | education
    achievement = Column(Text, nullable=False)   # the factual claim, in plain language
    proof = Column(Text, nullable=True)          # what it's backed by (project/role name)
    metric = Column(String, nullable=True)       # e.g. "10x throughput", "27% productivity"
    tags = Column(JSON, default=list)            # e.g. ["automation", "PM", "SQL", "fintech"]
    period_from = Column(sqlalchemy.Date, nullable=True)
    period_to = Column(sqlalchemy.Date, nullable=True)  # null = present (SPEC.md §1)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("Profile", back_populates="resume_facts")


class Match(Base):
    """F6 matching (SPEC.md §3.2). Hard filters run in SQL before this; score
    is 0.55*semantic + 0.30*skill_coverage + 0.15*recency.
    """
    __tablename__ = "matches"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    profile_id = Column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=False), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    score = Column(Numeric(5, 2), nullable=False)
    breakdown = Column(JSON, nullable=False)  # {semantic, skill_coverage, recency, matched_skills, missing_skills}
    state = Column(String, nullable=False, default="new")  # new | dismissed | saved
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("Profile", back_populates="matches")
    job = relationship("Job", back_populates="matches")

    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_match_profile_job"),)


class Event(Base):
    """Transactional outbox (ADR-012, SPEC.md §1/ARCHITECTURE.md §4.6). Written
    in the SAME transaction as the business row it announces; the relay worker
    (events/relay.py) publishes unpublished rows to Redis, then stamps
    published_at. `id` is monotonic and doubles as the SSE Last-Event-ID.
    """
    __tablename__ = "events"

    # SQLite (unit-test engine) only treats an exact "INTEGER" column as its
    # autoincrementing rowid alias — BIGINT doesn't qualify, so id inserts
    # come back NULL there unless BigInteger is downgraded to Integer for
    # that dialect specifically. Postgres (real DB) is unaffected.
    id = Column(BigInteger().with_variant(sqlalchemy.Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # match.new|application.status_changed|resume.parsed|notification.created
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)  # null = not yet relayed to Redis


class Notification(Base):
    """SPEC.md §2.6. status tracks delivery (pending -> sent|failed|skipped);
    'seen' is a fifth value for the in-app read receipt (PATCH /notifications/{id})
    — the SPEC's endpoint table and its DDL disagreed on this (DDL's CHECK only
    listed the four delivery states), resolved by extending the CHECK rather than
    adding a separate column, see WORKLOG.
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    trigger = Column(String, nullable=False)  # weekly_digest|follow_up_nudge|application_status
    channel = Column(String, nullable=False)  # email|in_app
    template = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    status = Column(String, nullable=False, default="pending")
    sent_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ConnectorRun(Base):
    """SPEC.md §1. Generic run-log for anything that fetches from the outside
    world on a schedule. F5's unknown-ATS classification (connectors/discovery.py
    ::discover_ats_for_domain) is the first real writer — a proposed ATS
    pattern goes in `notes` as JSON for the owner to review and manually
    promote into ATS_PATTERNS (decided: no new table/admin UI for that review
    surface, this is it).
    """
    __tablename__ = "connector_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    source = Column(String, nullable=False)
    token = Column(String, nullable=True)
    fetched = Column(sqlalchemy.Integer, nullable=False, default=0)
    inserted = Column(sqlalchemy.Integer, nullable=False, default=0)
    failed = Column(sqlalchemy.Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    notes = Column(JSON, nullable=True)  # structured payload, e.g. F5's proposed-pattern review row
    duration_ms = Column(sqlalchemy.Integer, nullable=True)
    ran_at = Column(DateTime, default=datetime.utcnow)


class ResumeUpload(Base):
    """Tracks one resume-parsing run (SPEC.md §2.1). The raw file is never
    persisted — only the parsed draft facts, until the user confirms them via
    facts:bulk (ADR-009: the resume blob is never the generation source).
    """
    __tablename__ = "resume_uploads"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    profile_id = Column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="parsing")  # parsing | ready | failed
    draft_facts = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnswerBank(Base):
    """One question the user has answered in their own words, reusable on every
    later form that asks the same thing (ADR-015). Without this, an auto-apply
    run stops on "why do you want to work here?" for every employer, forever;
    with it, the interruptions shrink.

    The text here is ALWAYS user-written — answer_bank.py::save_answer is the
    only write path and nothing in that module's import graph can reach
    call_llm. That is what keeps ADR-006/ADR-009 trivially satisfied for these
    answers: there is no generated claim, so there is nothing to truth-check.

    `question_text` is kept verbatim (it is what the user was looking at when
    they answered, and it is what the demographic guard re-checks on read);
    `question_normalized` is the derived matching key and half the unique key,
    so re-answering the same question updates the row rather than adding a
    second, contradictory answer to the same question.
    """
    __tablename__ = "answer_bank"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    profile_id = Column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)

    question_text = Column(Text, nullable=False)
    question_normalized = Column(String, nullable=False, index=True)
    answer_text = Column(Text, nullable=False)

    # Whether this feature is actually paying off, per answer. Incremented only
    # by serve_answer — a lookup is not a use.
    times_used = Column(sqlalchemy.Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="answers")

    __table_args__ = (
        UniqueConstraint("profile_id", "question_normalized", name="uq_answer_bank_profile_question"),
    )
