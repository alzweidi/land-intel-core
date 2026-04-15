from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import PriceBasisType
from landintel.domain.models import (
    BoroughBaselinePack,
    ListingCluster,
    ListingDocument,
    ListingItem,
    ListingSnapshot,
    PlanningApplication,
    PlanningApplicationDocument,
    PlanningConstraintFeature,
    PolicyArea,
    SiteCandidate,
    SiteConstraintFact,
    SiteLpaLink,
    SitePlanningLink,
    SitePolicyFact,
    SiteScenario,
    SiteTitleLink,
    SourceSnapshot,
)
from landintel.domain.schemas import (
    BoroughBaselinePackRead,
    BoroughRulepackRead,
    BrownfieldSiteStateRead,
    PlanningApplicationDocumentRead,
    PlanningApplicationRead,
    PlanningConstraintFeatureRead,
    PolicyAreaRead,
    SiteClusterSummaryRead,
    SiteConstraintFactRead,
    SiteDetailRead,
    SiteGeometryRead,
    SiteGeometryRevisionRead,
    SiteListingSummaryRead,
    SiteListResponse,
    SiteLpaLinkRead,
    SiteMarketEventRead,
    SitePlanningLinkRead,
    SitePolicyFactRead,
    SiteSummaryRead,
    SiteTitleLinkRead,
    SiteWarningRead,
    SourceCoverageSnapshotRead,
)
from landintel.evidence.assemble import assemble_scenario_evidence, assemble_site_evidence
from landintel.planning.enrich import (
    get_borough_baseline_pack,
    list_brownfield_states_for_site,
    list_latest_coverage_snapshots,
)
from landintel.planning.extant_permission import evaluate_site_extant_permission
from landintel.services.listings_readback import (
    serialize_listing_document,
    serialize_raw_asset,
    serialize_source_snapshot,
)


