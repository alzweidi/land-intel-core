from __future__ import annotations

import base64
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from landintel.connectors.base import ConnectorRunOutput, ParsedListing
from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    DocumentExtractionStatus,
    DocumentType,
    GeomSourceType,
    JobStatus,
    JobType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SourceParseStatus,
)
from landintel.domain.models import (
    JobRun,
    ListingCluster,
    ListingItem,
    ListingSnapshot,
    ListingSource,
)
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.jobs import service as job_service
from landintel.listings import clustering as clustering_service
from landintel.listings import documents as document_service
from landintel.listings import parsing as parsing_service
from landintel.listings import service as listings_service


class _Result:
    def __init__(self, *, item=None, items=None, scalar=None):
        self._item = item
        self._items = list(items or [])
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._item

    def scalar_one(self):
        return self._scalar

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _QueueSession:
    def __init__(self, results=None, get_result=None):
        self.results = deque(results or [])
        self.get_result = get_result
        self.executed = []
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.bind = None

    def execute(self, stmt):
        self.executed.append(stmt)
        if self.results:
            return self.results.popleft()
        return _Result()

    def get(self, model, identity):
        self.executed.append((model, identity))
        return self.get_result

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1


class _DummyStmt:
    def __init__(self):
        self.with_for_update_called = False
        self.skip_locked = None

    def limit(self, value):
        self.limit_value = value
        return self

    def with_for_update(self, *, skip_locked: bool):
        self.with_for_update_called = True
        self.skip_locked = skip_locked
        return self


class _FitzPage:
    def __init__(self, text: str):
        self._text = text

    def get_text(self, mode: str):
        assert mode == "text"
        return self._text


class _FitzDocument:
    def __init__(self, pages: list[str]):
        self.page_count = len(pages)
        self._pages = [_FitzPage(text) for text in pages]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def __iter__(self):
        return iter(self._pages)


def _job(*, job_type: JobType, payload_json: dict[str, object], attempts: int = 0) -> JobRun:
    now = datetime.now(UTC)
    return JobRun(
        job_type=job_type,
        payload_json=payload_json,
        status=JobStatus.QUEUED,
        run_at=now,
        next_run_at=now,
        requested_by="pytest",
        attempts=attempts,
    )


