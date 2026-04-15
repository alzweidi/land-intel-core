import base64
from datetime import UTC, datetime
from typing import Any

from landintel.connectors.base import (
    ConnectorAsset,
    ConnectorContext,
    ConnectorRunOutput,
    ListingConnector,
)
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.domain.enums import ConnectorType, DocumentType, SourceParseStatus
from landintel.listings.parsing import parse_csv_rows


class CsvImportConnector(ListingConnector):
    connector_type = ConnectorType.CSV_IMPORT

    def __init__(self, fetcher: HtmlSnapshotFetcher) -> None:
        self.fetcher = fetcher

    def run(
        self,
        *,
        context: ConnectorContext,
        payload: dict[str, Any],
    ) -> ConnectorRunOutput:
        filename = str(payload.get("filename", "import.csv"))
        csv_bytes = base64.b64decode(str(payload["csv_base64"]))
        csv_text = csv_bytes.decode("utf-8")
        listings = parse_csv_rows(csv_text, source_name=context.source_name)

        assets = [
            ConnectorAsset(
                asset_key="csv_import_file",
                asset_type="CSV",
                role="CSV_IMPORT",
                original_url=f"csv://{context.source_name}/{filename}",
                content=csv_bytes,
                content_type="text/csv",
                fetched_at=listings[0].observed_at if listings else datetime.now(UTC),
                metadata={"filename": filename},
            )
        ]

        document_counter = 0
        for index, listing in enumerate(listings, start=1):
            brochure_url = str(listing.raw_record_json.get("brochure_url", "") or "").strip()
            map_url = str(listing.raw_record_json.get("map_url", "") or "").strip()
            for doc_url, doc_type in (
                (brochure_url, DocumentType.BROCHURE),
                (map_url, DocumentType.MAP),
            ):
                if not doc_url:
                    continue
                fetched_document = self.fetcher.fetch_asset(doc_url)
                document_counter += 1
                asset_key = f"csv_row_{index}_document_{document_counter}"
                assets.append(
                    ConnectorAsset(
                        asset_key=asset_key,
                        asset_type="PDF",
                        role=doc_type.value,
                        original_url=fetched_document.final_url,
                        content=fetched_document.content,
                        content_type=fetched_document.content_type,
                        fetched_at=fetched_document.fetched_at,
                        metadata={
                            "status_code": fetched_document.status_code,
                            "headers": fetched_document.headers,
                            "doc_type": doc_type.value,
                        },
                    )
                )
                if doc_type == DocumentType.BROCHURE:
                    listing.brochure_asset_key = asset_key
                if doc_type == DocumentType.MAP:
                    listing.map_asset_key = asset_key

        parse_status = SourceParseStatus.PARSED if listings else SourceParseStatus.FAILED
        observed_at = listings[0].observed_at if listings else datetime.now(UTC)

        return ConnectorRunOutput(
            source_name=context.source_name,
            source_family=self.connector_type.value.lower(),
            source_uri=f"csv://{context.source_name}/{filename}",
            observed_at=observed_at,
            coverage_note=f"CSV import captured {len(listings)} listing rows.",
            parse_status=parse_status,
            manifest_json={
                "connector_type": self.connector_type.value,
                "requested_by": context.requested_by,
                "filename": filename,
                "row_count": len(listings),
                "asset_count": len(assets),
            },
            assets=assets,
            listings=listings,
        )
