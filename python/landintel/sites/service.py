from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import (
    GeomConfidence,
    GeomSourceType,
    SiteMarketEventType,
    SiteStatus,
)
from landintel.domain.models import (
    AuditEvent,
    HmlrTitlePolygon,
    ListingCluster,
    ListingClusterMember,
    ListingDocument,
    ListingItem,
    ListingSnapshot,
    LpaBoundary,
    SiteCandidate,
    SiteGeometryRevision,
    SiteLpaLink,
    SiteMarketEvent,
    SiteTitleLink,
)
from landintel.geospatial.geometry import (
    PreparedGeometry,
    build_bbox_geometry_from_bounds,
    build_point_geometry,
    derive_site_status,
    geometry_warning_dicts,
    load_wkt_geometry,
    normalize_geojson_geometry,
)
from landintel.geospatial.title_linkage import (
    TitleCandidate,
    build_title_union_geometry,
    compute_title_overlaps,
    select_title_candidates,
)
from landintel.planning.enrich import refresh_site_planning_context

SITE_NAMESPACE = uuid.UUID("f87417d2-b904-4724-94a3-7f5f18c41540")


class SiteBuildError(ValueError):
    pass


@dataclass(slots=True)
class ClusterSpatialHints:
    normalized_addresses: list[str]
    point_geometries_27700: list[Any]
    current_listing: ListingItem
    current_snapshot: ListingSnapshot | None


def build_or_refresh_site_from_cluster(
    *,
    session: Session,
    cluster_id: uuid.UUID,
    requested_by: str | None,
) -> SiteCandidate:
    cluster = session.execute(
        select(ListingCluster)
        .where(ListingCluster.id == cluster_id)
        .options(
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.source),
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.documents)
            .selectinload(ListingDocument.asset),
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.snapshots),
        )
    ).scalar_one_or_none()
    if cluster is None:
        raise SiteBuildError(f"Listing cluster '{cluster_id}' was not found.")

    hints = _build_cluster_hints(cluster)
    draft_geometry = _derive_cluster_geometry(session=session, cluster=cluster, hints=hints)
    site = session.execute(
        select(SiteCandidate)
        .where(SiteCandidate.listing_cluster_id == cluster.id)
        .options(selectinload(SiteCandidate.geometry_revisions))
    ).scalar_one_or_none()

    is_new = site is None
    before_payload = None if site is None else _site_audit_payload(site)
    if site is None:
        site = SiteCandidate(
            id=uuid.uuid5(SITE_NAMESPACE, f"site:{cluster.id}"),
            listing_cluster_id=cluster.id,
            display_name=_display_name_from_listing(hints.current_snapshot, hints.current_listing),
            geom_27700=draft_geometry.geom_27700_wkt,
            geom_4326=draft_geometry.geom_4326,
            geom_hash=draft_geometry.geom_hash,
            geom_source_type=draft_geometry.geom_source_type,
            geom_confidence=draft_geometry.geom_confidence,
            site_area_sqm=draft_geometry.area_sqm,
        )
        session.add(site)
        session.flush()
    else:
        if site.geom_source_type != GeomSourceType.ANALYST_DRAWN:
            site.geom_27700 = draft_geometry.geom_27700_wkt
            site.geom_4326 = draft_geometry.geom_4326
            site.geom_hash = draft_geometry.geom_hash
            site.geom_source_type = draft_geometry.geom_source_type
            site.geom_confidence = draft_geometry.geom_confidence
            site.site_area_sqm = draft_geometry.area_sqm
        else:
            draft_geometry = _prepared_from_site(site)
    site.display_name = _display_name_from_listing(hints.current_snapshot, hints.current_listing)
    site.current_listing_id = hints.current_listing.id
    if hints.current_snapshot is not None:
        site.current_price_gbp = hints.current_snapshot.guide_price_gbp
        site.current_price_basis_type = hints.current_snapshot.price_basis_type

    geometry_warnings = geometry_warning_dicts(draft_geometry.warnings)
    site.warning_json = {**site.warning_json, "geometry": geometry_warnings}

    _ensure_geometry_revision(
        session=session,
        site=site,
        prepared=draft_geometry,
        reason=(
            "Initial draft geometry from listing-cluster evidence."
            if is_new
            else "Cluster refresh geometry."
        ),
        created_by=requested_by or "system",
        raw_asset_id=_raw_asset_id_from_listing(hints.current_snapshot),
        deterministic=True,
    )

    refresh_site_links_and_status(session=session, site=site)
    _upsert_market_event(session=session, site=site, current_snapshot=hints.current_snapshot)
    refresh_site_planning_context(
        session=session,
        site=site,
        requested_by=requested_by or "system",
    )
    session.flush()

    _record_audit_event(
        session=session,
        action="site_created" if is_new else "site_refreshed",
        entity_type="site_candidate",
        entity_id=str(site.id),
        before_json=before_payload,
        after_json=_site_audit_payload(site),
    )
    return site


