from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


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


class MapFieldsRequest(BaseModel):
    profile_id: str
    url: str
    fields: List[FieldDescriptorIn]


class FieldMappingOut(BaseModel):
    field_id: str
    maps_to: str
    confidence: float
    value: Optional[str] = None


class TailorRequest(BaseModel):
    job_id: str
    profile_id: str


class BulletOut(BaseModel):
    text: str
    source_fact_ids: List[str] = []  # SPEC.md §3.3 — empty only on the nvidia_smoke dev path


class TailorResponse(BaseModel):
    summary: str
    bullets: List[BulletOut]
    cover_letter: str
    flagged_unsupported_claims: List[str] = []
