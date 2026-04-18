from __future__ import annotations

import base64
import json
import logging
import runpy
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import landintel.config as config_mod
import landintel.connectors.csv_import as csv_import_mod
import landintel.connectors.html_snapshot as html_snapshot_mod
import landintel.connectors.manual_url as manual_url_mod
import landintel.connectors.public_page as public_page_mod
import landintel.db.session as db_session_mod
import landintel.geospatial.bootstrap as geo_bootstrap
import landintel.geospatial.reference_data as reference_data_mod
import landintel.logging as logging_mod
import landintel.monitoring.metrics as metrics_mod
import landintel.planning.bootstrap as planning_bootstrap
import landintel.planning.planning_register_normalize as planning_register_normalize_mod
import landintel.planning.pld_ingest as pld_ingest_mod
import landintel.planning.reference_layers as reference_layers_mod
import landintel.storage.factory as storage_factory_mod
import landintel.valuation.assumptions as valuation_assumptions_mod
import landintel.valuation.bootstrap as valuation_bootstrap
import landintel.valuation.market as valuation_market_mod
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from landintel.auth import session as auth_session
from landintel.config import Settings
from landintel.connectors.base import (
    ConnectorAsset,
    ConnectorContext,
    ConnectorRunOutput,
    FetchedAsset,
    ListingConnector,
    ParsedListing,
)
from landintel.connectors.csv_import import CsvImportConnector
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.connectors.manual_url import ManualUrlConnector
from landintel.connectors.page_capture import capture_listing_page
from landintel.connectors.public_page import GenericPublicPageConnector, _discover_listing_links
from landintel.domain.enums import (
    AppRoleName,
    ConnectorType,
    DocumentType,
    ListingStatus,
    PriceBasisType,
    SourceParseStatus,
    StorageBackend,
)
from landintel.logging import JsonFormatter, configure_logging
from landintel.storage.base import StorageAdapter
from landintel.storage.factory import build_storage
from landintel.storage.local import LocalFileStorageAdapter
from landintel.storage.supabase import SupabaseStorageAdapter
from starlette.requests import Request


def _make_request(
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    raw_headers: list[tuple[bytes, bytes]] = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode("latin-1")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": raw_headers,
    }
    return Request(scope)


def _make_token(payload: dict[str, object], *, secret: str) -> str:
    payload_part = auth_session._encode_base64url(json.dumps(payload).encode("utf-8"))
    signature = auth_session._sign_payload(payload_part, secret)
    return f"{payload_part}.{signature}"


def _make_settings(**overrides: object) -> Settings:
    params: dict[str, object] = {
        "app_env": "test",
        "database_url": "sqlite:///tmp/test.db",
        "web_auth_session_secret": "test-secret",
        "web_auth_session_cookie_name": "custom-session",
        "storage_local_root": "/tmp/landintel-test-storage",
    }
    params.update(overrides)
    return Settings(**params)


def _make_context(*, refresh_policy_json: dict[str, object] | None = None) -> ConnectorContext:
    return ConnectorContext(
        source_name="fixture-source",
        connector_type=ConnectorType.PUBLIC_PAGE,
        refresh_policy_json=refresh_policy_json or {},
        requested_by="pytest",
    )


class _SessionContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> _SessionContext:
        self.events.append("enter")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.events.append("exit")
        return False

    def commit(self) -> None:
        self.events.append("commit")


def _patch_bootstrap_common(monkeypatch: pytest.MonkeyPatch, target_module) -> list[str]:
    events: list[str] = []
    settings = _make_settings()
    monkeypatch.setattr(target_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        target_module,
        "get_session_factory",
        lambda *_args, **_kwargs: lambda: _SessionContext(events),
    )
    monkeypatch.setattr(target_module, "build_storage", lambda _settings: "storage")
    return events


