from __future__ import annotations

import hashlib
import io
import json
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import respx
from httpx import Response
from landintel.data_fetch.http_assets import fetch_http_asset
from landintel.domain.enums import SourceFreshnessStatus, SourceParseStatus
from landintel.domain.models import (
    LpaBoundary,
    MarketIndexSeries,
    MarketSaleComp,
    RawAsset,
    SourceSnapshot,
)
from landintel.geospatial import hmlr_inspire
from landintel.geospatial import official_sources as geospatial_official_sources
from landintel.geospatial.reference_data import ReferenceImportResult
from landintel.planning import official_sources as planning_official_sources
from landintel.planning.import_common import PlanningImportResult
from landintel.valuation import official_sources as valuation_official_sources


def _source_snapshot(
    snapshot_id: uuid.UUID,
    label: str,
    source_family: str = "fixture",
) -> SourceSnapshot:
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()
    return SourceSnapshot(
        id=snapshot_id,
        source_family=source_family,
        source_name=label,
        source_uri=f"file://{label}",
        acquired_at=datetime.now(UTC),
        schema_hash=digest,
        content_hash=digest,
        coverage_note=label,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={"label": label},
    )


@respx.mock
def test_fetch_http_asset_uses_content_type_and_final_url() -> None:
    url = "https://example.test/data.json"
    respx.get(url).mock(
        return_value=Response(
            200,
            json={"ok": True},
            headers={"content-type": "application/json"},
        )
    )

    asset = fetch_http_asset(url, timeout_seconds=5)

    assert asset.requested_url == url
    assert asset.final_url == url
    assert json.loads(asset.content) == {"ok": True}
    assert asset.content_type == "application/json"


@respx.mock
def test_planning_official_source_remote_geojson_updates_provenance(
    seed_reference_data,
    db_session,
    storage,
) -> None:
    del seed_reference_data
    fixture_path = Path(__file__).parent / "fixtures" / "planning" / "brownfield_sites.geojson"
    remote_url = "https://example.test/brownfield.geojson"
    respx.get(remote_url).mock(
        return_value=Response(
            200,
            content=fixture_path.read_bytes(),
            headers={"content-type": "application/geo+json"},
        )
    )

    result = planning_official_sources.import_brownfield_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=remote_url,
    )

    snapshot = db_session.get(SourceSnapshot, result.source_snapshot_id)
    asset = db_session.get(RawAsset, result.raw_asset_id)

    assert snapshot is not None
    assert asset is not None
    assert snapshot.source_uri == remote_url
    assert asset.original_url == remote_url
    assert snapshot.manifest_json["fetch_mode"] == "remote"
    assert result.imported_count > 0
    assert result.coverage_count > 0


@respx.mock
def test_valuation_official_source_remote_csv_updates_provenance(
    seed_reference_data,
    db_session,
    storage,
) -> None:
    del seed_reference_data
    remote_url = "https://example.test/price-paid.csv"
    csv_payload = "\n".join(
        [
            "transaction_unique_identifier,date,price,district,property_type,duration,postcode,street,town,county",
            "CAM-PPD-REMOTE-1,2025-01-15,845000,Camden,FLAT,L,NW1 1AA,"
            "1 Example Mews,London,Greater London",
            "SWK-PPD-REMOTE-1,2025-02-20,910000,Southwark,HOUSE,F,SE1 2BB,"
            "8 Example Road,London,Greater London",
        ]
    )
    respx.get(remote_url).mock(
        return_value=Response(
            200,
            content=csv_payload.encode("utf-8"),
            headers={"content-type": "text/csv"},
        )
    )

    result = valuation_official_sources.import_hmlr_price_paid_fixture(
        session=db_session,
        storage=storage,
        fixture_path=(
            Path(__file__).parent / "fixtures" / "valuation" / "hmlr_price_paid_london.json"
        ),
        requested_by="pytest",
        remote_url=remote_url,
    )

    snapshot = db_session.get(SourceSnapshot, result.source_snapshot_id)
    asset = db_session.get(RawAsset, result.raw_asset_id)

    assert snapshot is not None
    assert asset is not None
    assert snapshot.source_uri == remote_url
    assert asset.original_url == remote_url
    assert snapshot.manifest_json["fetch_mode"] == "remote"
    assert result.imported_count == 2
    assert result.coverage_count == 2


