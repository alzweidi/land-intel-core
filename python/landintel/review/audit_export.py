from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import AppRoleName, AuditExportStatus
from landintel.domain.models import AssessmentRun, AuditEvent, AuditExport, ValuationRun
from landintel.domain.schemas import AuditExportRead
from landintel.review.visibility import ReviewAccessError, require_role
from landintel.services.assessments_readback import get_assessment
from landintel.storage.base import StorageAdapter
from landintel.valuation.service import latest_valuation_run

AUDIT_EXPORT_NAMESPACE = uuid.UUID("b1fe5406-8f10-4cc6-b8c2-04e2d5032ea8")


def build_assessment_audit_export(
    *,
    session: Session,
    storage: StorageAdapter,
    assessment_id: uuid.UUID,
    requested_by: str | None,
    actor_role: AppRoleName | str | None,
) -> AuditExportRead:
    role = require_role(
        actor_role,
        allowed_roles={AppRoleName.REVIEWER, AppRoleName.ADMIN},
    )
    run = session.execute(
        select(AssessmentRun)
        .where(AssessmentRun.id == assessment_id)
        .options(
            selectinload(AssessmentRun.result),
            selectinload(AssessmentRun.prediction_ledger),
            selectinload(AssessmentRun.valuation_runs).selectinload(ValuationRun.result),
            selectinload(AssessmentRun.valuation_runs).selectinload(
                ValuationRun.valuation_assumption_set
            ),
            selectinload(AssessmentRun.overrides),
        )
    ).scalar_one_or_none()
    if run is None:
        raise ReviewAccessError(f"Assessment '{assessment_id}' was not found.")

    detail = get_assessment(
        session=session,
        assessment_id=assessment_id,
        include_hidden=True,
        viewer_role=role,
    )
    if detail is None:
        raise ReviewAccessError(f"Assessment '{assessment_id}' was not found.")

    valuation_run = latest_valuation_run(run)
    manifest = {
        "assessment": detail.model_dump(mode="json"),
        "site_summary": detail.site_summary.model_dump(mode="json")
        if detail.site_summary is not None
        else None,
        "scenario_summary": detail.scenario_summary.model_dump(mode="json")
        if detail.scenario_summary is not None
        else None,
        "override_history": [
            item.model_dump(mode="json")
            for item in (
                detail.override_summary.active_overrides if detail.override_summary else []
            )
        ],
        "visibility": (
            None if detail.visibility is None else detail.visibility.model_dump(mode="json")
        ),
        "audit_event_refs": _serialize_audit_events(
            session=session,
            entity_refs=_entity_refs_for_run(run),
        ),
    }

    manifest_bytes = _json_bytes(manifest)
    manifest_hash = _sha256(manifest_bytes)
    export_id = uuid.uuid5(AUDIT_EXPORT_NAMESPACE, f"{assessment_id}:{manifest_hash}")
    existing = session.get(AuditExport, export_id)
    if existing is None:
        manifest_path = f"artifacts/audit_exports/{export_id}/manifest.json"
        storage.put_bytes(
            manifest_path,
            manifest_bytes,
            content_type="application/json",
        )
        existing = AuditExport(
            id=export_id,
            assessment_run_id=run.id,
            assessment_result_id=None if run.result is None else run.result.id,
            valuation_run_id=None if valuation_run is None else valuation_run.id,
            prediction_ledger_id=(
                None if run.prediction_ledger is None else run.prediction_ledger.id
            ),
            model_release_id=None if run.result is None else run.result.model_release_id,
            status=AuditExportStatus.READY,
            manifest_path=manifest_path,
            manifest_hash=manifest_hash,
            manifest_json=manifest,
            requested_by=requested_by or "api-audit-export",
        )
        session.add(existing)
        session.add(
            AuditEvent(
                action="assessment_audit_export_built",
                entity_type="assessment_run",
                entity_id=str(run.id),
                before_json=None,
                after_json={
                    "audit_export_id": str(existing.id),
                    "manifest_hash": manifest_hash,
                    "requested_by": requested_by,
                    "actor_role": role.value,
                },
            )
        )
        session.flush()
    return AuditExportRead(
        id=existing.id,
        assessment_run_id=existing.assessment_run_id,
        assessment_result_id=existing.assessment_result_id,
        valuation_run_id=existing.valuation_run_id,
        prediction_ledger_id=existing.prediction_ledger_id,
        model_release_id=existing.model_release_id,
        status=existing.status,
        manifest_path=existing.manifest_path,
        manifest_hash=existing.manifest_hash,
        manifest_json=dict(existing.manifest_json or {}),
        requested_by=existing.requested_by,
        created_at=existing.created_at,
    )


def _entity_refs_for_run(run: AssessmentRun) -> list[tuple[str, str]]:
    refs = [("assessment_run", str(run.id))]
    if run.result is not None:
        refs.append(("assessment_result", str(run.result.id)))
        if run.result.model_release_id is not None:
            refs.append(("model_release", str(run.result.model_release_id)))
    if run.prediction_ledger is not None:
        refs.append(("prediction_ledger", str(run.prediction_ledger.id)))
    for override in run.overrides:
        refs.append(("assessment_override", str(override.id)))
    return refs


def _serialize_audit_events(
    *,
    session: Session,
    entity_refs: Iterable[tuple[str, str]],
) -> list[dict[str, str | None]]:
    refs = list(entity_refs)
    if not refs:
        return []
    entity_types = {entity_type for entity_type, _ in refs}
    entity_ids = {entity_id for _, entity_id in refs}
    rows = session.execute(
        select(AuditEvent)
        .where(AuditEvent.entity_type.in_(entity_types))
        .where(AuditEvent.entity_id.in_(entity_ids))
        .order_by(AuditEvent.created_at.asc())
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def _json_bytes(payload: dict[str, object]) -> bytes:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()
