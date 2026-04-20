from __future__ import annotations

import io
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from landintel.domain.enums import SourceFreshnessStatus, SourceParseStatus
from landintel.domain.models import RawAsset, SourceSnapshot
from landintel.geospatial import hmlr_inspire
from landintel.geospatial import official_sources as geospatial_official_sources
from landintel.geospatial.reference_data import ReferenceImportResult
from landintel.planning import official_sources as planning_official_sources
from landintel.planning.import_common import PlanningImportResult
from landintel.valuation import official_sources as valuation_official_sources
from shapely.geometry import Point


def _source_snapshot(
    snapshot_id: uuid.UUID,
    *,
    manifest_json: dict | None = None,
) -> SourceSnapshot:
    return SourceSnapshot(
        id=snapshot_id,
        source_family="fixture",
        source_name="fixture-source",
        source_uri="https://fixture.test/source",
        schema_hash="schema",
        content_hash="content",
        coverage_note="fixture coverage",
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json=manifest_json or {},
    )


def _raw_asset(asset_id: uuid.UUID, snapshot_id: uuid.UUID) -> RawAsset:
    return RawAsset(
        id=asset_id,
        source_snapshot_id=snapshot_id,
        asset_type="JSON",
        original_url="https://fixture.test/source",
        storage_path="raw/fixture/data.json",
        mime_type="application/json",
        content_sha256="content",
        size_bytes=12,
    )


@pytest.mark.parametrize(
    ("wrapper_name", "url_key", "source_name"),
    [
        ("import_lpa_boundaries_fixture", "lpa", "custom-lpa"),
        ("import_hmlr_title_polygons_fixture", "titles", "custom-titles"),
    ],
)
def test_geospatial_wrapper_uses_configured_remote_url_and_passes_source_name(
    monkeypatch,
    wrapper_name: str,
    url_key: str,
    source_name: str,
) -> None:
    recorded: dict[str, object] = {}

    def _capture_import(**kwargs):
        recorded["source_name"] = kwargs["source_name"]
        return ReferenceImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
        )

    monkeypatch.setattr(
        geospatial_official_sources,
        "_configured_remote_url",
        lambda key: f"https://example.test/{key}.geojson",
    )
    monkeypatch.setattr(
        geospatial_official_sources,
        "_import_remote_geojson_or_fixture",
        lambda **kwargs: (
            recorded.update({"remote_url": kwargs["remote_url"]}),
            kwargs["fixture_importer"](
                session=kwargs["session"],
                storage=kwargs["storage"],
                fixture_path=kwargs["fixture_path"],
                requested_by=kwargs["requested_by"],
            ),
        )[1],
    )
    target_name = (
        "import_lpa_boundaries"
        if wrapper_name == "import_lpa_boundaries_fixture"
        else "import_hmlr_title_polygons"
    )
    monkeypatch.setattr(geospatial_official_sources, target_name, _capture_import)

    wrapper = getattr(geospatial_official_sources, wrapper_name)
    result = wrapper(
        session=SimpleNamespace(),
        storage=SimpleNamespace(),
        fixture_path="fixture.geojson",
        requested_by="pytest",
        source_name=source_name,
    )

    assert recorded["remote_url"] == f"https://example.test/{url_key}.geojson"
    assert recorded["source_name"] == source_name
    assert result.imported_count == 1


def test_geospatial_import_remote_geojson_uses_fixture_directly_without_remote() -> None:
    calls: list[str] = []

    def _fixture_importer(**kwargs):
        calls.append(str(kwargs["fixture_path"]))
        return ReferenceImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=3,
        )

    result = geospatial_official_sources._import_remote_geojson_or_fixture(
        session=SimpleNamespace(),
        storage=SimpleNamespace(),
        fixture_path="fixture.geojson",
        requested_by="pytest",
        remote_url=None,
        fixture_importer=_fixture_importer,
    )

    assert calls == ["fixture.geojson"]
    assert result.imported_count == 3


def test_geospatial_rewrite_and_fallback_helpers_tolerate_missing_rows() -> None:
    snapshot_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    snapshot = SimpleNamespace(
        source_uri="https://fixture.test/source",
        manifest_json={"existing": True},
    )
    asset = SimpleNamespace(
        original_url="https://fixture.test/source",
        mime_type="application/json",
    )
    lookup = {
        (geospatial_official_sources.SourceSnapshot, snapshot_id): snapshot,
        (geospatial_official_sources.RawAsset, asset_id): asset,
    }
    session = SimpleNamespace(get=lambda model, key: lookup.get((model, key)))

    geospatial_official_sources._rewrite_remote_provenance(
        session=session,
        source_snapshot_id=snapshot_id,
        raw_asset_id=asset_id,
        remote_url="https://remote.test/data.geojson",
        content_type="application/geo+json",
        fetched_at="2026-04-20T00:00:00+00:00",
        status_code=200,
    )
    geospatial_official_sources._rewrite_remote_provenance(
        session=session,
        source_snapshot_id=uuid.uuid4(),
        raw_asset_id=uuid.uuid4(),
        remote_url="https://remote.test/missing.geojson",
        content_type="application/json",
        fetched_at="2026-04-20T00:00:00+00:00",
        status_code=200,
    )
    geospatial_official_sources._annotate_fixture_fallback(
        session=session,
        source_snapshot_id=snapshot_id,
        remote_url="https://remote.test/data.geojson",
        fallback_reason="RuntimeError: boom",
    )
    geospatial_official_sources._annotate_fixture_fallback(
        session=session,
        source_snapshot_id=uuid.uuid4(),
        remote_url="https://remote.test/missing.geojson",
        fallback_reason="RuntimeError: boom",
    )

    assert snapshot.source_uri == "https://remote.test/data.geojson"
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"
    assert snapshot.manifest_json["fallback_reason"] == "RuntimeError: boom"
    assert asset.original_url == "https://remote.test/data.geojson"
    assert asset.mime_type == "application/geo+json"