def save_site_geometry_revision(
    *,
    session: Session,
    site_id: uuid.UUID,
    geom_4326: dict[str, Any],
    source_type: GeomSourceType,
    confidence: GeomConfidence | None,
    reason: str | None,
    created_by: str | None,
    raw_asset_id: uuid.UUID | None,
) -> SiteCandidate:
    site = session.execute(
        select(SiteCandidate)
        .where(SiteCandidate.id == site_id)
        .options(
            selectinload(SiteCandidate.geometry_revisions),
            selectinload(SiteCandidate.title_links),
            selectinload(SiteCandidate.lpa_links),
        )
    ).scalar_one_or_none()
    if site is None:
        raise SiteBuildError(f"Site '{site_id}' was not found.")

    before_payload = _site_audit_payload(site)
    prepared = normalize_geojson_geometry(
        geometry_payload=geom_4326,
        source_epsg=4326,
        source_type=source_type,
        confidence=confidence or _default_analyst_confidence(source_type),
    )
    site.geom_27700 = prepared.geom_27700_wkt
    site.geom_4326 = prepared.geom_4326
    site.geom_hash = prepared.geom_hash
    site.geom_source_type = prepared.geom_source_type
    site.geom_confidence = prepared.geom_confidence
    site.site_area_sqm = prepared.area_sqm

    _ensure_geometry_revision(
        session=session,
        site=site,
        prepared=prepared,
        reason=reason or "Analyst geometry edit.",
        created_by=created_by or "analyst",
        raw_asset_id=raw_asset_id,
        deterministic=False,
    )

    geometry_warnings = geometry_warning_dicts(prepared.warnings)
    site.warning_json = {**site.warning_json, "geometry": geometry_warnings}
    refresh_site_links_and_status(session=session, site=site)
    refresh_site_planning_context(
        session=session,
        site=site,
        requested_by=created_by or "analyst",
    )
    session.flush()

    _record_audit_event(
        session=session,
        action="geometry_changed",
        entity_type="site_candidate",
        entity_id=str(site.id),
        before_json=before_payload,
        after_json=_site_audit_payload(site),
    )
    return site


