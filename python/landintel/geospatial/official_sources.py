from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from landintel.config import get_settings
from landintel.data_fetch.http_assets import fetch_http_asset
from landintel.domain.models import RawAsset, SourceSnapshot
from landintel.geospatial.reference_data import (
    ReferenceImportResult,
    import_hmlr_title_polygons,
    import_lpa_boundaries,
)
from landintel.storage.base import StorageAdapter

GEOSPATIAL_OFFICIAL_SOURCE_URL_KEYS = {
    "lpa": "lpa",
    "titles": "titles",
}
DEFAULT_LPA_REMOTE_URL = (
    "https://gis2.london.gov.uk/server/rest/services/apps/webmap_context_layer/MapServer/3/"
    "query?where=1%3D1&outFields=name%2Cgss_code&f=geojson"
)


def import_lpa_boundaries_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "london_borough_boundaries",
    remote_url: str | None = None,
) -> ReferenceImportResult:
    return _import_remote_geojson_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("lpa"),
        fixture_importer=lambda **kwargs: import_lpa_boundaries(
            source_name=source_name,
            **kwargs,
        ),
    )


def import_hmlr_title_polygons_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "hmlr_inspire_title_polygons",
    remote_url: str | None = None,
) -> ReferenceImportResult:
    return _import_remote_geojson_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("titles"),
        fixture_importer=lambda **kwargs: import_hmlr_title_polygons(
            source_name=source_name,
            **kwargs,
        ),
    )


def _import_remote_geojson_or_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    remote_url: str | None,
    fixture_importer,
) -> ReferenceImportResult:
    if remote_url:
        remote_temp_path: Path | None = None
        try:
            fetched = fetch_http_asset(
                remote_url,
                timeout_seconds=get_settings().snapshot_http_timeout_seconds,
            )
            suffix = _suffix_for_content_type(fetched.content_type, remote_url)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(fetched.content)
                remote_temp_path = Path(tmp.name)
            result = fixture_importer(
                session=session,
                storage=storage,
                fixture_path=remote_temp_path,
                requested_by=requested_by,
            )
            _rewrite_remote_provenance(
                session=session,
                source_snapshot_id=result.source_snapshot_id,
                raw_asset_id=result.raw_asset_id,
                remote_url=fetched.final_url,
                content_type=fetched.content_type,
                fetched_at=fetched.fetched_at.isoformat(),
                status_code=fetched.status_code,
            )
            session.flush()
            return result
        except Exception as exc:
            session.rollback()
            fallback_result = fixture_importer(
                session=session,
                storage=storage,
                fixture_path=fixture_path,
                requested_by=requested_by,
            )
            _annotate_fixture_fallback(
                session=session,
                source_snapshot_id=fallback_result.source_snapshot_id,
                remote_url=remote_url,
                fallback_reason=f"{type(exc).__name__}: {exc}",
            )
            session.flush()
            return fallback_result
        finally:
            if remote_temp_path is not None:
                remote_temp_path.unlink(missing_ok=True)

    return fixture_importer(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
    )


def _rewrite_remote_provenance(
    *,
    session: Session,
    source_snapshot_id,
    raw_asset_id,
    remote_url: str,
    content_type: str,
    fetched_at: str,
    status_code: int,
) -> None:
    snapshot = session.get(SourceSnapshot, source_snapshot_id)
    asset = session.get(RawAsset, raw_asset_id)
    if snapshot is not None:
        snapshot.source_uri = remote_url
        snapshot.manifest_json = {
            **dict(snapshot.manifest_json or {}),
            "fetch_mode": "remote",
            "remote_url": remote_url,
            "content_type": content_type,
            "fetched_at": fetched_at,
            "status_code": status_code,
        }
    if asset is not None:
        asset.original_url = remote_url
        asset.mime_type = content_type


def _annotate_fixture_fallback(
    *,
    session: Session,
    source_snapshot_id,
    remote_url: str,
    fallback_reason: str,
) -> None:
    snapshot = session.get(SourceSnapshot, source_snapshot_id)
    if snapshot is None:
        return
    snapshot.manifest_json = {
        **dict(snapshot.manifest_json or {}),
        "fetch_mode": "fixture_fallback",
        "remote_url": remote_url,
        "fallback_reason": fallback_reason,
    }


def _configured_remote_url(key: str) -> str | None:
    settings = get_settings()
    configured = settings.geospatial_official_source_urls_json.get(key) or None
    if configured:
        return configured
    if settings.real_data_mode and key == "lpa":
        return DEFAULT_LPA_REMOTE_URL
    return None


def _suffix_for_content_type(content_type: str, remote_url: str) -> str:
    lowered = content_type.lower()
    if "geo+json" in lowered or remote_url.lower().endswith(".geojson"):
        return ".geojson"
    if "json" in lowered or remote_url.lower().endswith(".json"):
        return ".json"
    return Path(remote_url).suffix or ".geojson"