def test_geospatial_remote_url_and_suffix_helpers(monkeypatch, test_settings) -> None:
    configured = test_settings.model_copy(
        update={
            "real_data_mode": False,
            "geospatial_official_source_urls_json": {"titles": "https://example.test/titles.geojson"},
        }
    )
    monkeypatch.setattr(geospatial_official_sources, "get_settings", lambda: configured)

    assert geospatial_official_sources._configured_remote_url("titles") == "https://example.test/titles.geojson"
    assert geospatial_official_sources._configured_remote_url("lpa") is None
    monkeypatch.setattr(
        geospatial_official_sources,
        "get_settings",
        lambda: test_settings.model_copy(update={"real_data_mode": True}),
    )
    assert (
        geospatial_official_sources._configured_remote_url("lpa")
        == geospatial_official_sources.DEFAULT_LPA_REMOTE_URL
    )
    monkeypatch.setattr(geospatial_official_sources, "get_settings", lambda: configured)
    assert (
        geospatial_official_sources._suffix_for_content_type(
            "application/geo+json",
            "https://x.test/file",
        )
        == ".geojson"
    )
    assert (
        geospatial_official_sources._suffix_for_content_type(
            "application/json",
            "https://x.test/file",
        )
        == ".json"
    )
    assert (
        geospatial_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file.data",
        )
        == ".data"
    )
    assert (
        geospatial_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file",
        )
        == ".geojson"
    )


def test_geospatial_import_remote_geojson_covers_remote_success_and_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    fixture_path = tmp_path / "fixture.geojson"
    fixture_path.write_text('{"type":"FeatureCollection","features":[]}')
    snapshot_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    snapshot = SimpleNamespace(source_uri="fixture", manifest_json={})
    asset = SimpleNamespace(original_url="fixture", mime_type="application/json")
    lookup = {
        (geospatial_official_sources.SourceSnapshot, snapshot_id): snapshot,
        (geospatial_official_sources.RawAsset, asset_id): asset,
    }
    session = SimpleNamespace(
        get=lambda model, key: lookup.get((model, key)),
        flush=lambda: None,
        rollback=lambda: None,
    )

    monkeypatch.setattr(
        geospatial_official_sources,
        "fetch_http_asset",
        lambda remote_url, timeout_seconds: SimpleNamespace(
            content=b'{"type":"FeatureCollection","features":[]}',
            content_type="application/geo+json",
            final_url=remote_url,
            fetched_at=datetime.now(UTC),
            status_code=200,
        ),
    )

    seen_paths: list[Path] = []

    def _import_success(**kwargs):
        seen_paths.append(Path(kwargs["fixture_path"]))
        assert seen_paths[0] != fixture_path
        assert seen_paths[0].exists()
        return ReferenceImportResult(
            source_snapshot_id=snapshot_id,
            raw_asset_id=asset_id,
            imported_count=2,
        )

    result = geospatial_official_sources._import_remote_geojson_or_fixture(
        session=session,
        storage=SimpleNamespace(),
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://remote.test/remote.geojson",
        fixture_importer=_import_success,
    )

    assert result.imported_count == 2
    assert not seen_paths[0].exists()
    assert snapshot.manifest_json["fetch_mode"] == "remote"
    assert asset.mime_type == "application/geo+json"

    rollback_calls: list[str] = []
    seen_paths.clear()
    fallback_snapshot = SimpleNamespace(source_uri="fixture", manifest_json={})
    fallback_lookup = {
        (geospatial_official_sources.SourceSnapshot, snapshot_id): fallback_snapshot,
        (geospatial_official_sources.RawAsset, asset_id): asset,
    }
    fallback_session = SimpleNamespace(
        get=lambda model, key: fallback_lookup.get((model, key)),
        flush=lambda: None,
        rollback=lambda: rollback_calls.append("rolled-back"),
    )

    def _import_fallback(**kwargs):
        path = Path(kwargs["fixture_path"])
        seen_paths.append(path)
        if path != fixture_path:
            raise RuntimeError("remote import broke")
        return ReferenceImportResult(
            source_snapshot_id=snapshot_id,
            raw_asset_id=asset_id,
            imported_count=1,
        )

    fallback_result = geospatial_official_sources._import_remote_geojson_or_fixture(
        session=fallback_session,
        storage=SimpleNamespace(),
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://remote.test/remote.geojson",
        fixture_importer=_import_fallback,
    )

    assert fallback_result.imported_count == 1
    assert len(seen_paths) == 2
    assert seen_paths[0] != fixture_path
    assert seen_paths[1] == fixture_path
    assert rollback_calls == ["rolled-back"]
    assert fallback_snapshot.manifest_json["fetch_mode"] == "fixture_fallback"


def test_hmlr_maybe_import_title_union_returns_none_for_guard_conditions(
    monkeypatch,
    test_settings,
) -> None:
    monkeypatch.setattr(
        hmlr_inspire,
        "get_settings",
        lambda: test_settings.model_copy(update={"real_data_mode": False}),
    )
    assert (
        hmlr_inspire.maybe_import_title_union_for_listing_point(
            session=SimpleNamespace(),
            authority_name="Camden",
            lat=51.5,
            lon=-0.1,
            requested_by="pytest",
        )
        is None
    )

    monkeypatch.setattr(
        hmlr_inspire,
        "get_settings",
        lambda: test_settings.model_copy(update={"real_data_mode": True}),
    )
    assert (
        hmlr_inspire.maybe_import_title_union_for_listing_point(
            session=SimpleNamespace(),
            authority_name="   ",
            lat=51.5,
            lon=-0.1,
            requested_by="pytest",
        )
        is None
    )
    assert (
        hmlr_inspire.maybe_import_title_union_for_listing_point(
            session=SimpleNamespace(),
            authority_name="Camden",
            lat=None,
            lon=-0.1,
            requested_by="pytest",
        )
        is None
    )


