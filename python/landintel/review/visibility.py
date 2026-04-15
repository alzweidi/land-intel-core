from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.domain.enums import (
    AppRoleName,
    BaselinePackStatus,
    IncidentStatus,
    IncidentType,
    VisibilityMode,
)
from landintel.domain.models import (
    ActiveReleaseScope,
    AssessmentRun,
    AuditEvent,
    BoroughBaselinePack,
    BoroughRulepack,
    IncidentRecord,
)
from landintel.domain.schemas import VisibilityGateRead


class ReviewAccessError(ValueError):
    pass


_PRIVILEGED_ROLES = {AppRoleName.REVIEWER, AppRoleName.ADMIN}
_ROLE_RANK = {
    AppRoleName.ANALYST: 0,
    AppRoleName.REVIEWER: 1,
    AppRoleName.ADMIN: 2,
}
_BLOCK_REASON_TEXT = {
    "NO_SCOPE": "No active release scope is registered for this assessment.",
    "SCOPE_DISABLED": "Visible probability is disabled for this scope.",
    "ACTIVE_INCIDENT": "An active incident is blocking visible probability for this scope.",
    "REPLAY_FAILED": "Replay verification for this frozen assessment did not pass.",
    "ARTIFACT_HASH_MISMATCH": "Stored release artifact hashes no longer match the frozen ledger.",
    "SCOPE_RELEASE_MISMATCH": "The active release scope no longer matches the frozen result.",
    "ROLE_REDACTED": "This viewer role is not permitted to see visible probability for this scope.",
}


def coerce_role(role: AppRoleName | str | None) -> AppRoleName:
    if isinstance(role, AppRoleName):
        return role
    if isinstance(role, str) and role.strip():
        return AppRoleName(role.strip().lower())
    return AppRoleName.ANALYST


def require_role(
    actor_role: AppRoleName | str | None,
    *,
    allowed_roles: Iterable[AppRoleName],
) -> AppRoleName:
    resolved = coerce_role(actor_role)
    if resolved not in set(allowed_roles):
        allowed = ", ".join(sorted(role.value for role in allowed_roles))
        raise ReviewAccessError(
            f"Role '{resolved.value}' is not permitted. Allowed roles: {allowed}."
        )
    return resolved


def role_at_least(actor_role: AppRoleName | str | None, minimum: AppRoleName) -> AppRoleName:
    resolved = coerce_role(actor_role)
    if _ROLE_RANK[resolved] < _ROLE_RANK[minimum]:
        raise ReviewAccessError(
            f"Role '{resolved.value}' is not permitted. Minimum required role is '{minimum.value}'."
        )
    return resolved


def load_active_scope(
    session: Session,
    *,
    scope_key: str | None,
) -> ActiveReleaseScope | None:
    if scope_key is None:
        return None
    return session.execute(
        select(ActiveReleaseScope).where(ActiveReleaseScope.scope_key == scope_key)
    ).scalar_one_or_none()


def get_open_incident_for_scope(
    session: Session,
    *,
    scope_id: UUID | None = None,
    scope_key: str | None = None,
) -> IncidentRecord | None:
    stmt = select(IncidentRecord).where(IncidentRecord.status == IncidentStatus.OPEN)
    if scope_id is not None:
        stmt = stmt.where(IncidentRecord.active_release_scope_id == scope_id)
    elif scope_key is not None:
        stmt = stmt.where(IncidentRecord.scope_key == scope_key)
    else:
        return None
    stmt = stmt.order_by(IncidentRecord.created_at.desc())
    return session.execute(stmt).scalar_one_or_none()


