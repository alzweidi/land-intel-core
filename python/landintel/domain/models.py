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
    BaselinePackStatus,
    ComplianceMode,
    ConnectorType,
    DocumentExtractionStatus,
    DocumentType,
    EvidenceImportance,
    GeomConfidence,
    GeomSourceType,
    JobStatus,
    JobType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
    SiteMarketEventType,
    SiteStatus,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
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
        ForeignKey("listing_cluster.id", ondelete="CASCADE"),
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