def test_job_service_enqueue_helpers_cover_payloads_and_deduping(db_session):
    csv_bytes = b"headline,address\nSite,1 Test Road"
    cases = [
        (
            job_service.enqueue_manual_url_job,
            {
                "url": "https://example.com/listing",
                "source_name": "manual_url",
                "requested_by": "pytest",
            },
            JobType.MANUAL_URL_SNAPSHOT,
            {"url": "https://example.com/listing", "source_name": "manual_url"},
        ),
        (
            job_service.enqueue_csv_import_job,
            {
                "source_name": "csv_import",
                "filename": "listings.csv",
                "csv_bytes": csv_bytes,
                "requested_by": "pytest",
            },
            JobType.CSV_IMPORT_SNAPSHOT,
            {
                "source_name": "csv_import",
                "filename": "listings.csv",
                "csv_base64": base64.b64encode(csv_bytes).decode("ascii"),
            },
        ),
        (
            job_service.enqueue_connector_run_job,
            {"source_name": "public_page", "requested_by": "pytest"},
            JobType.LISTING_SOURCE_RUN,
            {"source_name": "public_page", "dedupe_key": "source:public_page"},
        ),
        (
            job_service.enqueue_cluster_rebuild_job,
            {"requested_by": "pytest"},
            JobType.LISTING_CLUSTER_REBUILD,
            {},
        ),
        (
            job_service.enqueue_site_build_job,
            {"cluster_id": "cluster-1", "requested_by": "pytest"},
            JobType.SITE_BUILD_REFRESH,
            {"cluster_id": "cluster-1", "dedupe_key": "cluster:cluster-1"},
        ),
        (
            job_service.enqueue_site_lpa_refresh_job,
            {"site_id": "site-1", "requested_by": "pytest"},
            JobType.SITE_LPA_LINK_REFRESH,
            {"site_id": "site-1", "dedupe_key": "site:site-1"},
        ),
        (
            job_service.enqueue_site_title_refresh_job,
            {"site_id": "site-1", "requested_by": "pytest"},
            JobType.SITE_TITLE_LINK_REFRESH,
            {"site_id": "site-1", "dedupe_key": "site:site-1"},
        ),
        (
            job_service.enqueue_pld_ingest_job,
            {"requested_by": "pytest"},
            JobType.PLD_INGEST_REFRESH,
            {"dedupe_key": "fixture:default-pld"},
        ),
        (
            job_service.enqueue_borough_register_ingest_job,
            {
                "fixture_path": "fixtures/borough.json",
                "requested_by": "pytest",
                "include_supporting_layers": False,
            },
            JobType.BOROUGH_REGISTER_INGEST,
            {
                "fixture_path": "fixtures/borough.json",
                "include_supporting_layers": False,
                "dedupe_key": "fixture:fixtures/borough.json",
            },
        ),
        (
            job_service.enqueue_site_planning_enrich_job,
            {"site_id": "site-1", "requested_by": "pytest"},
            JobType.SITE_PLANNING_ENRICH,
            {"site_id": "site-1", "dedupe_key": "site:site-1"},
        ),
        (
            job_service.enqueue_site_extant_permission_recheck_job,
            {"site_id": "site-1", "requested_by": "pytest"},
            JobType.SITE_EXTANT_PERMISSION_RECHECK,
            {"site_id": "site-1", "dedupe_key": "site:site-1"},
        ),
        (
            job_service.enqueue_source_coverage_refresh_job,
            {"borough_id": "camden", "requested_by": "pytest"},
            JobType.SOURCE_COVERAGE_REFRESH,
            {"borough_id": "camden", "dedupe_key": "borough:camden"},
        ),
        (
            job_service.enqueue_site_scenario_geometry_refresh_job,
            {"site_id": "site-1", "requested_by": "pytest"},
            JobType.SITE_SCENARIO_GEOMETRY_REFRESH,
            {"site_id": "site-1", "dedupe_key": "site:site-1"},
        ),
        (
            job_service.enqueue_borough_rulepack_scenario_refresh_job,
            {"borough_id": "camden", "requested_by": "pytest"},
            JobType.BOROUGH_RULEPACK_SCENARIO_REFRESH,
            {"borough_id": "camden", "dedupe_key": "borough:camden"},
        ),
        (
            job_service.enqueue_scenario_evidence_refresh_job,
            {"scenario_id": "scenario-1", "requested_by": "pytest"},
            JobType.SCENARIO_EVIDENCE_REFRESH,
            {"scenario_id": "scenario-1", "dedupe_key": "scenario:scenario-1"},
        ),
        (
            job_service.enqueue_historical_label_rebuild_job,
            {"requested_by": "pytest"},
            JobType.HISTORICAL_LABEL_REBUILD,
            {"dedupe_key": "historical-labels:current"},
        ),
        (
            job_service.enqueue_assessment_feature_snapshot_build_job,
            {"assessment_id": "assessment-1", "requested_by": "pytest"},
            JobType.ASSESSMENT_FEATURE_SNAPSHOT_BUILD,
            {"assessment_id": "assessment-1", "dedupe_key": "assessment:assessment-1"},
        ),
        (
            job_service.enqueue_comparable_retrieval_build_job,
            {"assessment_id": "assessment-2", "requested_by": "pytest"},
            JobType.COMPARABLE_RETRIEVAL_BUILD,
            {"assessment_id": "assessment-2", "dedupe_key": "assessment:assessment-2"},
        ),
        (
            job_service.enqueue_replay_verification_batch_job,
            {"requested_by": "pytest"},
            JobType.REPLAY_VERIFICATION_BATCH,
            {"dedupe_key": "replay-verification:current"},
        ),
        (
            job_service.enqueue_gold_set_refresh_job,
            {"requested_by": "pytest"},
            JobType.GOLD_SET_REFRESH,
            {"dedupe_key": "gold-set:current"},
        ),
        (
            job_service.enqueue_valuation_data_refresh_job,
            {"dataset": "ukhpi", "requested_by": "pytest"},
            JobType.VALUATION_DATA_REFRESH,
            {"dataset": "ukhpi", "dedupe_key": "valuation-dataset:ukhpi"},
        ),
        (
            job_service.enqueue_valuation_run_build_job,
            {"assessment_id": "assessment-3", "requested_by": "pytest"},
            JobType.VALUATION_RUN_BUILD,
            {"assessment_id": "assessment-3", "dedupe_key": "assessment:assessment-3"},
        ),
    ]

    for func, kwargs, expected_job_type, expected_payload_subset in cases:
        job = func(db_session, **kwargs)
        assert job.job_type == expected_job_type
        for key, value in expected_payload_subset.items():
            assert job.payload_json[key] == value
        assert job.requested_by == "pytest"

    manual_default = job_service.enqueue_site_scenario_suggest_refresh_job(
        db_session,
        site_id="site-4",
        requested_by=None,
    )
    manual_template = job_service.enqueue_site_scenario_suggest_refresh_job(
        db_session,
        site_id="site-4-template",
        requested_by=None,
        template_keys=["resi_5_9_full", "resi_10_plus_full"],
        manual_seed=True,
    )
    assert manual_default.payload_json == {
        "site_id": "site-4",
        "manual_seed": False,
        "dedupe_key": "site:site-4:all:0",
    }
    assert manual_template.payload_json == {
        "site_id": "site-4-template",
        "manual_seed": True,
        "template_keys": ["resi_5_9_full", "resi_10_plus_full"],
        "dedupe_key": "site:site-4-template:resi_5_9_full,resi_10_plus_full:1",
    }
    assert manual_default.requested_by is None


def test_enqueue_connector_run_job_reuses_existing_queued_job(db_session):
    first = job_service.enqueue_connector_run_job(
        db_session,
        source_name="example_public_page",
        requested_by="pytest",
    )
    second = job_service.enqueue_connector_run_job(
        db_session,
        source_name="example_public_page",
        requested_by="pytest",
    )

    assert first.id == second.id
    assert second.payload_json["dedupe_key"] == "source:example_public_page"


