from uuid import UUID

from landintel.domain.enums import JobStatus, JobType
from landintel.domain.models import JobRun


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
