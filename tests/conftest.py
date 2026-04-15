from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from landintel.config import Settings
from landintel.db.base import Base
from landintel.db.session import create_session_factory, create_sqlalchemy_engine
from landintel.domain import models  # noqa: F401
from landintel.domain.enums import ComplianceMode, ConnectorType, StorageBackend
from landintel.domain.models import ListingSource
from landintel.storage.local import LocalFileStorageAdapter
from sqlalchemy.orm import Session

from services.api.app.main import create_app
from services.worker.app.jobs.connectors import dispatch_connector_job
from services.worker.app.main import process_next_job


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_backend=StorageBackend.LOCAL,
        storage_local_root=str(tmp_path / "storage"),
        worker_id="worker-test-1",
        worker_metrics_port=19101,
        run_db_migrations=False,
    )


@pytest.fixture()
def session_factory(test_settings: Settings):
    engine = create_sqlalchemy_engine(test_settings.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(test_settings.database_url)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def storage(test_settings: Settings) -> LocalFileStorageAdapter:
    return LocalFileStorageAdapter(test_settings.storage_local_root)


@pytest.fixture()
def client(
    test_settings: Settings,
    session_factory,
    storage: LocalFileStorageAdapter,
) -> Generator[TestClient, None, None]:
    app = create_app(settings=test_settings, session_factory=session_factory, storage=storage)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(session_factory) -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session


@pytest.fixture()
def seed_listing_sources(db_session: Session) -> dict[str, ListingSource]:
    sources = {
        "manual_url": ListingSource(
            name="manual_url",
            connector_type=ConnectorType.MANUAL_URL,
            compliance_mode=ComplianceMode.MANUAL_ONLY,
            refresh_policy_json={"run_mode": "manual"},
            active=True,
        ),
        "csv_import": ListingSource(
            name="csv_import",
            connector_type=ConnectorType.CSV_IMPORT,
            compliance_mode=ComplianceMode.CSV_ONLY,
            refresh_policy_json={"run_mode": "manual"},
            active=True,
        ),
        "public_page_fixture": ListingSource(
            name="public_page_fixture",
            connector_type=ConnectorType.PUBLIC_PAGE,
            compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
            refresh_policy_json={
                "seed_urls": ["https://public.example/land"],
                "listing_link_selector": "a.listing-link",
                "listing_url_patterns": [r"/listings/"],
                "max_listings": 5,
            },
            active=True,
        ),
    }
    db_session.add_all(sources.values())
    db_session.commit()
    return sources


@pytest.fixture()
def drain_jobs(
    test_settings: Settings,
    session_factory,
    storage: LocalFileStorageAdapter,
) -> Callable[[], int]:
    def _drain(max_iterations: int = 10) -> int:
        processed = 0
        for _ in range(max_iterations):
            handled = process_next_job(
                settings=test_settings,
                session_factory=session_factory,
                dispatch_job=dispatch_connector_job,
                storage=storage,
            )
            if not handled:
                break
            processed += 1
        return processed

    return _drain
