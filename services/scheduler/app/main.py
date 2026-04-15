import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from landintel.config import get_settings
from landintel.db.session import get_session_factory
from landintel.domain.enums import ComplianceMode, JobStatus, JobType
from landintel.domain.models import JobRun, ListingSource
from landintel.jobs.service import enqueue_connector_run_job
from landintel.logging import configure_logging
from sqlalchemy import select

logger = logging.getLogger(__name__)


def scheduler_tick(session_factory) -> None:
    with session_factory() as session:
        sources = session.execute(
            select(ListingSource).where(
                ListingSource.active.is_(True),
                ListingSource.compliance_mode == ComplianceMode.COMPLIANT_AUTOMATED,
            )
        ).scalars().all()
        jobs = session.execute(
            select(JobRun).where(JobRun.job_type == JobType.LISTING_SOURCE_RUN)
        ).scalars().all()

        queued_sources = {
            str(job.payload_json.get("source_name"))
            for job in jobs
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}
        }
        latest_run_by_source: dict[str, datetime] = {}
        for job in jobs:
            source_name = str(job.payload_json.get("source_name", ""))
            latest_run_by_source[source_name] = max(
                latest_run_by_source.get(source_name, datetime.min.replace(tzinfo=UTC)),
                job.created_at,
            )

        enqueued = 0
        now = datetime.now(UTC)
        for source in sources:
            interval_hours = source.refresh_policy_json.get("interval_hours")
            if interval_hours is None:
                continue
            if source.name in queued_sources:
                continue

            interval = timedelta(hours=float(interval_hours))
            last_run_at = latest_run_by_source.get(source.name)
            if last_run_at is not None and now - last_run_at < interval:
                continue

            enqueue_connector_run_job(
                session=session,
                source_name=source.name,
                requested_by="scheduler",
            )
            enqueued += 1

        session.commit()
        logger.info(
            "scheduler_tick",
            extra={
                "active_source_count": len(sources),
                "connector_jobs_enqueued": enqueued,
            },
        )


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    session_factory = get_session_factory(settings.database_url, settings.database_echo)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        scheduler_tick,
        "interval",
        seconds=settings.scheduler_poll_interval_seconds,
        id="listing-refresh-enqueue",
        replace_existing=True,
        args=[session_factory],
    )
    logger.info(
        "scheduler_started",
        extra={"poll_interval_seconds": settings.scheduler_poll_interval_seconds},
    )
    scheduler.start()


if __name__ == "__main__":
    main()
