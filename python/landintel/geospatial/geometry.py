from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pyproj import Transformer
from shapely import force_2d, make_valid, normalize
from shapely.geometry import GeometryCollection, Point, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.wkt import dumps as dumps_wkt
from shapely.wkt import loads as loads_wkt

from landintel.domain.enums import GeomConfidence, GeomSourceType, SiteStatus

CANONICAL_EPSG = 27700
DISPLAY_EPSG = 4326
TRIVIAL_CROSS_LPA_OVERLAP_PCT = 0.05
TRIVIAL_CROSS_LPA_OVERLAP_SQM = 100.0


class GeometryNormalizationError(ValueError):
    pass


@dataclass(slots=True)
class GeometryWarning:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(slots=True)
class PreparedGeometry:
    geom_27700: BaseGeometry
    geom_27700_wkt: str
    geom_4326: dict[str, Any]
    geom_hash: str
    area_sqm: float
    geom_source_type: GeomSourceType
    geom_confidence: GeomConfidence
    warnings: list[GeometryWarning] = field(default_factory=list)


def warning(code: str, message: str) -> GeometryWarning:
    return GeometryWarning(code=code, message=message)


@lru_cache
def _transformer(from_epsg: int, to_epsg: int) -> Transformer:
    return Transformer.from_crs(
        f"EPSG:{from_epsg}",
        f"EPSG:{to_epsg}",
        always_xy=True,
    )


def transform_geometry(geometry: BaseGeometry, *, from_epsg: int, to_epsg: int) -> BaseGeometry:
    if from_epsg == to_epsg:
        return geometry
    return transform(_transformer(from_epsg, to_epsg).transform, geometry)


def load_geojson_geometry(geometry_payload: dict[str, Any]) -> BaseGeometry:
    try:
        geometry = shape(geometry_payload)
    except Exception as exc:  # pragma: no cover - defensive only
        raise GeometryNormalizationError("Invalid geometry payload.") from exc
    if geometry.is_empty:
        raise GeometryNormalizationError("Geometry payload is empty.")
    return geometry


def load_wkt_geometry(geometry_wkt: str) -> BaseGeometry:
    try:
        geometry = loads_wkt(geometry_wkt)
    except Exception as exc:  # pragma: no cover - defensive only
        raise GeometryNormalizationError("Invalid geometry WKT.") from exc
    if geometry.is_empty:
        raise GeometryNormalizationError("Geometry WKT is empty.")
    return geometry


def geometry_to_display_geojson(geometry_27700: BaseGeometry) -> dict[str, Any]:
    display_geometry = transform_geometry(
        geometry_27700,
        from_epsg=CANONICAL_EPSG,
        to_epsg=DISPLAY_EPSG,
    )
    return mapping(display_geometry)