def test_hmlr_maybe_import_title_union_covers_no_match_and_happy_path(
    monkeypatch,
    test_settings,
) -> None:
    monkeypatch.setattr(
        hmlr_inspire,
        "get_settings",
        lambda: test_settings.model_copy(update={"real_data_mode": True}),
    )
    monkeypatch.setattr(
        hmlr_inspire,
        "build_point_geometry",
        lambda lat, lon: SimpleNamespace(geom_27700=Point(0, 0)),
    )
    monkeypatch.setattr(
        hmlr_inspire,
        "_download_hmlr_zip",
        lambda download_url: b"zip-data",
    )
    monkeypatch.setattr(
        hmlr_inspire,
        "_register_snapshot",
        lambda **kwargs: (SimpleNamespace(id=uuid.uuid4()), SimpleNamespace()),
    )
    monkeypatch.setattr(
        hmlr_inspire,
        "_iter_matching_polygons",
        lambda **kwargs: [],
    )
    assert (
        hmlr_inspire.maybe_import_title_union_for_listing_point(
            session=SimpleNamespace(),
            authority_name="Camden",
            lat=51.5,
            lon=-0.1,
            requested_by="pytest",
        )
        is None
    )

    existing_id = uuid.uuid5(hmlr_inspire.REFERENCE_NAMESPACE, "title:TITLE-1")
    existing_row = SimpleNamespace(
        id=existing_id,
        title_number="TITLE-1",
        address_text="old",
        normalized_address="old",
        geom_27700=None,
        geom_4326=None,
        geom_hash="old",
        area_sqm=0.0,
        source_snapshot_id=None,
    )
    stored = {(hmlr_inspire.HmlrTitlePolygon, existing_id): existing_row}
    added: list[object] = []
    session = SimpleNamespace(
        get=lambda model, key: stored.get((model, key)),
        add=lambda instance: added.append(instance),
        flush=lambda: None,
    )

    polygon_one = hmlr_inspire.Polygon([(0, 0), (0, 2), (2, 2), (2, 0), (0, 0)])
    polygon_two = hmlr_inspire.Polygon([(2, 0), (2, 2), (4, 2), (4, 0), (2, 0)])

    def _normalize_input_geometry(*, geometry, source_epsg, source_type, confidence=None):
        if source_type == hmlr_inspire.GeomSourceType.SOURCE_POLYGON:
            return SimpleNamespace(
                geom_27700=geometry,
                geom_27700_wkt=geometry.wkt,
                geom_4326="4326",
                geom_hash=f"hash-{geometry.area}",
                area_sqm=geometry.area,
            )
        return SimpleNamespace(
            geom_source_type=source_type,
            geom_confidence=confidence,
            area_sqm=geometry.area,
        )

    monkeypatch.setattr(
        hmlr_inspire,
        "_iter_matching_polygons",
        lambda **kwargs: [("TITLE-1", polygon_one), ("TITLE-2", polygon_two)],
    )
    monkeypatch.setattr(hmlr_inspire, "normalize_input_geometry", _normalize_input_geometry)

    prepared = hmlr_inspire.maybe_import_title_union_for_listing_point(
        session=session,
        authority_name="Camden",
        lat=51.5,
        lon=-0.1,
        requested_by="pytest",
    )

    assert prepared is not None
    assert prepared.geom_source_type == hmlr_inspire.GeomSourceType.TITLE_UNION
    assert prepared.geom_confidence == hmlr_inspire.GeomConfidence.MEDIUM
    assert prepared.area_sqm == polygon_one.union(polygon_two).area
    assert existing_row.geom_hash == f"hash-{polygon_one.area}"
    assert len([entry for entry in added if isinstance(entry, hmlr_inspire.HmlrTitlePolygon)]) == 1


def test_hmlr_register_snapshot_reuses_existing_snapshot(
    db_session,
    storage,
    monkeypatch,
    test_settings,
) -> None:
    monkeypatch.setattr(hmlr_inspire, "get_settings", lambda: test_settings)
    monkeypatch.setattr(hmlr_inspire, "build_storage", lambda settings: storage)

    snapshot, asset = hmlr_inspire._register_snapshot(
        session=db_session,
        authority_label="Camden",
        download_url="https://example.test/camden.zip",
        zip_bytes=b"zip-data",
        requested_by="pytest",
    )
    db_session.expire_all()

    reused_snapshot, reused_asset = hmlr_inspire._register_snapshot(
        session=db_session,
        authority_label="Camden",
        download_url="https://example.test/camden.zip",
        zip_bytes=b"zip-data",
        requested_by="pytest",
    )

    assert reused_snapshot.id == snapshot.id
    assert reused_asset.id == asset.id


