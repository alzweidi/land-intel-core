from datetime import timedelta
from uuid import UUID

import pytest
from landintel.connectors.base import ConnectorAsset, ConnectorRunOutput, ParsedListing
from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    JobStatus,
    JobType,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SourceParseStatus,
)
from landintel.domain.models import JobRun, ListingSource, RawAsset, SourceSnapshot
from landintel.jobs.service import (
    STALE_RUNNING_JOB_LOCK_SECONDS,
    claim_next_job,
    mark_job_succeeded,
    refresh_job_lock,
    utc_now,
)
from landintel.listings.service import persist_connector_output

from services.worker.app import main as worker_main
from services.worker.app.main import process_next_job


def test_health_endpoints(client) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    ready_response = client.get("/readyz")
    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ready"}


def test_manual_url_intake_queues_job(client, db_session) -> None:
    response = client.post(
        "/api/listings/intake/url",
        json={"url": "https://example.com", "source_name": "manual_url"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == JobStatus.QUEUED.value
    assert payload["job_type"] == JobType.MANUAL_URL_SNAPSHOT.value

    job = db_session.get(JobRun, UUID(payload["job_id"]))
    assert job is not None
    assert job.payload_json["url"] == "https://example.com/"
    assert job.status == JobStatus.QUEUED


def test_csv_import_queues_job(client, db_session) -> None:
    response = client.post(
        "/api/listings/import/csv",
        files={"file": ("listings.csv", b"headline,address\nSite,1 Test Road", "text/csv")},
        data={"source_name": "csv_import", "requested_by": "pytest"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_type"] == JobType.CSV_IMPORT_SNAPSHOT.value

    job = db_session.get(JobRun, UUID(payload["job_id"]))
    assert job is not None
    assert job.payload_json["source_name"] == "csv_import"


def test_claim_next_job_reclaims_stale_running_jobs(db_session) -> None:
    job = JobRun(
        job_type=JobType.HISTORICAL_LABEL_REBUILD,
        payload_json={},
        status=JobStatus.RUNNING,
        attempts=0,
        run_at=utc_now(),
        next_run_at=utc_now() + timedelta(days=1),
        locked_at=utc_now() - timedelta(seconds=STALE_RUNNING_JOB_LOCK_SECONDS + 60),
        worker_id="stale-worker",
    )
    db_session.add(job)
    db_session.commit()

    claimed = claim_next_job(db_session, worker_id="worker-test-2")

    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING
    assert claimed.worker_id == "worker-test-2"
    assert claimed.attempts == 1


def test_refresh_job_lock_prevents_reclaim_of_a_healthy_running_job(db_session) -> None:
    job = JobRun(
        job_type=JobType.HISTORICAL_LABEL_REBUILD,
        payload_json={},
        status=JobStatus.RUNNING,
        attempts=1,
        run_at=utc_now(),
        next_run_at=utc_now() + timedelta(days=1),
        locked_at=utc_now() - timedelta(seconds=STALE_RUNNING_JOB_LOCK_SECONDS + 60),
        worker_id="worker-test-1",
    )
    db_session.add(job)
    db_session.commit()

    assert refresh_job_lock(db_session, job_id=job.id, worker_id="worker-test-1") is True
    db_session.commit()

    claimed = claim_next_job(db_session, worker_id="worker-test-2")

    assert claimed is None


def test_process_next_job_commits_claim_before_cross_session_refresh(
    test_settings,
    session_factory,
    storage,
    monkeypatch,
) -> None:
    job = JobRun(
        job_type=JobType.HISTORICAL_LABEL_REBUILD,
        payload_json={},
        status=JobStatus.QUEUED,
        attempts=0,
        run_at=utc_now(),
        next_run_at=utc_now(),
        requested_by="pytest",
    )
    with session_factory() as seed_session:
        seed_session.add(job)
        seed_session.commit()
        job_id = job.id

    class _DummyEvent:
        def set(self) -> None:
            return None

    class _DummyThread:
        def join(self, timeout: float | None = None) -> None:
            del timeout
            return None

    monkeypatch.setattr(
        worker_main,
        "_start_job_heartbeat",
        lambda **_: (_DummyEvent(), _DummyThread()),
    )

    def _dispatch_job(*, session, job, settings, storage):
        del storage
        with session_factory() as heartbeat_session:
            assert refresh_job_lock(
                heartbeat_session,
                job_id=job.id,
                worker_id=settings.worker_id,
            ) is True
            heartbeat_session.commit()
        mark_job_succeeded(session=session, job=job)
        return True

    assert (
        process_next_job(
            settings=test_settings,
            session_factory=session_factory,
            dispatch_job=_dispatch_job,
            storage=storage,
        )
        is True
    )

    with session_factory() as check_session:
        persisted = check_session.get(JobRun, job_id)
        assert persisted is not None
        assert persisted.status == JobStatus.SUCCEEDED
        assert persisted.worker_id == test_settings.worker_id


def test_persist_connector_output_is_idempotent_and_storage_path_safe(db_session) -> None:
    class StrictMemoryStorage:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_bytes(self, storage_path: str, payload: bytes, *, content_type: str):
            del content_type
            if storage_path in self.objects:
                raise RuntimeError("duplicate write")
            self.objects[storage_path] = payload
            return object()

        def get_bytes(self, storage_path: str) -> bytes:
            if storage_path not in self.objects:
                raise FileNotFoundError(storage_path)
            return self.objects[storage_path]

    source = ListingSource(
        name="../../unsafe/source name",
        connector_type=ConnectorType.MANUAL_URL,
        compliance_mode=ComplianceMode.MANUAL_ONLY,
        refresh_policy_json={},
        active=True,
    )
    job = JobRun(
        job_type=JobType.MANUAL_URL_SNAPSHOT,
        payload_json={"url": "https://example.com/listing", "source_name": source.name},
        status=JobStatus.QUEUED,
        run_at=utc_now(),
        next_run_at=utc_now(),
        requested_by="pytest",
    )
    db_session.add_all([source, job])
    db_session.commit()

    storage = StrictMemoryStorage()
    asset = ConnectorAsset(
        asset_key="page",
        asset_type="HTML",
        role="listing_page",
        original_url="https://example.com/listing",
        content=b"<html>listing</html>",
        content_type="text/html",
        fetched_at=utc_now(),
        metadata={},
    )
    listing = ParsedListing(
        source_listing_id="listing-1",
        canonical_url="https://example.com/listing",
        observed_at=utc_now(),
        listing_type=ListingType.LAND,
        headline="Listing",
        description_text="Listing",
        guide_price_gbp=1_000_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        address_text="1 Example Road",
        normalized_address="1 example road",
        lat=51.5,
        lon=-0.1,
        raw_record_json={"source": "fixture"},
        search_text="listing",
    )
    output = ConnectorRunOutput(
        source_name=source.name,
        source_family="listing.manual",
        source_uri="https://example.com/listing",
        observed_at=utc_now(),
        coverage_note="fixture",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={"source_name": source.name},
        assets=[asset],
        listings=[listing],
    )

    first = persist_connector_output(
        session=db_session,
        job=job,
        source=source,
        output=output,
        storage=storage,
    )
    db_session.rollback()

    second = persist_connector_output(
        session=db_session,
        job=job,
        source=source,
        output=output,
        storage=storage,
    )
    db_session.commit()

    assert first.source_snapshot_id == second.source_snapshot_id
    assert len(storage.objects) == 1
    storage_path = next(iter(storage.objects))
    assert storage_path.startswith("raw/")
    assert storage_path.count("/") == 2
    assert ".." not in storage_path
    assert db_session.query(SourceSnapshot).count() == 1
    assert db_session.query(RawAsset).count() == 1


def test_persist_connector_output_propagates_storage_lookup_failures(db_session) -> None:
    class FailingLookupStorage:
        def __init__(self) -> None:
            self.put_called = False

        def put_bytes(self, storage_path: str, payload: bytes, *, content_type: str):
            del storage_path, payload, content_type
            self.put_called = True
            return object()

        def get_bytes(self, storage_path: str) -> bytes:
            del storage_path
            raise RuntimeError("temporary storage failure")

    source = ListingSource(
        name="manual_url",
        connector_type=ConnectorType.MANUAL_URL,
        compliance_mode=ComplianceMode.MANUAL_ONLY,
        refresh_policy_json={},
        active=True,
    )
    job = JobRun(
        job_type=JobType.MANUAL_URL_SNAPSHOT,
        payload_json={"url": "https://example.com/listing", "source_name": source.name},
        status=JobStatus.QUEUED,
        run_at=utc_now(),
        next_run_at=utc_now(),
        requested_by="pytest",
    )
    db_session.add_all([source, job])
    db_session.commit()

    storage = FailingLookupStorage()
    output = ConnectorRunOutput(
        source_name=source.name,
        source_family="listing.manual",
        source_uri="https://example.com/listing",
        observed_at=utc_now(),
        coverage_note="fixture",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={"source_name": source.name},
        assets=[
            ConnectorAsset(
                asset_key="page",
                asset_type="HTML",
                role="listing_page",
                original_url="https://example.com/listing",
                content=b"<html>listing</html>",
                content_type="text/html",
                fetched_at=utc_now(),
                metadata={},
            )
        ],
        listings=[],
    )

    with pytest.raises(RuntimeError, match="temporary storage failure"):
        persist_connector_output(
            session=db_session,
            job=job,
            source=source,
            output=output,
            storage=storage,
        )

    assert storage.put_called is False
