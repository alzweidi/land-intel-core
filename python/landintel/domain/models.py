import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from landintel.db.base import Base
from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideStatus,
    AssessmentOverrideType,
    AssessmentRunState,
    AuditExportStatus,
    BaselinePackStatus,
    CalibrationMethod,
    ComparableOutcome,
    ComplianceMode,
    ConnectorType,
    DocumentExtractionStatus,
    DocumentType,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    EvidenceImportance,
    EvidencePolarity,
    GeomConfidence,
    GeomSourceType,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    HistoricalLabelDecision,
    IncidentStatus,
    IncidentType,
    JobStatus,
    JobType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    MarketLandCompSourceType,
    ModelReleaseStatus,
    PriceBasisType,
    ProposalForm,
    ReleaseChannel,
    ReviewStatus,
    ScenarioSource,
    ScenarioStatus,
    SiteMarketEventType,
    SiteStatus,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    ValuationQuality,
    ValuationRunState,
    VerifiedStatus,
    VisibilityMode,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_family: Mapped[str] = mapped_column(String(100), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schema_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    coverage_note: Mapped[str | None] = mapped_column(Text)
    freshness_status: Mapped[SourceFreshnessStatus] = mapped_column(
        Enum(SourceFreshnessStatus, name="source_freshness_status"),
        nullable=False,
        default=SourceFreshnessStatus.FRESH,
    )
    parse_status: Mapped[SourceParseStatus] = mapped_column(
        Enum(SourceParseStatus, name="source_parse_status"),
        nullable=False,
        default=SourceParseStatus.PENDING,
    )
    parse_error_text: Mapped[str | None] = mapped_column(Text)
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    raw_assets: Mapped[list["RawAsset"]] = relationship(back_populates="source_snapshot")
    listing_snapshots: Mapped[list["ListingSnapshot"]] = relationship(
        back_populates="source_snapshot"
    )
    coverage_snapshots: Mapped[list["SourceCoverageSnapshot"]] = relationship(
        back_populates="source_snapshot"
    )


class RawAsset(Base):
    __tablename__ = "raw_asset"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    source_snapshot: Mapped[SourceSnapshot] = relationship(back_populates="raw_assets")
    listing_documents: Mapped[list["ListingDocument"]] = relationship(back_populates="asset")
    planning_application_documents: Mapped[list["PlanningApplicationDocument"]] = relationship(
        back_populates="asset"
    )


class SourceCoverageSnapshot(Base):
    __tablename__ = "source_coverage_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    borough_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_family: Mapped[str] = mapped_column(String(100), nullable=False)
    coverage_geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_status: Mapped[SourceCoverageStatus] = mapped_column(
        Enum(SourceCoverageStatus, name="source_coverage_status"),
        nullable=False,
        default=SourceCoverageStatus.UNKNOWN,
    )
    gap_reason: Mapped[str | None] = mapped_column(Text)
    freshness_status: Mapped[SourceFreshnessStatus] = mapped_column(
        Enum(SourceFreshnessStatus, name="source_freshness_status", create_type=False),
        nullable=False,
        default=SourceFreshnessStatus.UNKNOWN,
    )
    coverage_note: Mapped[str | None] = mapped_column(Text)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="SET NULL"),
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    source_snapshot: Mapped[SourceSnapshot | None] = relationship(
        back_populates="coverage_snapshots"
    )
    borough: Mapped["LpaBoundary"] = relationship(back_populates="coverage_snapshots")


class ListingSource(Base):
    __tablename__ = "listing_source"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    connector_type: Mapped[ConnectorType] = mapped_column(
        Enum(ConnectorType, name="connector_type"),
        nullable=False,
    )
    compliance_mode: Mapped[ComplianceMode] = mapped_column(
        Enum(ComplianceMode, name="compliance_mode"),
        nullable=False,
    )
    refresh_policy_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    listing_items: Mapped[list["ListingItem"]] = relationship(back_populates="source")


class ListingItem(Base):
    __tablename__ = "listing_item"
    __table_args__ = (UniqueConstraint("source_id", "source_listing_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listing_source.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_listing_id: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    listing_type: Mapped[ListingType] = mapped_column(
        Enum(ListingType, name="listing_type"),
        nullable=False,
        default=ListingType.UNKNOWN,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    latest_status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, name="listing_status"),
        nullable=False,
        default=ListingStatus.UNKNOWN,
    )
    current_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    normalized_address: Mapped[str | None] = mapped_column(String(500))
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    source: Mapped[ListingSource] = relationship(back_populates="listing_items")
    snapshots: Mapped[list["ListingSnapshot"]] = relationship(
        back_populates="listing_item",
        cascade="all, delete-orphan",
        order_by="ListingSnapshot.observed_at.desc()",
    )
    documents: Mapped[list["ListingDocument"]] = relationship(
        back_populates="listing_item",
        cascade="all, delete-orphan",
    )
    cluster_members: Mapped[list["ListingClusterMember"]] = relationship(
        back_populates="listing_item",
        cascade="all, delete-orphan",
    )


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listing_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    headline: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)
    guide_price_gbp: Mapped[int | None] = mapped_column(BigInteger)
    price_basis_type: Mapped[PriceBasisType] = mapped_column(
        Enum(PriceBasisType, name="price_basis_type"),
        nullable=False,
        default=PriceBasisType.UNKNOWN,
    )
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, name="listing_status"),
        nullable=False,
        default=ListingStatus.UNKNOWN,
    )
    auction_date: Mapped[date | None] = mapped_column(Date)
    address_text: Mapped[str | None] = mapped_column(Text)
    normalized_address: Mapped[str | None] = mapped_column(String(500))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    brochure_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="SET NULL"),
    )
    map_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="SET NULL"),
    )
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    listing_item: Mapped[ListingItem] = relationship(back_populates="snapshots")
    source_snapshot: Mapped[SourceSnapshot] = relationship(back_populates="listing_snapshots")
    brochure_asset: Mapped[RawAsset | None] = relationship(
        foreign_keys=[brochure_asset_id],
        lazy="joined",
    )
    map_asset: Mapped[RawAsset | None] = relationship(
        foreign_keys=[map_asset_id],
        lazy="joined",
    )


class ListingDocument(Base):
    __tablename__ = "listing_document"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listing_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"),
        nullable=False,
        default=DocumentType.UNKNOWN,
    )
    page_count: Mapped[int | None] = mapped_column(Integer)
    extraction_status: Mapped[DocumentExtractionStatus] = mapped_column(
        Enum(DocumentExtractionStatus, name="document_extraction_status"),
        nullable=False,
        default=DocumentExtractionStatus.NOT_ATTEMPTED,
    )
    extracted_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    listing_item: Mapped[ListingItem] = relationship(back_populates="documents")
    asset: Mapped[RawAsset] = relationship(back_populates="listing_documents")


