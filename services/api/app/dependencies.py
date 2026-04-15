from collections.abc import Generator

from fastapi import Request
from landintel.config import Settings
from landintel.storage.base import StorageAdapter
from sqlalchemy.orm import Session, sessionmaker


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session_factory = get_session_factory(request)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_storage_adapter(request: Request) -> StorageAdapter:
    return request.app.state.storage

