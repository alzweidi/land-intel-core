from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.domain.enums import (
    BaselinePackStatus,
    GeomConfidence,
    GeomSourceType,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
)
from landintel.domain.models import (
    BoroughBaselinePack,
    BoroughRulepack,
    BrownfieldSiteState,
    LpaBoundary,
    PlanningApplication,
    PlanningApplicationDocument,
    PlanningConstraintFeature,
    PolicyArea,
    RawAsset,
    SourceCoverageSnapshot,
    SourceSnapshot,
)
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.storage.base import StorageAdapter

PLANNING_NAMESPACE = uuid.UUID("d49ec4d1-6a43-42f3-9c2b-d88752095d57")


@dataclass(slots=True)
class PlanningImportResult:
    source_snapshot_id: uuid.UUID
    raw_asset_id: uuid.UUID
    imported_count: int
    coverage_count: int


def load_fixture_payload(fixture_path: str | Path) -> tuple[Path, bytes, dict[str, Any]]:
    path = Path(fixture_path)
    payload_bytes = path.read_bytes()
    return path, payload_bytes, json.loads(payload_bytes)


def register_dataset_snapshot(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    dataset_key: str,
    source_family: str,
    source_name: str,
    schema_key: str,
    coverage_note: str,
    freshness_status: SourceFreshnessStatus,
    requested_by: str | None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
) -> tuple[SourceSnapshot, RawAsset, dict[str, Any]]:
    path, payload_bytes, payload = load_fixture_payload(fixture_path)
    content_hash = hashlib.sha256(payload_bytes).hexdigest()
    source_snapshot_id = uuid.uuid5(PLANNING_NAMESPACE, f"{dataset_key}:{content_hash}")
    existing_snapshot = session.get(SourceSnapshot, source_snapshot_id)

    if existing_snapshot is not None:
        existing_asset = session.execute(
            select(RawAsset).where(RawAsset.source_snapshot_id == existing_snapshot.id).limit(1)
        ).scalar_one()
        return existing_snapshot, existing_asset, payload

    raw_asset_id = uuid.uuid5(PLANNING_NAMESPACE, f"{source_snapshot_id}:dataset")
    suffix = path.suffix.lower() or ".json"
    storage_path = f"raw/planning/{dataset_key}/{content_hash}{suffix}"
    mime_type = _guess_mime_type(path)
    storage.put_bytes(storage_path, payload_bytes, content_type=mime_type)

    snapshot = SourceSnapshot(
        id=source_snapshot_id,
        source_family=source_family,
        source_name=source_name,
        source_uri=f"file://{path.resolve()}",
        effective_from=effective_from,
        effective_to=effective_to,
        schema_hash=hashlib.sha256(schema_key.encode("utf-8")).hexdigest(),
        content_hash=content_hash,
        coverage_note=coverage_note,
        freshness_status=freshness_status,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={
            "dataset_key": dataset_key,
            "requested_by": requested_by,
            "fixture_path": str(path),
        },
    )
    asset = RawAsset(
        id=raw_asset_id,
        source_snapshot_id=source_snapshot_id,
        asset_type="FIXTURE_JSON" if suffix == ".json" else "FIXTURE_GEOJSON",
        original_url=f"file://{path.resolve()}",
        storage_path=storage_path,
        mime_type=mime_type,
        content_sha256=content_hash,
        size_bytes=len(payload_bytes),
    )
    session.add(snapshot)
    session.add(asset)
    session.flush()
    return snapshot, asset, payload


