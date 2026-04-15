import base64
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from landintel.domain.enums import JobStatus, JobType
from landintel.domain.models import JobRun
from landintel.monitoring.metrics import JOB_CLAIMS_TOTAL, JOB_STATUS_TOTAL


def utc_now() -> datetime:
    return datetime.now(UTC)


def enqueue_manual_url_job(
    session: Session,
    *,
    url: str,
    source_name: str,
    requested_by: str | None,
) -> JobRun:
    return _create_job(
        session=session,
        job_type=JobType.MANUAL_URL_SNAPSHOT,
        payload_json={"url": url, "source_name": source_name},
        requested_by=requested_by,
    )


def enqueue_csv_import_job(
    session: Session,
    *,
    source_name: str,
    filename: str,
    csv_bytes: bytes,
    requested_by: str | None,
) -> JobRun:
    return _create_job(
        session=session,
        job_type=JobType.CSV_IMPORT_SNAPSHOT,
        payload_json={
            "source_name": source_name,
            "filename": filename,
            "csv_base64": base64.b64encode(csv_bytes).decode("ascii"),
        },
        requested_by=requested_by,
    )


def enqueue_connector_run_job(
    session: Session,
    *,
    source_name: str,
    requested_by: str | None,
) -> JobRun:
    return _create_job(
        session=session,
        job_type=JobType.LISTING_SOURCE_RUN,
        payload_json={"source_name": source_name},
        requested_by=requested_by,
    )


def enqueue_cluster_rebuild_job(
    session: Session,
    *,
    requested_by: str | None,
) -> JobRun:
    existing = session.execute(
        select(JobRun)
        .where(
            JobRun.job_type == JobType.LISTING_CLUSTER_REBUILD,
            JobRun.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .order_by(JobRun.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    return _create_job(
        session=session,
        job_type=JobType.LISTING_CLUSTER_REBUILD,
        payload_json={},
        requested_by=requested_by,
    )


def _create_job(
    *,
    session: Session,
    job_type: JobType,
    payload_json: dict[str, object],
    requested_by: str | None,
) -> JobRun:
    job = JobRun(
        job_type=job_type,
        payload_json=payload_json,
        status=JobStatus.QUEUED,
        run_at=utc_now(),
        next_run_at=utc_now(),
        requested_by=requested_by,
    )
    session.add(job)
    session.flush()
    JOB_STATUS_TOTAL.labels(job_type=job.job_type.value, status=job.status.value).inc()
    return job


def _claimable_jobs_stmt() -> Select[tuple[JobRun]]:
    return (
        select(JobRun)
        .where(
            JobRun.status.in_([JobStatus.QUEUED, JobStatus.FAILED]),
            JobRun.next_run_at <= utc_now(),
        )
        .order_by(JobRun.next_run_at.asc(), JobRun.created_at.asc())
    )


def claim_next_job(session: Session, worker_id: str) -> JobRun | None:
    stmt = _claimable_jobs_stmt().limit(1)
    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    if dialect_name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return None

    job.status = JobStatus.RUNNING
    job.worker_id = worker_id
    job.locked_at = utc_now()
    job.attempts += 1
    session.flush()

    JOB_CLAIMS_TOTAL.labels(worker_id=worker_id, job_type=job.job_type.value).inc()
    JOB_STATUS_TOTAL.labels(job_type=job.job_type.value, status=job.status.value).inc()
    return job


def mark_job_succeeded(session: Session, job: JobRun) -> None:
    job.status = JobStatus.SUCCEEDED
    job.error_text = None
    job.locked_at = None
    job.updated_at = utc_now()
    session.flush()
    JOB_STATUS_TOTAL.labels(job_type=job.job_type.value, status=job.status.value).inc()


def mark_job_failed(
    session: Session,
    job: JobRun,
    *,
    error_text: str,
    max_attempts: int,
    retry_delay_seconds: int = 15,
) -> None:
    job.error_text = error_text
    job.locked_at = None
    job.updated_at = utc_now()
    if job.attempts >= max_attempts:
        job.status = JobStatus.DEAD
        job.next_run_at = utc_now()
    else:
        job.status = JobStatus.FAILED
        job.next_run_at = utc_now() + timedelta(seconds=retry_delay_seconds)
    session.flush()
    JOB_STATUS_TOTAL.labels(job_type=job.job_type.value, status=job.status.value).inc()


def list_jobs(session: Session, *, limit: int = 100) -> list[JobRun]:
    stmt = select(JobRun).order_by(JobRun.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())
