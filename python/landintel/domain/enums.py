from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD = "DEAD"


class JobType(StrEnum):
    MANUAL_URL_SNAPSHOT = "MANUAL_URL_SNAPSHOT"


class SourceFreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class AppRoleName(StrEnum):
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class StorageBackend(StrEnum):
    LOCAL = "local"
    SUPABASE = "supabase"