def _patch_bootstrap_common_for_run_module(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    events: list[str] = []
    settings = _make_settings()
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(
        db_session_mod,
        "get_session_factory",
        lambda *_args, **_kwargs: lambda: _SessionContext(events),
    )
    monkeypatch.setattr(storage_factory_mod, "build_storage", lambda _settings: "storage")
    return events


def test_auth_session_resolution_and_helpers_cover_all_branches() -> None:
    settings = _make_settings()
    expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    no_token_actor = auth_session.resolve_request_actor(
        request=_make_request(),
        settings=settings,
    )
    assert no_token_actor.role is AppRoleName.ANALYST
    assert no_token_actor.authenticated is False

    valid_token = _make_token(
        {
            "user": {
                "role": " reviewer ",
                "id": "  user-1  ",
                "email": "  user@example.com ",
                "name": "  Test User  ",
            },
            "expiresAt": expires_at,
        },
        secret=settings.web_auth_session_secret,
    )
    actor = auth_session.resolve_request_actor(
        request=_make_request(headers={auth_session.SESSION_HEADER_NAME: valid_token}),
        settings=settings,
    )
    assert actor.role is AppRoleName.REVIEWER
    assert actor.authenticated is True
    assert actor.user_id == "user-1"
    assert actor.user_email == "user@example.com"
    assert actor.user_name == "Test User"
    assert auth_session.resolve_request_actor_name(actor, "fallback") == "Test User"

    cookie_actor = auth_session.resolve_request_actor(
        request=_make_request(cookies={settings.web_auth_session_cookie_name: valid_token}),
        settings=settings,
    )
    assert cookie_actor.authenticated is True

    legacy_cookie_actor = auth_session.resolve_request_actor(
        request=_make_request(cookies={"__Host-landintel-session": valid_token}),
        settings=settings,
    )
    assert legacy_cookie_actor.authenticated is True

    invalid_signature = auth_session.resolve_request_actor(
        request=_make_request(headers={auth_session.SESSION_HEADER_NAME: f"{valid_token}broken"}),
        settings=settings,
    )
    assert invalid_signature.session_error == "INVALID_OR_EXPIRED_SESSION"
    assert invalid_signature.session_token_present is True

    invalid_user_token = _make_token(
        {"user": "bad", "expiresAt": expires_at},
        secret=settings.web_auth_session_secret,
    )
    invalid_user_actor = auth_session.resolve_request_actor(
        request=_make_request(headers={auth_session.SESSION_HEADER_NAME: invalid_user_token}),
        settings=settings,
    )
    assert invalid_user_actor.session_error == "INVALID_SESSION_USER"

    invalid_role_token = _make_token(
        {"user": {"role": "boss"}, "expiresAt": expires_at},
        secret=settings.web_auth_session_secret,
    )
    invalid_role_actor = auth_session.resolve_request_actor(
        request=_make_request(headers={auth_session.SESSION_HEADER_NAME: invalid_role_token}),
        settings=settings,
    )
    assert invalid_role_actor.session_error == "INVALID_SESSION_ROLE"

    assert (
        auth_session.resolve_request_actor_name(
            auth_session.RequestActor(
                role=AppRoleName.ANALYST,
                authenticated=False,
                user_email="user@example.com",
            ),
            "fallback",
        )
        == "user@example.com"
    )
    assert (
        auth_session.resolve_request_actor_name(
            auth_session.RequestActor(
                role=AppRoleName.ANALYST,
                authenticated=False,
                user_id="user-123",
            ),
            "fallback",
        )
        == "user-123"
    )
    assert (
        auth_session.resolve_request_actor_name(
            auth_session.RequestActor(role=AppRoleName.ANALYST, authenticated=False),
            "fallback",
        )
        == "fallback"
    )

    assert auth_session.role_at_least(AppRoleName.REVIEWER, AppRoleName.ANALYST) is True
    assert auth_session.role_at_least(AppRoleName.ANALYST, AppRoleName.ADMIN) is False
    assert auth_session._split_token("missing") == (None, None)
    assert auth_session._split_token(" .sig") == (None, None)
    assert auth_session._split_token("payload. ") == (None, None)

    bad_json_payload = auth_session._encode_base64url(b"{")
    bad_json_token = (
        f"{bad_json_payload}."
        f"{auth_session._sign_payload(bad_json_payload, settings.web_auth_session_secret)}"
    )
    assert (
        auth_session._decode_session_token(
            token=bad_json_token,
            secret=settings.web_auth_session_secret,
        )
        is None
    )

    list_payload = auth_session._encode_base64url(
        json.dumps(["not", "a", "dict"]).encode("utf-8")
    )
    list_token = (
        f"{list_payload}."
        f"{auth_session._sign_payload(list_payload, settings.web_auth_session_secret)}"
    )
    assert (
        auth_session._decode_session_token(
            token=list_token,
            secret=settings.web_auth_session_secret,
        )
        is None
    )

    expired_token = _make_token(
        {
            "user": {"role": "analyst"},
            "expiresAt": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        },
        secret=settings.web_auth_session_secret,
    )
    assert (
        auth_session._decode_session_token(
            token=expired_token,
            secret=settings.web_auth_session_secret,
        )
        is None
    )
    assert (
        auth_session._decode_session_token(
            token="bad.token", secret=settings.web_auth_session_secret
        )
        is None
    )

    assert auth_session._parse_datetime(None) is None
    assert auth_session._parse_datetime("") is None
    assert auth_session._parse_datetime("not-a-date") is None
    naive = auth_session._parse_datetime("2026-04-18T10:00:00")
    assert naive is not None and naive.tzinfo is UTC
    aware = auth_session._parse_datetime("2026-04-18T10:00:00Z")
    assert aware is not None and aware.tzinfo is UTC

    assert auth_session._normalize_optional_text(None) is None
    assert auth_session._normalize_optional_text("   ") is None
    assert auth_session._normalize_optional_text("  hello  ") == "hello"


def test_config_validation_and_local_database_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    assert config_mod._is_local_database_url("sqlite:///tmp/test.db") is True
    assert config_mod._is_local_database_url("postgresql+psycopg://u:p@localhost:5432/db") is True
    assert (
        config_mod._is_local_database_url("postgresql+psycopg://u:p@db.example.com:5432/db")
        is False
    )

    with pytest.raises(ValueError, match="non-default value outside local dev"):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://u:p@db.example.com:5432/db",
        )

    monkeypatch.delenv("APP_ENV", raising=False)
    constructed = Settings.model_construct(
        app_env="development",
        database_url="postgresql+psycopg://u:p@db.example.com:5432/db",
        web_auth_session_secret=config_mod.DEFAULT_WEB_AUTH_SESSION_SECRET,
        database_echo=False,
        storage_backend=StorageBackend.LOCAL,
        storage_local_root="/tmp/landintel-test-storage",
        web_auth_session_cookie_name="landintel-session",
        _fields_set={"database_url", "web_auth_session_secret"},
    )
    with pytest.raises(ValueError, match="APP_ENV must be set explicitly"):
        Settings.validate_web_auth_session_secret(constructed)


