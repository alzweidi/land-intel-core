from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from landintel.config import Settings, get_settings
from landintel.db.session import get_engine, get_session_factory
from landintel.logging import configure_logging
from landintel.monitoring.health import database_ready
from landintel.monitoring.metrics import (
    metrics_response,
    register_fastapi_metrics,
)
from landintel.storage.factory import build_storage

from .routes import admin, assessments, listings, opportunities, scenarios, sites


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    if settings.run_db_migrations:
        # Migrations are usually handled by the one-shot compose job.
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
    yield


def create_app(
    settings: Settings | None = None,
    session_factory=None,
    storage=None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = get_engine(settings.database_url, settings.database_echo)
    app.state.session_factory = session_factory or get_session_factory(
        settings.database_url,
        settings.database_echo,
    )
    app.state.storage = storage or build_storage(settings)

    register_fastapi_metrics(app)

    app.include_router(listings.router)
    app.include_router(sites.router)
    app.include_router(scenarios.router)
    app.include_router(assessments.router)
    app.include_router(opportunities.router)
    app.include_router(admin.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz(response: Response) -> dict[str, str]:
        if not database_ready(app.state.session_factory):
            response.status_code = 503
            return {"status": "degraded"}
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics() -> Response:
        return metrics_response()

    return app
