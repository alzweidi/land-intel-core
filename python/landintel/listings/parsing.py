import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import StringIO
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from landintel.connectors.base import ParsedListing
from landintel.domain.enums import DocumentType, ListingStatus, ListingType, PriceBasisType

MONTH_LOOKUP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
PRICE_PATTERN = re.compile(r"£\s*([0-9][0-9,]*(?:\.[0-9]+)?)(m|mn|million|k|thousand)?", re.I)
DATE_PATTERN = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})\s+(?P<year>\d{4})",
    re.I,
)
LAT_LON_PATTERN = re.compile(
    r"(?P<lat>5[0-9]\.\d{3,})[^0-9+-]+(?P<lon>[+-]?0\.\d{3,})",
    re.I,
)
UK_POSTCODE_PATTERN = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
    re.I,
)
LONG_LAT_JSON_PATTERN = re.compile(
    r'long_lat"\s*:\s*"\{\\?"lat\\?":(?P<lat>-?\d+\.\d+),\\?"lng\\?":(?P<lon>-?\d+\.\d+)\}',
    re.I,
)
HTML_ATTRIBUTE_LAT_LON_PATTERNS = (
    re.compile(
        r'data-lat="\s*(?P<lat>-?\d+\.\d+)\s*"[^>]+data-l(?:ng|on)="\s*(?P<lon>-?\d+\.\d+)\s*"',
        re.I,
    ),
    re.compile(
        r"data-lat='\s*(?P<lat>-?\d+\.\d+)\s*'[^>]+data-l(?:ng|on)='\s*(?P<lon>-?\d+\.\d+)\s*'",
        re.I,
    ),
    re.compile(
        r"loadMap\([^)]*'(?P<lat>-?\d+\.\d+)'[^)]*'(?P<lon>-?\d+\.\d+)'",
        re.I,
    ),
    re.compile(r"[?&]q=(?P<lat>-?\d+\.\d+),(?P<lon>-?\d+\.\d+)", re.I),
)

GENERIC_HEADLINES = {
    "login to see times and book a viewing",
    "local information",
    "legal documents",
    "epc rating",
    "guide prices and common auction conditions",
    "addendums",
}
GENERIC_DOCUMENT_MARKERS = (
    "common_conditions",
    "common auction conditions",
    "auction_notices",
    "auction notices",
    "terms_and_conditions",
)


@dataclass(slots=True)
class DiscoveredDocumentLink:
    url: str
    doc_type: DocumentType
    label: str


