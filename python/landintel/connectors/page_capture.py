from dataclasses import dataclass

from landintel.connectors.base import ConnectorAsset, ParsedListing
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.domain.enums import DocumentType
from landintel.listings.parsing import discover_document_links, parse_html_listing


@dataclass(slots=True)
class CapturedListingPage:
    listing: ParsedListing
    assets: list[ConnectorAsset]


def capture_listing_page(
    *,
    fetcher: HtmlSnapshotFetcher,
    url: str,
    asset_prefix: str,
) -> CapturedListingPage:
    html_asset = fetcher.fetch_asset(url)
    assets = [
        ConnectorAsset(
            asset_key=f"{asset_prefix}_html",
            asset_type="HTML",
            role="LISTING_PAGE",
            original_url=html_asset.final_url,
            content=html_asset.content,
            content_type=html_asset.content_type,
            fetched_at=html_asset.fetched_at,
            metadata={
                "status_code": html_asset.status_code,
                "headers": html_asset.headers,
                "page_title": html_asset.page_title,
            },
        )
    ]

    brochure_asset_key = None
    map_asset_key = None
    document_links = discover_document_links(
        html_asset.content.decode("utf-8", errors="ignore"),
        base_url=html_asset.final_url,
    )
    for index, document in enumerate(
        document_links,
        start=1,
    ):
        try:
            fetched_document = fetcher.fetch_asset(document.url)
        except Exception:
            continue
        asset_key = f"{asset_prefix}_document_{index}"
        assets.append(
            ConnectorAsset(
                asset_key=asset_key,
                asset_type="PDF",
                role=document.doc_type.value,
                original_url=fetched_document.final_url,
                content=fetched_document.content,
                content_type=fetched_document.content_type,
                fetched_at=fetched_document.fetched_at,
                metadata={
                    "status_code": fetched_document.status_code,
                    "headers": fetched_document.headers,
                    "page_title": fetched_document.page_title,
                    "doc_type": document.doc_type.value,
                    "label": document.label,
                },
            )
        )
        if document.doc_type == DocumentType.BROCHURE and brochure_asset_key is None:
            brochure_asset_key = asset_key
        if document.doc_type == DocumentType.MAP and map_asset_key is None:
            map_asset_key = asset_key

    listing = parse_html_listing(
        html=html_asset.content.decode("utf-8", errors="ignore"),
        canonical_url=html_asset.final_url,
        page_title=html_asset.page_title,
        observed_at=html_asset.fetched_at,
        brochure_asset_key=brochure_asset_key,
        map_asset_key=map_asset_key,
    )
    return CapturedListingPage(listing=listing, assets=assets)