def test_hmlr_iter_matching_polygons_handles_missing_gml_and_reference_fallback() -> None:
    empty_zip = io.BytesIO()
    with zipfile.ZipFile(empty_zip, "w") as archive:
        archive.writestr("readme.txt", "no gml here")
    assert list(
        hmlr_inspire._iter_matching_polygons(
            zip_bytes=empty_zip.getvalue(),
            point_geometry_27700=Point(0, 0),
        )
    ) == []

    matching_zip = io.BytesIO()
    with zipfile.ZipFile(matching_zip, "w") as archive:
        archive.writestr(
            "titles.gml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<wfs:FeatureCollection '
                'xmlns:wfs="http://www.opengis.net/wfs/2.0" '
                'xmlns:LR="www.landregistry.gov.uk" '
                'xmlns:gml="http://www.opengis.net/gml/3.2">'
                '<wfs:member><LR:PREDEFINED>'
                '<LR:INSPIREID>NO-POSLIST</LR:INSPIREID>'
                '</LR:PREDEFINED></wfs:member>'
                '<wfs:member><LR:PREDEFINED>'
                '<LR:NATIONALCADASTRALREFERENCE>TITLE-42</LR:NATIONALCADASTRALREFERENCE>'
                '<LR:GEOMETRY><gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700">'
                '<gml:exterior><gml:LinearRing>'
                '<gml:posList>0 0 0 10 10 10 10 0 0 0</gml:posList>'
                '</gml:LinearRing></gml:exterior></gml:Polygon></LR:GEOMETRY>'
                '</LR:PREDEFINED></wfs:member>'
                '<wfs:member><LR:PREDEFINED>'
                '<LR:INSPIREID>MISS</LR:INSPIREID>'
                '<LR:GEOMETRY><gml:Polygon srsName="urn:ogc:def:crs:EPSG::27700">'
                '<gml:exterior><gml:LinearRing>'
                '<gml:posList>20 20 20 30 30 30 30 20 20 20</gml:posList>'
                '</gml:LinearRing></gml:exterior></gml:Polygon></LR:GEOMETRY>'
                '</LR:PREDEFINED></wfs:member>'
                '</wfs:FeatureCollection>'
            ),
        )

    matches = list(
        hmlr_inspire._iter_matching_polygons(
            zip_bytes=matching_zip.getvalue(),
            point_geometry_27700=Point(5, 5),
        )
    )

    assert len(matches) == 1
    assert matches[0][0] == "TITLE-42"


def test_hmlr_parse_helpers_cover_blank_invalid_and_download(monkeypatch) -> None:
    element = ET.fromstring(
        "<LR:PREDEFINED xmlns:LR='www.landregistry.gov.uk'>"
        "<LR:INSPIREID>  </LR:INSPIREID>"
        "</LR:PREDEFINED>"
    )
    assert hmlr_inspire._child_text(element, "LR:INSPIREID") is None
    assert hmlr_inspire._polygon_from_pos_list("0 0 0") is None
    polygon = hmlr_inspire._polygon_from_pos_list("0 0 0 1 1 1 1 0 0 0")
    assert polygon is not None and polygon.area > 0
    assert (
        hmlr_inspire._normalize_authority_label(
            "  city of london / the docks (X) "
        )
        == "City of London / the Docks"
    )
    assert hmlr_inspire._normalize_authority_label("   (X)") is None
    assert (
        hmlr_inspire._slugify_authority_label("City of London / the Docks")
        == "City_of_London_the_Docks"
    )
    assert hmlr_inspire._download_url_for_authority("City of London") == (
        f"{hmlr_inspire.HMLR_INSPIRE_DOWNLOAD_BASE_URL}/City_of_London.zip"
    )

    class _Response:
        content = b"zip-bits"

        @staticmethod
        def raise_for_status() -> None:
            return None

    class _Scraper:
        def get(self, download_url: str, allow_redirects: bool, timeout: int) -> _Response:
            assert download_url.endswith("/City_of_London.zip")
            assert allow_redirects is True
            assert timeout == 60
            return _Response()

    hmlr_inspire._download_hmlr_zip.cache_clear()
    monkeypatch.setattr(
        hmlr_inspire.cloudscraper,
        "create_scraper",
        lambda browser: _Scraper(),
    )

    assert (
        hmlr_inspire._download_hmlr_zip(
            f"{hmlr_inspire.HMLR_INSPIRE_DOWNLOAD_BASE_URL}/City_of_London.zip"
        )
        == b"zip-bits"
    )


@pytest.mark.parametrize(
    ("wrapper_name", "url_key", "source_name"),
    [
        ("import_pld_fixture", "pld", "pld-source"),
        ("import_borough_register_fixture", "borough_register", "borough-source"),
        ("import_brownfield_fixture", "brownfield", "brownfield-source"),
        ("import_policy_area_fixture", "policy", "policy-source"),
        ("import_constraint_fixture", "constraints", "constraint-source"),
        ("import_flood_fixture", "flood", "flood-source"),
        ("import_heritage_article4_fixture", "heritage_article4", "heritage-source"),
    ],
)
def test_planning_wrappers_use_configured_remote_url_and_pass_source_name(
    monkeypatch,
    wrapper_name: str,
    url_key: str,
    source_name: str,
) -> None:
    recorded: dict[str, object] = {}

    def _capture_import(**kwargs):
        recorded["source_name"] = kwargs["source_name"]
        return PlanningImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=2,
            coverage_count=1,
        )

    monkeypatch.setattr(
        planning_official_sources,
        "_configured_remote_url",
        lambda key: f"https://example.test/{key}.json",
    )
    monkeypatch.setattr(
        planning_official_sources,
        "_import_remote_json_or_fixture",
        lambda **kwargs: (
            recorded.update({"remote_url": kwargs["remote_url"]}),
            kwargs["fixture_importer"](
                session=kwargs["session"],
                storage=kwargs["storage"],
                fixture_path=kwargs["fixture_path"],
                requested_by=kwargs["requested_by"],
            ),
        )[1],
    )
    target_map = {
        "import_pld_fixture": ("pld_ingest_mod", "import_pld_fixture"),
        "import_borough_register_fixture": (
            "borough_register_mod",
            "import_borough_register_fixture",
        ),
        "import_brownfield_fixture": ("reference_layers_mod", "import_brownfield_fixture"),
        "import_policy_area_fixture": ("reference_layers_mod", "import_policy_area_fixture"),
        "import_constraint_fixture": ("reference_layers_mod", "import_constraint_fixture"),
        "import_flood_fixture": ("reference_layers_mod", "import_flood_fixture"),
        "import_heritage_article4_fixture": (
            "reference_layers_mod",
            "import_heritage_article4_fixture",
        ),
    }
    module_name, fn_name = target_map[wrapper_name]
    monkeypatch.setattr(getattr(planning_official_sources, module_name), fn_name, _capture_import)

    wrapper = getattr(planning_official_sources, wrapper_name)
    result = wrapper(
        session=SimpleNamespace(),
        storage=SimpleNamespace(),
        fixture_path="fixture.json",
        requested_by="pytest",
        source_name=source_name,
    )

    assert recorded["remote_url"] == f"https://example.test/{url_key}.json"
    assert recorded["source_name"] == source_name
    assert result.imported_count == 2