def upsert_coverage_snapshots(
    *,
    session: Session,
    source_snapshot: SourceSnapshot,
    coverage_rows: list[dict[str, Any]],
) -> int:
    imported = 0
    for row in coverage_rows:
        borough_id = str(row["borough_id"])
        boundary = session.get(LpaBoundary, borough_id)
        if boundary is None:
            raise ValueError(f"Coverage row references unknown borough '{borough_id}'.")

        source_family = str(row.get("source_family") or source_snapshot.source_family).upper()
        snapshot_id = uuid.uuid5(
            PLANNING_NAMESPACE,
            f"coverage:{source_snapshot.id}:{borough_id}:{source_family}",
        )
        entry = session.get(SourceCoverageSnapshot, snapshot_id)
        if entry is None:
            entry = SourceCoverageSnapshot(
                id=snapshot_id,
                borough_id=borough_id,
                source_family=source_family,
                coverage_geom_27700=boundary.geom_27700,
                source_snapshot_id=source_snapshot.id,
            )
            session.add(entry)

        entry.coverage_status = SourceCoverageStatus(
            str(row.get("coverage_status") or SourceCoverageStatus.UNKNOWN.value)
        )
        entry.gap_reason = _nullable_string(row.get("gap_reason"))
        entry.freshness_status = SourceFreshnessStatus(
            str(row.get("freshness_status") or source_snapshot.freshness_status.value)
        )
        entry.coverage_note = (
            _nullable_string(row.get("coverage_note")) or source_snapshot.coverage_note
        )
        entry.coverage_geom_27700 = boundary.geom_27700
        entry.source_snapshot_id = source_snapshot.id
        imported += 1
    return imported


def store_document_asset(
    *,
    session: Session,
    storage: StorageAdapter,
    source_snapshot_id: uuid.UUID,
    dataset_key: str,
    original_url: str,
    content: bytes,
    mime_type: str,
    asset_type: str = "PLANNING_DOCUMENT",
) -> RawAsset:
    content_hash = hashlib.sha256(content).hexdigest()
    asset_id = uuid.uuid5(
        PLANNING_NAMESPACE,
        f"{source_snapshot_id}:{dataset_key}:{original_url}:{content_hash}",
    )
    existing = session.get(RawAsset, asset_id)
    if existing is not None:
        return existing

    extension = _extension_for_mime(mime_type)
    storage_path = f"raw/planning/{dataset_key}/documents/{content_hash}{extension}"
    storage.put_bytes(storage_path, content, content_type=mime_type)
    asset = RawAsset(
        id=asset_id,
        source_snapshot_id=source_snapshot_id,
        asset_type=asset_type,
        original_url=original_url,
        storage_path=storage_path,
        mime_type=mime_type,
        content_sha256=content_hash,
        size_bytes=len(content),
    )
    session.add(asset)
    session.flush()
    return asset


def upsert_planning_application_rows(
    *,
    session: Session,
    storage: StorageAdapter,
    dataset_key: str,
    source_snapshot: SourceSnapshot,
    source_system: str,
    source_priority: int,
    applications: list[dict[str, Any]],
) -> int:
    imported = 0
    for payload in applications:
        external_ref = str(payload["external_ref"])
        application_id = uuid.uuid5(
            PLANNING_NAMESPACE,
            f"planning:{source_system}:{external_ref}",
        )
        row = session.get(PlanningApplication, application_id)
        if row is None:
            row = PlanningApplication(
                id=application_id,
                source_system=source_system,
                external_ref=external_ref,
                source_snapshot_id=source_snapshot.id,
            )
            session.add(row)

        row.borough_id = _nullable_string(payload.get("borough_id"))
        row.source_system = source_system
        row.source_snapshot_id = source_snapshot.id
        row.external_ref = external_ref
        row.application_type = str(payload.get("application_type") or "UNKNOWN")
        row.proposal_description = str(payload.get("proposal_description") or "")
        row.valid_date = _parse_date(payload.get("valid_date"))
        row.decision_date = _parse_date(payload.get("decision_date"))
        row.decision = _nullable_string(payload.get("decision"))
        row.decision_type = _nullable_string(payload.get("decision_type"))
        row.status = str(payload.get("status") or "UNKNOWN")
        row.route_normalized = _nullable_string(payload.get("route_normalized"))
        row.units_proposed = _parse_int(payload.get("units_proposed"))
        row.source_priority = int(payload.get("source_priority") or source_priority)
        row.source_url = _nullable_string(payload.get("source_url"))
        row.raw_record_json = dict(payload.get("raw_record_json") or payload)

        if isinstance(payload.get("geometry_4326"), dict):
            prepared = normalize_geojson_geometry(
                geometry_payload=payload["geometry_4326"],
                source_epsg=int(payload.get("source_epsg", 4326)),
                source_type=GeomSourceType.SOURCE_POLYGON,
            )
            row.site_geom_27700 = prepared.geom_27700_wkt
            row.site_geom_4326 = prepared.geom_4326
        else:
            row.site_geom_27700 = None
            row.site_geom_4326 = None

        if isinstance(payload.get("point_4326"), dict):
            prepared = normalize_geojson_geometry(
                geometry_payload=payload["point_4326"],
                source_epsg=int(payload.get("source_epsg", 4326)),
                source_type=GeomSourceType.POINT_ONLY,
                confidence=GeomConfidence.INSUFFICIENT,
            )
            row.site_point_27700 = prepared.geom_27700_wkt
            row.site_point_4326 = prepared.geom_4326
        else:
            row.site_point_27700 = None
            row.site_point_4326 = None

        session.flush()
        _upsert_planning_documents(
            session=session,
            storage=storage,
            dataset_key=dataset_key,
            source_snapshot_id=source_snapshot.id,
            planning_application=row,
            documents=list(payload.get("documents") or []),
        )
        imported += 1
    return imported