def test_job_service_claim_mark_and_list_jobs_cover_remaining_branches(monkeypatch, db_session):
    job_a = _job(job_type=JobType.HISTORICAL_LABEL_REBUILD, payload_json={"a": 1})
    job_b = _job(job_type=JobType.GOLD_SET_REFRESH, payload_json={"b": 2})
    job_a.created_at = datetime.now(UTC) - timedelta(minutes=2)
    job_b.created_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.add_all([job_a, job_b])
    db_session.commit()

    listed = job_service.list_jobs(db_session, limit=10)
    assert [job.id for job in listed] == [job_b.id, job_a.id]

    class _SessionForClaim:
        def __init__(self, job):
            self.job = job
            self.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
            self.flush_count = 0

        def execute(self, stmt):
            self.stmt = stmt
            return _Result(item=self.job)

        def flush(self):
            self.flush_count += 1

    dummy_stmt = _DummyStmt()
    monkeypatch.setattr(job_service, "_claimable_jobs_stmt", lambda: dummy_stmt)

    claim_session = _SessionForClaim(
        _job(job_type=JobType.HISTORICAL_LABEL_REBUILD, payload_json={})
    )
    claimed = job_service.claim_next_job(claim_session, worker_id="worker-1")
    assert claimed is not None
    assert dummy_stmt.with_for_update_called is True
    assert dummy_stmt.skip_locked is True
    assert claimed.status == JobStatus.RUNNING
    assert claimed.worker_id == "worker-1"
    assert claim_session.flush_count == 1

    empty_session = _SessionForClaim(None)
    assert job_service.claim_next_job(empty_session, worker_id="worker-1") is None

    health_job = _job(
        job_type=JobType.HISTORICAL_LABEL_REBUILD,
        payload_json={},
        attempts=0,
    )
    monkeypatch.setattr(job_service, "utc_now", lambda: datetime(2026, 4, 18, 12, 0, tzinfo=UTC))
    assert (
        job_service.refresh_job_lock(
            _QueueSession(get_result=health_job),
            job_id=health_job.id,
            worker_id="other-worker",
        )
        is False
    )

    session = _QueueSession()
    failed = _job(job_type=JobType.HISTORICAL_LABEL_REBUILD, payload_json={}, attempts=0)
    job_service.mark_job_failed(
        session,
        failed,
        error_text="boom",
        max_attempts=2,
        retry_delay_seconds=15,
    )
    assert failed.status == JobStatus.FAILED
    assert failed.next_run_at == datetime(2026, 4, 18, 12, 0, tzinfo=UTC) + timedelta(seconds=15)

    dead = _job(job_type=JobType.HISTORICAL_LABEL_REBUILD, payload_json={}, attempts=2)
    job_service.mark_job_failed(
        session,
        dead,
        error_text="boom",
        max_attempts=2,
    )
    assert dead.status == JobStatus.DEAD
    assert dead.next_run_at == datetime(2026, 4, 18, 12, 0, tzinfo=UTC)


def test_clustering_branches_cover_edges_and_singletons():
    same_url_a = clustering_service.ClusterListingInput(
        listing_item_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        canonical_url="https://example.com/listing",
        normalized_address="12 example road london",
        headline="Camden Yard Development Opportunity",
        guide_price_gbp=1_250_000,
        lat=51.5362,
        lon=-0.1421,
        document_hashes=("hash-1",),
    )
    same_url_b = clustering_service.ClusterListingInput(
        listing_item_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        canonical_url="https://example.com/listing",
        normalized_address="13 different road london",
        headline="Different headline",
        guide_price_gbp=1_000_000,
        lat=51.5,
        lon=-0.1,
        document_hashes=("hash-2",),
    )
    doc_hash_a = clustering_service.ClusterListingInput(
        listing_item_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        canonical_url="https://example.org/a",
        normalized_address="44 rye lane london",
        headline="Peckham Corner Site",
        guide_price_gbp=875_000,
        lat=51.4680,
        lon=-0.0700,
        document_hashes=("shared-hash",),
    )
    doc_hash_b = clustering_service.ClusterListingInput(
        listing_item_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        canonical_url="https://example.org/b",
        normalized_address="99 other lane london",
        headline="Other headline",
        guide_price_gbp=900_000,
        lat=51.4600,
        lon=-0.0600,
        document_hashes=("shared-hash",),
    )
    address_a = clustering_service.ClusterListingInput(
        listing_item_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        canonical_url="https://example.org/c",
        normalized_address="12 example road london",
        headline="Camden Yard Redevelopment",
        guide_price_gbp=1_250_000,
        lat=51.5362,
        lon=-0.1421,
        document_hashes=(),
    )
    address_b = clustering_service.ClusterListingInput(
        listing_item_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        canonical_url="https://example.org/d",
        normalized_address="12 example road london",
        headline="Camden Yard Redevelopment Scheme",
        guide_price_gbp=1_230_000,
        lat=51.53621,
        lon=-0.14209,
        document_hashes=(),
    )
    geo_a = clustering_service.ClusterListingInput(
        listing_item_id=UUID("11111111-1111-1111-1111-111111111111"),
        canonical_url="https://example.org/e",
        normalized_address="1 one road london",
        headline="South London Site",
        guide_price_gbp=500_000,
        lat=51.5000,
        lon=-0.1200,
        document_hashes=(),
    )
    geo_b = clustering_service.ClusterListingInput(
        listing_item_id=UUID("22222222-2222-2222-2222-222222222222"),
        canonical_url="https://example.org/f",
        normalized_address="2 two road london",
        headline="South London Site",
        guide_price_gbp=510_000,
        lat=51.5002,
        lon=-0.1201,
        document_hashes=(),
    )
    singleton = clustering_service.ClusterListingInput(
        listing_item_id=UUID("33333333-3333-3333-3333-333333333333"),
        canonical_url="https://example.org/g",
        normalized_address="3 three road london",
        headline="Single Site",
        guide_price_gbp=750_000,
        lat=None,
        lon=None,
        document_hashes=(),
    )

    edges = clustering_service.generate_cluster_edges(
        [same_url_a, same_url_b, doc_hash_a, doc_hash_b, address_a, address_b, geo_a, geo_b]
    )
    by_pair = {
        tuple(sorted((edge.left_listing_id, edge.right_listing_id), key=str)): edge
        for edge in edges
    }

    assert (
        by_pair[
            tuple(sorted((same_url_a.listing_item_id, same_url_b.listing_item_id), key=str))
        ].confidence
        == 0.995
    )
    assert (
        "canonical_url_exact"
        in by_pair[
            tuple(sorted((same_url_a.listing_item_id, same_url_b.listing_item_id), key=str))
        ].reasons
    )
    assert (
        "document_hash_exact"
        in by_pair[
            tuple(sorted((doc_hash_a.listing_item_id, doc_hash_b.listing_item_id), key=str))
        ].reasons
    )
    assert (
        "normalized_address_exact"
        in by_pair[
            tuple(sorted((address_a.listing_item_id, address_b.listing_item_id), key=str))
        ].reasons
    )
    assert (
        "coordinates_close"
        in by_pair[tuple(sorted((geo_a.listing_item_id, geo_b.listing_item_id), key=str))].reasons
    )

    clusters = clustering_service.build_clusters([singleton])
    assert len(clusters) == 1
    assert clusters[0].cluster_status == ListingClusterStatus.SINGLETON
    assert clusters[0].members[0].reasons == ["singleton"]
    assert clustering_service.build_clusters([]) == []


