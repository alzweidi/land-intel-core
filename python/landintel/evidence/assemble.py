from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from landintel.domain.enums import (
    BaselinePackStatus,
    EvidenceImportance,
    EvidencePolarity,
    ExtantPermissionStatus,
    SourceClass,
    VerifiedStatus,
)
from landintel.domain.models import BoroughBaselinePack, SiteCandidate, SiteScenario
from landintel.domain.schemas import EvidenceItemRead, EvidencePackRead, ExtantPermissionRead
from landintel.planning.enrich import (
    list_brownfield_states_for_site,
    list_latest_coverage_snapshots,
)
from landintel.planning.site_context_snapshots import (
    constraint_snapshot,
    planning_application_snapshot,
    policy_area_snapshot,
)


def assemble_site_evidence(
    *,
    session: Session,
    site: SiteCandidate,
    extant_permission: ExtantPermissionRead,
) -> EvidencePackRead:
    for_items: list[EvidenceItemRead] = []
    against_items: list[EvidenceItemRead] = []
    unknown_items: list[EvidenceItemRead] = []

    if extant_permission.status == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND:
        for_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.FOR,
                claim_text=extant_permission.summary,
                topic="extant_permission",
                importance=EvidenceImportance.HIGH,
                source_class=SourceClass.AUTHORITATIVE,
                source_label="Extant permission screen",
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=(
                    "Coverage-complete authoritative screening found no active extant "
                    "residential permission."
                ),
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    if extant_permission.status == ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND:
        for match in extant_permission.matched_records:
            if match.material:
                against_items.append(
                    EvidenceItemRead(
                        polarity=EvidencePolarity.AGAINST,
                        claim_text=match.detail,
                        topic="extant_permission",
                        importance=EvidenceImportance.HIGH,
                        source_class=_source_class_for_system(match.source_system),
                        source_label=match.source_label,
                        source_url=match.source_url,
                        source_snapshot_id=match.source_snapshot_id,
                        raw_asset_id=None,
                        excerpt_text=match.detail,
                        verified_status=VerifiedStatus.VERIFIED,
                    )
                )

    if extant_permission.status in {
        ExtantPermissionStatus.UNRESOLVED_MISSING_MANDATORY_SOURCE,
        ExtantPermissionStatus.CONTRADICTORY_SOURCE_MANUAL_REVIEW,
        ExtantPermissionStatus.NON_MATERIAL_OVERLAP_MANUAL_REVIEW,
    }:
        unknown_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text=extant_permission.summary,
                topic="extant_permission",
                importance=EvidenceImportance.HIGH,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label="Extant permission screen",
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text="Manual review or abstention is required.",
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    for gap in extant_permission.coverage_gaps:
        unknown_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text=gap.message,
                topic="source_coverage",
                importance=EvidenceImportance.HIGH,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=gap.code,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=gap.code,
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    for link in site.planning_links:
        app = link.planning_application
        app_snapshot = planning_application_snapshot(link)
        document_snapshots = app_snapshot.get("documents")
        first_document = (
            document_snapshots[0]
            if isinstance(document_snapshots, list)
            and document_snapshots
            and isinstance(document_snapshots[0], dict)
            else None
        )
        evidence = EvidenceItemRead(
            polarity=_planning_polarity(str(app_snapshot.get("status", app.status))),
            claim_text=(
                f"{app_snapshot.get('external_ref', app.external_ref)}: "
                f"{app_snapshot.get('proposal_description', app.proposal_description)}"
            ),
            topic="planning_history",
            importance=_planning_importance(str(app_snapshot.get("status", app.status))),
            source_class=_source_class_for_system(
                str(app_snapshot.get("source_system", app.source_system))
            ),
            source_label=(
                f"{app_snapshot.get('source_system', app.source_system)} "
                f"{app_snapshot.get('external_ref', app.external_ref)}"
            ),
            source_url=app_snapshot.get("source_url", app.source_url),
            source_snapshot_id=(
                getattr(link, "source_snapshot_id", None)
                or app_snapshot.get("source_snapshot_id")
                or app.source_snapshot_id
            ),
            raw_asset_id=None if first_document is None else first_document.get("asset_id"),
            excerpt_text=app_snapshot.get("decision") or app_snapshot.get("status", app.status),
            verified_status=VerifiedStatus.VERIFIED,
        )
        _append_by_polarity(
            evidence,
            for_items=for_items,
            against_items=against_items,
            unknown_items=unknown_items,
        )

    for state in list_brownfield_states_for_site(session=session, site=site):
        polarity = (
            EvidencePolarity.UNKNOWN
            if state.part.upper() == "PART_1"
            else EvidencePolarity.AGAINST
        )
        claim = (
            "Brownfield Part 1 entry overlaps the site. Part 1 is not PiP and is not "
            "exclusionary by itself."
            if state.part.upper() == "PART_1"
            else (
                "Brownfield Part 2 entry overlaps the site and can be materially "
                "exclusionary where PiP or linked TDC is active."
            )
        )
        evidence = EvidenceItemRead(
            polarity=polarity,
            claim_text=claim,
            topic="brownfield",
            importance=EvidenceImportance.MEDIUM,
            source_class=SourceClass.AUTHORITATIVE,
            source_label=f"Brownfield {state.external_ref}",
            source_url=state.source_url,
            source_snapshot_id=state.source_snapshot_id,
            raw_asset_id=None,
            excerpt_text=(
                f"{state.part} · PiP {state.pip_status or 'none'} · "
                f"TDC {state.tdc_status or 'none'}"
            ),
            verified_status=VerifiedStatus.VERIFIED,
        )
        _append_by_polarity(
            evidence,
            for_items=for_items,
            against_items=against_items,
            unknown_items=unknown_items,
        )

    for fact in site.policy_facts:
        area = fact.policy_area
        snapshot = policy_area_snapshot(fact)
        raw = snapshot.get("raw_record_json", area.raw_record_json)
        evidence = EvidenceItemRead(
            polarity=_polarity_from_record(raw, default=EvidencePolarity.FOR),
            claim_text=str(raw.get("summary") or snapshot.get("name", area.name)),
            topic="policy",
            importance=fact.importance,
            source_class=snapshot.get("source_class", area.source_class),
            source_label=(
                f"{snapshot.get('policy_family', area.policy_family)} "
                f"{snapshot.get('policy_code', area.policy_code)}"
            ),
            source_url=snapshot.get("source_url", area.source_url),
            source_snapshot_id=(
                getattr(fact, "source_snapshot_id", None)
                or snapshot.get("source_snapshot_id")
                or area.source_snapshot_id
            ),
            raw_asset_id=None,
            excerpt_text=fact.relation_type,
            verified_status=VerifiedStatus.VERIFIED,
        )
        _append_by_polarity(
            evidence,
            for_items=for_items,
            against_items=against_items,
            unknown_items=unknown_items,
        )

    for fact in site.constraint_facts:
        feature = fact.constraint_feature
        snapshot = constraint_snapshot(fact)
        raw = snapshot.get("raw_record_json", feature.raw_record_json)
        evidence = EvidenceItemRead(
            polarity=_polarity_from_record(raw, default=EvidencePolarity.AGAINST),
            claim_text=str(
                raw.get("summary") or snapshot.get("feature_subtype", feature.feature_subtype)
            ),
            topic="constraint",
            importance=fact.severity,
            source_class=snapshot.get("source_class", feature.source_class),
            source_label=(
                f"{snapshot.get('feature_family', feature.feature_family)} "
                f"{snapshot.get('feature_subtype', feature.feature_subtype)}"
            ),
            source_url=snapshot.get("source_url", feature.source_url),
            source_snapshot_id=(
                getattr(fact, "source_snapshot_id", None)
                or snapshot.get("source_snapshot_id")
                or feature.source_snapshot_id
            ),
            raw_asset_id=None,
            excerpt_text=snapshot.get("legal_status", feature.legal_status),
            verified_status=VerifiedStatus.VERIFIED,
        )
        _append_by_polarity(
            evidence,
            for_items=for_items,
            against_items=against_items,
            unknown_items=unknown_items,
        )

    for coverage in list_latest_coverage_snapshots(session=session, borough_id=site.borough_id):
        if coverage.coverage_status.value == "COMPLETE":
            continue
        unknown_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text=coverage.coverage_note
                or (
                    f"{coverage.source_family} coverage is "
                    f"{coverage.coverage_status.value.lower()}."
                ),
                topic="source_coverage",
                importance=EvidenceImportance.HIGH,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=coverage.source_family,
                source_url=None,
                source_snapshot_id=coverage.source_snapshot_id,
                raw_asset_id=None,
                excerpt_text=coverage.gap_reason,
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    return EvidencePackRead(
        for_=_dedupe_items(for_items),
        against=_dedupe_items(against_items),
        unknown=_dedupe_items(unknown_items),
    )


