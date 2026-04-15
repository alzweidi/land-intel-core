import logging
import time
from collections.abc import Callable

from landintel.config import Settings, get_settings
from landintel.db.session import get_session_factory
from landintel.domain.enums import JobStatus
from landintel.jobs.service import claim_next_job, mark_job_failed
from landintel.logging import configure_logging
from landintel.monitoring.metrics import WORKER_LOOP_COUNT
from landintel.storage.factory import build_storage
from prometheus_client import start_http_server

from .jobs.connectors import dispatch_connector_job

logger = logging.getLogger(__name__)


def process_next_job(
    settings: Settings,
    session_factory,
    dispatch_job: Callable,
    storage,
) -> bool:
    with session_factory() as session:
        job = claim_next_job(session=session, worker_id=settings.worker_id)
        if job is None:
            session.commit()
            return False

        try:
            handled = dispatch_job(session=session, job=job, settings=settings, storage=storage)
            session.commit()
            return handled
        except Exception as exc:  # pragma: no cover - guarded in tests via direct assertions
            logger.exception("worker_job_failed", extra={"job_id": str(job.id)})
            if job.status == JobStatus.RUNNING:
                mark_job_failed(
                    session=session,
                    job=job,
                    error_text=str(exc),
                    max_attempts=settings.worker_max_attempts,
                )
            session.commit()
            return False


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    session_factory = get_session_factory(settings.database_url, settings.database_echo)
    storage = build_storage(settings)

    start_http_server(settings.worker_metrics_port)
    logger.info(
        "worker_started",
        extra={"worker_id": settings.worker_id, "metrics_port": settings.worker_metrics_port},
    )

    while True:
        WORKER_LOOP_COUNT.inc()
        handled = process_next_job(
            settings=settings,
            session_factory=session_factory,
            dispatch_job=dispatch_connector_job,
            storage=storage,
        )
        if not handled:
            time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