@respx.mock
def test_official_source_falls_back_to_fixture_when_remote_fetch_fails(
    seed_reference_data,
    db_session,
    storage,
) -> None:
    del seed_reference_data
    remote_url = "https://example.test/brownfield.geojson"
    fixture_path = Path(__file__).parent / "fixtures" / "planning" / "brownfield_sites.geojson"
    respx.get(remote_url).mock(return_value=Response(503, text="service unavailable"))

    result = planning_official_sources.import_brownfield_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=remote_url,
    )

    snapshot = db_session.get(SourceSnapshot, result.source_snapshot_id)
    assert snapshot is not None
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"
    assert snapshot.manifest_json["remote_url"] == remote_url
    assert result.imported_count > 0


def test_geospatial_official_source_defaults_to_real_lpa_url_when_enabled(
    monkeypatch,
    test_settings,
) -> None:
    monkeypatch.setattr(
        geospatial_official_sources,
        "get_settings",
        lambda: test_settings.model_copy(update={"real_data_mode": True}),
    )

    assert (
        geospatial_official_sources._configured_remote_url("lpa")
        == geospatial_official_sources.DEFAULT_LPA_REMOTE_URL
    )


@respx.mock
def test_geospatial_official_source_derives_fixture_compatible_borough_ids(
    db_session,
    storage,
) -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "reference"
        / "london_borough_boundaries.geojson"
    )
    remote_url = "https://example.test/lpa-boundaries.geojson"
    payload = json.loads(fixture_path.read_text())
    payload["features"] = [payload["features"][0]]
    payload["features"][0].pop("id", None)
    payload["features"][0]["properties"].pop("borough_id", None)
    respx.get(remote_url).mock(
        return_value=Response(
            200,
            content=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/geo+json"},
        )
    )

    result = geospatial_official_sources.import_lpa_boundaries_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=remote_url,
    )

    snapshot = db_session.get(SourceSnapshot, result.source_snapshot_id)
    assert snapshot is not None
    boundary = db_session.get(LpaBoundary, "camden")
    assert boundary is not None
    assert boundary.external_ref == "E09000007"
    assert snapshot.manifest_json["fetch_mode"] == "remote"


def test_geospatial_official_source_fallback_isolates_remote_db_error_and_preserves_prior_work(
    db_session,
    storage,
    monkeypatch,
    tmp_path,
) -> None:
    fixture_path = tmp_path / "fallback.geojson"
    fixture_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"borough_id": "camden", "name": "Camden"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-0.14, 51.54],
                                    [-0.14, 51.55],
                                    [-0.13, 51.55],
                                    [-0.13, 51.54],
                                    [-0.14, 51.54],
                                ]
                            ],
                        },
                    }
                ],
            }
        )
    )
    attempts: list[Path] = []
    preserved_snapshot_id = uuid.uuid4()
    db_session.add(
        _source_snapshot(
            preserved_snapshot_id,
            "preserved-lpa",
            "reference.lpa_boundary",
        )
    )
    db_session.flush()

    def _fixture_importer(**kwargs) -> ReferenceImportResult:
        del kwargs["storage"], kwargs["requested_by"]
        session = kwargs["session"]
        attempts.append(Path(kwargs["fixture_path"]))
        if len(attempts) == 1:
            duplicate_id = uuid.uuid4()
            session.add(
                _source_snapshot(
                    duplicate_id,
                    "remote-first",
                    "reference.lpa_boundary",
                )
            )
            session.flush()
            session.add(
                _source_snapshot(
                    duplicate_id,
                    "remote-duplicate",
                    "reference.lpa_boundary",
                )
            )
            session.flush()
        fallback_id = uuid.uuid4()
        session.add(_source_snapshot(fallback_id, "fixture-fallback", "reference.lpa_boundary"))
        session.flush()
        return ReferenceImportResult(
            source_snapshot_id=fallback_id,
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
        )

    monkeypatch.setattr(
        geospatial_official_sources,
        "fetch_http_asset",
        lambda remote_url, timeout_seconds: SimpleNamespace(
            content=fixture_path.read_bytes(),
            content_type="application/geo+json",
            final_url=remote_url,
            fetched_at=datetime.now(UTC),
            status_code=200,
        ),
    )

    result = geospatial_official_sources._import_remote_geojson_or_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://example.test/lpa-boundaries.geojson",
        fixture_importer=_fixture_importer,
    )

    assert len(attempts) == 2
    assert attempts[0] != fixture_path
    assert attempts[1] == fixture_path
    snapshot = db_session.get(SourceSnapshot, result.source_snapshot_id)
    assert snapshot is not None
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"
    assert db_session.get(SourceSnapshot, preserved_snapshot_id) is not None