def test_planning_import_helpers_cover_local_remote_and_missing_rows(
    monkeypatch,
    test_settings,
) -> None:
    calls: list[str] = []

    def _fixture_importer(**kwargs):
        calls.append(str(kwargs["fixture_path"]))
        return PlanningImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=1,
            coverage_count=0,
        )

    local_result = planning_official_sources._import_remote_json_or_fixture(
        session=SimpleNamespace(),
        storage=SimpleNamespace(),
        fixture_path="fixture.json",
        requested_by="pytest",
        remote_url=None,
        fixture_importer=_fixture_importer,
    )
    assert local_result.imported_count == 1
    assert calls == ["fixture.json"]

    snapshot_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    snapshot = SimpleNamespace(
        source_uri="https://fixture.test/source",
        manifest_json={"existing": True},
    )
    asset = SimpleNamespace(original_url="https://fixture.test/source")
    lookup = {
        (planning_official_sources.SourceSnapshot, snapshot_id): snapshot,
        (planning_official_sources.RawAsset, asset_id): asset,
    }
    session = SimpleNamespace(get=lambda model, key: lookup.get((model, key)))

    planning_official_sources._rewrite_remote_provenance(
        session=session,
        source_snapshot_id=snapshot_id,
        raw_asset_id=asset_id,
        remote_url="https://remote.test/brownfield.geojson",
        content_type="application/geo+json",
        fetched_at="2026-04-20T00:00:00+00:00",
        status_code=200,
    )
    planning_official_sources._rewrite_remote_provenance(
        session=session,
        source_snapshot_id=uuid.uuid4(),
        raw_asset_id=uuid.uuid4(),
        remote_url="https://remote.test/missing.geojson",
        content_type="application/json",
        fetched_at="2026-04-20T00:00:00+00:00",
        status_code=200,
    )
    planning_official_sources._annotate_fixture_fallback(
        session=session,
        source_snapshot_id=snapshot_id,
        remote_url="https://remote.test/brownfield.geojson",
        fallback_reason="RuntimeError: failed",
    )
    planning_official_sources._annotate_fixture_fallback(
        session=session,
        source_snapshot_id=uuid.uuid4(),
        remote_url="https://remote.test/missing.geojson",
        fallback_reason="RuntimeError: failed",
    )

    assert snapshot.source_uri == "https://remote.test/brownfield.geojson"
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"
    assert asset.original_url == "https://remote.test/brownfield.geojson"

    monkeypatch.setattr(planning_official_sources, "get_settings", lambda: test_settings)
    assert planning_official_sources._configured_remote_url("pld") is None
    assert (
        planning_official_sources._suffix_for_content_type(
            "application/geojson",
            "https://x.test/file",
        )
        == ".geojson"
    )
    assert (
        planning_official_sources._suffix_for_content_type(
            "application/json",
            "https://x.test/file",
        )
        == ".json"
    )
    assert (
        planning_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file.data",
        )
        == ".data"
    )
    assert (
        planning_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file",
        )
        == ".json"
    )


def test_planning_import_remote_json_covers_success_and_fallback(tmp_path, monkeypatch) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text('{"rows":[]}')
    snapshot_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    snapshot = SimpleNamespace(source_uri="fixture", manifest_json={})
    asset = SimpleNamespace(original_url="fixture")
    lookup = {
        (planning_official_sources.SourceSnapshot, snapshot_id): snapshot,
        (planning_official_sources.RawAsset, asset_id): asset,
    }
    session = SimpleNamespace(get=lambda model, key: lookup.get((model, key)), flush=lambda: None)
    monkeypatch.setattr(
        planning_official_sources,
        "fetch_http_asset",
        lambda remote_url, timeout_seconds: SimpleNamespace(
            content=b'{"rows":[]}',
            content_type="application/json",
            final_url=remote_url,
            fetched_at=datetime.now(UTC),
            status_code=200,
        ),
    )

    seen_paths: list[Path] = []

    def _success(**kwargs):
        path = Path(kwargs["fixture_path"])
        seen_paths.append(path)
        assert path != fixture_path
        assert path.exists()
        return PlanningImportResult(
            source_snapshot_id=snapshot_id,
            raw_asset_id=asset_id,
            imported_count=2,
            coverage_count=1,
        )

    result = planning_official_sources._import_remote_json_or_fixture(
        session=session,
        storage=SimpleNamespace(),
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://remote.test/data.json",
        fixture_importer=_success,
    )

    assert result.imported_count == 2
    assert not seen_paths[0].exists()
    assert snapshot.manifest_json["fetch_mode"] == "remote"

    seen_paths.clear()
    fallback_snapshot = SimpleNamespace(source_uri="fixture", manifest_json={})
    fallback_lookup = {
        (planning_official_sources.SourceSnapshot, snapshot_id): fallback_snapshot,
        (planning_official_sources.RawAsset, asset_id): asset,
    }
    fallback_session = SimpleNamespace(
        get=lambda model, key: fallback_lookup.get((model, key)),
        flush=lambda: None,
    )

    def _fallback(**kwargs):
        path = Path(kwargs["fixture_path"])
        seen_paths.append(path)
        if path != fixture_path:
            raise RuntimeError("import failed after download")
        return PlanningImportResult(
            source_snapshot_id=snapshot_id,
            raw_asset_id=asset_id,
            imported_count=1,
            coverage_count=0,
        )

    fallback_result = planning_official_sources._import_remote_json_or_fixture(
        session=fallback_session,
        storage=SimpleNamespace(),
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://remote.test/data.json",
        fixture_importer=_fallback,
    )

    assert fallback_result.imported_count == 1
    assert len(seen_paths) == 2
    assert seen_paths[0] != fixture_path
    assert seen_paths[1] == fixture_path
    assert fallback_snapshot.manifest_json["fetch_mode"] == "fixture_fallback"


