from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path

import respx
from httpx import Response
from landintel.connectors.base import ConnectorContext
from landintel.db.base import Base
from landintel.db.session import create_sqlalchemy_engine
from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    ListingStatus,
    ListingType,
)
from landintel.domain.models import HmlrTitlePolygon, ListingSource, RawAsset, SourceSnapshot
from landintel.geospatial import hmlr_inspire
from landintel.geospatial import official_sources as geospatial_official_sources
from landintel.geospatial.geometry import build_point_geometry
from landintel.listings import service as listings_service
from openpyxl import Workbook
from sqlalchemy.orm import Session


def _load_migration_module(filename: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "db" / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_cabinet_office_workbook_bytes() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Register"
    worksheet.append(
        [
            "Surplus Status",
            "In Site Disposal Reference",
            "Contract Sector",
            "Contract Parent Organisation",
            "Contract Organisation",
            "Insite Property Reference",
            "Property Name",
            "Property Number",
            "Street Name",
            "Town",
            "Postcode",
            "Region",
            "Latitude",
            "Longitude",
            "Status of Sale",
            "Local Authority",
            "Land Usage",
            "Total Surplus Land Area",
            "Total Surplus Floor Area",
        ]
    )
    worksheet.append(
        [
            True,
            "CAMDEN-1",
            "Central Civil Estate",
            "Cabinet Office",
            "Government Property Agency",
            "PROP-1",
            "27-29",
            "27-29",
            "Example Road",
            "London",
            "NW3 2PN",
            "London",
            51.5506,
            -0.1671,
            "On the Market",
            "London Borough of Camden",
            "Surplus Land",
            0.17,
            0.0,
        ]
    )
    worksheet.append(
        [
            True,
            "SOUTHWARK-1",
            "Central Civil Estate",
            "Cabinet Office",
            "Government Property Agency",
            "PROP-2",
            "Bridge House",
            "4",
            "Borough High Street",
            "London",
            "SE1 1JA",
            "London",
            51.5016,
            -0.0924,
            "On the Market",
            "London Borough of Southwark",
            "Development land",
            0.09,
            12.0,
        ]
    )
    worksheet.append(
        [
            True,
            "MIDLANDS-1",
            "Central Civil Estate",
            "Cabinet Office",
            "Government Property Agency",
            "PROP-3",
            "Outside London",
            "1",
            "Example Way",
            "Telford",
            "TF3 4LR",
            "West Midlands",
            52.67,
            -2.44,
            "On the Market",
            "Telford and Wrekin Council",
            "Surplus Land",
            0.50,
            0.0,
        ]
    )
    payload = io.BytesIO()
    workbook.save(payload)
    return payload.getvalue()


@respx.mock
def test_tabular_feed_connector_parses_real_surplus_register_rows(test_settings) -> None:
    remote_url = "https://data.insite.cabinetoffice.gov.uk/insite/Register.xlsx"
    respx.get(remote_url).mock(
        return_value=Response(
            200,
            content=_build_cabinet_office_workbook_bytes(),
            headers={
                "content-type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            },
        )
    )

    connector = listings_service.build_connector(ConnectorType.TABULAR_FEED, settings=test_settings)
    output = connector.run(
        context=ConnectorContext(
            source_name="cabinet_office_surplus_property",
            connector_type=ConnectorType.TABULAR_FEED,
            refresh_policy_json={
                "feed_url": remote_url,
                "feed_format": "xlsx",
                "sheet_name": "Register",
                "row_transform": "cabinet_office_surplus_property_v1",
                "status_of_sale_values": ["On the Market"],
                "local_authority_contains_any": [
                    "London Borough",
                    "Royal Borough",
                    "City of London",
                ],
                "allowed_land_usage_contains_any": ["Surplus Land", "Development land"],
                "allowed_listing_types": ["LAND"],
                "max_surplus_floor_area_sqm": 0,
                "require_positive_land_area": True,
                "max_listings": 10,
            },
            requested_by="pytest",
        ),
        payload={},
    )

    assert output.source_name == "cabinet_office_surplus_property"
    assert output.manifest_json["listing_count"] == 1
    assert len(output.listings) == 1
    assert output.assets[0].asset_type == "XLSX"
    assert output.listings[0].source_listing_id == "CAMDEN-1"
    assert output.listings[0].listing_type == ListingType.LAND
    assert output.listings[0].status == ListingStatus.LIVE


def test_phase8a_real_source_migration_upserts_real_automated_source(tmp_path) -> None:
    launch_readiness = _load_migration_module("20260419_000011_phase8a_launch_readiness.py")
    migration = _load_migration_module("20260420_000012_phase8a_real_source_launch.py")
    assert migration.down_revision == launch_readiness.revision

    database_url = f"sqlite:///{tmp_path / 'real-source.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(
                ListingSource(
                    name=migration.REAL_SOURCE_NAME,
                    connector_type=ConnectorType.PUBLIC_PAGE,
                    compliance_mode=ComplianceMode.MANUAL_ONLY,
                    refresh_policy_json={"feed_url": "https://old.example/test.xlsx"},
                    active=False,
                )
            )
            session.commit()

        with engine.begin() as connection:
            migration._upsert_real_automated_source(connection)

        with Session(engine) as session:
            source = session.query(ListingSource).filter_by(name=migration.REAL_SOURCE_NAME).one()
            assert source.connector_type == ConnectorType.TABULAR_FEED
            assert source.compliance_mode == ComplianceMode.COMPLIANT_AUTOMATED
            assert source.active is True
            assert source.refresh_policy_json["interval_hours"] == 24
            assert source.refresh_policy_json["sheet_name"] == "Register"
            assert source.refresh_policy_json["status_of_sale_values"] == ["On the Market"]
            assert (
                source.refresh_policy_json["row_transform"]
                == "cabinet_office_surplus_property_v1"
            )
            assert source.refresh_policy_json["local_authority_contains_any"] == [
                "LONDON BOROUGH",
                "ROYAL BOROUGH",
                "CITY OF LONDON",
            ]
            assert source.refresh_policy_json["allowed_land_usage_contains_any"] == [
                "Surplus Land",
                "Development land",
            ]
            assert source.refresh_policy_json["allowed_listing_types"] == ["LAND"]
            assert source.refresh_policy_json["max_surplus_floor_area_sqm"] == 0
            assert source.refresh_policy_json["require_positive_land_area"] is True
    finally:
        engine.dispose()


@respx.mock
def test_geospatial_official_source_remote_geojson_updates_provenance(
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
    respx.get(remote_url).mock(
        return_value=Response(
            200,
            content=fixture_path.read_bytes(),
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
    asset = db_session.get(RawAsset, result.raw_asset_id)

    assert snapshot is not None
    assert asset is not None
    assert snapshot.source_uri == remote_url
    assert snapshot.manifest_json["fetch_mode"] == "remote"
    assert asset.original_url == remote_url
    assert result.imported_count > 0


def test_hmlr_inspire_lookup_builds_title_union_from_official_point(
    db_session,
    storage,
    monkeypatch,
    test_settings,
) -> None:
    point_geometry = build_point_geometry(lat=51.5506, lon=-0.1671).geom_27700
    x, y = point_geometry.x, point_geometry.y
    polygon_text = " ".join(
        [
            f"{x - 5:.3f} {y - 5:.3f}",
            f"{x + 5:.3f} {y - 5:.3f}",
            f"{x + 5:.3f} {y + 5:.3f}",
            f"{x - 5:.3f} {y + 5:.3f}",
            f"{x - 5:.3f} {y - 5:.3f}",
        ]
    )
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr(
            "Land_Registry_Cadastral_Parcels.gml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<wfs:FeatureCollection '
                'xmlns:wfs="http://www.opengis.net/wfs/2.0" '
                'xmlns:LR="www.landregistry.gov.uk" '
                'xmlns:gml="http://www.opengis.net/gml/3.2">'
                '<wfs:member><LR:PREDEFINED>'
                '<LR:GEOMETRY><gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700">'
                f"<gml:exterior><gml:LinearRing><gml:posList>{polygon_text}</gml:posList>"
                "</gml:LinearRing></gml:exterior></gml:Polygon></LR:GEOMETRY>"
                "<LR:INSPIREID>44079687</LR:INSPIREID>"
                "<LR:NATIONALCADASTRALREFERENCE>44079687</LR:NATIONALCADASTRALREFERENCE>"
                "</LR:PREDEFINED></wfs:member></wfs:FeatureCollection>"
            ),
        )

    monkeypatch.setattr(
        hmlr_inspire,
        "get_settings",
        lambda: test_settings.model_copy(update={"real_data_mode": True}),
    )
    monkeypatch.setattr(hmlr_inspire, "build_storage", lambda settings: storage)
    monkeypatch.setattr(
        hmlr_inspire,
        "_download_hmlr_zip",
        lambda download_url: zip_buffer.getvalue(),
    )

    prepared = hmlr_inspire.maybe_import_title_union_for_listing_point(
        session=db_session,
        authority_name="London Borough of Camden (CMD)",
        lat=51.5506,
        lon=-0.1671,
        requested_by="pytest",
    )

    assert prepared is not None
    assert prepared.geom_source_type.value == "TITLE_UNION"
    assert prepared.geom_confidence.value == "MEDIUM"
    assert prepared.area_sqm > 0
    assert db_session.query(SourceSnapshot).count() == 1
    assert db_session.query(RawAsset).count() == 1
    title_rows = db_session.query(HmlrTitlePolygon).all()
    assert len(title_rows) == 1
    assert title_rows[0].title_number == "44079687"
