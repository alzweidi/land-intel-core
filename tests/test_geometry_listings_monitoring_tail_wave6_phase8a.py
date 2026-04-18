from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from landintel.domain.enums import (
    DocumentType,
    GeomConfidence,
    GeomSourceType,
    ListingClusterStatus,
    ListingStatus,
)
from landintel.geospatial import geometry as geometry_service
from landintel.listings import clustering as clustering_service
from landintel.listings import parsing as parsing_service
from landintel.listings import service as listings_service
from landintel.monitoring import health as health_service
from shapely.geometry import GeometryCollection, LineString, Polygon


class _Result:
    def __init__(self, *, items=None, scalar=None, rows=None):
        self._items = list(items or [])
        self._scalar = scalar
        self._rows = list(rows or [])

    def scalars(self):
        return self

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def unique(self):
        return self

    def all(self):
        if self._items:
            return list(self._items)
        return list(self._rows)


class _QueueSession:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.executed = []
        self.flushed = 0

    def execute(self, stmt):
        self.executed.append(stmt)
        if self._results:
            return self._results.pop(0)
        return _Result(items=[])

    def add(self, obj):
        self.added.append(obj)

    def get(self, model, identity):
        del model
        return None

    def flush(self):
        self.flushed += 1


def test_geometry_helpers_cover_wkt_normalization_and_empty_repair() -> None:
    with pytest.raises(geometry_service.GeometryNormalizationError):
        geometry_service.repair_geometry(GeometryCollection())

    repaired = geometry_service.normalize_wkt_geometry(
        geometry_wkt="POLYGON ((0 0, 0 10, 10 10, 10 0, 0 0))",
        source_type=GeomSourceType.SOURCE_POLYGON,
    )
    assert repaired.geom_source_type == GeomSourceType.SOURCE_POLYGON
    assert repaired.geom_confidence == GeomConfidence.HIGH
    assert repaired.geom_27700.geom_type == "Polygon"

    assert geometry_service.geometry_warning_dicts(
        [geometry_service.warning("GEOMETRY_REPAIRED", "fixed")]
    ) == [{"code": "GEOMETRY_REPAIRED", "message": "fixed"}]


def test_geometry_helpers_cover_validity_repair_empty_and_collection_passthrough(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        geometry_service,
        "make_valid",
        lambda geometry: GeometryCollection(),
    )

    with pytest.raises(geometry_service.GeometryNormalizationError):
        geometry_service.repair_geometry(
            Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
        )

    repaired, warnings = geometry_service.repair_geometry(
        GeometryCollection([LineString([(0, 0), (1, 1)])])
    )
    assert repaired.geom_type == "GeometryCollection"
    assert warnings == []
    assert (
        geometry_service.derive_geom_confidence(
            source_type=GeomSourceType.TITLE_UNION,
            geometry_27700=GeometryCollection([LineString([(0, 0), (1, 1)])]),
        )
        == GeomConfidence.MEDIUM
    )


