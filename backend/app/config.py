"""
PRAHARI · configuration
════════════════════════════════════════════════════════════════════════════
Everything that differs between a laptop, a demo venue and a deployment lives
here and nowhere else. Three rules this module exists to enforce:

  1. No secret has a usable default. JWT_SECRET has no fallback in production —
     the app refuses to start rather than sign tokens with a guessable key.
  2. DEMO_MODE is a deployment decision, not a code path. Production cannot
     serve generated weather or seeded fields because the providers that
     produce them are not constructed at all when DEMO_MODE is false.
  3. Every external dependency is named by an env var and has an explicit
     "unavailable" state. Nothing falls back to fabricated data.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "demo", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore", case_sensitive=False)

    # ── environment ────────────────────────────────────────────────────────
    app_env: AppEnv = "development"
    demo_mode: bool = False
    app_version: str = "2.0.0"
    log_level: str = "INFO"
    log_json: bool = False

    # ── database ───────────────────────────────────────────────────────────
    # sqlite:///./prahari.db  ·  postgresql+psycopg://user:pw@host/db
    database_url: str = "sqlite:///./prahari.db"
    db_echo: bool = False
    auto_migrate: bool = True          # runs the versioned migration runner
    auto_seed_demo: bool = False       # NEVER honoured when app_env=production

    # ── auth ───────────────────────────────────────────────────────────────
    jwt_secret: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_hours: int = 12
    password_reset_ttl_minutes: int = 30
    password_min_length: int = 8

    # ── CORS / security ────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    trusted_hosts: str = "*"
    rate_limit_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10
    max_upload_bytes: int = 12_000_000

    # ── weather ────────────────────────────────────────────────────────────
    # openmeteo | demo | none
    weather_provider: str = "openmeteo"
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_api_key: str | None = None
    weather_cache_minutes: int = 90
    weather_timeout_seconds: float = 8.0
    # After a 429 or a 5xx the provider is left alone for this long. Without it
    # a rate-limited deployment retries on every request and holds itself under
    # the limit indefinitely — the failure amplifies instead of clearing.
    # `Retry-After`, when the provider sends one, wins over this default.
    weather_cooldown_seconds: int = 120
    weather_cooldown_max_seconds: int = 900
    # How old a cached series may be and still be served, clearly labelled
    # stale, when the provider cannot be reached. Real weather twelve hours old
    # and marked as such is honest; generated weather never is.
    weather_stale_max_hours: int = 12

    # ── vision ─────────────────────────────────────────────────────────────
    # onnx | api | none
    vision_provider: str = "none"
    vision_model_path: str | None = None
    vision_model_labels: str | None = None     # path to labels.json
    vision_model_version: str = "unset"
    vision_api_url: str | None = None
    vision_api_key: str | None = None
    vision_timeout_seconds: float = 20.0

    # ── the assistant's optional language-model seam ───────────────────────
    # Off by default and off in every test. When a key is present the model is
    # allowed to REPHRASE what PRAHARI retrieved and nothing else; see llm.py
    # for the guard that enforces it. A deployment-wide key here is the
    # fallback — a farmer's own key, stored per account, takes precedence.
    llm_provider: str = "none"                 # none | gemini | openai
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 20.0
    llm_max_output_tokens: int = 600
    # The symptom-feature classifier is NOT a neural network. It is allowed to
    # produce a ranked differential when no trained model is configured, but it
    # is always labelled as what it is, and a deployment can switch it off.
    allow_feature_engine: bool = True

    # ── object storage ─────────────────────────────────────────────────────
    storage_provider: str = "local"               # local | s3
    storage_local_dir: str = "./var/uploads"
    storage_public_base: str = "/media"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    signed_url_ttl_seconds: int = 900

    # ── notifications ──────────────────────────────────────────────────────
    sms_provider: str = "none"                    # none | log | http
    sms_api_url: str | None = None
    sms_api_key: str | None = None
    sms_sender_id: str | None = None
    email_provider: str = "none"                  # none | log | smtp
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    # ── clock ──────────────────────────────────────────────────────────────
    # Pin the system clock for a reproducible demo. Refused in production.
    prahari_today: str | None = None

    # ── derived ────────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        v = (self.cors_origins or "").strip()
        if v == "*":
            return ["*"]
        return [o.strip() for o in v.split(",") if o.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        v = (self.trusted_hosts or "*").strip()
        return [h.strip() for h in v.split(",") if h.strip()] or ["*"]

    @field_validator("weather_provider", "vision_provider", "storage_provider",
                     "sms_provider", "email_provider", mode="before")
    @classmethod
    def _lower(cls, v):
        return str(v).strip().lower() if v is not None else v

    @model_validator(mode="after")
    def _production_guards(self):
        if self.app_env == "production":
            if not self.jwt_secret or len(self.jwt_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be set to at least 32 characters in production. "
                    "Generate one with: python -c \"import secrets;print(secrets.token_urlsafe(48))\"")
            if self.demo_mode:
                raise ValueError("DEMO_MODE cannot be true when APP_ENV=production.")
            if self.auto_seed_demo:
                raise ValueError("AUTO_SEED_DEMO cannot be true when APP_ENV=production.")
            if self.weather_provider == "demo":
                raise ValueError(
                    "WEATHER_PROVIDER=demo is a generated series. Production must use a real "
                    "provider; if none is reachable the API returns weather_unavailable.")
            if self.prahari_today:
                raise ValueError("PRAHARI_TODAY pins the clock and is refused in production.")
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS=* is refused in production. Name the frontend origin.")
            if self.database_url.startswith("sqlite"):
                raise ValueError(
                    "SQLite is for local development and the demo build. Set DATABASE_URL to a "
                    "PostgreSQL URL for production.")
        if not self.jwt_secret:
            # Development / test only: ephemeral, so restarting invalidates tokens.
            self.jwt_secret = secrets.token_urlsafe(48)
        return self

    def redacted(self) -> dict:
        """What /api/health may safely say about how this instance is configured."""
        return {
            "app_env": self.app_env,
            "demo_mode": self.demo_mode,
            "version": self.app_version,
            "database": "postgresql" if "postgres" in self.database_url else "sqlite",
            "weather_provider": self.weather_provider,
            "vision_provider": self.vision_provider,
            "vision_model_version": self.vision_model_version,
            "storage_provider": self.storage_provider,
            "sms_provider": self.sms_provider,
            "email_provider": self.email_provider,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Tests build several apps in one process; each needs its own environment."""
    get_settings.cache_clear()
    return get_settings()


settings = get_settings()