def test_db_session_helpers_cover_cached_paths_and_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    sqlite_engine = db_session_mod.create_sqlalchemy_engine("sqlite:///tmp/test.db")
    postgres_engine = db_session_mod.create_sqlalchemy_engine(
        "postgresql+psycopg://landintel:landintel@localhost:5432/landintel"
    )
    assert sqlite_engine.dialect.name == "sqlite"
    assert postgres_engine.url.drivername == "postgresql+psycopg"

    created: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        db_session_mod,
        "get_settings",
        lambda: _make_settings(database_url="sqlite:///cached.db", database_echo=True),
    )
    monkeypatch.setattr(
        db_session_mod,
        "create_sqlalchemy_engine",
        lambda database_url, *, echo=False: created.append((database_url, echo))
        or f"engine:{database_url}:{echo}",
    )
    db_session_mod.get_engine.cache_clear()
    engine = db_session_mod.get_engine()
    assert engine == "engine:sqlite:///cached.db:True"
    assert created == [("sqlite:///cached.db", True)]

    monkeypatch.setattr(
        db_session_mod,
        "get_engine",
        lambda database_url=None, echo=None: f"cached:{database_url}:{echo}",
    )
    db_session_mod.get_session_factory.cache_clear()
    factory = db_session_mod.get_session_factory()
    assert factory.kw["bind"] == "cached:sqlite:///cached.db:True"

    commit_events: list[str] = []

    class FakeSession:
        def commit(self) -> None:
            commit_events.append("commit")

        def rollback(self) -> None:
            commit_events.append("rollback")

        def close(self) -> None:
            commit_events.append("close")

    with db_session_mod.session_scope(lambda: FakeSession()) as session:
        assert isinstance(session, FakeSession)
    assert commit_events == ["commit", "close"]

    rollback_events: list[str] = []

    class FailingSession:
        def commit(self) -> None:
            rollback_events.append("commit")

        def rollback(self) -> None:
            rollback_events.append("rollback")

        def close(self) -> None:
            rollback_events.append("close")

    with pytest.raises(RuntimeError, match="boom"), db_session_mod.session_scope(
        lambda: FailingSession()
    ):
        raise RuntimeError("boom")
    assert rollback_events == ["rollback", "close"]


