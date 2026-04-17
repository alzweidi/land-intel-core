from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from landintel.auth import RequestActor, resolve_request_actor, role_at_least
from landintel.config import Settings
from landintel.domain.enums import AppRoleName
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


def get_request_actor(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> RequestActor:
    return resolve_request_actor(request=request, settings=settings)


def require_reviewer_actor(
    actor: RequestActor = Depends(get_request_actor),
) -> RequestActor:
    if actor.session_token_present and not actor.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Reviewer or admin session is invalid or expired.",
        )
    if not role_at_least(actor.role, AppRoleName.REVIEWER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer or admin role required.",
        )
    return actor


def require_admin_actor(
    actor: RequestActor = Depends(get_request_actor),
) -> RequestActor:
    if actor.session_token_present and not actor.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin session is invalid or expired.",
        )
    if actor.role != AppRoleName.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required.",
        )
    return actor
