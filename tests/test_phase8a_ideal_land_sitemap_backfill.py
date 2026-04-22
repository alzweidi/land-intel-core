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


def test_phase8a_ideal_land_sitemap_backfill_migration_updates_existing_source(tmp_path) -> None:
    previous = _load_migration_module("20260421_000015_phase8a_bidwells_source.py")
    migration = _load_migration_module("20260421_000016_phase8a_ideal_sitemap_backfill.py")
    assert migration.down_revision == previous.revision

    database_url = f"sqlite:///{tmp_path / 'ideal-land-backfill.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(
                ListingSource(
                    name="ideal_land_current_sites",
                    connector_type=ConnectorType.PUBLIC_PAGE,
                    compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                    refresh_policy_json={"seed_urls": ["https://idealland.co.uk/properties"]},
                    active=True,
                )
            )
            session.commit()

        with engine.begin() as connection:
            migration._backfill_ideal_land_sitemap(connection)

        with Session(engine) as session:
            source = session.query(ListingSource).filter_by(name="ideal_land_current_sites").one()
            assert source.refresh_policy_json["seed_urls"] == ["https://idealland.co.uk/properties"]
            assert source.refresh_policy_json["sitemap_urls"] == [
                "https://idealland.co.uk/sitemap.xml"
            ]
    finally:
        engine.dispose()
