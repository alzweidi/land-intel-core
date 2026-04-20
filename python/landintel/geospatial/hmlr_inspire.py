from __future__ import annotations

import hashlib
import io
import uuid
import xml.etree.ElementTree as ET
import zipfile
from functools import lru_cache
from typing import Final

import cloudscraper
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.config import get_settings
from landintel.domain.enums import (
    GeomConfidence,
    GeomSourceType,
    SourceFreshnessStatus,
    SourceParseStatus,
)
from landintel.domain.models import HmlrTitlePolygon, RawAsset, SourceSnapshot
from landintel.geospatial.geometry import build_point_geometry, normalize_input_geometry
from landintel.geospatial.reference_data import REFERENCE_NAMESPACE
from landintel.storage.factory import build_storage

HMLR_INSPIRE_NAMESPACE = uuid.UUID("48d2e6bc-4f4f-4d01-a238-a359a2e7577a")
HMLR_INSPIRE_DOWNLOAD_BASE_URL: Final = (
    "https://use-land-property-data.service.gov.uk/datasets/inspire/download"
)
GML_NAMESPACES = {
    "LR": "www.landregistry.gov.uk",
    "gml": "http://www.opengis.net/gml/3.2",
}


def maybe_import_title_union_for_listing_point(
    *,
    session: Session,
    authority_name: str | None,
    lat: float | None,
    lon: float | None,
    requested_by: str | None,
) -> object | None:
    settings = get_settings()
    if not settings.real_data_mode:
        return None
    if authority_name is None or lat is None or lon is None:
        return None

    authority_label = _normalize_authority_label(authority_name)
    if authority_label is None:
        return None

    point_geometry = build_point_geometry(lat=lat, lon=lon).geom_27700
    download_url = _download_url_for_authority(authority_label)
    zip_bytes = _download_hmlr_zip(download_url)
    snapshot, raw_asset = _register_snapshot(
        session=session,
        authority_label=authority_label,
        download_url=download_url,
        zip_bytes=zip_bytes,
        requested_by=requested_by,
    )
    del raw_asset
    matches = list(
        _iter_matching_polygons(
            zip_bytes=zip_bytes,
            point_geometry_27700=point_geometry,
        )
    )
    if not matches:
        return None

    geometries: list[BaseGeometry] = []
    for title_number, geometry in matches:
        prepared = normalize_input_geometry(
            geometry=geometry,
            source_epsg=27700,
            source_type=GeomSourceType.SOURCE_POLYGON,
        )
        row = session.get(
            HmlrTitlePolygon,
            uuid.uuid5(REFERENCE_NAMESPACE, f"title:{title_number}"),
        )
        if row is None:
            row = HmlrTitlePolygon(
                id=uuid.uuid5(REFERENCE_NAMESPACE, f"title:{title_number}"),
                title_number=title_number,
            )
            session.add(row)
        row.title_number = title_number
        row.address_text = None
        row.normalized_address = None
        row.geom_27700 = prepared.geom_27700_wkt
        row.geom_4326 = prepared.geom_4326
        row.geom_hash = prepared.geom_hash
        row.area_sqm = prepared.area_sqm
        row.source_snapshot_id = snapshot.id
        geometries.append(prepared.geom_27700)

    session.flush()
    union_geometry = unary_union(geometries)
    return normalize_input_geometry(
        geometry=union_geometry,
        source_epsg=27700,
        source_type=GeomSourceType.TITLE_UNION,
        confidence=GeomConfidence.MEDIUM,
    )


