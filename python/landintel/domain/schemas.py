from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    DocumentExtractionStatus,
    DocumentType,
    GeomConfidence,
    GeomSourceType,
    JobStatus,
    JobType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SiteStatus,
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


class SiteFromClusterRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)


class SiteGeometryUpdateRequest(BaseModel):
    geom_4326: dict[str, Any]
    source_type: GeomSourceType = GeomSourceType.ANALYST_DRAWN
    confidence: GeomConfidence | None = None
    reason: str | None = Field(default=None, max_length=1000)
    created_by: str | None = Field(default=None, max_length=255)
    raw_asset_id: UUID | None = None


class SiteWarningRead(BaseModel):
    code: str
    message: str


class SiteGeometryRead(BaseModel):
    geom_4326: dict[str, Any]
    geom_hash: str
    geom_source_type: GeomSourceType
    geom_confidence: GeomConfidence
    site_area_sqm: float


class SiteGeometryRevisionRead(BaseModel):
    id: UUID
    geom_hash: str
    geom_4326: dict[str, Any]
    source_type: GeomSourceType
    confidence: GeomConfidence
    site_area_sqm: float
    reason: str | None
    created_by: str | None
    created_at: datetime
    raw_asset_id: UUID | None
    warnings: list[SiteWarningRead] = Field(default_factory=list)


class SiteLpaLinkRead(BaseModel):
    lpa_id: str
    lpa_name: str
    overlap_pct: float
    overlap_sqm: float
    is_primary: bool


class SiteTitleLinkRead(BaseModel):
    title_number: str
    overlap_pct: float
    overlap_sqm: float
    confidence: GeomConfidence


class SiteMarketEventRead(BaseModel):
    id: UUID
    event_type: str
    event_at: datetime
    price_gbp: int | None
    basis_type: PriceBasisType
    listing_item_id: UUID | None
    notes: str | None


class SiteClusterSummaryRead(BaseModel):
    id: UUID
    cluster_key: str
    cluster_status: ListingClusterStatus
    member_count: int


class SiteListingSummaryRead(BaseModel):
    id: UUID
    headline: str | None
    canonical_url: str
    latest_status: ListingStatus
    guide_price_gbp: int | None
    price_basis_type: PriceBasisType
    address_text: str | None
    source_name: str


class SiteSummaryRead(BaseModel):
    id: UUID
    display_name: str
    borough_id: str | None
    borough_name: str | None
    site_status: SiteStatus
    manual_review_required: bool
    warnings: list[SiteWarningRead]
    current_geometry: SiteGeometryRead
    current_listing: SiteListingSummaryRead | None
    listing_cluster: SiteClusterSummaryRead


class SiteDetailRead(SiteSummaryRead):
    geometry_revisions: list[SiteGeometryRevisionRead]
    lpa_links: list[SiteLpaLinkRead]
    title_links: list[SiteTitleLinkRead]
    market_events: list[SiteMarketEventRead]
    source_documents: list[ListingDocumentRead]
    source_snapshots: list[SourceSnapshotRead]


class SiteListResponse(BaseModel):
    items: list[SiteSummaryRead]
    total: int


class PlaceholderResponse(BaseModel):
    detail: str
    surface: str
    spec_phase: str


class AssessmentRequest(BaseModel):
    site_id: UUID
    scenario_id: UUID
    as_of_date: date