def test_valuation_import_entrypoints_delegate_and_fallback(
    db_session,
    storage,
    monkeypatch,
) -> None:
    fixture_path = "fixtures/valuation.json"
    fallback_snapshot_id = uuid.uuid4()
    db_session.add(_source_snapshot(fallback_snapshot_id, manifest_json={}))
    db_session.flush()

    monkeypatch.setattr(
        valuation_official_sources,
        "fetch_http_asset",
        lambda remote_url, timeout_seconds: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        valuation_official_sources.valuation_market_mod,
        "import_hmlr_price_paid_fixture",
        lambda **kwargs: PlanningImportResult(
            source_snapshot_id=fallback_snapshot_id,
            raw_asset_id=uuid.uuid4(),
            imported_count=4,
            coverage_count=2,
        ),
    )
    result = valuation_official_sources.import_hmlr_price_paid_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://remote.test/ppd.csv",
    )
    snapshot = db_session.get(SourceSnapshot, fallback_snapshot_id)
    assert result.imported_count == 4
    assert snapshot is not None
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"

    delegated_hmlr = valuation_official_sources.import_hmlr_price_paid_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=None,
    )
    assert delegated_hmlr.imported_count == 4

    monkeypatch.setattr(
        valuation_official_sources.valuation_market_mod,
        "import_ukhpi_fixture",
        lambda **kwargs: PlanningImportResult(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=5,
            coverage_count=3,
        ),
    )
    delegated = valuation_official_sources.import_ukhpi_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url=None,
    )
    assert delegated.imported_count == 5

    ukhpi_snapshot_id = uuid.uuid4()
    db_session.add(_source_snapshot(ukhpi_snapshot_id, manifest_json={}))
    db_session.flush()
    monkeypatch.setattr(
        valuation_official_sources.valuation_market_mod,
        "import_ukhpi_fixture",
        lambda **kwargs: PlanningImportResult(
            source_snapshot_id=ukhpi_snapshot_id,
            raw_asset_id=uuid.uuid4(),
            imported_count=6,
            coverage_count=2,
        ),
    )
    fallback_ukhpi = valuation_official_sources.import_ukhpi_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
        remote_url="https://remote.test/ukhpi.csv",
    )
    ukhpi_snapshot = db_session.get(SourceSnapshot, ukhpi_snapshot_id)
    assert fallback_ukhpi.imported_count == 6
    assert ukhpi_snapshot is not None
    assert ukhpi_snapshot.manifest_json["fetch_mode"] == "fixture_fallback"


def test_valuation_import_entrypoints_cover_remote_success(monkeypatch) -> None:
    snapshot = SimpleNamespace(id=uuid.uuid4(), manifest_json={"existing": True})
    asset = SimpleNamespace(id=uuid.uuid4(), original_url="fixture")
    session = SimpleNamespace(flush=lambda: None)
    monkeypatch.setattr(
        valuation_official_sources,
        "fetch_http_asset",
        lambda remote_url, timeout_seconds: SimpleNamespace(
            content=b"csv-bytes",
            content_type="text/csv",
            final_url=remote_url,
            status_code=200,
        ),
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_parse_hmlr_price_paid_payload",
        lambda content, content_type: [{"district": "Camden"}],
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_parse_ukhpi_payload",
        lambda content, content_type: [{"RegionName": "Camden"}],
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_register_remote_snapshot",
        lambda **kwargs: (snapshot, asset),
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_upsert_hmlr_coverage_snapshots",
        lambda **kwargs: 2,
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_upsert_hmlr_price_paid_rows",
        lambda **kwargs: 3,
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_upsert_ukhpi_coverage_snapshots",
        lambda **kwargs: 4,
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "_upsert_ukhpi_rows",
        lambda **kwargs: 5,
    )

    ppd_result = valuation_official_sources.import_hmlr_price_paid_fixture(
        session=session,
        storage=SimpleNamespace(),
        fixture_path="fixture.json",
        requested_by="pytest",
        remote_url="https://remote.test/ppd.csv",
    )
    assert ppd_result.imported_count == 3
    assert ppd_result.coverage_count == 2
    assert snapshot.manifest_json["record_count"] == 3
    assert asset.original_url == "https://remote.test/ppd.csv"

    snapshot.manifest_json = {"existing": True}
    asset.original_url = "fixture"
    ukhpi_result = valuation_official_sources.import_ukhpi_fixture(
        session=session,
        storage=SimpleNamespace(),
        fixture_path="fixture.json",
        requested_by="pytest",
        remote_url="https://remote.test/ukhpi.csv",
    )
    assert ukhpi_result.imported_count == 5
    assert ukhpi_result.coverage_count == 4
    assert snapshot.manifest_json["record_count"] == 5
    assert asset.original_url == "https://remote.test/ukhpi.csv"


