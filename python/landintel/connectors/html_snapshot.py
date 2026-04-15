from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from landintel.config import Settings
from landintel.connectors.base import FetchedAsset


class HtmlSnapshotFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch(self, url: str) -> FetchedAsset:
        with httpx.Client(
            follow_redirects=True,
            timeout=self.settings.snapshot_http_timeout_seconds,
            headers={"User-Agent": "landintel-phase0/0.1"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        content_type = response.headers.get("content-type", "text/html; charset=utf-8")
        return FetchedAsset(
            requested_url=url,
            final_url=str(response.url),
            content=response.content,
            content_type=content_type,
            status_code=response.status_code,
            fetched_at=datetime.now(UTC),
            headers=dict(response.headers),
            page_title=title,
        )

