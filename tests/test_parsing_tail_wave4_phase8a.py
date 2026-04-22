from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from landintel.domain.enums import DocumentType, ListingStatus, ListingType, PriceBasisType
from landintel.listings import parsing as parsing_service
from landintel.listings.parsing import (
    discover_document_links,
    parse_csv_rows,
    parse_html_listing,
    parse_optional_date,
    parse_price,
)


def test_parse_price_and_date_helpers_cover_remaining_basis_branches() -> None:
    assert parse_price(None) == (None, PriceBasisType.UNKNOWN)
    assert parse_price("Offers in excess of £500k") == (
        500_000,
        PriceBasisType.OFFERS_IN_EXCESS_OF,
    )
    assert parse_price("Asking price £12k") == (12_000, PriceBasisType.ASKING_PRICE)
    assert parse_optional_date("Auction 17 Foober 2026") is None


def test_parse_html_listing_covers_jsonld_description_title_and_coordinate_fallbacks() -> None:
    jsonld_html = """
    <html>
      <head>
        <script type="application/ld+json"></script>
        <script type="application/ld+json">not json</script>
        <script type="application/ld+json">
          [
            {
              "name": "Json Headline",
              "description": "Json Description",
              "address": {
                "streetAddress": "1 Json Road",
                "addressLocality": "London",
                "postalCode": "NW1 1AA"
              },
              "geo": {"latitude": "51.501", "longitude": "-0.101"}
            },
            {"name": "Ignored Record"}
          ]
        </script>
        <script type="application/ld+json">{"name": "Extra Record"}</script>
      </head>
      <body>
        <h1>Login to see times and book a viewing</h1>
      </body>
    </html>
    """

    parsed_jsonld = parse_html_listing(
        html=jsonld_html,
        canonical_url="https://example.test/listings/jsonld?lat=bad&lon=bad",
        page_title=None,
    )
    assert parsed_jsonld.headline == "Json Headline"
    assert parsed_jsonld.description_text == "Json Description"
    assert parsed_jsonld.address_text == "1 Json Road London NW1 1AA"
    assert parsed_jsonld.normalized_address == "1 json road london nw1 1aa"
    assert parsed_jsonld.lat == pytest.approx(51.501)
    assert parsed_jsonld.lon == pytest.approx(-0.101)

    savills_description_html = """
    <html>
      <head></head>
      <body>
        <h1>Login to see times and book a viewing</h1>
        <div class="lot-details-description">
          Description A cleared site with access from the road.
        </div>
      </body>
    </html>
    """

    parsed_description = parse_html_listing(
        html=savills_description_html,
        canonical_url="https://example.test/listings/savills-description?lat=bad&lon=bad",
        page_title="Savills | 12 Example Road, Manchester",
    )
    assert parsed_description.headline == "12 Example Road, Manchester"
    assert parsed_description.description_text == "A cleared site with access from the road."
    assert parsed_description.address_text is None
    assert parsed_description.lat is None
    assert parsed_description.lon is None

    savills_top_html = """
    <html>
      <head></head>
      <body>
        <h1>Login to see times and book a viewing</h1>
        <div class="lot-details-top">
          Book a viewing
          Key features
          Freehold development site in Islington
          Contact an agent
        </div>
      </body>
    </html>
    """

    parsed_top = parse_html_listing(
        html=savills_top_html,
        canonical_url="https://example.test/listings/savills-top?lat=bad&lon=bad",
        page_title="Savills Property Auctions | 12 Example Road, London",
    )
    assert parsed_top.headline == "12 Example Road, London"
    assert parsed_top.description_text == "Freehold development site in Islington"
    assert parsed_top.address_text == "12 Example Road, London"
    assert parsed_top.lat is None
    assert parsed_top.lon is None


def test_discover_document_links_and_parse_csv_rows_cover_filters_and_float_fallbacks() -> None:
    html = """
    <html>
      <body>
        <a href="/downloads/brochure.pdf">Brochure</a>
        <a href="/downloads/brochure.pdf">Brochure duplicate</a>
        <a href="/downloads/brochure.pdf">Site plan</a>
        <a href="/downloads/map.pdf">Map</a>
        <a href="/downloads/labeled-later.pdf"></a>
        <a href="/downloads/labeled-later.pdf">Brochure labelled later</a>
        <a href="https://assets.example.test/live/pdf.php?p=ABC123&amp;t=S">Brochure endpoint</a>
        <a href="/downloads/site-plan.pdf">Site plan</a>
        <a href="/downloads/common_conditions.pdf">Common auction conditions</a>
        <a href="/downloads/not-a-pdf.txt">Text</a>
      </body>
    </html>
    """
    documents = discover_document_links(
        html,
        base_url="https://example.test/listings/lot-1",
    )
    assert [(doc.doc_type, doc.label) for doc in documents] == [
        (DocumentType.MAP, "Site plan"),
        (DocumentType.MAP, "Map"),
        (DocumentType.BROCHURE, "Brochure labelled later"),
        (DocumentType.BROCHURE, "Brochure endpoint"),
        (DocumentType.MAP, "Site plan"),
    ]

    csv_text = (
        "headline,description,price,status,listing_type,auction_date,lat,lon,source_listing_id\n"
        ",,,,,,,,\n"
        "CSV Plot,Development opportunity,Offers in excess of £900k,Under offer,"
        "Land,17 April 2026,not-a-number,not-a-number,listing-123\n"
    )
    rows = parse_csv_rows(csv_text, source_name="csv_source")
    assert len(rows) == 2

    empty_row = rows[0]
    assert empty_row.source_listing_id == "csv://csv_source/row-1"
    assert empty_row.canonical_url == "csv://csv_source/row-1"
    assert empty_row.guide_price_gbp is None
    assert empty_row.price_basis_type == PriceBasisType.UNKNOWN
    assert empty_row.status == ListingStatus.UNKNOWN
    assert empty_row.listing_type == ListingType.UNKNOWN
    assert empty_row.raw_record_json == {}

    rich_row = rows[1]
    assert rich_row.source_listing_id == "listing-123"
    assert rich_row.canonical_url == "csv://csv_source/row-2"
    assert rich_row.guide_price_gbp == 900_000
    assert rich_row.price_basis_type == PriceBasisType.OFFERS_IN_EXCESS_OF
    assert rich_row.status == ListingStatus.UNDER_OFFER
    assert rich_row.listing_type == ListingType.REDEVELOPMENT_SITE
    assert rich_row.auction_date == datetime(2026, 4, 17, tzinfo=UTC).date()
    assert rich_row.lat is None
    assert rich_row.lon is None


def test_discover_document_links_covers_duplicate_map_upgrade_without_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_links: list[SimpleNamespace] = []

    def _fake_document_link(*, url: str, doc_type: DocumentType, label: str) -> SimpleNamespace:
        stored_type = DocumentType.BROCHURE if not created_links else doc_type
        link = SimpleNamespace(url=url, doc_type=stored_type, label=label)
        created_links.append(link)
        return link

    monkeypatch.setattr(parsing_service, "DiscoveredDocumentLink", _fake_document_link)

    documents = parsing_service.discover_document_links(
        """
        <html>
          <body>
            <a href="/downloads/map.pdf"></a>
            <a href="/downloads/map.pdf"></a>
          </body>
        </html>
        """,
        base_url="https://example.test/listings/lot-1",
    )

    assert len(documents) == 1
    assert documents[0].doc_type == DocumentType.MAP
    assert documents[0].label == ""