def test_valuation_register_snapshot_and_coverage_helpers(db_session, storage, monkeypatch) -> None:
    snapshot, asset = valuation_official_sources._register_remote_snapshot(
        session=db_session,
        storage=storage,
        raw_bytes=b'{"ok": true}',
        content_type="application/json",
        dataset_key="valuation_ukhpi",
        source_family="UKHPI",
        source_name="UKHPI official source",
        schema_key="valuation_ukhpi_v1",
        coverage_note="coverage",
        requested_by="pytest",
        remote_url="https://remote.test/ukhpi",
    )
    reused_snapshot, reused_asset = valuation_official_sources._register_remote_snapshot(
        session=db_session,
        storage=storage,
        raw_bytes=b'{"ok": true}',
        content_type="application/json",
        dataset_key="valuation_ukhpi",
        source_family="UKHPI",
        source_name="UKHPI official source",
        schema_key="valuation_ukhpi_v1",
        coverage_note="coverage",
        requested_by="pytest",
        remote_url="https://remote.test/ukhpi",
    )
    assert reused_snapshot.id == snapshot.id
    assert reused_asset.id == asset.id
    assert asset.asset_type == "JSON"
    assert asset.storage_path.endswith(".json")

    coverage_calls: list[list[dict[str, str]]] = []
    fake_session = SimpleNamespace(
        get=lambda model, key: object() if key == "camden" else None,
    )
    monkeypatch.setattr(
        valuation_official_sources,
        "upsert_coverage_snapshots",
        lambda **kwargs: (
            coverage_calls.append(kwargs["coverage_rows"])
            or len(kwargs["coverage_rows"])
        ),
    )
    fake_snapshot = SimpleNamespace(
        id=uuid.uuid4(),
        freshness_status=SimpleNamespace(value="FRESH"),
        coverage_note="coverage",
    )

    ppd_count = valuation_official_sources._upsert_hmlr_coverage_snapshots(
        session=fake_session,
        snapshot=fake_snapshot,
        rows=[{"district": "Camden"}, {"district": "Unknown"}],
    )
    ukhpi_count = valuation_official_sources._upsert_ukhpi_coverage_snapshots(
        session=fake_session,
        snapshot=fake_snapshot,
        rows=[{"RegionName": "Camden"}, {"RegionName": "Unknown"}],
    )

    assert ppd_count == 1
    assert ukhpi_count == 1
    assert coverage_calls[0][0]["borough_id"] == "camden"
    assert coverage_calls[1][0]["source_family"] == "UKHPI"
    assert valuation_official_sources._upsert_hmlr_coverage_snapshots(
        session=SimpleNamespace(get=lambda model, key: None),
        snapshot=fake_snapshot,
        rows=[{"district": "Unknown"}],
    ) == 0
    assert valuation_official_sources._upsert_ukhpi_coverage_snapshots(
        session=SimpleNamespace(get=lambda model, key: None),
        snapshot=fake_snapshot,
        rows=[{"RegionName": "Unknown"}],
    ) == 0


def test_valuation_row_upserts_cover_fallback_fields() -> None:
    snapshot_id = uuid.uuid4()
    snapshot = SimpleNamespace(id=snapshot_id)
    raw_asset_id = uuid.uuid4()
    stored: dict[tuple[type, uuid.UUID], object] = {}
    added: list[object] = []

    def _get(model, key):
        return stored.get((model, key))

    def _add(instance):
        stored[(type(instance), instance.id)] = instance
        added.append(instance)

    session = SimpleNamespace(get=_get, add=_add)

    imported_sales = valuation_official_sources._upsert_hmlr_price_paid_rows(
        session=session,
        snapshot=snapshot,
        raw_asset_id=raw_asset_id,
        rows=[
            {
                "transaction unique identifier": "txn-space",
                "district_name": "Camden",
                "completion_date": "2025-01-15",
                "Price": "850000",
                "Property Type": "HOUSE",
                "Duration": "F",
                "Postcode": "NW1 1AA",
                "street": "1 Example Mews",
                "town": "London",
                "county": "Greater London",
                "floor_area_sqm": "100",
                "rebased_price_per_sqm_hint": "8500.5",
            }
        ],
    )
    imported_index = valuation_official_sources._upsert_ukhpi_rows(
        session=session,
        snapshot=snapshot,
        raw_asset_id=raw_asset_id,
        rows=[
            {
                "AreaCode": "Camden",
                "Date": "2025-02-01",
                "Index": "131.5",
            }
        ],
    )

    sale = next(
        entry for entry in added if isinstance(entry, valuation_official_sources.MarketSaleComp)
    )
    index_row = next(
        entry for entry in added if isinstance(entry, valuation_official_sources.MarketIndexSeries)
    )
    assert imported_sales == 1
    assert imported_index == 1
    assert sale.transaction_ref == "txn-space"
    assert sale.borough_id == "camden"
    assert sale.price_gbp == 850000
    assert sale.tenure == "FREEHOLD"
    assert sale.postcode_district == "NW1"
    assert sale.address_text == "1 Example Mews, London, Greater London"
    assert sale.floor_area_sqm == 100.0
    assert sale.rebased_price_per_sqm_hint == 8500.5
    assert index_row.borough_id == "camden"
    assert index_row.index_key == "UKHPI"
    assert index_row.period_month == date(2025, 2, 1)
    assert index_row.index_value == 131.5

    updated_sales = valuation_official_sources._upsert_hmlr_price_paid_rows(
        session=session,
        snapshot=snapshot,
        raw_asset_id=raw_asset_id,
        rows=[
            {
                "transaction_ref": "txn-space",
                "borough_id": "Southwark",
                "sale_date": "2025-03-01",
                "price_gbp": "910000",
                "property_type": "FLAT",
                "tenure": "L",
                "postcode_district": "SE1",
                "address_text": "Updated address",
            }
        ],
    )
    updated_index = valuation_official_sources._upsert_ukhpi_rows(
        session=session,
        snapshot=snapshot,
        raw_asset_id=raw_asset_id,
        rows=[
            {
                "RegionName": "Camden",
                "IndexKey": "UKHPI",
                "Date": "2025-02-01",
                "Index": "140.0",
            }
        ],
    )

    assert updated_sales == 1
    assert updated_index == 1
    assert sale.borough_id == "southwark"
    assert sale.price_gbp == 910000
    assert sale.tenure == "LEASEHOLD"
    assert sale.address_text == "Updated address"
    assert index_row.borough_id == "camden"
    assert index_row.index_value == 140.0


