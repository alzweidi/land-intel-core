import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from landintel.connectors.base import (
    ConnectorAsset,
    ConnectorContext,
    ConnectorRunOutput,
    ListingConnector,
    ParsedListing,
)
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.connectors.page_capture import capture_listing_page
from landintel.domain.enums import ConnectorType, ListingStatus, ListingType, SourceParseStatus
from landintel.listings.parsing import (
    build_search_text,
    detect_listing_type,
    normalize_address,
    normalize_space,
    normalize_url,
    parse_price,
)


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
        sitemap_urls = [str(url) for url in refresh_policy.get("sitemap_urls", [])]
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

        for index, sitemap_url in enumerate(sitemap_urls, start=1):
            fetched_sitemap = self.fetcher.fetch_asset(sitemap_url)
            assets.append(
                ConnectorAsset(
                    asset_key=f"sitemap_{index}_xml",
                    asset_type="XML",
                    role="SEED_SITEMAP",
                    original_url=fetched_sitemap.final_url,
                    content=fetched_sitemap.content,
                    content_type=fetched_sitemap.content_type,
                    fetched_at=fetched_sitemap.fetched_at,
                    metadata={
                        "status_code": fetched_sitemap.status_code,
                        "headers": fetched_sitemap.headers,
                    },
                )
            )
            listing_urls.extend(
                _discover_sitemap_listing_links(
                    xml_payload=fetched_sitemap.content.decode("utf-8", errors="ignore"),
                    patterns=patterns,
                )
            )

        deduped_urls: list[str] = []
        seen_urls: set[str] = set()
        for listing_url in listing_urls:
            normalized = normalize_url(listing_url)
            if normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            deduped_urls.append(normalized)

        listings = []
        accepted_urls: list[str] = []
        filtered_out_urls: list[str] = []
        skipped_listing_urls: list[dict[str, str]] = []
        processed_listing_urls: list[str] = []
        for listing_url in deduped_urls:
            if max_listings > 0 and len(accepted_urls) >= max_listings:
                break
            processed_listing_urls.append(listing_url)
            index = len(processed_listing_urls)
            try:
                captured = capture_listing_page(
                    fetcher=self.fetcher,
                    url=listing_url,
                    asset_prefix=f"public_listing_{index}",
                )
            except httpx.HTTPError as exc:
                skipped_listing_urls.append(
                    {
                        "url": listing_url,
                        "reason": exc.__class__.__name__,
                    }
                )
                continue
            assets.extend(captured.assets)
            listing_html = (
                captured.assets[0].content.decode("utf-8", errors="ignore")
                if captured.assets
                else ""
            )
            listing = _apply_page_extract_mode(
                listing=captured.listing,
                html=listing_html,
                refresh_policy=refresh_policy,
            )
            listing_canonical_url = getattr(listing, "canonical_url", None) or listing_url
            if _listing_passes_source_fit(listing=listing, refresh_policy=refresh_policy):
                listings.append(listing)
                accepted_urls.append(listing_canonical_url)
            else:
                filtered_out_urls.append(listing_canonical_url)

        parse_status = SourceParseStatus.PARSED if listings else SourceParseStatus.FAILED
        observed_at = (
            listings[0].observed_at
            if listings
            else (assets[0].fetched_at if assets else None)
        )
        if observed_at is None:
            raise ValueError("Public-page connector did not fetch any assets.")

        return ConnectorRunOutput(
            source_name=context.source_name,
            source_family=self.connector_type.value.lower(),
            source_uri=seed_urls[0],
            observed_at=observed_at,
            coverage_note=(
                "Generic compliant public-page connector processed "
                f"{len(processed_listing_urls)} listing page(s), skipped "
                f"{len(skipped_listing_urls)} stale or unreachable page(s), and accepted "
                f"{len(accepted_urls)} qualifying listing(s)."
            ),
            parse_status=parse_status,
            manifest_json={
                "connector_type": self.connector_type.value,
                "requested_by": context.requested_by,
                "seed_urls": seed_urls,
                "sitemap_urls": sitemap_urls,
                "listing_urls": processed_listing_urls,
                "discovered_listing_urls": deduped_urls,
                "accepted_listing_urls": accepted_urls,
                "filtered_out_listing_urls": filtered_out_urls,
                "skipped_listing_urls": skipped_listing_urls,
                "selector": selector,
                "asset_count": len(assets),
                "processed_listing_count": len(processed_listing_urls),
                "discovered_listing_count": len(deduped_urls),
                "listing_count": len(listings),
                "filtered_out_count": len(filtered_out_urls),
                "skipped_count": len(skipped_listing_urls),
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


def _discover_sitemap_listing_links(
    *,
    xml_payload: str,
    patterns: list[re.Pattern[str]],
) -> list[str]:
    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError:
        return []

    urls: list[str] = []
    for loc in root.findall(".//{*}loc"):
        if loc.text is None:
            continue
        absolute_url = normalize_url(loc.text)
        if patterns and not any(pattern.search(absolute_url) for pattern in patterns):
            continue
        urls.append(absolute_url)
    return urls


def _apply_page_extract_mode(
    *,
    listing: ParsedListing,
    html: str,
    refresh_policy: dict[str, Any],
) -> ParsedListing:
    mode = str(refresh_policy.get("page_extract_mode") or "").strip()
    if mode == "ideal_land_v1":
        return _apply_ideal_land_extract(listing=listing, html=html)
    return listing


def _apply_ideal_land_extract(*, listing: ParsedListing, html: str) -> ParsedListing:
    soup = BeautifulSoup(html, "html.parser")

    headline = _node_text(soup.find("h1")) or listing.headline
    badge_container = soup.select_one("div.mt-8.mb-8")
    badges = (
        [
            text
            for text in (_node_text(span) for span in badge_container.select("span"))
            if text
        ]
        if badge_container is not None
        else []
    )
    status_label = badges[0] if badges else None
    property_type_label = badges[1] if len(badges) > 1 else None
    address = _node_text(soup.select_one("h1 + div span")) or listing.address_text
    description = _section_text(soup, "Description") or listing.description_text
    key_features = _section_text(soup, "Key Features")
    specifications = _extract_specifications(soup)
    planning_status = specifications.get("Planning Status")
    units = specifications.get("Units")
    tenure = specifications.get("Tenure")
    floor_area_text = specifications.get("Floor Area")
    price_container = soup.select_one("h1 + div + div.mb-8") or soup.select_one("div.mb-8")
    price_gbp, price_basis_type = parse_price(_node_text(price_container))

    listing.headline = headline
    listing.description_text = description
    listing.address_text = address
    listing.normalized_address = normalize_address(address)
    listing.status = _ideal_land_status(status_label) or listing.status
    listing.listing_type = _ideal_land_listing_type(
        property_type_label=property_type_label,
        headline=headline,
        description=description,
        planning_status=planning_status,
    )
    if price_gbp is not None or price_basis_type != listing.price_basis_type:
        listing.guide_price_gbp = price_gbp
        listing.price_basis_type = price_basis_type
    listing.raw_record_json.update(
        {
            "source_status_label": status_label,
            "source_property_type_label": property_type_label,
            "source_planning_status": planning_status,
            "source_units": units,
            "source_tenure": tenure,
            "source_floor_area_text": floor_area_text,
            "address_text": address,
        }
    )
    listing.search_text = build_search_text(
        headline,
        description,
        address,
        property_type_label,
        planning_status,
        key_features,
    )
    return listing


def _listing_passes_source_fit(
    *,
    listing: ParsedListing,
    refresh_policy: dict[str, Any],
) -> bool:
    fit_policy = refresh_policy.get("source_fit_policy")
    if not isinstance(fit_policy, dict):
        return True

    raw_record = listing.raw_record_json or {}
    status_label = _lower_or_none(raw_record.get("source_status_label"))
    property_type_label = _lower_or_none(raw_record.get("source_property_type_label"))
    planning_status = _lower_or_none(raw_record.get("source_planning_status"))
    search_text = " ".join(
        part
        for part in (
            listing.headline,
            listing.description_text,
            listing.address_text,
            listing.search_text,
        )
        if part
    ).lower()

    required_statuses = _normalized_values(fit_policy.get("required_statuses"))
    if required_statuses and status_label not in required_statuses:
        return False

    allowed_property_types = _normalized_values(fit_policy.get("allowed_property_types"))
    if allowed_property_types and property_type_label not in allowed_property_types:
        return False

    required_planning_statuses = _normalized_values(fit_policy.get("required_planning_statuses"))
    if required_planning_statuses and planning_status not in required_planning_statuses:
        return False

    required_listing_types = _normalized_values(fit_policy.get("required_listing_types"))
    if required_listing_types and listing.listing_type.value.lower() not in required_listing_types:
        return False

    required_listing_statuses = _normalized_values(fit_policy.get("required_listing_statuses"))
    if required_listing_statuses and listing.status.value.lower() not in required_listing_statuses:
        return False

    if fit_policy.get("require_address_text") and not listing.address_text:
        return False

    required_text_markers_any = _normalized_values(fit_policy.get("required_text_contains_any"))
    if required_text_markers_any and not any(
        marker in search_text for marker in required_text_markers_any
    ):
        return False

    required_text_markers_all = _normalized_values(fit_policy.get("required_text_contains_all"))
    if required_text_markers_all and not all(
        marker in search_text for marker in required_text_markers_all
    ):
        return False

    for marker in _normalized_values(fit_policy.get("excluded_text_contains_any")):
        if marker and marker in search_text:
            return False

    if fit_policy.get("require_point_coordinates") and (
        listing.lat is None or listing.lon is None
    ):
        return False

    if fit_policy.get("require_brochure_asset") and not listing.brochure_asset_key:
        return False

    if fit_policy.get("require_map_asset") and not listing.map_asset_key:
        return False

    bounds = fit_policy.get("required_coordinate_bbox_4326")
    if isinstance(bounds, list) and len(bounds) == 4:
        if listing.lat is None or listing.lon is None:
            return False
        min_lon, min_lat, max_lon, max_lat = [float(value) for value in bounds]
        if not (min_lon <= listing.lon <= max_lon and min_lat <= listing.lat <= max_lat):
            return False

    return True


def _node_text(node: Any) -> str | None:
    if node is None:
        return None
    return normalize_space(node.get_text(" ", strip=True))


def _section_text(soup: BeautifulSoup, heading: str) -> str | None:
    for section in soup.find_all("section"):
        title = _node_text(section.find(["h2", "h3"]))
        if title != heading:
            continue
        prose = section.select_one("div.prose")
        return _node_text(prose) or _node_text(section)
    return None


def _extract_specifications(soup: BeautifulSoup) -> dict[str, str]:
    specifications: dict[str, str] = {}
    for section in soup.find_all("section"):
        if _node_text(section.find(["h2", "h3"])) != "Specifications":
            continue
        for row in section.select("div.flex.justify-between"):
            values = [
                text
                for text in (_node_text(span) for span in row.find_all("span"))
                if text
            ]
            if len(values) < 2:
                continue
            specifications[values[0]] = values[1]
        break
    return specifications


def _ideal_land_status(status_label: str | None) -> ListingStatus | None:
    lowered = _lower_or_none(status_label)
    if lowered == "available":
        return ListingStatus.LIVE
    if lowered == "under offer":
        return ListingStatus.UNDER_OFFER
    if lowered in {"sold stc", "sstc"}:
        return ListingStatus.SOLD_STC
    if lowered in {"acquired", "withdrawn"}:
        return ListingStatus.WITHDRAWN
    if lowered == "auction":
        return ListingStatus.AUCTION
    return None


def _ideal_land_listing_type(
    *,
    property_type_label: str | None,
    headline: str | None,
    description: str | None,
    planning_status: str | None,
) -> ListingType:
    lowered = _lower_or_none(property_type_label)
    if lowered == "mixed use":
        return ListingType.LAND_WITH_BUILDING
    if lowered == "garage court":
        return ListingType.GARAGE_COURT
    if lowered in {"backland", "development site"}:
        return ListingType.LAND
    return detect_listing_type(property_type_label, headline, description, planning_status)


def _normalized_values(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        item.strip().lower()
        for item in value
        if isinstance(item, str) and item.strip()
    }


def _lower_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None
