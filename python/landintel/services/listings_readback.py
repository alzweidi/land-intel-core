from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from landintel.domain.models import (
    ListingCluster,
    ListingClusterMember,
    ListingDocument,
    ListingItem,
    ListingSnapshot,
    ListingSource,
    RawAsset,
    SourceSnapshot,
)
from landintel.domain.schemas import (
    ListingClusterDetailRead,
    ListingClusterListResponse,
    ListingClusterMemberRead,
    ListingClusterSummaryRead,
    ListingDetailRead,
    ListingDocumentRead,
    ListingListResponse,
    ListingSnapshotRead,
    ListingSourceRead,
    ListingSummaryRead,
    RawAssetRead,
    SourceSnapshotRead,
)


def list_source_snapshots(session: Session, *, limit: int = 100) -> list[SourceSnapshotRead]:
    stmt = (
        select(SourceSnapshot)
        .options(selectinload(SourceSnapshot.raw_assets))
        .order_by(SourceSnapshot.acquired_at.desc())
        .limit(limit)
    )
    snapshots = list(session.execute(stmt).scalars().all())
    return [serialize_source_snapshot(snapshot) for snapshot in snapshots]


def get_source_snapshot(session: Session, *, snapshot_id: UUID) -> SourceSnapshotRead | None:
    stmt = (
        select(SourceSnapshot)
        .options(selectinload(SourceSnapshot.raw_assets))
        .where(SourceSnapshot.id == snapshot_id)
    )
    snapshot = session.execute(stmt).scalar_one_or_none()
    if snapshot is None:
        return None
    return serialize_source_snapshot(snapshot)


def list_listing_sources(session: Session) -> list[ListingSourceRead]:
    stmt = select(ListingSource).order_by(ListingSource.name.asc())
    return [ListingSourceRead.model_validate(source) for source in session.execute(stmt).scalars()]


def list_listings(
    session: Session,
    *,
    q: str | None = None,
    source: str | None = None,
    status=None,
    listing_type=None,
    min_price_gbp: int | None = None,
    max_price_gbp: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ListingListResponse:
    current_snapshot = aliased(ListingSnapshot)
    stmt = (
        select(ListingItem)
        .join(ListingSource, ListingSource.id == ListingItem.source_id)
        .join(
            current_snapshot,
            current_snapshot.id == ListingItem.current_snapshot_id,
            isouter=True,
        )
    )

    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                ListingItem.search_text.ilike(pattern),
                current_snapshot.search_text.ilike(pattern),
                current_snapshot.address_text.ilike(pattern),
            )
        )
    if source:
        stmt = stmt.where(ListingSource.name == source)
    if status:
        stmt = stmt.where(ListingItem.latest_status == status)
    if listing_type:
        stmt = stmt.where(ListingItem.listing_type == listing_type)
    if min_price_gbp is not None:
        stmt = stmt.where(current_snapshot.guide_price_gbp >= min_price_gbp)
    if max_price_gbp is not None:
        stmt = stmt.where(current_snapshot.guide_price_gbp <= max_price_gbp)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = session.execute(count_stmt).scalar_one()

    stmt = (
        stmt.options(
            selectinload(ListingItem.source),
            selectinload(ListingItem.snapshots)
            .selectinload(ListingSnapshot.source_snapshot)
            .selectinload(SourceSnapshot.raw_assets),
            selectinload(ListingItem.documents).selectinload(ListingDocument.asset),
            selectinload(ListingItem.cluster_members).selectinload(ListingClusterMember.listing_cluster),
        )
        .order_by(ListingItem.last_seen_at.desc(), ListingItem.first_seen_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = session.execute(stmt).scalars().unique().all()
    return ListingListResponse(
        items=[serialize_listing_summary(item) for item in items],
        total=total,
    )


def get_listing(session: Session, *, listing_id: UUID) -> ListingDetailRead | None:
    stmt = (
        select(ListingItem)
        .where(ListingItem.id == listing_id)
        .options(
            selectinload(ListingItem.source),
            selectinload(ListingItem.snapshots)
            .selectinload(ListingSnapshot.source_snapshot)
            .selectinload(SourceSnapshot.raw_assets),
            selectinload(ListingItem.documents).selectinload(ListingDocument.asset),
            selectinload(ListingItem.cluster_members).selectinload(ListingClusterMember.listing_cluster),
        )
    )
    listing = session.execute(stmt).scalar_one_or_none()
    if listing is None:
        return None
    return serialize_listing_detail(listing)


def list_listing_clusters(
    session: Session,
    *,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ListingClusterListResponse:
    stmt = select(ListingCluster)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = (
            stmt.join(ListingCluster.members)
            .join(ListingClusterMember.listing_item)
            .where(
                or_(
                    ListingItem.search_text.ilike(pattern),
                    ListingItem.normalized_address.ilike(pattern),
                )
            )
            .distinct()
        )

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = session.execute(count_stmt).scalar_one()
    stmt = (
        stmt.options(
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.source),
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.snapshots),
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.cluster_members)
            .selectinload(ListingClusterMember.listing_cluster),
        )
        .order_by(ListingCluster.created_at.desc(), ListingCluster.cluster_key.asc())
        .limit(limit)
        .offset(offset)
    )
    clusters = session.execute(stmt).scalars().unique().all()
    return ListingClusterListResponse(
        items=[serialize_cluster_summary(cluster) for cluster in clusters],
        total=total,
    )


def get_listing_cluster(session: Session, *, cluster_id: UUID) -> ListingClusterDetailRead | None:
    stmt = (
        select(ListingCluster)
        .where(ListingCluster.id == cluster_id)
        .options(
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.source),
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.snapshots),
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.cluster_members)
            .selectinload(ListingClusterMember.listing_cluster),
        )
    )
    cluster = session.execute(stmt).scalar_one_or_none()
    if cluster is None:
        return None
    return serialize_cluster_detail(cluster)


