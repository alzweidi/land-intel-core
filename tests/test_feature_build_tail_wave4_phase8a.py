from collections import deque
from datetime import date
from types import SimpleNamespace

import pytest
from landintel.domain.enums import (
    GeomConfidence,
    GeomSourceType,
    HistoricalLabelClass,
    PriceBasisType,
    ProposalForm,
    ScenarioSource,
)
from landintel.features import build as features_build
from shapely.geometry import Point


class _Result:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _QueuedSession:
    def __init__(self, results):
        self._results = deque(results)

    def execute(self, _stmt):
        if self._results:
            return self._results.popleft()
        return _Result([])


class _RepeatSession:
    def __init__(self, items):
        self._items = list(items)

    def execute(self, _stmt):
        return _Result(self._items)


def _feature_case(
    *,
    application_id: str,
    label_class: HistoricalLabelClass,
    template_key: str,
    source_snapshot_id: str,
    first_substantive_decision_date: date,
    units_proposed: int | None,
    decision_date: str | None,
    raw_record_json,
    geometry,
    route_normalized: str = "FULL",
):
    record = SimpleNamespace(
        id=application_id,
        planning_application_id=application_id,
        source_snapshot_id=source_snapshot_id,
        borough_id=None,
        source_snapshot_ids_json=[source_snapshot_id],
        raw_asset_ids_json=[f"asset-{application_id}"],
        label_class=label_class,
        first_substantive_decision_date=first_substantive_decision_date,
        template_key=template_key,
        label_version="v1",
        route_normalized=route_normalized,
        units_proposed=units_proposed,
        raw_record_json=raw_record_json,
        decision="APPROVED" if label_class == HistoricalLabelClass.POSITIVE else "REFUSED",
        decision_date=date.fromisoformat(decision_date) if decision_date else None,
        valid_date=date(2025, 1, 1),
        documents=[SimpleNamespace(asset_id=f"asset-{application_id}")],
        planning_application=None,
        source_family="planning",
        coverage_status="complete",
        freshness_status="current",
        gap_reason=None,
        geometry=geometry,
    )
    record.planning_application = record
    return record


def _historical_case(
    *,
    application_id: str,
    site_geom_27700,
    site_point_27700,
    valid_date,
    decision_date,
):
    application = SimpleNamespace(
        id=application_id,
        site_geom_27700=site_geom_27700,
        site_point_27700=site_point_27700,
        valid_date=valid_date,
        decision_date=decision_date,
        route_normalized="FULL",
    )
    return SimpleNamespace(
        id=f"historical-{application_id}",
        planning_application=application,
        template_key="resi_5_9_full",
        borough_id="borough-1",
        site_area_sqm=60.0,
        valid_date=valid_date,
        units_proposed=6,
        proposal_form=ProposalForm.REDEVELOPMENT,
    )


def test_build_designation_profile_skips_inactive_policy_and_constraint_facts(monkeypatch):
    policy_row = SimpleNamespace(
        legal_effective_from=date(2030, 1, 1),
        legal_effective_to=date(2031, 1, 1),
        policy_area_snapshot_json={
            "legal_effective_from": "2030-01-01",
            "legal_effective_to": "2031-01-01",
            "policy_family": "SITE_ALLOCATION",
            "source_snapshot_id": "policy-snap",
        },
        policy_area=SimpleNamespace(
            policy_family="SITE_ALLOCATION",
            source_snapshot_id="policy-snap",
        ),
        source_snapshot_id="policy-snap",
    )
    constraint_row = SimpleNamespace(
        effective_from=date(2030, 1, 1),
        effective_to=date(2031, 1, 1),
        constraint_snapshot_json={
            "effective_from": "2030-01-01",
            "effective_to": "2031-01-01",
            "feature_family": "heritage",
            "feature_subtype": "conservation_area",
            "source_snapshot_id": "constraint-snap",
        },
        constraint_feature=SimpleNamespace(
            feature_family="heritage",
            feature_subtype="conservation_area",
            source_snapshot_id="constraint-snap",
        ),
        source_snapshot_id="constraint-snap",
    )

    monkeypatch.setattr(
        features_build,
        "_apply_brownfield_designations",
        lambda **kwargs: (kwargs["profile"], kwargs["source_snapshot_ids"]),
    )

    profile, source_ids = features_build.build_designation_profile_for_geometry(
        session=_QueuedSession(
            [
                _Result([policy_row]),
                _Result([constraint_row]),
            ]
        ),
        geometry=SimpleNamespace(),
        area_sqm=120.0,
        as_of_date=date(2026, 4, 18),
    )

    assert profile["policy_families"] == []
    assert profile["constraint_families"] == []
    assert profile["has_site_allocation"] is False
    assert profile["has_conservation_area"] is False
    assert profile["has_article4"] is False
    assert profile["has_flood_zone"] is False
    assert profile["has_listed_building_nearby"] is False
    assert source_ids == set()


