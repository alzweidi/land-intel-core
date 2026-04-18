from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideType,
    BaselinePackStatus,
    CalibrationMethod,
    GoldSetReviewStatus,
    IncidentStatus,
    IncidentType,
    JobStatus,
    JobType,
    ModelReleaseStatus,
    PriceBasisType,
    ReleaseChannel,
    VisibilityMode,
)
from landintel.domain.models import (
    ActiveReleaseScope,
    BoroughBaselinePack,
    BoroughRulepack,
    IncidentRecord,
    ModelRelease,
)
from landintel.domain.schemas import (
    AssessmentOverrideRequest,
    IncidentActionRequest,
    JobRunRead,
    ModelReleaseActivateRequest,
    ModelReleaseRetireRequest,
    ReleaseScopeVisibilityRequest,
    VisibilityGateRead,
)
from landintel.review import overrides as overrides_service
from landintel.review import visibility as visibility_service
from landintel.review.visibility import ReviewAccessError

from services.api.app.routes import admin as admin_routes

FIXED_NOW = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)


def _make_release(
    *,
    scope_key: str,
    template_key: str = "resi_5_9_full",
    borough_id: str = "camden",
) -> ModelRelease:
    return ModelRelease(
        id=uuid4(),
        template_key=template_key,
        release_channel=ReleaseChannel.HIDDEN,
        scope_key=scope_key,
        scope_borough_id=borough_id,
        status=ModelReleaseStatus.VALIDATED,
        model_kind="REGULARIZED_LOGISTIC_REGRESSION",
        transform_version="v1",
        feature_version="phase8a_v1",
        calibration_method=CalibrationMethod.NONE,
        model_artifact_path=None,
        model_artifact_hash=None,
        calibration_artifact_path=None,
        calibration_artifact_hash=None,
        validation_artifact_path=None,
        validation_artifact_hash=None,
        model_card_path=None,
        model_card_hash=None,
        support_count=0,
        positive_count=0,
        negative_count=0,
        metrics_json={},
        manifest_json={},
    )


def _seed_scope_with_release(
    db_session,
    *,
    scope_key: str,
    borough_id: str = "camden",
    template_key: str = "resi_5_9_full",
) -> tuple[ModelRelease, ActiveReleaseScope]:
    release = _make_release(scope_key=scope_key, borough_id=borough_id, template_key=template_key)
    scope = ActiveReleaseScope(
        scope_key=scope_key,
        template_key=template_key,
        release_channel=release.release_channel,
        borough_id=borough_id,
        model_release_id=release.id,
    )
    db_session.add_all([release, scope])
    db_session.flush()
    return release, scope


def _seed_signed_off_visibility_pack(
    db_session,
    *,
    borough_id: str,
    template_key: str,
) -> tuple[BoroughBaselinePack, BoroughRulepack]:
    baseline_pack = BoroughBaselinePack(
        borough_id=borough_id,
        version="2026-04",
        status=BaselinePackStatus.SIGNED_OFF,
        pack_json={},
    )
    db_session.add(baseline_pack)
    db_session.flush()
    rulepack = BoroughRulepack(
        borough_baseline_pack_id=baseline_pack.id,
        template_key=template_key,
        status=BaselinePackStatus.SIGNED_OFF,
        rule_json={},
    )
    db_session.add(rulepack)
    db_session.flush()
    return baseline_pack, rulepack


def _job_payload(job_id: UUID | None = None) -> dict[str, object]:
    return {
        "id": uuid4() if job_id is None else job_id,
        "job_type": JobType.GOLD_SET_REFRESH,
        "status": JobStatus.QUEUED,
        "attempts": 2,
        "run_at": FIXED_NOW,
        "next_run_at": FIXED_NOW,
        "locked_at": None,
        "worker_id": "worker-test-1",
        "error_text": None,
        "payload_json": {"limit": 5},
    }


