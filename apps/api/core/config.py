from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
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

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7  # 7 days

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env/.env, validated at boot
