from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from landintel.domain.enums import (
    BaselinePackStatus,
    EligibilityStatus,
    EvidenceImportance,
    EvidencePolarity,
    ExtantPermissionStatus,
    SourceClass,
    VerifiedStatus,
)
from landintel.domain.schemas import (
    EvidenceItemRead,
    EvidencePackRead,
    ExtantPermissionMatchRead,
    ExtantPermissionRead,
    SiteWarningRead,
)
from landintel.evidence import assemble as evidence_service


class _Session:
    pass


def _site():
    return SimpleNamespace(
        borough_id="camden",
        planning_links=[],
        policy_facts=[],
        constraint_facts=[],
    )


def _app(
    *,
    external_ref: str,
    status: str,
    source_system: str = "BOROUGH_REGISTER",
    decision: str = "APPROVED",
    decision_type: str = "FULL_RESIDENTIAL",
    proposal_description: str = "Residential scheme.",
    units_proposed: int = 8,
):
    return SimpleNamespace(
        external_ref=external_ref,
        source_system=source_system,
        source_snapshot_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        proposal_description=proposal_description,
        status=status,
        decision=decision,
        decision_type=decision_type,
        route_normalized="FULL",
        units_proposed=units_proposed,
        source_url=f"https://example.test/{external_ref}",
        documents=[SimpleNamespace(asset_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))],
        raw_record_json={},
    )


def _base_site_evidence() -> EvidencePackRead:
    return EvidencePackRead(
        for_=[
            EvidenceItemRead(
                polarity=EvidencePolarity.FOR,
                claim_text="Base site evidence",
                topic="site_base",
                importance=EvidenceImportance.LOW,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label="Base",
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=None,
                verified_status=VerifiedStatus.VERIFIED,
            )
        ],
        against=[],
        unknown=[],
    )


def _baseline_pack(*, status: BaselinePackStatus = BaselinePackStatus.PILOT_READY):
    return SimpleNamespace(
        borough_id="camden",
        status=status,
        source_snapshot_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        rulepacks=[
            SimpleNamespace(
                template_key="resi_5_9_full",
                rule_json={
                    "summary": "Fixture rulepack summary",
                    "citations": [
                        {
                            "source_url": "https://example.test/rulepack",
                            "label": "Camden rulepack",
                            "source_family": "BOROUGH_REGISTER",
                            "effective_date": "2026-04-18",
                        }
                    ],
                    "scenario_rules": {"preferred_route": "FULL"},
                },
            )
        ],
    )


def _scenario(
    *,
    net_developable_area_pct: float,
    parking_assumption: str | None = None,
    affordable_housing_assumption: str | None = None,
    access_assumption: str | None = None,
    warning_codes: list[str] | None = None,
    missing_data_flags: list[str] | None = None,
    stale_reason: str | None = None,
):
    scenario = SimpleNamespace(
        id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        site_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        template_key="resi_5_9_full",
        template_version="1.0",
        proposal_form=SimpleNamespace(value="REDEVELOPMENT"),
        units_assumed=8,
        route_assumed="FULL",
        height_band_assumed="MID_RISE",
        net_developable_area_pct=net_developable_area_pct,
        red_line_geom_hash="geom-hash",
        scenario_source=SimpleNamespace(value="ANALYST"),
        status=SimpleNamespace(value="ANALYST_CONFIRMED"),
        supersedes_id=None,
        is_current=True,
        is_headline=False,
        heuristic_rank=3,
        manual_review_required=False,
        stale_reason=stale_reason,
        housing_mix_assumed_json={},
        parking_assumption=parking_assumption,
        affordable_housing_assumption=affordable_housing_assumption,
        access_assumption=access_assumption,
        reason_codes=[],
        missing_data_flags=missing_data_flags or [],
        warning_codes=warning_codes or [],
    )
    scenario.rationale_json = {
        "missing_data_flags": list(missing_data_flags or []),
        "warning_codes": list(warning_codes or []),
    }
    return scenario


