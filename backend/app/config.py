from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "StockOut Alert"
    environment: str = "development"
    database_url: str = "sqlite:///./stockout.db"
    secret_key: str = "dev-only-insecure-secret-change-me"
    access_token_expire_minutes: int = 60
    bcrypt_rounds: int = 12
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    demo_mode: bool = True
    demo_password: str = "Demo#2026!"
    # Comma-separated E.164 numbers allowed to receive *live* SMS while DEMO_MODE is on.
    demo_sms_allowlist: str = ""
    demo_staff_phone: str = ""

    # Africa's Talking
    at_username: str = ""
    at_api_key: str = ""
    at_sender_id: str = ""
    at_environment: str = "sandbox"  # sandbox | live
    at_webhook_token: str = ""
    at_webhook_allowed_ips: str = ""
    at_ussd_service_code: str = ""
    sms_force_simulation: bool = False
    sms_http_timeout_seconds: float = 10.0
    sms_max_attempts: int = 3
    sms_retry_base_seconds: int = 60

    # Freshness defaults (overridable at runtime through system configuration)
    fresh_hours: int = 72
    unknown_after_days: int = 30

    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    ussd_session_timeout_seconds: int = 180

    rate_limit_public_per_minute: int = 60
    rate_limit_sensitive_per_minute: int = 10

    @field_validator("database_url")
    @classmethod
    def _db_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            return "postgresql://" + v[len("postgres://"):]
        return v

    @field_validator("at_environment")
    @classmethod
    def _env(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"sandbox", "live"}:
            raise ValueError("AT_ENVIRONMENT must be 'sandbox' or 'live'")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def demo_sms_allowlist_set(self) -> set[str]:
        return {p.strip() for p in self.demo_sms_allowlist.split(",") if p.strip()}

    @property
    def at_configured(self) -> bool:
        return bool(self.at_username and self.at_api_key)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and s.secret_key.startswith("dev-only"):
        raise RuntimeError("SECRET_KEY must be set in production")
    return s
