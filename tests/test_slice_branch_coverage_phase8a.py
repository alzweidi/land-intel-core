from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideStatus,
    AssessmentOverrideType,
    GeomConfidence,
    GeomSourceType,
    ScenarioStatus,
    SiteStatus,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    VisibilityMode,
)
from landintel.domain.models import HmlrTitlePolygon, RawAsset, ScenarioTemplate, SourceSnapshot
from landintel.geospatial.geometry import (
    GeometryNormalizationError,
    _collapse_collection,
    canonical_geom_hash,
    derive_geom_confidence,
    derive_site_status,
    geometry_area_sqm,
    geometry_to_display_geojson,
    geometry_warning_dicts,
    load_geojson_geometry,
    load_wkt_geometry,
    repair_geometry,
    transform_geometry,
)
from landintel.geospatial.reference_data import import_hmlr_title_polygons, import_lpa_boundaries
from landintel.geospatial.title_linkage import (
    _confidence_from_overlap,
    _score_address_match,
    build_title_union_geometry,
    compute_title_overlaps,
    select_title_candidates,
    title_polygon_geom,
)
from landintel.planning.enrich import (
    coverage_warning_dicts,
    match_generic_geometry,
    match_planning_application,
)
from landintel.planning.planning_register_normalize import import_borough_register_fixture
from landintel.planning.site_context_snapshots import (
    constraint_snapshot,
    planning_application_snapshot,
    policy_area_snapshot,
    snapshot_planning_application,
    snapshot_raw_asset,
)
from landintel.review.audit_export import (
    _entity_refs_for_run,
    _json_bytes,
    _serialize_audit_events,
    _sha256,
)
from landintel.review.overrides import (
    _build_override_payload,
    _serialize_override,
    _text_or_none,
    _validate_override_role,
    build_override_summary,
)
from landintel.review.visibility import (
    ReviewAccessError,
    _redact_visibility_gate_for_role,
    coerce_role,
    get_open_incident_for_scope,
    load_active_scope,
    require_role,
    role_at_least,
    set_scope_visibility,
)
from landintel.scenarios.catalog import (
    ensure_scenario_templates_seeded,
    get_enabled_scenario_templates,
    template_definition_map,
)
from landintel.scenarios.normalize import (
    confirm_or_update_scenario,
    refresh_site_scenarios_after_rulepack_change,
)
from shapely.geometry import GeometryCollection, Point, Polygon, box

from tests.test_planning_phase3a import _build_camden_site


def _geojson_feature_collection(feature: dict[str, object]) -> dict[str, object]:
    return {"type": "FeatureCollection", "features": [feature]}


def _write_geojson(tmp_path: Path, name: str, feature_collection: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(feature_collection), encoding="utf-8")
    return path