def upsert_brownfield_rows(
    *,
    session: Session,
    source_snapshot: SourceSnapshot,
    features: list[dict[str, Any]],
) -> int:
    imported = 0
    for feature in features:
        properties = dict(feature.get("properties") or {})
        borough_id = str(properties["borough_id"])
        external_ref = str(properties["external_ref"])
        row_id = uuid.uuid5(
            PLANNING_NAMESPACE,
            f"brownfield:{borough_id}:{external_ref}",
        )
        row = session.get(BrownfieldSiteState, row_id)
        if row is None:
            row = BrownfieldSiteState(
                id=row_id,
                borough_id=borough_id,
                external_ref=external_ref,
                source_snapshot_id=source_snapshot.id,
            )
            session.add(row)

        prepared = normalize_geojson_geometry(
            geometry_payload=feature["geometry"],
            source_epsg=int(properties.get("source_epsg", 4326)),
            source_type=GeomSourceType.SOURCE_POLYGON,
        )
        row.borough_id = borough_id
        row.source_snapshot_id = source_snapshot.id
        row.external_ref = external_ref
        row.geom_27700 = prepared.geom_27700_wkt
        row.geom_4326 = prepared.geom_4326
        row.part = str(properties.get("part") or "PART_1")
        row.pip_status = _nullable_string(properties.get("pip_status"))
        row.tdc_status = _nullable_string(properties.get("tdc_status"))
        row.effective_from = _parse_date(properties.get("effective_from"))
        row.effective_to = _parse_date(properties.get("effective_to"))
        row.raw_record_id = str(properties.get("raw_record_id") or external_ref)
        row.source_url = _nullable_string(properties.get("source_url"))
        row.raw_record_json = dict(properties.get("raw_record_json") or properties)
        imported += 1
    return imported