def test_geospatial_official_helper_branches_cover_suffix_and_fallback_noop(
    monkeypatch,
    test_settings,
) -> None:
    monkeypatch.setattr(
        geospatial_official_sources,
        "get_settings",
        lambda: test_settings.model_copy(
            update={
                "real_data_mode": True,
                "geospatial_official_source_urls_json": {"titles": "https://example.test/titles.json"},
            }
        ),
    )

    assert (
        geospatial_official_sources._configured_remote_url("titles")
        == "https://example.test/titles.json"
    )
    assert (
        geospatial_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://example.test/data",
        )
        == ".geojson"
    )
    geospatial_official_sources._annotate_fixture_fallback(
        session=SimpleNamespace(get=lambda *_args, **_kwargs: None),
        source_snapshot_id=uuid.uuid4(),
        remote_url="https://example.test/lpa.geojson",
        fallback_reason="boom",
    )


def test_planning_official_source_fallback_isolates_remote_db_error_and_preserves_prior_work(
    db_session,
    monkeypatch,
    tmp_path,
) -> None:
    fixture_path = tmp_path / "fallback.json"
    fixture_path.write_text("{}")
    preserved_snapshot_id = uuid.uuid4()
    db_session.add(
        _source_snapshot(
            preserved_snapshot_id,
            "preserved-planning",
            "planning.fixture",
        )
    )
    db_session.flush()
    attempts: list[Path] = []

    def _fixture_importer(**kwargs) -> PlanningImportResult:
        del kwargs["storage"], kwargs["requested_by"]
        session = kwargs["session"]
        attempts.append(Path(kwargs["fixture_path"]))
        if len(attempts) == 1:
            duplicate_id = uuid.uuid4()
            session.add(_source_snapshot(duplicate_id, "planning-remote-first", "planning.fixture"))
            session.flush()
            session.add(
                _source_snapshot(duplicate_id, "planning-remote-duplicate", "planning.fixture")
            )
            session.flush()
        fallback_id = uuid.uuid4()
        session.add(_source_snapshot(fallback_id, "planning-fixture-fallback", "planning.fixture"))
        session.flush()
        return PlanningImportResult(
            source_snapshot_id=fallback_id,
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
            coverage_count=0,
        )

    monkeypatch.setattr(
        planning_official_sources,
        "fetch_http_asset",
        lambda remote_url, timeout_seconds: SimpleNamespace(
            content=b"{}",
            content_type="application/json",
            final_url=remote_url,
            fetched_at=datetime.now(UTC),
            status_code=200,
        ),
    )

    result = planning_official_sources._import_remote_json_or_fixture(
        session=db_session,
        storage=SimpleNamespace(),
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://example.test/planning.json",
        fixture_importer=_fixture_importer,
    )

    assert len(attempts) == 2
    assert attempts[0] != fixture_path
    assert attempts[1] == fixture_path
    snapshot = db_session.get(SourceSnapshot, result.source_snapshot_id)
    assert snapshot is not None
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"
    assert db_session.get(SourceSnapshot, preserved_snapshot_id) is not None