def test_extract_pdf_text_covers_success_and_failure(monkeypatch):
    monkeypatch.setattr(
        document_service.fitz, "open", lambda **kwargs: _FitzDocument(["Page 1", "Page 2"])
    )
    success = document_service.extract_pdf_text(b"%PDF-1.4")
    assert success.extraction_status == DocumentExtractionStatus.EXTRACTED
    assert success.extracted_text == "Page 1\n\nPage 2"
    assert success.page_count == 2

    def fail_open(**kwargs):
        raise RuntimeError("bad pdf")

    monkeypatch.setattr(document_service.fitz, "open", fail_open)
    failed = document_service.extract_pdf_text(b"not-a-pdf")
    assert failed.extraction_status == DocumentExtractionStatus.FAILED
    assert failed.extracted_text is None
    assert failed.page_count is None


def test_listing_parser_helpers_cover_edge_cases():
    assert parsing_service.normalize_space(["alpha", "", "beta"]) == "alpha, beta"
    assert (
        parsing_service.normalize_url(" https://example.com/a/?x=1#frag ")
        == "https://example.com/a/?x=1"
    )
    assert parsing_service.normalize_address("12 EXAMPLE Rd, London") == "12 example road london"
    assert parsing_service._clean_title("Savills | Land to the east") == "Land to the east"
    assert parsing_service._is_generic_headline("Local information") is True
    assert parsing_service._is_generic_headline("Real listing headline") is False
    assert parsing_service.build_search_text("A", None, "B") == "A B"
    assert (
        parsing_service.extract_text_content(
            "<html><script>ignore()</script><p>Use this</p></html>"
        )
        == "Use this"
    )
    assert parsing_service.parse_price("£1.2m guide price") == (
        1_200_000,
        PriceBasisType.GUIDE_PRICE,
    )
    assert parsing_service.parse_price("Offers over £500k") == (500_000, PriceBasisType.OFFERS_OVER)
    assert parsing_service.parse_price("Price on application") == (
        None,
        PriceBasisType.PRICE_ON_APPLICATION,
    )
    assert parsing_service.detect_price_basis("Auction guide price") == PriceBasisType.AUCTION_GUIDE
    assert (
        parsing_service.parse_optional_date("Auction 17 April 2026") == datetime(2026, 4, 17).date()
    )
    assert parsing_service.parse_optional_date("not a date") is None
    assert parsing_service.detect_listing_status("Sold STC") == ListingStatus.SOLD_STC
    assert parsing_service.detect_listing_status("Under offer") == ListingStatus.UNDER_OFFER
    assert parsing_service.detect_listing_status("Withdrawn") == ListingStatus.WITHDRAWN
    assert parsing_service.detect_listing_status("Auction") == ListingStatus.AUCTION
    assert parsing_service.detect_listing_status("something live") == ListingStatus.LIVE
    assert parsing_service.detect_listing_status() == ListingStatus.UNKNOWN
    assert parsing_service.detect_listing_type("Garage court") == ListingType.GARAGE_COURT
    assert (
        parsing_service.detect_listing_type("Site with building") == ListingType.LAND_WITH_BUILDING
    )
    assert (
        parsing_service.detect_listing_type("Development opportunity")
        == ListingType.REDEVELOPMENT_SITE
    )
    assert parsing_service.detect_listing_type("Land parcel") == ListingType.LAND
    assert parsing_service.detect_listing_type("No clue") == ListingType.UNKNOWN
    assert parsing_service.extract_coordinates_from_text("51.5000 -0.1000") == (51.5, -0.1)
    assert parsing_service.extract_coordinates_from_text("none") == (None, None)
    assert parsing_service.extract_coordinates_from_html(
        '<script>window.__LOT__={"long_lat":"{\\"lat\\":51.5,\\"lng\\":-0.1}"}</script>'
    ) == (51.5, -0.1)
    assert (
        parsing_service.extract_coordinates_from_html(
            '<div id="map_canvas" data-lat="51.6050293" data-lng="-0.1461130"></div>'
        )
        == (51.6050293, -0.146113)
    )
    assert (
        parsing_service.extract_coordinates_from_html(
            '<a href="https://maps.google.com/?q=51.4122128,-0.0277321">Map</a>'
        )
        == (51.4122128, -0.0277321)
    )

    soup_html = """
    <html>
      <head>
        <script type="application/ld+json">
          [{"name":"Listing A"},{"description":"Description A"}]
        </script>
        <script type="application/ld+json">{"name":"Listing B"}</script>
        <script type="application/ld+json">not json</script>
      </head>
    </html>
    """
    soup = parsing_service.BeautifulSoup(soup_html, "html.parser")
    records = parsing_service._load_json_ld(soup)
    assert [record.get("name") for record in records if "name" in record] == [
        "Listing A",
        "Listing B",
    ]


