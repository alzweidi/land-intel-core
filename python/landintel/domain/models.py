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