def test_planning_official_helper_branches_cover_direct_wrappers_and_suffixes(
    monkeypatch,
    db_session,
    storage,
    test_settings,
    tmp_path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text("{}")
    calls: list[str] = []

    monkeypatch.setattr(
        planning_official_sources.reference_layers_mod,
        "import_constraint_fixture",
        lambda **kwargs: calls.append("constraints")
        or PlanningImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
            coverage_count=1,
        ),
    )
    monkeypatch.setattr(
        planning_official_sources.reference_layers_mod,
        "import_flood_fixture",
        lambda **kwargs: calls.append("flood")
        or PlanningImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
            coverage_count=1,
        ),
    )
    monkeypatch.setattr(
        planning_official_sources.reference_layers_mod,
        "import_heritage_article4_fixture",
        lambda **kwargs: calls.append("heritage")
        or PlanningImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
            coverage_count=1,
        ),
    )
    monkeypatch.setattr(
        planning_official_sources,
        "get_settings",
        lambda: test_settings.model_copy(update={"planning_official_source_urls_json": {}}),
    )

    planning_official_sources.import_constraint_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=None,
    )
    planning_official_sources.import_flood_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=None,
    )
    planning_official_sources.import_heritage_article4_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=None,
    )

    assert calls == ["constraints", "flood", "heritage"]
    monkeypatch.setattr(
        planning_official_sources,
        "get_settings",
        lambda: test_settings.model_copy(
            update={
                "planning_official_source_urls_json": {
                    "constraints": "https://example.test/constraints.json"
                }
            }
        ),
    )
    assert (
        planning_official_sources._configured_remote_url("constraints")
        == "https://example.test/constraints.json"
    )
    assert (
        planning_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://example.test/file",
        )
        == ".json"
    )
    planning_official_sources._annotate_fixture_fallback(
        session=SimpleNamespace(get=lambda *_args, **_kwargs: None),
        source_snapshot_id=uuid.uuid4(),
        remote_url="https://example.test/constraints.json",
        fallback_reason="boom",
    )


def test_valuation_official_source_fallback_isolates_remote_db_error_and_preserves_prior_work(
    seed_reference_data,
    db_session,
    storage,
    monkeypatch,
) -> None:
    del seed_reference_data
    preserved_snapshot_id = uuid.uuid4()
    db_session.add(
        _source_snapshot(
            preserved_snapshot_id,
            "preserved-valuation",
            "valuation.fixture",
        )
    )
    db_session.flush()

    remote_url = "https://example.test/price-paid.csv"
    csv_payload = "\n".join(
        [
            "transaction_unique_identifier,date,price,district,property_type,duration,postcode,street,town,county",
            "CAM-PPD-REMOTE-1,2025-01-15,845000,Camden,FLAT,L,NW1 1AA,"
            "1 Example Mews,London,Greater London",
        ]
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "fetch_http_asset",
        lambda url, timeout_seconds: SimpleNamespace(
            content=csv_payload.encode("utf-8"),
            content_type="text/csv",
            final_url=url,
            fetched_at=datetime.now(UTC),
            status_code=200,
        ),
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_upsert_hmlr_price_paid_rows",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("malformed remote row")),
    )

    result = valuation_official_sources.import_hmlr_price_paid_fixture(
        session=db_session,
        storage=storage,
        fixture_path=(
            Path(__file__).parent / "fixtures" / "valuation" / "hmlr_price_paid_london.json"
        ),
        requested_by="pytest",
        remote_url=remote_url,
    )

    snapshot = db_session.get(SourceSnapshot, result.source_snapshot_id)
    assert snapshot is not None
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"
    assert db_session.get(SourceSnapshot, preserved_snapshot_id) is not None
    source_snapshot_ids = {
        row[0]
        for row in db_session.query(MarketSaleComp.source_snapshot_id).distinct().all()
    }
    assert source_snapshot_ids == {result.source_snapshot_id}