def test_listing_parser_document_and_listing_rows_cover_fallbacks():
    html = """
    <html>
      <head>
        <title>Savills Property Auctions | Example Road</title>
      </head>
      <body>
        <h1>Login to see times and book a viewing</h1>
        <p>Detailed listing description.</p>
        <a href="/downloads/brochure.pdf">Brochure</a>
        <a href="/downloads/map.pdf">Map</a>
        <a href="/downloads/common_conditions.pdf">Common auction conditions</a>
      </body>
    </html>
    """
    documents = parsing_service.discover_document_links(
        html,
        base_url="https://example.com/listings/lot-1",
    )
    assert [(doc.doc_type, Path(doc.url).name) for doc in documents] == [
        (DocumentType.BROCHURE, "brochure.pdf"),
        (DocumentType.MAP, "map.pdf"),
    ]

    parsed = parsing_service.parse_html_listing(
        html=(
            "<html><head><meta name='description' "
            "content='Savills Property Auctions listing'></head>"
            "<body><h1>Real Camden Site</h1>"
            "<p>3 Apr 2026 auction. Guide price £500k.</p></body></html>"
        ),
        canonical_url="https://example.com/listings/lot-1?lat=51.501&lon=-0.101",
        page_title="Savills Property Auctions | Real Camden Site",
    )
    assert parsed.headline == "Real Camden Site"
    assert parsed.lat == pytest.approx(51.501)
    assert parsed.lon == pytest.approx(-0.101)
    assert parsed.search_text == "Real Camden Site 3 Apr 2026 auction. Guide price £500k."

    rows = parsing_service.parse_csv_rows(
        "headline,address,price,status,listing_type,auction_date\n"
        "CSV Site,1 Test Road,Offers over £500k,Under offer,Land,17 April 2026",
        source_name="csv_source",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.source_listing_id == "csv://csv_source/row-1"
    assert row.normalized_address == "1 test road"
    assert row.guide_price_gbp == 500_000
    assert row.status == ListingStatus.UNDER_OFFER
    assert row.listing_type == ListingType.LAND
    assert row.auction_date == datetime(2026, 4, 17).date()


def test_listing_service_helpers_cover_connectors_compliance_storage_and_rebuild(
    db_session,
    seed_reference_data,
):
    del seed_reference_data

    class DummyFetcher:
        def __init__(self, settings):
            self.settings = settings

    class DummyConnector:
        def __init__(self, fetcher):
            self.fetcher = fetcher

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(listings_service, "HtmlSnapshotFetcher", DummyFetcher)
    monkeypatch.setattr(listings_service, "ManualUrlConnector", DummyConnector)
    monkeypatch.setattr(listings_service, "CsvImportConnector", DummyConnector)
    monkeypatch.setattr(listings_service, "GenericPublicPageConnector", DummyConnector)

    connector = listings_service.build_connector(
        ConnectorType.MANUAL_URL,
        settings=SimpleNamespace(marker="manual"),
    )
    assert isinstance(connector, DummyConnector)
    assert connector.fetcher.settings.marker == "manual"
    assert isinstance(
        listings_service.build_connector(
            ConnectorType.CSV_IMPORT, settings=SimpleNamespace(marker="csv")
        ),
        DummyConnector,
    )
    assert isinstance(
        listings_service.build_connector(
            ConnectorType.PUBLIC_PAGE, settings=SimpleNamespace(marker="public")
        ),
        DummyConnector,
    )
    with pytest.raises(ValueError):
        listings_service.build_connector(SimpleNamespace(), settings=SimpleNamespace(marker="bad"))
    monkeypatch.undo()

    source = ListingSource(
        name="manual_source",
        connector_type=ConnectorType.MANUAL_URL,
        compliance_mode=ComplianceMode.MANUAL_ONLY,
        refresh_policy_json={},
        active=True,
    )
    db_session.add(source)
    db_session.commit()

    existing = listings_service.resolve_listing_source(
        session=db_session,
        job=_job(
            job_type=JobType.MANUAL_URL_SNAPSHOT, payload_json={"source_name": "manual_source"}
        ),
    )
    assert existing.id == source.id

    created_manual = listings_service.resolve_listing_source(
        session=db_session,
        job=_job(job_type=JobType.MANUAL_URL_SNAPSHOT, payload_json={"source_name": "new_manual"}),
    )
    assert created_manual.connector_type == ConnectorType.MANUAL_URL
    assert created_manual.compliance_mode == ComplianceMode.MANUAL_ONLY

    created_csv = listings_service.resolve_listing_source(
        session=db_session,
        job=_job(job_type=JobType.CSV_IMPORT_SNAPSHOT, payload_json={"source_name": "csv_source"}),
    )
    assert created_csv.connector_type == ConnectorType.CSV_IMPORT
    assert created_csv.compliance_mode == ComplianceMode.CSV_ONLY

    with pytest.raises(ValueError):
        listings_service.resolve_listing_source(
            session=db_session,
            job=_job(job_type=JobType.LISTING_SOURCE_RUN, payload_json={"source_name": "missing"}),
        )

    with pytest.raises(listings_service.ComplianceError):
        listings_service.enforce_compliance(
            source=SimpleNamespace(
                name="inactive", active=False, compliance_mode=ComplianceMode.MANUAL_ONLY
            ),
            job=_job(job_type=JobType.MANUAL_URL_SNAPSHOT, payload_json={}),
        )
    listings_service.enforce_compliance(
        source=SimpleNamespace(name="csv", active=True, compliance_mode=ComplianceMode.CSV_ONLY),
        job=_job(job_type=JobType.CSV_IMPORT_SNAPSHOT, payload_json={}),
    )
    with pytest.raises(listings_service.ComplianceError):
        listings_service.enforce_compliance(
            source=SimpleNamespace(
                name="bad", active=True, compliance_mode=ComplianceMode.CSV_ONLY
            ),
            job=_job(job_type=JobType.LISTING_SOURCE_RUN, payload_json={}),
        )
    with pytest.raises(ValueError):
        listings_service.enforce_compliance(
            source=SimpleNamespace(
                name="bad", active=True, compliance_mode=ComplianceMode.CSV_ONLY
            ),
            job=SimpleNamespace(job_type=SimpleNamespace(value="BROKEN"), payload_json={}),
        )

    assert (
        listings_service.build_storage_path(
            source_name="../../unsafe/source name",
            raw_asset_id=UUID("11111111-1111-1111-1111-111111111111"),
            asset=SimpleNamespace(asset_type="HTML", original_url="https://example.com/file.html"),
        )
        == "raw/unsafe-source-name/11111111-1111-1111-1111-111111111111.html"
    )
    assert listings_service.build_storage_path(
        source_name="source",
        raw_asset_id=UUID("22222222-2222-2222-2222-222222222222"),
        asset=SimpleNamespace(
            asset_type="UNKNOWN", original_url="https://example.com/file.geojson"
        ),
    ).endswith(".geojson")

    assert listings_service._safe_storage_source_name("") == "source"
    long_name = "x" * 80
    assert len(listings_service._safe_storage_source_name(long_name)) <= 61

    class MemoryStorage:
        def __init__(self, payload: bytes):
            self.payload = payload
            self.put_calls = 0

        def get_bytes(self, storage_path: str) -> bytes:
            del storage_path
            return self.payload

        def put_bytes(self, storage_path: str, payload: bytes, *, content_type: str):
            del storage_path, payload, content_type
            self.put_calls += 1
            return object()

    listings_service._store_bytes_idempotently(
        MemoryStorage(b"same"),
        storage_path="raw/test/file.pdf",
        payload=b"same",
        content_type="application/pdf",
    )
    with pytest.raises(ValueError):
        listings_service._store_bytes_idempotently(
            MemoryStorage(b"different"),
            storage_path="raw/test/file.pdf",
            payload=b"payload",
            content_type="application/pdf",
        )

    now = datetime.now(UTC)
    source = ListingSource(
        name="manual_url",
        connector_type=ConnectorType.MANUAL_URL,
        compliance_mode=ComplianceMode.MANUAL_ONLY,
        refresh_policy_json={},
        active=True,
    )
    db_session.add(source)
    db_session.flush()
    listing_one = ListingItem(
        source_id=source.id,
        source_listing_id="listing-1",
        canonical_url="https://example.com/listing-1",
        listing_type=ListingType.LAND,
        first_seen_at=now,
        last_seen_at=now,
        latest_status=ListingStatus.LIVE,
        normalized_address="12 example road london",
        search_text="listing one",
    )
    listing_two = ListingItem(
        source_id=source.id,
        source_listing_id="listing-2",
        canonical_url="https://example.com/listing-2",
        listing_type=ListingType.LAND,
        first_seen_at=now,
        last_seen_at=now,
        latest_status=ListingStatus.LIVE,
        normalized_address="12 example road london",
        search_text="listing two",
    )
    db_session.add_all([listing_one, listing_two])
    db_session.flush()
    snapshot_one = ListingSnapshot(
        listing_item_id=listing_one.id,
        source_snapshot_id=uuid.uuid4(),
        observed_at=now,
        headline="Example Road Site",
        description_text="Listing one",
        guide_price_gbp=1_000_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        address_text="12 Example Road, London",
        normalized_address="12 example road london",
        lat=51.5001,
        lon=-0.1001,
        raw_record_json={},
        search_text="listing one",
    )
    snapshot_two = ListingSnapshot(
        listing_item_id=listing_two.id,
        source_snapshot_id=uuid.uuid4(),
        observed_at=now,
        headline="Example Road Development Site",
        description_text="Listing two",
        guide_price_gbp=1_020_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        address_text="12 Example Road, London",
        normalized_address="12 example road london",
        lat=51.50011,
        lon=-0.10009,
        raw_record_json={},
        search_text="listing two",
    )
    db_session.add_all([snapshot_one, snapshot_two])
    db_session.flush()
    listing_one.current_snapshot_id = snapshot_one.id
    listing_two.current_snapshot_id = snapshot_two.id
    db_session.add(
        ListingCluster(
            id=uuid.uuid4(),
            cluster_key="obsolete",
            cluster_status=ListingClusterStatus.SINGLETON,
        )
    )
    db_session.commit()

    clusters = listings_service.rebuild_listing_clusters(session=db_session)
    assert clusters
    assert (
        len(db_session.query(ListingCluster).filter(ListingCluster.cluster_key == "obsolete").all())
        == 0
    )


def test_runtime_listing_filters_keep_only_required_lpa_rows() -> None:
    boundary_geometry = normalize_geojson_geometry(
        geometry_payload={
            "type": "Polygon",
            "coordinates": [[
                [-0.12, 51.545],
                [-0.08, 51.545],
                [-0.08, 51.57],
                [-0.12, 51.57],
                [-0.12, 51.545],
            ]],
        },
        source_epsg=4326,
        source_type=GeomSourceType.SOURCE_POLYGON,
    )
    session = _QueueSession(
        results=[
            _Result(
                items=[
                    SimpleNamespace(
                        id="islington",
                        geom_27700=boundary_geometry.geom_27700_wkt,
                    )
                ]
            )
        ]
    )
    source = SimpleNamespace(
        refresh_policy_json={"source_fit_policy": {"required_lpa_ids": ["islington"]}}
    )
    output = ConnectorRunOutput(
        source_name="savills_development_land",
        source_family="public_page",
        source_uri="https://search.savills.com",
        observed_at=datetime.now(UTC),
        coverage_note="fixture",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={"filtered_out_count": 0},
        assets=[],
        listings=[
            ParsedListing(
                source_listing_id="hamilton",
                canonical_url="https://search.savills.com/com/en/property-detail/9d0e1d60",
                observed_at=datetime.now(UTC),
                headline="2 Hamilton Lane",
                listing_type=ListingType.REDEVELOPMENT_SITE,
                status=ListingStatus.LIVE,
                address_text="2 Hamilton Lane, Highbury, N5 1SH",
                lat=51.5538983970221,
                lon=-0.0989907835926118,
            ),
            ParsedListing(
                source_listing_id="larkhall",
                canonical_url="https://search.savills.com/com/en/property-detail/fc13d0e0",
                observed_at=datetime.now(UTC),
                headline="94 A & B Larkhall Lane",
                listing_type=ListingType.REDEVELOPMENT_SITE,
                status=ListingStatus.LIVE,
                address_text="94 A & B Larkhall Lane, Clapham, London, SW4 6SP",
                lat=51.473477,
                lon=-0.128152,
            ),
            ParsedListing(
                source_listing_id="missing-coords",
                canonical_url="https://search.savills.com/com/en/property-detail/missing",
                observed_at=datetime.now(UTC),
                headline="Missing coords",
                listing_type=ListingType.REDEVELOPMENT_SITE,
                status=ListingStatus.LIVE,
                address_text="Unknown",
            ),
        ],
    )

    filtered = listings_service._apply_runtime_listing_filters(
        session=session,
        source=source,
        output=output,
    )

    assert [listing.source_listing_id for listing in filtered.listings] == ["hamilton"]
    assert filtered.parse_status == SourceParseStatus.PARSED
    assert filtered.manifest_json["boundary_filter_required_lpa_ids"] == ["islington"]
    assert filtered.manifest_json["boundary_loaded_lpa_ids"] == ["islington"]
    assert filtered.manifest_json["boundary_filter_missing_lpa_ids"] == []
    assert filtered.manifest_json["boundary_allowed_listing_urls"] == [
        "https://search.savills.com/com/en/property-detail/9d0e1d60"
    ]
    assert filtered.manifest_json["filtered_out_count"] == 2
    assert filtered.manifest_json["boundary_filtered_out_listing_urls"] == [
        {
            "url": "https://search.savills.com/com/en/property-detail/fc13d0e0",
            "reason": "OUTSIDE_REQUIRED_LPA",
        },
        {
            "url": "https://search.savills.com/com/en/property-detail/missing",
            "reason": "BOUNDARY_COORDINATES_MISSING",
        },
    ]
    assert "Runtime LPA filter kept 1 of 3 listing(s)" in filtered.coverage_note


def test_runtime_listing_filters_fail_closed_when_required_boundaries_are_missing() -> None:
    session = _QueueSession(results=[_Result(items=[])])
    source = SimpleNamespace(
        refresh_policy_json={"source_fit_policy": {"required_lpa_ids": ["islington"]}}
    )
    output = ConnectorRunOutput(
        source_name="savills_development_land",
        source_family="public_page",
        source_uri="https://search.savills.com",
        observed_at=datetime.now(UTC),
        coverage_note="fixture",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={},
        assets=[],
        listings=[
            ParsedListing(
                source_listing_id="hamilton",
                canonical_url="https://search.savills.com/com/en/property-detail/9d0e1d60",
                observed_at=datetime.now(UTC),
                headline="2 Hamilton Lane",
                listing_type=ListingType.REDEVELOPMENT_SITE,
                status=ListingStatus.LIVE,
                address_text="2 Hamilton Lane, Highbury, N5 1SH",
                lat=51.5538983970221,
                lon=-0.0989907835926118,
            )
        ],
    )

    filtered = listings_service._apply_runtime_listing_filters(
        session=session,
        source=source,
        output=output,
    )

    assert filtered.listings == []
    assert filtered.parse_status == SourceParseStatus.FAILED
    assert filtered.manifest_json["boundary_loaded_lpa_ids"] == []
    assert filtered.manifest_json["boundary_filter_missing_lpa_ids"] == ["islington"]
    assert filtered.manifest_json["boundary_filtered_out_listing_urls"] == [
        {
            "url": "https://search.savills.com/com/en/property-detail/9d0e1d60",
            "reason": "REQUIRED_LPA_BOUNDARY_MISSING",
        }
    ]
    assert "failed closed because required borough boundaries were missing: islington." in (
        filtered.coverage_note
    )


def test_runtime_listing_filters_fail_closed_when_only_some_required_boundaries_exist() -> None:
    boundary_geometry = normalize_geojson_geometry(
        geometry_payload={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.115, 51.548],
                    [-0.078, 51.548],
                    [-0.078, 51.564],
                    [-0.115, 51.564],
                    [-0.115, 51.548],
                ]
            ],
        },
        source_epsg=4326,
        source_type=GeomSourceType.TITLE_UNION,
    )
    session = _QueueSession(
        results=[
            _Result(
                items=[
                    SimpleNamespace(
                        id="islington",
                        geom_27700=boundary_geometry.geom_27700_wkt,
                    )
                ]
            )
        ]
    )
    source = SimpleNamespace(
        refresh_policy_json={
            "source_fit_policy": {"required_lpa_ids": ["islington", "southwark"]}
        }
    )
    output = ConnectorRunOutput(
        source_name="savills_development_land",
        source_family="public_page",
        source_uri="https://search.savills.com",
        observed_at=datetime.now(UTC),
        coverage_note="fixture",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={},
        assets=[],
        listings=[
            ParsedListing(
                source_listing_id="hamilton",
                canonical_url="https://search.savills.com/com/en/property-detail/9d0e1d60",
                observed_at=datetime.now(UTC),
                headline="2 Hamilton Lane",
                listing_type=ListingType.REDEVELOPMENT_SITE,
                status=ListingStatus.LIVE,
                address_text="2 Hamilton Lane, Highbury, N5 1SH",
                lat=51.5538983970221,
                lon=-0.0989907835926118,
            ),
            ParsedListing(
                source_listing_id="southwark-site",
                canonical_url="https://search.savills.com/com/en/property-detail/southwark",
                observed_at=datetime.now(UTC),
                headline="Southwark site",
                listing_type=ListingType.REDEVELOPMENT_SITE,
                status=ListingStatus.LIVE,
                address_text="Southwark site",
                lat=51.5007,
                lon=-0.0917,
            ),
        ],
    )

    filtered = listings_service._apply_runtime_listing_filters(
        session=session,
        source=source,
        output=output,
    )

    assert filtered.listings == []
    assert filtered.parse_status == SourceParseStatus.FAILED
    assert filtered.manifest_json["boundary_loaded_lpa_ids"] == ["islington"]
    assert filtered.manifest_json["boundary_filter_missing_lpa_ids"] == ["southwark"]
    assert filtered.manifest_json["boundary_filtered_out_listing_urls"] == [
        {
            "url": "https://search.savills.com/com/en/property-detail/9d0e1d60",
            "reason": "REQUIRED_LPA_BOUNDARY_MISSING",
        },
        {
            "url": "https://search.savills.com/com/en/property-detail/southwark",
            "reason": "REQUIRED_LPA_BOUNDARY_MISSING",
        },
    ]


