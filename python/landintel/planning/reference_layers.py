from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from landintel.domain.enums import SourceFreshnessStatus
from landintel.storage.base import StorageAdapter

from .constants import (
    SOURCE_FAMILY_BASELINE_PACK,
    SOURCE_FAMILY_BROWNFIELD,
    SOURCE_FAMILY_CONSTRAINT,
    SOURCE_FAMILY_FLOOD,
    SOURCE_FAMILY_HERITAGE_ARTICLE4,
    SOURCE_FAMILY_POLICY,
)
from .import_common import (
    PlanningImportResult,
    dataset_meta,
    register_dataset_snapshot,
    upsert_baseline_pack_rows,
    upsert_brownfield_rows,
    upsert_constraint_rows,
    upsert_coverage_snapshots,
    upsert_policy_area_rows,
)


def import_brownfield_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "brownfield_register_fixture",
) -> PlanningImportResult:
    return _import_geojson_layer(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        dataset_key="brownfield_sites",
        source_family=SOURCE_FAMILY_BROWNFIELD,
        source_name=source_name,
        schema_key="phase3a:brownfield:geojson:v1",
        default_coverage_note=(
            "Brownfield Part 1 and Part 2 fixture import for Phase 3A local/dev."
        ),
        row_importer=upsert_brownfield_rows,
    )


def import_policy_area_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "borough_policy_layer_fixture",
) -> PlanningImportResult:
    return _import_geojson_layer(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        dataset_key="policy_areas",
        source_family=SOURCE_FAMILY_POLICY,
        source_name=source_name,
        schema_key="phase3a:policy-areas:geojson:v1",
        default_coverage_note="London-first policy-area fixture import for Phase 3A local/dev.",
        row_importer=upsert_policy_area_rows,
    )


def import_constraint_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "planning_constraint_fixture",
) -> PlanningImportResult:
    return _import_geojson_layer(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        dataset_key="constraint_features",
        source_family=SOURCE_FAMILY_CONSTRAINT,
        source_name=source_name,
        schema_key="phase3a:constraints:geojson:v1",
        default_coverage_note="Critical planning constraint fixture import for Phase 3A local/dev.",
        row_importer=upsert_constraint_rows,
    )


def import_flood_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "flood_constraint_fixture",
) -> PlanningImportResult:
    return _import_geojson_layer(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        dataset_key="flood_constraints",
        source_family=SOURCE_FAMILY_FLOOD,
        source_name=source_name,
        schema_key="phase3a:flood:geojson:v1",
        default_coverage_note="Flood constraint fixture import for Phase 3A local/dev.",
        row_importer=upsert_constraint_rows,
    )


def import_heritage_article4_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "heritage_article4_fixture",
) -> PlanningImportResult:
    return _import_geojson_layer(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        dataset_key="heritage_article4",
        source_family=SOURCE_FAMILY_HERITAGE_ARTICLE4,
        source_name=source_name,
        schema_key="phase3a:heritage-article4:geojson:v1",
        default_coverage_note=(
            "Heritage and Article 4 constraint fixture import for Phase 3A local/dev."
        ),
        row_importer=upsert_constraint_rows,
    )


def import_baseline_pack_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "borough_baseline_pack_fixture",
) -> PlanningImportResult:
    snapshot, asset, payload = register_dataset_snapshot(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="borough_baseline_pack",
        source_family=SOURCE_FAMILY_BASELINE_PACK,
        source_name=source_name,
        schema_key="phase3a:baseline-pack:json:v1",
        coverage_note="Borough baseline-pack scaffold fixture import for Phase 3A local/dev.",
        freshness_status=SourceFreshnessStatus.FRESH,
        requested_by=requested_by,
    )
    meta = dataset_meta(payload)
    snapshot.coverage_note = str(meta.get("coverage_note") or snapshot.coverage_note)
    snapshot.freshness_status = SourceFreshnessStatus(
        str(meta.get("freshness_status") or snapshot.freshness_status.value)
    )
    coverage_count = upsert_coverage_snapshots(
        session=session,
        source_snapshot=snapshot,
        coverage_rows=list(meta.get("coverage") or []),
    )
    imported_count = upsert_baseline_pack_rows(
        session=session,
        source_snapshot=snapshot,
        baseline_packs=list(payload.get("baseline_packs") or []),
    )
    snapshot.manifest_json = {
        **snapshot.manifest_json,
        "coverage_rows": coverage_count,
        "record_count": imported_count,
    }
    session.flush()
    return PlanningImportResult(
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        imported_count=imported_count,
        coverage_count=coverage_count,
    )


def _import_geojson_layer(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    dataset_key: str,
    source_family: str,
    source_name: str,
    schema_key: str,
    default_coverage_note: str,
    row_importer,
) -> PlanningImportResult:
    snapshot, asset, payload = register_dataset_snapshot(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key=dataset_key,
        source_family=source_family,
        source_name=source_name,
        schema_key=schema_key,
        coverage_note=default_coverage_note,
        freshness_status=SourceFreshnessStatus.FRESH,
        requested_by=requested_by,
    )
    meta = dataset_meta(payload)
    snapshot.coverage_note = str(meta.get("coverage_note") or snapshot.coverage_note)
    snapshot.freshness_status = SourceFreshnessStatus(
        str(meta.get("freshness_status") or snapshot.freshness_status.value)
    )
    coverage_count = upsert_coverage_snapshots(
        session=session,
        source_snapshot=snapshot,
        coverage_rows=list(meta.get("coverage") or []),
    )
    imported_count = row_importer(
        session=session,
        source_snapshot=snapshot,
        features=list(payload.get("features") or []),
    )
    snapshot.manifest_json = {
        **snapshot.manifest_json,
        "coverage_rows": coverage_count,
        "record_count": imported_count,
    }
    session.flush()
    return PlanningImportResult(
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        imported_count=imported_count,
        coverage_count=coverage_count,
    )