def test_assemble_site_evidence_covers_extant_permission_planning_brownfield_and_coverage(
    monkeypatch,
):
    site = _site()
    approvals = _app(
        external_ref="CAM-APPROVED",
        status="APPROVED",
        source_system="BOROUGH_REGISTER",
    )
    refusals = _app(
        external_ref="CAM-REFUSED",
        status="REFUSED",
        source_system="PLD",
        decision="REFUSED",
        decision_type="MIXED_USE",
        proposal_description="Commercial shell only.",
    )
    site.planning_links = [
        SimpleNamespace(
            planning_application=approvals,
            source_snapshot_id=UUID("11111111-1111-1111-1111-111111111111"),
            snapshot_json={
                "status": "APPROVED",
                "external_ref": "CAM-APPROVED",
                "proposal_description": "Approved residential scheme.",
                "source_system": "BOROUGH_REGISTER",
                "source_url": "https://example.test/cam-approved",
                "source_snapshot_id": UUID("11111111-1111-1111-1111-111111111111"),
                "documents": [
                    {
                        "asset_id": UUID("aaaaaaaa-0000-0000-0000-000000000001"),
                    }
                ],
            },
        ),
        SimpleNamespace(
            planning_application=refusals,
            source_snapshot_id=None,
            snapshot_json={
                "status": "REFUSED",
                "external_ref": "CAM-REFUSED",
                "proposal_description": "Commercial shell only.",
                "source_system": "PLD",
                "source_url": "https://example.test/cam-refused",
                "source_snapshot_id": UUID("22222222-2222-2222-2222-222222222222"),
                "documents": [],
            },
        ),
    ]
    site.policy_facts = [
        SimpleNamespace(
            importance=EvidenceImportance.HIGH,
            relation_type="supports",
            source_snapshot_id=UUID("33333333-3333-3333-3333-333333333333"),
            policy_area=SimpleNamespace(
                policy_family="SITE_ALLOCATION",
                policy_code="SA1",
                name="Site allocation policy",
                source_class=SourceClass.AUTHORITATIVE,
                source_url="https://example.test/policy",
                source_snapshot_id=UUID("33333333-3333-3333-3333-333333333333"),
                raw_record_json={"summary": "Policy supports redevelopment."},
            ),
            snapshot_json={
                "policy_family": "SITE_ALLOCATION",
                "policy_code": "SA1",
                "source_url": "https://example.test/policy",
                "source_snapshot_id": UUID("33333333-3333-3333-3333-333333333333"),
                "raw_record_json": {
                    "summary": "Policy supports redevelopment.",
                    "evidence_polarity": "for",
                },
            },
        )
    ]
    site.constraint_facts = [
        SimpleNamespace(
            severity=EvidenceImportance.MEDIUM,
            source_snapshot_id=UUID("44444444-4444-4444-4444-444444444444"),
            constraint_feature=SimpleNamespace(
                feature_family="heritage",
                feature_subtype="listed_building",
                legal_status="designated",
                source_class=SourceClass.AUTHORITATIVE,
                source_url="https://example.test/constraint",
                source_snapshot_id=UUID("44444444-4444-4444-4444-444444444444"),
                raw_record_json={"summary": "Constraint argues against development."},
            ),
            snapshot_json={
                "feature_family": "heritage",
                "feature_subtype": "listed_building",
                "legal_status": "designated",
                "source_url": "https://example.test/constraint",
                "source_snapshot_id": UUID("44444444-4444-4444-4444-444444444444"),
                "raw_record_json": {
                    "summary": "Constraint argues against development.",
                    "evidence_polarity": "against",
                },
            },
        )
    ]

    brownfield_rows = [
        SimpleNamespace(
            part="PART_1",
            external_ref="BF-1",
            source_url="https://example.test/bf-1",
            source_snapshot_id=UUID("55555555-5555-5555-5555-555555555555"),
            pip_status="ACTIVE",
            tdc_status=None,
        ),
        SimpleNamespace(
            part="PART_2",
            external_ref="BF-2",
            source_url="https://example.test/bf-2",
            source_snapshot_id=UUID("66666666-6666-6666-6666-666666666666"),
            pip_status=None,
            tdc_status="ACTIVE",
        ),
    ]
    coverage_rows = [
        SimpleNamespace(
            coverage_status=SimpleNamespace(value="COMPLETE"),
            source_family="planning",
            coverage_note="complete planning coverage",
            gap_reason=None,
            source_snapshot_id=UUID("77777777-7777-7777-7777-777777777777"),
        ),
        SimpleNamespace(
            coverage_status=SimpleNamespace(value="PARTIAL"),
            source_family="heritage",
            coverage_note=None,
            gap_reason="missing heritage register feed",
            source_snapshot_id=UUID("88888888-8888-8888-8888-888888888888"),
        ),
    ]

    monkeypatch.setattr(
        evidence_service,
        "planning_application_snapshot",
        lambda link: dict(link.snapshot_json),
    )
    monkeypatch.setattr(
        evidence_service,
        "policy_area_snapshot",
        lambda fact: dict(fact.snapshot_json),
    )
    monkeypatch.setattr(
        evidence_service,
        "constraint_snapshot",
        lambda fact: dict(fact.snapshot_json),
    )
    monkeypatch.setattr(
        evidence_service,
        "list_brownfield_states_for_site",
        lambda **kwargs: list(brownfield_rows),
    )
    monkeypatch.setattr(
        evidence_service,
        "list_latest_coverage_snapshots",
        lambda **kwargs: list(coverage_rows),
    )

    statuses = [
        (
            ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            ExtantPermissionRead(
                status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
                eligibility_status=EligibilityStatus.PASS,
                manual_review_required=False,
                summary="No active permission found",
                matched_records=[],
                coverage_gaps=[SiteWarningRead(code="GAP-1", message="Missing coverage")],
            ),
        ),
        (
            ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND,
            ExtantPermissionRead(
                status=ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND,
                eligibility_status=EligibilityStatus.FAIL,
                manual_review_required=True,
                summary="Active permission found",
                matched_records=[
                    ExtantPermissionMatchRead(
                        source_kind="planning",
                        source_system="BOROUGH_REGISTER",
                        source_label="Approved record",
                        source_url="https://example.test/cam-approved",
                        source_snapshot_id=UUID("11111111-1111-1111-1111-111111111111"),
                        material=True,
                        detail="Material approved permission",
                    ),
                    ExtantPermissionMatchRead(
                        source_kind="planning",
                        source_system="PLD",
                        source_label="Unrelated record",
                        source_url="https://example.test/cam-refused",
                        source_snapshot_id=UUID("22222222-2222-2222-2222-222222222222"),
                        material=False,
                        detail="Non-material record",
                    ),
                ],
            ),
        ),
        (
            ExtantPermissionStatus.CONTRADICTORY_SOURCE_MANUAL_REVIEW,
            ExtantPermissionRead(
                status=ExtantPermissionStatus.CONTRADICTORY_SOURCE_MANUAL_REVIEW,
                eligibility_status=EligibilityStatus.ABSTAIN,
                manual_review_required=True,
                summary="Contradictory sources",
                matched_records=[],
            ),
        ),
    ]

    no_active_evidence = None
    for status, extant_permission in statuses:
        evidence = evidence_service.assemble_site_evidence(
            session=_Session(),
            site=site,
            extant_permission=extant_permission,
        )
        topics = [item.topic for item in evidence.for_ + evidence.against + evidence.unknown]
        assert "planning_history" in topics
        assert "brownfield" in topics
        assert "policy" in topics
        assert "constraint" in topics
        assert "source_coverage" in topics
        if status == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND:
            no_active_evidence = evidence
            assert any(
                item.topic == "extant_permission" and item.polarity == EvidencePolarity.FOR
                for item in evidence.for_
            )
        elif status == ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND:
            assert any(
                item.topic == "extant_permission" and item.polarity == EvidencePolarity.AGAINST
                for item in evidence.against
            )
            assert all("Non-material" not in item.claim_text for item in evidence.against)
        else:
            assert any(
                item.topic == "extant_permission" and item.polarity == EvidencePolarity.UNKNOWN
                for item in evidence.unknown
            )

    assert no_active_evidence is not None
    assert any(
        item.topic == "source_coverage" and item.claim_text == "Missing coverage"
        for item in no_active_evidence.unknown
    )
    assert any(
        item.topic == "brownfield" and item.polarity == EvidencePolarity.UNKNOWN
        for item in no_active_evidence.unknown
    )
    assert any(
        item.topic == "brownfield" and item.polarity == EvidencePolarity.AGAINST
        for item in no_active_evidence.against
    )
    assert any(
        item.topic == "policy" and item.polarity == EvidencePolarity.FOR
        for item in no_active_evidence.for_
    )
    assert any(
        item.topic == "constraint" and item.polarity == EvidencePolarity.AGAINST
        for item in no_active_evidence.against
    )
    assert any(
        item.topic == "source_coverage" and item.claim_text == "heritage coverage is partial."
        for item in no_active_evidence.unknown
    )