def test_geometry_helpers_cover_branch_variants() -> None:
    polygon = box(0, 0, 10, 10)
    reversed_polygon = Polygon([(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)])

    same_epsg = transform_geometry(polygon, from_epsg=27700, to_epsg=27700)
    assert same_epsg is polygon
    assert geometry_to_display_geojson(polygon)["type"] == "Polygon"
    assert canonical_geom_hash(polygon) == canonical_geom_hash(reversed_polygon)
    assert geometry_area_sqm(Point(5, 5)) == 0.0
    assert derive_geom_confidence(
        source_type=GeomSourceType.SOURCE_POLYGON,
        geometry_27700=polygon,
    ) == GeomConfidence.HIGH
    assert derive_geom_confidence(
        source_type=GeomSourceType.APPROXIMATE_BBOX,
        geometry_27700=polygon,
    ) == GeomConfidence.LOW
    assert derive_geom_confidence(
        source_type=GeomSourceType.POINT_ONLY,
        geometry_27700=Point(0, 0),
    ) == GeomConfidence.INSUFFICIENT
    assert derive_site_status(
        geom_confidence=GeomConfidence.INSUFFICIENT,
        manual_review_required=False,
    ) == SiteStatus.INSUFFICIENT_GEOMETRY
    assert derive_site_status(
        geom_confidence=GeomConfidence.LOW,
        manual_review_required=False,
    ) == SiteStatus.MANUAL_REVIEW
    assert derive_site_status(
        geom_confidence=GeomConfidence.HIGH,
        manual_review_required=False,
    ) == SiteStatus.ACTIVE
    assert geometry_warning_dicts([]) == []

    with pytest.raises(GeometryNormalizationError, match="Geometry WKT is empty"):
        load_wkt_geometry("POINT EMPTY")
    with pytest.raises(GeometryNormalizationError, match="Invalid geometry payload"):
        load_geojson_geometry({"type": "NotAGeometry"})

    polygon_collection = GeometryCollection([box(0, 0, 1, 1), box(2, 2, 3, 3)])
    point_collection = GeometryCollection([Point(0, 0), Point(1, 1)])
    assert _collapse_collection(polygon_collection).geom_type in {"MultiPolygon", "Polygon"}
    assert _collapse_collection(point_collection).geom_type in {"MultiPoint", "Point"}

    repaired, warnings = repair_geometry(polygon)
    assert repaired.geom_type in {"Polygon", "MultiPolygon"}
    assert warnings == []


def test_title_linkage_helpers_cover_candidate_overlap_and_confidence(
    seed_reference_data,
    db_session,
) -> None:
    del seed_reference_data
    titles = db_session.query(HmlrTitlePolygon).order_by(HmlrTitlePolygon.title_number.asc()).all()
    title = next(row for row in titles if row.normalized_address)
    title_geom = title_polygon_geom(title)
    inside_point = title_geom.representative_point()

    exact = select_title_candidates(
        title_polygons=[title],
        normalized_addresses=[title.normalized_address],
        point_geometries_27700=[inside_point],
    )
    assert exact and exact[0].score == 1.0
    assert "listing_address_exact_title_address" in exact[0].reasons
    assert "listing_point_intersects_title" in exact[0].reasons

    partial = select_title_candidates(
        title_polygons=[title],
        normalized_addresses=[title.normalized_address.split()[0]],
        point_geometries_27700=[],
    )
    assert partial and partial[0].score == pytest.approx(0.8)
    assert "listing_address_partial_title_address" in partial[0].reasons

    assert select_title_candidates(
        title_polygons=[title],
        normalized_addresses=[],
        point_geometries_27700=[],
    ) == []
    assert build_title_union_geometry([]) is None

    zero_area_overlaps = compute_title_overlaps(
        site_geometry_27700=inside_point,
        title_polygons=[title],
    )
    assert zero_area_overlaps[0].overlap_sqm == 0.0
    assert zero_area_overlaps[0].overlap_pct == 1.0
    assert zero_area_overlaps[0].confidence == GeomConfidence.HIGH

    assert _score_address_match(
        listing_addresses=[title.normalized_address],
        title_address=title.normalized_address,
    ) == (0.95, "listing_address_exact_title_address")
    assert _score_address_match(
        listing_addresses=[title.normalized_address.split()[0]],
        title_address=title.normalized_address,
    ) == (0.8, "listing_address_partial_title_address")
    assert _score_address_match(
        listing_addresses=["unmatched"],
        title_address=title.normalized_address,
    ) == (
        0.0,
        None,
    )
    assert _confidence_from_overlap(0.9) == GeomConfidence.HIGH
    assert _confidence_from_overlap(0.5) == GeomConfidence.MEDIUM
    assert _confidence_from_overlap(0.2) == GeomConfidence.LOW
    assert _confidence_from_overlap(0.0) == GeomConfidence.INSUFFICIENT


