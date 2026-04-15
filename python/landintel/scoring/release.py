from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import CalibrationMethod, ModelReleaseStatus, ReleaseChannel
from landintel.domain.models import ActiveReleaseScope, AuditEvent, ModelRelease, ScenarioTemplate
from landintel.planning.historical_labels import rebuild_historical_case_labels
from landintel.scenarios.catalog import get_enabled_scenario_templates
from landintel.storage.base import StorageAdapter

from .train import build_model_card_markdown, build_training_manifest, load_training_rows

RELEASE_NAMESPACE = uuid.UUID("2bcd68fd-03ba-46a7-b7d6-a25771151a92")


def scope_key_for(
    *,
    template_key: str,
    release_channel: ReleaseChannel = ReleaseChannel.HIDDEN,
    borough_id: str | None = None,
) -> str:
    return f"{release_channel.value}:{borough_id or 'london'}:{template_key}"


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _release_id(*, scope_key: str, payload_hash: str) -> uuid.UUID:
    return uuid.uuid5(RELEASE_NAMESPACE, f"{scope_key}:{payload_hash}")


def build_hidden_model_releases(
    *,
    session: Session,
    storage: StorageAdapter,
    requested_by: str | None,
    template_keys: list[str] | None = None,
    auto_activate_hidden: bool = False,
) -> list[ModelRelease]:
    rebuild_historical_case_labels(
        session=session,
        requested_by=requested_by or "model-release-build",
    )
    templates = get_enabled_scenario_templates(session, template_keys=template_keys)
    releases: list[ModelRelease] = []
    for template in templates:
        release = _build_template_release(
            session=session,
            storage=storage,
            template=template,
            requested_by=requested_by,
        )
        releases.append(release)
        if auto_activate_hidden and release.status == ModelReleaseStatus.VALIDATED:
            activate_model_release(
                session=session,
                release_id=release.id,
                requested_by=requested_by,
            )
    return releases


def _build_template_release(
    *,
    session: Session,
    storage: StorageAdapter,
    template: ScenarioTemplate,
    requested_by: str | None,
) -> ModelRelease:
    rows = load_training_rows(session=session, template_key=template.key)
    manifest = build_training_manifest(template_key=template.key, rows=rows)
    scope_key = scope_key_for(template_key=template.key)
    release_id = _release_id(scope_key=scope_key, payload_hash=str(manifest["payload_hash"]))
    existing = session.get(ModelRelease, release_id)
    if existing is not None:
        return existing

    validation_payload = (
        manifest["validation"] if manifest["status"] == "VALIDATED" else manifest
    )
    validation_bytes = _json_bytes(validation_payload)
    validation_hash = _sha256(validation_bytes)
    validation_path = f"artifacts/model_releases/{release_id}/validation.json"
    storage.put_bytes(validation_path, validation_bytes, content_type="application/json")

    model_card_text = build_model_card_markdown(manifest)
    model_card_bytes = model_card_text.encode("utf-8")
    model_card_hash = _sha256(model_card_bytes)
    model_card_path = f"artifacts/model_releases/{release_id}/model_card.md"
    storage.put_bytes(model_card_path, model_card_bytes, content_type="text/markdown")

    model_artifact_path = None
    model_artifact_hash = None
    calibration_artifact_path = None
    calibration_artifact_hash = None
    calibration_method = CalibrationMethod.NONE
    metrics_json = (
        manifest["validation"].get("metrics", {})
        if manifest["status"] == "VALIDATED"
        else {}
    )

    if manifest["status"] == "VALIDATED":
        model_bytes = _json_bytes(manifest["model_artifact"])
        model_artifact_hash = _sha256(model_bytes)
        model_artifact_path = f"artifacts/model_releases/{release_id}/model.json"
        storage.put_bytes(model_artifact_path, model_bytes, content_type="application/json")

        calibration_bytes = _json_bytes(manifest["calibration_artifact"])
        calibration_artifact_hash = _sha256(calibration_bytes)
        calibration_artifact_path = f"artifacts/model_releases/{release_id}/calibration.json"
        storage.put_bytes(
            calibration_artifact_path,
            calibration_bytes,
            content_type="application/json",
        )
        calibration_method = CalibrationMethod.PLATT

    release = ModelRelease(
        id=release_id,
        template_key=template.key,
        release_channel=ReleaseChannel.HIDDEN,
        scope_key=scope_key,
        scope_borough_id=None,
        status=(
            ModelReleaseStatus.VALIDATED
            if manifest["status"] == "VALIDATED"
            else ModelReleaseStatus.NOT_READY
        ),
        model_kind="REGULARIZED_LOGISTIC_REGRESSION",
        transform_version=str(manifest["transform_version"]),
        feature_version=str(manifest["feature_version"]),
        calibration_method=calibration_method,
        model_artifact_path=model_artifact_path,
        model_artifact_hash=model_artifact_hash,
        calibration_artifact_path=calibration_artifact_path,
        calibration_artifact_hash=calibration_artifact_hash,
        validation_artifact_path=validation_path,
        validation_artifact_hash=validation_hash,
        model_card_path=model_card_path,
        model_card_hash=model_card_hash,
        train_window_start=manifest.get("train_window_start"),
        train_window_end=manifest.get("train_window_end"),
        support_count=int(manifest["support_counts"]["total"]),
        positive_count=int(manifest["support_counts"]["positive"]),
        negative_count=int(manifest["support_counts"]["negative"]),
        metrics_json=metrics_json,
        manifest_json={
            "payload_hash": manifest["payload_hash"],
            "support_counts": manifest["support_counts"],
            "validation_summary": manifest["validation"]
            if manifest["status"] == "VALIDATED"
            else {
                "status": "NOT_READY",
                "not_ready_reasons": list(manifest.get("not_ready_reasons") or []),
                "support_counts": manifest["support_counts"],
                "validation_rows": list(manifest.get("rows") or []),
                "leakage_checks": dict(manifest.get("leakage_checks") or {}),
            },
            "source_snapshot_ids": list(manifest.get("source_snapshot_ids") or []),
            "raw_asset_ids": list(manifest.get("raw_asset_ids") or []),
            "feature_hashes": list(manifest.get("feature_hashes") or []),
        },
        reason_text=(
            None
            if manifest["status"] == "VALIDATED"
            else "; ".join(list(manifest.get("not_ready_reasons") or []))
        ),
    )
    session.add(release)
    session.add(
        AuditEvent(
            action="model_release_registered",
            entity_type="model_release",
            entity_id=str(release.id),
            before_json=None,
            after_json={
                "template_key": template.key,
                "status": release.status.value,
                "scope_key": scope_key,
                "requested_by": requested_by,
            },
        )
    )
    session.flush()
    return release


