from __future__ import annotations

from uuid import UUID

from landintel.assessments.service import (
    build_assessment_artifacts_for_run,
    replay_verify_all_assessments,
)
from landintel.planning.historical_labels import rebuild_historical_case_labels


def run_historical_label_rebuild_job(*, session, job) -> None:
    summary = rebuild_historical_case_labels(
        session=session,
        requested_by=job.requested_by or "worker",
    )
    job.payload_json = {
        **job.payload_json,
        "result": {
            "total": summary.total,
            "positive": summary.positive,
            "negative": summary.negative,
            "excluded": summary.excluded,
            "censored": summary.censored,
        },
    }
    session.flush()

def run_assessment_feature_snapshot_build_job(*, session, job, storage) -> None:
    build_assessment_artifacts_for_run(
        session=session,
        assessment_run_id=UUID(str(job.payload_json["assessment_id"])),
        requested_by=job.requested_by or "worker",
        storage=storage,
    )
    session.flush()


def run_comparable_retrieval_build_job(*, session, job, storage) -> None:
    build_assessment_artifacts_for_run(
        session=session,
        assessment_run_id=UUID(str(job.payload_json["assessment_id"])),
        requested_by=job.requested_by or "worker",
        storage=storage,
    )
    session.flush()


def run_replay_verification_batch_job(*, session, job, storage) -> None:
    summary = replay_verify_all_assessments(session=session, storage=storage)
    job.payload_json = {**job.payload_json, "result": summary}
    session.flush()


def run_gold_set_refresh_job(*, session, job) -> None:
    summary = rebuild_historical_case_labels(
        session=session,
        requested_by=job.requested_by or "worker",
    )
    job.payload_json = {
        **job.payload_json,
        "result": {
            "total": summary.total,
            "positive": summary.positive,
            "negative": summary.negative,
            "excluded": summary.excluded,
            "censored": summary.censored,
        },
    }
    session.flush()
