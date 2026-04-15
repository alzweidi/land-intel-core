from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    DocumentExtractionStatus,
    DocumentType,
    JobStatus,
    JobType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SourceFreshnessStatus,
    SourceParseStatus,
)


class ManualUrlIntakeRequest(BaseModel):
    url: AnyHttpUrl
    source_name: str = Field(default="manual_url", min_length=1, max_length=255)
    requested_by: str | None = Field(default=None, max_length=255)


class ConnectorRunRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)


class JobAcceptedResponse(BaseModel):
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
    parse_status: SourceParseStatus
    parse_error_text: str | None
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


class ListingSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    connector_type: ConnectorType
    compliance_mode: ComplianceMode
    refresh_policy_json: dict[str, Any]
    active: bool
    created_at: datetime


class ListingDocumentRead(BaseModel):
    id: UUID
    asset_id: UUID
    doc_type: DocumentType
    page_count: int | None
    extraction_status: DocumentExtractionStatus
    extracted_text: str | None
    asset: RawAssetRead


class ListingSnapshotRead(BaseModel):
    id: UUID
    source_snapshot_id: UUID
    observed_at: datetime
    headline: str | None
    description_text: str | None
    guide_price_gbp: int | None
    price_basis_type: PriceBasisType
    status: ListingStatus
    auction_date: date | None
    address_text: str | None
    lat: float | None
    lon: float | None
    brochure_asset: RawAssetRead | None
    map_asset: RawAssetRead | None
    raw_record_json: dict[str, Any]


class ListingSummaryRead(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str
    source_listing_id: str
    canonical_url: str
    listing_type: ListingType
    first_seen_at: datetime
    last_seen_at: datetime
    latest_status: ListingStatus
    current_snapshot_id: UUID | None
    current_snapshot: ListingSnapshotRead | None
    normalized_address: str | None
    cluster_id: UUID | None = None
    cluster_status: ListingClusterStatus | None = None
    cluster_confidence: float | None = None


class ListingDetailRead(ListingSummaryRead):
    snapshots: list[ListingSnapshotRead]
    documents: list[ListingDocumentRead]
    source_snapshots: list[SourceSnapshotRead]


class ListingListResponse(BaseModel):
    items: list[ListingSummaryRead]
    total: int


class ListingClusterMemberRead(BaseModel):
    id: UUID
    listing_item_id: UUID
    confidence: float
    rules_json: dict[str, Any]
    created_at: datetime
    listing: ListingSummaryRead


class ListingClusterSummaryRead(BaseModel):
    id: UUID
    cluster_key: str
    cluster_status: ListingClusterStatus
    created_at: datetime
    member_count: int
    members: list[ListingSummaryRead]


class ListingClusterDetailRead(BaseModel):
    id: UUID
    cluster_key: str
    cluster_status: ListingClusterStatus
    created_at: datetime
    members: list[ListingClusterMemberRead]


class ListingClusterListResponse(BaseModel):
    items: list[ListingClusterSummaryRead]
    total: int


class PlaceholderResponse(BaseModel):
    detail: str
    surface: str
    spec_phase: str


class AssessmentRequest(BaseModel):
    site_id: UUID
    scenario_id: UUID
    as_of_date: date