def serialize_raw_asset(asset: RawAsset) -> RawAssetRead:
    return RawAssetRead.model_validate(asset)


def serialize_source_snapshot(snapshot: SourceSnapshot) -> SourceSnapshotRead:
    return SourceSnapshotRead(
        id=snapshot.id,
        source_family=snapshot.source_family,
        source_name=snapshot.source_name,
        source_uri=snapshot.source_uri,
        acquired_at=snapshot.acquired_at,
        effective_from=snapshot.effective_from,
        effective_to=snapshot.effective_to,
        schema_hash=snapshot.schema_hash,
        content_hash=snapshot.content_hash,
        coverage_note=snapshot.coverage_note,
        freshness_status=snapshot.freshness_status,
        parse_status=snapshot.parse_status,
        parse_error_text=snapshot.parse_error_text,
        manifest_json=snapshot.manifest_json,
        raw_assets=[serialize_raw_asset(asset) for asset in snapshot.raw_assets],
    )


def serialize_listing_snapshot(snapshot: ListingSnapshot) -> ListingSnapshotRead:
    return ListingSnapshotRead(
        id=snapshot.id,
        source_snapshot_id=snapshot.source_snapshot_id,
        observed_at=snapshot.observed_at,
        headline=snapshot.headline,
        description_text=snapshot.description_text,
        guide_price_gbp=snapshot.guide_price_gbp,
        price_basis_type=snapshot.price_basis_type,
        status=snapshot.status,
        auction_date=snapshot.auction_date,
        address_text=snapshot.address_text,
        lat=snapshot.lat,
        lon=snapshot.lon,
        brochure_asset=(
            serialize_raw_asset(snapshot.brochure_asset)
            if snapshot.brochure_asset
            else None
        ),
        map_asset=serialize_raw_asset(snapshot.map_asset) if snapshot.map_asset else None,
        raw_record_json=snapshot.raw_record_json,
    )


def serialize_listing_document(document: ListingDocument) -> ListingDocumentRead:
    return ListingDocumentRead(
        id=document.id,
        asset_id=document.asset_id,
        doc_type=document.doc_type,
        page_count=document.page_count,
        extraction_status=document.extraction_status,
        extracted_text=document.extracted_text,
        asset=serialize_raw_asset(document.asset),
    )


def serialize_listing_summary(item: ListingItem) -> ListingSummaryRead:
    current_snapshot = _current_snapshot_for(item)
    member = item.cluster_members[0] if item.cluster_members else None
    return ListingSummaryRead(
        id=item.id,
        source_id=item.source_id,
        source_name=item.source.name,
        source_listing_id=item.source_listing_id,
        canonical_url=item.canonical_url,
        listing_type=item.listing_type,
        first_seen_at=item.first_seen_at,
        last_seen_at=item.last_seen_at,
        latest_status=item.latest_status,
        current_snapshot_id=item.current_snapshot_id,
        current_snapshot=serialize_listing_snapshot(current_snapshot) if current_snapshot else None,
        normalized_address=item.normalized_address,
        cluster_id=member.listing_cluster_id if member else None,
        cluster_status=member.listing_cluster.cluster_status if member else None,
        cluster_confidence=member.confidence if member else None,
    )


def serialize_listing_detail(item: ListingItem) -> ListingDetailRead:
    source_snapshots = {
        snapshot.source_snapshot.id: snapshot.source_snapshot
        for snapshot in item.snapshots
        if snapshot.source_snapshot is not None
    }
    summary = serialize_listing_summary(item)
    return ListingDetailRead(
        **summary.model_dump(),
        snapshots=[serialize_listing_snapshot(snapshot) for snapshot in item.snapshots],
        documents=[serialize_listing_document(document) for document in item.documents],
        source_snapshots=[
            serialize_source_snapshot(snapshot) for snapshot in source_snapshots.values()
        ],
    )


def serialize_cluster_summary(cluster: ListingCluster) -> ListingClusterSummaryRead:
    member_items = [member.listing_item for member in _sorted_members(cluster.members)]
    return ListingClusterSummaryRead(
        id=cluster.id,
        cluster_key=cluster.cluster_key,
        cluster_status=cluster.cluster_status,
        created_at=cluster.created_at,
        member_count=len(member_items),
        members=[serialize_listing_summary(item) for item in member_items],
    )


def serialize_cluster_detail(cluster: ListingCluster) -> ListingClusterDetailRead:
    return ListingClusterDetailRead(
        id=cluster.id,
        cluster_key=cluster.cluster_key,
        cluster_status=cluster.cluster_status,
        created_at=cluster.created_at,
        members=[
            ListingClusterMemberRead(
                id=member.id,
                listing_item_id=member.listing_item_id,
                confidence=member.confidence,
                rules_json=member.rules_json,
                created_at=member.created_at,
                listing=serialize_listing_summary(member.listing_item),
            )
            for member in _sorted_members(cluster.members)
        ],
    )


def _current_snapshot_for(item: ListingItem) -> ListingSnapshot | None:
    if item.current_snapshot_id is None:
        return item.snapshots[0] if item.snapshots else None
    return next(
        (
            snapshot
            for snapshot in item.snapshots
            if snapshot.id == item.current_snapshot_id
        ),
        None,
    )


def _sorted_members(members: Sequence[ListingClusterMember]) -> list[ListingClusterMember]:
    return sorted(
        members,
        key=lambda member: (
            member.listing_item.last_seen_at,
            str(member.listing_item_id),
        ),
        reverse=True,
    )