def test_storage_adapters_and_factory_cover_error_branches(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = LocalFileStorageAdapter(str(tmp_path))
    stored = adapter.put_bytes("raw/asset.txt", b"alpha", content_type="text/plain")
    assert stored.size_bytes == 5
    same = adapter.put_bytes("raw/asset.txt", b"alpha", content_type="text/plain")
    assert same.storage_path == "raw/asset.txt"
    assert adapter.get_bytes("raw/asset.txt") == b"alpha"
    with pytest.raises(ValueError, match="immutable raw asset"):
        adapter.put_bytes("raw/asset.txt", b"beta", content_type="text/plain")

    class RaisingAdapter(StorageAdapter):
        def put_bytes(self, storage_path: str, payload: bytes, *, content_type: str):
            return super().put_bytes(storage_path, payload, content_type=content_type)

        def get_bytes(self, storage_path: str) -> bytes:
            return super().get_bytes(storage_path)

    raising = RaisingAdapter()
    with pytest.raises(NotImplementedError):
        raising.put_bytes("x", b"y", content_type="text/plain")
    with pytest.raises(NotImplementedError):
        raising.get_bytes("x")

    local_storage = build_storage(
        _make_settings(storage_backend=StorageBackend.LOCAL, storage_local_root=str(tmp_path))
    )
    assert isinstance(local_storage, LocalFileStorageAdapter)
    supabase_storage = build_storage(
        _make_settings(
            storage_backend=StorageBackend.SUPABASE,
            supabase_url="https://supabase.example.com",
            supabase_service_role_key="service-role",
        )
    )
    assert isinstance(supabase_storage, SupabaseStorageAdapter)
    with pytest.raises(ValueError, match="Unsupported storage backend"):
        build_storage(SimpleNamespace(storage_backend="bad", storage_local_root=str(tmp_path)))

    with pytest.raises(ValueError, match="Supabase storage requires"):
        SupabaseStorageAdapter(
            _make_settings(
                storage_backend=StorageBackend.SUPABASE,
                supabase_url=None,
                supabase_service_role_key=None,
            )
        )

    settings = _make_settings(
        storage_backend=StorageBackend.SUPABASE,
        supabase_url="https://supabase.example.com",
        supabase_service_role_key="service-role",
    )
    supabase = SupabaseStorageAdapter(settings)

    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: SimpleNamespace(status_code=500, text="upload failed"),
    )
    with pytest.raises(RuntimeError, match="upload failed"):
        supabase.put_bytes("raw/test.txt", b"body", content_type="text/plain")

    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: SimpleNamespace(status_code=201, text="ok"),
    )
    stored_object = supabase.put_bytes("raw/test.txt", b"body", content_type="text/plain")
    assert stored_object.size_bytes == 4

    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: SimpleNamespace(status_code=404, text="missing", content=b""),
    )
    with pytest.raises(FileNotFoundError):
        supabase.get_bytes("raw/test.txt")

    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: SimpleNamespace(status_code=503, text="unavailable", content=b""),
    )
    with pytest.raises(RuntimeError, match="unavailable"):
        supabase.get_bytes("raw/test.txt")

    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: SimpleNamespace(status_code=200, text="ok", content=b"payload"),
    )
    assert supabase.get_bytes("raw/test.txt") == b"payload"


def test_logging_and_metrics_cover_all_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "landintel", logging.INFO, __file__, 10, "hello %s", ("world",), None
    )
    record.detail = "detail"
    record.worker_id = "worker-1"
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "hello world"
    assert payload["detail"] == "detail"
    assert payload["worker_id"] == "worker-1"

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    init_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        logging_mod.sentry_sdk,
        "init",
        lambda **kwargs: init_calls.append((kwargs["dsn"], kwargs["environment"])),
    )
    try:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root_logger.handlers = [handler]
        configure_logging(_make_settings(log_level="debug", sentry_dsn="https://dsn.example.com"))
        assert init_calls == []

        root_logger.handlers = []
        configure_logging(_make_settings(log_level="warning", sentry_dsn="https://dsn.example.com"))
        assert root_logger.level == logging.WARNING
        assert any(isinstance(handler.formatter, JsonFormatter) for handler in root_logger.handlers)
        assert init_calls == [("https://dsn.example.com", "test")]
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)

    app = FastAPI()
    metrics_mod.register_fastapi_metrics(app)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/ok")
    assert response.status_code == 200

    metrics_response = metrics_mod.metrics_response()
    assert metrics_response.media_type.startswith("text/plain")
    assert metrics_response.body

    class FakeGauge:
        def __init__(self) -> None:
            self.values: list[tuple[str | None, float]] = []

        def set(self, value: float) -> None:
            self.values.append((None, value))

        def labels(self, *, quality: str):
            return SimpleNamespace(set=lambda value: self.values.append((quality, value)))

    uplift = FakeGauge()
    asking = FakeGauge()
    quality = FakeGauge()
    monkeypatch.setattr(metrics_mod, "UPLIFT_NULL_RATE", uplift)
    monkeypatch.setattr(metrics_mod, "ASKING_PRICE_MISSING_RATE", asking)
    monkeypatch.setattr(metrics_mod, "VALUATION_QUALITY_TOTAL", quality)

    metrics_mod.update_valuation_metrics(
        {
            "uplift_null_rate": 0.25,
            "asking_price_missing_rate": 0.5,
            "valuation_quality_distribution": {"HIGH": 2, "LOW": "ignore"},
        }
    )
    metrics_mod.update_valuation_metrics(
        {
            "uplift_null_rate": "skip",
            "asking_price_missing_rate": None,
            "valuation_quality_distribution": ["not-a-dict"],
        }
    )
    assert uplift.values == [(None, 0.25)]
    assert asking.values == [(None, 0.5)]
    assert quality.values == [("HIGH", 2.0)]


