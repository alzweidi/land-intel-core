from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from landintel.domain.enums import GeomConfidence, GeomSourceType
from landintel.domain.models import HmlrTitlePolygon
from landintel.geospatial.geometry import (
    PreparedGeometry,
    load_wkt_geometry,
    normalize_input_geometry,
)


@dataclass(slots=True)
class TitleCandidate:
    title_polygon: HmlrTitlePolygon
    score: float
    reasons: list[str]


@dataclass(slots=True)
class TitleOverlap:
    title_polygon: HmlrTitlePolygon
    overlap_pct: float
    overlap_sqm: float
    confidence: GeomConfidence


def select_title_candidates(
    *,
    title_polygons: Iterable[HmlrTitlePolygon],
    normalized_addresses: list[str],
    point_geometries_27700: list[BaseGeometry],
) -> list[TitleCandidate]:
    candidates: list[TitleCandidate] = []
    unique_addresses = [value for value in normalized_addresses if value]

    for title_polygon in title_polygons:
        score = 0.0
        reasons: list[str] = []
        title_geometry = normalize_input_geometry(
            geometry=title_polygon_geom(title_polygon),
            source_epsg=27700,
            source_type=GeomSourceType.TITLE_UNION,
        ).geom_27700

        if title_polygon.normalized_address and unique_addresses:
            address_score, address_reason = _score_address_match(
                listing_addresses=unique_addresses,
                title_address=title_polygon.normalized_address,
            )
            score = max(score, address_score)
            if address_reason:
                reasons.append(address_reason)

        if point_geometries_27700:
            point_score = max(
                (
                    1.0
                    if point_geometry.intersects(title_geometry)
                    else 0.0
                )
                for point_geometry in point_geometries_27700
            )
            if point_score:
                score = max(score, point_score)
                reasons.append("listing_point_intersects_title")

        if score >= 0.75:
            candidates.append(
                TitleCandidate(
                    title_polygon=title_polygon,
                    score=score,
                    reasons=reasons,
                )
            )

    return sorted(candidates, key=lambda item: (-item.score, item.title_polygon.title_number))


def build_title_union_geometry(
    title_candidates: Iterable[TitleCandidate],
) -> PreparedGeometry | None:
    title_geometries = [
        title_polygon_geom(candidate.title_polygon)
        for candidate in title_candidates
    ]
    if not title_geometries:
        return None
    union_geometry = unary_union(title_geometries)
    return normalize_input_geometry(
        geometry=union_geometry,
        source_epsg=27700,
        source_type=GeomSourceType.TITLE_UNION,
        confidence=GeomConfidence.MEDIUM,
    )


def compute_title_overlaps(
    *,
    site_geometry_27700: BaseGeometry,
    title_polygons: Iterable[HmlrTitlePolygon],
) -> list[TitleOverlap]:
    site_area_sqm = (
        float(site_geometry_27700.area)
        if site_geometry_27700.geom_type in {"Polygon", "MultiPolygon"}
        else 0.0
    )
    overlaps: list[TitleOverlap] = []

    for title_polygon in title_polygons:
        title_geometry = title_polygon_geom(title_polygon)
        if site_area_sqm > 0:
            intersection = site_geometry_27700.intersection(title_geometry)
            overlap_sqm = float(intersection.area) if not intersection.is_empty else 0.0
            if overlap_sqm <= 0:
                continue
            overlap_pct = overlap_sqm / site_area_sqm
        else:
            if not site_geometry_27700.intersects(title_geometry):
                continue
            overlap_sqm = 0.0
            overlap_pct = 1.0

        overlaps.append(
            TitleOverlap(
                title_polygon=title_polygon,
                overlap_pct=overlap_pct,
                overlap_sqm=overlap_sqm,
                confidence=_confidence_from_overlap(overlap_pct),
            )
        )

    return sorted(overlaps, key=lambda item: (-item.overlap_pct, item.title_polygon.title_number))


def title_polygon_geom(title_polygon: HmlrTitlePolygon) -> BaseGeometry:
    return normalize_input_geometry(
        geometry=load_wkt_geometry(title_polygon.geom_27700),
        source_epsg=27700,
        source_type=GeomSourceType.TITLE_UNION,
    ).geom_27700


def _score_address_match(
    *,
    listing_addresses: list[str],
    title_address: str,
) -> tuple[float, str | None]:
    for listing_address in listing_addresses:
        if listing_address == title_address:
            return 0.95, "listing_address_exact_title_address"
        if listing_address in title_address or title_address in listing_address:
            return 0.8, "listing_address_partial_title_address"
    return 0.0, None


def _confidence_from_overlap(overlap_pct: float) -> GeomConfidence:
    if overlap_pct >= 0.8:
        return GeomConfidence.HIGH
    if overlap_pct >= 0.35:
        return GeomConfidence.MEDIUM
    if overlap_pct > 0:
        return GeomConfidence.LOW
    return GeomConfidence.INSUFFICIENT
