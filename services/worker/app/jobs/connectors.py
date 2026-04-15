from landintel.domain.enums import JobType
from landintel.jobs.service import mark_job_failed, mark_job_succeeded
from landintel.listings.service import execute_listing_job, rebuild_listing_clusters
from landintel.storage.base import StorageAdapter

from .assessment import (
    run_assessment_feature_snapshot_build_job,
    run_comparable_retrieval_build_job,
    run_gold_set_refresh_job,
    run_historical_label_rebuild_job,
    run_replay_verification_batch_job,
)
from .planning_enrich import (
    run_borough_register_ingest_job,
    run_pld_ingest_job,
    run_site_extant_permission_recheck_job,
    run_site_planning_enrich_job,
    run_source_coverage_refresh_job,
)
from .scenarios import (
    run_borough_rulepack_scenario_refresh_job,
    run_scenario_evidence_refresh_job,
    run_site_scenario_geometry_refresh_job,
    run_site_scenario_suggest_refresh_job,
)
from .site_build import (
    run_site_build_job,
    run_site_lpa_refresh_job,
    run_site_title_refresh_job,
)
from .valuation import run_valuation_data_refresh_job, run_valuation_run_build_job


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

    if job.job_type == JobType.PLD_INGEST_REFRESH:
        run_pld_ingest_job(session=session, job=job, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.BOROUGH_REGISTER_INGEST:
        run_borough_register_ingest_job(session=session, job=job, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SITE_PLANNING_ENRICH:
        run_site_planning_enrich_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SITE_EXTANT_PERMISSION_RECHECK:
        run_site_extant_permission_recheck_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SOURCE_COVERAGE_REFRESH:
        run_source_coverage_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SITE_SCENARIO_SUGGEST_REFRESH:
        run_site_scenario_suggest_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SITE_SCENARIO_GEOMETRY_REFRESH:
        run_site_scenario_geometry_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.BOROUGH_RULEPACK_SCENARIO_REFRESH:
        run_borough_rulepack_scenario_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.SCENARIO_EVIDENCE_REFRESH:
        run_scenario_evidence_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.HISTORICAL_LABEL_REBUILD:
        run_historical_label_rebuild_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.ASSESSMENT_FEATURE_SNAPSHOT_BUILD:
        run_assessment_feature_snapshot_build_job(session=session, job=job, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.COMPARABLE_RETRIEVAL_BUILD:
        run_comparable_retrieval_build_job(session=session, job=job, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.REPLAY_VERIFICATION_BATCH:
        run_replay_verification_batch_job(session=session, job=job, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.GOLD_SET_REFRESH:
        run_gold_set_refresh_job(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.VALUATION_DATA_REFRESH:
        run_valuation_data_refresh_job(session=session, job=job, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    if job.job_type == JobType.VALUATION_RUN_BUILD:
        run_valuation_run_build_job(session=session, job=job, storage=storage)
        mark_job_succeeded(session=session, job=job)
        return True

    mark_job_failed(
        session=session,
        job=job,
        error_text=f"Unsupported job type for connector dispatcher: {job.job_type}",
        max_attempts=settings.worker_max_attempts,
    )
    return False
