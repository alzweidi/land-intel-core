from landintel.domain.enums import JobType
from landintel.jobs.service import mark_job_failed, mark_job_succeeded
from landintel.listings.service import execute_listing_job, rebuild_listing_clusters
from landintel.storage.base import StorageAdapter

from .site_build import (
    run_site_build_job,
    run_site_lpa_refresh_job,
    run_site_title_refresh_job,
)


def dispatch_connector_job(session, job, settings, storage: StorageAdapter) -> bool:
    if job.job_type in {
        JobType.MANUAL_URL_SNAPSHOT,
        JobType.CSV_IMPORT_SNAPSHOT,
        JobType.LISTING_SOURCE_RUN,
    }:
        execute_listing_job(session=session, job=job, settings=settings, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.LISTING_CLUSTER_REBUILD:
        rebuild_listing_clusters(session=session)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SITE_BUILD_REFRESH:
        run_site_build_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SITE_LPA_LINK_REFRESH:
        run_site_lpa_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SITE_TITLE_LINK_REFRESH:
        run_site_title_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    mark_job_failed(
        session=session,
        job=job,
        error_text=f"Unsupported job type for connector dispatcher: {job.job_type}",
        max_attempts=settings.worker_max_attempts,
    )
    return False