def list_model_releases(
    *,
    session: Session,
    template_key: str | None = None,
) -> list[ModelRelease]:
    stmt = select(ModelRelease).options(selectinload(ModelRelease.active_scopes)).order_by(
        ModelRelease.created_at.desc()
    )
    if template_key is not None:
        stmt = stmt.where(ModelRelease.template_key == template_key)
    return session.execute(stmt).scalars().all()


def get_model_release(*, session: Session, release_id: uuid.UUID) -> ModelRelease | None:
    return session.execute(
        select(ModelRelease)
        .where(ModelRelease.id == release_id)
        .options(selectinload(ModelRelease.active_scopes))
    ).scalar_one_or_none()


def activate_model_release(
    *,
    session: Session,
    release_id: uuid.UUID,
    requested_by: str | None,
) -> ActiveReleaseScope:
    release = session.get(ModelRelease, release_id)
    if release is None:
        raise ValueError(f"Model release '{release_id}' was not found.")
    if release.status == ModelReleaseStatus.NOT_READY:
        raise ValueError("Model release is not ready and cannot be activated.")

    existing = session.execute(
        select(ActiveReleaseScope).where(ActiveReleaseScope.scope_key == release.scope_key)
    ).scalar_one_or_none()
    if existing is not None and existing.model_release_id != release.id:
        prior = session.get(ModelRelease, existing.model_release_id)
        if prior is not None:
            prior.status = ModelReleaseStatus.RETIRED
            prior.retired_by = requested_by
            prior.retired_at = datetime.now(UTC)

    if existing is None:
        existing = ActiveReleaseScope(
            scope_key=release.scope_key,
            template_key=release.template_key,
            release_channel=release.release_channel,
            borough_id=release.scope_borough_id,
            model_release_id=release.id,
            activated_by=requested_by,
        )
        session.add(existing)
    else:
        existing.model_release_id = release.id
        existing.template_key = release.template_key
        existing.release_channel = release.release_channel
        existing.borough_id = release.scope_borough_id
        existing.activated_by = requested_by
        existing.activated_at = datetime.now(UTC)

    release.status = ModelReleaseStatus.ACTIVE
    release.activated_by = requested_by
    release.activated_at = datetime.now(UTC)
    release.retired_by = None
    release.retired_at = None
    session.add(
        AuditEvent(
            action="model_release_activated",
            entity_type="model_release",
            entity_id=str(release.id),
            before_json=None,
            after_json={
                "scope_key": release.scope_key,
                "requested_by": requested_by,
            },
        )
    )
    session.flush()
    return existing


def retire_model_release(
    *,
    session: Session,
    release_id: uuid.UUID,
    requested_by: str | None,
) -> ModelRelease:
    release = session.get(ModelRelease, release_id)
    if release is None:
        raise ValueError(f"Model release '{release_id}' was not found.")
    scopes = session.execute(
        select(ActiveReleaseScope).where(ActiveReleaseScope.model_release_id == release.id)
    ).scalars().all()
    for scope in scopes:
        session.delete(scope)
    release.status = ModelReleaseStatus.RETIRED
    release.retired_by = requested_by
    release.retired_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            action="model_release_retired",
            entity_type="model_release",
            entity_id=str(release.id),
            before_json=None,
            after_json={"requested_by": requested_by},
        )
    )
    session.flush()
    return release


def resolve_active_release(
    *,
    session: Session,
    template_key: str,
    borough_id: str | None = None,
    release_channel: ReleaseChannel = ReleaseChannel.HIDDEN,
) -> tuple[ModelRelease | None, str]:
    exact_scope = scope_key_for(
        template_key=template_key,
        release_channel=release_channel,
        borough_id=borough_id,
    )
    exact = session.execute(
        select(ActiveReleaseScope)
        .where(ActiveReleaseScope.scope_key == exact_scope)
        .options(selectinload(ActiveReleaseScope.model_release))
    ).scalar_one_or_none()
    if exact is not None:
        return exact.model_release, exact.scope_key

    global_scope = scope_key_for(template_key=template_key, release_channel=release_channel)
    row = session.execute(
        select(ActiveReleaseScope)
        .where(ActiveReleaseScope.scope_key == global_scope)
        .options(selectinload(ActiveReleaseScope.model_release))
    ).scalar_one_or_none()
    if row is None:
        return None, global_scope
    return row.model_release, row.scope_key


def load_release_artifact_json(
    *,
    storage: StorageAdapter,
    release: ModelRelease,
    artifact: str,
) -> dict[str, Any] | None:
    path = {
        "model": release.model_artifact_path,
        "calibration": release.calibration_artifact_path,
        "validation": release.validation_artifact_path,
    }[artifact]
    if not path:
        return None
    return json.loads(storage.get_bytes(path))