class ListingCluster(Base):
    __tablename__ = "listing_cluster"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cluster_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    cluster_status: Mapped[ListingClusterStatus] = mapped_column(
        Enum(ListingClusterStatus, name="listing_cluster_status"),
        nullable=False,
        default=ListingClusterStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    members: Mapped[list["ListingClusterMember"]] = relationship(
        back_populates="listing_cluster",
        cascade="all, delete-orphan",
    )
    site_candidates: Mapped[list["SiteCandidate"]] = relationship(
        back_populates="listing_cluster"
    )


class ListingClusterMember(Base):
    __tablename__ = "listing_cluster_member"
    __table_args__ = (
        UniqueConstraint("listing_cluster_id", "listing_item_id"),
        UniqueConstraint("listing_item_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listing_cluster.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listing_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rules_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    listing_cluster: Mapped[ListingCluster] = relationship(back_populates="members")
    listing_item: Mapped[ListingItem] = relationship(back_populates="cluster_members")


class LpaBoundary(Base):
    __tablename__ = "lpa_boundary"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(100), unique=True)
    authority_level: Mapped[str] = mapped_column(String(50), nullable=False, default="BOROUGH")
    geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    geom_4326: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    geom_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site_candidates: Mapped[list["SiteCandidate"]] = relationship(back_populates="borough")
    site_lpa_links: Mapped[list["SiteLpaLink"]] = relationship(back_populates="lpa")
    coverage_snapshots: Mapped[list["SourceCoverageSnapshot"]] = relationship(
        back_populates="borough"
    )
    planning_applications: Mapped[list["PlanningApplication"]] = relationship(
        back_populates="borough"
    )
    brownfield_site_states: Mapped[list["BrownfieldSiteState"]] = relationship(
        back_populates="borough"
    )
    policy_areas: Mapped[list["PolicyArea"]] = relationship(back_populates="borough")
    baseline_packs: Mapped[list["BoroughBaselinePack"]] = relationship(
        back_populates="borough"
    )


class HmlrTitlePolygon(Base):
    __tablename__ = "hmlr_title_polygon"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title_number: Mapped[str] = mapped_column(String(100), nullable=False)
    address_text: Mapped[str | None] = mapped_column(Text)
    normalized_address: Mapped[str | None] = mapped_column(String(500))
    geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    geom_4326: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    geom_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site_title_links: Mapped[list["SiteTitleLink"]] = relationship(
        back_populates="title_polygon"
    )


class SiteCandidate(Base):
    __tablename__ = "site_candidate"
    __table_args__ = (UniqueConstraint("listing_cluster_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    listing_cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("listing_cluster.id", ondelete="RESTRICT"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    borough_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
    )
    geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    geom_4326: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    geom_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    geom_source_type: Mapped[GeomSourceType] = mapped_column(
        Enum(GeomSourceType, name="geom_source_type"),
        nullable=False,
    )
    geom_confidence: Mapped[GeomConfidence] = mapped_column(
        Enum(GeomConfidence, name="geom_confidence"),
        nullable=False,
    )
    site_area_sqm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("listing_item.id", ondelete="SET NULL"),
    )
    current_price_gbp: Mapped[int | None] = mapped_column(BigInteger)
    current_price_basis_type: Mapped[PriceBasisType] = mapped_column(
        Enum(PriceBasisType, name="price_basis_type", create_type=False),
        nullable=False,
        default=PriceBasisType.UNKNOWN,
    )
    site_status: Mapped[SiteStatus] = mapped_column(
        Enum(SiteStatus, name="site_status"),
        nullable=False,
        default=SiteStatus.DRAFT,
    )
    manual_review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    warning_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    listing_cluster: Mapped[ListingCluster] = relationship(back_populates="site_candidates")
    borough: Mapped[LpaBoundary | None] = relationship(back_populates="site_candidates")
    current_listing: Mapped[ListingItem | None] = relationship(foreign_keys=[current_listing_id])
    geometry_revisions: Mapped[list["SiteGeometryRevision"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        order_by="SiteGeometryRevision.created_at.desc()",
    )
    title_links: Mapped[list["SiteTitleLink"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
    )
    lpa_links: Mapped[list["SiteLpaLink"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
    )
    market_events: Mapped[list["SiteMarketEvent"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        order_by="SiteMarketEvent.event_at.desc()",
    )
    planning_links: Mapped[list["SitePlanningLink"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
    )
    policy_facts: Mapped[list["SitePolicyFact"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
    )
    constraint_facts: Mapped[list["SiteConstraintFact"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
    )
    scenarios: Mapped[list["SiteScenario"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        order_by="SiteScenario.updated_at.desc()",
    )
    assessment_runs: Mapped[list["AssessmentRun"]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        order_by="AssessmentRun.created_at.desc()",
    )


class SiteGeometryRevision(Base):
    __tablename__ = "site_geometry_revision"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    geom_4326: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    geom_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[GeomSourceType] = mapped_column(
        Enum(GeomSourceType, name="geom_source_type", create_type=False),
        nullable=False,
    )
    confidence: Mapped[GeomConfidence] = mapped_column(
        Enum(GeomConfidence, name="geom_confidence", create_type=False),
        nullable=False,
    )
    site_area_sqm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    raw_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="SET NULL"),
    )
    warning_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    site: Mapped[SiteCandidate] = relationship(back_populates="geometry_revisions")
    raw_asset: Mapped[RawAsset | None] = relationship(foreign_keys=[raw_asset_id])
    frozen_scenarios: Mapped[list["SiteScenario"]] = relationship(
        back_populates="geometry_revision"
    )


class SiteTitleLink(Base):
    __tablename__ = "site_title_link"
    __table_args__ = (UniqueConstraint("site_id", "title_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    title_polygon_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("hmlr_title_polygon.id", ondelete="SET NULL"),
    )
    title_number: Mapped[str] = mapped_column(String(100), nullable=False)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    overlap_pct: Mapped[float] = mapped_column(Float, nullable=False)
    overlap_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[GeomConfidence] = mapped_column(
        Enum(GeomConfidence, name="geom_confidence", create_type=False),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="title_links")
    title_polygon: Mapped[HmlrTitlePolygon | None] = relationship(back_populates="site_title_links")


class SiteLpaLink(Base):
    __tablename__ = "site_lpa_link"
    __table_args__ = (UniqueConstraint("site_id", "lpa_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    lpa_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id"),
    )
    overlap_pct: Mapped[float] = mapped_column(Float, nullable=False)
    overlap_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="lpa_links")
    lpa: Mapped[LpaBoundary] = relationship(back_populates="site_lpa_links")


class SiteMarketEvent(Base):
    __tablename__ = "site_market_event"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[SiteMarketEventType] = mapped_column(
        Enum(SiteMarketEventType, name="site_market_event_type"),
        nullable=False,
        default=SiteMarketEventType.LISTING_EVIDENCE,
    )
    event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    price_gbp: Mapped[int | None] = mapped_column(BigInteger)
    basis_type: Mapped[PriceBasisType] = mapped_column(
        Enum(PriceBasisType, name="price_basis_type", create_type=False),
        nullable=False,
        default=PriceBasisType.UNKNOWN,
    )
    listing_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("listing_item.id", ondelete="SET NULL"),
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="market_events")
    listing_item: Mapped[ListingItem | None] = relationship(foreign_keys=[listing_item_id])


class PlanningApplication(Base):
    __tablename__ = "planning_application"
    __table_args__ = (UniqueConstraint("source_system", "external_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    borough_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
    )
    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    application_type: Mapped[str] = mapped_column(String(100), nullable=False)
    proposal_description: Mapped[str] = mapped_column(Text, nullable=False)
    valid_date: Mapped[date | None] = mapped_column(Date)
    decision_date: Mapped[date | None] = mapped_column(Date)
    decision: Mapped[str | None] = mapped_column(String(100))
    decision_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    route_normalized: Mapped[str | None] = mapped_column(String(100))
    units_proposed: Mapped[int | None] = mapped_column(Integer)
    site_geom_27700: Mapped[str | None] = mapped_column(Text)
    site_geom_4326: Mapped[dict[str, object] | None] = mapped_column(JSON)
    site_point_27700: Mapped[str | None] = mapped_column(Text)
    site_point_4326: Mapped[dict[str, object] | None] = mapped_column(JSON)
    source_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    borough: Mapped[LpaBoundary | None] = relationship(back_populates="planning_applications")
    source_snapshot: Mapped[SourceSnapshot] = relationship()
    documents: Mapped[list["PlanningApplicationDocument"]] = relationship(
        back_populates="planning_application",
        cascade="all, delete-orphan",
    )
    site_links: Mapped[list["SitePlanningLink"]] = relationship(
        back_populates="planning_application"
    )
    historical_labels: Mapped[list["HistoricalCaseLabel"]] = relationship(
        back_populates="planning_application",
        cascade="all, delete-orphan",
    )
    comparable_members: Mapped[list["ComparableCaseMember"]] = relationship(
        back_populates="planning_application"
    )


class PlanningApplicationDocument(Base):
    __tablename__ = "planning_application_document"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    planning_application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("planning_application.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="CASCADE"),
        nullable=False,
    )
    doc_type: Mapped[str] = mapped_column(String(100), nullable=False)
    doc_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    planning_application: Mapped[PlanningApplication] = relationship(back_populates="documents")
    asset: Mapped[RawAsset] = relationship(back_populates="planning_application_documents")


class SitePlanningLink(Base):
    __tablename__ = "site_planning_link"
    __table_args__ = (UniqueConstraint("site_id", "planning_application_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    planning_application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("planning_application.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id"),
    )
    application_snapshot_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    link_type: Mapped[str] = mapped_column(String(100), nullable=False)
    distance_m: Mapped[float | None] = mapped_column(Float)
    overlap_pct: Mapped[float | None] = mapped_column(Float)
    match_confidence: Mapped[GeomConfidence] = mapped_column(
        Enum(GeomConfidence, name="geom_confidence", create_type=False),
        nullable=False,
    )
    manual_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="planning_links")
    planning_application: Mapped[PlanningApplication] = relationship(back_populates="site_links")


class BrownfieldSiteState(Base):
    __tablename__ = "brownfield_site_state"
    __table_args__ = (UniqueConstraint("borough_id", "external_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    borough_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    geom_4326: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    part: Mapped[str] = mapped_column(String(50), nullable=False)
    pip_status: Mapped[str | None] = mapped_column(String(100))
    tdc_status: Mapped[str | None] = mapped_column(String(100))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    raw_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    borough: Mapped[LpaBoundary] = relationship(back_populates="brownfield_site_states")
    source_snapshot: Mapped[SourceSnapshot] = relationship()


class PolicyArea(Base):
    __tablename__ = "policy_area"
    __table_args__ = (UniqueConstraint("borough_id", "policy_family", "policy_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    borough_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
    )
    policy_family: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    geom_4326: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    legal_effective_from: Mapped[date | None] = mapped_column(Date)
    legal_effective_to: Mapped[date | None] = mapped_column(Date)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_class: Mapped[SourceClass] = mapped_column(
        Enum(SourceClass, name="source_class"),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    borough: Mapped[LpaBoundary | None] = relationship(back_populates="policy_areas")
    source_snapshot: Mapped[SourceSnapshot] = relationship()
    site_facts: Mapped[list["SitePolicyFact"]] = relationship(back_populates="policy_area")


class PlanningConstraintFeature(Base):
    __tablename__ = "planning_constraint_feature"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    feature_family: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_subtype: Mapped[str] = mapped_column(String(100), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(100), nullable=False)
    geom_27700: Mapped[str] = mapped_column(Text, nullable=False)
    geom_4326: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    legal_status: Mapped[str | None] = mapped_column(String(100))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_class: Mapped[SourceClass] = mapped_column(
        Enum(SourceClass, name="source_class", create_type=False),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    source_snapshot: Mapped[SourceSnapshot] = relationship()
    site_facts: Mapped[list["SiteConstraintFact"]] = relationship(
        back_populates="constraint_feature"
    )


class SitePolicyFact(Base):
    __tablename__ = "site_policy_fact"
    __table_args__ = (UniqueConstraint("site_id", "policy_area_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_area_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("policy_area.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id"),
    )
    policy_area_snapshot_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    relation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    overlap_pct: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    importance: Mapped[EvidenceImportance] = mapped_column(
        Enum(EvidenceImportance, name="evidence_importance"),
        nullable=False,
        default=EvidenceImportance.MEDIUM,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="policy_facts")
    policy_area: Mapped[PolicyArea] = relationship(back_populates="site_facts")


class SiteConstraintFact(Base):
    __tablename__ = "site_constraint_fact"
    __table_args__ = (UniqueConstraint("site_id", "constraint_feature_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    constraint_feature_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("planning_constraint_feature.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id"),
    )
    constraint_snapshot_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    overlap_pct: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[EvidenceImportance] = mapped_column(
        Enum(EvidenceImportance, name="evidence_importance", create_type=False),
        nullable=False,
        default=EvidenceImportance.MEDIUM,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="constraint_facts")
    constraint_feature: Mapped[PlanningConstraintFeature] = relationship(
        back_populates="site_facts"
    )


class BoroughBaselinePack(Base):
    __tablename__ = "borough_baseline_pack"
    __table_args__ = (UniqueConstraint("borough_id", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    borough_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[BaselinePackStatus] = mapped_column(
        Enum(BaselinePackStatus, name="baseline_pack_status"),
        nullable=False,
        default=BaselinePackStatus.DRAFT,
    )
    freshness_status: Mapped[SourceFreshnessStatus] = mapped_column(
        Enum(SourceFreshnessStatus, name="source_freshness_status", create_type=False),
        nullable=False,
        default=SourceFreshnessStatus.UNKNOWN,
    )
    signed_off_by: Mapped[str | None] = mapped_column(String(255))
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pack_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    borough: Mapped[LpaBoundary] = relationship(back_populates="baseline_packs")
    source_snapshot: Mapped[SourceSnapshot | None] = relationship()
    rulepacks: Mapped[list["BoroughRulepack"]] = relationship(
        back_populates="borough_baseline_pack",
        cascade="all, delete-orphan",
    )


class BoroughRulepack(Base):
    __tablename__ = "borough_rulepack"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    borough_baseline_pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("borough_baseline_pack.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[BaselinePackStatus] = mapped_column(
        Enum(BaselinePackStatus, name="baseline_pack_status", create_type=False),
        nullable=False,
        default=BaselinePackStatus.DRAFT,
    )
    freshness_status: Mapped[SourceFreshnessStatus] = mapped_column(
        Enum(SourceFreshnessStatus, name="source_freshness_status", create_type=False),
        nullable=False,
        default=SourceFreshnessStatus.UNKNOWN,
    )
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="SET NULL"),
    )
    rule_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    borough_baseline_pack: Mapped[BoroughBaselinePack] = relationship(
        back_populates="rulepacks"
    )
    source_snapshot: Mapped[SourceSnapshot | None] = relationship()


class ScenarioTemplate(Base):
    __tablename__ = "scenario_template"
    __table_args__ = (UniqueConstraint("key", "version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )


class SiteScenario(Base):
    __tablename__ = "site_scenario"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    proposal_form: Mapped[ProposalForm] = mapped_column(
        Enum(ProposalForm, name="proposal_form"),
        nullable=False,
    )
    units_assumed: Mapped[int] = mapped_column(Integer, nullable=False)
    route_assumed: Mapped[str] = mapped_column(String(100), nullable=False)
    height_band_assumed: Mapped[str] = mapped_column(String(100), nullable=False)
    net_developable_area_pct: Mapped[float] = mapped_column(Float, nullable=False)
    housing_mix_assumed_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    parking_assumption: Mapped[str | None] = mapped_column(Text)
    affordable_housing_assumption: Mapped[str | None] = mapped_column(Text)
    access_assumption: Mapped[str | None] = mapped_column(Text)
    site_geometry_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("site_geometry_revision.id", ondelete="SET NULL"),
    )
    red_line_geom_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_source: Mapped[ScenarioSource] = mapped_column(
        Enum(ScenarioSource, name="scenario_source"),
        nullable=False,
        default=ScenarioSource.AUTO,
    )
    status: Mapped[ScenarioStatus] = mapped_column(
        Enum(ScenarioStatus, name="scenario_status"),
        nullable=False,
        default=ScenarioStatus.SUGGESTED,
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("site_scenario.id", ondelete="SET NULL"),
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_headline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    heuristic_rank: Mapped[int | None] = mapped_column(Integer)
    manual_review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    stale_reason: Mapped[str | None] = mapped_column(Text)
    rationale_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    evidence_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="scenarios")
    geometry_revision: Mapped[SiteGeometryRevision | None] = relationship(
        back_populates="frozen_scenarios"
    )
    supersedes: Mapped["SiteScenario | None"] = relationship(
        remote_side="SiteScenario.id",
        back_populates="superseded_by",
    )
    superseded_by: Mapped[list["SiteScenario"]] = relationship(back_populates="supersedes")
    reviews: Mapped[list["ScenarioReview"]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="ScenarioReview.reviewed_at.desc()",
    )
    assessment_runs: Mapped[list["AssessmentRun"]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="AssessmentRun.created_at.desc()",
    )


class ScenarioReview(Base):
    __tablename__ = "scenario_review"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_scenario.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_status: Mapped[ScenarioStatus] = mapped_column(
        Enum(ScenarioStatus, name="scenario_status", create_type=False),
        nullable=False,
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    scenario: Mapped[SiteScenario] = relationship(back_populates="reviews")


class HistoricalCaseLabel(Base):
    __tablename__ = "historical_case_label"
    __table_args__ = (UniqueConstraint("planning_application_id", "label_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    planning_application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("planning_application.id", ondelete="CASCADE"),
        nullable=False,
    )
    borough_id: Mapped[str | None] = mapped_column(String(100))
    template_key: Mapped[str | None] = mapped_column(String(100))
    proposal_form: Mapped[ProposalForm | None] = mapped_column(
        Enum(ProposalForm, name="proposal_form", create_type=False),
    )
    route_normalized: Mapped[str | None] = mapped_column(String(100))
    units_proposed: Mapped[int | None] = mapped_column(Integer)
    site_area_sqm: Mapped[float | None] = mapped_column(Float)
    label_version: Mapped[str] = mapped_column(String(100), nullable=False)
    label_class: Mapped[HistoricalLabelClass] = mapped_column(
        Enum(HistoricalLabelClass, name="historical_label_class"),
        nullable=False,
    )
    label_decision: Mapped[HistoricalLabelDecision] = mapped_column(
        Enum(HistoricalLabelDecision, name="historical_label_decision"),
        nullable=False,
    )
    label_reason: Mapped[str | None] = mapped_column(Text)
    valid_date: Mapped[date | None] = mapped_column(Date)
    first_substantive_decision_date: Mapped[date | None] = mapped_column(Date)
    label_window_end: Mapped[date | None] = mapped_column(Date)
    source_priority_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archetype_key: Mapped[str | None] = mapped_column(String(255))
    designation_profile_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    provenance_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    source_snapshot_ids_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    raw_asset_ids_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    review_status: Mapped[GoldSetReviewStatus] = mapped_column(
        Enum(GoldSetReviewStatus, name="gold_set_review_status"),
        nullable=False,
        default=GoldSetReviewStatus.PENDING,
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notable_policy_issues_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    extant_permission_outcome: Mapped[str | None] = mapped_column(String(100))
    site_geometry_confidence: Mapped[GeomConfidence | None] = mapped_column(
        Enum(GeomConfidence, name="geom_confidence", create_type=False),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    planning_application: Mapped[PlanningApplication] = relationship(
        back_populates="historical_labels"
    )


class ModelRelease(Base):
    __tablename__ = "model_release"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    release_channel: Mapped[ReleaseChannel] = mapped_column(
        Enum(ReleaseChannel, name="release_channel"),
        nullable=False,
        default=ReleaseChannel.HIDDEN,
    )
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_borough_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[ModelReleaseStatus] = mapped_column(
        Enum(ModelReleaseStatus, name="model_release_status"),
        nullable=False,
        default=ModelReleaseStatus.NOT_READY,
    )
    model_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    transform_version: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(100), nullable=False)
    calibration_method: Mapped[CalibrationMethod] = mapped_column(
        Enum(CalibrationMethod, name="calibration_method"),
        nullable=False,
        default=CalibrationMethod.NONE,
    )
    model_artifact_path: Mapped[str | None] = mapped_column(Text)
    model_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    calibration_artifact_path: Mapped[str | None] = mapped_column(Text)
    calibration_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    validation_artifact_path: Mapped[str | None] = mapped_column(Text)
    validation_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    model_card_path: Mapped[str | None] = mapped_column(Text)
    model_card_hash: Mapped[str | None] = mapped_column(String(64))
    train_window_start: Mapped[date | None] = mapped_column(Date)
    train_window_end: Mapped[date | None] = mapped_column(Date)
    support_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    reason_text: Mapped[str | None] = mapped_column(Text)
    supersedes_release_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("model_release.id", ondelete="SET NULL"),
    )
    activated_by: Mapped[str | None] = mapped_column(String(255))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[str | None] = mapped_column(String(255))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    supersedes_release: Mapped["ModelRelease | None"] = relationship(
        remote_side="ModelRelease.id",
        back_populates="superseded_by_releases",
    )
    superseded_by_releases: Mapped[list["ModelRelease"]] = relationship(
        back_populates="supersedes_release"
    )
    active_scopes: Mapped[list["ActiveReleaseScope"]] = relationship(
        back_populates="model_release",
        cascade="all, delete-orphan",
    )
    assessment_results: Mapped[list["AssessmentResult"]] = relationship(
        back_populates="model_release"
    )
    prediction_ledgers: Mapped[list["PredictionLedger"]] = relationship(
        back_populates="model_release"
    )
    incidents: Mapped[list["IncidentRecord"]] = relationship(back_populates="model_release")
    audit_exports: Mapped[list["AuditExport"]] = relationship(back_populates="model_release")


class ActiveReleaseScope(Base):
    __tablename__ = "active_release_scope"
    __table_args__ = (UniqueConstraint("scope_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    release_channel: Mapped[ReleaseChannel] = mapped_column(
        Enum(ReleaseChannel, name="release_channel", create_type=False),
        nullable=False,
        default=ReleaseChannel.HIDDEN,
    )
    borough_id: Mapped[str | None] = mapped_column(String(100))
    model_release_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("model_release.id", ondelete="CASCADE"),
        nullable=False,
    )
    activated_by: Mapped[str | None] = mapped_column(String(255))
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    visibility_mode: Mapped[VisibilityMode] = mapped_column(
        Enum(VisibilityMode, name="visibility_mode"),
        nullable=False,
        default=VisibilityMode.HIDDEN_ONLY,
    )
    visibility_reason: Mapped[str | None] = mapped_column(Text)
    visible_enabled_by: Mapped[str | None] = mapped_column(String(255))
    visible_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    visibility_updated_by: Mapped[str | None] = mapped_column(String(255))
    visibility_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    model_release: Mapped[ModelRelease] = relationship(back_populates="active_scopes")
    incidents: Mapped[list["IncidentRecord"]] = relationship(
        back_populates="active_release_scope",
        cascade="all, delete-orphan",
        order_by="IncidentRecord.created_at.desc()",
    )


class AssessmentRun(Base):
    __tablename__ = "assessment_run"
    __table_args__ = (UniqueConstraint("idempotency_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_candidate.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("site_scenario.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[AssessmentRunState] = mapped_column(
        Enum(AssessmentRunState, name="assessment_run_state"),
        nullable=False,
        default=AssessmentRunState.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    requested_by: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    site: Mapped[SiteCandidate] = relationship(back_populates="assessment_runs")
    scenario: Mapped[SiteScenario] = relationship(back_populates="assessment_runs")
    feature_snapshot: Mapped["AssessmentFeatureSnapshot | None"] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    result: Mapped["AssessmentResult | None"] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    comparable_case_set: Mapped["ComparableCaseSet | None"] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        order_by="EvidenceItem.created_at.asc()",
    )
    prediction_ledger: Mapped["PredictionLedger | None"] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    overrides: Mapped[list["AssessmentOverride"]] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        order_by="AssessmentOverride.created_at.desc()",
    )
    audit_exports: Mapped[list["AuditExport"]] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        order_by="AuditExport.created_at.desc()",
    )
    valuation_runs: Mapped[list["ValuationRun"]] = relationship(
        back_populates="assessment_run",
        cascade="all, delete-orphan",
        order_by="ValuationRun.created_at.desc()",
    )


class AssessmentFeatureSnapshot(Base):
    __tablename__ = "assessment_feature_snapshot"
    __table_args__ = (UniqueConstraint("assessment_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_version: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    coverage_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="feature_snapshot")


class AssessmentResult(Base):
    __tablename__ = "assessment_result"
    __table_args__ = (UniqueConstraint("assessment_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_release_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("model_release.id", ondelete="SET NULL"),
    )
    release_scope_key: Mapped[str | None] = mapped_column(String(255))
    eligibility_status: Mapped[EligibilityStatus] = mapped_column(
        Enum(EligibilityStatus, name="eligibility_status", create_type=False),
        nullable=False,
    )
    estimate_status: Mapped[EstimateStatus] = mapped_column(
        Enum(EstimateStatus, name="estimate_status"),
        nullable=False,
        default=EstimateStatus.NONE,
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status"),
        nullable=False,
        default=ReviewStatus.NOT_REQUIRED,
    )
    approval_probability_raw: Mapped[float | None] = mapped_column(Float)
    approval_probability_display: Mapped[str | None] = mapped_column(String(32))
    estimate_quality: Mapped[EstimateQuality | None] = mapped_column(
        Enum(EstimateQuality, name="estimate_quality"),
    )
    source_coverage_quality: Mapped[str | None] = mapped_column(String(32))
    geometry_quality: Mapped[str | None] = mapped_column(String(32))
    support_quality: Mapped[str | None] = mapped_column(String(32))
    scenario_quality: Mapped[str | None] = mapped_column(String(32))
    ood_quality: Mapped[str | None] = mapped_column(String(32))
    ood_status: Mapped[str | None] = mapped_column(String(32))
    manual_review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    result_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="result")
    model_release: Mapped[ModelRelease | None] = relationship(back_populates="assessment_results")
    overrides: Mapped[list["AssessmentOverride"]] = relationship(
        back_populates="assessment_result",
        order_by="AssessmentOverride.created_at.desc()",
    )


class ComparableCaseSet(Base):
    __tablename__ = "comparable_case_set"
    __table_args__ = (UniqueConstraint("assessment_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(String(100), nullable=False)
    same_borough_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    london_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refused_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="comparable_case_set")
    members: Mapped[list["ComparableCaseMember"]] = relationship(
        back_populates="comparable_case_set",
        cascade="all, delete-orphan",
        order_by="ComparableCaseMember.rank.asc()",
    )


class ComparableCaseMember(Base):
    __tablename__ = "comparable_case_member"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    comparable_case_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("comparable_case_set.id", ondelete="CASCADE"),
        nullable=False,
    )
    planning_application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("planning_application.id", ondelete="CASCADE"),
        nullable=False,
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[ComparableOutcome] = mapped_column(
        Enum(ComparableOutcome, name="comparable_outcome"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    fallback_path: Mapped[str] = mapped_column(String(100), nullable=False)
    match_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    comparable_case_set: Mapped[ComparableCaseSet] = relationship(back_populates="members")
    planning_application: Mapped[PlanningApplication] = relationship(
        back_populates="comparable_members"
    )


class EvidenceItem(Base):
    __tablename__ = "evidence_item"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    polarity: Mapped[EvidencePolarity] = mapped_column(
        Enum(EvidencePolarity, name="evidence_polarity"),
        nullable=False,
    )
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[EvidenceImportance] = mapped_column(
        Enum(EvidenceImportance, name="evidence_importance", create_type=False),
        nullable=False,
    )
    source_class: Mapped[SourceClass] = mapped_column(
        Enum(SourceClass, name="source_class", create_type=False),
        nullable=False,
    )
    source_label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    raw_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    excerpt_text: Mapped[str | None] = mapped_column(Text)
    verified_status: Mapped[VerifiedStatus] = mapped_column(
        Enum(VerifiedStatus, name="verified_status"),
        nullable=False,
        default=VerifiedStatus.VERIFIED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="evidence_items")


class PredictionLedger(Base):
    __tablename__ = "prediction_ledger"
    __table_args__ = (UniqueConstraint("assessment_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_geom_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_release_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("model_release.id", ondelete="SET NULL"),
    )
    release_scope_key: Mapped[str | None] = mapped_column(String(255))
    calibration_hash: Mapped[str | None] = mapped_column(String(64))
    model_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    validation_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    valuation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("valuation_run.id", ondelete="SET NULL"),
    )
    response_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="PRE_SCORE")
    source_snapshot_ids_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    raw_asset_ids_json: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    result_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    replay_verification_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="HASH_CAPTURED",
    )
    replay_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replay_verification_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="prediction_ledger")
    model_release: Mapped[ModelRelease | None] = relationship(back_populates="prediction_ledgers")
    valuation_run: Mapped["ValuationRun | None"] = relationship()
    audit_exports: Mapped[list["AuditExport"]] = relationship(
        back_populates="prediction_ledger",
        order_by="AuditExport.created_at.desc()",
    )


class AssessmentOverride(Base):
    __tablename__ = "assessment_override"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    assessment_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("assessment_result.id", ondelete="SET NULL"),
    )
    valuation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("valuation_run.id", ondelete="SET NULL"),
    )
    override_type: Mapped[AssessmentOverrideType] = mapped_column(
        Enum(AssessmentOverrideType, name="assessment_override_type"),
        nullable=False,
    )
    status: Mapped[AssessmentOverrideStatus] = mapped_column(
        Enum(AssessmentOverrideStatus, name="assessment_override_status"),
        nullable=False,
        default=AssessmentOverrideStatus.ACTIVE,
    )
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_role: Mapped[AppRoleName] = mapped_column(
        Enum(AppRoleName, name="app_role_name", create_type=False),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    override_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("assessment_override.id", ondelete="SET NULL"),
    )
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="overrides")
    assessment_result: Mapped[AssessmentResult | None] = relationship(back_populates="overrides")
    valuation_run: Mapped["ValuationRun | None"] = relationship(back_populates="overrides")
    supersedes: Mapped["AssessmentOverride | None"] = relationship(
        remote_side="AssessmentOverride.id",
        back_populates="superseded_by",
    )
    superseded_by: Mapped[list["AssessmentOverride"]] = relationship(
        back_populates="supersedes"
    )


class IncidentRecord(Base):
    __tablename__ = "incident_record"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    active_release_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("active_release_scope.id", ondelete="SET NULL"),
    )
    model_release_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("model_release.id", ondelete="SET NULL"),
    )
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)
    borough_id: Mapped[str | None] = mapped_column(String(100))
    incident_type: Mapped[IncidentType] = mapped_column(
        Enum(IncidentType, name="incident_type"),
        nullable=False,
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status"),
        nullable=False,
        default=IncidentStatus.OPEN,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_visibility_mode: Mapped[VisibilityMode | None] = mapped_column(
        Enum(VisibilityMode, name="visibility_mode", create_type=False),
    )
    applied_visibility_mode: Mapped[VisibilityMode] = mapped_column(
        Enum(VisibilityMode, name="visibility_mode", create_type=False),
        nullable=False,
    )
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("incident_record.id", ondelete="SET NULL"),
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    active_release_scope: Mapped[ActiveReleaseScope | None] = relationship(
        back_populates="incidents"
    )
    model_release: Mapped[ModelRelease | None] = relationship(back_populates="incidents")
    supersedes: Mapped["IncidentRecord | None"] = relationship(
        remote_side="IncidentRecord.id",
        back_populates="superseded_by",
    )
    superseded_by: Mapped[list["IncidentRecord"]] = relationship(back_populates="supersedes")


class AuditExport(Base):
    __tablename__ = "audit_export"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    assessment_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("assessment_result.id", ondelete="SET NULL"),
    )
    valuation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("valuation_run.id", ondelete="SET NULL"),
    )
    prediction_ledger_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("prediction_ledger.id", ondelete="SET NULL"),
    )
    model_release_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("model_release.id", ondelete="SET NULL"),
    )
    status: Mapped[AuditExportStatus] = mapped_column(
        Enum(AuditExportStatus, name="audit_export_status"),
        nullable=False,
        default=AuditExportStatus.READY,
    )
    manifest_path: Mapped[str | None] = mapped_column(Text)
    manifest_hash: Mapped[str | None] = mapped_column(String(64))
    manifest_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="audit_exports")
    valuation_run: Mapped["ValuationRun | None"] = relationship(back_populates="audit_exports")
    prediction_ledger: Mapped[PredictionLedger | None] = relationship(
        back_populates="audit_exports"
    )
    model_release: Mapped[ModelRelease | None] = relationship(back_populates="audit_exports")


class MarketSaleComp(Base):
    __tablename__ = "market_sale_comp"
    __table_args__ = (UniqueConstraint("transaction_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    transaction_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    borough_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
    )
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="CASCADE"),
        nullable=False,
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_gbp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tenure: Mapped[str | None] = mapped_column(String(50))
    postcode_district: Mapped[str | None] = mapped_column(String(16))
    address_text: Mapped[str | None] = mapped_column(Text)
    floor_area_sqm: Mapped[float | None] = mapped_column(Float)
    rebased_price_per_sqm_hint: Mapped[float | None] = mapped_column(Float)
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    source_snapshot: Mapped[SourceSnapshot] = relationship()
    raw_asset: Mapped[RawAsset] = relationship()


class MarketIndexSeries(Base):
    __tablename__ = "market_index_series"
    __table_args__ = (UniqueConstraint("borough_id", "index_key", "period_month"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    borough_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
    )
    index_key: Mapped[str] = mapped_column(String(50), nullable=False)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    index_value: Mapped[float] = mapped_column(Float, nullable=False)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    source_snapshot: Mapped[SourceSnapshot] = relationship()
    raw_asset: Mapped[RawAsset] = relationship()


class MarketLandComp(Base):
    __tablename__ = "market_land_comp"
    __table_args__ = (UniqueConstraint("comp_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    comp_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    borough_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
    )
    template_key: Mapped[str | None] = mapped_column(String(100))
    proposal_form: Mapped[ProposalForm | None] = mapped_column(
        Enum(ProposalForm, name="proposal_form", create_type=False),
    )
    comp_source_type: Mapped[MarketLandCompSourceType] = mapped_column(
        Enum(MarketLandCompSourceType, name="market_land_comp_source_type"),
        nullable=False,
    )
    evidence_date: Mapped[date | None] = mapped_column(Date)
    unit_count: Mapped[int | None] = mapped_column(Integer)
    site_area_sqm: Mapped[float | None] = mapped_column(Float)
    post_permission_value_low: Mapped[float | None] = mapped_column(Float)
    post_permission_value_mid: Mapped[float | None] = mapped_column(Float)
    post_permission_value_high: Mapped[float | None] = mapped_column(Float)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("source_snapshot.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("raw_asset.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_record_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    source_snapshot: Mapped[SourceSnapshot] = relationship()
    raw_asset: Mapped[RawAsset] = relationship()


class ValuationAssumptionSet(Base):
    __tablename__ = "valuation_assumption_set"
    __table_args__ = (UniqueConstraint("version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    cost_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    policy_burden_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    discount_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    valuation_runs: Mapped[list["ValuationRun"]] = relationship(
        back_populates="valuation_assumption_set"
    )


class ValuationRun(Base):
    __tablename__ = "valuation_run"
    __table_args__ = (UniqueConstraint("assessment_run_id", "valuation_assumption_set_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("assessment_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    valuation_assumption_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("valuation_assumption_set.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[ValuationRunState] = mapped_column(
        Enum(ValuationRunState, name="valuation_run_state"),
        nullable=False,
        default=ValuationRunState.PENDING,
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_text: Mapped[str | None] = mapped_column(Text)

    assessment_run: Mapped[AssessmentRun] = relationship(back_populates="valuation_runs")
    valuation_assumption_set: Mapped[ValuationAssumptionSet] = relationship(
        back_populates="valuation_runs"
    )
    result: Mapped["ValuationResult | None"] = relationship(
        back_populates="valuation_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    overrides: Mapped[list["AssessmentOverride"]] = relationship(
        back_populates="valuation_run",
        order_by="AssessmentOverride.created_at.desc()",
    )
    audit_exports: Mapped[list["AuditExport"]] = relationship(
        back_populates="valuation_run",
        order_by="AuditExport.created_at.desc()",
    )


class ValuationResult(Base):
    __tablename__ = "valuation_result"
    __table_args__ = (UniqueConstraint("valuation_run_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    valuation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("valuation_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    post_permission_value_low: Mapped[float | None] = mapped_column(Float)
    post_permission_value_mid: Mapped[float | None] = mapped_column(Float)
    post_permission_value_high: Mapped[float | None] = mapped_column(Float)
    uplift_low: Mapped[float | None] = mapped_column(Float)
    uplift_mid: Mapped[float | None] = mapped_column(Float)
    uplift_high: Mapped[float | None] = mapped_column(Float)
    expected_uplift_mid: Mapped[float | None] = mapped_column(Float)
    valuation_quality: Mapped[ValuationQuality] = mapped_column(
        Enum(ValuationQuality, name="valuation_quality"),
        nullable=False,
        default=ValuationQuality.LOW,
    )
    manual_review_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    basis_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    sense_check_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )

    valuation_run: Mapped[ValuationRun] = relationship(back_populates="result")


class AuthUser(Base):
    __tablename__ = "auth_user"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_auth_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="supabase")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    role_links: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AppRole(Base):
    __tablename__ = "app_role"

    name: Mapped[AppRoleName] = mapped_column(
        Enum(AppRoleName, name="app_role_name"),
        primary_key=True,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)

    user_links: Mapped[list["UserRole"]] = relationship(back_populates="role")


class UserRole(Base):
    __tablename__ = "user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("auth_user.id", ondelete="CASCADE"))
    role_name: Mapped[AppRoleName] = mapped_column(
        Enum(AppRoleName, name="app_role_name", create_type=False),
        ForeignKey("app_role.name", ondelete="CASCADE"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    user: Mapped[AuthUser] = relationship(back_populates="role_links")
    role: Mapped[AppRole] = relationship(back_populates="user_links")


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("auth_user.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    before_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )


class JobRun(Base):
    __tablename__ = "job_run"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    job_type: Mapped[JobType] = mapped_column(Enum(JobType, name="job_type"), nullable=False)
    payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"),
        nullable=False,
        default=JobStatus.QUEUED,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(255))
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )
    requested_by: Mapped[str | None] = mapped_column(String(255))


Index("ix_job_run_status_next_run_at", JobRun.status, JobRun.next_run_at)
Index("ix_source_snapshot_source_uri", SourceSnapshot.source_uri)
Index("ix_source_snapshot_source_name", SourceSnapshot.source_name)
Index("ix_raw_asset_source_snapshot_id", RawAsset.source_snapshot_id)
Index(
    "ix_source_coverage_snapshot_borough_family_captured",
    SourceCoverageSnapshot.borough_id,
    SourceCoverageSnapshot.source_family,
    SourceCoverageSnapshot.captured_at,
)
Index("ix_listing_item_canonical_url", ListingItem.canonical_url)
Index("ix_listing_item_source_last_seen", ListingItem.source_id, ListingItem.last_seen_at)
Index("ix_listing_item_latest_status", ListingItem.latest_status)
Index(
    "ix_listing_snapshot_listing_item_observed",
    ListingSnapshot.listing_item_id,
    ListingSnapshot.observed_at,
)
Index("ix_listing_snapshot_source_snapshot_id", ListingSnapshot.source_snapshot_id)
Index("ix_listing_document_listing_item_id", ListingDocument.listing_item_id)
Index("ix_listing_cluster_status", ListingCluster.cluster_status)
Index("ix_listing_cluster_member_cluster", ListingClusterMember.listing_cluster_id)
Index("ix_lpa_boundary_external_ref", LpaBoundary.external_ref)
Index("ix_hmlr_title_polygon_title_number", HmlrTitlePolygon.title_number)
Index("ix_hmlr_title_polygon_normalized_address", HmlrTitlePolygon.normalized_address)
Index("ix_site_candidate_borough_id", SiteCandidate.borough_id)
Index("ix_site_candidate_status", SiteCandidate.site_status)
Index(
    "ix_site_geometry_revision_site_created",
    SiteGeometryRevision.site_id,
    SiteGeometryRevision.created_at,
)
Index("ix_site_title_link_site_id", SiteTitleLink.site_id)
Index("ix_site_lpa_link_site_id", SiteLpaLink.site_id)
Index("ix_site_market_event_site_event_at", SiteMarketEvent.site_id, SiteMarketEvent.event_at)
Index("ix_planning_application_borough_id", PlanningApplication.borough_id)
Index("ix_planning_application_external_ref", PlanningApplication.external_ref)
Index("ix_planning_application_status", PlanningApplication.status)
Index("ix_planning_application_valid_date", PlanningApplication.valid_date)
Index("ix_planning_application_decision_date", PlanningApplication.decision_date)
Index(
    "ix_planning_application_source_system_priority",
    PlanningApplication.source_system,
    PlanningApplication.source_priority,
)
Index(
    "ix_planning_application_document_application_id",
    PlanningApplicationDocument.planning_application_id,
)
Index("ix_site_planning_link_site_id", SitePlanningLink.site_id)
Index("ix_site_planning_link_application_id", SitePlanningLink.planning_application_id)
Index("ix_brownfield_site_state_borough_id", BrownfieldSiteState.borough_id)
Index("ix_brownfield_site_state_external_ref", BrownfieldSiteState.external_ref)
Index("ix_brownfield_site_state_effective_to", BrownfieldSiteState.effective_to)
Index("ix_policy_area_borough_id", PolicyArea.borough_id)
Index("ix_policy_area_policy_code", PolicyArea.policy_code)
Index("ix_policy_area_effective_from", PolicyArea.legal_effective_from)
Index("ix_policy_area_effective_to", PolicyArea.legal_effective_to)
Index("ix_planning_constraint_feature_family", PlanningConstraintFeature.feature_family)
Index("ix_planning_constraint_feature_effective_to", PlanningConstraintFeature.effective_to)
Index("ix_site_policy_fact_site_id", SitePolicyFact.site_id)
Index("ix_site_constraint_fact_site_id", SiteConstraintFact.site_id)
Index("ix_borough_baseline_pack_borough_id", BoroughBaselinePack.borough_id)
Index("ix_borough_baseline_pack_status", BoroughBaselinePack.status)
Index("ix_borough_baseline_pack_freshness", BoroughBaselinePack.freshness_status)
Index(
    "ix_borough_rulepack_pack_template",
    BoroughRulepack.borough_baseline_pack_id,
    BoroughRulepack.template_key,
)
Index("ix_borough_rulepack_status", BoroughRulepack.status)
Index("ix_borough_rulepack_freshness", BoroughRulepack.freshness_status)
Index("ix_scenario_template_enabled", ScenarioTemplate.enabled)
Index("ix_scenario_template_key", ScenarioTemplate.key)
Index("ix_site_scenario_site_id", SiteScenario.site_id)
Index("ix_site_scenario_status", SiteScenario.status)
Index("ix_site_scenario_template_key", SiteScenario.template_key)
Index("ix_site_scenario_site_current", SiteScenario.site_id, SiteScenario.is_current)
Index("ix_site_scenario_site_headline", SiteScenario.site_id, SiteScenario.is_headline)
Index(
    "ix_site_scenario_geometry_revision_id",
    SiteScenario.site_geometry_revision_id,
)
Index("ix_scenario_review_scenario_id", ScenarioReview.scenario_id)
Index("ix_scenario_review_reviewed_at", ScenarioReview.reviewed_at)
Index(
    "ix_historical_case_label_borough_template_class",
    HistoricalCaseLabel.borough_id,
    HistoricalCaseLabel.template_key,
    HistoricalCaseLabel.label_class,
)
Index("ix_historical_case_label_review_status", HistoricalCaseLabel.review_status)
Index("ix_historical_case_label_decision_date", HistoricalCaseLabel.first_substantive_decision_date)
Index("ix_historical_case_label_valid_date", HistoricalCaseLabel.valid_date)
Index("ix_assessment_run_state", AssessmentRun.state)
Index("ix_assessment_run_site_as_of_date", AssessmentRun.site_id, AssessmentRun.as_of_date)
Index(
    "ix_assessment_run_scenario_as_of_date",
    AssessmentRun.scenario_id,
    AssessmentRun.as_of_date,
)
Index("ix_assessment_feature_snapshot_run_id", AssessmentFeatureSnapshot.assessment_run_id)
Index("ix_assessment_result_run_id", AssessmentResult.assessment_run_id)
Index("ix_comparable_case_set_run_id", ComparableCaseSet.assessment_run_id)
Index(
    "ix_comparable_case_member_set_outcome_rank",
    ComparableCaseMember.comparable_case_set_id,
    ComparableCaseMember.outcome,
    ComparableCaseMember.rank,
)
Index(
    "ix_evidence_item_run_polarity",
    EvidenceItem.assessment_run_id,
    EvidenceItem.polarity,
)
Index("ix_prediction_ledger_run_id", PredictionLedger.assessment_run_id)
Index(
    "ix_prediction_ledger_scope_created",
    PredictionLedger.release_scope_key,
    PredictionLedger.created_at,
)
Index(
    "ix_assessment_override_run_type_status",
    AssessmentOverride.assessment_run_id,
    AssessmentOverride.override_type,
    AssessmentOverride.status,
)
Index(
    "ix_assessment_override_actor_created",
    AssessmentOverride.actor_name,
    AssessmentOverride.created_at,
)
Index("ix_incident_record_scope_status", IncidentRecord.scope_key, IncidentRecord.status)
Index("ix_incident_record_created_at", IncidentRecord.created_at)
Index("ix_audit_export_run_created", AuditExport.assessment_run_id, AuditExport.created_at)
Index("ix_market_sale_comp_borough_sale_date", MarketSaleComp.borough_id, MarketSaleComp.sale_date)
Index("ix_market_sale_comp_postcode_district", MarketSaleComp.postcode_district)
Index(
    "ix_market_index_series_borough_period",
    MarketIndexSeries.borough_id,
    MarketIndexSeries.period_month,
)
Index(
    "ix_market_land_comp_borough_template_date",
    MarketLandComp.borough_id,
    MarketLandComp.template_key,
    MarketLandComp.evidence_date,
)
Index("ix_market_land_comp_source_type", MarketLandComp.comp_source_type)
Index("ix_valuation_assumption_set_effective_from", ValuationAssumptionSet.effective_from)
Index("ix_valuation_run_assessment_id", ValuationRun.assessment_run_id)
Index(
    "ix_valuation_run_assessment_assumptions",
    ValuationRun.assessment_run_id,
    ValuationRun.valuation_assumption_set_id,
)
Index("ix_valuation_result_run_id", ValuationResult.valuation_run_id)
