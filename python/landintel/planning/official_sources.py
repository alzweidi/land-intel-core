from __future__ import annotations

import tempfile
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

from sqlalchemy.orm import Session

from landintel.config import get_settings
from landintel.data_fetch.http_assets import fetch_http_asset
from landintel.domain.models import RawAsset, SourceSnapshot
from landintel.planning import planning_register_normalize as borough_register_mod
from landintel.planning import pld_ingest as pld_ingest_mod
from landintel.planning import reference_layers as reference_layers_mod
from landintel.planning.import_common import PlanningImportResult
from landintel.storage.base import StorageAdapter

PLANNING_OFFICIAL_SOURCE_URL_KEYS = {
    "pld": "pld",
    "borough_register": "borough_register",
    "brownfield": "brownfield",
    "policy": "policy",
    "constraints": "constraints",
    "flood": "flood",
    "heritage_article4": "heritage_article4",
}


def import_pld_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "planning_london_datahub_fixture",
    remote_url: str | None = None,
) -> PlanningImportResult:
    return _import_remote_json_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("pld"),
        fixture_importer=lambda **kwargs: pld_ingest_mod.import_pld_fixture(
            source_name=source_name,
            **kwargs,
        ),
    )


def import_borough_register_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "borough_planning_register_fixture",
    remote_url: str | None = None,
) -> PlanningImportResult:
    return _import_remote_json_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("borough_register"),
        fixture_importer=lambda **kwargs: borough_register_mod.import_borough_register_fixture(
            source_name=source_name,
            **kwargs,
        ),
    )


def import_brownfield_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "brownfield_register_fixture",
    remote_url: str | None = None,
) -> PlanningImportResult:
    return _import_remote_json_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("brownfield"),
        fixture_importer=lambda **kwargs: reference_layers_mod.import_brownfield_fixture(
            source_name=source_name,
            **kwargs,
        ),
    )


def import_policy_area_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "borough_policy_layer_fixture",
    remote_url: str | None = None,
) -> PlanningImportResult:
    return _import_remote_json_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("policy"),
        fixture_importer=lambda **kwargs: reference_layers_mod.import_policy_area_fixture(
            source_name=source_name,
            **kwargs,
        ),
    )


def import_constraint_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "planning_constraint_fixture",
    remote_url: str | None = None,
) -> PlanningImportResult:
    return _import_remote_json_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("constraints"),
        fixture_importer=lambda **kwargs: reference_layers_mod.import_constraint_fixture(
            source_name=source_name,
            **kwargs,
        ),
    )


def import_flood_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "flood_constraint_fixture",
    remote_url: str | None = None,
) -> PlanningImportResult:
    return _import_remote_json_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("flood"),
        fixture_importer=lambda **kwargs: reference_layers_mod.import_flood_fixture(
            source_name=source_name,
            **kwargs,
        ),
    )


def import_heritage_article4_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    source_name: str = "heritage_article4_fixture",
    remote_url: str | None = None,
) -> PlanningImportResult:
    return _import_remote_json_or_fixture(
        session=session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by=requested_by,
        remote_url=remote_url or _configured_remote_url("heritage_article4"),
        fixture_importer=lambda **kwargs: reference_layers_mod.import_heritage_article4_fixture(
            source_name=source_name,
            **kwargs,
        ),
    )


def _import_remote_json_or_fixture(
    *,
    session: Session,
    storage: StorageAdapter,
    fixture_path: str | Path,
    requested_by: str | None,
    remote_url: str | None,
    fixture_importer: Callable[..., PlanningImportResult],
) -> PlanningImportResult:
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
            with _begin_nested_if_supported(session):
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
            **snapshot.manifest_json,
            "fetch_mode": "remote",
            "remote_url": remote_url,
            "content_type": content_type,
            "fetched_at": fetched_at,
            "status_code": status_code,
        }
    if asset is not None:
        asset.original_url = remote_url


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
        **snapshot.manifest_json,
        "fetch_mode": "fixture_fallback",
        "remote_url": remote_url,
        "fallback_reason": fallback_reason,
    }


def _begin_nested_if_supported(session: Session):
    begin_nested = getattr(session, "begin_nested", None)
    if callable(begin_nested):
        return begin_nested()
    return nullcontext()


def _configured_remote_url(key: str) -> str | None:
    settings = get_settings()
    return settings.planning_official_source_urls_json.get(key) or None


def _suffix_for_content_type(content_type: str, remote_url: str) -> str:
    lowered = content_type.lower()
    if "geojson" in lowered:
        return ".geojson"
    if "json" in lowered:
        return ".json"
    suffix = Path(remote_url).suffix
    return suffix or ".json"