def evaluate_assessment_visibility(
    *,
    session: Session,
    assessment_run: AssessmentRun,
    viewer_role: AppRoleName | str | None,
    include_hidden: bool = False,
) -> VisibilityGateRead:
    role = coerce_role(viewer_role)
    result = assessment_run.result
    ledger = assessment_run.prediction_ledger
    scope = load_active_scope(
        session,
        scope_key=None if result is None else result.release_scope_key,
    )
    visibility_mode = scope.visibility_mode if scope is not None else VisibilityMode.HIDDEN_ONLY
    active_incident = (
        None
        if scope is None
        else get_open_incident_for_scope(session, scope_id=scope.id, scope_key=scope.scope_key)
    )

    payload_hash_matches = False
    if result is not None and ledger is not None:
        payload_hash_matches = _payload_hash_matches(assessment_run)

    artifact_hashes_match = True
    scope_release_matches_result = True
    if result is not None and result.model_release_id is not None:
        if scope is None:
            artifact_hashes_match = False
            scope_release_matches_result = False
        else:
            release = scope.model_release
            scope_release_matches_result = result.model_release_id == scope.model_release_id
            artifact_hashes_match = (
                ledger is not None
                and ledger.model_artifact_hash == release.model_artifact_hash
                and ledger.validation_artifact_hash == release.validation_artifact_hash
                and ledger.calibration_hash == release.calibration_artifact_hash
            )

    blocked_reason_codes: list[str] = []
    if result is not None and result.approval_probability_raw is not None:
        if scope is None:
            blocked_reason_codes.append("NO_SCOPE")
        else:
            if visibility_mode == VisibilityMode.DISABLED:
                blocked_reason_codes.append("SCOPE_DISABLED")
            if active_incident is not None:
                blocked_reason_codes.append("ACTIVE_INCIDENT")
            if not payload_hash_matches:
                blocked_reason_codes.append("REPLAY_FAILED")
            if not artifact_hashes_match:
                blocked_reason_codes.append("ARTIFACT_HASH_MISMATCH")
            if not scope_release_matches_result:
                blocked_reason_codes.append("SCOPE_RELEASE_MISMATCH")

    hidden_probability_allowed = (
        include_hidden
        and role in _PRIVILEGED_ROLES
        and result is not None
        and result.approval_probability_raw is not None
    )
    visible_probability_allowed = (
        not include_hidden
        and role in _PRIVILEGED_ROLES
        and result is not None
        and result.approval_probability_display is not None
        and visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY
        and not blocked_reason_codes
    )
    if (
        not hidden_probability_allowed
        and not visible_probability_allowed
        and result is not None
        and result.approval_probability_raw is not None
        and role not in _PRIVILEGED_ROLES
        and visibility_mode != VisibilityMode.DISABLED
        and not blocked_reason_codes
    ):
        blocked_reason_codes.append("ROLE_REDACTED")

    blocked = any(code != "ROLE_REDACTED" for code in blocked_reason_codes)
    blocked_reason_text = (
        None
        if not blocked_reason_codes
        else _BLOCK_REASON_TEXT.get(blocked_reason_codes[0], blocked_reason_codes[0])
    )
    exposure_mode = "REDACTED"
    if hidden_probability_allowed:
        exposure_mode = "HIDDEN_INTERNAL"
    elif visible_probability_allowed:
        exposure_mode = "VISIBLE_REVIEWER_ONLY"

    return VisibilityGateRead(
        scope_key=None if result is None else result.release_scope_key,
        visibility_mode=visibility_mode,
        exposure_mode=exposure_mode,
        viewer_role=role,
        visible_probability_allowed=visible_probability_allowed,
        hidden_probability_allowed=hidden_probability_allowed,
        blocked=blocked,
        blocked_reason_codes=blocked_reason_codes,
        blocked_reason_text=blocked_reason_text,
        active_incident_id=None if active_incident is None else active_incident.id,
        active_incident_reason=None if active_incident is None else active_incident.reason,
        replay_verified=payload_hash_matches,
        payload_hash_matches=payload_hash_matches,
        artifact_hashes_match=artifact_hashes_match,
        scope_release_matches_result=scope_release_matches_result,
    )


def set_scope_visibility(
    *,
    session: Session,
    scope_key: str,
    visibility_mode: VisibilityMode,
    requested_by: str | None,
    actor_role: AppRoleName | str | None,
    reason: str,
) -> ActiveReleaseScope:
    role_at_least(actor_role, AppRoleName.ADMIN)
    scope = load_active_scope(session, scope_key=scope_key)
    if scope is None:
        raise ReviewAccessError(f"Active release scope '{scope_key}' was not found.")
    if visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY:
        if scope.borough_id is None:
            raise ReviewAccessError(
                "Reviewer-visible mode requires a borough-scoped active release. "
                "London-wide hidden scopes cannot be made visible."
            )
        baseline_pack = session.execute(
            select(BoroughBaselinePack)
            .where(BoroughBaselinePack.borough_id == scope.borough_id)
            .order_by(BoroughBaselinePack.created_at.desc())
        ).scalar_one_or_none()
        if baseline_pack is None or baseline_pack.status != BaselinePackStatus.SIGNED_OFF:
            raise ReviewAccessError(
                "Reviewer-visible mode requires a signed-off borough baseline pack."
            )
        rulepack = session.execute(
            select(BoroughRulepack)
            .where(BoroughRulepack.borough_baseline_pack_id == baseline_pack.id)
            .where(BoroughRulepack.template_key == scope.template_key)
            .order_by(BoroughRulepack.created_at.desc())
        ).scalar_one_or_none()
        if rulepack is None or rulepack.status != BaselinePackStatus.SIGNED_OFF:
            raise ReviewAccessError(
                "Reviewer-visible mode requires a signed-off borough rulepack for this template."
            )

    before_json = {
        "visibility_mode": scope.visibility_mode.value,
        "visibility_reason": scope.visibility_reason,
        "visible_enabled_by": scope.visible_enabled_by,
        "visible_enabled_at": None
        if scope.visible_enabled_at is None
        else scope.visible_enabled_at.isoformat(),
    }
    scope.visibility_mode = visibility_mode
    scope.visibility_reason = reason
    scope.visibility_updated_by = requested_by or "api-admin"
    scope.visibility_updated_at = datetime.now(UTC)
    if visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY:
        scope.visible_enabled_by = requested_by or "api-admin"
        scope.visible_enabled_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            action="release_scope_visibility_changed",
            entity_type="active_release_scope",
            entity_id=str(scope.id),
            before_json=before_json,
            after_json={
                "visibility_mode": scope.visibility_mode.value,
                "visibility_reason": scope.visibility_reason,
                "requested_by": requested_by,
            },
        )
    )
    session.flush()
    return scope