def normalize_space(value: str | list[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = ", ".join(part for part in value if part)
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed or None


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    cleaned = parsed._replace(fragment="")
    normalized = urlunparse(cleaned)
    return normalized.rstrip("/") if parsed.path not in {"", "/"} else normalized


def normalize_address(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None

    replacements = {
        " rd ": " road ",
        " st ": " street ",
        " ave ": " avenue ",
        " ln ": " lane ",
        " ct ": " court ",
    }
    normalized = f" {text.lower()} "
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def _clean_title(value: str | None) -> str | None:
    text = normalize_space(value)
    if not text:
        return None
    if "|" in text:
        text = text.split("|", maxsplit=1)[1]
    return normalize_space(text)


def _is_generic_headline(value: str | None) -> bool:
    text = normalize_space(value)
    if not text:
        return True
    return text.lower() in GENERIC_HEADLINES


def _selector_text(soup: BeautifulSoup, selector: str) -> str | None:
    node = soup.select_one(selector)
    if node is None:
        return None
    return normalize_space(node.get_text(" ", strip=True))


def _extract_savills_description(soup: BeautifulSoup) -> str | None:
    description = _selector_text(soup, ".lot-details-description")
    if description:
        description = re.sub(r"^Description\s*", "", description, flags=re.I).strip()
        return normalize_space(description)

    key_features = _selector_text(soup, ".lot-details-top")
    if not key_features:
        return None

    cleaned = key_features
    for marker in (
        "Book a viewing",
        "View Virtual Tour",
        "Remove from wishlist",
        "Add to wishlist",
        "Key features",
        "Contact an agent",
    ):
        cleaned = cleaned.replace(marker, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return normalize_space(cleaned)


def _extract_address_from_title(headline: str | None) -> str | None:
    text = _clean_title(headline)
    if not text:
        return None
    normalized = f" {text.lower()} "
    if " london " in normalized:
        return text
    if UK_POSTCODE_PATTERN.search(text):
        return text
    if text.count(",") >= 2 and any(
        token in normalized
        for token in (" road", " street", " lane", " avenue", " close", " way", " court")
    ):
        return text
    return None


def build_search_text(*parts: str | None) -> str:
    return normalize_space(" ".join(part for part in parts if part)) or ""


def extract_text_content(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return normalize_space(soup.get_text(" ", strip=True)) or ""


def parse_price(value: str | None) -> tuple[int | None, PriceBasisType]:
    text = normalize_space(value)
    if not text:
        return None, PriceBasisType.UNKNOWN

    match = PRICE_PATTERN.search(text)
    if match is None:
        basis = detect_price_basis(text)
        return None, basis

    amount = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    if suffix in {"m", "mn", "million"}:
        amount *= 1_000_000
    elif suffix in {"k", "thousand"}:
        amount *= 1_000

    return round(amount), detect_price_basis(text)


def detect_price_basis(text: str) -> PriceBasisType:
    lowered = text.lower()
    if "price on application" in lowered or "poa" in lowered:
        return PriceBasisType.PRICE_ON_APPLICATION
    if "offers in excess" in lowered:
        return PriceBasisType.OFFERS_IN_EXCESS_OF
    if "offers over" in lowered:
        return PriceBasisType.OFFERS_OVER
    if "guide price" in lowered and "auction" in lowered:
        return PriceBasisType.AUCTION_GUIDE
    if "guide price" in lowered:
        return PriceBasisType.GUIDE_PRICE
    if "asking price" in lowered:
        return PriceBasisType.ASKING_PRICE
    return PriceBasisType.UNKNOWN


def parse_optional_date(value: str | None) -> date | None:
    text = normalize_space(value)
    if not text:
        return None

    match = DATE_PATTERN.search(text)
    if match is None:
        return None

    month = MONTH_LOOKUP.get(match.group("month")[:3].lower())
    if month is None:
        return None

    try:
        return date(int(match.group("year")), month, int(match.group("day")))
    except ValueError:
        return None


def detect_listing_status(*values: str | None) -> ListingStatus:
    text = " ".join(value for value in values if value).lower()
    if "sold stc" in text or "sstc" in text:
        return ListingStatus.SOLD_STC
    if "under offer" in text:
        return ListingStatus.UNDER_OFFER
    if "withdrawn" in text:
        return ListingStatus.WITHDRAWN
    if "auction" in text:
        return ListingStatus.AUCTION
    if text:
        return ListingStatus.LIVE
    return ListingStatus.UNKNOWN


def detect_listing_type(*values: str | None) -> ListingType:
    text = " ".join(value for value in values if value).lower()
    if "garage court" in text:
        return ListingType.GARAGE_COURT
    if "site with building" in text or "land with building" in text:
        return ListingType.LAND_WITH_BUILDING
    if "redevelopment" in text or "development opportunity" in text:
        return ListingType.REDEVELOPMENT_SITE
    if any(keyword in text for keyword in ("land", "plot", "site")):
        return ListingType.LAND
    return ListingType.UNKNOWN


def extract_coordinates_from_text(text: str) -> tuple[float | None, float | None]:
    match = LAT_LON_PATTERN.search(text)
    if match is not None:
        return float(match.group("lat")), float(match.group("lon"))
    return None, None


def extract_coordinates_from_html(html: str) -> tuple[float | None, float | None]:
    match = LONG_LAT_JSON_PATTERN.search(html)
    if match is not None:
        return float(match.group("lat")), float(match.group("lon"))
    for pattern in HTML_ATTRIBUTE_LAT_LON_PATTERNS:
        match = pattern.search(html)
        if match is not None:
            return float(match.group("lat")), float(match.group("lon"))
    return extract_coordinates_from_text(html)


def _load_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not script.string:
            continue
        try:
            payload = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            records.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            records.append(payload)
    return records


def discover_document_links(html: str, *, base_url: str) -> list[DiscoveredDocumentLink]:
    soup = BeautifulSoup(html, "html.parser")
    documents: list[DiscoveredDocumentLink] = []
    seen_indexes: dict[str, int] = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        label = normalize_space(anchor.get_text(" ", strip=True)) or ""
        absolute_url = normalize_url(urljoin(base_url, href))

        lowered = f"{absolute_url} {label}".lower()
        if ".pdf" not in lowered and "pdf.php" not in lowered:
            continue
        if any(marker in lowered for marker in GENERIC_DOCUMENT_MARKERS):
            continue

        doc_type = DocumentType.BROCHURE
        if any(marker in lowered for marker in ("map", "site plan", "floor plan", "floorplan")):
            doc_type = DocumentType.MAP

        existing_index = seen_indexes.get(absolute_url)
        if existing_index is not None:
            existing = documents[existing_index]
            if doc_type == DocumentType.MAP and existing.doc_type != DocumentType.MAP:
                existing.doc_type = DocumentType.MAP
                if label:
                    existing.label = label
            elif not existing.label and label:
                existing.label = label
            continue

        seen_indexes[absolute_url] = len(documents)
        documents.append(DiscoveredDocumentLink(url=absolute_url, doc_type=doc_type, label=label))

    return documents


def parse_html_listing(
    *,
    html: str,
    canonical_url: str,
    page_title: str | None,
    observed_at: datetime | None = None,
    brochure_asset_key: str | None = None,
    map_asset_key: str | None = None,
) -> ParsedListing:
    soup = BeautifulSoup(html, "html.parser")
    json_ld_records = _load_json_ld(soup)

    headline = None
    description = None
    address = None
    lat = lon = None

    for record in json_ld_records:
        headline = headline or normalize_space(
            record.get("name") if isinstance(record.get("name"), str) else None
        )
        description = description or normalize_space(
            record.get("description") if isinstance(record.get("description"), str) else None
        )

        address_payload = record.get("address")
        if isinstance(address_payload, dict):
            address = address or normalize_space(
                " ".join(
                    str(address_payload.get(part, ""))
                    for part in (
                        "streetAddress",
                        "addressLocality",
                        "postalCode",
                    )
                )
            )

        geo_payload = record.get("geo")
        if isinstance(geo_payload, dict):
            record_lat = geo_payload.get("latitude")
            record_lon = geo_payload.get("longitude")
            if record_lat is not None and record_lon is not None:
                lat = float(record_lat)
                lon = float(record_lon)

    title_headline = _clean_title(page_title)
    h1 = next(
        (
            tag
            for tag in soup.find_all("h1")
            if not _is_generic_headline(tag.get_text(" ", strip=True))
        ),
        None,
    )
    headline = headline or normalize_space(
        soup.find("meta", attrs={"property": "og:title"}).get("content")
        if soup.find("meta", attrs={"property": "og:title"})
        else None
    )
    if _is_generic_headline(headline):
        headline = None
    headline = headline or normalize_space(h1.get_text(" ", strip=True) if h1 else None)
    headline = headline or title_headline

    description = description or normalize_space(
        soup.find("meta", attrs={"name": "description"}).get("content")
        if soup.find("meta", attrs={"name": "description"})
        else None
    )
    if description and description.startswith("Savills Property Auctions"):
        description = None
    description = description or _extract_savills_description(soup)
    if description is None:
        paragraphs = [
            normalize_space(paragraph.get_text(" ", strip=True))
            for paragraph in soup.find_all("p")
        ]
        description = next((paragraph for paragraph in paragraphs if paragraph), None)

    address = address or normalize_space(
        soup.find(attrs={"itemprop": "streetAddress"}).get_text(" ", strip=True)
        if soup.find(attrs={"itemprop": "streetAddress"})
        else None
    )
    address = address or _extract_address_from_title(headline or title_headline)

    text_content = extract_text_content(html)
    status_text = _selector_text(soup, ".lot-status-container")
    price_text = _selector_text(soup, ".sv-property-price")
    page_price, price_basis = parse_price(text_content)
    auction_date = parse_optional_date(text_content)
    if price_text:
        page_price, price_basis = parse_price(price_text)
    status = detect_listing_status(status_text, headline, description, text_content)
    listing_type = detect_listing_type(headline, description, text_content)

    if lat is None or lon is None:
        query = parse_qs(urlparse(canonical_url).query)
        if "lat" in query and "lon" in query:
            try:
                lat = float(query["lat"][0])
                lon = float(query["lon"][0])
            except (ValueError, TypeError):
                lat = lon = None

    if lat is None or lon is None:
        lat, lon = extract_coordinates_from_text(text_content)
    if lat is None or lon is None:
        lat, lon = extract_coordinates_from_html(html)

    normalized_address = normalize_address(address)
    observed = observed_at or datetime.now(UTC)
    source_listing_id = normalize_url(canonical_url)

    return ParsedListing(
        source_listing_id=source_listing_id,
        canonical_url=normalize_url(canonical_url),
        observed_at=observed,
        listing_type=listing_type,
        headline=headline,
        description_text=description,
        guide_price_gbp=page_price,
        price_basis_type=price_basis,
        status=status,
        auction_date=auction_date,
        address_text=address,
        normalized_address=normalized_address,
        lat=lat,
        lon=lon,
        brochure_asset_key=brochure_asset_key,
        map_asset_key=map_asset_key,
        raw_record_json={
            "canonical_url": normalize_url(canonical_url),
            "page_title": page_title,
            "headline": headline,
            "description_text": description,
            "address_text": address,
            "lat": lat,
            "lon": lon,
            "auction_date": auction_date.isoformat() if auction_date else None,
        },
        search_text=build_search_text(headline, description, address),
    )


def parse_csv_rows(csv_text: str, *, source_name: str) -> list[ParsedListing]:
    reader = csv.DictReader(StringIO(csv_text))
    listings: list[ParsedListing] = []

    for row_number, row in enumerate(reader, start=1):
        normalized_row = {
            str(key).strip().lower(): normalize_space(value)
            for key, value in row.items()
        }
        headline = _first_present(normalized_row, "headline", "title", "name")
        description = _first_present(normalized_row, "description", "details", "summary")
        canonical_url = normalize_url(
            _first_present(normalized_row, "canonical_url", "url", "link")
            or f"csv://{source_name}/row-{row_number}"
        )
        source_listing_id = (
            _first_present(
                normalized_row,
                "source_listing_id",
                "listing_id",
                "id",
                "reference",
                "ref",
            )
            or canonical_url
        )
        price_value = _first_present(normalized_row, "guide_price_gbp", "price", "guide_price")
        guide_price_gbp, price_basis_type = parse_price(price_value or description or headline)
        status = detect_listing_status(
            _first_present(normalized_row, "status", "listing_status"),
            headline,
            description,
        )
        address = _first_present(normalized_row, "address", "address_text", "location")
        listing_type = detect_listing_type(
            _first_present(normalized_row, "listing_type"),
            headline,
            description,
        )
        auction_date = parse_optional_date(_first_present(normalized_row, "auction_date"))
        lat = _parse_float(_first_present(normalized_row, "lat", "latitude"))
        lon = _parse_float(_first_present(normalized_row, "lon", "longitude"))

        listings.append(
            ParsedListing(
                source_listing_id=source_listing_id,
                canonical_url=canonical_url,
                observed_at=datetime.now(UTC),
                listing_type=listing_type,
                headline=headline,
                description_text=description,
                guide_price_gbp=guide_price_gbp,
                price_basis_type=price_basis_type,
                status=status,
                auction_date=auction_date,
                address_text=address,
                normalized_address=normalize_address(address),
                lat=lat,
                lon=lon,
                raw_record_json={
                    key: value for key, value in normalized_row.items() if value is not None
                },
                search_text=build_search_text(headline, description, address),
            )
        )

    return listings


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _first_present(row: dict[str, str | None], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None
