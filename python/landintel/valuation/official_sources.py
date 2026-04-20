from __future__ import annotations

import csv
import io
import json
import uuid
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.config import get_settings
from landintel.data_fetch.http_assets import fetch_http_asset
from landintel.domain.enums import SourceFreshnessStatus, SourceParseStatus
from landintel.domain.models import (
    LpaBoundary,
    MarketIndexSeries,
    MarketSaleComp,
    RawAsset,
    SourceSnapshot,
)
from landintel.planning.import_common import PlanningImportResult, upsert_coverage_snapshots
from landintel.storage.base import StorageAdapter
from landintel.valuation import market as valuation_market_mod

VALUATION_OFFICIAL_SOURCE_URL_KEYS = {
    "hmlr_price_paid": "hmlr_price_paid",
    "ukhpi": "ukhpi",
}
VALUATION_OFFICIAL_NAMESPACE = uuid.UUID("a7c33f56-4a7f-4f4f-9b3c-3e6b3f7a49e3")


def import_hmlr_price_paid_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    remote_url: str | None = None,
) -> PlanningImportResult:
    remote_url = remote_url or _configured_remote_url("hmlr_price_paid")
    if remote_url:
        try:
            fetched = fetch_http_asset(
                remote_url,
                timeout_seconds=get_settings().snapshot_http_timeout_seconds,
            )
            payload = _parse_hmlr_price_paid_payload(fetched.content, fetched.content_type)
            with _begin_nested_if_supported(session):
                snapshot, asset = _register_remote_snapshot(
                    session=session,
                    storage=storage,
                    raw_bytes=fetched.content,
                    content_type=fetched.content_type,
                    dataset_key="valuation_hmlr_price_paid",
                    source_family="HMLR_PRICE_PAID",
                    source_name="HMLR Price Paid official source",
                    schema_key="valuation_hmlr_price_paid_v1",
                    coverage_note=(
                        "Official HMLR Price Paid evidence for "
                        "Phase 8A valuation refresh."
                    ),
                    requested_by=requested_by,
                    remote_url=fetched.final_url,
                )
                coverage_count = _upsert_hmlr_coverage_snapshots(
                    session=session,
                    snapshot=snapshot,
                    rows=payload,
                )
                imported_count = _upsert_hmlr_price_paid_rows(
                    session=session,
                    snapshot=snapshot,
                    raw_asset_id=asset.id,
                    rows=payload,
                )
                snapshot.manifest_json = {
                    **snapshot.manifest_json,
                    "coverage_rows": coverage_count,
                    "record_count": imported_count,
                    "fetch_mode": "remote",
                    "remote_url": fetched.final_url,
                    "content_type": fetched.content_type,
                    "status_code": fetched.status_code,
                }
                asset.original_url = fetched.final_url
                session.flush()
            return PlanningImportResult(
                source_snapshot_id=snapshot.id,
                raw_asset_id=asset.id,
                imported_count=imported_count,
                coverage_count=coverage_count,
            )
        except Exception as exc:
            fallback_result = valuation_market_mod.import_hmlr_price_paid_fixture(
                session=session,
                storage=storage,
                fixture_path=fixture_path,
                requested_by=requested_by,
            )
            _annotate_fixture_fallback(
                session=session,
                source_snapshot_id=fallback_result.source_snapshot_id,
                remote_url=remote_url,
                fallback_reason=f"{type(exc).__name__}: {exc}",
            )
            session.flush()
            return fallback_result

    return valuation_market_mod.import_hmlr_price_paid_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
    )


