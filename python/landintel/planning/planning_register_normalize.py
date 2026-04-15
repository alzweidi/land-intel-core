from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from landintel.domain.enums import SourceFreshnessStatus
from landintel.storage.base import StorageAdapter

from .constants import (
    SOURCE_FAMILY_BOROUGH_REGISTER,
    SOURCE_FAMILY_PRIOR_APPROVAL,
)
from .import_common import (
    PlanningImportResult,
    dataset_meta,
    register_dataset_snapshot,
    upsert_coverage_snapshots,
    upsert_planning_application_rows,
)


def import_borough_register_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "borough_planning_register_fixture",
) -> PlanningImportResult:
    snapshot, asset, payload = register_dataset_snapshot(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="borough_register",
        source_family=SOURCE_FAMILY_BOROUGH_REGISTER,
        source_name=source_name,
        schema_key="phase3a:borough-register:applications:v1",
        coverage_note=(
            "Pilot borough planning-register fixture import for Phase 3A local/dev. "
            "Borough data is the authority of record where present."
        ),
        freshness_status=SourceFreshnessStatus.FRESH,
        requested_by=requested_by,
    )
    meta = dataset_meta(payload)
    snapshot.coverage_note = str(meta.get("coverage_note") or snapshot.coverage_note)
    snapshot.freshness_status = SourceFreshnessStatus(
        str(meta.get("freshness_status") or snapshot.freshness_status.value)
    )
    coverage_rows = list(meta.get("coverage") or [])
    has_prior_approval_coverage = any(
        str(row.get("source_family")) == SOURCE_FAMILY_PRIOR_APPROVAL
        for row in coverage_rows
    )
    if not has_prior_approval_coverage:
        for row in list(coverage_rows):
            if (
                str(row.get("source_family") or SOURCE_FAMILY_BOROUGH_REGISTER)
                != SOURCE_FAMILY_BOROUGH_REGISTER
            ):
                continue
            coverage_rows.append({**row, "source_family": SOURCE_FAMILY_PRIOR_APPROVAL})
    snapshot.manifest_json = {
        **snapshot.manifest_json,
        "source_system": "BOROUGH_REGISTER",
        "coverage_rows": len(coverage_rows),
        "record_count": len(list(payload.get("applications") or [])),
    }

    coverage_count = upsert_coverage_snapshots(
        session=session,
        source_snapshot=snapshot,
        coverage_rows=coverage_rows,
    )
    imported_count = upsert_planning_application_rows(
        session=session,
        storage=storage,
        dataset_key="borough_register",
        source_snapshot=snapshot,
        source_system="BOROUGH_REGISTER",
        source_priority=100,
        applications=list(payload.get("applications") or []),
    )
    session.flush()
    return PlanningImportResult(
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        imported_count=imported_count,
        coverage_count=coverage_count,
    )
