import uuid
from pathlib import Path

import pytest
import respx
from httpx import Response
from landintel.domain.enums import DocumentExtractionStatus, ListingClusterStatus
from landintel.domain.models import (
    ListingCluster,
    ListingDocument,
    ListingItem,
    ListingSnapshot,
    RawAsset,
    SourceSnapshot,
)
from landintel.listings.clustering import ClusterListingInput, build_clusters
from landintel.listings.parsing import parse_html_listing

from tests.fixtures.listing_fixtures import (
    CSV_IMPORT_TEXT,
    MANUAL_BROCHURE_PDF,
    MANUAL_BROCHURE_URL,
    MANUAL_LISTING_HTML,
    MANUAL_LISTING_URL,
    MANUAL_MAP_PDF,
    MANUAL_MAP_URL,
    PUBLIC_BROCHURE_PDF,
    PUBLIC_BROCHURE_URL,
    PUBLIC_INDEX_HTML,
    PUBLIC_INDEX_URL,
    PUBLIC_LISTING_HTML,
    PUBLIC_LISTING_URL,
)


def test_html_parser_extracts_expected_fields() -> None:
    parsed = parse_html_listing(
        html=MANUAL_LISTING_HTML,
        canonical_url=MANUAL_LISTING_URL,
        page_title="Camden Yard Development Opportunity",
    )

    assert parsed.headline == "Camden Yard Development Opportunity"
    assert parsed.guide_price_gbp == 1_250_000
    assert parsed.address_text == "12 Example Rd London NW1 7AA"
    assert parsed.normalized_address == "12 example road london nw1 7aa"
    assert parsed.brochure_asset_key is None
    assert parsed.lat == 51.5362
    assert parsed.lon == -0.1421


def test_clustering_rules_merge_duplicates_and_keep_distinct() -> None:
    duplicate_a = ClusterListingInput(
        listing_item_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        canonical_url="https://example.com/a",
        normalized_address="12 example road london",
        headline="Camden Yard Development Opportunity",
        guide_price_gbp=1_250_000,
        lat=51.5362,
        lon=-0.1421,
        document_hashes=("hash-1",),
    )
    duplicate_b = ClusterListingInput(
        listing_item_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        canonical_url="https://example.org/camden-yard",
        normalized_address="12 example road london",
        headline="Camden Yard Land Site",
        guide_price_gbp=1_240_000,
        lat=51.5362,
        lon=-0.1421,
        document_hashes=("hash-1",),
    )
    distinct = ClusterListingInput(
        listing_item_id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        canonical_url="https://example.com/other",
        normalized_address="44 rye lane london",
        headline="Peckham Corner Site",
        guide_price_gbp=875_000,
        lat=51.4680,
        lon=-0.0700,
        document_hashes=("hash-2",),
    )

    clusters = build_clusters([duplicate_a, duplicate_b, distinct])

    assert len(clusters) == 2
    active_clusters = [
        cluster
        for cluster in clusters
        if cluster.cluster_status == ListingClusterStatus.ACTIVE
    ]
    assert len(active_clusters) == 1
    assert len(active_clusters[0].members) == 2


@respx.mock
def test_phase1a_ingestion_and_cluster_integration(
    client,
    session_factory,
    drain_jobs,
    seed_listing_sources,
) -> None:
    del seed_listing_sources

    respx.get(MANUAL_LISTING_URL).mock(
        return_value=Response(200, text=MANUAL_LISTING_HTML, headers={"content-type": "text/html"})
    )
    respx.get(MANUAL_BROCHURE_URL).mock(
        return_value=Response(
            200,
            content=MANUAL_BROCHURE_PDF,
            headers={"content-type": "application/pdf"},
        )
    )
    respx.get(MANUAL_MAP_URL).mock(
        return_value=Response(
            200,
            content=MANUAL_MAP_PDF,
            headers={"content-type": "application/pdf"},
        )
    )
    respx.get(PUBLIC_INDEX_URL).mock(
        return_value=Response(200, text=PUBLIC_INDEX_HTML, headers={"content-type": "text/html"})
    )
    respx.get(PUBLIC_LISTING_URL).mock(
        return_value=Response(200, text=PUBLIC_LISTING_HTML, headers={"content-type": "text/html"})
    )
    respx.get(PUBLIC_BROCHURE_URL).mock(
        return_value=Response(
            200,
            content=PUBLIC_BROCHURE_PDF,
            headers={"content-type": "application/pdf"},
        )
    )

    manual_response = client.post(
        "/api/listings/intake/url",
        json={"url": MANUAL_LISTING_URL, "source_name": "manual_url", "requested_by": "pytest"},
    )
    assert manual_response.status_code == 202

    csv_response = client.post(
        "/api/listings/import/csv",
        files={"file": ("listings.csv", CSV_IMPORT_TEXT.encode("utf-8"), "text/csv")},
        data={"source_name": "csv_import", "requested_by": "pytest"},
    )
    assert csv_response.status_code == 202

    connector_response = client.post(
        "/api/listings/connectors/public_page_fixture/run",
        json={"requested_by": "pytest"},
    )
    assert connector_response.status_code == 202

    processed = drain_jobs(max_iterations=10)
    assert processed >= 4

    with session_factory() as session:
        assert session.query(SourceSnapshot).count() == 3
        assert session.query(ListingItem).count() == 3
        assert session.query(ListingSnapshot).count() == 3
        assert session.query(ListingDocument).count() >= 2
        assert session.query(RawAsset).count() >= 6

        documents = session.query(ListingDocument).all()
        assert any(
            document.extraction_status == DocumentExtractionStatus.EXTRACTED
            for document in documents
        )

        clusters = session.query(ListingCluster).all()
        assert len(clusters) == 2
        active_cluster = next(
            cluster for cluster in clusters if cluster.cluster_status == ListingClusterStatus.ACTIVE
        )
        assert len(active_cluster.members) == 2

    listings_response = client.get("/api/listings")
    assert listings_response.status_code == 200
    listings_payload = listings_response.json()
    assert listings_payload["total"] == 3

    duplicate_listing = next(
        item
        for item in listings_payload["items"]
        if item["cluster_status"] == ListingClusterStatus.ACTIVE.value
    )
    detail_response = client.get(f"/api/listings/{duplicate_listing['id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["documents"]
    assert detail_payload["source_snapshots"]

    cluster_list_response = client.get("/api/listing-clusters")
    assert cluster_list_response.status_code == 200
    cluster_payload = cluster_list_response.json()
    assert cluster_payload["total"] == 2
    active_cluster_payload = next(
        item
        for item in cluster_payload["items"]
        if item["cluster_status"] == ListingClusterStatus.ACTIVE.value
    )

    cluster_detail_response = client.get(f"/api/listing-clusters/{active_cluster_payload['id']}")
    assert cluster_detail_response.status_code == 200
    assert len(cluster_detail_response.json()["members"]) == 2


def test_storage_is_immutable(storage, test_settings) -> None:
    first_path = "raw/test/immutable.html"
    storage.put_bytes(first_path, b"alpha", content_type="text/html")

    with pytest.raises(ValueError):
        storage.put_bytes(first_path, b"beta", content_type="text/html")

    saved = Path(test_settings.storage_local_root) / first_path
    assert saved.read_bytes() == b"alpha"