def test_valuation_parse_and_scalar_helpers_cover_branch_variants(
    monkeypatch,
    test_settings,
    db_session,
) -> None:
    assert valuation_official_sources._parse_hmlr_price_paid_payload(
        b'{"sales":[{"transaction_ref":"a"}]}',
        "application/json",
    ) == [{"transaction_ref": "a"}]
    assert valuation_official_sources._parse_ukhpi_payload(
        b'{"rows":[{"borough_id":"camden"}]}',
        "application/json",
    ) == [{"borough_id": "camden"}]

    with pytest.raises(ValueError, match="HMLR Price Paid JSON payload did not contain a row list"):
        valuation_official_sources._parse_hmlr_price_paid_payload(
            b'{"rows":{"bad":true}}',
            "application/json",
        )
    with pytest.raises(ValueError, match="UKHPI JSON payload did not contain a row list"):
        valuation_official_sources._parse_ukhpi_payload(
            b'{"rows":{"bad":true}}',
            "application/json",
        )

    ppd_rows = valuation_official_sources._parse_hmlr_price_paid_payload(
        (
            b"transaction_unique_identifier,District,Date,Price,Property Type,"
            b"Duration,Postcode,street,town\n"
            b",Camden,2025-01-01,500000,FLAT,L,NW1 1AA,1 Example Mews,London\n"
        ),
        "text/csv",
    )
    ukhpi_rows = valuation_official_sources._parse_ukhpi_payload(
        b"RegionName,Date,Index\nCamden,2025-02-01,132.1\n",
        "text/csv",
    )

    assert ppd_rows[0]["transaction_ref"] == "ppd-1"
    assert ppd_rows[0]["borough_id"] == "Camden"
    assert ppd_rows[0]["address_text"] == "1 Example Mews, London"
    assert ukhpi_rows[0]["borough_id"] == "Camden"
    assert ukhpi_rows[0]["index_key"] == "UKHPI"

    snapshot_id = uuid.uuid4()
    db_session.add(_source_snapshot(snapshot_id, manifest_json={}))
    db_session.flush()
    valuation_official_sources._annotate_fixture_fallback(
        session=db_session,
        source_snapshot_id=snapshot_id,
        remote_url="https://remote.test/ukhpi.csv",
        fallback_reason="RuntimeError: boom",
    )
    valuation_official_sources._annotate_fixture_fallback(
        session=db_session,
        source_snapshot_id=uuid.uuid4(),
        remote_url="https://remote.test/ukhpi.csv",
        fallback_reason="RuntimeError: boom",
    )

    snapshot = db_session.get(SourceSnapshot, snapshot_id)
    assert snapshot is not None
    assert snapshot.manifest_json["fetch_mode"] == "fixture_fallback"

    monkeypatch.setattr(valuation_official_sources, "get_settings", lambda: test_settings)
    assert valuation_official_sources._configured_remote_url("ukhpi") is None
    assert (
        valuation_official_sources._suffix_for_content_type(
            "text/csv",
            "https://x.test/file",
        )
        == ".csv"
    )
    assert (
        valuation_official_sources._suffix_for_content_type(
            "application/json",
            "https://x.test/file",
        )
        == ".json"
    )
    assert (
        valuation_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file.data",
        )
        == ".data"
    )
    assert (
        valuation_official_sources._suffix_for_content_type(
            "application/octet-stream",
            "https://x.test/file",
        )
        == ".csv"
    )
    assert valuation_official_sources._asset_type_for_content_type("text/csv") == "CSV"
    assert valuation_official_sources._asset_type_for_content_type("application/json") == "JSON"
    assert (
        valuation_official_sources._asset_type_for_content_type("application/octet-stream")
        == "OFFICIAL_DATA"
    )
    assert len(valuation_official_sources._sha256(b"abc")) == 64
    assert valuation_official_sources._slugify(" Camden / Borough ") == "camdenborough"
    assert valuation_official_sources._slugify(None) is None
    assert valuation_official_sources._slugify("   ") is None
    assert valuation_official_sources._nullable_string("  hi  ") == "hi"
    assert valuation_official_sources._nullable_string("   ") is None
    assert valuation_official_sources._parse_date(date(2025, 1, 1)) == date(2025, 1, 1)
    assert valuation_official_sources._parse_date("2025-01-01") == date(2025, 1, 1)
    with pytest.raises(ValueError, match="date value is required"):
        valuation_official_sources._parse_date("")
    assert valuation_official_sources._parse_float("1.5") == 1.5
    assert valuation_official_sources._parse_float("") is None
    assert valuation_official_sources._map_tenure("F") == "FREEHOLD"
    assert valuation_official_sources._map_tenure("leasehold") == "LEASEHOLD"
    assert valuation_official_sources._map_tenure("commonhold") == "COMMONHOLD"
    assert valuation_official_sources._map_tenure(None) is None
    assert valuation_official_sources._postcode_district("sw1a 1aa") == "SW1A"
    assert valuation_official_sources._postcode_district(None) is None
    assert valuation_official_sources._compose_address(
        {
            "street": "1 Example Mews",
            "town": "London",
            "postcode": "NW1 1AA",
        }
    ) == "1 Example Mews, London, NW1 1AA"
    assert valuation_official_sources._compose_address({}) is None
