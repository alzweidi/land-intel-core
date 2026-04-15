import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from landintel.connectors.base import (
    ConnectorAsset,
    ConnectorContext,
    ConnectorRunOutput,
    ListingConnector,
)
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.connectors.page_capture import capture_listing_page
from landintel.domain.enums import ConnectorType, SourceParseStatus
from landintel.listings.parsing import normalize_url


class GenericPublicPageConnector(ListingConnector):
    connector_type = ConnectorType.PUBLIC_PAGE

    def __init__(self, fetcher: HtmlSnapshotFetcher) -> None:
        self.fetcher = fetcher

    def run(
        self,
        *,
        context: ConnectorContext,
        payload: dict[str, Any],
    ) -> ConnectorRunOutput:
        del payload

        refresh_policy = context.refresh_policy_json
        seed_urls = [str(url) for url in refresh_policy.get("seed_urls", [])]
        if not seed_urls:
            raise ValueError("Public-page connector requires refresh_policy_json.seed_urls")

        selector = refresh_policy.get("listing_link_selector")
        patterns = [
            re.compile(pattern)
            for pattern in refresh_policy.get("listing_url_patterns", [])
        ]
        max_listings = int(refresh_policy.get("max_listings", 10))

        assets: list[ConnectorAsset] = []
        listing_urls: list[str] = []

        for index, seed_url in enumerate(seed_urls, start=1):
            if selector:
                fetched_seed = self.fetcher.fetch_asset(seed_url)
                assets.append(
                    ConnectorAsset(
                        asset_key=f"seed_{index}_html",
                        asset_type="HTML",
                        role="SEED_PAGE",
                        original_url=fetched_seed.final_url,
                        content=fetched_seed.content,
                        content_type=fetched_seed.content_type,
                        fetched_at=fetched_seed.fetched_at,
                        metadata={
                            "status_code": fetched_seed.status_code,
                            "headers": fetched_seed.headers,
                            "page_title": fetched_seed.page_title,
                        },
                    )
                )
                listing_urls.extend(
                    _discover_listing_links(
                        html=fetched_seed.content.decode("utf-8", errors="ignore"),
                        base_url=fetched_seed.final_url,
                        selector=str(selector),
                        patterns=patterns,
                    )
                )
            else:
                listing_urls.append(normalize_url(seed_url))

        deduped_urls: list[str] = []
        seen_urls: set[str] = set()
        for listing_url in listing_urls:
            normalized = normalize_url(listing_url)
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            deduped_urls.append(normalized)
            if len(deduped_urls) >= max_listings:
                break

        listings = []
        for index, listing_url in enumerate(deduped_urls, start=1):
            captured = capture_listing_page(
                fetcher=self.fetcher,
                url=listing_url,
                asset_prefix=f"public_listing_{index}",
            )
            assets.extend(captured.assets)
            listings.append(captured.listing)

        parse_status = SourceParseStatus.PARSED if listings else SourceParseStatus.FAILED
        observed_at = listings[0].observed_at if listings else assets[0].fetched_at

        return ConnectorRunOutput(
            source_name=context.source_name,
            source_family=self.connector_type.value.lower(),
            source_uri=seed_urls[0],
            observed_at=observed_at,
            coverage_note=(
                "Generic compliant public-page connector processed "
                f"{len(deduped_urls)} listing page(s)."
            ),
            parse_status=parse_status,
            manifest_json={
                "connector_type": self.connector_type.value,
                "requested_by": context.requested_by,
                "seed_urls": seed_urls,
                "listing_urls": deduped_urls,
                "selector": selector,
                "asset_count": len(assets),
                "listing_count": len(listings),
            },
            assets=assets,
            listings=listings,
        )


def _discover_listing_links(
    *,
    html: str,
    base_url: str,
    selector: str,
    patterns: list[re.Pattern[str]],
) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    for anchor in soup.select(selector):
        href = anchor.get("href")
        if not href:
            continue
        absolute_url = normalize_url(urljoin(base_url, href))
        if patterns and not any(pattern.search(absolute_url) for pattern in patterns):
            continue
        urls.append(absolute_url)

    return urls