def test_listing_clustering_helpers_cover_transitive_unions_and_fallback_edges() -> None:
    shared_url = "https://example.com/listing"
    a = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        canonical_url=shared_url,
        normalized_address="12 example road london",
        headline="Camden Yard Site",
        guide_price_gbp=1_000_000,
        lat=51.5000,
        lon=-0.1000,
        document_hashes=(),
    )
    b = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        canonical_url=shared_url,
        normalized_address="12 example road london",
        headline="Camden Yard Site",
        guide_price_gbp=1_005_000,
        lat=51.5002,
        lon=-0.1002,
        document_hashes=(),
    )
    c = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        canonical_url=shared_url,
        normalized_address="12 example road london",
        headline="Camden Yard Site",
        guide_price_gbp=1_010_000,
        lat=51.5004,
        lon=-0.1004,
        document_hashes=(),
    )
    d = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        canonical_url="https://example.org/d",
        normalized_address="44 rye lane london",
        headline="South London Site",
        guide_price_gbp=500_000,
        lat=51.6000,
        lon=-0.2000,
        document_hashes=(),
    )
    e = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        canonical_url="https://example.org/e",
        normalized_address="44 rye lane london",
        headline="South London Site",
        guide_price_gbp=505_000,
        lat=None,
        lon=None,
        document_hashes=(),
    )
    f = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        canonical_url="https://example.org/f",
        normalized_address="99 another street london",
        headline="Redevelopment opportunity",
        guide_price_gbp=750_000,
        lat=51.5100,
        lon=-0.1010,
        document_hashes=(),
    )
    g = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        canonical_url="https://example.org/g",
        normalized_address="99 different street london",
        headline="Redevelopment opportunity",
        guide_price_gbp=755_000,
        lat=51.5103,
        lon=-0.1012,
        document_hashes=(),
    )

    edges = clustering_service.generate_cluster_edges([a, b, c, d, e, f, g])
    by_pair = {
        tuple(sorted((edge.left_listing_id, edge.right_listing_id), key=str)): edge
        for edge in edges
    }

    assert len(
        [
            edge
            for edge in edges
            if edge.left_listing_id in {a.listing_item_id, b.listing_item_id, c.listing_item_id}
        ]
    ) == 3
    assert (
        by_pair[tuple(sorted((d.listing_item_id, e.listing_item_id), key=str))].confidence
        >= 0.95
    )
    assert "coordinates_consistent" in by_pair[
        tuple(sorted((d.listing_item_id, e.listing_item_id), key=str))
    ].reasons
    assert "coordinates_close" in by_pair[
        tuple(sorted((f.listing_item_id, g.listing_item_id), key=str))
    ].reasons
    assert "headline_similarity" in by_pair[
        tuple(sorted((f.listing_item_id, g.listing_item_id), key=str))
    ].reasons
    assert (
        clustering_service._headline_similarity(None, "Headline")
        == 0.0
    )
    assert clustering_service._headline_similarity("!!!", "???") == 0.0
    assert (
        clustering_service._compare_pair(
            clustering_service.ClusterListingInput(
                listing_item_id=uuid.UUID("99999999-9999-9999-9999-999999999999"),
                canonical_url="https://example.org/h",
                normalized_address="1 same road london",
                headline="Alpha",
                guide_price_gbp=100_000,
                lat=51.50,
                lon=-0.10,
                document_hashes=(),
            ),
            clustering_service.ClusterListingInput(
                listing_item_id=uuid.UUID("88888888-8888-8888-8888-888888888888"),
                canonical_url="https://example.org/i",
                normalized_address="1 same road london",
                headline="Beta",
                guide_price_gbp=200_000,
                lat=51.70,
                lon=-0.30,
                document_hashes=(),
            ),
        )
        is None
    )

    clusters = clustering_service.build_clusters([a, b, c, d, e, f, g])
    assert len(clusters) == 3
    shared_cluster = next(
        cluster
        for cluster in clusters
        if {member.listing_item_id for member in cluster.members}
        == {a.listing_item_id, b.listing_item_id, c.listing_item_id}
    )
    assert shared_cluster.cluster_status == ListingClusterStatus.ACTIVE
    assert len(shared_cluster.members) == 3
    assert all(member.reasons for member in shared_cluster.members)


