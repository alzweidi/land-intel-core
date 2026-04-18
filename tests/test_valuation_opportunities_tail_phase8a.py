from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from landintel.domain.enums import (
    AppRoleName,
    OpportunityBand,
    PriceBasisType,
    ValuationQuality,
    ValuationRunState,
    VisibilityMode,
)
from landintel.domain.schemas import (
    AssessmentOverrideSummaryRead,
    OpportunityListResponse,
    OpportunitySummaryRead,
    SiteScenarioSummaryRead,
    SiteSummaryRead,
    ValuationResultRead,
    VisibilityGateRead,
)
from landintel.services import opportunities_readback
from landintel.valuation import service as valuation_service


class _NoopSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flush_count += 1


def _make_assessment_run(
    *,
    result: object,
    feature_snapshot: object,
    scenario: object | None = None,
    site: object | None = None,
    valuation_runs: list[object] | None = None,
    prediction_ledger: object | None = None,
    as_of_date: date = date(2026, 4, 18),
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        result=result,
        feature_snapshot=feature_snapshot,
        scenario=scenario
        or SimpleNamespace(
            id=uuid4(),
            red_line_geom_hash="scenario-geom-hash",
            template_key="resi_5_9_full",
            proposal_form="REDEVELOPMENT",
            units_assumed=6,
            manual_review_required=False,
            stale_reason=None,
            housing_mix_assumed_json={},
        ),
        site=site
        or SimpleNamespace(
            borough_id="camden",
            current_price_gbp=125000,
            current_price_basis_type=PriceBasisType.GUIDE_PRICE,
        ),
        valuation_runs=valuation_runs or [],
        prediction_ledger=prediction_ledger,
        as_of_date=as_of_date,
    )


def _make_opportunity_summary(
    *,
    site_id: UUID,
    band: OpportunityBand,
    valuation_quality: ValuationQuality,
    manual_review_required: bool,
    asking_price_gbp: int | None,
    auction_date: date | None,
    visible_allowed: bool = True,
    hidden_allowed: bool = False,
    hold_reason: str | None = None,
    ranking_reason: str = "fixture ranking reason",
    expected_uplift_mid: float | None = 33.0,
    same_borough_support_count: int = 1,
) -> OpportunitySummaryRead:
    visibility = VisibilityGateRead.model_construct(
        scope_key="scope-1",
        visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        exposure_mode=(
            "HIDDEN_INTERNAL"
            if hidden_allowed
            else ("VISIBLE_REVIEWER_ONLY" if visible_allowed else "REDACTED")
        ),
        viewer_role=AppRoleName.REVIEWER,
        visible_probability_allowed=visible_allowed,
        hidden_probability_allowed=hidden_allowed,
        blocked=False,
        blocked_reason_codes=[],
        blocked_reason_text=None,
        active_incident_id=None,
        active_incident_reason=None,
        replay_verified=True,
        payload_hash_matches=True,
        artifact_hashes_match=True,
        scope_release_matches_result=True,
    )
    return OpportunitySummaryRead.model_construct(
        site_id=site_id,
        display_name=f"Site {site_id}",
        borough_id="camden",
        borough_name="Camden",
        assessment_id=uuid4(),
        scenario_id=uuid4(),
        probability_band=band,
        hold_reason=hold_reason,
        ranking_reason=ranking_reason,
        hidden_mode_only=not visible_allowed,
        visibility=visibility,
        display_block_reason=None,
        eligibility_status="PASS",
        estimate_status="NONE",
        manual_review_required=manual_review_required,
        valuation_quality=valuation_quality,
        asking_price_gbp=asking_price_gbp,
        asking_price_basis_type=PriceBasisType.GUIDE_PRICE,
        auction_date=auction_date,
        post_permission_value_mid=125000.0,
        uplift_mid=25000.0,
        expected_uplift_mid=expected_uplift_mid,
        same_borough_support_count=same_borough_support_count,
        site_summary=None,
        scenario_summary=None,
    )