def refresh_site_lpa_links(*, session: Session, site: SiteCandidate) -> list[dict[str, str]]:
    session.execute(delete(SiteLpaLink).where(SiteLpaLink.site_id == site.id))
    session.flush()

    geometry = load_wkt_geometry(site.geom_27700)
    boundaries = session.execute(select(LpaBoundary)).scalars().all()
    warnings: list[dict[str, str]] = []
    overlaps: list[tuple[LpaBoundary, float, float]] = []

    is_polygonal = geometry.geom_type in {"Polygon", "MultiPolygon"} and site.site_area_sqm > 0
    for boundary in boundaries:
        boundary_geometry = load_wkt_geometry(boundary.geom_27700)
        if is_polygonal:
            intersection = geometry.intersection(boundary_geometry)
            overlap_sqm = float(intersection.area) if not intersection.is_empty else 0.0
            if overlap_sqm <= 0:
                continue
            overlap_pct = overlap_sqm / site.site_area_sqm
        else:
            if not geometry.intersects(boundary_geometry):
                continue
            overlap_sqm = 0.0
            overlap_pct = 1.0
        overlaps.append((boundary, overlap_pct, overlap_sqm))

    if not overlaps:
        site.borough_id = None
        return [
            {
                "code": "LPA_UNRESOLVED",
                "message": (
                    "No borough/LPA boundary intersected the current site geometry."
                ),
            }
        ]

    overlaps.sort(key=lambda item: (item[2], item[1], item[0].name), reverse=True)
    primary_boundary = overlaps[0][0]
    secondary_overlap_pct = sum(item[1] for item in overlaps[1:])
    secondary_overlap_sqm = sum(item[2] for item in overlaps[1:])

    for index, (boundary, overlap_pct, overlap_sqm) in enumerate(overlaps):
        session.add(
            SiteLpaLink(
                id=uuid.uuid5(SITE_NAMESPACE, f"site-lpa:{site.id}:{boundary.id}"),
                site_id=site.id,
                lpa_id=boundary.id,
                overlap_pct=overlap_pct,
                overlap_sqm=overlap_sqm,
                is_primary=index == 0,
            )
        )

    if len(overlaps) == 1 or not is_polygonal:
        site.borough_id = primary_boundary.id
        return warnings

    if secondary_overlap_pct < 0.05 and secondary_overlap_sqm < 100.0:
        site.borough_id = primary_boundary.id
        warnings.append(
            {
                "code": "CROSS_LPA_TRIVIAL",
                "message": (
                    "Site overlaps a secondary LPA only trivially; "
                    "majority borough retained and flagged."
                ),
            }
        )
        return warnings

    site.borough_id = None
    warnings.append(
        {
            "code": "CROSS_LPA_MATERIAL",
            "message": (
                "Site crosses multiple LPAs materially and requires "
                "analyst clipping or confirmation."
            ),
        }
    )
    return warnings


def refresh_site_title_links(*, session: Session, site: SiteCandidate) -> list[dict[str, str]]:
    session.execute(delete(SiteTitleLink).where(SiteTitleLink.site_id == site.id))
    session.flush()

    geometry = load_wkt_geometry(site.geom_27700)
    title_polygons = session.execute(select(HmlrTitlePolygon)).scalars().all()
    overlaps = compute_title_overlaps(site_geometry_27700=geometry, title_polygons=title_polygons)
    warnings: list[dict[str, str]] = []

    for overlap in overlaps:
        session.add(
            SiteTitleLink(
                id=uuid.uuid5(
                    SITE_NAMESPACE,
                    f"site-title:{site.id}:{overlap.title_polygon.title_number}",
                ),
                site_id=site.id,
                title_polygon_id=overlap.title_polygon.id,
                title_number=overlap.title_polygon.title_number,
                source_snapshot_id=overlap.title_polygon.source_snapshot_id,
                overlap_pct=overlap.overlap_pct,
                overlap_sqm=overlap.overlap_sqm,
                confidence=overlap.confidence,
            )
        )

    if not overlaps:
        warnings.append(
            {
                "code": "NO_TITLE_LINK",
                "message": "No HMLR INSPIRE title polygons overlapped the current site geometry.",
            }
        )
        return warnings

    warnings.append(
        {
            "code": "TITLE_LINK_INDICATIVE",
            "message": (
                "HMLR INSPIRE title polygons are indicative evidence only "
                "and not legal parcel truth."
            ),
        }
    )
    return warnings


def refresh_site_links_and_status(*, session: Session, site: SiteCandidate) -> None:
    existing = dict(site.warning_json or {})
    geometry_warnings = list(existing.get("geometry", []))
    lpa_warnings = refresh_site_lpa_links(session=session, site=site)
    title_warnings = refresh_site_title_links(session=session, site=site)
    site.warning_json = {
        **{
            key: value
            for key, value in existing.items()
            if key not in {"geometry", "lpa", "title"}
        },
        "geometry": geometry_warnings,
        "lpa": lpa_warnings,
        "title": title_warnings,
    }
    site.manual_review_required = bool(
        any(item["code"] == "CROSS_LPA_MATERIAL" for item in lpa_warnings)
        or site.geom_confidence in {GeomConfidence.LOW, GeomConfidence.INSUFFICIENT}
    )
    site.site_status = derive_site_status(
        geom_confidence=site.geom_confidence,
        manual_review_required=site.manual_review_required,
    )