def test_reference_data_import_is_idempotent(tmp_path, db_session, storage) -> None:
    lpa_fixture = _write_geojson(
        tmp_path,
        "lpa.geojson",
        _geojson_feature_collection(
            {
                "type": "Feature",
                "id": "camden",
                "properties": {
                    "name": "Camden",
                    "borough_id": "camden",
                    "gss_code": "E09000007",
                    "authority_level": "BOROUGH",
                    "source_epsg": 4326,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-0.1428, 51.5359],
                            [-0.1412, 51.5359],
                            [-0.1412, 51.5365],
                            [-0.1428, 51.5365],
                            [-0.1428, 51.5359],
                        ]
                    ],
                },
            }
        ),
    )
    first = import_lpa_boundaries(session=db_session, storage=storage, fixture_path=lpa_fixture)
    second = import_lpa_boundaries(session=db_session, storage=storage, fixture_path=lpa_fixture)
    assert first.source_snapshot_id == second.source_snapshot_id
    assert first.raw_asset_id == second.raw_asset_id
    assert first.imported_count == second.imported_count == 1
    assert db_session.query(SourceSnapshot).count() == 1
    assert db_session.query(RawAsset).count() == 1

    title_fixture = _write_geojson(
        tmp_path,
        "titles.geojson",
        _geojson_feature_collection(
            {
                "type": "Feature",
                "id": "T12345",
                "properties": {
                    "title_number": "T12345",
                    "address_text": "1 Example Road, Camden",
                    "source_epsg": 4326,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-0.1428, 51.5359],
                            [-0.1412, 51.5359],
                            [-0.1412, 51.5365],
                            [-0.1428, 51.5365],
                            [-0.1428, 51.5359],
                        ]
                    ],
                },
            }
        ),
    )
    title_first = import_hmlr_title_polygons(
        session=db_session,
        storage=storage,
        fixture_path=title_fixture,
    )
    title_second = import_hmlr_title_polygons(
        session=db_session,
        storage=storage,
        fixture_path=title_fixture,
    )
    assert title_first.source_snapshot_id == title_second.source_snapshot_id
    assert title_first.raw_asset_id == title_second.raw_asset_id
    assert title_first.imported_count == title_second.imported_count == 1


