from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import PriceBasisType
from landintel.domain.models import (
    ListingCluster,
    ListingDocument,
    ListingItem,
    ListingSnapshot,
    SiteCandidate,
    SiteLpaLink,
    SiteTitleLink,
    SourceSnapshot,
)
from landintel.domain.schemas import (
    SiteClusterSummaryRead,
    SiteDetailRead,
    SiteGeometryRead,
    SiteGeometryRevisionRead,
    SiteListingSummaryRead,
    SiteListResponse,
    SiteLpaLinkRead,
    SiteMarketEventRead,
    SiteSummaryRead,
    SiteTitleLinkRead,
    SiteWarningRead,
)
from landintel.services.listings_readback import (
    serialize_listing_document,
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
    return serialize_site_detail(site)


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


def serialize_site_detail(site: SiteCandidate) -> SiteDetailRead:
    summary = serialize_site_summary(site)
    current_listing = site.current_listing
    source_snapshots = _source_snapshots_for_listing(current_listing)
    documents = current_listing.documents if current_listing is not None else []
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
        source_documents=[serialize_listing_document(document) for document in documents],
        source_snapshots=[serialize_source_snapshot(snapshot) for snapshot in source_snapshots],
    )


def _site_load_options():
    return (
        selectinload(SiteCandidate.borough),
        selectinload(SiteCandidate.listing_cluster).selectinload(ListingCluster.members),
        selectinload(SiteCandidate.current_listing).selectinload(ListingItem.source),
        selectinload(SiteCandidate.current_listing).selectinload(ListingItem.documents).selectinload(ListingDocument.asset),
        selectinload(SiteCandidate.current_listing)
        .selectinload(ListingItem.snapshots)
        .selectinload(ListingSnapshot.source_snapshot)
        .selectinload(SourceSnapshot.raw_assets),
        selectinload(SiteCandidate.geometry_revisions),
        selectinload(SiteCandidate.lpa_links).selectinload(SiteLpaLink.lpa),
        selectinload(SiteCandidate.title_links).selectinload(SiteTitleLink.title_polygon),
        selectinload(SiteCandidate.market_events),
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