def test_html_snapshot_fetcher_covers_html_non_html_and_fetch_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        SimpleNamespace(
            headers={"content-type": "text/html"},
            text="<html><title> Listing </title></html>",
            content=b"<html><title> Listing </title></html>",
            status_code=200,
            url="https://example.com/listing",
            raise_for_status=lambda: None,
        ),
        SimpleNamespace(
            headers={"content-type": "application/pdf"},
            text="",
            content=b"%PDF-1.7",
            status_code=200,
            url="https://example.com/brochure.pdf",
            raise_for_status=lambda: None,
        ),
    ]

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str):
            return responses.pop(0)

    monkeypatch.setattr(html_snapshot_mod.httpx, "Client", lambda **kwargs: FakeClient(**kwargs))
    fetcher = HtmlSnapshotFetcher(_make_settings(snapshot_http_timeout_seconds=9))

    html_asset = fetcher.fetch_asset("https://example.com/listing")
    assert html_asset.page_title == "Listing"
    pdf_asset = fetcher.fetch_asset("https://example.com/brochure.pdf")
    assert pdf_asset.page_title is None

    sentinel = SimpleNamespace(final_url="https://example.com")
    monkeypatch.setattr(fetcher, "fetch_asset", lambda url: sentinel)
    assert fetcher.fetch("https://example.com") is sentinel


def test_csv_import_connector_covers_success_and_failed_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    fetcher = SimpleNamespace(
        fetch_asset=lambda url: FetchedAsset(
            requested_url=url,
            final_url=url,
            content=b"document",
            content_type="application/pdf",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "application/pdf"},
            page_title=None,
        )
    )
    connector = CsvImportConnector(fetcher)
    context = ConnectorContext(
        source_name="csv-source",
        connector_type=ConnectorType.CSV_IMPORT,
        refresh_policy_json={},
        requested_by="pytest",
    )

    monkeypatch.setattr(csv_import_mod, "parse_csv_rows", lambda csv_text, source_name: [])
    failed = connector.run(
        context=context,
        payload={"csv_base64": base64.b64encode(b"id\n").decode("ascii"), "filename": "empty.csv"},
    )
    assert failed.parse_status is SourceParseStatus.FAILED
    assert failed.manifest_json["row_count"] == 0
    assert failed.assets[0].metadata["filename"] == "empty.csv"

    listing = ParsedListing(
        source_listing_id="listing-1",
        canonical_url="https://example.com/listing-1",
        observed_at=now,
        status=ListingStatus.LIVE,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        raw_record_json={
            "brochure_url": "https://example.com/brochure.pdf",
            "map_url": "https://example.com/map.pdf",
        },
    )
    monkeypatch.setattr(csv_import_mod, "parse_csv_rows", lambda csv_text, source_name: [listing])
    parsed = connector.run(
        context=context,
        payload={
            "csv_base64": base64.b64encode(b"id\n1\n").decode("ascii"),
            "filename": "listing.csv",
        },
    )
    assert parsed.parse_status is SourceParseStatus.PARSED
    assert parsed.coverage_note == "CSV import captured 1 listing rows."
    assert listing.brochure_asset_key == "csv_row_1_document_1"
    assert listing.map_asset_key == "csv_row_1_document_2"
    assert [asset.role for asset in parsed.assets[1:]] == [
        DocumentType.BROCHURE.value,
        DocumentType.MAP.value,
    ]


def test_public_page_connector_covers_discovery_dedup_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    fetch_assets = {
        "https://example.com/seed": FetchedAsset(
            requested_url="https://example.com/seed",
            final_url="https://example.com/seed",
            content=(
                b"<html><title>Seed</title><body>"
                b'<a href="/listing/1">One</a>'
                b'<a href="https://example.com/listing/1">Duplicate</a>'
                b'<a href="/skip/2">Skip</a>'
                b"<a>No href</a>"
                b"</body></html>"
            ),
            content_type="text/html",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "text/html"},
            page_title="Seed",
        ),
        "https://example.com/empty": FetchedAsset(
            requested_url="https://example.com/empty",
            final_url="https://example.com/empty",
            content=b"<html><title>Empty</title><body><a>No href</a></body></html>",
            content_type="text/html",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "text/html"},
            page_title="Empty",
        ),
    }
    fetcher = SimpleNamespace(fetch_asset=lambda url: fetch_assets[url])
    connector = GenericPublicPageConnector(fetcher)

    with pytest.raises(ValueError, match="seed_urls"):
        connector.run(context=_make_context(), payload={})

    captured_calls: list[str] = []
    monkeypatch.setattr(
        public_page_mod,
        "capture_listing_page",
        lambda *, fetcher, url, asset_prefix: captured_calls.append(url)
        or SimpleNamespace(
            assets=[
                ConnectorAsset(
                    asset_key=f"{asset_prefix}_html",
                    asset_type="HTML",
                    role="LISTING_PAGE",
                    original_url=url,
                    content=b"<html></html>",
                    content_type="text/html",
                    fetched_at=now,
                    metadata={},
                )
            ],
            listing=ParsedListing(
                source_listing_id=asset_prefix,
                canonical_url=url,
                observed_at=now,
            ),
        ),
    )

    parsed = connector.run(
        context=_make_context(
            refresh_policy_json={
                "seed_urls": ["https://example.com/seed"],
                "listing_link_selector": "a",
                "listing_url_patterns": [r"/listing/"],
                "max_listings": 1,
            }
        ),
        payload={},
    )
    assert parsed.parse_status is SourceParseStatus.PARSED
    assert captured_calls == ["https://example.com/listing/1"]
    assert parsed.manifest_json["listing_urls"] == ["https://example.com/listing/1"]

    no_selector = connector.run(
        context=_make_context(refresh_policy_json={"seed_urls": ["https://example.com/seed"]}),
        payload={},
    )
    assert no_selector.manifest_json["listing_urls"] == ["https://example.com/seed"]

    failed = connector.run(
        context=_make_context(
            refresh_policy_json={
                "seed_urls": ["https://example.com/empty"],
                "listing_link_selector": "a",
            }
        ),
        payload={},
    )
    assert failed.parse_status is SourceParseStatus.FAILED
    assert failed.observed_at == now

    discovered = _discover_listing_links(
        html='<a href="/listing/2">Two</a><a href="/other/3">Other</a><a>No href</a>',
        base_url="https://example.com/root",
        selector="a",
        patterns=[],
    )
    assert discovered == ["https://example.com/listing/2", "https://example.com/other/3"]


