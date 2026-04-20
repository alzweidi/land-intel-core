from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx


@dataclass(slots=True)
class FetchedHttpAsset:
    requested_url: str
    final_url: str
    content: bytes
    content_type: str
    status_code: int
    fetched_at: datetime
    headers: dict[str, str]


def fetch_http_asset(url: str, *, timeout_seconds: int) -> FetchedHttpAsset:
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={"User-Agent": "landintel-official-refresh/0.1"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()

    return FetchedHttpAsset(
        requested_url=url,
        final_url=str(response.url),
        content=response.content,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        status_code=response.status_code,
        fetched_at=datetime.now(UTC),
        headers=dict(response.headers),
    )