def test_visibility_helpers_cover_no_scope_hash_mismatch_and_redaction_branches(
    db_session,
):
    scope_key = "scope-no-scope"
    incident = IncidentRecord(
        scope_key=scope_key,
        template_key="resi_5_9_full",
        incident_type=IncidentType.VISIBILITY_KILL_SWITCH,
        status=IncidentStatus.OPEN,
        reason="Active incident for scope-key lookup.",
        applied_visibility_mode=VisibilityMode.DISABLED,
        created_by="pytest",
    )
    db_session.add(incident)
    db_session.flush()

    matched_incident = visibility_service.get_open_incident_for_scope(
        session=db_session,
        scope_key=scope_key,
    )
    assert matched_incident is not None
    assert matched_incident.id == incident.id
    assert visibility_service.get_open_incident_for_scope(session=db_session) is None

    no_scope_result = SimpleNamespace(
        release_scope_key="scope-no-scope",
        approval_probability_raw=0.61,
        approval_probability_display=0.6,
        model_release_id=uuid4(),
    )
    no_scope_ledger = SimpleNamespace(replay_verification_status="VERIFIED")
    no_scope_run = SimpleNamespace(
        result=no_scope_result,
        prediction_ledger=no_scope_ledger,
        feature_snapshot={"frozen": True},
    )
    monkeypatched_scope = SimpleNamespace(
        id=uuid4(),
        scope_key="scope-no-scope",
        visibility_mode=VisibilityMode.HIDDEN_ONLY,
        model_release_id=None,
        model_release=SimpleNamespace(
            model_artifact_hash="artifact-hash",
            validation_artifact_hash="validation-hash",
            calibration_artifact_hash="calibration-hash",
        ),
    )
    original_load_active_scope = visibility_service.load_active_scope
    original_get_open_incident = visibility_service.get_open_incident_for_scope
    original_payload_hash_matches = visibility_service._payload_hash_matches
    try:
        visibility_service.load_active_scope = lambda _session, *, scope_key: None
        visibility_service.get_open_incident_for_scope = lambda *args, **kwargs: None
        visibility_service._payload_hash_matches = lambda _run: True
        no_scope_gate = visibility_service.evaluate_assessment_visibility(
            session=db_session,
            assessment_run=no_scope_run,
            viewer_role=AppRoleName.ANALYST,
            include_hidden=False,
        )
        assert no_scope_gate.blocked is True
        assert no_scope_gate.blocked_reason_codes == ["NO_SCOPE"]
        assert (
            no_scope_gate.blocked_reason_text == visibility_service._BLOCK_REASON_TEXT["NO_SCOPE"]
        )
        assert no_scope_gate.exposure_mode == "REDACTED"
        assert no_scope_gate.visible_probability_allowed is False
        assert no_scope_gate.hidden_probability_allowed is False
        assert no_scope_gate.payload_hash_matches is None

        visibility_service.load_active_scope = lambda _session, *, scope_key: monkeypatched_scope
        artifact_mismatch_result = SimpleNamespace(
            release_scope_key="scope-with-scope",
            approval_probability_raw=0.73,
            approval_probability_display=0.7,
            model_release_id=uuid4(),
        )
        artifact_mismatch_ledger = SimpleNamespace(
            replay_verification_status="VERIFIED",
            model_artifact_hash="different-model-hash",
            validation_artifact_hash="different-validation-hash",
            calibration_hash="different-calibration-hash",
        )
        artifact_mismatch_run = SimpleNamespace(
            result=artifact_mismatch_result,
            prediction_ledger=artifact_mismatch_ledger,
            feature_snapshot={"frozen": True},
        )
        artifact_gate = visibility_service.evaluate_assessment_visibility(
            session=db_session,
            assessment_run=artifact_mismatch_run,
            viewer_role=AppRoleName.REVIEWER,
            include_hidden=False,
        )
        assert artifact_gate.blocked is True
        assert artifact_gate.blocked_reason_codes == [
            "ARTIFACT_HASH_MISMATCH",
            "SCOPE_RELEASE_MISMATCH",
        ]
        assert (
            artifact_gate.blocked_reason_text
            == visibility_service._BLOCK_REASON_TEXT["ARTIFACT_HASH_MISMATCH"]
        )
        assert artifact_gate.replay_verified is True
        assert artifact_gate.exposure_mode == "REDACTED"
        assert artifact_gate.visible_probability_allowed is False
        assert artifact_gate.hidden_probability_allowed is False

        internal_gate = VisibilityGateRead(
            scope_key="scope-with-scope",
            visibility_mode=VisibilityMode.HIDDEN_ONLY,
            exposure_mode="REDACTED",
            viewer_role=AppRoleName.ANALYST,
            visible_probability_allowed=False,
            hidden_probability_allowed=False,
            blocked=True,
            blocked_reason_codes=["REPLAY_FAILED"],
            blocked_reason_text=visibility_service._BLOCK_REASON_TEXT["REPLAY_FAILED"],
            active_incident_id=uuid4(),
            active_incident_reason="internal block",
            replay_verified=False,
            payload_hash_matches=False,
            artifact_hashes_match=False,
            scope_release_matches_result=False,
        )
        redacted_gate = visibility_service._redact_visibility_gate_for_role(
            gate=internal_gate,
            viewer_role=AppRoleName.ANALYST,
        )
        assert redacted_gate.blocked_reason_codes == ["OUTPUT_BLOCKED"]
        assert (
            redacted_gate.blocked_reason_text
            == visibility_service._BLOCK_REASON_TEXT["OUTPUT_BLOCKED"]
        )
        assert redacted_gate.active_incident_id is None
        assert redacted_gate.active_incident_reason is None
        assert redacted_gate.replay_verified is None
        assert redacted_gate.payload_hash_matches is None
        assert redacted_gate.artifact_hashes_match is None
        assert redacted_gate.scope_release_matches_result is None
    finally:
        visibility_service.load_active_scope = original_load_active_scope
        visibility_service.get_open_incident_for_scope = original_get_open_incident
        visibility_service._payload_hash_matches = original_payload_hash_matches

    assert (
        visibility_service._payload_hash_matches(
            SimpleNamespace(
                feature_snapshot=None,
                result=SimpleNamespace(),
                prediction_ledger=SimpleNamespace(),
            )
        )
        is False
    )


