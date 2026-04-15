from typing import Any

from landintel.connectors.base import ConnectorContext, ConnectorRunOutput, ListingConnector
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.connectors.page_capture import capture_listing_page
from landintel.domain.enums import ConnectorType, SourceParseStatus


class ManualUrlConnector(ListingConnector):
    connector_type = ConnectorType.MANUAL_URL

    def __init__(self, fetcher: HtmlSnapshotFetcher) -> None:
        self.fetcher = fetcher

    def run(
        self,
        *,
        context: ConnectorContext,
        payload: dict[str, Any],
    ) -> ConnectorRunOutput:
        url = str(payload["url"])
        captured = capture_listing_page(fetcher=self.fetcher, url=url, asset_prefix="manual")

        parse_status = (
            SourceParseStatus.PARSED
            if captured.listing.search_text or captured.listing.headline
            else SourceParseStatus.PARTIAL
        )
        return ConnectorRunOutput(
            source_name=context.source_name,
            source_family=self.connector_type.value.lower(),
            source_uri=captured.listing.canonical_url,
            observed_at=captured.listing.observed_at,
            coverage_note="Manual URL intake captured one listing page and any linked PDFs.",
            parse_status=parse_status,
            manifest_json={
                "connector_type": self.connector_type.value,
                "requested_by": context.requested_by,
                "input_url": url,
                "asset_count": len(captured.assets),
                "document_count": sum(1 for asset in captured.assets if asset.asset_type == "PDF"),
            },
            assets=captured.assets,
            listings=[captured.listing],
        )
