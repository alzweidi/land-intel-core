from __future__ import annotations

from sqlalchemy.orm import Session

from landintel.domain.models import ActiveReleaseScope, ModelRelease
from landintel.domain.schemas import (
    ActiveReleaseScopeRead,
    ModelReleaseDetailRead,
    ModelReleaseListResponse,
    ModelReleaseSummaryRead,
)
from landintel.scoring.release import get_model_release, list_model_releases


def serialize_active_release_scope(scope: ActiveReleaseScope) -> ActiveReleaseScopeRead:
    return ActiveReleaseScopeRead(
        id=scope.id,
        scope_key=scope.scope_key,
        template_key=scope.template_key,
        release_channel=scope.release_channel,
        borough_id=scope.borough_id,
        model_release_id=scope.model_release_id,
        activated_by=scope.activated_by,
        activated_at=scope.activated_at,
    )


def serialize_model_release_summary(release: ModelRelease) -> ModelReleaseSummaryRead:
    return ModelReleaseSummaryRead(
        id=release.id,
        template_key=release.template_key,
        release_channel=release.release_channel,
        scope_key=release.scope_key,
        scope_borough_id=release.scope_borough_id,
        status=release.status,
        model_kind=release.model_kind,
        transform_version=release.transform_version,
        feature_version=release.feature_version,
        calibration_method=release.calibration_method,
        support_count=release.support_count,
        positive_count=release.positive_count,
        negative_count=release.negative_count,
        reason_text=release.reason_text,
        activated_by=release.activated_by,
        activated_at=release.activated_at,
        retired_by=release.retired_by,
        retired_at=release.retired_at,
        created_at=release.created_at,
        updated_at=release.updated_at,
    )


def serialize_model_release_detail(release: ModelRelease) -> ModelReleaseDetailRead:
    return ModelReleaseDetailRead(
        **serialize_model_release_summary(release).model_dump(),
        model_artifact_path=release.model_artifact_path,
        model_artifact_hash=release.model_artifact_hash,
        calibration_artifact_path=release.calibration_artifact_path,
        calibration_artifact_hash=release.calibration_artifact_hash,
        validation_artifact_path=release.validation_artifact_path,
        validation_artifact_hash=release.validation_artifact_hash,
        model_card_path=release.model_card_path,
        model_card_hash=release.model_card_hash,
        train_window_start=release.train_window_start,
        train_window_end=release.train_window_end,
        metrics_json=dict(release.metrics_json or {}),
        manifest_json=dict(release.manifest_json or {}),
        active_scopes=[
            serialize_active_release_scope(scope) for scope in release.active_scopes
        ],
    )


def list_model_releases_read(
    *,
    session: Session,
    template_key: str | None = None,
) -> ModelReleaseListResponse:
    rows = list_model_releases(session=session, template_key=template_key)
    return ModelReleaseListResponse(
        items=[serialize_model_release_summary(row) for row in rows],
        total=len(rows),
    )


def get_model_release_read(
    *,
    session: Session,
    release_id,
) -> ModelReleaseDetailRead | None:
    row = get_model_release(session=session, release_id=release_id)
    if row is None:
        return None
    return serialize_model_release_detail(row)