def assemble_scenario_evidence(
    *,
    session: Session,
    site: SiteCandidate,
    scenario: SiteScenario,
    site_evidence: EvidencePackRead | None,
    extant_permission: ExtantPermissionRead,
    baseline_pack: BoroughBaselinePack | None = None,
) -> EvidencePackRead:
    base = site_evidence or assemble_site_evidence(
        session=session,
        site=site,
        extant_permission=extant_permission,
    )
    for_items = list(base.for_)
    against_items = list(base.against)
    unknown_items = list(base.unknown)

    rationale = dict(scenario.rationale_json or {})
    missing_data_flags = list(rationale.get("missing_data_flags") or [])
    warning_codes = list(rationale.get("warning_codes") or [])

    for_items.append(
        EvidenceItemRead(
            polarity=EvidencePolarity.FOR,
            claim_text=(
                f"Scenario {scenario.template_key} assumes {scenario.units_assumed} units via "
                f"{scenario.route_assumed} route."
            ),
            topic="scenario_fit",
            importance=EvidenceImportance.HIGH,
            source_class=SourceClass.ANALYST_DERIVED,
            source_label=scenario.template_key,
            source_url=None,
            source_snapshot_id=None,
            raw_asset_id=None,
            excerpt_text=scenario.height_band_assumed,
            verified_status=VerifiedStatus.VERIFIED,
        )
    )

    if baseline_pack is not None:
        rulepack = next(
            (row for row in baseline_pack.rulepacks if row.template_key == scenario.template_key),
            None,
        )
        if rulepack is not None:
            rule_json = dict(rulepack.rule_json or {})
            citations = list(rule_json.get("citations") or [])
            scenario_rules = dict(rule_json.get("scenario_rules") or {})
            route_message = (
                f"Rulepack for {scenario.template_key} expects route "
                f"{scenario_rules.get('preferred_route', scenario.route_assumed)}."
            )
            for_items.append(
                EvidenceItemRead(
                    polarity=EvidencePolarity.FOR,
                    claim_text=route_message,
                    topic="route_fit",
                    importance=EvidenceImportance.MEDIUM,
                    source_class=SourceClass.ANALYST_DERIVED,
                    source_label=f"{baseline_pack.borough_id} rulepack",
                    source_url=_citation_url(citations),
                    source_snapshot_id=baseline_pack.source_snapshot_id,
                    raw_asset_id=None,
                    excerpt_text=rule_json.get("summary"),
                    verified_status=VerifiedStatus.VERIFIED,
                )
            )

            if baseline_pack.status not in {
                BaselinePackStatus.PILOT_READY,
                BaselinePackStatus.SIGNED_OFF,
            }:
                unknown_items.append(
                    EvidenceItemRead(
                        polarity=EvidencePolarity.UNKNOWN,
                        claim_text=(
                            f"Rulepack status is {baseline_pack.status.value}; analyst review "
                            "remains required."
                        ),
                        topic="rulepack_status",
                        importance=EvidenceImportance.HIGH,
                        source_class=SourceClass.ANALYST_DERIVED,
                        source_label=f"{baseline_pack.borough_id} rulepack",
                        source_url=_citation_url(citations),
                        source_snapshot_id=baseline_pack.source_snapshot_id,
                        raw_asset_id=None,
                        excerpt_text=rule_json.get("summary"),
                        verified_status=VerifiedStatus.VERIFIED,
                    )
                )

    if scenario.net_developable_area_pct < 0.6:
        against_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.AGAINST,
                claim_text=(
                    f"Scenario assumes only {round(scenario.net_developable_area_pct * 100, 1)}% "
                    "net developable area, which may constrain delivery."
                ),
                topic="developable_area",
                importance=EvidenceImportance.MEDIUM,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=scenario.template_key,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=scenario.access_assumption,
                verified_status=VerifiedStatus.VERIFIED,
            )
        )
    else:
        for_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.FOR,
                claim_text=(
                    "Net developable area assumption is "
                    f"{round(scenario.net_developable_area_pct * 100, 1)}%."
                ),
                topic="developable_area",
                importance=EvidenceImportance.MEDIUM,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=scenario.template_key,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=scenario.access_assumption,
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    if scenario.parking_assumption:
        unknown_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text=scenario.parking_assumption,
                topic="parking",
                importance=EvidenceImportance.MEDIUM,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=scenario.template_key,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text="Parking remains an assumption in Phase 4A.",
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    if scenario.affordable_housing_assumption:
        unknown_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text=scenario.affordable_housing_assumption,
                topic="affordable_housing",
                importance=EvidenceImportance.MEDIUM,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=scenario.template_key,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text="Affordable-housing triggers remain scenario-conditioned.",
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    if scenario.access_assumption:
        unknown_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text=scenario.access_assumption,
                topic="access",
                importance=EvidenceImportance.HIGH,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=scenario.template_key,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text="Access/frontage remains a deterministic assumption in Phase 4A.",
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    for flag in missing_data_flags:
        unknown_items.append(
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text=f"Scenario missing-data flag: {flag}",
                topic="scenario_gap",
                importance=EvidenceImportance.HIGH,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=scenario.template_key,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=flag,
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    for code in warning_codes:
        target = unknown_items
        polarity = EvidencePolarity.UNKNOWN
        importance = EvidenceImportance.MEDIUM
        if "OUT_OF_SCOPE" in code:
            target = against_items
            polarity = EvidencePolarity.AGAINST
            importance = EvidenceImportance.HIGH
        target.append(
            EvidenceItemRead(
                polarity=polarity,
                claim_text=f"Scenario warning: {code}",
                topic="scenario_warning",
                importance=importance,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label=scenario.template_key,
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=scenario.stale_reason,
                verified_status=VerifiedStatus.VERIFIED,
            )
        )

    return EvidencePackRead(
        for_=_dedupe_items(for_items),
        against=_dedupe_items(against_items),
        unknown=_dedupe_items(unknown_items),
    )


def _append_by_polarity(
    item: EvidenceItemRead,
    *,
    for_items: list[EvidenceItemRead],
    against_items: list[EvidenceItemRead],
    unknown_items: list[EvidenceItemRead],
) -> None:
    if item.polarity == EvidencePolarity.FOR:
        for_items.append(item)
        return
    if item.polarity == EvidencePolarity.AGAINST:
        against_items.append(item)
        return
    unknown_items.append(item)


def _citation_url(citations: list[dict[str, object]]) -> str | None:
    for citation in citations:
        for key in ("source_url", "url"):
            url = citation.get(key)
            if isinstance(url, str) and url:
                return url
    return None


def _planning_polarity(status: str) -> EvidencePolarity:
    normalized = status.upper()
    if normalized in {"APPROVED", "LAPSED", "EXPIRED", "WITHDRAWN"}:
        return EvidencePolarity.FOR
    if normalized in {"REFUSED", "REJECTED"}:
        return EvidencePolarity.AGAINST
    return EvidencePolarity.UNKNOWN


def _planning_importance(status: str) -> EvidenceImportance:
    normalized = status.upper()
    if normalized in {"APPROVED", "REFUSED"}:
        return EvidenceImportance.HIGH
    if normalized in {"LAPSED", "EXPIRED"}:
        return EvidenceImportance.MEDIUM
    return EvidenceImportance.LOW


def _source_class_for_system(source_system: str) -> SourceClass:
    if source_system == "BOROUGH_REGISTER":
        return SourceClass.AUTHORITATIVE
    if source_system == "PLD":
        return SourceClass.OFFICIAL_INDICATIVE
    if source_system == "BROWNFIELD":
        return SourceClass.AUTHORITATIVE
    return SourceClass.ANALYST_DERIVED


def _polarity_from_record(
    raw_record_json: dict[str, object] | None,
    *,
    default: EvidencePolarity,
) -> EvidencePolarity:
    if raw_record_json is None:
        return default
    value = raw_record_json.get("evidence_polarity")
    if value is None:
        return default
    return EvidencePolarity(str(value).upper())


def _dedupe_items(items: Iterable[EvidenceItemRead]) -> list[EvidenceItemRead]:
    deduped: dict[tuple[str, str, str], EvidenceItemRead] = {}
    for item in items:
        key = (item.topic, item.source_label, item.claim_text)
        deduped.setdefault(key, item)
    return list(deduped.values())
