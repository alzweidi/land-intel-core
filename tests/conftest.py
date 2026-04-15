from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from landintel.config import Settings
from landintel.db.base import Base
from landintel.db.session import create_session_factory, create_sqlalchemy_engine
from landintel.domain import models  # noqa: F401
from landintel.domain.enums import StorageBackend
from landintel.storage.local import LocalFileStorageAdapter
from sqlalchemy.orm import Session

from services.api.app.main import create_app


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