def open_scope_incident(
    *,
    session: Session,
    scope_key: str,
    requested_by: str | None,
    actor_role: AppRoleName | str | None,
    reason: str,
    incident_type: IncidentType = IncidentType.VISIBILITY_KILL_SWITCH,
) -> IncidentRecord:
    role_at_least(actor_role, AppRoleName.ADMIN)
    scope = load_active_scope(session, scope_key=scope_key)
    if scope is None:
        raise ReviewAccessError(f"Active release scope '{scope_key}' was not found.")

    existing = get_open_incident_for_scope(session, scope_id=scope.id)
    if existing is not None:
        return existing

    previous_mode = scope.visibility_mode
    scope.visibility_mode = VisibilityMode.DISABLED
    scope.visibility_reason = reason
    scope.visibility_updated_by = requested_by or "api-admin"
    scope.visibility_updated_at = datetime.now(UTC)
    incident = IncidentRecord(
        active_release_scope_id=scope.id,
        model_release_id=scope.model_release_id,
        scope_key=scope.scope_key,
        template_key=scope.template_key,
        borough_id=scope.borough_id,
        incident_type=incident_type,
        status=IncidentStatus.OPEN,
        reason=reason,
        previous_visibility_mode=previous_mode,
        applied_visibility_mode=VisibilityMode.DISABLED,
        created_by=requested_by or "api-admin",
    )
    session.add(incident)
    session.add(
        AuditEvent(
            action="release_scope_incident_opened",
            entity_type="active_release_scope",
            entity_id=str(scope.id),
            before_json={"visibility_mode": previous_mode.value},
            after_json={
                "visibility_mode": scope.visibility_mode.value,
                "reason": reason,
                "requested_by": requested_by,
            },
        )
    )
    session.flush()
    return incident


def resolve_scope_incident(
    *,
    session: Session,
    scope_key: str,
    requested_by: str | None,
    actor_role: AppRoleName | str | None,
    reason: str,
    rollback_visibility: bool,
) -> IncidentRecord:
    role_at_least(actor_role, AppRoleName.ADMIN)
    scope = load_active_scope(session, scope_key=scope_key)
    if scope is None:
        raise ReviewAccessError(f"Active release scope '{scope_key}' was not found.")
    incident = get_open_incident_for_scope(session, scope_id=scope.id)
    if incident is None:
        raise ReviewAccessError(f"No open incident exists for scope '{scope_key}'.")

    previous_mode = scope.visibility_mode
    if rollback_visibility and incident.previous_visibility_mode is not None:
        scope.visibility_mode = incident.previous_visibility_mode
        scope.visibility_reason = reason
        scope.visibility_updated_by = requested_by or "api-admin"
        scope.visibility_updated_at = datetime.now(UTC)
        if scope.visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY:
            scope.visible_enabled_by = requested_by or "api-admin"
            scope.visible_enabled_at = datetime.now(UTC)

    incident.status = IncidentStatus.RESOLVED
    incident.resolved_by = requested_by or "api-admin"
    incident.resolved_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            action="release_scope_incident_resolved",
            entity_type="active_release_scope",
            entity_id=str(scope.id),
            before_json={"visibility_mode": previous_mode.value},
            after_json={
                "visibility_mode": scope.visibility_mode.value,
                "reason": reason,
                "requested_by": requested_by,
                "rollback_visibility": rollback_visibility,
            },
        )
    )
    session.flush()
    return incident


def _payload_hash_matches(assessment_run: AssessmentRun) -> bool:
    if (
        assessment_run.feature_snapshot is None
        or assessment_run.result is None
        or assessment_run.prediction_ledger is None
    ):
        return False

    from landintel.assessments.service import (
        _build_stable_result_payload,
        _note_for_result,
        _pack_from_rows,
        _serialize_valuation_payload,
        _stable_comparable_payload,
    )
    from landintel.features.build import canonical_json_hash
    from landintel.valuation.service import latest_valuation_run

    evidence = _pack_from_rows(assessment_run.evidence_items)
    comparable_payload = _stable_comparable_payload(assessment_run)
    valuation_run = latest_valuation_run(assessment_run)
    valuation_payload = (
        None
        if valuation_run is None or valuation_run.result is None
        else _serialize_valuation_payload(valuation_run)
    )
    stable_payload = _build_stable_result_payload(
        site_id=assessment_run.site_id,
        scenario_id=assessment_run.scenario_id,
        as_of_date=assessment_run.as_of_date,
        red_line_geom_hash=assessment_run.scenario.red_line_geom_hash,
        feature_snapshot=assessment_run.feature_snapshot,
        result=assessment_run.result,
        valuation_payload=valuation_payload,
        evidence=evidence,
        comparables=comparable_payload,
        note_text=_note_for_result(assessment_run.result),
    )
    return (
        canonical_json_hash(stable_payload)
        == assessment_run.prediction_ledger.result_payload_hash
    )