def test_runtime_listing_filters_fail_closed_when_boundary_geometry_is_blank() -> None:
    session = _QueueSession(
        results=[_Result(items=[SimpleNamespace(id="islington", geom_27700=None)])]
    )
    source = SimpleNamespace(
        refresh_policy_json={"source_fit_policy": {"required_lpa_ids": ["islington"]}}
    )
    output = ConnectorRunOutput(
        source_name="savills_development_land",
        source_family="public_page",
        source_uri="https://search.savills.com",
        observed_at=datetime.now(UTC),
        coverage_note="fixture",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={},
        assets=[],
        listings=[
            ParsedListing(
                source_listing_id="hamilton",
                canonical_url="https://search.savills.com/com/en/property-detail/9d0e1d60",
                observed_at=datetime.now(UTC),
                headline="2 Hamilton Lane",
                listing_type=ListingType.REDEVELOPMENT_SITE,
                status=ListingStatus.LIVE,
                address_text="2 Hamilton Lane, Highbury, N5 1SH",
                lat=51.5538983970221,
                lon=-0.0989907835926118,
            )
        ],
    )

    filtered = listings_service._apply_runtime_listing_filters(
        session=session,
        source=source,
        output=output,
    )

    assert filtered.listings == []
    assert filtered.parse_status == SourceParseStatus.FAILED
    assert filtered.manifest_json["boundary_loaded_lpa_ids"] == []
    assert filtered.manifest_json["boundary_filter_missing_lpa_ids"] == ["islington"]
