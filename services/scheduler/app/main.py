import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from landintel.config import get_settings
from landintel.logging import configure_logging

logger = logging.getLogger(__name__)


def scheduler_tick() -> None:
    logger.info(
        "scheduler_tick",
        extra={
            # TODO(spec Phase 1/3/6): replace the heartbeat with recurring queue
            # writers once those jobs exist.
            "detail": "Phase 0 scheduler heartbeat only.",
        },
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        scheduler_tick,
        "interval",
        seconds=settings.scheduler_poll_interval_seconds,
        id="phase0-heartbeat",
        replace_existing=True,
    )
    logger.info(
        "scheduler_started",
        extra={"poll_interval_seconds": settings.scheduler_poll_interval_seconds},
    )
    scheduler.start()


if __name__ == "__main__":
    main()
