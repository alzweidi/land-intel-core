from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.connectors.manual_url import ManualUrlSnapshotService
from landintel.domain.enums import JobType
from landintel.jobs.service import mark_job_failed, mark_job_succeeded
from landintel.storage.base import StorageAdapter


def dispatch_connector_job(session, job, settings, storage: StorageAdapter) -> bool:
    if job.job_type == JobType.MANUAL_URL_SNAPSHOT:
        service = ManualUrlSnapshotService(fetcher=HtmlSnapshotFetcher(settings), storage=storage)
        service.execute(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    mark_job_failed(
        session=session,
        job=job,
        error_text=f"Unsupported job type for connector dispatcher: {job.job_type}",
        max_attempts=settings.worker_max_attempts,
    )
    return False