def test_site_context_snapshot_helpers_use_stored_and_fallback_values() -> None:
    asset = SimpleNamespace(
        id=uuid.uuid4(),
        storage_path="raw/example.txt",
        asset_type="TEXT",
        original_url="https://example.com/example.txt",
        mime_type="text/plain",
        content_sha256="abc123",
        size_bytes=3,
        fetched_at=datetime(2026, 4, 18, tzinfo=UTC),
    )
    document = SimpleNamespace(
        id=uuid.uuid4(),
        asset_id=asset.id,
        doc_type="BROCHURE",
        doc_url="https://example.com/brochure.pdf",
        asset=asset,
    )
    application = SimpleNamespace(
        id=uuid.uuid4(),
        borough_id="camden",
        source_system="BOROUGH_REGISTER",
        source_snapshot_id=uuid.uuid4(),
        external_ref="CAM/2026/0001",
        application_type="FULL",
        proposal_description="Example proposal",
        valid_date=date(2026, 4, 18),
        decision_date=None,
        decision="APPROVED",
        decision_type="FULL_RESIDENTIAL",
        status="APPROVED",
        route_normalized="FULL",
        units_proposed=7,
        source_priority=100,
        source_url="https://example.com/app",
        site_geom_4326={"type": "Polygon"},
        site_point_4326={"type": "Point"},
        raw_record_json={"importance": "HIGH"},
        documents=[document],
    )
    policy_area = SimpleNamespace(
        id=uuid.uuid4(),
        borough_id="camden",
        policy_family="local_plan",
        policy_code="LP1",
        name="Policy 1",
        geom_4326={"type": "Polygon"},
        legal_effective_from=date(2026, 1, 1),
        legal_effective_to=None,
        source_snapshot_id=uuid.uuid4(),
        source_class=SourceClass.AUTHORITATIVE,
        source_url="https://example.com/policy",
        raw_record_json={"example": True},
    )
    constraint_feature = SimpleNamespace(
        id=uuid.uuid4(),
        feature_family="flood",
        feature_subtype="zone2",
        authority_level="BOROUGH",
        geom_4326={"type": "Polygon"},
        legal_status="ACTIVE",
        effective_from=None,
        effective_to=None,
        source_snapshot_id=uuid.uuid4(),
        source_class=SourceClass.AUTHORITATIVE,
        source_url="https://example.com/constraint",
        raw_record_json={"severity": "LOW"},
    )
    stored_link = SimpleNamespace(
        application_snapshot_json={"cached": True},
        planning_application=application,
    )
    policy_fact = SimpleNamespace(policy_area_snapshot_json={}, policy_area=policy_area)
    stored_policy_fact = SimpleNamespace(
        policy_area_snapshot_json={"cached": True},
        policy_area=policy_area,
    )
    constraint_fact = SimpleNamespace(
        constraint_snapshot_json={},
        constraint_feature=constraint_feature,
    )
    stored_constraint_fact = SimpleNamespace(
        constraint_snapshot_json={"cached": True},
        constraint_feature=constraint_feature,
    )

    assert snapshot_raw_asset(None) is None
    assert snapshot_raw_asset(asset)["storage_path"] == "raw/example.txt"
    assert snapshot_planning_application(application)["external_ref"] == "CAM/2026/0001"
    assert planning_application_snapshot(stored_link) == {"cached": True}
    assert policy_area_snapshot(policy_fact)["policy_code"] == "LP1"
    assert policy_area_snapshot(stored_policy_fact) == {"cached": True}
    assert constraint_snapshot(constraint_fact)["feature_subtype"] == "zone2"
    assert constraint_snapshot(stored_constraint_fact) == {"cached": True}


def test_planning_enrich_helper_branches_cover_geometry_matching_and_warnings() -> None:
    site_geometry = box(0, 0, 10, 10)
    polygon_match = match_generic_geometry(
        site_geometry=site_geometry,
        site_area_sqm=float(site_geometry.area),
        feature_wkt=box(2, 2, 4, 4).wkt,
        near_distance_m=0.0,
    )
    point_match = match_generic_geometry(
        site_geometry=site_geometry,
        site_area_sqm=float(site_geometry.area),
        feature_wkt=Point(5, 5).wkt,
        near_distance_m=0.0,
    )
    near_match = match_generic_geometry(
        site_geometry=site_geometry,
        site_area_sqm=float(site_geometry.area),
        feature_wkt=Point(10.5, 5).wkt,
        near_distance_m=1.0,
    )
    no_match = match_generic_geometry(
        site_geometry=site_geometry,
        site_area_sqm=float(site_geometry.area),
        feature_wkt=Point(15, 15).wkt,
        near_distance_m=1.0,
    )
    assert polygon_match is not None and polygon_match.link_type == "POLYGON_INTERSECTS"
    assert point_match is not None and point_match.link_type == "POINT_WITHIN_SITE"
    assert near_match is not None and near_match.link_type == "POINT_NEAR_SITE"
    assert no_match is None

    application = SimpleNamespace(
        site_geom_27700=None,
        site_point_27700=Point(10.5, 5).wkt,
    )
    assert (
        match_planning_application(
            site_geometry=site_geometry,
            site_area_sqm=float(site_geometry.area),
            application=application,
        ).link_type
        == "POINT_NEAR_SITE"
    )

    warnings = coverage_warning_dicts(
        coverage_rows=[
            SimpleNamespace(
                source_family="BOROUGH_REGISTER",
                coverage_status=SourceCoverageStatus.COMPLETE,
                gap_reason=None,
            ),
            SimpleNamespace(
                source_family="PRIOR_APPROVAL",
                coverage_status=SourceCoverageStatus.PARTIAL,
                gap_reason="Missing borough register rows.",
            ),
        ]
    )
    assert any(item["code"] == "MANDATORY_SOURCE_PRIOR_APPROVAL_PARTIAL" for item in warnings)
    assert any(item["code"].startswith("MANDATORY_SOURCE_") for item in warnings)