def _build_cluster_hints(cluster: ListingCluster) -> ClusterSpatialHints:
    members = sorted(
        cluster.members,
        key=lambda member: (
            member.listing_item.last_seen_at,
            member.confidence,
            str(member.listing_item_id),
        ),
        reverse=True,
    )
    if not members:
        raise SiteBuildError("Listing cluster has no members.")

    current_listing = members[0].listing_item
    current_snapshot = _current_snapshot(current_listing)
    normalized_addresses = [
        value
        for value in (
            _current_snapshot(member.listing_item).normalized_address
            if _current_snapshot(member.listing_item) is not None
            else member.listing_item.normalized_address
            for member in members
        )
        if value
    ]

    point_geometries_27700 = []
    for member in members:
        snapshot = _current_snapshot(member.listing_item)
        if snapshot is None or snapshot.lat is None or snapshot.lon is None:
            continue
        point_geometries_27700.append(
            build_point_geometry(lat=snapshot.lat, lon=snapshot.lon).geom_27700
        )

    return ClusterSpatialHints(
        normalized_addresses=normalized_addresses,
        point_geometries_27700=point_geometries_27700,
        current_listing=current_listing,
        current_snapshot=current_snapshot,
    )


def _derive_cluster_geometry(
    *,
    session: Session,
    cluster: ListingCluster,
    hints: ClusterSpatialHints,
) -> PreparedGeometry:
    del cluster
    if hints.current_snapshot is not None:
        raw_record = hints.current_snapshot.raw_record_json
        if isinstance(raw_record.get("geometry_4326"), dict):
            return normalize_geojson_geometry(
                geometry_payload=raw_record["geometry_4326"],
                source_epsg=4326,
                source_type=GeomSourceType.SOURCE_POLYGON,
            )
        bounds = raw_record.get("bbox_4326")
        if isinstance(bounds, list) and len(bounds) == 4:
            min_lon, min_lat, max_lon, max_lat = [float(value) for value in bounds]
            return build_bbox_geometry_from_bounds(
                min_lon=min_lon,
                min_lat=min_lat,
                max_lon=max_lon,
                max_lat=max_lat,
            )

    title_candidates = _cluster_title_candidates(session=session, hints=hints)
    title_union = build_title_union_geometry(title_candidates)
    if title_union is not None:
        return title_union

    if (
        hints.current_snapshot is not None
        and hints.current_snapshot.lat is not None
        and hints.current_snapshot.lon is not None
    ):
        return build_point_geometry(lat=hints.current_snapshot.lat, lon=hints.current_snapshot.lon)

    raise SiteBuildError(
        "No explicit geometry, title linkage, or point evidence was available for this cluster."
    )


def _cluster_title_candidates(
    *,
    session: Session,
    hints: ClusterSpatialHints,
) -> list[TitleCandidate]:
    title_polygons = session.execute(select(HmlrTitlePolygon)).scalars().all()
    return select_title_candidates(
        title_polygons=title_polygons,
        normalized_addresses=hints.normalized_addresses,
        point_geometries_27700=hints.point_geometries_27700,
    )