def test_visibility_scope_mutation_and_incident_branches(db_session):
    visible_scope_key = "scope-visible-reviewer"
    _, visible_scope = _seed_scope_with_release(
        db_session,
        scope_key=visible_scope_key,
        borough_id="camden",
        template_key="resi_5_9_full",
    )
    _seed_signed_off_visibility_pack(
        db_session,
        borough_id="camden",
        template_key="resi_5_9_full",
    )

    updated_scope = visibility_service.set_scope_visibility(
        session=db_session,
        scope_key=visible_scope_key,
        visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        requested_by="pytest-visible",
        actor_role=AppRoleName.ADMIN,
        reason="Enable reviewer visibility for the pilot borough.",
    )
    assert updated_scope.id == visible_scope.id
    assert updated_scope.visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY
    assert updated_scope.visibility_reason == "Enable reviewer visibility for the pilot borough."
    assert updated_scope.visibility_updated_by == "pytest-visible"
    assert updated_scope.visible_enabled_by == "pytest-visible"
    assert updated_scope.visible_enabled_at is not None

    open_scope_key = "scope-open-existing"
    _, open_scope = _seed_scope_with_release(
        db_session,
        scope_key=open_scope_key,
        borough_id="camden",
        template_key="resi_1_4_full",
    )
    open_incident = IncidentRecord(
        active_release_scope_id=open_scope.id,
        scope_key=open_scope_key,
        template_key="resi_1_4_full",
        incident_type=IncidentType.VISIBILITY_BLOCK,
        status=IncidentStatus.OPEN,
        reason="Existing open incident.",
        previous_visibility_mode=VisibilityMode.HIDDEN_ONLY,
        applied_visibility_mode=VisibilityMode.DISABLED,
        created_by="pytest",
    )
    db_session.add(open_incident)
    db_session.flush()

    by_scope_key = visibility_service.get_open_incident_for_scope(
        session=db_session,
        scope_key=open_scope_key,
    )
    assert by_scope_key is not None
    assert by_scope_key.id == open_incident.id

    returned_existing = visibility_service.open_scope_incident(
        session=db_session,
        scope_key=open_scope_key,
        requested_by="pytest-existing",
        actor_role=AppRoleName.ADMIN,
        reason="Should return the existing incident.",
    )
    assert returned_existing.id == open_incident.id
    assert open_scope.visibility_mode == VisibilityMode.HIDDEN_ONLY

    with pytest.raises(
        ReviewAccessError, match=r"Active release scope 'missing-scope' was not found\."
    ):
        visibility_service.open_scope_incident(
            session=db_session,
            scope_key="missing-scope",
            requested_by="pytest-missing",
            actor_role=AppRoleName.ADMIN,
            reason="Missing scope.",
        )

    rollback_scope_key = "scope-rollback-visible"
    _, rollback_scope = _seed_scope_with_release(
        db_session,
        scope_key=rollback_scope_key,
        borough_id="camden",
        template_key="resi_10_49_outline",
    )
    rollback_scope.visibility_mode = VisibilityMode.DISABLED
    rollback_incident = IncidentRecord(
        active_release_scope_id=rollback_scope.id,
        scope_key=rollback_scope_key,
        template_key="resi_10_49_outline",
        incident_type=IncidentType.VISIBILITY_KILL_SWITCH,
        status=IncidentStatus.OPEN,
        reason="Rollback after reviewer-visible toggle.",
        previous_visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        applied_visibility_mode=VisibilityMode.DISABLED,
        created_by="pytest",
    )
    db_session.add(rollback_incident)
    db_session.flush()

    resolved = visibility_service.resolve_scope_incident(
        session=db_session,
        scope_key=rollback_scope_key,
        requested_by="pytest-rollback",
        actor_role=AppRoleName.ADMIN,
        reason="Restore the previous reviewer-visible mode.",
        rollback_visibility=True,
    )
    assert resolved.id == rollback_incident.id
    assert resolved.status == IncidentStatus.RESOLVED
    assert rollback_scope.visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY
    assert rollback_scope.visibility_updated_by == "pytest-rollback"
    assert rollback_scope.visible_enabled_by == "pytest-rollback"
    assert rollback_scope.visible_enabled_at is not None

    with pytest.raises(ReviewAccessError, match="No open incident exists for scope"):
        visibility_service.resolve_scope_incident(
            session=db_session,
            scope_key=rollback_scope_key,
            requested_by="pytest-rollback",
            actor_role=AppRoleName.ADMIN,
            reason="No open incident remains.",
            rollback_visibility=True,
        )

    with pytest.raises(
        ReviewAccessError, match=r"Active release scope 'missing-scope' was not found\."
    ):
        visibility_service.resolve_scope_incident(
            session=db_session,
            scope_key="missing-scope",
            requested_by="pytest-missing",
            actor_role=AppRoleName.ADMIN,
            reason="Missing scope.",
            rollback_visibility=True,
        )

    with pytest.raises(
        ReviewAccessError, match=r"Active release scope 'missing-scope' was not found\."
    ):
        visibility_service.open_scope_incident(
            session=db_session,
            scope_key="missing-scope",
            requested_by="pytest-missing",
            actor_role=AppRoleName.ADMIN,
            reason="Missing scope for open.",
        )