def import_ukhpi_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    remote_url: str | None = None,
) -> PlanningImportResult:
    remote_url = remote_url or _configured_remote_url("ukhpi")
    if remote_url:
        try:
            fetched = fetch_http_asset(
                remote_url,
                timeout_seconds=get_settings().snapshot_http_timeout_seconds,
            )
            payload = _parse_ukhpi_payload(fetched.content, fetched.content_type)
            with _begin_nested_if_supported(session):
                snapshot, asset = _register_remote_snapshot(
                    session=session,
                    storage=storage,
                    raw_bytes=fetched.content,
                    content_type=fetched.content_type,
                    dataset_key="valuation_ukhpi",
                    source_family="UKHPI",
                    source_name="UKHPI official source",
                    schema_key="valuation_ukhpi_v1",
                    coverage_note="Official UKHPI evidence for Phase 8A valuation refresh.",
                    requested_by=requested_by,
                    remote_url=fetched.final_url,
                )
                coverage_count = _upsert_ukhpi_coverage_snapshots(
                    session=session,
                    snapshot=snapshot,
                    rows=payload,
                )
                imported_count = _upsert_ukhpi_rows(
                    session=session,
                    snapshot=snapshot,
                    raw_asset_id=asset.id,
                    rows=payload,
                )
                snapshot.manifest_json = {
                    **snapshot.manifest_json,
                    "coverage_rows": coverage_count,
                    "record_count": imported_count,
                    "fetch_mode": "remote",
                    "remote_url": fetched.final_url,
                    "content_type": fetched.content_type,
                    "status_code": fetched.status_code,
                }
                asset.original_url = fetched.final_url
                session.flush()
            return PlanningImportResult(
                source_snapshot_id=snapshot.id,
                raw_asset_id=asset.id,
                imported_count=imported_count,
                coverage_count=coverage_count,
            )
        except Exception as exc:
            fallback_result = valuation_market_mod.import_ukhpi_fixture(
                session=session,
                storage=storage,
                fixture_path=fixture_path,
                requested_by=requested_by,
            )
            _annotate_fixture_fallback(
                session=session,
                source_snapshot_id=fallback_result.source_snapshot_id,
                remote_url=remote_url,
                fallback_reason=f"{type(exc).__name__}: {exc}",
            )
            session.flush()
            return fallback_result

    return valuation_market_mod.import_ukhpi_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
    )


def _register_remote_snapshot(
    *,
    session: Session,
    storage: StorageAdapter,
    raw_bytes: bytes,
    content_type: str,
    dataset_key: str,
    source_family: str,
    source_name: str,
    schema_key: str,
    coverage_note: str,
    requested_by: str | None,
    remote_url: str,
) -> tuple[SourceSnapshot, RawAsset]:
    content_hash = _sha256(raw_bytes)
    source_snapshot_id = uuid.uuid5(VALUATION_OFFICIAL_NAMESPACE, f"{dataset_key}:{content_hash}")
    existing_snapshot = session.get(SourceSnapshot, source_snapshot_id)
    if existing_snapshot is not None:
        existing_asset = session.execute(
            select(RawAsset).where(RawAsset.source_snapshot_id == existing_snapshot.id).limit(1)
        ).scalar_one()
        return existing_snapshot, existing_asset

    asset_suffix = _suffix_for_content_type(content_type, remote_url)
    storage_path = f"raw/official/{dataset_key}/{content_hash}{asset_suffix}"
    storage.put_bytes(storage_path, raw_bytes, content_type=content_type)

    snapshot = SourceSnapshot(
        id=source_snapshot_id,
        source_family=source_family,
        source_name=source_name,
        source_uri=remote_url,
        schema_hash=_sha256(schema_key.encode("utf-8")),
        content_hash=content_hash,
        coverage_note=coverage_note,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={
            "dataset_key": dataset_key,
            "requested_by": requested_by,
            "remote_url": remote_url,
            "content_type": content_type,
            "storage_path": storage_path,
            "fetch_mode": "remote",
        },
    )
    asset = RawAsset(
        id=uuid.uuid5(VALUATION_OFFICIAL_NAMESPACE, f"{source_snapshot_id}:raw_asset"),
        source_snapshot_id=source_snapshot_id,
        asset_type=_asset_type_for_content_type(content_type),
        original_url=remote_url,
        storage_path=storage_path,
        mime_type=content_type,
        content_sha256=content_hash,
        size_bytes=len(raw_bytes),
    )
    session.add(snapshot)
    session.add(asset)
    session.flush()
    return snapshot, asset


def _upsert_hmlr_price_paid_rows(
    *,
    session: Session,
    snapshot: SourceSnapshot,
    raw_asset_id: uuid.UUID,
    rows: list[dict[str, Any]],
) -> int:
    imported = 0
    for row in rows:
        transaction_ref = str(
            row.get("transaction_ref")
            or row.get("transaction_unique_identifier")
            or row.get("transaction_id")
            or row.get("transaction unique identifier")
            or f"ppd-{imported + 1}"
        )
        entry_id = uuid.uuid5(
            valuation_market_mod.VALUATION_MARKET_NAMESPACE,
            f"sale:{transaction_ref}",
        )
        entry = session.get(MarketSaleComp, entry_id)
        if entry is None:
            entry = MarketSaleComp(id=entry_id, transaction_ref=transaction_ref)
            session.add(entry)
        entry.borough_id = _slugify(
            row.get("borough_id")
            or row.get("district")
            or row.get("district_name")
            or row.get("RegionName")
            or row.get("region_name")
        )
        entry.source_snapshot_id = snapshot.id
        entry.raw_asset_id = raw_asset_id
        entry.sale_date = _parse_date(
            row.get("sale_date") or row.get("date") or row.get("Date") or row.get("completion_date")
        )
        entry.price_gbp = int(row.get("price_gbp") or row.get("price") or row.get("Price") or 0)
        entry.property_type = str(row.get("property_type") or row.get("Property Type") or "UNKNOWN")
        entry.tenure = _map_tenure(row.get("tenure") or row.get("duration") or row.get("Duration"))
        entry.postcode_district = _postcode_district(
            row.get("postcode_district") or row.get("postcode") or row.get("Postcode")
        )
        entry.address_text = _nullable_string(
            row.get("address_text")
            or row.get("address")
            or row.get("Address")
            or _compose_address(row)
        )
        entry.floor_area_sqm = _parse_float(row.get("floor_area_sqm"))
        entry.rebased_price_per_sqm_hint = _parse_float(row.get("rebased_price_per_sqm_hint"))
        entry.raw_record_json = dict(row)
        imported += 1
    return imported