def list_sites(
    session: Session,
    *,
    q: str | None = None,
    borough: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> SiteListResponse:
    stmt = select(SiteCandidate)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(SiteCandidate.display_name.ilike(pattern))
    if borough:
        stmt = stmt.where(SiteCandidate.borough_id == borough)
    if status:
        stmt = stmt.where(SiteCandidate.site_status == status)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = session.execute(count_stmt).scalar_one()

    stmt = (
        stmt.options(*_site_load_options())
        .order_by(SiteCandidate.updated_at.desc(), SiteCandidate.display_name.asc())
        .limit(limit)
        .offset(offset)
    )
    items = session.execute(stmt).scalars().unique().all()
    return SiteListResponse(items=[serialize_site_summary(item) for item in items], total=total)


def get_site(session: Session, *, site_id: UUID) -> SiteDetailRead | None:
    stmt = (
        select(SiteCandidate)
        .where(SiteCandidate.id == site_id)
        .options(*_site_load_options())
    )
    site = session.execute(stmt).scalar_one_or_none()
    if site is None:
        return None
    return serialize_site_detail(session=session, site=site)


def serialize_site_summary(site: SiteCandidate) -> SiteSummaryRead:
    return SiteSummaryRead(
        id=site.id,
        display_name=site.display_name,
        borough_id=site.borough_id,
        borough_name=site.borough.name if site.borough else None,
        site_status=site.site_status,
        manual_review_required=site.manual_review_required,
        warnings=_flatten_warnings(site.warning_json),
        current_geometry=SiteGeometryRead(
            geom_4326=site.geom_4326,
            geom_hash=site.geom_hash,
            geom_source_type=site.geom_source_type,
            geom_confidence=site.geom_confidence,
            site_area_sqm=site.site_area_sqm,
        ),
        current_listing=_serialize_site_listing(site.current_listing),
        listing_cluster=SiteClusterSummaryRead(
            id=site.listing_cluster.id,
            cluster_key=site.listing_cluster.cluster_key,
            cluster_status=site.listing_cluster.cluster_status,
            member_count=len(site.listing_cluster.members),
        ),
    )


def serialize_site_detail(*, session: Session, site: SiteCandidate) -> SiteDetailRead:
    summary = serialize_site_summary(site)
    current_listing = site.current_listing
    source_snapshots = _source_snapshots_for_listing(current_listing)
    coverage_rows = list_latest_coverage_snapshots(session=session, borough_id=site.borough_id)
    brownfield_states = list_brownfield_states_for_site(session=session, site=site)
    extant_permission = evaluate_site_extant_permission(session=session, site=site)
    evidence = assemble_site_evidence(
        session=session,
        site=site,
        extant_permission=extant_permission,
    )
    baseline_pack = get_borough_baseline_pack(session=session, borough_id=site.borough_id)
    from landintel.services.scenarios_readback import serialize_site_scenario_summary

    scenario_summaries = [
        serialize_site_scenario_summary(
            session=session,
            scenario=scenario,
            baseline_pack=baseline_pack,
            site=site,
        )
        for scenario in sorted(
            site.scenarios,
            key=lambda row: (
                not row.is_headline,
                not row.is_current,
                row.heuristic_rank if row.heuristic_rank is not None else 999,
                row.updated_at,
                str(row.id),
            ),
        )
    ]
    headline_scenario = next((row for row in site.scenarios if row.is_headline), None)
    if headline_scenario is not None:
        evidence = assemble_scenario_evidence(
            session=session,
            site=site,
            scenario=headline_scenario,
            site_evidence=evidence,
            extant_permission=extant_permission,
            baseline_pack=baseline_pack,
        )

    return SiteDetailRead(
        **summary.model_dump(),
        geometry_revisions=[
            SiteGeometryRevisionRead(
                id=revision.id,
                geom_hash=revision.geom_hash,
                geom_4326=revision.geom_4326,
                source_type=revision.source_type,
                confidence=revision.confidence,
                site_area_sqm=revision.site_area_sqm,
                reason=revision.reason,
                created_by=revision.created_by,
                created_at=revision.created_at,
                raw_asset_id=revision.raw_asset_id,
                warnings=_flatten_warnings(revision.warning_json),
            )
            for revision in site.geometry_revisions
        ],
        lpa_links=[
            SiteLpaLinkRead(
                lpa_id=link.lpa_id,
                lpa_name=link.lpa.name,
                overlap_pct=round(link.overlap_pct, 4),
                overlap_sqm=round(link.overlap_sqm, 2),
                is_primary=link.is_primary,
            )
            for link in sorted(site.lpa_links, key=lambda item: item.overlap_sqm, reverse=True)
        ],
        title_links=[
            SiteTitleLinkRead(
                title_number=link.title_number,
                overlap_pct=round(link.overlap_pct, 4),
                overlap_sqm=round(link.overlap_sqm, 2),
                confidence=link.confidence,
            )
            for link in site.title_links
        ],
        market_events=[
            SiteMarketEventRead(
                id=event.id,
                event_type=event.event_type.value,
                event_at=event.event_at,
                price_gbp=event.price_gbp,
                basis_type=event.basis_type,
                listing_item_id=event.listing_item_id,
                notes=event.notes,
            )
            for event in site.market_events
        ],
        source_documents=[
            serialize_listing_document(document)
            for document in (current_listing.documents if current_listing is not None else [])
        ],
        source_snapshots=[serialize_source_snapshot(snapshot) for snapshot in source_snapshots],
        source_coverage=[
            SourceCoverageSnapshotRead(
                id=row.id,
                borough_id=row.borough_id,
                source_family=row.source_family,
                coverage_status=row.coverage_status,
                gap_reason=row.gap_reason,
                freshness_status=row.freshness_status,
                coverage_note=row.coverage_note,
                source_snapshot_id=row.source_snapshot_id,
                captured_at=row.captured_at,
            )
            for row in coverage_rows
        ],
        planning_history=[
            SitePlanningLinkRead(
                id=link.id,
                link_type=link.link_type,
                distance_m=round(link.distance_m, 2) if link.distance_m is not None else None,
                overlap_pct=round(link.overlap_pct, 4) if link.overlap_pct is not None else None,
                match_confidence=link.match_confidence,
                manual_verified=link.manual_verified,
                planning_application=_serialize_planning_application(link.planning_application),
            )
            for link in sorted(
                site.planning_links,
                key=lambda item: (
                    item.match_confidence.value,
                    item.distance_m if item.distance_m is not None else 0.0,
                ),
            )
        ],
        brownfield_states=[
            BrownfieldSiteStateRead(
                id=row.id,
                borough_id=row.borough_id,
                source_snapshot_id=row.source_snapshot_id,
                external_ref=row.external_ref,
                part=row.part,
                pip_status=row.pip_status,
                tdc_status=row.tdc_status,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                raw_record_id=row.raw_record_id,
                source_url=row.source_url,
            )
            for row in brownfield_states
        ],
        policy_facts=[
            SitePolicyFactRead(
                id=fact.id,
                relation_type=fact.relation_type,
                overlap_pct=round(fact.overlap_pct, 4) if fact.overlap_pct is not None else None,
                distance_m=round(fact.distance_m, 2) if fact.distance_m is not None else None,
                importance=fact.importance,
                policy_area=_serialize_policy_area(fact.policy_area),
            )
            for fact in site.policy_facts
        ],
        constraint_facts=[
            SiteConstraintFactRead(
                id=fact.id,
                overlap_pct=round(fact.overlap_pct, 4) if fact.overlap_pct is not None else None,
                distance_m=round(fact.distance_m, 2) if fact.distance_m is not None else None,
                severity=fact.severity,
                constraint_feature=_serialize_constraint_feature(fact.constraint_feature),
            )
            for fact in site.constraint_facts
        ],
        extant_permission=extant_permission,
        evidence=evidence,
        baseline_pack=_serialize_baseline_pack(baseline_pack),
        scenarios=scenario_summaries,
    )


def _site_load_options():
    return (
        selectinload(SiteCandidate.borough),
        selectinload(SiteCandidate.listing_cluster).selectinload(ListingCluster.members),
        selectinload(SiteCandidate.current_listing).selectinload(ListingItem.source),
        selectinload(SiteCandidate.current_listing)
        .selectinload(ListingItem.documents)
        .selectinload(ListingDocument.asset),
        selectinload(SiteCandidate.current_listing)
        .selectinload(ListingItem.snapshots)
        .selectinload(ListingSnapshot.source_snapshot)
        .selectinload(SourceSnapshot.raw_assets),
        selectinload(SiteCandidate.geometry_revisions),
        selectinload(SiteCandidate.lpa_links).selectinload(SiteLpaLink.lpa),
        selectinload(SiteCandidate.title_links).selectinload(SiteTitleLink.title_polygon),
        selectinload(SiteCandidate.market_events),
        selectinload(SiteCandidate.planning_links)
        .selectinload(SitePlanningLink.planning_application)
        .selectinload(PlanningApplication.documents)
        .selectinload(PlanningApplicationDocument.asset),
        selectinload(SiteCandidate.policy_facts).selectinload(SitePolicyFact.policy_area),
        selectinload(SiteCandidate.constraint_facts).selectinload(
            SiteConstraintFact.constraint_feature
        ),
        selectinload(SiteCandidate.scenarios)
        .selectinload(SiteScenario.reviews),
        selectinload(SiteCandidate.scenarios).selectinload(SiteScenario.geometry_revision),
    )


def _serialize_site_listing(listing_item: ListingItem | None) -> SiteListingSummaryRead | None:
    if listing_item is None:
        return None
    snapshot = _current_snapshot(listing_item)
    return SiteListingSummaryRead(
        id=listing_item.id,
        headline=snapshot.headline if snapshot else None,
        canonical_url=listing_item.canonical_url,
        latest_status=listing_item.latest_status,
        guide_price_gbp=snapshot.guide_price_gbp if snapshot else None,
        price_basis_type=(
            snapshot.price_basis_type if snapshot is not None else PriceBasisType.UNKNOWN
        ),
        address_text=snapshot.address_text if snapshot else None,
        source_name=listing_item.source.name,
    )


def _serialize_planning_application(application: PlanningApplication) -> PlanningApplicationRead:
    return PlanningApplicationRead(
        id=application.id,
        borough_id=application.borough_id,
        source_system=application.source_system,
        source_snapshot_id=application.source_snapshot_id,
        external_ref=application.external_ref,
        application_type=application.application_type,
        proposal_description=application.proposal_description,
        valid_date=application.valid_date,
        decision_date=application.decision_date,
        decision=application.decision,
        decision_type=application.decision_type,
        status=application.status,
        route_normalized=application.route_normalized,
        units_proposed=application.units_proposed,
        source_priority=application.source_priority,
        source_url=application.source_url,
        site_geom_4326=application.site_geom_4326,
        site_point_4326=application.site_point_4326,
        raw_record_json=application.raw_record_json,
        documents=[
            PlanningApplicationDocumentRead(
                id=document.id,
                asset_id=document.asset_id,
                doc_type=document.doc_type,
                doc_url=document.doc_url,
                asset=serialize_raw_asset(document.asset) if document.asset is not None else None,
            )
            for document in application.documents
        ],
    )


def _serialize_policy_area(area: PolicyArea) -> PolicyAreaRead:
    return PolicyAreaRead(
        id=area.id,
        borough_id=area.borough_id,
        policy_family=area.policy_family,
        policy_code=area.policy_code,
        name=area.name,
        geom_4326=area.geom_4326,
        legal_effective_from=area.legal_effective_from,
        legal_effective_to=area.legal_effective_to,
        source_snapshot_id=area.source_snapshot_id,
        source_class=area.source_class,
        source_url=area.source_url,
    )


def _serialize_constraint_feature(
    feature: PlanningConstraintFeature,
) -> PlanningConstraintFeatureRead:
    return PlanningConstraintFeatureRead(
        id=feature.id,
        feature_family=feature.feature_family,
        feature_subtype=feature.feature_subtype,
        authority_level=feature.authority_level,
        geom_4326=feature.geom_4326,
        legal_status=feature.legal_status,
        effective_from=feature.effective_from,
        effective_to=feature.effective_to,
        source_snapshot_id=feature.source_snapshot_id,
        source_class=feature.source_class,
        source_url=feature.source_url,
    )


def _serialize_baseline_pack(pack: BoroughBaselinePack | None) -> BoroughBaselinePackRead | None:
    if pack is None:
        return None
    return BoroughBaselinePackRead(
        id=pack.id,
        borough_id=pack.borough_id,
        version=pack.version,
        status=pack.status,
        freshness_status=pack.freshness_status,
        signed_off_by=pack.signed_off_by,
        signed_off_at=pack.signed_off_at,
        pack_json=pack.pack_json,
        source_snapshot_id=pack.source_snapshot_id,
        rulepacks=[
            BoroughRulepackRead(
                id=rule.id,
                template_key=rule.template_key,
                status=rule.status,
                freshness_status=rule.freshness_status,
                source_snapshot_id=rule.source_snapshot_id,
                effective_from=rule.effective_from,
                effective_to=rule.effective_to,
                rule_json=rule.rule_json,
                citations_complete=_rulepack_citations_complete(rule.rule_json),
            )
            for rule in pack.rulepacks
        ],
    )


def _current_snapshot(listing_item: ListingItem) -> ListingSnapshot | None:
    if listing_item.current_snapshot_id is None:
        return listing_item.snapshots[0] if listing_item.snapshots else None
    return next(
        (
            snapshot
            for snapshot in listing_item.snapshots
            if snapshot.id == listing_item.current_snapshot_id
        ),
        None,
    )


def _source_snapshots_for_listing(listing_item: ListingItem | None) -> list[SourceSnapshot]:
    if listing_item is None:
        return []
    source_snapshots = {
        snapshot.source_snapshot.id: snapshot.source_snapshot
        for snapshot in listing_item.snapshots
        if snapshot.source_snapshot is not None
    }
    return list(source_snapshots.values())


def _flatten_warnings(warning_json: dict[str, object] | None) -> list[SiteWarningRead]:
    if not warning_json:
        return []

    flattened: list[SiteWarningRead] = []
    for category_value in warning_json.values():
        if not isinstance(category_value, list):
            continue
        for item in category_value:
            if not isinstance(item, dict):
                continue
            code = item.get("code")
            message = item.get("message")
            if isinstance(code, str) and isinstance(message, str):
                flattened.append(SiteWarningRead(code=code, message=message))
    return flattened


def _rulepack_citations_complete(rule_json: dict[str, object] | None) -> bool:
    if not isinstance(rule_json, dict):
        return False
    citations = rule_json.get("citations")
    if not isinstance(citations, list) or not citations:
        return False
    for citation in citations:
        if not isinstance(citation, dict):
            return False
        if not isinstance(citation.get("label"), str) or not citation.get("label"):
            return False
        if not isinstance(citation.get("source_family"), str) or not citation.get("source_family"):
            return False
    return True
