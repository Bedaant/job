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
    # Per-request cap on every LLM call (the SDK default is 600 s).
    llm_timeout_seconds: float = 120.0
    # Retried once on this model (same provider, same validated path) when the primary fails.
    llm_fallback_model: str | None = None
    llm_cache_ttl_seconds: int = 7 * 24 * 3600

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
    # The owner: receives ops alerts and is the only user allowed GET /ops/health. Unset = both off.
    alert_email: str | None = None

    # REACH-A. Encrypts the Gmail refresh token at rest (ADR-003: "the highest-value
    # secret in the system"). Optional ONLY so the rest of the app boots without it —
    # `crypto.py` refuses to encrypt or decrypt when it is unset, it never degrades to
    # plaintext. Generate one with `python -c "from crypto import generate_key;
    # print(generate_key())"`.
    encryption_key: str | None = None
    # Gmail OAuth client (REACH-A). The owner creates these in the Google Cloud console;
    # they cannot be produced from code. Consent screen stays in Testing mode, which
    # allows 100 listed test users with no verification review — see
    # docs/PLAN-GMAIL-CREDENTIALS.md. Past ~80 users that ceiling needs revisiting, and
    # hitting it looks like "OAuth suddenly broke" rather than "we outgrew Testing mode".
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # REACH-E. Paid contact sourcing via Apify's linkedin-profile-search actor. Declared
    # here rather than left to `os.environ` because `extra="ignore"` means an undeclared
    # key in `.env` is silently DROPPED — the adapter then no-ops and reports "no
    # candidates", which is indistinguishable from a company having nobody. Found live:
    # the token was in `.env` and reachable by neither path.
    apify_token: str | None = None
    # REACH-B / DEPLOY-A.2. `GitHubContactSource` calls api.github.com directly rather
    # than shelling out to the `gh` CLI, which would have been a runtime dependency a
    # container does not have. Optional: anonymous works at GitHub's 60 req/hour, and a
    # token raises it to 5,000. Declared here for the same reason as `apify_token` —
    # `extra="ignore"` silently drops an undeclared key from `.env`.
    github_token: str | None = None
    # Daily USD ceilings enforced by providers/guard.py before each paid call (None = no cap).
    daily_usd_cap_apify: float | None = 2.0
    daily_usd_cap_voyage: float | None = 1.0
    daily_usd_cap_llm: float | None = 5.0

    cors_origins: list[str] = ["http://localhost:3000"]
    # Where emailed links (password reset) point.
    web_base_url: str = "http://localhost:3000"
    # Where the API itself is reachable from outside. Distinct from `web_base_url`
    # because the outreach unsubscribe route is served by the API, not the web app, and
    # that link goes to a RECIPIENT who is not a user — if it points at localhost they
    # cannot opt out at all. Must be set to a public URL before any outreach is sent.
    api_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env/.env, validated at boot
