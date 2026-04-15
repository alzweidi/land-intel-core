from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from landintel.domain.enums import MarketLandCompSourceType, ProposalForm, SourceFreshnessStatus
from landintel.domain.models import MarketIndexSeries, MarketLandComp, MarketSaleComp
from landintel.planning.import_common import (
    PlanningImportResult,
    register_dataset_snapshot,
    upsert_coverage_snapshots,
)
from landintel.storage.base import StorageAdapter

VALUATION_MARKET_NAMESPACE = uuid.UUID("df8ff428-4260-4a9b-82bd-135f77f95dfa")


@dataclass(slots=True)
class SalesCompSummary:
    count: int
    price_per_sqm_low: float | None
    price_per_sqm_mid: float | None
    price_per_sqm_high: float | None
    source_snapshot_ids: set[str]
    raw_asset_ids: set[str]


@dataclass(slots=True)
class LandCompSummary:
    count: int
    post_permission_value_low: float | None
    post_permission_value_mid: float | None
    post_permission_value_high: float | None
    fallback_path: str
    source_snapshot_ids: set[str]
    raw_asset_ids: set[str]


def import_hmlr_price_paid_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
) -> PlanningImportResult:
    snapshot, asset, payload = register_dataset_snapshot(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="valuation_hmlr_price_paid",
        source_family="HMLR_PRICE_PAID",
        source_name="HMLR Price Paid fixture",
        schema_key="valuation_hmlr_price_paid_v1",
        coverage_note="Fixture-scale London HMLR Price Paid evidence for Phase 7A.",
        freshness_status=SourceFreshnessStatus.FRESH,
        requested_by=requested_by,
    )
    coverage_count = upsert_coverage_snapshots(
        session=session,
        source_snapshot=snapshot,
        coverage_rows=list((payload.get("meta") or {}).get("coverage") or []),
    )
    imported = 0
    for row in list(payload.get("sales") or []):
        transaction_ref = str(row["transaction_ref"])
        entry_id = uuid.uuid5(VALUATION_MARKET_NAMESPACE, f"sale:{transaction_ref}")
        entry = session.get(MarketSaleComp, entry_id)
        if entry is None:
            entry = MarketSaleComp(id=entry_id, transaction_ref=transaction_ref)
            session.add(entry)
        entry.borough_id = _nullable_string(row.get("borough_id"))
        entry.source_snapshot_id = snapshot.id
        entry.raw_asset_id = asset.id
        entry.sale_date = _parse_date(row.get("sale_date"))
        entry.price_gbp = int(row.get("price_gbp") or 0)
        entry.property_type = str(row.get("property_type") or "UNKNOWN")
        entry.tenure = _nullable_string(row.get("tenure"))
        entry.postcode_district = _nullable_string(row.get("postcode_district"))
        entry.address_text = _nullable_string(row.get("address_text"))
        entry.floor_area_sqm = _parse_float(row.get("floor_area_sqm"))
        entry.rebased_price_per_sqm_hint = _parse_float(row.get("rebased_price_per_sqm_hint"))
        entry.raw_record_json = dict(row)
        imported += 1
    session.flush()
    return PlanningImportResult(
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        imported_count=imported,
        coverage_count=coverage_count,
    )


def import_ukhpi_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
) -> PlanningImportResult:
    snapshot, asset, payload = register_dataset_snapshot(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="valuation_ukhpi",
        source_family="UKHPI",
        source_name="UKHPI fixture",
        schema_key="valuation_ukhpi_v1",
        coverage_note="Fixture-scale UKHPI index series for Phase 7A rebasing.",
        freshness_status=SourceFreshnessStatus.FRESH,
        requested_by=requested_by,
    )
    coverage_count = upsert_coverage_snapshots(
        session=session,
        source_snapshot=snapshot,
        coverage_rows=list((payload.get("meta") or {}).get("coverage") or []),
    )
    imported = 0
    for row in list(payload.get("index_rows") or []):
        borough_id = _nullable_string(row.get("borough_id"))
        period_month = _parse_date(row.get("period_month"))
        index_key = str(row.get("index_key") or "UKHPI")
        entry_id = uuid.uuid5(
            VALUATION_MARKET_NAMESPACE,
            f"ukhpi:{borough_id or 'london'}:{index_key}:{period_month.isoformat()}",
        )
        entry = session.get(MarketIndexSeries, entry_id)
        if entry is None:
            entry = MarketIndexSeries(id=entry_id)
            session.add(entry)
        entry.borough_id = borough_id
        entry.index_key = index_key
        entry.period_month = period_month
        entry.index_value = float(row.get("index_value") or 0.0)
        entry.source_snapshot_id = snapshot.id
        entry.raw_asset_id = asset.id
        entry.raw_record_json = dict(row)
        imported += 1
    session.flush()
    return PlanningImportResult(
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        imported_count=imported,
        coverage_count=coverage_count,
    )


