import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from landintel.connectors.base import FetchedAsset
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.domain.enums import SourceFreshnessStatus
from landintel.domain.models import JobRun, RawAsset, SourceSnapshot
from landintel.storage.base import StorageAdapter

UUID_NAMESPACE = uuid.UUID("5e8e30f6-3102-4e1d-b4a1-4e54f6dd6a9d")


def deterministic_uuid(job_id: uuid.UUID, suffix: str) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, f"{job_id}:{suffix}")


def sha256_hexdigest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(slots=True)
class ManualUrlSnapshotResult:
    source_snapshot_id: uuid.UUID
    raw_asset_id: uuid.UUID
    storage_path: str


class ManualUrlSnapshotService:
    def __init__(self, fetcher: HtmlSnapshotFetcher, storage: StorageAdapter) -> None:
        self.fetcher = fetcher
        self.storage = storage

    def execute(self, session: Session, job: JobRun) -> ManualUrlSnapshotResult:
        url = str(job.payload_json["url"])
        source_name = str(job.payload_json.get("source_name", "manual_url"))

        source_snapshot_id = deterministic_uuid(job.id, "source_snapshot")
        raw_asset_id = deterministic_uuid(job.id, "raw_asset_html")

        source_snapshot = session.get(SourceSnapshot, source_snapshot_id)
        raw_asset = session.get(RawAsset, raw_asset_id)
        if source_snapshot is not None and raw_asset is not None:
            return ManualUrlSnapshotResult(
                source_snapshot_id=source_snapshot_id,
                raw_asset_id=raw_asset_id,
                storage_path=raw_asset.storage_path,
            )

        fetched = self.fetcher.fetch(url)
        storage_path = f"raw/manual-url/{job.id}/{raw_asset_id}.html"
        self.storage.put_bytes(storage_path, fetched.content, content_type=fetched.content_type)

        content_hash = sha256_hexdigest(fetched.content)
        schema_hash = sha256_hexdigest(b"manual_url_snapshot_v1")
        manifest_json = self._build_manifest(job=job, fetched=fetched)

        if source_snapshot is None:
            source_snapshot = SourceSnapshot(
                id=source_snapshot_id,
                source_family="manual_url",
                source_name=source_name,
                source_uri=url,
                acquired_at=fetched.fetched_at,
                effective_from=None,
                effective_to=None,
                schema_hash=schema_hash,
                content_hash=content_hash,
                coverage_note="Manual URL intake snapshot",
                freshness_status=SourceFreshnessStatus.FRESH,
                manifest_json=manifest_json,
            )
            session.add(source_snapshot)

        if raw_asset is None:
            raw_asset = RawAsset(
                id=raw_asset_id,
                source_snapshot_id=source_snapshot_id,
                asset_type="HTML",
                original_url=url,
                storage_path=storage_path,
                mime_type=fetched.content_type,
                content_sha256=content_hash,
                size_bytes=len(fetched.content),
                fetched_at=fetched.fetched_at,
            )
            session.add(raw_asset)

        session.flush()
        return ManualUrlSnapshotResult(
            source_snapshot_id=source_snapshot_id,
            raw_asset_id=raw_asset_id,
            storage_path=storage_path,
        )

    @staticmethod
    def _build_manifest(job: JobRun, fetched: FetchedAsset) -> dict[str, object]:
        return {
            "job_id": str(job.id),
            "job_type": job.job_type.value,
            "requested_by": job.requested_by,
            "request": {"url": fetched.requested_url},
            "response": {
                "final_url": fetched.final_url,
                "status_code": fetched.status_code,
                "headers": fetched.headers,
                "page_title": fetched.page_title,
            },
        }