def test_assemble_scenario_evidence_covers_baseline_pack_branches_and_warning_paths(monkeypatch):
    site = _site()
    site.planning_links = [
        SimpleNamespace(
            planning_application=_app(
                external_ref="CAM-APPROVED",
                status="APPROVED",
                decision="APPROVED",
                proposal_description="Residential scheme with frontage access.",
            ),
            source_snapshot_id=UUID("11111111-1111-1111-1111-111111111111"),
            snapshot_json={
                "status": "APPROVED",
                "external_ref": "CAM-APPROVED",
                "proposal_description": "Approved residential scheme.",
                "source_system": "BOROUGH_REGISTER",
                "source_url": "https://example.test/cam-approved",
                "source_snapshot_id": UUID("11111111-1111-1111-1111-111111111111"),
                "documents": [
                    {
                        "asset_id": UUID("aaaaaaaa-0000-0000-0000-000000000001"),
                    }
                ],
            },
        )
    ]

    monkeypatch.setattr(
        evidence_service,
        "planning_application_snapshot",
        lambda link: dict(link.snapshot_json),
    )
    monkeypatch.setattr(
        evidence_service,
        "policy_area_snapshot",
        lambda fact: {},
    )
    monkeypatch.setattr(
        evidence_service,
        "constraint_snapshot",
        lambda fact: {},
    )
    monkeypatch.setattr(
        evidence_service,
        "list_brownfield_states_for_site",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        evidence_service,
        "list_latest_coverage_snapshots",
        lambda **kwargs: [],
    )

    base = _base_site_evidence()
    scenario = _scenario(
        net_developable_area_pct=0.55,
        parking_assumption="Parking assumed on street.",
        affordable_housing_assumption="30% affordable housing assumed.",
        access_assumption="Access assumed via frontage.",
        warning_codes=["OUT_OF_SCOPE_EXTANT_PERMISSION", "RULEPACK_STALE"],
        missing_data_flags=["MISSING_SOURCE"],
        stale_reason="Scenario stale due to geometry change.",
    )
    baseline_pack = _baseline_pack(status=BaselinePackStatus.STALE)

    result = evidence_service.assemble_scenario_evidence(
        session=_Session(),
        site=site,
        scenario=scenario,
        site_evidence=base,
        extant_permission=ExtantPermissionRead(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="No active permission found",
            matched_records=[],
        ),
        baseline_pack=baseline_pack,
    )

    assert any(item.topic == "site_base" for item in result.for_)
    assert any(item.topic == "scenario_fit" for item in result.for_)
    assert any(item.topic == "route_fit" for item in result.for_)
    assert any(item.topic == "rulepack_status" for item in result.unknown)
    assert any(
        item.topic == "developable_area" and item.polarity == EvidencePolarity.AGAINST
        for item in result.against
    )
    assert any(item.topic == "parking" for item in result.unknown)
    assert any(item.topic == "affordable_housing" for item in result.unknown)
    assert any(item.topic == "access" for item in result.unknown)
    assert any(item.topic == "scenario_gap" for item in result.unknown)
    assert any(
        item.topic == "scenario_warning" and item.polarity == EvidencePolarity.AGAINST
        for item in result.against
    )
    assert any(
        item.topic == "scenario_warning" and item.polarity == EvidencePolarity.UNKNOWN
        for item in result.unknown
    )

    fallback_result = evidence_service.assemble_scenario_evidence(
        session=_Session(),
        site=site,
        scenario=_scenario(net_developable_area_pct=0.72),
        site_evidence=None,
        extant_permission=ExtantPermissionRead(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="No active permission found",
            matched_records=[],
        ),
        baseline_pack=baseline_pack,
    )
    assert any(item.topic == "scenario_fit" for item in fallback_result.for_)
    assert any(
        item.topic == "developable_area" and item.polarity == EvidencePolarity.FOR
        for item in fallback_result.for_
    )