def import_land_comp_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
) -> PlanningImportResult:
    snapshot, asset, payload = register_dataset_snapshot(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="valuation_land_comps",
        source_family="MARKET_LAND_COMP",
        source_name="Permissioned land and benchmark fixture",
        schema_key="valuation_land_comp_v1",
        coverage_note="Fixture-scale permissioned land, auction, and analyst benchmark evidence.",
        freshness_status=SourceFreshnessStatus.FRESH,
        requested_by=requested_by,
    )
    coverage_count = upsert_coverage_snapshots(
        session=session,
        source_snapshot=snapshot,
        coverage_rows=list((payload.get("meta") or {}).get("coverage") or []),
    )
    imported = 0
    for row in list(payload.get("comparables") or []):
        comp_ref = str(row["comp_ref"])
        entry_id = uuid.uuid5(VALUATION_MARKET_NAMESPACE, f"land-comp:{comp_ref}")
        entry = session.get(MarketLandComp, entry_id)
        if entry is None:
            entry = MarketLandComp(id=entry_id, comp_ref=comp_ref)
            session.add(entry)
        entry.borough_id = _nullable_string(row.get("borough_id"))
        entry.template_key = _nullable_string(row.get("template_key"))
        proposal_form = _nullable_string(row.get("proposal_form"))
        entry.proposal_form = None if proposal_form is None else ProposalForm(proposal_form)
        entry.comp_source_type = MarketLandCompSourceType(str(row["comp_source_type"]))
        entry.evidence_date = (
            _parse_date(row.get("evidence_date"))
            if row.get("evidence_date")
            else None
        )
        entry.unit_count = _parse_int(row.get("unit_count"))
        entry.site_area_sqm = _parse_float(row.get("site_area_sqm"))
        entry.post_permission_value_low = _parse_float(row.get("post_permission_value_low"))
        entry.post_permission_value_mid = _parse_float(row.get("post_permission_value_mid"))
        entry.post_permission_value_high = _parse_float(row.get("post_permission_value_high"))
        entry.source_url = _nullable_string(row.get("source_url"))
        entry.source_snapshot_id = snapshot.id
        entry.raw_asset_id = asset.id
        entry.raw_record_json = dict(row)
        imported += 1
    session.flush()
    return PlanningImportResult(
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        imported_count=imported,
        coverage_count=coverage_count,
    )


def rebase_price_with_ukhpi(
    *,
    session: Session,
    borough_id: str | None,
    price_gbp: float,
    sale_date: date,
    as_of_date: date,
) -> float:
    sale_index = _resolve_index_value(
        session=session,
        borough_id=borough_id,
        period_month=_month_start(sale_date),
    )
    as_of_index = _resolve_index_value(
        session=session,
        borough_id=borough_id,
        period_month=_month_start(as_of_date),
    )
    if sale_index is None or as_of_index is None or sale_index <= 0:
        return float(price_gbp)
    return float(price_gbp) * (as_of_index / sale_index)


