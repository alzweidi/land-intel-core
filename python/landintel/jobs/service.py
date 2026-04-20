import base64
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from landintel.domain.enums import JobStatus, JobType
from landintel.domain.models import JobRun
from landintel.monitoring.metrics import JOB_CLAIMS_TOTAL, JOB_STATUS_TOTAL

STALE_RUNNING_JOB_LOCK_SECONDS = 15 * 60


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
    return _deduplicated_job(
        session=session,
        job_type=JobType.LISTING_SOURCE_RUN,
        dedupe_key=f"source:{source_name}",
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


def enqueue_site_build_job(
    session: Session,
    *,
    cluster_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.SITE_BUILD_REFRESH,
        dedupe_key=f"cluster:{cluster_id}",
        payload_json={"cluster_id": cluster_id},
        requested_by=requested_by,
    )


def enqueue_site_lpa_refresh_job(
    session: Session,
    *,
    site_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.SITE_LPA_LINK_REFRESH,
        dedupe_key=f"site:{site_id}",
        payload_json={"site_id": site_id},
        requested_by=requested_by,
    )


def enqueue_site_title_refresh_job(
    session: Session,
    *,
    site_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.SITE_TITLE_LINK_REFRESH,
        dedupe_key=f"site:{site_id}",
        payload_json={"site_id": site_id},
        requested_by=requested_by,
    )


def enqueue_pld_ingest_job(
    session: Session,
    *,
    fixture_path: str | None = None,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.PLD_INGEST_REFRESH,
        dedupe_key=f"fixture:{fixture_path or 'default-pld'}",
        payload_json={"fixture_path": fixture_path} if fixture_path else {},
        requested_by=requested_by,
    )


def enqueue_borough_register_ingest_job(
    session: Session,
    *,
    fixture_path: str | None = None,
    requested_by: str | None,
    include_supporting_layers: bool = True,
) -> JobRun:
    payload_json: dict[str, object] = {"include_supporting_layers": include_supporting_layers}
    if fixture_path:
        payload_json["fixture_path"] = fixture_path
    return _deduplicated_job(
        session=session,
        job_type=JobType.BOROUGH_REGISTER_INGEST,
        dedupe_key=f"fixture:{fixture_path or 'default-borough-register'}",
        payload_json=payload_json,
        requested_by=requested_by,
    )


def enqueue_site_planning_enrich_job(
    session: Session,
    *,
    site_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.SITE_PLANNING_ENRICH,
        dedupe_key=f"site:{site_id}",
        payload_json={"site_id": site_id},
        requested_by=requested_by,
    )


def enqueue_site_extant_permission_recheck_job(
    session: Session,
    *,
    site_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.SITE_EXTANT_PERMISSION_RECHECK,
        dedupe_key=f"site:{site_id}",
        payload_json={"site_id": site_id},
        requested_by=requested_by,
    )


def enqueue_source_coverage_refresh_job(
    session: Session,
    *,
    borough_id: str | None,
    requested_by: str | None,
) -> JobRun:
    dedupe_key = f"borough:{borough_id or 'all'}"
    payload_json: dict[str, object] = {}
    if borough_id:
        payload_json["borough_id"] = borough_id
    return _deduplicated_job(
        session=session,
        job_type=JobType.SOURCE_COVERAGE_REFRESH,
        dedupe_key=dedupe_key,
        payload_json=payload_json,
        requested_by=requested_by,
    )


def enqueue_site_scenario_suggest_refresh_job(
    session: Session,
    *,
    site_id: str,
    requested_by: str | None,
    template_keys: list[str] | None = None,
    manual_seed: bool = False,
) -> JobRun:
    payload_json: dict[str, object] = {
        "site_id": site_id,
        "manual_seed": manual_seed,
    }
    if template_keys:
        payload_json["template_keys"] = template_keys
    dedupe_key = f"site:{site_id}:{','.join(template_keys or ['all'])}:{int(manual_seed)}"
    return _deduplicated_job(
        session=session,
        job_type=JobType.SITE_SCENARIO_SUGGEST_REFRESH,
        dedupe_key=dedupe_key,
        payload_json=payload_json,
        requested_by=requested_by,
    )


def enqueue_site_scenario_geometry_refresh_job(
    session: Session,
    *,
    site_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.SITE_SCENARIO_GEOMETRY_REFRESH,
        dedupe_key=f"site:{site_id}",
        payload_json={"site_id": site_id},
        requested_by=requested_by,
    )


def enqueue_borough_rulepack_scenario_refresh_job(
    session: Session,
    *,
    borough_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.BOROUGH_RULEPACK_SCENARIO_REFRESH,
        dedupe_key=f"borough:{borough_id}",
        payload_json={"borough_id": borough_id},
        requested_by=requested_by,
    )


def enqueue_scenario_evidence_refresh_job(
    session: Session,
    *,
    scenario_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.SCENARIO_EVIDENCE_REFRESH,
        dedupe_key=f"scenario:{scenario_id}",
        payload_json={"scenario_id": scenario_id},
        requested_by=requested_by,
    )


def enqueue_historical_label_rebuild_job(
    session: Session,
    *,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.HISTORICAL_LABEL_REBUILD,
        dedupe_key="historical-labels:current",
        payload_json={},
        requested_by=requested_by,
    )


def enqueue_assessment_feature_snapshot_build_job(
    session: Session,
    *,
    assessment_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.ASSESSMENT_FEATURE_SNAPSHOT_BUILD,
        dedupe_key=f"assessment:{assessment_id}",
        payload_json={"assessment_id": assessment_id},
        requested_by=requested_by,
    )


def enqueue_comparable_retrieval_build_job(
    session: Session,
    *,
    assessment_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.COMPARABLE_RETRIEVAL_BUILD,
        dedupe_key=f"assessment:{assessment_id}",
        payload_json={"assessment_id": assessment_id},
        requested_by=requested_by,
    )


def enqueue_replay_verification_batch_job(
    session: Session,
    *,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.REPLAY_VERIFICATION_BATCH,
        dedupe_key="replay-verification:current",
        payload_json={},
        requested_by=requested_by,
    )


def enqueue_gold_set_refresh_job(
    session: Session,
    *,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.GOLD_SET_REFRESH,
        dedupe_key="gold-set:current",
        payload_json={},
        requested_by=requested_by,
    )


def enqueue_valuation_data_refresh_job(
    session: Session,
    *,
    dataset: str = "all",
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.VALUATION_DATA_REFRESH,
        dedupe_key=f"valuation-dataset:{dataset}",
        payload_json={"dataset": dataset},
        requested_by=requested_by,
    )


def enqueue_valuation_run_build_job(
    session: Session,
    *,
    assessment_id: str,
    requested_by: str | None,
) -> JobRun:
    return _deduplicated_job(
        session=session,
        job_type=JobType.VALUATION_RUN_BUILD,
        dedupe_key=f"assessment:{assessment_id}",
        payload_json={"assessment_id": assessment_id},
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


def _deduplicated_job(
    *,
    session: Session,
    job_type: JobType,
    dedupe_key: str,
    payload_json: dict[str, object],
    requested_by: str | None,
) -> JobRun:
    existing_jobs = session.execute(
        select(JobRun)
        .where(
            JobRun.job_type == job_type,
            JobRun.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .order_by(JobRun.created_at.asc())
    ).scalars()
    for existing in existing_jobs:
        if str(existing.payload_json.get("dedupe_key")) == dedupe_key:
            return existing

    return _create_job(
        session=session,
        job_type=job_type,
        payload_json={**payload_json, "dedupe_key": dedupe_key},
        requested_by=requested_by,
    )


def _claimable_jobs_stmt() -> Select[tuple[JobRun]]:
    now = utc_now()
    stale_cutoff = now - timedelta(seconds=STALE_RUNNING_JOB_LOCK_SECONDS)
    return (
        select(JobRun)
        .where(
            or_(
                and_(
                    JobRun.status.in_([JobStatus.QUEUED, JobStatus.FAILED]),
                    JobRun.next_run_at <= now,
                ),
                and_(
                    JobRun.status == JobStatus.RUNNING,
                    or_(JobRun.locked_at.is_(None), JobRun.locked_at <= stale_cutoff),
                ),
            ),
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


def refresh_job_lock(
    session: Session,
    *,
    job_id,
    worker_id: str,
) -> bool:
    job = session.get(JobRun, job_id)
    if (
        job is None
        or job.status != JobStatus.RUNNING
        or job.worker_id != worker_id
    ):
        return False
    job.locked_at = utc_now()
    job.updated_at = utc_now()
    session.flush()
    return True


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