def test_valuation_official_helper_parsers_and_scalar_helpers() -> None:
    assert valuation_official_sources._parse_hmlr_price_paid_payload(
        json.dumps({"sales": [{"transaction_ref": "sale-1"}]}).encode("utf-8"),
        "application/json",
    ) == [{"transaction_ref": "sale-1"}]
    assert valuation_official_sources._parse_hmlr_price_paid_payload(
        (
            b"transaction_unique_identifier,date,price,district,street,town,county,postcode\n"
            b"sale-2,2025-01-01,100000,Camden,Example Street,London,Greater London,NW1 1AA\n"
        ),
        "text/csv",
    )[0]["transaction_ref"] == "sale-2"
    with pytest.raises(ValueError, match="row list"):
        valuation_official_sources._parse_hmlr_price_paid_payload(
            json.dumps({"sales": "bad"}).encode("utf-8"),
            "application/json",
        )

    assert valuation_official_sources._parse_ukhpi_payload(
        json.dumps({"index_rows": [{"borough_id": "camden"}]}).encode("utf-8"),
        "application/json",
    ) == [{"borough_id": "camden"}]
    assert valuation_official_sources._parse_ukhpi_payload(
        b"RegionName,Date,Index\nCamden,2025-01-01,123.4\n",
        "text/csv",
    )[0]["index_value"] == "123.4"
    with pytest.raises(ValueError, match="row list"):
        valuation_official_sources._parse_ukhpi_payload(
            json.dumps({"rows": "bad"}).encode("utf-8"),
            "application/json",
        )

    assert (
        valuation_official_sources._suffix_for_content_type(
            "text/csv",
            "https://x.test/feed",
        )
        == ".csv"
    )
    assert (
        valuation_official_sources._suffix_for_content_type(
            "application/json",
            "https://x.test/feed",
        )
        == ".json"
    )
    assert (
        valuation_official_sources._asset_type_for_content_type("application/octet-stream")
        == "OFFICIAL_DATA"
    )
    assert (
        valuation_official_sources._slugify("London Borough of Camden")
        == "londonboroughofcamden"
    )
    assert valuation_official_sources._slugify("   ") is None
    assert valuation_official_sources._nullable_string("  example  ") == "example"
    assert valuation_official_sources._nullable_string(None) is None
    assert valuation_official_sources._parse_date(date(2025, 1, 1)) == date(2025, 1, 1)
    with pytest.raises(ValueError, match="required"):
        valuation_official_sources._parse_date("")
    assert valuation_official_sources._parse_float("") is None
    assert valuation_official_sources._parse_float("3.5") == 3.5
    assert valuation_official_sources._map_tenure("f") == "FREEHOLD"
    assert valuation_official_sources._map_tenure("l") == "LEASEHOLD"
    assert valuation_official_sources._map_tenure("custom") == "CUSTOM"
    assert valuation_official_sources._postcode_district("nw1 1aa") == "NW1"
    assert (
        valuation_official_sources._compose_address(
            {
                "street": "Example Street",
                "town": "London",
                "county": "Greater London",
                "postcode": "NW1 1AA",
            }
        )
        == "Example Street, London, Greater London, NW1 1AA"
    )