def build_sales_comp_summary(
    *,
    session: Session,
    borough_id: str | None,
    as_of_date: date,
    max_age_months: int,
    limit: int = 6,
) -> SalesCompSummary:
    min_date = date(as_of_date.year - (max_age_months // 12), max(1, as_of_date.month), 1)
    rows = session.execute(
        select(MarketSaleComp)
        .where(
            MarketSaleComp.sale_date <= as_of_date,
            MarketSaleComp.sale_date >= min_date,
            or_(MarketSaleComp.borough_id == borough_id, MarketSaleComp.borough_id.is_(None)),
        )
        .order_by(
            (MarketSaleComp.borough_id == borough_id).desc(),
            MarketSaleComp.sale_date.desc(),
        )
        .limit(limit)
    ).scalars().all()
    ppsm_values: list[float] = []
    source_snapshot_ids: set[str] = set()
    raw_asset_ids: set[str] = set()
    for row in rows:
        source_snapshot_ids.add(str(row.source_snapshot_id))
        raw_asset_ids.add(str(row.raw_asset_id))
        rebased_price = rebase_price_with_ukhpi(
            session=session,
            borough_id=row.borough_id,
            price_gbp=float(row.price_gbp),
            sale_date=row.sale_date,
            as_of_date=as_of_date,
        )
        if row.floor_area_sqm and row.floor_area_sqm > 0:
            ppsm_values.append(rebased_price / float(row.floor_area_sqm))
        elif row.rebased_price_per_sqm_hint:
            ppsm_values.append(float(row.rebased_price_per_sqm_hint))
    if not ppsm_values:
        return SalesCompSummary(0, None, None, None, source_snapshot_ids, raw_asset_ids)
    midpoint = median(ppsm_values)
    return SalesCompSummary(
        count=len(ppsm_values),
        price_per_sqm_low=round(midpoint * 0.94, 2),
        price_per_sqm_mid=round(midpoint, 2),
        price_per_sqm_high=round(midpoint * 1.06, 2),
        source_snapshot_ids=source_snapshot_ids,
        raw_asset_ids=raw_asset_ids,
    )


def build_land_comp_summary(
    *,
    session: Session,
    borough_id: str | None,
    template_key: str,
    proposal_form: ProposalForm | None,
    as_of_date: date,
    limit: int = 6,
) -> LandCompSummary:
    same_borough_rows = session.execute(
        select(MarketLandComp)
        .where(
            MarketLandComp.evidence_date <= as_of_date,
            MarketLandComp.borough_id == borough_id,
            MarketLandComp.template_key == template_key,
        )
        .order_by(MarketLandComp.evidence_date.desc())
        .limit(limit)
    ).scalars().all()
    fallback_path = "same_borough_same_template"
    rows = same_borough_rows
    if not rows:
        rows = session.execute(
            select(MarketLandComp)
            .where(
                MarketLandComp.evidence_date <= as_of_date,
                MarketLandComp.template_key == template_key,
            )
            .order_by(MarketLandComp.evidence_date.desc())
            .limit(limit)
        ).scalars().all()
        fallback_path = "london_same_template"
    if not rows and proposal_form is not None:
        rows = session.execute(
            select(MarketLandComp)
            .where(
                MarketLandComp.evidence_date <= as_of_date,
                MarketLandComp.proposal_form == proposal_form,
            )
            .order_by(MarketLandComp.evidence_date.desc())
            .limit(limit)
        ).scalars().all()
        fallback_path = "proposal_form_fallback"

    source_snapshot_ids: set[str] = set()
    raw_asset_ids: set[str] = set()
    lows: list[float] = []
    mids: list[float] = []
    highs: list[float] = []
    for row in rows:
        source_snapshot_ids.add(str(row.source_snapshot_id))
        raw_asset_ids.add(str(row.raw_asset_id))
        if row.post_permission_value_low is not None:
            lows.append(float(row.post_permission_value_low))
        if row.post_permission_value_mid is not None:
            mids.append(float(row.post_permission_value_mid))
        if row.post_permission_value_high is not None:
            highs.append(float(row.post_permission_value_high))
    if not mids:
        return LandCompSummary(
            count=0,
            post_permission_value_low=None,
            post_permission_value_mid=None,
            post_permission_value_high=None,
            fallback_path=fallback_path,
            source_snapshot_ids=source_snapshot_ids,
            raw_asset_ids=raw_asset_ids,
        )
    return LandCompSummary(
        count=len(mids),
        post_permission_value_low=round(median(lows or mids), 2),
        post_permission_value_mid=round(median(mids), 2),
        post_permission_value_high=round(median(highs or mids), 2),
        fallback_path=fallback_path,
        source_snapshot_ids=source_snapshot_ids,
        raw_asset_ids=raw_asset_ids,
    )


def _resolve_index_value(
    *,
    session: Session,
    borough_id: str | None,
    period_month: date,
) -> float | None:
    exact = session.execute(
        select(MarketIndexSeries)
        .where(
            MarketIndexSeries.index_key == "UKHPI",
            MarketIndexSeries.period_month <= period_month,
            MarketIndexSeries.borough_id == borough_id,
        )
        .order_by(MarketIndexSeries.period_month.desc())
        .limit(1)
    ).scalar_one_or_none()
    if exact is not None:
        return float(exact.index_value)
    fallback = session.execute(
        select(MarketIndexSeries)
        .where(
            MarketIndexSeries.index_key == "UKHPI",
            MarketIndexSeries.period_month <= period_month,
            MarketIndexSeries.borough_id.is_(None),
        )
        .order_by(MarketIndexSeries.period_month.desc())
        .limit(1)
    ).scalar_one_or_none()
    if fallback is None:
        return None
    return float(fallback.index_value)


def _month_start(value: date | datetime) -> date:
    return date(value.year, value.month, 1)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _parse_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return int(value)