def test_planning_register_normalize_adds_prior_approval_coverage_when_missing(monkeypatch) -> None:
    snapshot = SimpleNamespace(
        id=uuid.uuid4(),
        coverage_note="original note",
        freshness_status=SourceFreshnessStatus.FRESH,
        manifest_json={"dataset_key": "borough_register"},
    )
    asset = SimpleNamespace(id=uuid.uuid4())
    payload = {
        "coverage": [{"borough_id": "camden", "source_family": "BOROUGH_REGISTER"}],
        "applications": [],
    }
    captured_rows: list[dict[str, object]] = []

    monkeypatch.setattr(
        "landintel.planning.planning_register_normalize.register_dataset_snapshot",
        lambda **kwargs: (snapshot, asset, payload),
    )
    monkeypatch.setattr(
        "landintel.planning.planning_register_normalize.dataset_meta",
        lambda data: {
            "coverage_note": "meta coverage note",
            "freshness_status": "STALE",
            "coverage": list(data["coverage"]),
        },
    )
    monkeypatch.setattr(
        "landintel.planning.planning_register_normalize.upsert_coverage_snapshots",
        lambda **kwargs: captured_rows.extend(kwargs["coverage_rows"])
        or len(kwargs["coverage_rows"]),
    )
    monkeypatch.setattr(
        "landintel.planning.planning_register_normalize.upsert_planning_application_rows",
        lambda **kwargs: len(kwargs["applications"]),
    )

    result = import_borough_register_fixture(
        session=SimpleNamespace(flush=lambda: None),
        storage=SimpleNamespace(),
        fixture_path="/tmp/fixture.json",
        requested_by="pytest",
    )
    assert snapshot.coverage_note == "meta coverage note"
    assert snapshot.freshness_status == SourceFreshnessStatus.STALE
    assert len(captured_rows) == 2
    assert any(row["source_family"] == "PRIOR_APPROVAL" for row in captured_rows)
    assert result.coverage_count == 2


def test_catalog_seed_and_filters_cover_creation_update_and_query(db_session) -> None:
    templates = ensure_scenario_templates_seeded(db_session)
    assert len(templates) == 3
    first = templates[0]
    first.enabled = False
    db_session.flush()

    reseeded = ensure_scenario_templates_seeded(db_session)
    assert len(reseeded) == 3
    assert db_session.get(ScenarioTemplate, first.id).enabled is True

    filtered = get_enabled_scenario_templates(db_session, template_keys=["resi_5_9_full"])
    assert [row.key for row in filtered] == ["resi_5_9_full"]
    assert "resi_10_49_outline" in template_definition_map()


@dataclass
class _FakeGate:
    blocked_reason_codes: list[str]
    blocked_reason_text: str | None = None
    active_incident_id: uuid.UUID | None = None
    active_incident_reason: str | None = None
    replay_verified: bool | None = True
    payload_hash_matches: bool | None = True
    artifact_hashes_match: bool | None = True
    scope_release_matches_result: bool | None = True

    def model_copy(self, *, update: dict[str, object]) -> _FakeGate:
        payload = self.__dict__.copy()
        payload.update(update)
        return _FakeGate(**payload)