def canonical_geom_hash(geometry_27700: BaseGeometry) -> str:
    normalized_geometry = normalize(geometry_27700)
    payload = json.dumps(
        _round_mapping(mapping(normalized_geometry)),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def geometry_area_sqm(geometry_27700: BaseGeometry) -> float:
    if geometry_27700.geom_type in {"Polygon", "MultiPolygon"}:
        return float(geometry_27700.area)
    return 0.0


def normalize_input_geometry(
    *,
    geometry: BaseGeometry,
    source_epsg: int,
    source_type: GeomSourceType,
    confidence: GeomConfidence | None = None,
) -> PreparedGeometry:
    geometry_27700 = transform_geometry(geometry, from_epsg=source_epsg, to_epsg=CANONICAL_EPSG)
    repaired_geometry, warnings = repair_geometry(geometry_27700)
    resolved_confidence = confidence or derive_geom_confidence(
        source_type=source_type,
        geometry_27700=repaired_geometry,
    )

    return PreparedGeometry(
        geom_27700=repaired_geometry,
        geom_27700_wkt=dumps_wkt(repaired_geometry, rounding_precision=3),
        geom_4326=geometry_to_display_geojson(repaired_geometry),
        geom_hash=canonical_geom_hash(repaired_geometry),
        area_sqm=geometry_area_sqm(repaired_geometry),
        geom_source_type=source_type,
        geom_confidence=resolved_confidence,
        warnings=warnings,
    )


def normalize_geojson_geometry(
    *,
    geometry_payload: dict[str, Any],
    source_epsg: int,
    source_type: GeomSourceType,
    confidence: GeomConfidence | None = None,
) -> PreparedGeometry:
    return normalize_input_geometry(
        geometry=load_geojson_geometry(geometry_payload),
        source_epsg=source_epsg,
        source_type=source_type,
        confidence=confidence,
    )


def normalize_wkt_geometry(
    *,
    geometry_wkt: str,
    source_type: GeomSourceType,
    confidence: GeomConfidence | None = None,
) -> PreparedGeometry:
    return normalize_input_geometry(
        geometry=load_wkt_geometry(geometry_wkt),
        source_epsg=CANONICAL_EPSG,
        source_type=source_type,
        confidence=confidence,
    )


def build_point_geometry(*, lat: float, lon: float) -> PreparedGeometry:
    return normalize_input_geometry(
        geometry=Point(lon, lat),
        source_epsg=DISPLAY_EPSG,
        source_type=GeomSourceType.POINT_ONLY,
        confidence=GeomConfidence.INSUFFICIENT,
    )


def build_bbox_geometry_from_bounds(
    *,
    min_lon: float,
    min_lat: float,
    max_lon: float,
    max_lat: float,
    source_type: GeomSourceType = GeomSourceType.APPROXIMATE_BBOX,
    confidence: GeomConfidence | None = None,
) -> PreparedGeometry:
    return normalize_input_geometry(
        geometry=box(min_lon, min_lat, max_lon, max_lat),
        source_epsg=DISPLAY_EPSG,
        source_type=source_type,
        confidence=confidence,
    )


def repair_geometry(geometry_27700: BaseGeometry) -> tuple[BaseGeometry, list[GeometryWarning]]:
    warnings: list[GeometryWarning] = []
    repaired = force_2d(geometry_27700)
    if repaired.is_empty:
        raise GeometryNormalizationError("Geometry is empty after dimensionality cleanup.")

    if not repaired.is_valid:
        repaired = make_valid(repaired)
        warnings.append(
            warning(
                "GEOMETRY_REPAIRED",
                "Input geometry was invalid and has been repaired before storage.",
            )
        )

    repaired = _collapse_collection(repaired)
    if repaired.is_empty:
        raise GeometryNormalizationError("Geometry is empty after validity repair.")
    return repaired, warnings


def derive_geom_confidence(
    *,
    source_type: GeomSourceType,
    geometry_27700: BaseGeometry,
) -> GeomConfidence:
    if geometry_27700.geom_type in {"Point", "MultiPoint"}:
        return GeomConfidence.INSUFFICIENT

    mapping_by_source = {
        GeomSourceType.SOURCE_POLYGON: GeomConfidence.HIGH,
        GeomSourceType.ANALYST_DRAWN: GeomConfidence.HIGH,
        GeomSourceType.SOURCE_MAP_DIGITISED: GeomConfidence.MEDIUM,
        GeomSourceType.TITLE_UNION: GeomConfidence.MEDIUM,
        GeomSourceType.APPROXIMATE_BBOX: GeomConfidence.LOW,
        GeomSourceType.POINT_ONLY: GeomConfidence.INSUFFICIENT,
    }
    return mapping_by_source[source_type]


def derive_site_status(
    *,
    geom_confidence: GeomConfidence,
    manual_review_required: bool,
) -> SiteStatus:
    if geom_confidence == GeomConfidence.INSUFFICIENT:
        return SiteStatus.INSUFFICIENT_GEOMETRY
    if manual_review_required or geom_confidence == GeomConfidence.LOW:
        return SiteStatus.MANUAL_REVIEW
    return SiteStatus.ACTIVE


def geometry_warning_dicts(warnings: list[GeometryWarning]) -> list[dict[str, str]]:
    return [item.as_dict() for item in warnings]


def _collapse_collection(geometry: BaseGeometry) -> BaseGeometry:
    if not isinstance(geometry, GeometryCollection):
        return geometry

    polygon_parts = [
        part
        for part in geometry.geoms
        if part.geom_type in {"Polygon", "MultiPolygon"} and not part.is_empty
    ]
    if polygon_parts:
        return unary_union(polygon_parts)

    point_parts = [
        part
        for part in geometry.geoms
        if part.geom_type in {"Point", "MultiPoint"} and not part.is_empty
    ]
    if point_parts:
        return unary_union(point_parts)

    return geometry


def _round_mapping(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, list):
        return [_round_mapping(item) for item in value]
    if isinstance(value, tuple):
        return [_round_mapping(item) for item in value]
    if isinstance(value, dict):
        return {key: _round_mapping(item) for key, item in value.items()}
    return value