def upsert_policy_area_rows(
    *,
    session: Session,
    source_snapshot: SourceSnapshot,
    features: list[dict[str, Any]],
) -> int:
    imported = 0
    for feature in features:
        properties = dict(feature.get("properties") or {})
        borough_id = _nullable_string(properties.get("borough_id"))
        policy_family = str(properties.get("policy_family") or "UNKNOWN")
        policy_code = str(properties.get("policy_code") or properties.get("code") or "UNKNOWN")
        row_id = uuid.uuid5(
            PLANNING_NAMESPACE,
            f"policy:{borough_id or 'london'}:{policy_family}:{policy_code}",
        )
        row = session.get(PolicyArea, row_id)
        if row is None:
            row = PolicyArea(
                id=row_id,
                borough_id=borough_id,
                policy_family=policy_family,
                policy_code=policy_code,
                source_snapshot_id=source_snapshot.id,
                source_class=SourceClass.AUTHORITATIVE,
            )
            session.add(row)

        prepared = normalize_geojson_geometry(
            geometry_payload=feature["geometry"],
            source_epsg=int(properties.get("source_epsg", 4326)),
            source_type=GeomSourceType.SOURCE_POLYGON,
        )
        row.borough_id = borough_id
        row.policy_family = policy_family
        row.policy_code = policy_code
        row.name = str(properties.get("name") or policy_code)
        row.geom_27700 = prepared.geom_27700_wkt
        row.geom_4326 = prepared.geom_4326
        row.legal_effective_from = _parse_date(properties.get("legal_effective_from"))
        row.legal_effective_to = _parse_date(properties.get("legal_effective_to"))
        row.source_snapshot_id = source_snapshot.id
        row.source_class = SourceClass(
            str(properties.get("source_class") or SourceClass.AUTHORITATIVE.value)
        )
        row.source_url = _nullable_string(properties.get("source_url"))
        row.raw_record_json = dict(properties.get("raw_record_json") or properties)
        imported += 1
    return imported


def upsert_constraint_rows(
    *,
    session: Session,
    source_snapshot: SourceSnapshot,
    features: list[dict[str, Any]],
) -> int:
    imported = 0
    for feature in features:
        properties = dict(feature.get("properties") or {})
        family = str(properties.get("feature_family") or "constraint")
        subtype = str(properties.get("feature_subtype") or "UNKNOWN")
        feature_key = str(
            properties.get("external_ref") or properties.get("raw_record_id") or subtype
        )
        row_id = uuid.uuid5(
            PLANNING_NAMESPACE,
            f"constraint:{family}:{subtype}:{feature_key}",
        )
        row = session.get(PlanningConstraintFeature, row_id)
        if row is None:
            row = PlanningConstraintFeature(
                id=row_id,
                feature_family=family,
                feature_subtype=subtype,
                authority_level=str(properties.get("authority_level") or "BOROUGH"),
                source_snapshot_id=source_snapshot.id,
                source_class=SourceClass.AUTHORITATIVE,
            )
            session.add(row)

        prepared = normalize_geojson_geometry(
            geometry_payload=feature["geometry"],
            source_epsg=int(properties.get("source_epsg", 4326)),
            source_type=GeomSourceType.SOURCE_POLYGON,
        )
        row.feature_family = family
        row.feature_subtype = subtype
        row.authority_level = str(properties.get("authority_level") or "BOROUGH")
        row.geom_27700 = prepared.geom_27700_wkt
        row.geom_4326 = prepared.geom_4326
        row.legal_status = _nullable_string(properties.get("legal_status"))
        row.effective_from = _parse_date(properties.get("effective_from"))
        row.effective_to = _parse_date(properties.get("effective_to"))
        row.source_snapshot_id = source_snapshot.id
        row.source_class = SourceClass(
            str(properties.get("source_class") or SourceClass.AUTHORITATIVE.value)
        )
        row.source_url = _nullable_string(properties.get("source_url"))
        row.raw_record_json = dict(properties.get("raw_record_json") or properties)
        imported += 1
    return imported


