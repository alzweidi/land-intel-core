from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from landintel.domain.enums import StorageBackend


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

    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

