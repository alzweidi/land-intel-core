from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from landintel.domain.models import RawAsset, SourceSnapshot
from landintel.planning.import_common import PlanningImportResult
from landintel.valuation import official_sources as valuation_official_sources


def test_valuation_official_source_entrypoint_branches_cover_direct_paths(monkeypatch) -> None:
    direct_hmlr = PlanningImportResult(
        source_snapshot_id=uuid.uuid4(),
        raw_asset_id=uuid.uuid4(),
        imported_count=1,
        coverage_count=1,
    )
    direct_ukhpi = PlanningImportResult(
        source_snapshot_id=uuid.uuid4(),
        raw_asset_id=uuid.uuid4(),
        imported_count=2,
        coverage_count=2,
    )
    monkeypatch.setattr(
        valuation_official_sources.valuation_market_mod,
        "import_hmlr_price_paid_fixture",
        lambda **kwargs: direct_hmlr,
    )
    monkeypatch.setattr(
        valuation_official_sources.valuation_market_mod,
        "import_ukhpi_fixture",
        lambda **kwargs: direct_ukhpi,
    )

    assert (
        valuation_official_sources.import_hmlr_price_paid_fixture(
            session=SimpleNamespace(),
            storage=SimpleNamespace(),
            fixture_path="fixture.json",
            requested_by="pytest",
            remote_url=None,
        )
        == direct_hmlr
    )
    assert (
        valuation_official_sources.import_ukhpi_fixture(
            session=SimpleNamespace(),
            storage=SimpleNamespace(),
            fixture_path="fixture.json",
            requested_by="pytest",
            remote_url=None,
        )
        == direct_ukhpi
    )