def test_valuation_build_paths_cover_ready_return_and_failure_state(monkeypatch) -> None:
    assessment_run = _make_assessment_run(
        result=SimpleNamespace(approval_probability_raw=0.4),
        feature_snapshot=SimpleNamespace(feature_json={"values": {"current_price_gbp": 120000}}),
    )
    assumption_set = SimpleNamespace(
        id=uuid4(),
        version="fixture-v1",
        cost_json={},
        policy_burden_json={},
        discount_json={},
    )
    ready_run = SimpleNamespace(
        state=ValuationRunState.READY,
        result=SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(
        valuation_service,
        "resolve_active_assumption_set",
        lambda _session, **_kwargs: assumption_set,
    )
    monkeypatch.setattr(valuation_service, "_valuation_input_hash", lambda **_kwargs: "hash-1")
    monkeypatch.setattr(
        valuation_service,
        "_get_or_create_run",
        lambda **_kwargs: ready_run,
    )

    returned = valuation_service._build_or_refresh_valuation_for_assessment(
        session=_NoopSession(),
        assessment_run=assessment_run,
        requested_by="pytest",
        assumption_set=None,
    )
    assert returned is ready_run

    failure_run = SimpleNamespace(
        state=ValuationRunState.PENDING,
        result=None,
    )
    failing_session = _NoopSession()
    monkeypatch.setattr(
        valuation_service,
        "_get_or_create_run",
        lambda **_kwargs: failure_run,
    )
    monkeypatch.setattr(
        valuation_service,
        "build_sales_comp_summary",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("fixture sales comp failure")),
    )

    with pytest.raises(ValueError, match="fixture sales comp failure"):
        valuation_service._build_or_refresh_valuation_for_assessment(
            session=failing_session,
            assessment_run=assessment_run,
            requested_by="pytest",
            assumption_set=assumption_set,
        )

    assert failure_run.state == ValuationRunState.FAILED
    assert failure_run.error_text == "fixture sales comp failure"
    assert failure_run.finished_at is not None


def test_valuation_helpers_cover_empty_latest_and_fallback_inputs() -> None:
    empty_latest = valuation_service.latest_valuation_run(SimpleNamespace(valuation_runs=[]))
    assert empty_latest is None

    older = SimpleNamespace(id=UUID(int=1), created_at=datetime(2026, 4, 1, tzinfo=UTC))
    newer = SimpleNamespace(id=UUID(int=2), created_at=datetime(2026, 4, 2, tzinfo=UTC))
    latest = valuation_service.latest_valuation_run(SimpleNamespace(valuation_runs=[older, newer]))
    assert latest is newer

    existing = SimpleNamespace(id=uuid4())
    existing_run = valuation_service._get_or_create_run(
        session=_NoopSession(),
        assessment_run=SimpleNamespace(
            id=uuid4(),
            valuation_runs=[
                SimpleNamespace(
                    valuation_assumption_set_id=UUID(int=3),
                    id=existing.id,
                )
            ],
        ),
        assumption_set=SimpleNamespace(id=UUID(int=3)),
        input_hash="hash-2",
    )
    assert existing_run is not None
    assert existing_run.id == existing.id

    basis_inputs = valuation_service._frozen_basis_inputs(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(
                feature_json={
                    "values": {
                        "current_price_gbp": "120000",
                        "current_price_basis_type": "NOT_A_REAL_TYPE",
                    }
                }
            )
        )
    )
    assert basis_inputs == (None, PriceBasisType.UNKNOWN)

    context = valuation_service._frozen_assessment_context(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(feature_json={"values": "not-a-dict"}),
            site=SimpleNamespace(borough_id="camden"),
            scenario=SimpleNamespace(
                template_key="resi_5_9_full",
                proposal_form="REDEVELOPMENT",
                manual_review_required=True,
                stale_reason="stale",
            ),
        )
    )
    assert context["borough_id"] == "camden"
    assert context["scenario_template_key"] == "resi_5_9_full"

    frozen_scenario = valuation_service._frozen_scenario_for_valuation(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(feature_json={"values": "not-a-dict"}),
            scenario=SimpleNamespace(
                template_key="resi_5_9_full",
                units_assumed=6,
                housing_mix_assumed_json={"studio": 1.0},
            ),
        )
    )
    assert frozen_scenario.template_key == "resi_5_9_full"
    assert frozen_scenario.units_assumed == 6
    assert frozen_scenario.housing_mix_assumed_json == {"studio": 1.0}