def upsert_baseline_pack_rows(
    *,
    session: Session,
    source_snapshot: SourceSnapshot,
    baseline_packs: list[dict[str, Any]],
) -> int:
    imported = 0
    for payload in baseline_packs:
        borough_id = str(payload["borough_id"])
        version = str(payload["version"])
        pack_id = uuid.uuid5(
            PLANNING_NAMESPACE,
            f"baseline-pack:{borough_id}:{version}",
        )
        pack = session.get(BoroughBaselinePack, pack_id)
        if pack is None:
            pack = BoroughBaselinePack(
                id=pack_id,
                borough_id=borough_id,
                version=version,
                source_snapshot_id=source_snapshot.id,
            )
            session.add(pack)

        pack.borough_id = borough_id
        pack.version = version
        pack.status = BaselinePackStatus(
            str(payload.get("status") or BaselinePackStatus.DRAFT.value)
        )
        pack.freshness_status = SourceFreshnessStatus(
            str(payload.get("freshness_status") or source_snapshot.freshness_status.value)
        )
        pack.signed_off_by = _nullable_string(payload.get("signed_off_by"))
        pack.signed_off_at = _parse_datetime(payload.get("signed_off_at"))
        pack.pack_json = dict(payload.get("pack_json") or {})
        pack.source_snapshot_id = source_snapshot.id
        session.flush()

        for rule_payload in list(payload.get("rulepacks") or []):
            template_key = str(rule_payload["template_key"])
            rulepack_id = uuid.uuid5(
                PLANNING_NAMESPACE,
                f"rulepack:{pack.id}:{template_key}",
            )
            rulepack = session.get(BoroughRulepack, rulepack_id)
            if rulepack is None:
                rulepack = BoroughRulepack(
                    id=rulepack_id,
                    borough_baseline_pack_id=pack.id,
                    template_key=template_key,
                )
                session.add(rulepack)

            rulepack.borough_baseline_pack_id = pack.id
            rulepack.template_key = template_key
            rulepack.status = BaselinePackStatus(
                str(rule_payload.get("status") or pack.status.value)
            )
            rulepack.freshness_status = SourceFreshnessStatus(
                str(
                    rule_payload.get("freshness_status")
                    or payload.get("freshness_status")
                    or source_snapshot.freshness_status.value
                )
            )
            rulepack.effective_from = _parse_date(rule_payload.get("effective_from"))
            rulepack.effective_to = _parse_date(rule_payload.get("effective_to"))
            rulepack.rule_json = dict(rule_payload.get("rule_json") or {})
            rulepack.source_snapshot_id = source_snapshot.id
        imported += 1
    return imported


def dataset_meta(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("meta"), dict):
        return dict(payload["meta"])
    if isinstance(payload.get("metadata"), dict):
        return dict(payload["metadata"])
    return {}


def parse_source_class(value: str | None, default: SourceClass) -> SourceClass:
    return SourceClass(value or default.value)


def _upsert_planning_documents(
    *,
    session: Session,
    storage: StorageAdapter,
    dataset_key: str,
    source_snapshot_id: uuid.UUID,
    planning_application: PlanningApplication,
    documents: list[dict[str, Any]],
) -> None:
    for payload in documents:
        doc_url = str(payload["doc_url"])
        doc_type = str(payload.get("doc_type") or "unknown")
        mime_type = str(payload.get("mime_type") or "text/plain")
        content_text = str(
            payload.get("content_text")
            or payload.get("excerpt_text")
            or f"Fixture document for {planning_application.external_ref}"
        )
        asset = store_document_asset(
            session=session,
            storage=storage,
            source_snapshot_id=source_snapshot_id,
            dataset_key=dataset_key,
            original_url=doc_url,
            content=content_text.encode("utf-8"),
            mime_type=mime_type,
        )
        document_id = uuid.uuid5(
            PLANNING_NAMESPACE,
            f"planning-doc:{planning_application.id}:{doc_url}",
        )
        row = session.get(PlanningApplicationDocument, document_id)
        if row is None:
            row = PlanningApplicationDocument(
                id=document_id,
                planning_application_id=planning_application.id,
                asset_id=asset.id,
                doc_type=doc_type,
                doc_url=doc_url,
            )
            session.add(row)
        row.planning_application_id = planning_application.id
        row.asset_id = asset.id
        row.doc_type = doc_type
        row.doc_url = doc_url


def _guess_mime_type(path: Path) -> str:
    if path.suffix.lower() == ".geojson":
        return "application/geo+json"
    return mimetypes.guess_type(path.name)[0] or "application/json"


def _extension_for_mime(mime_type: str) -> str:
    if mime_type == "application/pdf":
        return ".pdf"
    if mime_type in {"application/geo+json", "application/json"}:
        return ".json"
    if mime_type == "text/html":
        return ".html"
    return ".txt"


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any) -> date | None:
    if value in {None, ""}:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _parse_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)
