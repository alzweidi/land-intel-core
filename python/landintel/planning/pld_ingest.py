from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from landintel.domain.enums import SourceFreshnessStatus
from landintel.storage.base import StorageAdapter

from .constants import SOURCE_FAMILY_PLD
from .import_common import (
    PlanningImportResult,
    dataset_meta,
    register_dataset_snapshot,
    upsert_coverage_snapshots,
    upsert_planning_application_rows,
)


def import_pld_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "planning_london_datahub_fixture",
) -> PlanningImportResult:
    snapshot, asset, payload = register_dataset_snapshot(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="pld_applications",
        source_family=SOURCE_FAMILY_PLD,
        source_name=source_name,
        schema_key="phase3a:pld:applications:v1",
        coverage_note=(
            "Planning London Datahub fixture import for Phase 3A local/dev. "
            "PLD remains supplemental only."
        ),
        freshness_status=SourceFreshnessStatus.STALE,
        requested_by=requested_by,
    )
    meta = dataset_meta(payload)
    snapshot.coverage_note = str(meta.get("coverage_note") or snapshot.coverage_note)
    snapshot.freshness_status = SourceFreshnessStatus(
        str(meta.get("freshness_status") or snapshot.freshness_status.value)
    )
    snapshot.manifest_json = {
        **snapshot.manifest_json,
        "source_system": "PLD",
        "coverage_rows": len(list(meta.get("coverage") or [])),
        "record_count": len(list(payload.get("applications") or [])),
    }

    coverage_count = upsert_coverage_snapshots(
        session=session,
        source_snapshot=snapshot,
        coverage_rows=list(meta.get("coverage") or []),
    )
    imported_count = upsert_planning_application_rows(
        session=session,
        storage=storage,
        dataset_key="pld_applications",
        source_snapshot=snapshot,
        source_system="PLD",
        source_priority=50,
        applications=list(payload.get("applications") or []),
    )
    session.flush()
    return PlanningImportResult(
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        imported_count=imported_count,
        coverage_count=coverage_count,
    )