def test_valuation_official_helpers_cover_snapshot_reuse_and_upserts(
    seed_reference_data,
    db_session,
    storage,
) -> None:
    del seed_reference_data
    raw_bytes = b'{"rows":[]}'
    snapshot, asset = valuation_official_sources._register_remote_snapshot(
        session=db_session,
        storage=storage,
        raw_bytes=raw_bytes,
        content_type="application/json",
        dataset_key="valuation-test",
        source_family="UKHPI",
        source_name="valuation-test",
        schema_key="schema-v1",
        coverage_note="coverage",
        requested_by="pytest",
        remote_url="https://example.test/valuation.json",
    )
    existing_snapshot, existing_asset = valuation_official_sources._register_remote_snapshot(
        session=db_session,
        storage=storage,
        raw_bytes=raw_bytes,
        content_type="application/json",
        dataset_key="valuation-test",
        source_family="UKHPI",
        source_name="valuation-test",
        schema_key="schema-v1",
        coverage_note="coverage",
        requested_by="pytest",
        remote_url="https://example.test/valuation.json",
    )

    assert existing_snapshot.id == snapshot.id
    assert existing_asset.id == asset.id

    hmlr_rows = [
        {
            "transaction_ref": "sale-1",
            "district": "Camden",
            "sale_date": "2025-01-01",
            "price_gbp": "100000",
            "property_type": "HOUSE",
            "tenure": "L",
            "postcode": "NW1 1AA",
        },
        {
            "transaction_ref": "sale-2",
            "district": "Missing Borough",
            "sale_date": "2025-02-01",
            "price_gbp": "110000",
            "property_type": "FLAT",
            "tenure": "F",
            "postcode": "ZZ1 1ZZ",
        },
    ]
    imported_sales = valuation_official_sources._upsert_hmlr_price_paid_rows(
        session=db_session,
        snapshot=snapshot,
        raw_asset_id=asset.id,
        rows=hmlr_rows,
    )
    coverage_sales = valuation_official_sources._upsert_hmlr_coverage_snapshots(
        session=db_session,
        snapshot=snapshot,
        rows=hmlr_rows,
    )
    imported_index = valuation_official_sources._upsert_ukhpi_rows(
        session=db_session,
        snapshot=snapshot,
        raw_asset_id=asset.id,
        rows=[
            {"borough_id": "camden", "period_month": "2025-01-01", "index_value": "123.4"},
            {"borough_id": "missing", "period_month": "2025-02-01", "index_value": "124.4"},
        ],
    )
    coverage_index = valuation_official_sources._upsert_ukhpi_coverage_snapshots(
        session=db_session,
        snapshot=snapshot,
        rows=[
            {"borough_id": "camden"},
            {"borough_id": "missing"},
        ],
    )

    assert imported_sales == 2
    assert imported_index == 2
    assert coverage_sales == 1
    assert coverage_index == 1
    db_session.flush()
    assert db_session.query(MarketSaleComp).count() == 2
    assert db_session.query(MarketIndexSeries).count() == 2

    valuation_official_sources._annotate_fixture_fallback(
        session=SimpleNamespace(get=lambda *_args, **_kwargs: None),
        source_snapshot_id=uuid.uuid4(),
        remote_url="https://example.test/fallback.json",
        fallback_reason="boom",
    )


def test_valuation_official_import_branches_cover_fallback_and_direct_fixture_paths(
    monkeypatch,
    db_session,
    storage,
    test_settings,
    tmp_path,
) -> None:
    fixture_path = tmp_path / "valuation.json"
    fixture_path.write_text("[]")
    fallback_snapshot_id = uuid.uuid4()
    direct_snapshot_id = uuid.uuid4()

    monkeypatch.setattr(
        valuation_official_sources.valuation_market_mod,
        "import_hmlr_price_paid_fixture",
        lambda **kwargs: PlanningImportResult(
            source_snapshot_id=fallback_snapshot_id,
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
            coverage_count=1,
        ),
    )
    monkeypatch.setattr(
        valuation_official_sources.valuation_market_mod,
        "import_ukhpi_fixture",
        lambda **kwargs: PlanningImportResult(
            source_snapshot_id=direct_snapshot_id,
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
            coverage_count=1,
        ),
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "fetch_http_asset",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "get_settings",
        lambda: test_settings.model_copy(
            update={"valuation_official_source_urls_json": {"ukhpi": "https://example.test/ukhpi.json"}}
        ),
    )

    fallback_result = valuation_official_sources.import_hmlr_price_paid_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://example.test/hmlr.csv",
    )
    direct_result = valuation_official_sources.import_ukhpi_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=None,
    )

    assert fallback_result.source_snapshot_id == fallback_snapshot_id
    assert direct_result.source_snapshot_id == direct_snapshot_id
    assert (
        valuation_official_sources._configured_remote_url("ukhpi")
        == "https://example.test/ukhpi.json"
    )