def test_build_feature_snapshot_covers_on_site_history_and_nearby_missing_geometry(monkeypatch):
    template_key = "resi_5_9_full"
    positive_on_site = _feature_case(
        application_id="app-positive",
        label_class=HistoricalLabelClass.POSITIVE,
        template_key=template_key,
        source_snapshot_id="snap-positive",
        first_substantive_decision_date=date(2026, 4, 1),
        units_proposed=4,
        decision_date="2026-04-01",
        raw_record_json={"active_extant": True},
        geometry=Point(1, 1),
    )
    negative_on_site = _feature_case(
        application_id="app-negative",
        label_class=HistoricalLabelClass.NEGATIVE,
        template_key=template_key,
        source_snapshot_id="snap-negative",
        first_substantive_decision_date=date(2026, 4, 2),
        units_proposed=6,
        decision_date="2026-04-02",
        raw_record_json={"active_extant": False},
        geometry=Point(2, 2),
    )
    nearby_missing_geometry = _feature_case(
        application_id="app-nearby-missing",
        label_class=HistoricalLabelClass.NEGATIVE,
        template_key=template_key,
        source_snapshot_id="snap-nearby-missing",
        first_substantive_decision_date=date(2026, 4, 3),
        units_proposed=2,
        decision_date="2026-04-03",
        raw_record_json={"active_extant": False},
        geometry=None,
    )
    nearby_positive = _feature_case(
        application_id="app-nearby-positive",
        label_class=HistoricalLabelClass.POSITIVE,
        template_key=template_key,
        source_snapshot_id="snap-nearby-positive",
        first_substantive_decision_date=date(2026, 4, 4),
        units_proposed=8,
        decision_date="2026-04-04",
        raw_record_json={"active_extant": False},
        geometry=Point(120, 0),
    )
    nearby_negative = _feature_case(
        application_id="app-nearby-negative",
        label_class=HistoricalLabelClass.NEGATIVE,
        template_key=template_key,
        source_snapshot_id="snap-nearby-negative",
        first_substantive_decision_date=date(2026, 4, 5),
        units_proposed=3,
        decision_date="2026-04-05",
        raw_record_json={"active_extant": False},
        geometry=Point(30, 0),
    )

    records = [
        positive_on_site,
        negative_on_site,
        nearby_missing_geometry,
        nearby_positive,
        nearby_negative,
    ]
    session = _RepeatSession(records)

    monkeypatch.setattr(
        features_build,
        "build_designation_profile_for_site_context",
        lambda **kwargs: (
            {
                "policy_families": [],
                "constraint_families": [],
                "has_site_allocation": False,
                "has_density_guidance": False,
                "has_conservation_area": False,
                "has_article4": False,
                "has_flood_zone": False,
                "has_listed_building_nearby": False,
                "brownfield_part1": False,
                "brownfield_part2_active": False,
                "pip_active": False,
                "tdc_active": False,
            },
            {"designation-snapshot"},
        ),
    )
    monkeypatch.setattr(
        features_build,
        "planning_application_snapshot",
        lambda link: {
            "source_snapshot_id": link.source_snapshot_id,
            "route_normalized": link.planning_application.route_normalized,
            "units_proposed": link.planning_application.units_proposed,
            "raw_record_json": None,
            "decision": link.planning_application.decision,
            "decision_date": link.planning_application.decision_date.isoformat(),
            "valid_date": link.planning_application.valid_date.isoformat(),
            "documents": [
                {"asset_id": document.asset_id} for document in link.planning_application.documents
            ],
        },
    )
    monkeypatch.setattr(
        features_build,
        "planning_application_geometry",
        lambda application: {
            "app-positive": Point(1, 1),
            "app-negative": Point(2, 2),
            "app-nearby-missing": None,
            "app-nearby-positive": Point(120, 0),
            "app-nearby-negative": Point(30, 0),
        }[application.id],
    )

    site = SimpleNamespace(
        id="site-1",
        geom_27700="POLYGON((0 0, 0 20, 20 20, 20 0, 0 0))",
        site_area_sqm=400.0,
        geom_source_type=GeomSourceType.SOURCE_POLYGON,
        geom_confidence=GeomConfidence.MEDIUM,
        borough_id=None,
        current_price_gbp=None,
        current_price_basis_type=PriceBasisType.UNKNOWN,
        planning_links=[
            SimpleNamespace(
                planning_application=positive_on_site,
                planning_application_id=positive_on_site.id,
                source_snapshot_id=positive_on_site.source_snapshot_id,
            ),
            SimpleNamespace(
                planning_application=negative_on_site,
                planning_application_id=negative_on_site.id,
                source_snapshot_id=negative_on_site.source_snapshot_id,
            ),
        ],
        manual_review_required=False,
    )
    scenario = SimpleNamespace(
        id="scenario-1",
        template_key=template_key,
        units_assumed=5,
        housing_mix_assumed_json={},
        proposal_form=ProposalForm.REDEVELOPMENT,
        scenario_source=ScenarioSource.AUTO,
        route_assumed="FULL",
        net_developable_area_pct=0.7,
        access_assumption=None,
    )

    result = features_build.build_feature_snapshot(
        session=session,
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 18),
    )

    values = result.feature_json["values"]
    assert values["onsite_positive_count"] == 1
    assert values["onsite_negative_count"] == 1
    assert values["active_extant_permission_count"] == 1
    assert values["onsite_max_units_approved"] == 4
    assert values["onsite_max_units_refused"] == 6
    assert values["same_template_positive_500m"] == 1
    assert values["adjacent_refused_0_50m"] == 1


