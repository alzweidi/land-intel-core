from __future__ import annotations

from pathlib import Path
from uuid import UUID

from landintel.assessments.service import build_assessment_artifacts_for_run
from landintel.valuation.assumptions import ensure_default_assumption_set
from landintel.valuation.market import import_land_comp_fixture
from landintel.valuation.official_sources import (
    import_hmlr_price_paid_fixture,
    import_ukhpi_fixture,
)

FIXTURES_ROOT = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "valuation"
)


def run_valuation_data_refresh_job(*, session, job, storage) -> None:
    dataset = str(job.payload_json.get("dataset") or "all")
    requested_by = job.requested_by or "worker"
    result: dict[str, object] = {"dataset": dataset}
    if dataset in {"all", "assumptions"}:
        assumption_set = ensure_default_assumption_set(session)
        result["assumption_set_version"] = assumption_set.version
    if dataset in {"all", "hmlr-price-paid"}:
        summary = import_hmlr_price_paid_fixture(
            session=session,
            storage=storage,
            fixture_path=FIXTURES_ROOT / "hmlr_price_paid_london.json",
            requested_by=requested_by,
        )
        result["hmlr_price_paid"] = {
            "source_snapshot_id": str(summary.source_snapshot_id),
            "raw_asset_id": str(summary.raw_asset_id),
            "imported_count": summary.imported_count,
        }
    if dataset in {"all", "ukhpi"}:
        summary = import_ukhpi_fixture(
            session=session,
            storage=storage,
            fixture_path=FIXTURES_ROOT / "ukhpi_london.json",
            requested_by=requested_by,
        )
        result["ukhpi"] = {
            "source_snapshot_id": str(summary.source_snapshot_id),
            "raw_asset_id": str(summary.raw_asset_id),
            "imported_count": summary.imported_count,
        }
    if dataset in {"all", "land-comps"}:
        summary = import_land_comp_fixture(
            session=session,
            storage=storage,
            fixture_path=FIXTURES_ROOT / "land_comps_london.json",
            requested_by=requested_by,
        )
        result["land_comps"] = {
            "source_snapshot_id": str(summary.source_snapshot_id),
            "raw_asset_id": str(summary.raw_asset_id),
            "imported_count": summary.imported_count,
        }
    job.payload_json = {**job.payload_json, "result": result}
    session.flush()


def run_valuation_run_build_job(*, session, job, storage) -> None:
    assessment_id = UUID(str(job.payload_json["assessment_id"]))
    build_assessment_artifacts_for_run(
        session=session,
        assessment_run_id=assessment_id,
        requested_by=job.requested_by or "worker",
        storage=storage,
    )
    session.flush()