def _upsert_hmlr_coverage_snapshots(
    *,
    session: Session,
    snapshot: SourceSnapshot,
    rows: list[dict[str, Any]],
) -> int:
    borough_ids = {
        _slugify(
            row.get("borough_id")
            or row.get("district")
            or row.get("district_name")
            or row.get("RegionName")
            or row.get("region_name")
        )
        for row in rows
        if _slugify(
            row.get("borough_id")
            or row.get("district")
            or row.get("district_name")
            or row.get("RegionName")
            or row.get("region_name")
        )
    }
    coverage_rows: list[dict[str, Any]] = []
    for borough_id in sorted(borough_ids):
        if session.get(LpaBoundary, borough_id) is None:
            continue
        coverage_rows.append(
            {
                "borough_id": borough_id,
                "source_family": "HMLR_PRICE_PAID",
                "coverage_status": "COMPLETE",
                "freshness_status": snapshot.freshness_status.value,
                "coverage_note": snapshot.coverage_note,
            }
        )
    if coverage_rows:
        return upsert_coverage_snapshots(
            session=session,
            source_snapshot=snapshot,
            coverage_rows=coverage_rows,
        )
    return 0


def _upsert_ukhpi_rows(
    *,
    session: Session,
    snapshot: SourceSnapshot,
    raw_asset_id: uuid.UUID,
    rows: list[dict[str, Any]],
) -> int:
    imported = 0
    for row in rows:
        borough_id = _slugify(
            row.get("borough_id")
            or row.get("RegionName")
            or row.get("region_name")
            or row.get("AreaCode")
            or row.get("area_code")
        )
        period_month = _parse_date(
            row.get("period_month") or row.get("Date") or row.get("date") or row.get("month")
        )
        index_key = str(row.get("index_key") or row.get("IndexKey") or "UKHPI")
        entry_id = uuid.uuid5(
            valuation_market_mod.VALUATION_MARKET_NAMESPACE,
            f"ukhpi:{borough_id or 'london'}:{index_key}:{period_month.isoformat()}",
        )
        entry = session.get(MarketIndexSeries, entry_id)
        if entry is None:
            entry = MarketIndexSeries(id=entry_id)
            session.add(entry)
        entry.borough_id = borough_id
        entry.index_key = index_key
        entry.period_month = period_month
        entry.index_value = float(
            row.get("index_value") or row.get("Index") or row.get("index") or 0.0
        )
        entry.source_snapshot_id = snapshot.id
        entry.raw_asset_id = raw_asset_id
        entry.raw_record_json = dict(row)
        imported += 1
    return imported


def _upsert_ukhpi_coverage_snapshots(
    *,
    session: Session,
    snapshot: SourceSnapshot,
    rows: list[dict[str, Any]],
) -> int:
    borough_ids = {
        _slugify(
            row.get("borough_id")
            or row.get("RegionName")
            or row.get("region_name")
        )
        for row in rows
        if _slugify(row.get("borough_id") or row.get("RegionName") or row.get("region_name"))
    }
    coverage_rows: list[dict[str, Any]] = []
    for borough_id in sorted(borough_ids):
        if session.get(LpaBoundary, borough_id) is None:
            continue
        coverage_rows.append(
            {
                "borough_id": borough_id,
                "source_family": "UKHPI",
                "coverage_status": "COMPLETE",
                "freshness_status": snapshot.freshness_status.value,
                "coverage_note": snapshot.coverage_note,
            }
        )
    if coverage_rows:
        return upsert_coverage_snapshots(
            session=session,
            source_snapshot=snapshot,
            coverage_rows=coverage_rows,
        )
    return 0


