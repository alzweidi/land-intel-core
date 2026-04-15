from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from landintel.config import get_settings


def create_sqlalchemy_engine(database_url: str, *, echo: bool = False) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        database_url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@lru_cache
def get_engine(database_url: str | None = None, echo: bool | None = None) -> Engine:
    settings = get_settings()
    resolved_url = database_url or settings.database_url
    resolved_echo = settings.database_echo if echo is None else echo
    return create_sqlalchemy_engine(resolved_url, echo=resolved_echo)


def create_session_factory(
    database_url: str,
    *,
    echo: bool = False,
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=create_sqlalchemy_engine(database_url, echo=echo),
        autoflush=False,
        expire_on_commit=False,
    )


@lru_cache
def get_session_factory(
    database_url: str | None = None,
    echo: bool | None = None,
) -> sessionmaker[Session]:
    settings = get_settings()
    resolved_url = database_url or settings.database_url
    resolved_echo = settings.database_echo if echo is None else echo
    return sessionmaker(
        bind=get_engine(resolved_url, resolved_echo),
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope(session_factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    factory = session_factory or get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
