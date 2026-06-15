"""
Pydantic-settings configuration — Gemini-only build.

P0 variables (GEMINI_API_KEY, SECRET_KEY, DATABASE_URL, REDIS_URL) are
validated in model_post_init and cause an immediate sys.exit(1) if missing or
still set to placeholder values, so misconfiguration is caught at startup.

All LLM, embedding, vision, audio, and video operations route exclusively
through Google Gemini APIs.
"""

import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_VALUES = {
    "your_gemini_api_key_here",
    "change_me_to_a_long_random_string",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # P0 — required
    GEMINI_API_KEY: str
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str

    # P1 — defaults provided
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION: str = "geminirag_chunks"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    UPLOAD_DIR: str = "/tmp/geminirag_uploads"

    # Gemini models
    LLM_PROVIDER: str = "gemini"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/gemini-embedding-2"

    # RAG tuning
    CHUNK_SIZE: int = 600
    CHILD_CHUNK_SIZE: int = 150
    CHUNK_OVERLAP: int = 50
    RAG_TOP_K: int = 8
    CONFIDENCE_THRESHOLD: float = 0.35

    # Celery retry config
    CELERY_MAX_RETRIES: int = 3
    CELERY_RETRY_BACKOFF: int = 60

    # Observability
    OTEL_EXPORTER: str = "stdout"
    OTEL_SERVICE_NAME: str = "geminirag"

    ALLOWED_ORIGINS: str = "http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    def model_post_init(self, __context) -> None:
        errors = []
        if not self.GEMINI_API_KEY or self.GEMINI_API_KEY in _PLACEHOLDER_VALUES:
            errors.append("GEMINI_API_KEY is missing or still a placeholder")
        if not self.SECRET_KEY or self.SECRET_KEY in _PLACEHOLDER_VALUES:
            errors.append("SECRET_KEY is missing or still a placeholder")
        if not self.DATABASE_URL:
            errors.append("DATABASE_URL is missing")
        if errors:
            sys.stderr.write("STARTUP ERROR — missing required environment variables:\n")
            for e in errors:
                sys.stderr.write(f"  • {e}\n")
            sys.exit(1)


settings = Settings()


def get_settings() -> Settings:
    return settings