def test_visibility_and_override_helpers_cover_branch_variants(db_session, monkeypatch) -> None:
    assert coerce_role(None) == AppRoleName.ANALYST
    assert coerce_role(" reviewer ") == AppRoleName.REVIEWER
    assert (
        require_role(
            AppRoleName.REVIEWER,
            allowed_roles={AppRoleName.REVIEWER},
        )
        == AppRoleName.REVIEWER
    )
    with pytest.raises(ReviewAccessError):
        require_role(AppRoleName.ANALYST, allowed_roles={AppRoleName.REVIEWER})
    with pytest.raises(ReviewAccessError):
        role_at_least(AppRoleName.ANALYST, AppRoleName.ADMIN)
    assert load_active_scope(db_session, scope_key=None) is None
    assert get_open_incident_for_scope(db_session) is None
    with pytest.raises(ReviewAccessError, match="was not found"):
        set_scope_visibility(
            session=db_session,
            scope_key="missing",
            visibility_mode=VisibilityMode.HIDDEN_ONLY,
            requested_by="pytest",
            actor_role=AppRoleName.ADMIN,
            reason="missing scope",
        )

    redacted = _redact_visibility_gate_for_role(
        gate=_FakeGate(
            blocked_reason_codes=["REPLAY_FAILED"],
            blocked_reason_text="Replay failed.",
            active_incident_id=uuid.uuid4(),
            active_incident_reason="incident",
        ),
        viewer_role=AppRoleName.ANALYST,
    )
    assert redacted.blocked_reason_codes == ["OUTPUT_BLOCKED"]
    assert (
        redacted.blocked_reason_text
        == "Visible publication is currently blocked for this scope."
    )
    assert redacted.active_incident_id is None
    privileged = _redact_visibility_gate_for_role(
        gate=_FakeGate(blocked_reason_codes=["REPLAY_FAILED"]),
        viewer_role=AppRoleName.REVIEWER,
    )
    assert privileged.blocked_reason_codes == ["REPLAY_FAILED"]

    assert _text_or_none("  value  ") == "value"
    assert _text_or_none("   ") is None
    assert _validate_override_role(
        SimpleNamespace(
            override_type=AssessmentOverrideType.ACQUISITION_BASIS,
            actor_role=AppRoleName.ANALYST,
        )
    ) == AppRoleName.ANALYST
    with pytest.raises(ReviewAccessError):
        _validate_override_role(
            SimpleNamespace(
                override_type=AssessmentOverrideType.REVIEW_DISPOSITION,
                actor_role=AppRoleName.ANALYST,
            )
        )

    acquisition_payload, valuation_run = _build_override_payload(
        session=SimpleNamespace(),
        run=SimpleNamespace(),
        request=SimpleNamespace(
            override_type=AssessmentOverrideType.ACQUISITION_BASIS,
            acquisition_basis_gbp=123456.789,
            acquisition_basis_type=None,
        ),
        actor_name="pytest",
    )
    assert acquisition_payload["acquisition_basis_gbp"] == 123456.79
    assert valuation_run is None

    fake_valuation_set = SimpleNamespace(id=uuid.uuid4(), version="v9")
    fake_valuation_run = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(
        "landintel.review.overrides.build_or_refresh_valuation_for_assessment_with_assumption_set",
        lambda **kwargs: fake_valuation_run,
    )
    valuation_payload, resolved_run = _build_override_payload(
        session=SimpleNamespace(get=lambda *args, **kwargs: fake_valuation_set),
        run=SimpleNamespace(),
        request=SimpleNamespace(
            override_type=AssessmentOverrideType.VALUATION_ASSUMPTION_SET,
            valuation_assumption_set_id=fake_valuation_set.id,
        ),
        actor_name="pytest",
    )
    assert valuation_payload["valuation_run_id"] == str(fake_valuation_run.id)
    assert resolved_run is fake_valuation_run

    with pytest.raises(ReviewAccessError):
        _build_override_payload(
            session=SimpleNamespace(),
            run=SimpleNamespace(),
            request=SimpleNamespace(
                override_type=AssessmentOverrideType.VALUATION_ASSUMPTION_SET,
                valuation_assumption_set_id=None,
            ),
            actor_name="pytest",
        )

    review_payload, review_run = _build_override_payload(
        session=SimpleNamespace(),
        run=SimpleNamespace(),
        request=SimpleNamespace(
            override_type=AssessmentOverrideType.REVIEW_DISPOSITION,
            review_resolution_note="reviewed",
            resolve_manual_review=True,
        ),
        actor_name="pytest",
    )
    assert review_payload["resolve_manual_review"] is True
    assert review_run is None
    ranking_payload, ranking_run = _build_override_payload(
        session=SimpleNamespace(),
        run=SimpleNamespace(),
        request=SimpleNamespace(
            override_type=AssessmentOverrideType.RANKING_SUPPRESSION,
            ranking_suppressed=True,
            display_block_reason="hidden",
        ),
        actor_name="pytest",
    )
    assert ranking_payload["ranking_suppressed"] is True
    assert ranking_run is None

    serialized = _serialize_override(
        SimpleNamespace(
            id=uuid.uuid4(),
            override_type=AssessmentOverrideType.RANKING_SUPPRESSION,
                status=AssessmentOverrideStatus.ACTIVE,
            actor_name="pytest",
            actor_role=AppRoleName.ADMIN,
            reason="reason",
            override_json={"ranking_suppressed": True},
            supersedes_id=None,
            resolved_by=None,
            resolved_at=None,
            created_at=datetime(2026, 4, 18, tzinfo=UTC),
        )
    )
    assert serialized.reason == "reason"

    empty_summary = build_override_summary(
        session=SimpleNamespace(),
        assessment_run=SimpleNamespace(
            overrides=[],
            result=None,
            valuation_runs=[],
        ),
    )
    assert empty_summary is None


