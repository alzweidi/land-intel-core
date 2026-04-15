"""Phase 2 site geometry, reference data, and linkage schema."""

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import (
    GeomConfidence,
    GeomSourceType,
    PriceBasisType,
    SiteMarketEventType,
    SiteStatus,
)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000003"
down_revision = "20260415_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        geom_source_type = postgresql.ENUM(GeomSourceType, name="geom_source_type")
        geom_confidence = postgresql.ENUM(GeomConfidence, name="geom_confidence")
        site_status = postgresql.ENUM(SiteStatus, name="site_status")
        site_market_event_type = postgresql.ENUM(
            SiteMarketEventType,
            name="site_market_event_type",
        )
        price_basis_type_ref = postgresql.ENUM(
            PriceBasisType,
            name="price_basis_type",
            create_type=False,
        )
        geom_source_type_ref = postgresql.ENUM(
            GeomSourceType,
            name="geom_source_type",
            create_type=False,
        )
        geom_confidence_ref = postgresql.ENUM(
            GeomConfidence,
            name="geom_confidence",
            create_type=False,
        )
        site_status_ref = postgresql.ENUM(
            SiteStatus,
            name="site_status",
            create_type=False,
        )
        site_market_event_type_ref = postgresql.ENUM(
            SiteMarketEventType,
            name="site_market_event_type",
            create_type=False,
        )
    else:
        geom_source_type = sa.Enum(GeomSourceType, name="geom_source_type")
        geom_confidence = sa.Enum(GeomConfidence, name="geom_confidence")
        site_status = sa.Enum(SiteStatus, name="site_status")
        site_market_event_type = sa.Enum(SiteMarketEventType, name="site_market_event_type")
        price_basis_type_ref = sa.Enum(PriceBasisType, name="price_basis_type")
        geom_source_type_ref = geom_source_type
        geom_confidence_ref = geom_confidence
        site_status_ref = site_status
        site_market_event_type_ref = site_market_event_type

    if is_postgres:
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'SITE_BUILD_REFRESH'")
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'SITE_LPA_LINK_REFRESH'")
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'SITE_TITLE_LINK_REFRESH'")
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    geom_source_type.create(bind, checkfirst=True)
    geom_confidence.create(bind, checkfirst=True)
    site_status.create(bind, checkfirst=True)
    site_market_event_type.create(bind, checkfirst=True)

    op.create_table(
        "lpa_boundary",
        sa.Column("id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("external_ref", sa.String(length=100), nullable=True),
        sa.Column("authority_level", sa.String(length=50), nullable=False),
        sa.Column("geom_27700", sa.Text(), nullable=False),
        sa.Column("geom_4326", sa.JSON(), nullable=False),
        sa.Column("geom_hash", sa.String(length=64), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_ref"),
    )
    op.create_index("ix_lpa_boundary_external_ref", "lpa_boundary", ["external_ref"])

    op.create_table(
        "hmlr_title_polygon",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("title_number", sa.String(length=100), nullable=False),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("normalized_address", sa.String(length=500), nullable=True),
        sa.Column("geom_27700", sa.Text(), nullable=False),
        sa.Column("geom_4326", sa.JSON(), nullable=False),
        sa.Column("geom_hash", sa.String(length=64), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hmlr_title_polygon_title_number", "hmlr_title_polygon", ["title_number"])
    op.create_index(
        "ix_hmlr_title_polygon_normalized_address",
        "hmlr_title_polygon",
        ["normalized_address"],
    )

    op.create_table(
        "site_candidate",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "listing_cluster_id",
            sa.Uuid(),
            sa.ForeignKey("listing_cluster.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "borough_id",
            sa.String(length=100),
            sa.ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("geom_27700", sa.Text(), nullable=False),
        sa.Column("geom_4326", sa.JSON(), nullable=False),
        sa.Column("geom_hash", sa.String(length=64), nullable=False),
        sa.Column("geom_source_type", geom_source_type_ref, nullable=False),
        sa.Column("geom_confidence", geom_confidence_ref, nullable=False),
        sa.Column("site_area_sqm", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "current_listing_id",
            sa.Uuid(),
            sa.ForeignKey("listing_item.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("current_price_gbp", sa.BigInteger(), nullable=True),
        sa.Column(
            "current_price_basis_type",
            price_basis_type_ref,
            nullable=False,
            server_default=PriceBasisType.UNKNOWN.value,
        ),
        sa.Column(
            "site_status",
            site_status_ref,
            nullable=False,
            server_default=SiteStatus.DRAFT.value,
        ),
        sa.Column(
            "manual_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("warning_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("listing_cluster_id"),
    )
    op.create_index("ix_site_candidate_borough_id", "site_candidate", ["borough_id"])
    op.create_index("ix_site_candidate_status", "site_candidate", ["site_status"])

    op.create_table(
        "site_geometry_revision",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("geom_27700", sa.Text(), nullable=False),
        sa.Column("geom_4326", sa.JSON(), nullable=False),
        sa.Column("geom_hash", sa.String(length=64), nullable=False),
        sa.Column("source_type", geom_source_type_ref, nullable=False),
        sa.Column("confidence", geom_confidence_ref, nullable=False),
        sa.Column("site_area_sqm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_asset_id",
            sa.Uuid(),
            sa.ForeignKey("raw_asset.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("warning_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "ix_site_geometry_revision_site_created",
        "site_geometry_revision",
        ["site_id", "created_at"],
    )

    op.create_table(
        "site_title_link",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "title_polygon_id",
            sa.Uuid(),
            sa.ForeignKey("hmlr_title_polygon.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title_number", sa.String(length=100), nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("overlap_pct", sa.Float(), nullable=False),
        sa.Column("overlap_sqm", sa.Float(), nullable=False),
        sa.Column("confidence", geom_confidence_ref, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("site_id", "title_number"),
    )
    op.create_index("ix_site_title_link_site_id", "site_title_link", ["site_id"])

    op.create_table(
        "site_lpa_link",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lpa_id",
            sa.String(length=100),
            sa.ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("overlap_pct", sa.Float(), nullable=False),
        sa.Column("overlap_sqm", sa.Float(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("site_id", "lpa_id"),
    )
    op.create_index("ix_site_lpa_link_site_id", "site_lpa_link", ["site_id"])

    op.create_table(
        "site_market_event",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", site_market_event_type_ref, nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_gbp", sa.BigInteger(), nullable=True),
        sa.Column("basis_type", price_basis_type_ref, nullable=False),
        sa.Column(
            "listing_item_id",
            sa.Uuid(),
            sa.ForeignKey("listing_item.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_site_market_event_site_event_at",
        "site_market_event",
        ["site_id", "event_at"],
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_lpa_boundary_geom_27700_gist "
            "ON lpa_boundary USING GIST (ST_GeomFromText(geom_27700, 27700))"
        )
        op.execute(
            "CREATE INDEX ix_hmlr_title_polygon_geom_27700_gist "
            "ON hmlr_title_polygon USING GIST (ST_GeomFromText(geom_27700, 27700))"
        )
        op.execute(
            "CREATE INDEX ix_site_candidate_geom_27700_gist "
            "ON site_candidate USING GIST (ST_GeomFromText(geom_27700, 27700))"
        )
        op.execute(
            "CREATE INDEX ix_site_geometry_revision_geom_27700_gist "
            "ON site_geometry_revision USING GIST (ST_GeomFromText(geom_27700, 27700))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_site_geometry_revision_geom_27700_gist")
        op.execute("DROP INDEX IF EXISTS ix_site_candidate_geom_27700_gist")
        op.execute("DROP INDEX IF EXISTS ix_hmlr_title_polygon_geom_27700_gist")
        op.execute("DROP INDEX IF EXISTS ix_lpa_boundary_geom_27700_gist")

    op.drop_index("ix_site_market_event_site_event_at", table_name="site_market_event")
    op.drop_table("site_market_event")

    op.drop_index("ix_site_lpa_link_site_id", table_name="site_lpa_link")
    op.drop_table("site_lpa_link")

    op.drop_index("ix_site_title_link_site_id", table_name="site_title_link")
    op.drop_table("site_title_link")

    op.drop_index(
        "ix_site_geometry_revision_site_created",
        table_name="site_geometry_revision",
    )
    op.drop_table("site_geometry_revision")

    op.drop_index("ix_site_candidate_status", table_name="site_candidate")
    op.drop_index("ix_site_candidate_borough_id", table_name="site_candidate")
    op.drop_table("site_candidate")

    op.drop_index(
        "ix_hmlr_title_polygon_normalized_address",
        table_name="hmlr_title_polygon",
    )
    op.drop_index("ix_hmlr_title_polygon_title_number", table_name="hmlr_title_polygon")
    op.drop_table("hmlr_title_polygon")

    op.drop_index("ix_lpa_boundary_external_ref", table_name="lpa_boundary")
    op.drop_table("lpa_boundary")

    geom_source_type = sa.Enum(GeomSourceType, name="geom_source_type")
    geom_confidence = sa.Enum(GeomConfidence, name="geom_confidence")
    site_status = sa.Enum(SiteStatus, name="site_status")
    site_market_event_type = sa.Enum(SiteMarketEventType, name="site_market_event_type")

    geom_source_type.drop(bind, checkfirst=True)
    geom_confidence.drop(bind, checkfirst=True)
    site_status.drop(bind, checkfirst=True)
    site_market_event_type.drop(bind, checkfirst=True)