def _ensure_geometry_revision(
    *,
    session: Session,
    site: SiteCandidate,
    prepared: PreparedGeometry,
    reason: str,
    created_by: str | None,
    raw_asset_id: uuid.UUID | None,
    deterministic: bool,
) -> None:
    if deterministic and any(
        revision.geom_hash == prepared.geom_hash
        and revision.source_type == prepared.geom_source_type
        for revision in site.geometry_revisions
    ):
        return

    revision_id = (
        uuid.uuid5(
            SITE_NAMESPACE,
            (
                "site-revision:"
                f"{site.id}:{prepared.geom_hash}:{prepared.geom_source_type}:"
                f"{created_by or 'system'}"
            ),
        )
        if deterministic
        else uuid.uuid4()
    )
    existing = session.get(SiteGeometryRevision, revision_id)
    if existing is not None:
        return

    session.add(
        SiteGeometryRevision(
            id=revision_id,
            site_id=site.id,
            geom_27700=prepared.geom_27700_wkt,
            geom_4326=prepared.geom_4326,
            geom_hash=prepared.geom_hash,
            source_type=prepared.geom_source_type,
            confidence=prepared.geom_confidence,
            site_area_sqm=prepared.area_sqm,
            reason=reason,
            created_by=created_by,
            raw_asset_id=raw_asset_id,
            warning_json={"geometry": geometry_warning_dicts(prepared.warnings)},
        )
    )


def _upsert_market_event(
    *,
    session: Session,
    site: SiteCandidate,
    current_snapshot: ListingSnapshot | None,
) -> None:
    listing_item_id = site.current_listing_id
    event_at = current_snapshot.observed_at if current_snapshot is not None else site.updated_at
    event_id = uuid.uuid5(
        SITE_NAMESPACE,
        f"site-market-event:{site.id}:{listing_item_id}:{event_at.isoformat()}",
    )
    if session.get(SiteMarketEvent, event_id) is not None:
        return

    session.add(
        SiteMarketEvent(
            id=event_id,
            site_id=site.id,
            event_type=SiteMarketEventType.LISTING_EVIDENCE,
            event_at=event_at,
            price_gbp=site.current_price_gbp,
            basis_type=site.current_price_basis_type,
            listing_item_id=listing_item_id,
            notes="Derived from the current linked listing snapshot.",
        )
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


def _prepared_from_site(site: SiteCandidate) -> PreparedGeometry:
    prepared = normalize_geojson_geometry(
        geometry_payload=site.geom_4326,
        source_epsg=4326,
        source_type=site.geom_source_type,
        confidence=site.geom_confidence,
    )
    return prepared


def _display_name_from_listing(
    snapshot: ListingSnapshot | None,
    listing_item: ListingItem,
) -> str:
    if snapshot is not None and snapshot.address_text:
        return snapshot.address_text
    if snapshot is not None and snapshot.headline:
        return snapshot.headline
    return listing_item.canonical_url


def _raw_asset_id_from_listing(snapshot: ListingSnapshot | None) -> uuid.UUID | None:
    if snapshot is None:
        return None
    return snapshot.map_asset_id or snapshot.brochure_asset_id


def _default_analyst_confidence(source_type: GeomSourceType) -> GeomConfidence:
    if source_type == GeomSourceType.ANALYST_DRAWN:
        return GeomConfidence.HIGH
    if source_type == GeomSourceType.APPROXIMATE_BBOX:
        return GeomConfidence.LOW
    return GeomConfidence.MEDIUM


def _record_audit_event(
    *,
    session: Session,
    action: str,
    entity_type: str,
    entity_id: str,
    before_json: dict[str, Any] | None,
    after_json: dict[str, Any] | None,
) -> None:
    session.add(
        AuditEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=before_json,
            after_json=after_json,
        )
    )


def _site_audit_payload(site: SiteCandidate) -> dict[str, Any]:
    return {
        "site_id": str(site.id),
        "listing_cluster_id": str(site.listing_cluster_id),
        "display_name": site.display_name,
        "borough_id": site.borough_id,
        "geom_hash": site.geom_hash,
        "geom_source_type": site.geom_source_type.value,
        "geom_confidence": site.geom_confidence.value,
        "site_area_sqm": site.site_area_sqm,
        "current_listing_id": str(site.current_listing_id) if site.current_listing_id else None,
        "site_status": (
            site.site_status.value
            if isinstance(site.site_status, SiteStatus)
            else str(site.site_status)
        ),
        "manual_review_required": site.manual_review_required,
    }