def test_listing_connector_base_run_raises_not_implemented() -> None:
    class IncompleteConnector(ListingConnector):
        connector_type = ConnectorType.MANUAL_URL

        def run(
            self, *, context: ConnectorContext, payload: dict[str, object]
        ) -> ConnectorRunOutput:
            return super().run(context=context, payload=payload)

    with pytest.raises(NotImplementedError):
        IncompleteConnector().run(context=_make_context(), payload={})


@pytest.mark.parametrize(
    ("dataset", "expected_calls"),
    [
        ("lpa", ["lpa"]),
        ("titles", ["titles"]),
        ("all", ["lpa", "titles"]),
    ],
)
def test_geospatial_bootstrap_main_covers_all_datasets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dataset: str,
    expected_calls: list[str],
) -> None:
    labels = {
        "lpa": "Imported LPA boundaries",
        "titles": "Imported title polygons",
    }
    events = _patch_bootstrap_common(monkeypatch, geo_bootstrap)
    calls: list[str] = []
    monkeypatch.setattr(
        geo_bootstrap,
        "import_lpa_boundaries",
        lambda **kwargs: calls.append("lpa")
        or SimpleNamespace(source_snapshot_id=1, imported_count=2),
    )
    monkeypatch.setattr(
        geo_bootstrap,
        "import_hmlr_title_polygons",
        lambda **kwargs: calls.append("titles")
        or SimpleNamespace(source_snapshot_id=2, imported_count=3),
    )
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--dataset", dataset])
    geo_bootstrap.main()
    assert calls == expected_calls
    assert events == ["enter", "commit", "exit"]
    output = capsys.readouterr().out
    for expected in expected_calls:
        assert labels[expected] in output


@pytest.mark.parametrize(
    ("dataset", "expected_calls"),
    [
        ("pld", ["pld"]),
        ("borough-register", ["borough-register"]),
        ("brownfield", ["brownfield"]),
        ("policy", ["policy"]),
        ("constraints", ["constraints"]),
        ("flood", ["flood"]),
        ("heritage-article4", ["heritage"]),
        ("baseline-pack", ["baseline"]),
        (
            "all",
            [
                "pld",
                "borough-register",
                "brownfield",
                "policy",
                "constraints",
                "flood",
                "heritage",
                "baseline",
            ],
        ),
    ],
)
def test_planning_bootstrap_main_covers_all_datasets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dataset: str,
    expected_calls: list[str],
) -> None:
    labels = {
        "pld": "Imported PLD fixture",
        "borough-register": "Imported borough-register fixture",
        "brownfield": "Imported brownfield fixture",
        "policy": "Imported policy fixture",
        "constraints": "Imported constraint fixture",
        "flood": "Imported flood fixture",
        "heritage": "Imported heritage/article4 fixture",
        "baseline": "Imported baseline-pack fixture",
    }
    events = _patch_bootstrap_common(monkeypatch, planning_bootstrap)
    calls: list[str] = []

    def _result(label: str) -> SimpleNamespace:
        calls.append(label)
        return SimpleNamespace(source_snapshot_id=10, imported_count=20, coverage_count=30)

    monkeypatch.setattr(planning_bootstrap, "import_pld_fixture", lambda **kwargs: _result("pld"))
    monkeypatch.setattr(
        planning_bootstrap,
        "import_borough_register_fixture",
        lambda **kwargs: _result("borough-register"),
    )
    monkeypatch.setattr(
        planning_bootstrap, "import_brownfield_fixture", lambda **kwargs: _result("brownfield")
    )
    monkeypatch.setattr(
        planning_bootstrap, "import_policy_area_fixture", lambda **kwargs: _result("policy")
    )
    monkeypatch.setattr(
        planning_bootstrap, "import_constraint_fixture", lambda **kwargs: _result("constraints")
    )
    monkeypatch.setattr(
        planning_bootstrap, "import_flood_fixture", lambda **kwargs: _result("flood")
    )
    monkeypatch.setattr(
        planning_bootstrap,
        "import_heritage_article4_fixture",
        lambda **kwargs: _result("heritage"),
    )
    monkeypatch.setattr(
        planning_bootstrap,
        "import_baseline_pack_fixture",
        lambda **kwargs: _result("baseline"),
    )
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--dataset", dataset])
    planning_bootstrap.main()
    assert calls == expected_calls
    assert events == ["enter", "commit", "exit"]
    output = capsys.readouterr().out
    for expected in expected_calls:
        assert labels[expected] in output