def test_hmlr_inspire_helper_branches_cover_shortcuts_and_parsing(monkeypatch) -> None:
    settings = SimpleNamespace(real_data_mode=False)
    monkeypatch.setattr(hmlr_inspire, "get_settings", lambda: settings)
    assert (
        hmlr_inspire.maybe_import_title_union_for_listing_point(
            session=SimpleNamespace(),
            authority_name="Camden",
            lat=51.5,
            lon=-0.1,
            requested_by="pytest",
        )
        is None
    )
    assert hmlr_inspire._normalize_authority_label("  ") is None
    assert (
        hmlr_inspire._normalize_authority_label("london borough of camden")
        == "London Borough of Camden"
    )
    assert (
        hmlr_inspire._slugify_authority_label("London Borough of Camden")
        == "London_Borough_of_Camden"
    )
    assert hmlr_inspire._polygon_from_pos_list("1 2 3") is None
    assert hmlr_inspire._polygon_from_pos_list("0 0 0 1 1 1 0 0") is not None
    element = ET.fromstring(
        "<root xmlns:LR='www.landregistry.gov.uk'>"
        "<LR:INSPIREID>ABC</LR:INSPIREID>"
        "</root>"
    )
    assert hmlr_inspire._child_text(element, "LR:INSPIREID") == "ABC"
    assert hmlr_inspire._child_text(element, "LR:MISSING") is None


def test_hmlr_inspire_snapshot_and_iter_helpers_cover_existing_and_empty_paths(
    db_session,
    storage,
    monkeypatch,
) -> None:
    monkeypatch.setattr(hmlr_inspire, "build_storage", lambda settings: storage)
    zip_bytes = b"zip-bytes"
    snapshot, raw_asset = hmlr_inspire._register_snapshot(
        session=db_session,
        authority_label="Camden",
        download_url="https://example.test/camden.zip",
        zip_bytes=zip_bytes,
        requested_by="pytest",
    )
    existing_snapshot, existing_asset = hmlr_inspire._register_snapshot(
        session=db_session,
        authority_label="Camden",
        download_url="https://example.test/camden.zip",
        zip_bytes=zip_bytes,
        requested_by="pytest",
    )
    assert existing_snapshot.id == snapshot.id
    assert existing_asset.id == raw_asset.id

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("readme.txt", "no gml")
    assert (
        list(
            hmlr_inspire._iter_matching_polygons(
                zip_bytes=archive_buffer.getvalue(),
                point_geometry_27700=(
                    hmlr_inspire.build_point_geometry(lat=51.5, lon=-0.1).geom_27700
                ),
            )
        )
        == []
    )

    class _FakeResponse:
        content = b"payload"

        def raise_for_status(self) -> None:
            return None

    class _FakeScraper:
        def get(self, download_url, allow_redirects, timeout):
            assert download_url == "https://example.test/camden.zip"
            assert allow_redirects is True
            assert timeout == 60
            return _FakeResponse()

    monkeypatch.setattr(
        hmlr_inspire.cloudscraper,
        "create_scraper",
        lambda **kwargs: _FakeScraper(),
    )
    hmlr_inspire._download_hmlr_zip.cache_clear()
    assert hmlr_inspire._download_hmlr_zip("https://example.test/camden.zip") == b"payload"