def test_override_helpers_cover_lookup_and_serialization_edges(db_session):
    with pytest.raises(ReviewAccessError, match="Assessment '"):
        overrides_service.apply_assessment_override(
            session=db_session,
            assessment_id=uuid4(),
            request=AssessmentOverrideRequest(
                override_type=AssessmentOverrideType.ACQUISITION_BASIS,
                reason="Missing assessment should fail.",
                acquisition_basis_gbp=125000.0,
                acquisition_basis_type=PriceBasisType.GUIDE_PRICE,
                requested_by="pytest",
                actor_role=AppRoleName.ANALYST,
            ),
        )

    with pytest.raises(
        ReviewAccessError,
        match=r"Acquisition-basis override requires acquisition_basis_gbp\.",
    ):
        overrides_service._build_override_payload(
            session=SimpleNamespace(get=lambda *args, **kwargs: None),
            run=SimpleNamespace(valuation_runs=[], result=SimpleNamespace()),
            request=AssessmentOverrideRequest(
                override_type=AssessmentOverrideType.ACQUISITION_BASIS,
                reason="Missing basis.",
                acquisition_basis_gbp=None,
                acquisition_basis_type=PriceBasisType.GUIDE_PRICE,
                requested_by="pytest",
                actor_role=AppRoleName.ANALYST,
            ),
            actor_name="pytest",
        )

    missing_assumption_id = uuid4()
    with pytest.raises(
        ReviewAccessError,
        match=f"Valuation assumption set '{missing_assumption_id}' was not found.",
    ):
        overrides_service._build_override_payload(
            session=SimpleNamespace(get=lambda *args, **kwargs: None),
            run=SimpleNamespace(valuation_runs=[], result=SimpleNamespace()),
            request=AssessmentOverrideRequest(
                override_type=AssessmentOverrideType.VALUATION_ASSUMPTION_SET,
                reason="Missing assumption set.",
                valuation_assumption_set_id=missing_assumption_id,
                requested_by="pytest",
                actor_role=AppRoleName.REVIEWER,
            ),
            actor_name="pytest",
        )

    valuation_run_id = uuid4()
    matching_run = SimpleNamespace(id=valuation_run_id)
    fallback_run = SimpleNamespace(id=uuid4())
    assumption_override = SimpleNamespace(override_json={"valuation_run_id": str(valuation_run_id)})
    fallback_override = SimpleNamespace(override_json={"valuation_run_id": str(fallback_run.id)})
    resolved_match = overrides_service._resolve_effective_valuation_run(
        session=SimpleNamespace(
            get=lambda model, ident: fallback_run if ident == fallback_run.id else None,
        ),
        assessment_run=SimpleNamespace(valuation_runs=[matching_run]),
        assumption_override=assumption_override,
    )
    assert resolved_match.id == valuation_run_id

    resolved_fallback = overrides_service._resolve_effective_valuation_run(
        session=SimpleNamespace(
            get=lambda model, ident: fallback_run if ident == fallback_run.id else None,
        ),
        assessment_run=SimpleNamespace(valuation_runs=[]),
        assumption_override=fallback_override,
    )
    assert resolved_fallback.id == fallback_run.id

    assert (
        overrides_service._serialize_effective_valuation(
            assessment_run=SimpleNamespace(result=None),
            valuation_run=None,
            basis_override=None,
        )
        is None
    )


