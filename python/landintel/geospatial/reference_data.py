from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.domain.enums import SourceFreshnessStatus, SourceParseStatus
from landintel.domain.models import (
    HmlrTitlePolygon,
    LpaBoundary,
    RawAsset,
    SourceSnapshot,
)
from landintel.geospatial.geometry import (
    GeomSourceType,
    normalize_geojson_geometry,
)
from landintel.listings.parsing import normalize_address
from landintel.storage.base import StorageAdapter

REFERENCE_NAMESPACE = uuid.UUID("34f0f114-c8df-420a-b848-5350205f198a")


@dataclass(slots=True)
class ReferenceImportResult:
    source_snapshot_id: uuid.UUID
    raw_asset_id: uuid.UUID
    imported_count: int


def import_lpa_boundaries(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    source_name: str = "london_borough_boundaries",
    requested_by: str | None = None,
) -> ReferenceImportResult:
    return _import_geojson_dataset(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="lpa_boundary",
        source_name=source_name,
        coverage_note="London borough/LPA boundary fixture import for Phase 2 local/dev.",
        row_importer=_upsert_lpa_boundaries,
        requested_by=requested_by,
    )


def import_hmlr_title_polygons(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    source_name: str = "hmlr_inspire_title_polygons",
    requested_by: str | None = None,
) -> ReferenceImportResult:
    return _import_geojson_dataset(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="hmlr_title_polygon",
        source_name=source_name,
        coverage_note="HMLR INSPIRE title polygon fixture import for Phase 2 local/dev.",
        row_importer=_upsert_title_polygons,
        requested_by=requested_by,
    )


def _import_geojson_dataset(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    dataset_key: str,
    source_name: str,
    coverage_note: str,
    row_importer,
    requested_by: str | None,
) -> ReferenceImportResult:
    path = Path(fixture_path)
    payload_bytes = path.read_bytes()
    content_hash = hashlib.sha256(payload_bytes).hexdigest()
    source_snapshot_id = uuid.uuid5(REFERENCE_NAMESPACE, f"{dataset_key}:{content_hash}")
    existing_snapshot = session.get(SourceSnapshot, source_snapshot_id)

    if existing_snapshot is not None:
        existing_asset = session.execute(
            select(RawAsset).where(RawAsset.source_snapshot_id == existing_snapshot.id).limit(1)
        ).scalar_one()
        imported_count = row_importer(
            session=session,
            source_snapshot_id=existing_snapshot.id,
            feature_collection=json.loads(payload_bytes),
        )
        session.flush()
        return ReferenceImportResult(
            source_snapshot_id=existing_snapshot.id,
            raw_asset_id=existing_asset.id,
            imported_count=imported_count,
        )

    raw_asset_id = uuid.uuid5(REFERENCE_NAMESPACE, f"{source_snapshot_id}:raw_asset")
    storage_path = f"raw/reference/{dataset_key}/{content_hash}.geojson"
    storage.put_bytes(storage_path, payload_bytes, content_type="application/geo+json")

    feature_collection = json.loads(payload_bytes)
    feature_count = len(feature_collection.get("features", []))
    source_uri = f"file://{path.resolve()}"

    source_snapshot = SourceSnapshot(
        id=source_snapshot_id,
        source_family=f"reference.{dataset_key}",
        source_name=source_name,
        source_uri=source_uri,
        schema_hash=hashlib.sha256(f"{dataset_key}:geojson:v1".encode()).hexdigest(),
        content_hash=content_hash,
        coverage_note=coverage_note,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={
            "dataset_key": dataset_key,
            "feature_count": feature_count,
            "requested_by": requested_by,
        },
    )
    session.add(source_snapshot)
    session.add(
        RawAsset(
            id=raw_asset_id,
            source_snapshot_id=source_snapshot_id,
            asset_type="GEOJSON",
            original_url=source_uri,
            storage_path=storage_path,
            mime_type="application/geo+json",
            content_sha256=content_hash,
            size_bytes=len(payload_bytes),
        )
    )
    session.flush()

    imported_count = row_importer(
        session=session,
        source_snapshot_id=source_snapshot_id,
        feature_collection=feature_collection,
    )
    session.flush()
    return ReferenceImportResult(
        source_snapshot_id=source_snapshot_id,
        raw_asset_id=raw_asset_id,
        imported_count=imported_count,
    )


def _upsert_lpa_boundaries(
    *,
    session: Session,
    source_snapshot_id: uuid.UUID,
    feature_collection: dict[str, Any],
) -> int:
    imported = 0
    for feature in feature_collection.get("features", []):
        properties = dict(feature.get("properties", {}))
        lpa_id = str(
            properties.get("borough_id")
            or properties.get("lpa_id")
            or properties.get("slug")
            or feature.get("id")
        )
        prepared = normalize_geojson_geometry(
            geometry_payload=feature["geometry"],
            source_epsg=int(properties.get("source_epsg", 4326)),
            source_type=GeomSourceType.SOURCE_POLYGON,
        )
        row = session.get(LpaBoundary, lpa_id)
        if row is None:
            row = LpaBoundary(id=lpa_id, name=str(properties.get("name") or lpa_id))
            session.add(row)
        row.name = str(properties.get("name") or row.name)
        row.external_ref = (
            str(properties["gss_code"])
            if properties.get("gss_code")
            else row.external_ref
        )
        row.authority_level = str(properties.get("authority_level") or "BOROUGH")
        row.geom_27700 = prepared.geom_27700_wkt
        row.geom_4326 = prepared.geom_4326
        row.geom_hash = prepared.geom_hash
        row.area_sqm = prepared.area_sqm
        row.source_snapshot_id = source_snapshot_id
        imported += 1
    return imported


def _upsert_title_polygons(
    *,
    session: Session,
    source_snapshot_id: uuid.UUID,
    feature_collection: dict[str, Any],
) -> int:
    imported = 0
    for feature in feature_collection.get("features", []):
        properties = dict(feature.get("properties", {}))
        title_number = str(properties.get("title_number") or feature.get("id"))
        prepared = normalize_geojson_geometry(
            geometry_payload=feature["geometry"],
            source_epsg=int(properties.get("source_epsg", 4326)),
            source_type=GeomSourceType.SOURCE_POLYGON,
        )
        title_id = uuid.uuid5(REFERENCE_NAMESPACE, f"title:{title_number}")
        row = session.get(HmlrTitlePolygon, title_id)
        if row is None:
            row = HmlrTitlePolygon(id=title_id, title_number=title_number)
            session.add(row)
        row.title_number = title_number
        row.address_text = properties.get("address_text")
        row.normalized_address = normalize_address(properties.get("address_text"))
        row.geom_27700 = prepared.geom_27700_wkt
        row.geom_4326 = prepared.geom_4326
        row.geom_hash = prepared.geom_hash
        row.area_sqm = prepared.area_sqm
        row.source_snapshot_id = source_snapshot_id
        imported += 1
    return imported
