"""Phase 8A lineage integrity hardening.

Revision ID: 20260417_000010_phase8a_lineage_integrity
Revises: 20260415_000009_phase8a_controls_visibility
Create Date: 2026-04-17
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "20260417_000010_phase8a_lineage_integrity"
down_revision = "20260415_000009_phase8a_controls_visibility"
branch_labels = None
depends_on = None


def _site_cluster_fk_name(bind) -> str:
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("site_candidate"):
        if fk.get("referred_table") != "listing_cluster":
            continue
        if fk.get("constrained_columns") != ["listing_cluster_id"]:
            continue
        name = fk.get("name")
        if not name:
            break
        return name
    raise RuntimeError("Could not locate the site_candidate -> listing_cluster foreign key.")


def upgrade() -> None:
    bind = op.get_bind()
    fk_name = _site_cluster_fk_name(bind)
    op.drop_constraint(fk_name, "site_candidate", type_="foreignkey")
    op.create_foreign_key(
        "fk_site_candidate_listing_cluster",
        "site_candidate",
        "listing_cluster",
        ["listing_cluster_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    with op.batch_alter_table("site_lpa_link") as batch_op:
        batch_op.add_column(sa.Column("source_snapshot_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_site_lpa_link_source_snapshot",
            "source_snapshot",
            ["source_snapshot_id"],
            ["id"],
        )

    with op.batch_alter_table("site_planning_link") as batch_op:
        batch_op.add_column(sa.Column("source_snapshot_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("application_snapshot_json", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_site_planning_link_source_snapshot",
            "source_snapshot",
            ["source_snapshot_id"],
            ["id"],
        )

    with op.batch_alter_table("site_policy_fact") as batch_op:
        batch_op.add_column(sa.Column("source_snapshot_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("policy_area_snapshot_json", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_site_policy_fact_source_snapshot",
            "source_snapshot",
            ["source_snapshot_id"],
            ["id"],
        )

    with op.batch_alter_table("site_constraint_fact") as batch_op:
        batch_op.add_column(sa.Column("source_snapshot_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("constraint_snapshot_json", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_site_constraint_fact_source_snapshot",
            "source_snapshot",
            ["source_snapshot_id"],
            ["id"],
        )

    op.execute(
        sa.text(
            """
            UPDATE site_lpa_link
            SET source_snapshot_id = (
                SELECT lpa_boundary.source_snapshot_id
                FROM lpa_boundary
                WHERE lpa_boundary.id = site_lpa_link.lpa_id
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE site_planning_link
            SET source_snapshot_id = (
                SELECT planning_application.source_snapshot_id
                FROM planning_application
                WHERE planning_application.id = site_planning_link.planning_application_id
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE site_policy_fact
            SET source_snapshot_id = (
                SELECT policy_area.source_snapshot_id
                FROM policy_area
                WHERE policy_area.id = site_policy_fact.policy_area_id
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE site_constraint_fact
            SET source_snapshot_id = (
                SELECT planning_constraint_feature.source_snapshot_id
                FROM planning_constraint_feature
                WHERE planning_constraint_feature.id = site_constraint_fact.constraint_feature_id
            )
            """
        )
    )
    _backfill_site_context_snapshots(bind)

    with op.batch_alter_table("site_lpa_link") as batch_op:
        batch_op.alter_column("source_snapshot_id", nullable=False)

    with op.batch_alter_table("site_planning_link") as batch_op:
        batch_op.alter_column("source_snapshot_id", nullable=False)

    with op.batch_alter_table("site_policy_fact") as batch_op:
        batch_op.alter_column("source_snapshot_id", nullable=False)

    with op.batch_alter_table("site_constraint_fact") as batch_op:
        batch_op.alter_column("source_snapshot_id", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("site_constraint_fact") as batch_op:
        batch_op.drop_constraint("fk_site_constraint_fact_source_snapshot", type_="foreignkey")
        batch_op.drop_column("constraint_snapshot_json")
        batch_op.drop_column("source_snapshot_id")

    with op.batch_alter_table("site_policy_fact") as batch_op:
        batch_op.drop_constraint("fk_site_policy_fact_source_snapshot", type_="foreignkey")
        batch_op.drop_column("policy_area_snapshot_json")
        batch_op.drop_column("source_snapshot_id")

    with op.batch_alter_table("site_planning_link") as batch_op:
        batch_op.drop_constraint("fk_site_planning_link_source_snapshot", type_="foreignkey")
        batch_op.drop_column("application_snapshot_json")
        batch_op.drop_column("source_snapshot_id")

    with op.batch_alter_table("site_lpa_link") as batch_op:
        batch_op.drop_constraint("fk_site_lpa_link_source_snapshot", type_="foreignkey")
        batch_op.drop_column("source_snapshot_id")

    op.drop_constraint("fk_site_candidate_listing_cluster", "site_candidate", type_="foreignkey")
    op.create_foreign_key(
        "fk_site_candidate_listing_cluster",
        "site_candidate",
        "listing_cluster",
        ["listing_cluster_id"],
        ["id"],
        ondelete="CASCADE",
    )


def _backfill_site_context_snapshots(bind) -> None:
    planning_rows = bind.execute(
        sa.text(
            """
            SELECT
                spl.id AS link_id,
                pa.id AS application_id,
                pa.borough_id,
                pa.source_system,
                pa.source_snapshot_id,
                pa.external_ref,
                pa.application_type,
                pa.proposal_description,
                pa.valid_date,
                pa.decision_date,
                pa.decision,
                pa.decision_type,
                pa.status,
                pa.route_normalized,
                pa.units_proposed,
                pa.source_priority,
                pa.source_url,
                pa.site_geom_4326,
                pa.site_point_4326,
                pa.raw_record_json
            FROM site_planning_link spl
            JOIN planning_application pa ON pa.id = spl.planning_application_id
            """
        )
    ).mappings()
    for row in planning_rows:
        payload = {
            "id": str(row["application_id"]),
            "borough_id": row["borough_id"],
            "source_system": row["source_system"],
            "source_snapshot_id": str(row["source_snapshot_id"]),
            "external_ref": row["external_ref"],
            "application_type": row["application_type"],
            "proposal_description": row["proposal_description"],
            "valid_date": None if row["valid_date"] is None else row["valid_date"].isoformat(),
            "decision_date": (
                None if row["decision_date"] is None else row["decision_date"].isoformat()
            ),
            "decision": row["decision"],
            "decision_type": row["decision_type"],
            "status": row["status"],
            "route_normalized": row["route_normalized"],
            "units_proposed": row["units_proposed"],
            "source_priority": row["source_priority"],
            "source_url": row["source_url"],
            "site_geom_4326": row["site_geom_4326"],
            "site_point_4326": row["site_point_4326"],
            "raw_record_json": row["raw_record_json"] or {},
        }
        bind.execute(
            sa.text(
                """
                UPDATE site_planning_link
                SET application_snapshot_json = :payload
                WHERE id = :link_id
                """
            ),
            {"link_id": row["link_id"], "payload": json.dumps(payload, default=str)},
        )

    policy_rows = bind.execute(
        sa.text(
            """
            SELECT
                spf.id AS fact_id,
                pa.id AS policy_area_id,
                pa.borough_id,
                pa.policy_family,
                pa.policy_code,
                pa.name,
                pa.geom_4326,
                pa.legal_effective_from,
                pa.legal_effective_to,
                pa.source_snapshot_id,
                pa.source_class,
                pa.source_url,
                pa.raw_record_json
            FROM site_policy_fact spf
            JOIN policy_area pa ON pa.id = spf.policy_area_id
            """
        )
    ).mappings()
    for row in policy_rows:
        payload = {
            "id": str(row["policy_area_id"]),
            "borough_id": row["borough_id"],
            "policy_family": row["policy_family"],
            "policy_code": row["policy_code"],
            "name": row["name"],
            "geom_4326": row["geom_4326"],
            "legal_effective_from": (
                None
                if row["legal_effective_from"] is None
                else row["legal_effective_from"].isoformat()
            ),
            "legal_effective_to": (
                None if row["legal_effective_to"] is None else row["legal_effective_to"].isoformat()
            ),
            "source_snapshot_id": str(row["source_snapshot_id"]),
            "source_class": row["source_class"],
            "source_url": row["source_url"],
            "raw_record_json": row["raw_record_json"] or {},
        }
        bind.execute(
            sa.text(
                """
                UPDATE site_policy_fact
                SET policy_area_snapshot_json = :payload
                WHERE id = :fact_id
                """
            ),
            {"fact_id": row["fact_id"], "payload": json.dumps(payload, default=str)},
        )

    constraint_rows = bind.execute(
        sa.text(
            """
            SELECT
                scf.id AS fact_id,
                pcf.id AS feature_id,
                pcf.feature_family,
                pcf.feature_subtype,
                pcf.authority_level,
                pcf.geom_4326,
                pcf.legal_status,
                pcf.effective_from,
                pcf.effective_to,
                pcf.source_snapshot_id,
                pcf.source_class,
                pcf.source_url,
                pcf.raw_record_json
            FROM site_constraint_fact scf
            JOIN planning_constraint_feature pcf ON pcf.id = scf.constraint_feature_id
            """
        )
    ).mappings()
    for row in constraint_rows:
        payload = {
            "id": str(row["feature_id"]),
            "feature_family": row["feature_family"],
            "feature_subtype": row["feature_subtype"],
            "authority_level": row["authority_level"],
            "geom_4326": row["geom_4326"],
            "legal_status": row["legal_status"],
            "effective_from": (
                None if row["effective_from"] is None else row["effective_from"].isoformat()
            ),
            "effective_to": (
                None if row["effective_to"] is None else row["effective_to"].isoformat()
            ),
            "source_snapshot_id": str(row["source_snapshot_id"]),
            "source_class": row["source_class"],
            "source_url": row["source_url"],
            "raw_record_json": row["raw_record_json"] or {},
        }
        bind.execute(
            sa.text(
                """
                UPDATE site_constraint_fact
                SET constraint_snapshot_json = :payload
                WHERE id = :fact_id
                """
            ),
            {"fact_id": row["fact_id"], "payload": json.dumps(payload, default=str)},
        )