@pytest.mark.parametrize(
    ("dataset", "expected_calls"),
    [
        ("assumptions", ["assumptions"]),
        ("hmlr-price-paid", ["hmlr"]),
        ("ukhpi", ["ukhpi"]),
        ("land-comps", ["land-comps"]),
        ("all", ["assumptions", "hmlr", "ukhpi", "land-comps"]),
    ],
)
def test_valuation_bootstrap_main_covers_all_datasets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dataset: str,
    expected_calls: list[str],
) -> None:
    labels = {
        "assumptions": "Seeded valuation assumptions",
        "hmlr": "Imported HMLR Price Paid fixture",
        "ukhpi": "Imported UKHPI fixture",
        "land-comps": "Imported land comps fixture",
    }
    events = _patch_bootstrap_common(monkeypatch, valuation_bootstrap)
    calls: list[str] = []

    monkeypatch.setattr(
        valuation_bootstrap,
        "ensure_default_assumption_set",
        lambda session: calls.append("assumptions") or SimpleNamespace(version="v1", id=1),
    )

    def _result(label: str) -> SimpleNamespace:
        calls.append(label)
        return SimpleNamespace(source_snapshot_id=10, imported_count=20, coverage_count=30)

    monkeypatch.setattr(
        valuation_bootstrap,
        "import_hmlr_price_paid_fixture",
        lambda **kwargs: _result("hmlr"),
    )
    monkeypatch.setattr(
        valuation_bootstrap, "import_ukhpi_fixture", lambda **kwargs: _result("ukhpi")
    )
    monkeypatch.setattr(
        valuation_bootstrap,
        "import_land_comp_fixture",
        lambda **kwargs: _result("land-comps"),
    )
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--dataset", dataset])
    valuation_bootstrap.main()
    assert calls == expected_calls
    assert events == ["enter", "commit", "exit"]
    output = capsys.readouterr().out
    for expected in expected_calls:
        assert labels[expected] in output


