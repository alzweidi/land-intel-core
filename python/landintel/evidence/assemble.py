from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from landintel.domain.enums import (
    EvidenceImportance,
    EvidencePolarity,
    ExtantPermissionStatus,
    SourceClass,
    VerifiedStatus,
)
from landintel.domain.models import SiteCandidate
from landintel.domain.schemas import EvidenceItemRead, EvidencePackRead, ExtantPermissionRead
from landintel.planning.enrich import (
    list_brownfield_states_for_site,
    list_latest_coverage_snapshots,
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
        evidence = EvidenceItemRead(
            polarity=_planning_polarity(app.status),
            claim_text=f"{app.external_ref}: {app.proposal_description}",
            topic="planning_history",
            importance=_planning_importance(app.status),
            source_class=_source_class_for_system(app.source_system),
            source_label=f"{app.source_system} {app.external_ref}",
            source_url=app.source_url,
            source_snapshot_id=app.source_snapshot_id,
            raw_asset_id=app.documents[0].asset_id if app.documents else None,
            excerpt_text=app.decision or app.status,
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
        raw = fact.policy_area.raw_record_json
        evidence = EvidenceItemRead(
            polarity=_polarity_from_record(raw, default=EvidencePolarity.FOR),
            claim_text=str(raw.get("summary") or fact.policy_area.name),
            topic="policy",
            importance=fact.importance,
            source_class=fact.policy_area.source_class,
            source_label=f"{fact.policy_area.policy_family} {fact.policy_area.policy_code}",
            source_url=fact.policy_area.source_url,
            source_snapshot_id=fact.policy_area.source_snapshot_id,
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
        raw = fact.constraint_feature.raw_record_json
        evidence = EvidenceItemRead(
            polarity=_polarity_from_record(raw, default=EvidencePolarity.AGAINST),
            claim_text=str(raw.get("summary") or fact.constraint_feature.feature_subtype),
            topic="constraint",
            importance=fact.severity,
            source_class=fact.constraint_feature.source_class,
            source_label=(
                f"{fact.constraint_feature.feature_family} "
                f"{fact.constraint_feature.feature_subtype}"
            ),
            source_url=fact.constraint_feature.source_url,
            source_snapshot_id=fact.constraint_feature.source_snapshot_id,
            raw_asset_id=None,
            excerpt_text=fact.constraint_feature.legal_status,
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
