from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from landintel.db.base import Base
from landintel.db.session import create_sqlalchemy_engine
from landintel.domain.enums import ComplianceMode, ConnectorType, ListingType
from landintel.domain.models import ListingSource
from landintel.listings import service as listings_service
from sqlalchemy.orm import Session


def _load_migration_module(filename: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "db" / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase8a_live_source_fit_migration_deactivates_placeholder_and_updates_policy(
    tmp_path,
) -> None:
    previous = _load_migration_module("20260420_000012_phase8a_real_source_launch.py")
    migration = _load_migration_module("20260420_000013_phase8a_live_source_fit.py")
    assert migration.down_revision == previous.revision

    database_url = f"sqlite:///{tmp_path / 'live-source-fit.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all(
                [
                    ListingSource(
                        name="example_public_page",
                        connector_type=ConnectorType.PUBLIC_PAGE,
                        compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                        refresh_policy_json={"interval_hours": 24, "seed_urls": ["https://example.com"]},
                        active=True,
                    ),
                    ListingSource(
                        name="cabinet_office_surplus_property",
                        connector_type=ConnectorType.TABULAR_FEED,
                        compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                        refresh_policy_json={
                            "status_of_sale_values": ["On the Market", "Under Offer"]
                        },
                        active=True,
                    ),
                ]
            )
            session.commit()

        with engine.begin() as connection:
            migration._deactivate_example_public_page(connection)
            migration._tighten_real_source_policy(connection)

        with Session(engine) as session:
            example = session.query(ListingSource).filter_by(name="example_public_page").one()
            real_source = (
                session.query(ListingSource)
                .filter_by(name="cabinet_office_surplus_property")
                .one()
            )
            assert example.active is False
            assert real_source.active is True
            assert real_source.refresh_policy_json["status_of_sale_values"] == ["On the Market"]
            assert real_source.refresh_policy_json["local_authority_contains_any"] == [
                "LONDON BOROUGH",
                "ROYAL BOROUGH",
                "CITY OF LONDON",
            ]
            assert real_source.refresh_policy_json["allowed_land_usage_contains_any"] == [
                "Surplus Land",
                "Development land",
            ]
            assert real_source.refresh_policy_json["allowed_listing_types"] == ["LAND"]
            assert real_source.refresh_policy_json["max_surplus_floor_area_sqm"] == 0
            assert real_source.refresh_policy_json["require_positive_land_area"] is True
    finally:
        engine.dispose()


def test_listing_eligible_for_auto_site_build_blocks_building_heavy_cabinet_rows() -> None:
    cabinet_listing = SimpleNamespace(
        listing_type=ListingType.LAND_WITH_BUILDING,
        source=SimpleNamespace(name="cabinet_office_surplus_property"),
    )
    generic_listing = SimpleNamespace(
        listing_type=ListingType.LAND_WITH_BUILDING,
        source=SimpleNamespace(name="example_public_page"),
    )
    land_listing = SimpleNamespace(
        listing_type=ListingType.LAND,
        source=SimpleNamespace(name="cabinet_office_surplus_property"),
    )
    ideal_land_listing = SimpleNamespace(
        listing_type=ListingType.LAND,
        source=SimpleNamespace(name="ideal_land_current_sites"),
    )
    building_snapshot = SimpleNamespace(raw_record_json={})
    generic_snapshot = SimpleNamespace(raw_record_json={})
    land_snapshot = SimpleNamespace(raw_record_json={"bbox_4326": [-0.1, 51.4, -0.09, 51.41]})
    ideal_land_snapshot = SimpleNamespace(raw_record_json={})
    ideal_land_geometry_snapshot = SimpleNamespace(
        raw_record_json={"bbox_4326": [-0.2, 51.42, -0.19, 51.43]}
    )
    ideal_land_polygon_snapshot = SimpleNamespace(
        raw_record_json={
            "geometry_4326": {
                "type": "Polygon",
                "coordinates": [[[-0.2, 51.42], [-0.19, 51.42], [-0.19, 51.43], [-0.2, 51.42]]],
            }
        }
    )
    geometry_snapshot = SimpleNamespace(
        raw_record_json={
            "geometry_4326": {
                "type": "Polygon",
                "coordinates": [[[-0.1, 51.4], [-0.09, 51.4], [-0.09, 51.41], [-0.1, 51.4]]],
            }
        }
    )
    weak_land_snapshot = SimpleNamespace(raw_record_json={})

    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=cabinet_listing,
            listing_snapshot=building_snapshot,
        )
        is False
    )
    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=generic_listing,
            listing_snapshot=generic_snapshot,
        )
        is True
    )
    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=land_listing,
            listing_snapshot=land_snapshot,
        )
        is True
    )
    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=land_listing,
            listing_snapshot=geometry_snapshot,
        )
        is True
    )
    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=ideal_land_listing,
            listing_snapshot=ideal_land_snapshot,
        )
        is False
    )
    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=ideal_land_listing,
            listing_snapshot=ideal_land_polygon_snapshot,
        )
        is True
    )
    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=ideal_land_listing,
            listing_snapshot=ideal_land_geometry_snapshot,
        )
        is True
    )
    assert (
        listings_service._listing_eligible_for_auto_site_build(
            listing_item=land_listing,
            listing_snapshot=weak_land_snapshot,
        )
        is False
    )
