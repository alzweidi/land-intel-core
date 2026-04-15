from datetime import UTC, datetime
from pathlib import Path

from landintel.connectors.base import FetchedAsset
from landintel.connectors.manual_url import ManualUrlSnapshotService
from landintel.domain.enums import JobStatus
from landintel.domain.models import RawAsset, SourceSnapshot
from landintel.jobs.service import enqueue_manual_url_job, mark_job_succeeded

from services.worker.app.main import process_next_job


class DummyFetcher:
    def fetch(self, url: str) -> FetchedAsset:
        return FetchedAsset(
            requested_url=url,
            final_url=url,
            content=b"<html><title>Example</title><body>stub</body></html>",
            content_type="text/html; charset=utf-8",
            status_code=200,
            fetched_at=datetime.now(UTC),
            headers={"content-type": "text/html; charset=utf-8"},
            page_title="Example",
        )


def test_worker_processes_manual_snapshot_job(test_settings, session_factory, storage) -> None:
    with session_factory() as session:
        job = enqueue_manual_url_job(
            session=session,
            url="https://example.com",
            source_name="manual_url",
            requested_by="pytest",
        )
        job_id = job.id
        session.commit()

    def dispatch_job(session, job, settings, storage):
        service = ManualUrlSnapshotService(fetcher=DummyFetcher(), storage=storage)
        service.execute(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        return True

    handled = process_next_job(
        settings=test_settings,
        session_factory=session_factory,
        dispatch_job=dispatch_job,
        storage=storage,
    )

    assert handled is True

    with session_factory() as session:
        source_snapshot = session.query(SourceSnapshot).one()
        raw_asset = session.query(RawAsset).one()
        updated_job = session.get(type(job), job_id)

        assert source_snapshot.source_uri == "https://example.com"
        assert raw_asset.asset_type == "HTML"
        assert updated_job.status == JobStatus.SUCCEEDED

        saved_path = Path(test_settings.storage_local_root) / raw_asset.storage_path
        assert saved_path.exists()
        assert saved_path.read_bytes().startswith(b"<html>")


def test_source_snapshot_readback_endpoint(client, session_factory, storage) -> None:
    with session_factory() as session:
        job = enqueue_manual_url_job(
            session=session,
            url="https://example.com",
            source_name="manual_url",
            requested_by="pytest",
        )
        service = ManualUrlSnapshotService(fetcher=DummyFetcher(), storage=storage)
        service.execute(session=session, job=job)
        mark_job_succeeded(session=session, job=job)
        session.commit()

    response = client.get("/api/admin/source-snapshots")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["source_family"] == "manual_url"
    assert payload[0]["raw_assets"][0]["asset_type"] == "HTML"
