from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from landintel.domain.enums import JobStatus, JobType, SourceFreshnessStatus


class ManualUrlIntakeRequest(BaseModel):
    url: AnyHttpUrl
    source_name: str = Field(default="manual_url", min_length=1, max_length=255)
    requested_by: str | None = Field(default=None, max_length=255)


class ManualUrlIntakeResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    job_type: JobType


class RawAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_type: str
    original_url: str
    storage_path: str
    mime_type: str
    content_sha256: str
    size_bytes: int
    fetched_at: datetime


class SourceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_family: str
    source_name: str
    source_uri: str
    acquired_at: datetime
    effective_from: datetime | None
    effective_to: datetime | None
    schema_hash: str
    content_hash: str
    coverage_note: str | None
    freshness_status: SourceFreshnessStatus
    manifest_json: dict[str, Any]
    raw_assets: list[RawAssetRead]


class JobRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: JobType
    status: JobStatus
    attempts: int
    run_at: datetime
    next_run_at: datetime
    locked_at: datetime | None
    worker_id: str | None
    error_text: str | None
    payload_json: dict[str, Any]


class PlaceholderResponse(BaseModel):
    detail: str
    surface: str
    spec_phase: str


class AssessmentRequest(BaseModel):
    site_id: UUID
    scenario_id: UUID
    as_of_date: date