def test_evidence_helpers_cover_polarity_citation_and_dedupe_paths():
    appended_for: list[EvidenceItemRead] = []
    appended_against: list[EvidenceItemRead] = []
    appended_unknown: list[EvidenceItemRead] = []

    for_item = EvidenceItemRead(
        polarity=EvidencePolarity.FOR,
        claim_text="A",
        topic="t",
        importance=EvidenceImportance.LOW,
        source_class=SourceClass.ANALYST_DERIVED,
        source_label="L",
        source_url=None,
        source_snapshot_id=None,
        raw_asset_id=None,
        excerpt_text=None,
        verified_status=VerifiedStatus.VERIFIED,
    )
    against_item = for_item.model_copy(update={"polarity": EvidencePolarity.AGAINST})
    unknown_item = for_item.model_copy(update={"polarity": EvidencePolarity.UNKNOWN})

    evidence_service._append_by_polarity(
        for_item,
        for_items=appended_for,
        against_items=appended_against,
        unknown_items=appended_unknown,
    )
    evidence_service._append_by_polarity(
        against_item,
        for_items=appended_for,
        against_items=appended_against,
        unknown_items=appended_unknown,
    )
    evidence_service._append_by_polarity(
        unknown_item,
        for_items=appended_for,
        against_items=appended_against,
        unknown_items=appended_unknown,
    )
    assert appended_for == [for_item]
    assert appended_against == [against_item]
    assert appended_unknown == [unknown_item]

    assert (
        evidence_service._citation_url(
            [{"url": "https://example.test/first"}, {"source_url": "https://example.test/second"}]
        )
        == "https://example.test/first"
    )
    assert evidence_service._citation_url([]) is None

    assert evidence_service._planning_polarity("approved") == EvidencePolarity.FOR
    assert evidence_service._planning_polarity("refused") == EvidencePolarity.AGAINST
    assert evidence_service._planning_polarity("pending") == EvidencePolarity.UNKNOWN
    assert evidence_service._planning_importance("approved") == EvidenceImportance.HIGH
    assert evidence_service._planning_importance("lapsed") == EvidenceImportance.MEDIUM
    assert evidence_service._planning_importance("unknown") == EvidenceImportance.LOW

    assert (
        evidence_service._source_class_for_system("BOROUGH_REGISTER") == SourceClass.AUTHORITATIVE
    )
    assert evidence_service._source_class_for_system("PLD") == SourceClass.OFFICIAL_INDICATIVE
    assert evidence_service._source_class_for_system("BROWNFIELD") == SourceClass.AUTHORITATIVE
    assert evidence_service._source_class_for_system("OTHER") == SourceClass.ANALYST_DERIVED

    assert (
        evidence_service._polarity_from_record(None, default=EvidencePolarity.FOR)
        == EvidencePolarity.FOR
    )
    assert (
        evidence_service._polarity_from_record(
            {"evidence_polarity": "against"}, default=EvidencePolarity.FOR
        )
        == EvidencePolarity.AGAINST
    )
    assert (
        evidence_service._polarity_from_record({}, default=EvidencePolarity.UNKNOWN)
        == EvidencePolarity.UNKNOWN
    )

    deduped = evidence_service._dedupe_items(
        [
            EvidenceItemRead(
                polarity=EvidencePolarity.FOR,
                claim_text="duplicate",
                topic="t",
                importance=EvidenceImportance.LOW,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label="L",
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=None,
                verified_status=VerifiedStatus.VERIFIED,
            ),
            EvidenceItemRead(
                polarity=EvidencePolarity.FOR,
                claim_text="duplicate",
                topic="t",
                importance=EvidenceImportance.LOW,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label="L",
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=None,
                verified_status=VerifiedStatus.VERIFIED,
            ),
        ]
    )
    assert len(deduped) == 1