@pytest.mark.parametrize(
    ("module_name", "argv", "patches"),
    [
        (
            "landintel.geospatial.bootstrap",
            ["bootstrap", "--dataset", "titles"],
            lambda monkeypatch: (
                _patch_bootstrap_common_for_run_module(monkeypatch),
                monkeypatch.setattr(
                    reference_data_mod,
                    "import_lpa_boundaries",
                    lambda **kwargs: SimpleNamespace(source_snapshot_id=1, imported_count=2),
                ),
                monkeypatch.setattr(
                    reference_data_mod,
                    "import_hmlr_title_polygons",
                    lambda **kwargs: SimpleNamespace(source_snapshot_id=2, imported_count=3),
                ),
            ),
        ),
        (
            "landintel.planning.bootstrap",
            ["bootstrap", "--dataset", "policy"],
            lambda monkeypatch: (
                _patch_bootstrap_common_for_run_module(monkeypatch),
                monkeypatch.setattr(
                    pld_ingest_mod,
                    "import_pld_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    planning_register_normalize_mod,
                    "import_borough_register_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    reference_layers_mod,
                    "import_brownfield_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    reference_layers_mod,
                    "import_policy_area_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    reference_layers_mod,
                    "import_constraint_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    reference_layers_mod,
                    "import_flood_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    reference_layers_mod,
                    "import_heritage_article4_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    reference_layers_mod,
                    "import_baseline_pack_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
            ),
        ),
        (
            "landintel.valuation.bootstrap",
            ["bootstrap", "--dataset", "assumptions"],
            lambda monkeypatch: (
                _patch_bootstrap_common_for_run_module(monkeypatch),
                monkeypatch.setattr(
                    valuation_assumptions_mod,
                    "ensure_default_assumption_set",
                    lambda session: SimpleNamespace(version="v1", id=1),
                ),
                monkeypatch.setattr(
                    valuation_market_mod,
                    "import_hmlr_price_paid_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    valuation_market_mod,
                    "import_ukhpi_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
                monkeypatch.setattr(
                    valuation_market_mod,
                    "import_land_comp_fixture",
                    lambda **kwargs: SimpleNamespace(
                        source_snapshot_id=1, imported_count=2, coverage_count=3
                    ),
                ),
            ),
        ),
    ],
)
def test_bootstrap_module_main_guards_execute(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    module_name: str,
    argv: list[str],
    patches,
) -> None:
    patches(monkeypatch)
    monkeypatch.setattr(sys, "argv", argv)
    sys.modules.pop(module_name, None)
    runpy.run_module(module_name, run_name="__main__")
    assert capsys.readouterr().out


def test_capture_listing_page_collects_html_and_document_assets() -> None:
    now = datetime.now(UTC)
    fetch_assets = {
        "https://example.com/listing": FetchedAsset(
            requested_url="https://example.com/listing",
            final_url="https://example.com/listing",
            content=(
                b"<html><head><title>Listing</title></head><body>"
                b'<a href="/brochure.pdf">Brochure</a>'
                b'<a href="/map.pdf">Map</a>'
                b"</body></html>"
            ),
            content_type="text/html",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "text/html"},
            page_title="Listing",
        ),
        "https://example.com/brochure.pdf": FetchedAsset(
            requested_url="https://example.com/brochure.pdf",
            final_url="https://example.com/brochure.pdf",
            content=b"%PDF-1.7 brochure",
            content_type="application/pdf",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "application/pdf"},
            page_title=None,
        ),
        "https://example.com/map.pdf": FetchedAsset(
            requested_url="https://example.com/map.pdf",
            final_url="https://example.com/map.pdf",
            content=b"%PDF-1.7 map",
            content_type="application/pdf",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "application/pdf"},
            page_title=None,
        ),
    }
    fetcher = SimpleNamespace(fetch_asset=lambda url: fetch_assets[url])

    captured = capture_listing_page(
        fetcher=fetcher,
        url="https://example.com/listing",
        asset_prefix="manual",
    )

    assert captured.listing.canonical_url == "https://example.com/listing"
    assert captured.listing.brochure_asset_key == "manual_document_1"
    assert captured.listing.map_asset_key == "manual_document_2"
    assert [asset.role for asset in captured.assets] == [
        "LISTING_PAGE",
        DocumentType.BROCHURE.value,
        DocumentType.MAP.value,
    ]


def test_capture_listing_page_handles_missing_document_links() -> None:
    now = datetime.now(UTC)
    fetcher = SimpleNamespace(
        fetch_asset=lambda url: FetchedAsset(
            requested_url=url,
            final_url=url,
            content=b"<html><head><title>Listing</title></head><body></body></html>",
            content_type="text/html",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "text/html"},
            page_title="Listing",
        )
    )

    captured = capture_listing_page(
        fetcher=fetcher,
        url="https://example.com/listing",
        asset_prefix="manual",
    )

    assert captured.listing.brochure_asset_key is None
    assert captured.listing.map_asset_key is None
    assert len(captured.assets) == 1


@pytest.mark.parametrize(
    ("search_text", "headline", "expected_status"),
    [
        ("headline", None, SourceParseStatus.PARSED),
        ("", None, SourceParseStatus.PARTIAL),
    ],
)
def test_manual_url_connector_uses_captured_listing_status(
    monkeypatch: pytest.MonkeyPatch,
    search_text: str,
    headline: str | None,
    expected_status: SourceParseStatus,
) -> None:
    now = datetime.now(UTC)
    captured = SimpleNamespace(
        listing=SimpleNamespace(
            canonical_url="https://example.com/listing",
            observed_at=now,
            search_text=search_text,
            headline=headline,
        ),
        assets=[
            SimpleNamespace(asset_type="HTML"),
            SimpleNamespace(asset_type="PDF"),
        ],
    )
    monkeypatch.setattr(manual_url_mod, "capture_listing_page", lambda **kwargs: captured)
    connector = ManualUrlConnector(fetcher=SimpleNamespace())
    context = ConnectorContext(
        source_name="manual_url",
        connector_type=ConnectorType.MANUAL_URL,
        refresh_policy_json={},
        requested_by="pytest",
    )

    output = connector.run(
        context=context,
        payload={"url": "https://example.com/listing"},
    )

    assert output.parse_status is expected_status
    assert output.source_uri == "https://example.com/listing"
    assert output.coverage_note.startswith("Manual URL intake")
    assert output.manifest_json["asset_count"] == 2
    assert output.manifest_json["document_count"] == 1
