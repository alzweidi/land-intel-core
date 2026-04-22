from __future__ import annotations

import importlib.util
from pathlib import Path

from landintel.db.base import Base
from landintel.db.session import create_sqlalchemy_engine
from landintel.domain.enums import ComplianceMode, ConnectorType
from landintel.domain.models import ListingSource
from sqlalchemy.orm import Session


def _load_migration_module(filename: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "db" / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase8a_savills_source_migration_upserts_live_public_page_source(tmp_path) -> None:
    previous = _load_migration_module("20260421_000016_phase8a_ideal_sitemap_backfill.py")
    migration = _load_migration_module("20260421_000017_phase8a_savills_source.py")
    assert migration.down_revision == previous.revision

    database_url = f"sqlite:///{tmp_path / 'savills-source.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(
                ListingSource(
                    name="savills_development_land",
                    connector_type=ConnectorType.PUBLIC_PAGE,
                    compliance_mode=ComplianceMode.MANUAL_ONLY,
                    refresh_policy_json={"interval_hours": 72},
                    active=False,
                )
            )
            session.commit()

        with engine.begin() as connection:
            migration._upsert_savills_source(connection)

        with Session(engine) as session:
            source = session.query(ListingSource).filter_by(name="savills_development_land").one()
            assert source.connector_type == ConnectorType.PUBLIC_PAGE
            assert source.compliance_mode == ComplianceMode.COMPLIANT_AUTOMATED
            assert source.active is True
            assert source.refresh_policy_json["interval_hours"] == 24
            assert source.refresh_policy_json["seed_urls"] == [
                "https://search.savills.com/com/en/list/commercial/property-for-sale/development-land/england/camden-borough",
                "https://search.savills.com/com/en/list/commercial/property-for-sale/development-land/england/islington-borough",
                "https://search.savills.com/com/en/list/commercial/property-for-sale/development-land/england/southwark-borough",
            ]
            assert (
                source.refresh_policy_json["listing_link_selector"]
                == "a[href*='/property-detail/']"
            )
            assert source.refresh_policy_json["source_fit_policy"]["required_listing_types"] == [
                "LAND",
                "REDEVELOPMENT_SITE",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["required_listing_statuses"] == [
                "LIVE",
                "AUCTION",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["required_lpa_ids"] == [
                "camden",
                "islington",
                "southwark",
            ]
            assert (
                source.refresh_policy_json["source_fit_policy"]["require_point_coordinates"]
                is True
            )
            assert source.refresh_policy_json["source_fit_policy"]["require_address_text"] is True
            assert source.refresh_policy_json["source_fit_policy"]["require_map_asset"] is False
            assert source.refresh_policy_json["compliance_basis"]["reviewed_at"] == "2026-04-21"
    finally:
        engine.dispose()


def test_phase8a_savills_fit_backfill_updates_existing_source_policy(tmp_path) -> None:
    previous = _load_migration_module("20260421_000017_phase8a_savills_source.py")
    migration = _load_migration_module("20260421_000018_phase8a_savills_fit_backfill.py")
    assert migration.down_revision == previous.revision

    database_url = f"sqlite:///{tmp_path / 'savills-fit-backfill.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(
                ListingSource(
                    name="savills_development_land",
                    connector_type=ConnectorType.PUBLIC_PAGE,
                    compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                    refresh_policy_json={
                        "source_fit_policy": {
                            "required_listing_types": ["LAND", "REDEVELOPMENT_SITE"],
                            "require_point_coordinates": True,
                            "require_address_text": True,
                        }
                    },
                    active=True,
                )
            )
            session.commit()

        with engine.begin() as connection:
            migration._backfill_savills_source_fit(connection)

        with Session(engine) as session:
            source = session.query(ListingSource).filter_by(name="savills_development_land").one()
            assert source.refresh_policy_json["source_fit_policy"]["required_listing_statuses"] == [
                "LIVE",
                "AUCTION",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["required_lpa_ids"] == [
                "camden",
                "islington",
                "southwark",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["require_map_asset"] is False
    finally:
        engine.dispose()


def test_phase8a_savills_fit_backfill_downgrade_restores_revision_17_policy(tmp_path) -> None:
    migration = _load_migration_module("20260421_000018_phase8a_savills_fit_backfill.py")

    database_url = f"sqlite:///{tmp_path / 'savills-fit-downgrade.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(
                ListingSource(
                    name="savills_development_land",
                    connector_type=ConnectorType.PUBLIC_PAGE,
                    compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                    refresh_policy_json={
                        "source_fit_policy": {
                            "required_listing_types": ["LAND", "REDEVELOPMENT_SITE"],
                        }
                    },
                    active=True,
                )
            )
            session.commit()

        with engine.begin() as connection:
            migration._restore_revision_17_savills_source_fit(connection)

        with Session(engine) as session:
            source = session.query(ListingSource).filter_by(name="savills_development_land").one()
            assert source.refresh_policy_json["source_fit_policy"]["required_listing_statuses"] == [
                "LIVE",
                "AUCTION",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["required_lpa_ids"] == [
                "camden",
                "islington",
                "southwark",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["require_map_asset"] is False
    finally:
        engine.dispose()


def test_phase8a_savills_scope_repair_restores_required_lpa_ids_on_existing_rows(tmp_path) -> None:
    previous = _load_migration_module("20260421_000018_phase8a_savills_fit_backfill.py")
    migration = _load_migration_module("20260422_000019_phase8a_savills_scope_repair.py")
    assert migration.down_revision == previous.revision

    database_url = f"sqlite:///{tmp_path / 'savills-scope-repair.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(
                ListingSource(
                    name="savills_development_land",
                    connector_type=ConnectorType.PUBLIC_PAGE,
                    compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                    refresh_policy_json={
                        "source_fit_policy": {
                            "required_listing_types": ["LAND", "REDEVELOPMENT_SITE"],
                            "required_listing_statuses": ["LIVE", "AUCTION"],
                            "require_map_asset": True,
                        }
                    },
                    active=True,
                )
            )
            session.commit()

        with engine.begin() as connection:
            migration._repair_savills_scope(connection)

        with Session(engine) as session:
            source = session.query(ListingSource).filter_by(name="savills_development_land").one()
            assert source.refresh_policy_json["source_fit_policy"]["required_lpa_ids"] == [
                "camden",
                "islington",
                "southwark",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["required_listing_statuses"] == [
                "LIVE",
                "AUCTION",
            ]
            assert source.refresh_policy_json["source_fit_policy"]["require_map_asset"] is False
    finally:
        engine.dispose()