def _parse_hmlr_price_paid_payload(content: bytes, content_type: str) -> list[dict[str, Any]]:
    del content_type
    text = content.decode("utf-8-sig")
    if text.lstrip().startswith("{"):
        payload = json.loads(text)
        rows = payload.get("sales") or payload.get("rows") or []
        if isinstance(rows, list):
            return [dict(row) for row in rows]
        raise ValueError("HMLR Price Paid JSON payload did not contain a row list.")

    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(reader, start=1):
        rows.append(
            {
                "transaction_ref": row.get("transaction_unique_identifier")
                or row.get("transaction_ref")
                or f"ppd-{index}",
                "borough_id": row.get("district")
                or row.get("District")
                or row.get("RegionName"),
                "sale_date": row.get("date") or row.get("Date"),
                "price_gbp": row.get("price") or row.get("Price"),
                "property_type": row.get("property_type") or row.get("Property Type"),
                "tenure": row.get("tenure") or row.get("duration") or row.get("Duration"),
                "postcode_district": row.get("postcode") or row.get("Postcode"),
                "address_text": _compose_address(row),
                "floor_area_sqm": row.get("floor_area_sqm"),
                "rebased_price_per_sqm_hint": row.get("rebased_price_per_sqm_hint"),
                "raw_record_json": dict(row),
            }
        )
    return rows


def _parse_ukhpi_payload(content: bytes, content_type: str) -> list[dict[str, Any]]:
    del content_type
    text = content.decode("utf-8-sig")
    if text.lstrip().startswith("{"):
        payload = json.loads(text)
        rows = payload.get("index_rows") or payload.get("rows") or []
        if isinstance(rows, list):
            return [dict(row) for row in rows]
        raise ValueError("UKHPI JSON payload did not contain a row list.")

    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for row in reader:
        rows.append(
            {
                "borough_id": row.get("borough_id") or row.get("RegionName"),
                "index_key": row.get("index_key") or "UKHPI",
                "period_month": row.get("period_month") or row.get("Date"),
                "index_value": row.get("index_value") or row.get("Index"),
                "raw_record_json": dict(row),
            }
        )
    return rows


def _configured_remote_url(key: str) -> str | None:
    settings = get_settings()
    return settings.valuation_official_source_urls_json.get(key) or None


def _annotate_fixture_fallback(
    *,
    session: Session,
    source_snapshot_id,
    remote_url: str,
    fallback_reason: str,
) -> None:
    snapshot = session.get(SourceSnapshot, source_snapshot_id)
    if snapshot is None:
        return
    snapshot.manifest_json = {
        **snapshot.manifest_json,
        "fetch_mode": "fixture_fallback",
        "remote_url": remote_url,
        "fallback_reason": fallback_reason,
    }


def _begin_nested_if_supported(session: Session):
    begin_nested = getattr(session, "begin_nested", None)
    if callable(begin_nested):
        return begin_nested()
    return nullcontext()


def _suffix_for_content_type(content_type: str, remote_url: str) -> str:
    lowered = content_type.lower()
    if "csv" in lowered:
        return ".csv"
    if "json" in lowered:
        return ".json"
    suffix = Path(remote_url).suffix
    return suffix or ".csv"


def _asset_type_for_content_type(content_type: str) -> str:
    lowered = content_type.lower()
    if "csv" in lowered:
        return "CSV"
    if "json" in lowered:
        return "JSON"
    return "OFFICIAL_DATA"


def _sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def _slugify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_"})


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: Any):
    from datetime import date

    if value in {None, ""}:
        raise ValueError("date value is required")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _parse_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _map_tenure(value: Any) -> str | None:
    tenure = _nullable_string(value)
    if tenure is None:
        return None
    normalized = tenure.upper()
    if normalized in {"F", "FREEHOLD"}:
        return "FREEHOLD"
    if normalized in {"L", "LEASEHOLD"}:
        return "LEASEHOLD"
    return normalized


def _postcode_district(value: Any) -> str | None:
    postcode = _nullable_string(value)
    if postcode is None:
        return None
    return postcode.split(" ", 1)[0].upper()


def _compose_address(row: dict[str, Any]) -> str | None:
    bits = [
        _nullable_string(row.get("address_text")),
        _nullable_string(row.get("street")),
        _nullable_string(row.get("locality")),
        _nullable_string(row.get("town")),
        _nullable_string(row.get("district")),
        _nullable_string(row.get("county")),
        _nullable_string(row.get("postcode")),
    ]
    joined = ", ".join(part for part in bits if part)
    return joined or None
