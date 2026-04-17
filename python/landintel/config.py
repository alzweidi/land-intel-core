from functools import lru_cache
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from landintel.domain.enums import StorageBackend

DEFAULT_WEB_AUTH_SESSION_SECRET = "landintel-local-web-session-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_name: str = "landintel-core"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://landintel:landintel@postgres:5432/landintel"
    database_echo: bool = False

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    worker_id: str = "worker-local-1"
    worker_poll_interval_seconds: int = 2
    worker_max_attempts: int = 3
    worker_metrics_port: int = 9101

    scheduler_poll_interval_seconds: int = 30

    storage_backend: StorageBackend = StorageBackend.LOCAL
    storage_local_root: str = "/data/storage"

    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "raw-assets"
    supabase_auth_jwks_url: str | None = None

    snapshot_http_timeout_seconds: int = Field(default=20, ge=1)
    run_db_migrations: bool = False

    next_public_api_base_url: str = "http://localhost:8000"
    next_public_map_style_url: str = "https://demotiles.maplibre.org/style.json"
    web_auth_session_secret: str = Field(
        default=DEFAULT_WEB_AUTH_SESSION_SECRET,
        validation_alias=AliasChoices("LANDINTEL_WEB_AUTH_SECRET", "AUTH_SECRET"),
    )
    web_auth_session_cookie_name: str = "landintel-session"

    sentry_dsn: str | None = None

    @model_validator(mode="after")
    def validate_web_auth_session_secret(self) -> "Settings":
        app_env_explicit = "app_env" in self.model_fields_set
        app_env = self.app_env.strip().lower()
        if (
            app_env not in {"development", "test"}
            and self.web_auth_session_secret == DEFAULT_WEB_AUTH_SESSION_SECRET
        ):
            raise ValueError(
                "LANDINTEL_WEB_AUTH_SECRET must be set to a non-default value outside local dev."
            )
        if (
            not app_env_explicit
            and self.web_auth_session_secret == DEFAULT_WEB_AUTH_SESSION_SECRET
            and not _is_local_database_url(self.database_url)
        ):
            raise ValueError(
                "APP_ENV must be set explicitly when using a non-local database with the "
                "default web auth secret."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _is_local_database_url(database_url: str) -> bool:
    lowered = database_url.strip().lower()
    if lowered.startswith("sqlite"):
        return True
    parsed = urlparse(database_url)
    hostname = (parsed.hostname or "").strip().lower()
    return hostname in {"postgres", "localhost", "127.0.0.1"}
