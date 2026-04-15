from dataclasses import dataclass
from datetime import datetime


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