def test_audit_export_helpers_cover_empty_and_populated_paths(monkeypatch) -> None:
    assert _json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
    assert _sha256(b"payload") == _sha256(b"payload")
    assert (
        _serialize_audit_events(
            session=SimpleNamespace(execute=lambda *args, **kwargs: None),
            entity_refs=[],
        )
        == []
    )

    rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            action="audit",
            entity_type="assessment_run",
            entity_id="run-1",
            created_at=datetime(2026, 4, 18, tzinfo=UTC),
        )
    ]

    class _Result:
        def scalars(self) -> _Result:
            return self

        def all(self) -> list[object]:
            return rows

    session = SimpleNamespace(execute=lambda *args, **kwargs: _Result())
    assert _serialize_audit_events(session=session, entity_refs=[("assessment_run", "run-1")])[0][
        "action"
    ] == "audit"

    valuation_run = SimpleNamespace(id=uuid.uuid4())
    run = SimpleNamespace(
        id=uuid.uuid4(),
        result=SimpleNamespace(id=uuid.uuid4(), model_release_id=uuid.uuid4()),
        prediction_ledger=SimpleNamespace(id=uuid.uuid4()),
        valuation_runs=[valuation_run],
        overrides=[SimpleNamespace(id=uuid.uuid4())],
    )
    monkeypatch.setattr(
        "landintel.review.audit_export.frozen_valuation_run",
        lambda assessment_run: valuation_run,
    )
    refs = _entity_refs_for_run(run)
    assert ("assessment_run", str(run.id)) in refs
    assert ("valuation_run", str(valuation_run.id)) in refs


def test_scenario_normalize_reject_and_rulepack_refresh_branches(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    ).json()
    scenario_id = uuid.UUID(suggest["items"][0]["id"])

    rejected = confirm_or_update_scenario(
        session=db_session,
        scenario_id=scenario_id,
        request=SimpleNamespace(
            action="REJECT",
            requested_by="pytest",
            review_notes="Reject this scenario.",
        ),
    )
    assert rejected.status == ScenarioStatus.REJECTED
    assert rejected.is_current is False
    assert rejected.is_headline is False

    refreshed = refresh_site_scenarios_after_rulepack_change(
        session=db_session,
        site=rejected.site,
        requested_by="pytest",
    )
    assert refreshed >= 0