def test_parsing_helpers_cover_document_deduplication_and_listing_fallbacks() -> None:
    html = """
    <html>
      <head>
        <title>Savills Property Auctions | 12 Example Rd, London</title>
        <meta name="description" content="Savills Property Auctions listing">
      </head>
      <body>
        <h1>Login to see times and book a viewing</h1>
        <p>Fallback description paragraph.</p>
        <script>window.__LOT__={"long_lat":"{\\"lat\\":51.5001,\\"lng\\":-0.1001}"}</script>
        <a href="/docs/brochure.pdf">Brochure</a>
        <a href="/docs/brochure.pdf">Duplicate brochure</a>
        <a href="/docs/common_conditions.pdf">Common auction conditions</a>
        <a href="/docs/map.pdf">Map</a>
      </body>
    </html>
    """

    assert parsing_service._extract_address_from_title("Warehouse only") is None
    assert parsing_service._extract_address_from_title(None) is None

    documents = parsing_service.discover_document_links(
        html,
        base_url="https://example.com/listings/lot-1",
    )
    assert [(doc.doc_type, doc.label) for doc in documents] == [
        (DocumentType.BROCHURE, "Brochure"),
        (DocumentType.MAP, "Map"),
    ]

    parsed = parsing_service.parse_html_listing(
        html=html,
        canonical_url="https://example.com/listings/lot-1",
        page_title="Savills Property Auctions | 12 Example Rd, London",
    )
    assert parsed.headline == "12 Example Rd, London"
    assert parsed.description_text == "Fallback description paragraph."
    assert parsed.normalized_address == "12 example road london"
    assert parsed.status == ListingStatus.AUCTION
    assert parsed.lat == pytest.approx(51.5001)
    assert parsed.lon == pytest.approx(-0.1001)
    assert "12 Example Rd, London" in parsed.search_text