def test_valuation_official_source_helper_branches_cover_remaining_edges(
    seed_reference_data,
    db_session,
    storage,
    monkeypatch,
) -> None:
    del seed_reference_data

    class _NestedScope:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    assert isinstance(
        valuation_official_sources._begin_nested_if_supported(
            SimpleNamespace(begin_nested=lambda: _NestedScope())
        ),
        _NestedScope,
    )
    with valuation_official_sources._begin_nested_if_supported(SimpleNamespace()):
        pass

    monkeypatch.setattr(
        valuation_official_sources,
        "get_settings",
        lambda: SimpleNamespace(
            valuation_official_source_urls_json={"hmlr_price_paid": "https://remote.test/hmlr.csv"}
        ),
    )
    assert (
        valuation_official_sources._configured_remote_url("hmlr_price_paid")
        == "https://remote.test/hmlr.csv"
    )
    assert valuation_official_sources._configured_remote_url("ukhpi") is None

    raw_bytes = b'{"rows":[]}'
    snapshot, asset = valuation_official_sources._register_remote_snapshot(
        session=db_session,
        storage=storage,
        raw_bytes=raw_bytes,
        content_type="application/octet-stream",
        dataset_key="valuation-coverage",
        source_family="UKHPI",
        source_name="valuation-coverage",
        schema_key="schema-v1",
        coverage_note="coverage",
        requested_by="pytest",
        remote_url="https://remote.test/download",
    )
    reused_snapshot, reused_asset = valuation_official_sources._register_remote_snapshot(
        session=db_session,
        storage=storage,
        raw_bytes=raw_bytes,
        content_type="application/octet-stream",
        dataset_key="valuation-coverage",
        source_family="UKHPI",
        source_name="valuation-coverage",
        schema_key="schema-v1",
        coverage_note="coverage",
        requested_by="pytest",
        remote_url="https://remote.test/download",
    )
    assert reused_snapshot.id == snapshot.id
    assert reused_asset.id == asset.id
    assert asset.asset_type == "OFFICIAL_DATA"
    assert asset.storage_path.endswith(".csv")

    assert (
        valuation_official_sources._upsert_hmlr_price_paid_rows(
            session=db_session,
            snapshot=snapshot,
            raw_asset_id=asset.id,
            rows=[],
        )
        == 0
    )
    assert (
        valuation_official_sources._upsert_ukhpi_rows(
            session=db_session,
            snapshot=snapshot,
            raw_asset_id=asset.id,
            rows=[],
        )
        == 0
    )

    assert (
        valuation_official_sources._upsert_hmlr_price_paid_rows(
            session=db_session,
            snapshot=snapshot,
            raw_asset_id=asset.id,
            rows=[
                {
                    "transaction_id": "txn-1",
                    "district_name": "Camden",
                    "completion_date": "2025-01-15",
                    "Price": "100000",
                    "Property Type": "HOUSE",
                    "Duration": "F",
                    "Postcode": "NW1 1AA",
                    "street": "1 Example Mews",
                    "town": "London",
                    "county": "Greater London",
                }
            ],
        )
        == 1
    )
    assert (
        valuation_official_sources._upsert_hmlr_price_paid_rows(
            session=db_session,
            snapshot=snapshot,
            raw_asset_id=asset.id,
            rows=[
                {
                    "transaction_ref": "txn-1",
                    "borough_id": "Southwark",
                    "sale_date": "2025-02-01",
                    "price_gbp": "120000",
                    "property_type": "FLAT",
                    "tenure": "L",
                    "postcode_district": "SE1",
                    "address_text": "Updated address",
                    "rebased_price_per_sqm_hint": "12.5",
                }
            ],
        )
        == 1
    )
    assert (
        valuation_official_sources._upsert_ukhpi_rows(
            session=db_session,
            snapshot=snapshot,
            raw_asset_id=asset.id,
            rows=[
                {
                    "area_code": "Camden",
                    "month": "2025-03-01",
                    "index": "130.5",
                }
            ],
        )
        == 1
    )
    assert (
        valuation_official_sources._upsert_ukhpi_rows(
            session=db_session,
            snapshot=snapshot,
            raw_asset_id=asset.id,
            rows=[
                {
                    "RegionName": "Camden",
                    "IndexKey": "UKHPI",
                    "Date": "2025-03-01",
                    "Index": "131.5",
                }
            ],
        )
        == 1
    )

    assert (
        valuation_official_sources._upsert_hmlr_coverage_snapshots(
            session=db_session,
            snapshot=snapshot,
            rows=[
                {"district": "Camden"},
                {"RegionName": "Unknown"},
            ],
        )
        == 1
    )
    assert (
        valuation_official_sources._upsert_hmlr_coverage_snapshots(
            session=db_session,
            snapshot=snapshot,
            rows=[],
        )
        == 0
    )
    assert (
        valuation_official_sources._upsert_ukhpi_coverage_snapshots(
            session=db_session,
            snapshot=snapshot,
            rows=[
                {"region_name": "Camden"},
                {"borough_id": "Missing"},
            ],
        )
        == 1
    )
    assert (
        valuation_official_sources._upsert_ukhpi_coverage_snapshots(
            session=db_session,
            snapshot=snapshot,
            rows=[],
        )
        == 0
    )

    assert valuation_official_sources._parse_hmlr_price_paid_payload(
        b'{"rows":[{"transaction_ref":"json-sale"}]}',
        "application/json",
    ) == [{"transaction_ref": "json-sale"}]
    assert valuation_official_sources._parse_hmlr_price_paid_payload(
        b"transaction_unique_identifier,date,price\n",
        "text/csv",
    ) == []
    with pytest.raises(ValueError, match="row list"):
        valuation_official_sources._parse_hmlr_price_paid_payload(
            b'{"rows":{"bad":true}}',
            "application/json",
        )

    assert valuation_official_sources._parse_ukhpi_payload(
        b'{"index_rows":[{"borough_id":"camden"}]}',
        "application/json",
    ) == [{"borough_id": "camden"}]
    assert valuation_official_sources._parse_ukhpi_payload(
        b"borough_id,Date,Index\n",
        "text/csv",
    ) == []
    with pytest.raises(ValueError, match="row list"):
        valuation_official_sources._parse_ukhpi_payload(
            b'{"rows":{"bad":true}}',
            "application/json",
        )

    valuation_official_sources._annotate_fixture_fallback(
        session=db_session,
        source_snapshot_id=snapshot.id,
        remote_url="https://remote.test/download",
        fallback_reason="boom",
    )
    valuation_official_sources._annotate_fixture_fallback(
        session=SimpleNamespace(get=lambda *_args, **_kwargs: None),
        source_snapshot_id=uuid.uuid4(),
        remote_url="https://remote.test/download",
        fallback_reason="boom",
    )
    stored_snapshot = db_session.get(SourceSnapshot, snapshot.id)
    assert stored_snapshot is not None
    assert stored_snapshot.manifest_json["fetch_mode"] == "fixture_fallback"

    assert (
        valuation_official_sources._suffix_for_content_type(
            "text/csv",
            "https://x.test/file",
        )
        == ".csv"
    )
    assert (
        valuation_official_sources._suffix_for_content_type(
            "application/json",
            "https://x.test/file",
        )
        == ".json"
    )
    assert (
        valuation_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file.data",
        )
        == ".data"
    )
    assert (
        valuation_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file",
        )
        == ".csv"
    )
    assert valuation_official_sources._asset_type_for_content_type("text/csv") == "CSV"
    assert valuation_official_sources._asset_type_for_content_type("application/json") == "JSON"
    assert (
        valuation_official_sources._asset_type_for_content_type("application/octet-stream")
        == "OFFICIAL_DATA"
    )
    assert len(valuation_official_sources._sha256(b"abc")) == 64
    assert valuation_official_sources._slugify(" Camden / Borough ") == "camdenborough"
    assert valuation_official_sources._slugify("   ") is None
    assert valuation_official_sources._slugify(None) is None
    assert valuation_official_sources._nullable_string("  hi  ") == "hi"
    assert valuation_official_sources._nullable_string("") is None
    assert valuation_official_sources._nullable_string(None) is None
    assert valuation_official_sources._parse_date(date(2025, 1, 1)) == date(2025, 1, 1)
    assert valuation_official_sources._parse_date("2025-01-01") == date(2025, 1, 1)
    with pytest.raises(ValueError, match="date value is required"):
        valuation_official_sources._parse_date(None)
    assert valuation_official_sources._parse_float("1.5") == 1.5
    assert valuation_official_sources._parse_float("") is None
    assert valuation_official_sources._parse_float(None) is None
    assert valuation_official_sources._map_tenure("F") == "FREEHOLD"
    assert valuation_official_sources._map_tenure("leasehold") == "LEASEHOLD"
    assert valuation_official_sources._map_tenure("other") == "OTHER"
    assert valuation_official_sources._map_tenure(None) is None
    assert valuation_official_sources._postcode_district("sw1a 1aa") == "SW1A"
    assert valuation_official_sources._postcode_district(None) is None
    assert (
        valuation_official_sources._compose_address(
            {
                "address_text": "Primary",
                "street": "Ignored street",
                "town": "London",
                "county": "Greater London",
                "postcode": "SW1A 1AA",
            }
        )
        == "Primary, Ignored street, London, Greater London, SW1A 1AA"
    )
    assert valuation_official_sources._compose_address({}) is None

    assert isinstance(
        db_session.query(RawAsset).filter(RawAsset.id == asset.id).one(),
        RawAsset,
    )