def test_admin_route_wrappers_cover_success_and_not_found_paths(monkeypatch):
    class _FakeSession:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    fake_session = _FakeSession()
    admin_actor = SimpleNamespace(role=AppRoleName.ADMIN)
    reviewer_actor = SimpleNamespace(role=AppRoleName.REVIEWER)
    fake_source_snapshot = {"id": uuid4(), "source_name": "snapshot-1"}
    fake_case = {"id": uuid4(), "review_status": GoldSetReviewStatus.PENDING.value}
    fake_model_release_list = [{"id": uuid4(), "template_key": "resi_5_9_full"}]

    monkeypatch.setattr(
        admin_routes,
        "list_jobs",
        lambda *, session, limit: [_job_payload(job_id=uuid4()) if limit == 2 else _job_payload()],
    )
    jobs = admin_routes.get_jobs(limit=2, session=fake_session, _actor=admin_actor)
    assert len(jobs) == 1
    assert isinstance(jobs[0], JobRunRead)
    assert jobs[0].job_type == JobType.GOLD_SET_REFRESH
    assert jobs[0].status == JobStatus.QUEUED

    monkeypatch.setattr(
        admin_routes,
        "list_source_snapshots",
        lambda *, session, limit: [fake_source_snapshot] if limit == 3 else [],
    )
    source_snapshots = admin_routes.get_source_snapshots(
        limit=3,
        session=fake_session,
        _actor=admin_actor,
    )
    assert source_snapshots == [fake_source_snapshot]

    monkeypatch.setattr(
        admin_routes, "get_source_snapshot", lambda *, session, snapshot_id: fake_source_snapshot
    )
    source_snapshot_id = uuid4()
    assert (
        admin_routes.get_source_snapshot_detail(
            snapshot_id=source_snapshot_id,
            session=fake_session,
            _actor=admin_actor,
        )
        == fake_source_snapshot
    )
    monkeypatch.setattr(admin_routes, "get_source_snapshot", lambda *, session, snapshot_id: None)
    with pytest.raises(HTTPException) as exc_info:
        admin_routes.get_source_snapshot_detail(
            snapshot_id=source_snapshot_id,
            session=fake_session,
            _actor=admin_actor,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {
        "message": "Source snapshot not found.",
        "snapshot_id": str(source_snapshot_id),
    }

    monkeypatch.setattr(
        admin_routes,
        "list_model_releases_read",
        lambda *, session, template_key=None: fake_model_release_list,
    )
    assert (
        admin_routes.get_model_releases(
            template_key="resi_5_9_full",
            session=fake_session,
            _actor=admin_actor,
        )
        == fake_model_release_list
    )

    monkeypatch.setattr(admin_routes, "_ensure_historical_labels", lambda *, session: None)
    monkeypatch.setattr(
        admin_routes, "get_gold_set_case_read", lambda *, session, case_id: fake_case
    )
    assert (
        admin_routes.get_gold_set_case_detail(
            case_id=uuid4(),
            session=fake_session,
            _actor=reviewer_actor,
        )
        == fake_case
    )
    monkeypatch.setattr(admin_routes, "get_gold_set_case_read", lambda *, session, case_id: None)
    with pytest.raises(HTTPException) as exc_info:
        admin_routes.get_gold_set_case_detail(
            case_id=uuid4(),
            session=fake_session,
            _actor=reviewer_actor,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["message"] == "Gold-set case not found."

    monkeypatch.setattr(admin_routes, "get_historical_label_case", lambda *, session, case_id: None)
    with pytest.raises(HTTPException) as exc_info:
        admin_routes.review_gold_set_case(
            case_id=uuid4(),
            request=IncidentActionRequest(
                action="open",
                reason="Missing case should fail.",
                requested_by="pytest-review",
                actor_role=AppRoleName.REVIEWER,
            ),
            session=fake_session,
            actor=reviewer_actor,
        )
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["message"] == "Gold-set case not found."

    captured_refresh = {}
    monkeypatch.setattr(
        admin_routes,
        "resolve_request_actor_name",
        lambda actor, fallback: fallback,
    )
    monkeypatch.setattr(
        admin_routes,
        "enqueue_gold_set_refresh_job",
        lambda *, session, requested_by: (
            (captured_refresh.setdefault("requested_by", requested_by) and False) or _job_payload()
        ),
    )
    refreshed_job = admin_routes.refresh_gold_set(session=fake_session, actor=reviewer_actor)
    assert fake_session.commits == 1
    assert captured_refresh["requested_by"] == "api-admin"
    assert isinstance(refreshed_job, JobRunRead)
    assert refreshed_job.job_type == JobType.GOLD_SET_REFRESH

    captured_activation = {}

    def _capture_activation(*, session, release_id, requested_by):
        captured_activation["requested_by"] = requested_by

    monkeypatch.setattr(admin_routes, "activate_model_release", _capture_activation)
    monkeypatch.setattr(admin_routes, "get_model_release_read", lambda *, session, release_id: None)
    commits_before = fake_session.commits
    with pytest.raises(HTTPException) as exc_info:
        admin_routes.activate_hidden_release(
            release_id=uuid4(),
            request=ModelReleaseActivateRequest(requested_by=None, actor_role=AppRoleName.ADMIN),
            session=fake_session,
            actor=admin_actor,
        )
    assert exc_info.value.status_code == 404
    assert captured_activation["requested_by"] == "api-admin"
    assert fake_session.commits == commits_before + 1

    captured_retire = {}

    def _capture_retire(*, session, release_id, requested_by):
        captured_retire["requested_by"] = requested_by

    monkeypatch.setattr(admin_routes, "retire_model_release", _capture_retire)
    monkeypatch.setattr(admin_routes, "get_model_release_read", lambda *, session, release_id: None)
    commits_before = fake_session.commits
    with pytest.raises(HTTPException) as exc_info:
        admin_routes.retire_hidden_release(
            release_id=uuid4(),
            request=ModelReleaseRetireRequest(requested_by=None, actor_role=AppRoleName.ADMIN),
            session=fake_session,
            actor=admin_actor,
        )
    assert exc_info.value.status_code == 404
    assert captured_retire["requested_by"] == "api-admin"
    assert fake_session.commits == commits_before + 1

    captured_visibility = {}

    def _capture_visibility(
        *,
        session,
        scope_key,
        visibility_mode,
        requested_by,
        actor_role,
        reason,
    ):
        captured_visibility.update(
            {
                "scope_key": scope_key,
                "visibility_mode": visibility_mode,
                "requested_by": requested_by,
                "actor_role": actor_role,
                "reason": reason,
            }
        )

    monkeypatch.setattr(admin_routes, "set_scope_visibility", _capture_visibility)
    monkeypatch.setattr(
        admin_routes,
        "list_model_releases_read",
        lambda *, session, template_key=None: fake_model_release_list,
    )
    commits_before = fake_session.commits
    visibility_list = admin_routes.update_release_scope_visibility(
        scope_key="scope-visible",
        request=ReleaseScopeVisibilityRequest(
            requested_by=None,
            actor_role=AppRoleName.ADMIN,
            visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
            reason="Make visible for reviewer-only rollout.",
        ),
        session=fake_session,
        actor=admin_actor,
    )
    assert fake_session.commits == commits_before + 1
    assert captured_visibility["scope_key"] == "scope-visible"
    assert captured_visibility["requested_by"] == "api-admin"
    assert captured_visibility["actor_role"] == AppRoleName.ADMIN
    assert captured_visibility["visibility_mode"] == VisibilityMode.VISIBLE_REVIEWER_ONLY
    assert visibility_list == fake_model_release_list