def _register_snapshot(
    *,
    session: Session,
    authority_label: str,
    download_url: str,
    zip_bytes: bytes,
    requested_by: str | None,
) -> tuple[SourceSnapshot, RawAsset]:
    content_hash = hashlib.sha256(zip_bytes).hexdigest()
    snapshot_id = uuid.uuid5(
        HMLR_INSPIRE_NAMESPACE,
        f"hmlr-inspire:{authority_label}:{content_hash}",
    )
    existing_snapshot = session.get(SourceSnapshot, snapshot_id)
    if existing_snapshot is not None:
        existing_asset = session.execute(
            select(RawAsset).where(RawAsset.source_snapshot_id == existing_snapshot.id).limit(1)
        ).scalar_one()
        return existing_snapshot, existing_asset

    storage = build_storage(get_settings())
    storage_path = f"raw/official/hmlr_inspire/{content_hash}.zip"
    storage.put_bytes(storage_path, zip_bytes, content_type="application/zip")

    snapshot = SourceSnapshot(
        id=snapshot_id,
        source_family="reference.hmlr_title_polygon",
        source_name=f"hmlr_inspire_title_polygons:{authority_label}",
        source_uri=download_url,
        schema_hash=hashlib.sha256(b"hmlr_inspire_title_polygon_zip_v1").hexdigest(),
        content_hash=content_hash,
        coverage_note=(
            "Official HM Land Registry INSPIRE index polygons fetched for "
            f"{authority_label}."
        ),
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={
            "authority_name": authority_label,
            "download_url": download_url,
            "fetch_mode": "remote",
            "requested_by": requested_by,
            "storage_path": storage_path,
        },
    )
    raw_asset = RawAsset(
        id=uuid.uuid5(HMLR_INSPIRE_NAMESPACE, f"{snapshot_id}:raw_asset"),
        source_snapshot_id=snapshot_id,
        asset_type="ZIP",
        original_url=download_url,
        storage_path=storage_path,
        mime_type="application/zip",
        content_sha256=content_hash,
        size_bytes=len(zip_bytes),
    )
    session.add(snapshot)
    session.add(raw_asset)
    session.flush()
    return snapshot, raw_asset


def _iter_matching_polygons(
    *,
    zip_bytes: bytes,
    point_geometry_27700: BaseGeometry,
):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        gml_name = next(
            (name for name in archive.namelist() if name.lower().endswith(".gml")),
            None,
        )
        if gml_name is None:
            return
        with archive.open(gml_name) as handle:
            for _, element in ET.iterparse(handle, events=("end",)):
                if element.tag != f"{{{GML_NAMESPACES['LR']}}}PREDEFINED":
                    continue
                title_number = _child_text(
                    element,
                    "LR:INSPIREID",
                ) or _child_text(element, "LR:NATIONALCADASTRALREFERENCE")
                pos_list = element.find(".//gml:posList", GML_NAMESPACES)
                if not title_number or pos_list is None or not pos_list.text:
                    element.clear()
                    continue
                geometry = _polygon_from_pos_list(pos_list.text)
                if (
                    geometry is None
                    or geometry.is_empty
                    or not point_geometry_27700.intersects(geometry)
                ):
                    element.clear()
                    continue
                yield title_number, geometry
                element.clear()


def _child_text(element: ET.Element, path: str) -> str | None:
    child = element.find(path, GML_NAMESPACES)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _polygon_from_pos_list(pos_list: str) -> Polygon | None:
    values = [float(value) for value in pos_list.strip().split()]
    if len(values) < 6 or len(values) % 2 != 0:
        return None
    coordinates = [(values[index], values[index + 1]) for index in range(0, len(values), 2)]
    polygon = Polygon(coordinates)
    return polygon if not polygon.is_empty else None


def _download_url_for_authority(authority_label: str) -> str:
    slug = _slugify_authority_label(authority_label)
    return f"{HMLR_INSPIRE_DOWNLOAD_BASE_URL}/{slug}.zip"


@lru_cache(maxsize=16)
def _download_hmlr_zip(download_url: str) -> bytes:
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    response = scraper.get(download_url, allow_redirects=True, timeout=60)
    response.raise_for_status()
    return response.content


def _normalize_authority_label(authority_name: str) -> str | None:
    stripped = authority_name.strip()
    if not stripped:
        return None
    core = stripped.split("(", 1)[0].strip()
    if not core:
        return None
    return (
        core.title()
        .replace(" Of ", " of ")
        .replace(" And ", " and ")
        .replace(" Upon ", " upon ")
        .replace(" The ", " the ")
    )


def _slugify_authority_label(authority_label: str) -> str:
    return "_".join(
        token
        for token in [
            "".join(character for character in part if character.isalnum())
            for part in authority_label.replace("-", " ").replace("/", " ").split()
        ]
        if token
    )
