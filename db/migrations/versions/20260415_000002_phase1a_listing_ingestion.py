"""Phase 1A listing ingestion and clustering schema."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    DocumentExtractionStatus,
    DocumentType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SourceParseStatus,
)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000002"
down_revision = "20260415_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        connector_type = postgresql.ENUM(ConnectorType, name="connector_type")
        compliance_mode = postgresql.ENUM(ComplianceMode, name="compliance_mode")
        source_parse_status = postgresql.ENUM(SourceParseStatus, name="source_parse_status")
        listing_type = postgresql.ENUM(ListingType, name="listing_type")
        listing_status = postgresql.ENUM(ListingStatus, name="listing_status")
        price_basis_type = postgresql.ENUM(PriceBasisType, name="price_basis_type")
        document_type = postgresql.ENUM(DocumentType, name="document_type")
        document_extraction_status = postgresql.ENUM(
            DocumentExtractionStatus,
            name="document_extraction_status",
        )
        listing_cluster_status = postgresql.ENUM(
            ListingClusterStatus,
            name="listing_cluster_status",
        )
        connector_type_ref = postgresql.ENUM(
            ConnectorType,
            name="connector_type",
            create_type=False,
        )
        compliance_mode_ref = postgresql.ENUM(
            ComplianceMode,
            name="compliance_mode",
            create_type=False,
        )
        source_parse_status_ref = postgresql.ENUM(
            SourceParseStatus,
            name="source_parse_status",
            create_type=False,
        )
        listing_type_ref = postgresql.ENUM(
            ListingType,
            name="listing_type",
            create_type=False,
        )
        listing_status_ref = postgresql.ENUM(
            ListingStatus,
            name="listing_status",
            create_type=False,
        )
        price_basis_type_ref = postgresql.ENUM(
            PriceBasisType,
            name="price_basis_type",
            create_type=False,
        )
        document_type_ref = postgresql.ENUM(
            DocumentType,
            name="document_type",
            create_type=False,
        )
        document_extraction_status_ref = postgresql.ENUM(
            DocumentExtractionStatus,
            name="document_extraction_status",
            create_type=False,
        )
        listing_cluster_status_ref = postgresql.ENUM(
            ListingClusterStatus,
            name="listing_cluster_status",
            create_type=False,
        )
    else:
        connector_type = sa.Enum(ConnectorType, name="connector_type")
        compliance_mode = sa.Enum(ComplianceMode, name="compliance_mode")
        source_parse_status = sa.Enum(SourceParseStatus, name="source_parse_status")
        listing_type = sa.Enum(ListingType, name="listing_type")
        listing_status = sa.Enum(ListingStatus, name="listing_status")
        price_basis_type = sa.Enum(PriceBasisType, name="price_basis_type")
        document_type = sa.Enum(DocumentType, name="document_type")
        document_extraction_status = sa.Enum(
            DocumentExtractionStatus,
            name="document_extraction_status",
        )
        listing_cluster_status = sa.Enum(
            ListingClusterStatus,
            name="listing_cluster_status",
        )
        connector_type_ref = connector_type
        compliance_mode_ref = compliance_mode
        source_parse_status_ref = source_parse_status
        listing_type_ref = listing_type
        listing_status_ref = listing_status
        price_basis_type_ref = price_basis_type
        document_type_ref = document_type
        document_extraction_status_ref = document_extraction_status
        listing_cluster_status_ref = listing_cluster_status

    if is_postgres:
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'CSV_IMPORT_SNAPSHOT'")
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'LISTING_SOURCE_RUN'")
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'LISTING_CLUSTER_REBUILD'")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    connector_type.create(bind, checkfirst=True)
    compliance_mode.create(bind, checkfirst=True)
    source_parse_status.create(bind, checkfirst=True)
    listing_type.create(bind, checkfirst=True)
    listing_status.create(bind, checkfirst=True)
    price_basis_type.create(bind, checkfirst=True)
    document_type.create(bind, checkfirst=True)
    document_extraction_status.create(bind, checkfirst=True)
    listing_cluster_status.create(bind, checkfirst=True)

    op.add_column(
        "source_snapshot",
        sa.Column(
            "parse_status",
            source_parse_status_ref,
            nullable=False,
            server_default=SourceParseStatus.PENDING.value,
        ),
    )
    op.add_column("source_snapshot", sa.Column("parse_error_text", sa.Text(), nullable=True))

    op.create_table(
        "listing_source",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("connector_type", connector_type_ref, nullable=False),
        sa.Column("compliance_mode", compliance_mode_ref, nullable=False),
        sa.Column("refresh_policy_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "listing_item",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("listing_source.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_listing_id", sa.String(length=255), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("listing_type", listing_type_ref, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_status", listing_status_ref, nullable=False),
        sa.Column("current_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("normalized_address", sa.String(length=500), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.UniqueConstraint("source_id", "source_listing_id"),
    )
    op.create_index("ix_listing_item_canonical_url", "listing_item", ["canonical_url"])
    op.create_index(
        "ix_listing_item_source_last_seen",
        "listing_item",
        ["source_id", "last_seen_at"],
    )
    op.create_index("ix_listing_item_latest_status", "listing_item", ["latest_status"])

    op.create_table(
        "listing_snapshot",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "listing_item_id",
            sa.Uuid(),
            sa.ForeignKey("listing_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("guide_price_gbp", sa.BigInteger(), nullable=True),
        sa.Column("price_basis_type", price_basis_type_ref, nullable=False),
        sa.Column("status", listing_status_ref, nullable=False),
        sa.Column("auction_date", sa.Date(), nullable=True),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("normalized_address", sa.String(length=500), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column(
            "brochure_asset_id",
            sa.Uuid(),
            sa.ForeignKey("raw_asset.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "map_asset_id",
            sa.Uuid(),
            sa.ForeignKey("raw_asset.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_record_json", sa.JSON(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_listing_snapshot_listing_item_observed",
        "listing_snapshot",
        ["listing_item_id", "observed_at"],
    )
    op.create_index(
        "ix_listing_snapshot_source_snapshot_id",
        "listing_snapshot",
        ["source_snapshot_id"],
    )

    op.create_table(
        "listing_document",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "listing_item_id",
            sa.Uuid(),
            sa.ForeignKey("listing_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("raw_asset.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_type", document_type_ref, nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_status", document_extraction_status_ref, nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("asset_id"),
    )
    op.create_index("ix_listing_document_listing_item_id", "listing_document", ["listing_item_id"])

    op.create_table(
        "listing_cluster",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("cluster_key", sa.String(length=255), nullable=False),
        sa.Column("cluster_status", listing_cluster_status_ref, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cluster_key"),
    )
    op.create_index("ix_listing_cluster_status", "listing_cluster", ["cluster_status"])

    op.create_table(
        "listing_cluster_member",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "listing_cluster_id",
            sa.Uuid(),
            sa.ForeignKey("listing_cluster.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "listing_item_id",
            sa.Uuid(),
            sa.ForeignKey("listing_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("listing_cluster_id", "listing_item_id"),
        sa.UniqueConstraint("listing_item_id"),
    )
    op.create_index(
        "ix_listing_cluster_member_cluster",
        "listing_cluster_member",
        ["listing_cluster_id"],
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_listing_item_search_trgm "
            "ON listing_item USING GIN (search_text gin_trgm_ops)"
        )

    op.bulk_insert(
        sa.table(
            "listing_source",
            sa.column("id", sa.Uuid()),
            sa.column("name", sa.String(length=255)),
            sa.column("connector_type", connector_type_ref),
            sa.column("compliance_mode", compliance_mode_ref),
            sa.column("refresh_policy_json", sa.JSON()),
            sa.column("active", sa.Boolean()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": uuid.UUID("0d3576fc-3d3f-4b0a-bf7b-2cc184b99f0d"),
                "name": "manual_url",
                "connector_type": ConnectorType.MANUAL_URL.value,
                "compliance_mode": ComplianceMode.MANUAL_ONLY.value,
                "refresh_policy_json": {"run_mode": "manual"},
                "active": True,
                "created_at": datetime.now(UTC),
            },
            {
                "id": uuid.UUID("f539a9b8-757c-4df2-95b9-6f4c48e8d88e"),
                "name": "csv_import",
                "connector_type": ConnectorType.CSV_IMPORT.value,
                "compliance_mode": ComplianceMode.CSV_ONLY.value,
                "refresh_policy_json": {"run_mode": "manual"},
                "active": True,
                "created_at": datetime.now(UTC),
            },
            {
                "id": uuid.UUID("3769d0fc-5b30-4c6b-97de-58dc7aa3de6d"),
                "name": "example_public_page",
                "connector_type": ConnectorType.PUBLIC_PAGE.value,
                "compliance_mode": ComplianceMode.COMPLIANT_AUTOMATED.value,
                "refresh_policy_json": {
                    "seed_urls": ["https://example.com"],
                    "max_listings": 1,
                },
                "active": True,
                "created_at": datetime.now(UTC),
            },
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.execute(
        "DELETE FROM listing_source "
        "WHERE name IN ('manual_url', 'csv_import', 'example_public_page')"
    )
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_listing_item_search_trgm")

    op.drop_index("ix_listing_cluster_member_cluster", table_name="listing_cluster_member")
    op.drop_table("listing_cluster_member")
    op.drop_index("ix_listing_cluster_status", table_name="listing_cluster")
    op.drop_table("listing_cluster")
    op.drop_index("ix_listing_document_listing_item_id", table_name="listing_document")
    op.drop_table("listing_document")
    op.drop_index("ix_listing_snapshot_source_snapshot_id", table_name="listing_snapshot")
    op.drop_index("ix_listing_snapshot_listing_item_observed", table_name="listing_snapshot")
    op.drop_table("listing_snapshot")
    op.drop_index("ix_listing_item_latest_status", table_name="listing_item")
    op.drop_index("ix_listing_item_source_last_seen", table_name="listing_item")
    op.drop_index("ix_listing_item_canonical_url", table_name="listing_item")
    op.drop_table("listing_item")
    op.drop_table("listing_source")
    op.drop_column("source_snapshot", "parse_error_text")
    op.drop_column("source_snapshot", "parse_status")

    if is_postgres:
        listing_cluster_status = postgresql.ENUM(
            ListingClusterStatus,
            name="listing_cluster_status",
        )
        document_extraction_status = postgresql.ENUM(
            DocumentExtractionStatus,
            name="document_extraction_status",
        )
        document_type = postgresql.ENUM(DocumentType, name="document_type")
        price_basis_type = postgresql.ENUM(PriceBasisType, name="price_basis_type")
        listing_status = postgresql.ENUM(ListingStatus, name="listing_status")
        listing_type = postgresql.ENUM(ListingType, name="listing_type")
        source_parse_status = postgresql.ENUM(SourceParseStatus, name="source_parse_status")
        compliance_mode = postgresql.ENUM(ComplianceMode, name="compliance_mode")
        connector_type = postgresql.ENUM(ConnectorType, name="connector_type")
    else:
        listing_cluster_status = sa.Enum(ListingClusterStatus, name="listing_cluster_status")
        document_extraction_status = sa.Enum(
            DocumentExtractionStatus,
            name="document_extraction_status",
        )
        document_type = sa.Enum(DocumentType, name="document_type")
        price_basis_type = sa.Enum(PriceBasisType, name="price_basis_type")
        listing_status = sa.Enum(ListingStatus, name="listing_status")
        listing_type = sa.Enum(ListingType, name="listing_type")
        source_parse_status = sa.Enum(SourceParseStatus, name="source_parse_status")
        compliance_mode = sa.Enum(ComplianceMode, name="compliance_mode")
        connector_type = sa.Enum(ConnectorType, name="connector_type")

    listing_cluster_status.drop(bind, checkfirst=True)
    document_extraction_status.drop(bind, checkfirst=True)
    document_type.drop(bind, checkfirst=True)
    price_basis_type.drop(bind, checkfirst=True)
    listing_status.drop(bind, checkfirst=True)
    listing_type.drop(bind, checkfirst=True)
    source_parse_status.drop(bind, checkfirst=True)
    compliance_mode.drop(bind, checkfirst=True)
    connector_type.drop(bind, checkfirst=True)
