from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # RLS backstop (migration 0010): the FastAPI app connects as a
    # deliberately restricted role (no BYPASSRLS) for every real request;
    # migrations and background workers keep using database_url's owner
    # role. Optional and falls back to database_url when unset, so nothing
    # breaks before the role/password actually exists on a given Postgres
    # instance (e.g. the SQLite test engine never needs this at all).
    app_database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str
    reed_api_key: str | None = None  # optional — reed connector no-ops without it
    voyage_api_key: str | None = None  # optional — embedding pipeline no-ops without it
    langfuse_secret_key: str | None = None  # optional — tracing no-ops without it (ADR-014)
    langfuse_public_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Dev-only smoke-test provider swap for tailoring/engine.py. Default
    # ("anthropic") is the real, unchanged path. "nvidia_smoke" routes the
    # tailoring call through NVIDIA NIM's free OpenAI-compatible API instead —
    # verifies the pipeline fires mechanically, does NOT validate real
    # tailoring quality (NIM serves open models, not Claude).
    llm_provider: str = "anthropic"
    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_smoke_model: str = "google/diffusiongemma-26b-a4b-it"
    # "nvidia" (the owner's production choice, 2026-09-27): NIM through the SAME
    # validated paths as Claude — instructor + fact-id grounding + truth-check.
    # Picked by a live bake-off on a fabrication-trap tailoring task: fastest of
    # the models that cited only real facts and didn't invent a skill (WORKLOG
    # latest+34). Override with NVIDIA_MODEL.
    nvidia_model: str = "nvidia/nemotron-3-super-120b-a12b"
    # Off by default: measured live, thinking made the same answer 6x slower
    # (4.4s vs 0.7s) and pushed tailoring's JSON past its token cap.
    nvidia_enable_thinking: bool = False

    def nvidia_extra_body(self) -> dict:
        """Request extras for NIM. Only the real "nvidia" provider — the smoke
        model may not accept chat_template_kwargs."""
        if self.llm_provider != "nvidia":
            return {}
        return {"chat_template_kwargs": {"enable_thinking": self.nvidia_enable_thinking}}

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7  # 7 days

    # Daily digest email (digest.smtp_sender). Unset SMTP_HOST = log-only, nothing sent.
    smtp_host: str | None = None
    smtp_port: int = 587  # 465 = implicit TLS, anything else = STARTTLS
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None  # defaults to smtp_user

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env/.env, validated at boot
