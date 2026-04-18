from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from landintel.assessments import service as assessment_service
from landintel.domain.enums import EligibilityStatus, GeomConfidence
from landintel.planning import extant_permission as extant_permission_service
from landintel.planning import historical_labels as historical_labels_service
from landintel.sites import service as sites_service


class _Geometry:
    def __init__(
        self,
        *,
        geom_type: str = "Polygon",
        area: float = 100.0,
        intersects: bool = True,
        overlap_area: float = 40.0,
        distance_m: float = 50.0,
    ):
        self.geom_type = geom_type
        self.area = area
        self._intersects = intersects
        self._overlap_area = overlap_area
        self._distance_m = distance_m

    def intersects(self, _other) -> bool:
        return self._intersects

    def intersection(self, _other):
        return SimpleNamespace(area=self._overlap_area)

    def distance(self, _other) -> float:
        return self._distance_m


def _application(*, geometry, description: str = "Housing redevelopment"):
    return SimpleNamespace(
        borough_id="camden",
        units_proposed=6,
        route_normalized="FULL",
        application_type="FULL",
        valid_date=date(2024, 1, 1),
        proposal_description=description,
        _geometry=geometry,
    )


def test_same_case_helper_covers_non_intersect_distance_and_description_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        historical_labels_service,
        "planning_application_geometry",
        lambda application: application._geometry,
    )

    stronger = _application(geometry=_Geometry())
    non_intersecting = _application(geometry=_Geometry(intersects=False))
    assert historical_labels_service._same_case(non_intersecting, stronger) is False

    distance_match = _application(geometry=_Geometry(overlap_area=10.0, distance_m=20.0))
    assert historical_labels_service._same_case(distance_match, stronger) is True

    no_geometry = _application(geometry=None, description="Redevelopment housing")
    stronger_no_geometry = _application(geometry=None, description="Housing redevelopment")
    assert historical_labels_service._same_case(no_geometry, stronger_no_geometry) is True


def test_extant_permission_brownfield_nonmaterial_and_no_match_paths(monkeypatch) -> None:
    site = SimpleNamespace(
        borough_id="camden",
        geom_27700="POLYGON((0 0, 20 0, 20 20, 0 20, 0 0))",
        site_area_sqm=400.0,
        planning_links=[],
    )
    monkeypatch.setattr(
        extant_permission_service,
        "list_latest_coverage_snapshots",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        extant_permission_service,
        "load_wkt_geometry",
        lambda _wkt: _Geometry(),
    )

    active_state = SimpleNamespace(
        part="PART_2",
        pip_status="ACTIVE",
        tdc_status=None,
        effective_to=None,
        id=uuid4(),
        external_ref="BF-1",
        source_url="https://example.test/bf-1",
        source_snapshot_id=uuid4(),
        geom_27700="POLYGON",
    )
    monkeypatch.setattr(
        extant_permission_service,
        "list_brownfield_states_for_site",
        lambda **_kwargs: [
            SimpleNamespace(
                part="PART_2",
                pip_status="ACTIVE",
                tdc_status=None,
                effective_to=None,
                id=uuid4(),
                external_ref="skip",
                source_url=None,
                source_snapshot_id=None,
                geom_27700="POLYGON",
            ),
            active_state,
        ],
    )

    calls = {"count": 0}

    def _match_generic_geometry(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return SimpleNamespace(overlap_pct=0.05, overlap_sqm=40.0, distance_m=0.0)

    monkeypatch.setattr(
        extant_permission_service,
        "match_generic_geometry",
        _match_generic_geometry,
    )

    nonmaterial = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert nonmaterial.status.value == "NON_MATERIAL_OVERLAP_MANUAL_REVIEW"
    assert nonmaterial.eligibility_status == EligibilityStatus.ABSTAIN

    monkeypatch.setattr(
        extant_permission_service,
        "list_brownfield_states_for_site",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        extant_permission_service,
        "MANDATORY_EXTANT_SOURCE_FAMILIES",
        (),
    )
    clean = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert clean.status.value == "NO_ACTIVE_PERMISSION_FOUND"
    assert clean.reasons == []


def test_site_and_assessment_helpers_cover_remaining_simple_fallbacks() -> None:
    assert sites_service._raw_asset_id_from_listing(None) is None
    assert (
        sites_service._raw_asset_id_from_listing(
            SimpleNamespace(map_asset_id=None, brochure_asset_id="brochure-1")
        )
        == "brochure-1"
    )
    assert (
        sites_service._display_name_from_listing(
            SimpleNamespace(
                address_text=None,
                headline=None,
            ),
            SimpleNamespace(canonical_url="https://example.test/fallback"),
        )
        == "https://example.test/fallback"
    )

    assessment_service._record_replay_verification(
        assessment_run=SimpleNamespace(prediction_ledger=None),
        check={"replay_passed": True},
    )

    prepared = sites_service._prepared_from_site(
        SimpleNamespace(
            geom_27700="POINT(0 0)",
            geom_source_type=sites_service.GeomSourceType.SOURCE_POLYGON,
            geom_confidence=GeomConfidence.HIGH,
            site_area_sqm=0.0,
            geom_hash="hash",
            geom_4326={"type": "Point", "coordinates": [0.0, 0.0]},
            warning_json={},
        )
    )
    assert prepared.geom_confidence == GeomConfidence.HIGH