def test_parsing_helpers_cover_jsonld_and_partial_geo_fallbacks() -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json"></script>
        <script type="application/ld+json">
          [
            {
              "name": "JSONLD Headline",
              "description": "JSONLD Description",
              "geo": {"latitude": 51.5001}
            }
          ]
        </script>
        <script type="application/ld+json">
          {"name": "Secondary Headline", "geo": {"latitude": 51.5002, "longitude": -0.1002}}
        </script>
      </head>
      <body>
        <p>Body fallback.</p>
      </body>
    </html>
    """
    soup = parsing_service.BeautifulSoup(html, "html.parser")
    records = parsing_service._load_json_ld(soup)
    assert [record.get("name") for record in records] == [
        "JSONLD Headline",
        "Secondary Headline",
    ]

    scalar_html = """
    <html>
      <head>
        <script type="application/ld+json">"ignore me"</script>
        <script type="application/ld+json">
          {"name": "Kept Headline", "geo": {"latitude": 51.5003, "longitude": -0.1003}}
        </script>
      </head>
    </html>
    """
    scalar_soup = parsing_service.BeautifulSoup(scalar_html, "html.parser")
    scalar_records = parsing_service._load_json_ld(scalar_soup)
    assert [record.get("name") for record in scalar_records] == ["Kept Headline"]

    parsed = parsing_service.parse_html_listing(
        html=html,
        canonical_url="https://example.com/listings/jsonld",
        page_title="Savills Property Auctions | JSONLD Headline",
    )
    assert parsed.headline == "JSONLD Headline"
    assert parsed.description_text == "JSONLD Description"
    assert parsed.lat == pytest.approx(51.5002)
    assert parsed.lon == pytest.approx(-0.1002)


def test_build_data_health_and_model_health_cover_ok_paths_and_manual_review_metrics(
    monkeypatch,
) -> None:
    coverage_complete = SimpleNamespace(
        borough_id="camden",
        source_family="planning",
        coverage_status=SimpleNamespace(value="COMPLETE"),
        gap_reason=None,
        freshness_status=SimpleNamespace(value="FRESH"),
        coverage_note="ok",
        source_snapshot_id=uuid.uuid4(),
        captured_at=datetime(2025, 1, 2, tzinfo=UTC),
    )
    baseline_rule = SimpleNamespace(
        template_key="rule-1",
        status=SimpleNamespace(value="SIGNED_OFF"),
        freshness_status=SimpleNamespace(value="FRESH"),
        source_snapshot_id=uuid.uuid4(),
    )
    baseline_pack = SimpleNamespace(
        borough_id="camden",
        version="v1",
        status=SimpleNamespace(value="SIGNED_OFF"),
        freshness_status=SimpleNamespace(value="FRESH"),
        signed_off_by="analyst",
        signed_off_at=datetime(2025, 1, 3, tzinfo=UTC),
        rulepacks=[baseline_rule],
    )
    data_session = _QueueSession(
        results=[
            _Result(items=[coverage_complete]),
            _Result(items=[baseline_pack]),
            _Result(items=[]),
            _Result(scalar=0),
            _Result(scalar=0),
            _Result(rows=[]),
            _Result(items=[]),
        ]
    )
    valuation_metrics_calls = []
    monkeypatch.setattr(
        health_service,
        "update_valuation_metrics",
        lambda metrics: valuation_metrics_calls.append(metrics),
    )

    data_health = health_service.build_data_health(data_session)

    assert data_health["status"] == "ok"
    assert data_health["connector_failure_rate"] is None
    assert data_health["listing_parse_success_rate"] is None
    assert data_health["geometry_confidence_distribution"] == {}
    assert data_health["extant_permission_unresolved_rate"] is None
    assert data_health["borough_baseline_coverage"] == {
        "total": 1,
        "signed_off": 1,
        "pilot_ready": 0,
    }
    assert valuation_metrics_calls == [
        {
            "total": 0,
            "uplift_null_rate": None,
            "asking_price_missing_rate": None,
            "valuation_quality_distribution": {},
        }
    ]

    actual_assessment_model_metrics = health_service._assessment_model_metrics
    release = SimpleNamespace(
        id=uuid.uuid4(),
        template_key="template-a",
        scope_key="scope-a",
        status=SimpleNamespace(value="ACTIVE"),
        support_count=2,
        positive_count=1,
        negative_count=1,
        reason_text="ready",
        model_kind="classifier",
        created_at=datetime(2025, 1, 4, tzinfo=UTC),
        activated_at=datetime(2025, 1, 5, tzinfo=UTC),
        active_scopes=[],
    )
    active_scope = SimpleNamespace(
        scope_key="scope-a",
        template_key="template-a",
        model_release_id=uuid.uuid4(),
        activated_at=datetime(2025, 1, 6, tzinfo=UTC),
        visibility_mode=SimpleNamespace(value="VISIBLE"),
        visibility_reason="fixture",
    )
    model_session = _QueueSession(results=[_Result(items=[release]), _Result(items=[active_scope])])
    monkeypatch.setattr(
        health_service,
        "_assessment_model_metrics",
        lambda session: {
            "calibration_by_probability_band": [],
            "brier_score": None,
            "log_loss": None,
            "manual_review_agreement_by_band": [],
            "false_positive_reviewer_rate": None,
            "abstain_rate": None,
            "ood_rate": None,
            "template_level_performance": [],
        },
    )
    monkeypatch.setattr(
        health_service,
        "_build_valuation_metrics",
        lambda session: {
            "total": 0,
            "uplift_null_rate": None,
            "asking_price_missing_rate": None,
            "valuation_quality_distribution": {},
        },
    )

    model_health = health_service.build_model_health(model_session)
    assert model_health["status"] == "ok"
    assert model_health["releases"][0]["status"] == "ACTIVE"
    assert model_health["active_scopes"][0]["visibility_mode"] == "VISIBLE"

    reviewer_override = SimpleNamespace(
        assessment_run_id="run-1",
        created_at=datetime(2025, 1, 7, tzinfo=UTC),
        status=SimpleNamespace(value="ACTIVE"),
        override_json={"resolve_manual_review": True},
    )
    row_with_override = SimpleNamespace(
        assessment_run_id="run-1",
        assessment_run=SimpleNamespace(scenario=SimpleNamespace(template_key="template-a")),
        approval_probability_raw=0.22,
        approval_probability_display="LOW",
        ood_status="IN_SUPPORT",
        manual_review_required=True,
        eligibility_status=SimpleNamespace(value="LIVE"),
        result_json={},
    )
    row_without_override = SimpleNamespace(
        assessment_run_id="run-2",
        assessment_run=SimpleNamespace(scenario=SimpleNamespace(template_key="template-a")),
        approval_probability_raw=0.34,
        approval_probability_display="LOW",
        ood_status="IN_SUPPORT",
        manual_review_required=True,
        eligibility_status=SimpleNamespace(value="LIVE"),
        result_json={},
    )
    row_override_no_manual_review = SimpleNamespace(
        assessment_run_id="run-1",
        assessment_run=SimpleNamespace(scenario=SimpleNamespace(template_key="template-a")),
        approval_probability_raw=0.31,
        approval_probability_display="LOW",
        ood_status="IN_SUPPORT",
        manual_review_required=False,
        eligibility_status=SimpleNamespace(value="LIVE"),
        result_json={},
    )
    row_without_override_no_manual_review = SimpleNamespace(
        assessment_run_id="run-3",
        assessment_run=SimpleNamespace(scenario=SimpleNamespace(template_key="template-a")),
        approval_probability_raw=0.41,
        approval_probability_display="LOW",
        ood_status="IN_SUPPORT",
        manual_review_required=False,
        eligibility_status=SimpleNamespace(value="LIVE"),
        result_json={},
    )
    metrics_session = _QueueSession(
        results=[
            _Result(
                items=[
                    row_with_override,
                    row_without_override,
                    row_override_no_manual_review,
                    row_without_override_no_manual_review,
                ]
            ),
            _Result(items=[reviewer_override]),
        ]
    )

    metrics = actual_assessment_model_metrics(metrics_session)
    assert metrics["false_positive_reviewer_rate"] == 0.5
    assert metrics["manual_review_agreement_by_band"] == [
        {"band": "LOW", "total": 4, "completed": 2, "agreement_rate": 0.5}
    ]


def test_listing_service_rebuild_listing_clusters_relinks_sites_and_clears_obsolete_clusters(
    monkeypatch,
) -> None:
    item_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    old_cluster_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    new_cluster_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    snapshot = SimpleNamespace(
        id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        normalized_address="12 example road london",
        headline="Camden Yard Site",
        guide_price_gbp=1_000_000,
        lat=51.5,
        lon=-0.1,
    )
    current_item = SimpleNamespace(
        id=item_id,
        current_snapshot_id=snapshot.id,
        snapshots=[snapshot],
        documents=[],
        canonical_url="https://example.com/listing",
        normalized_address="12 example road london",
    )
    site = SimpleNamespace(
        id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        current_listing_id=item_id,
        listing_cluster_id=old_cluster_id,
    )

    class _ClusterResult:
        def __init__(self):
            self.cluster_id = new_cluster_id
            self.cluster_key = "listing-cluster:test"
            self.cluster_status = ListingClusterStatus.ACTIVE
            self.members = [
                SimpleNamespace(
                    listing_item_id=item_id,
                    confidence=0.91,
                    reasons=["canonical_url_exact"],
                )
            ]

    session = _QueueSession(
        results=[
            _Result(items=[old_cluster_id]),
            _Result(items=[current_item]),
            _Result(items=[]),
            _Result(items=[site]),
            _Result(items=[]),
            _Result(items=[]),
            _Result(items=[]),
        ]
    )
    session.get = lambda model, identity: None

    monkeypatch.setattr(listings_service, "build_clusters", lambda inputs: [_ClusterResult()])
    monkeypatch.setattr(
        listings_service,
        "_site_cluster_audit_payload",
        lambda site_obj: {
            "site_id": str(site_obj.id),
            "cluster_id": str(site_obj.listing_cluster_id),
        },
    )

    rebuilt = listings_service.rebuild_listing_clusters(session)

    assert len(rebuilt) == 1
    assert rebuilt[0].id == new_cluster_id
    assert rebuilt[0].cluster_key == "listing-cluster:test"
    assert site.listing_cluster_id == new_cluster_id
    assert any(getattr(obj, "action", None) == "site_cluster_relinked" for obj in session.added)
    assert session.flushed >= 3


def test_listing_service_rebuild_listing_clusters_skips_membership_reset_when_empty(
    monkeypatch,
) -> None:
    session = _QueueSession(
        results=[
            _Result(items=[]),
            _Result(items=[]),
            _Result(items=[]),
            _Result(items=[]),
        ]
    )
    monkeypatch.setattr(listings_service, "build_clusters", lambda inputs: [])

    rebuilt = listings_service.rebuild_listing_clusters(session)

    assert rebuilt == []
    assert session.added == []
    assert session.flushed == 2