def test_opportunity_list_filters_and_detail_ranking_branches(monkeypatch) -> None:
    base_site_ids = [uuid4() for _ in range(8)]
    summaries = [
        _make_opportunity_summary(
            site_id=base_site_ids[0],
            band=OpportunityBand.BAND_A,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=False,
            asking_price_gbp=150000,
            auction_date=date(2026, 4, 22),
        ),
        _make_opportunity_summary(
            site_id=base_site_ids[1],
            band=OpportunityBand.BAND_B,
            valuation_quality=ValuationQuality.LOW,
            manual_review_required=False,
            asking_price_gbp=150000,
            auction_date=date(2026, 4, 22),
        ),
        _make_opportunity_summary(
            site_id=base_site_ids[2],
            band=OpportunityBand.BAND_B,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=True,
            asking_price_gbp=150000,
            auction_date=date(2026, 4, 22),
        ),
        _make_opportunity_summary(
            site_id=base_site_ids[3],
            band=OpportunityBand.BAND_B,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=False,
            asking_price_gbp=90000,
            auction_date=date(2026, 4, 22),
        ),
        _make_opportunity_summary(
            site_id=base_site_ids[4],
            band=OpportunityBand.BAND_B,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=False,
            asking_price_gbp=250000,
            auction_date=date(2026, 4, 22),
        ),
        _make_opportunity_summary(
            site_id=base_site_ids[5],
            band=OpportunityBand.BAND_B,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=False,
            asking_price_gbp=150000,
            auction_date=None,
        ),
        _make_opportunity_summary(
            site_id=base_site_ids[6],
            band=OpportunityBand.BAND_B,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=False,
            asking_price_gbp=150000,
            auction_date=date(2026, 6, 1),
        ),
        _make_opportunity_summary(
            site_id=base_site_ids[7],
            band=OpportunityBand.BAND_B,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=False,
            asking_price_gbp=150000,
            auction_date=date(2026, 4, 21),
        ),
    ]
    runs = [SimpleNamespace(site_id=site_id, id=uuid4()) for site_id in base_site_ids]
    original_serialize_summary = opportunities_readback._serialize_opportunity_summary
    monkeypatch.setattr(
        opportunities_readback,
        "_latest_runs_by_site",
        lambda _session: runs,
    )

    def _serialize_summary(*, run, **_kwargs):
        index = runs.index(run)
        return summaries[index]

    monkeypatch.setattr(
        opportunities_readback, "_serialize_opportunity_summary", _serialize_summary
    )

    opportunity_list = opportunities_readback.list_opportunities(
        SimpleNamespace(),
        borough="camden",
        probability_band=OpportunityBand.BAND_B,
        valuation_quality=ValuationQuality.MEDIUM,
        manual_review_required=False,
        min_price=100000,
        max_price=200000,
        auction_deadline_days=10,
    )

    assert isinstance(opportunity_list, OpportunityListResponse)
    assert opportunity_list.total == 1
    assert opportunity_list.items[0].site_id == base_site_ids[7]

    ranking_run = SimpleNamespace(
        id=uuid4(),
        site_id=base_site_ids[7],
        site=SimpleNamespace(
            id=base_site_ids[7],
            display_name="Fixture opportunity site",
            borough_id="camden",
            borough=SimpleNamespace(name="Camden"),
            current_price_gbp=150000,
            current_price_basis_type=PriceBasisType.GUIDE_PRICE,
            current_listing=SimpleNamespace(snapshots=[]),
        ),
        scenario=SimpleNamespace(id=uuid4()),
        result=SimpleNamespace(
            result_json={"support_summary": {}},
            manual_review_required=False,
            estimate_status="NONE",
            eligibility_status="PASS",
            approval_probability_raw=0.61,
            estimate_quality=None,
        ),
        valuation_runs=[],
        overrides=[],
    )
    visible_visibility = VisibilityGateRead.model_construct(
        scope_key="scope-1",
        visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        exposure_mode="VISIBLE_REVIEWER_ONLY",
        viewer_role=AppRoleName.REVIEWER,
        visible_probability_allowed=True,
        hidden_probability_allowed=False,
        blocked=False,
        blocked_reason_codes=[],
        blocked_reason_text=None,
        active_incident_id=None,
        active_incident_reason=None,
        replay_verified=True,
        payload_hash_matches=True,
        artifact_hashes_match=True,
        scope_release_matches_result=True,
    )
    monkeypatch.setattr(
        opportunities_readback,
        "evaluate_assessment_visibility",
        lambda *args, **kwargs: visible_visibility,
    )
    monkeypatch.setattr(
        opportunities_readback,
        "serialize_site_summary",
        lambda *_args, **_kwargs: SiteSummaryRead.model_construct(),
    )
    monkeypatch.setattr(
        opportunities_readback,
        "serialize_site_scenario_summary",
        lambda *_args, **_kwargs: SiteScenarioSummaryRead.model_construct(),
    )
    monkeypatch.setattr(
        opportunities_readback,
        "build_override_summary",
        lambda *args, **kwargs: AssessmentOverrideSummaryRead.model_construct(
            active_overrides=[],
            effective_review_status=None,
            effective_manual_review_required=None,
            ranking_suppressed=True,
            display_block_reason="Ranking suppressed by override.",
            effective_valuation=ValuationResultRead.model_construct(
                id=uuid4(),
                valuation_run_id=uuid4(),
                valuation_assumption_set_id=uuid4(),
                valuation_assumption_version="fixture-v1",
                post_permission_value_low=100000.0,
                post_permission_value_mid=125000.0,
                post_permission_value_high=150000.0,
                uplift_low=10000.0,
                uplift_mid=25000.0,
                uplift_high=40000.0,
                expected_uplift_mid=33.0,
                valuation_quality=ValuationQuality.MEDIUM,
                manual_review_required=False,
                basis_json={},
                sense_check_json={},
                result_json={},
                payload_hash="hash",
                created_at=datetime(2026, 4, 18, tzinfo=UTC),
            ),
        ),
    )
    monkeypatch.setattr(
        opportunities_readback,
        "frozen_valuation_run",
        lambda *args, **kwargs: SimpleNamespace(
            id=uuid4(),
            valuation_assumption_set_id=uuid4(),
            valuation_assumption_set=SimpleNamespace(version="fixture-v1"),
            result=SimpleNamespace(
                id=uuid4(),
                post_permission_value_low=100000.0,
                post_permission_value_mid=125000.0,
                post_permission_value_high=150000.0,
                uplift_low=10000.0,
                uplift_mid=25000.0,
                uplift_high=40000.0,
                expected_uplift_mid=33.0,
                valuation_quality=ValuationQuality.MEDIUM,
                manual_review_required=False,
                basis_json={},
                sense_check_json={},
                result_json={},
                payload_hash="hash",
                created_at=datetime(2026, 4, 18, tzinfo=UTC),
            ),
        ),
    )

    ranking_summary = original_serialize_summary(
        session=SimpleNamespace(),
        run=ranking_run,
        viewer_role=AppRoleName.ANALYST,
        include_hidden=False,
    )

    assert ranking_summary.probability_band == OpportunityBand.HOLD
    assert ranking_summary.hold_reason == "Ranking suppressed by override."
    assert ranking_summary.expected_uplift_mid == 33.0
    assert opportunities_readback._same_borough_support_count(SimpleNamespace(result=None)) == 0
    assert opportunities_readback._current_auction_date(None) is None
    assert (
        opportunities_readback._current_auction_date(
            SimpleNamespace(snapshots=[], current_snapshot_id=None)
        )
        is None
    )