@pytest.mark.parametrize(
    ("historical_label", "geometry_patch", "expected_message"),
    [
        (
            _historical_case(
                application_id="hist-missing-geom",
                site_geom_27700=None,
                site_point_27700=None,
                valid_date=date(2026, 4, 1),
                decision_date=date(2026, 4, 1),
            ),
            None,
            "does not have a site geometry or point",
        ),
        (
            _historical_case(
                application_id="hist-no-geometry",
                site_geom_27700="POLYGON((0 0, 0 4, 4 4, 4 0, 0 0))",
                site_point_27700=None,
                valid_date=date(2026, 4, 1),
                decision_date=date(2026, 4, 1),
            ),
            lambda _application: None,
            "does not have a usable planning geometry",
        ),
        (
            _historical_case(
                application_id="hist-no-date",
                site_geom_27700="POLYGON((0 0, 0 4, 4 4, 4 0, 0 0))",
                site_point_27700=None,
                valid_date=None,
                decision_date=None,
            ),
            lambda _application: Point(0, 0),
            "does not have a stable as_of_date",
        ),
    ],
)
def test_build_historical_feature_snapshot_raises_for_missing_geometry_and_date(
    monkeypatch,
    historical_label,
    geometry_patch,
    expected_message,
):
    if geometry_patch is not None:
        monkeypatch.setattr(features_build, "planning_application_geometry", geometry_patch)

    with pytest.raises(ValueError, match=expected_message):
        features_build.build_historical_feature_snapshot(
            session=SimpleNamespace(),
            historical_label=historical_label,
        )


def test_snapshot_asset_and_coverage_helpers_cover_edge_branches():
    assert features_build._planning_application_snapshot_raw_asset_ids(
        {
            "documents": [
                {"asset_id": "asset-1"},
                {"asset_id": ""},
                {"asset_id": None},
                "not-a-dict",
                {"asset_id": 7},
            ]
        }
    ) == {"asset-1", "7"}

    session = SimpleNamespace(
        execute=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("execute should not be called for a missing borough")
        )
    )
    assert features_build._latest_coverage_rows(session=session, borough_id=None) == []

    assert (
        features_build._decision_on_or_before(
            application=SimpleNamespace(decision_date=date(2026, 4, 18)),
            as_of_date=date(2026, 4, 18),
        )
        is True
    )
    assert (
        features_build._decision_on_or_before(
            application=SimpleNamespace(decision_date=date(2026, 4, 19)),
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
    assert (
        features_build._decision_on_or_before(
            application=SimpleNamespace(decision_date=None),
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
