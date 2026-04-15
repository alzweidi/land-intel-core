from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from landintel.domain.enums import (
    ConnectorType,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SourceParseStatus,
)


@dataclass(slots=True)
class FetchedAsset:
    requested_url: str
    final_url: str
    content: bytes
    content_type: str
    status_code: int
    fetched_at: datetime
    headers: dict[str, str]
    page_title: str | None


@dataclass(slots=True)
class ConnectorContext:
    source_name: str
    connector_type: ConnectorType
    refresh_policy_json: dict[str, Any]
    requested_by: str | None


@dataclass(slots=True)
class ConnectorAsset:
    asset_key: str
    asset_type: str
    role: str
    original_url: str
    content: bytes
    content_type: str
    fetched_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedListing:
    source_listing_id: str
    canonical_url: str
    observed_at: datetime
    listing_type: ListingType = ListingType.UNKNOWN
    headline: str | None = None
    description_text: str | None = None
    guide_price_gbp: int | None = None
    price_basis_type: PriceBasisType = PriceBasisType.UNKNOWN
    status: ListingStatus = ListingStatus.UNKNOWN
    auction_date: date | None = None
    address_text: str | None = None
    normalized_address: str | None = None
    lat: float | None = None
    lon: float | None = None
    brochure_asset_key: str | None = None
    map_asset_key: str | None = None
    raw_record_json: dict[str, Any] = field(default_factory=dict)
    search_text: str = ""


@dataclass(slots=True)
class ConnectorRunOutput:
    source_name: str
    source_family: str
    source_uri: str
    observed_at: datetime
    coverage_note: str
    parse_status: SourceParseStatus
    manifest_json: dict[str, Any]
    assets: list[ConnectorAsset]
    listings: list[ParsedListing]


class ComplianceError(PermissionError):
    pass


class ConnectorError(RuntimeError):
    pass


class ListingConnector(ABC):
    connector_type: ConnectorType

    @abstractmethod
    def run(
        self,
        *,
        context: ConnectorContext,
        payload: dict[str, Any],
    ) -> ConnectorRunOutput:
        raise NotImplementedError
