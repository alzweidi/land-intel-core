from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from landintel.db.base import Base
from landintel.db.session import create_sqlalchemy_engine
from landintel.domain.enums import ComplianceMode, ConnectorType, JobStatus, JobType
from landintel.domain.models import JobRun, ListingSource
from sqlalchemy.orm import Session


def _load_migration_module(filename: str):
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "db" / "migrations" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase8a_launch_readiness_migration_backfills_defaults(tmp_path):
    bridge = _load_migration_module("20260416_000009a_alembic_version_width.py")
    migration = _load_migration_module("20260419_000011_phase8a_launch_readiness.py")
    previous_head = _load_migration_module("20260417_000010_phase8a_lineage_integrity.py")
    assert bridge.down_revision == "20260415_000009"
    assert len(bridge.revision) <= 32
    assert previous_head.revision == "20260417_000010_phase8a_lineage_integrity"
    assert previous_head.down_revision == bridge.revision
    assert migration.revision == "20260419_000011_phase8a_launch_readiness"
    assert migration.down_revision == previous_head.revision

    database_url = f"sqlite:///{tmp_path / 'launch-readiness.db'}"
    engine = create_sqlalchemy_engine(database_url)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            source = ListingSource(
                name="example_public_page",
                connector_type=ConnectorType.PUBLIC_PAGE,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                refresh_policy_json={"seed_urls": ["https://example.com"], "max_listings": 1},
                active=True,
            )
            queued_job = JobRun(
                job_type=JobType.LISTING_SOURCE_RUN,
                payload_json={"source_name": "example_public_page"},
                status=JobStatus.QUEUED,
                run_at=datetime.now(UTC),
                next_run_at=datetime.now(UTC),
                requested_by="pytest",
            )
            running_job = JobRun(
                job_type=JobType.LISTING_SOURCE_RUN,
                payload_json={"source_name": "example_public_page", "dedupe_key": "source:wrong"},
                status=JobStatus.RUNNING,
                run_at=datetime.now(UTC),
                next_run_at=datetime.now(UTC),
                requested_by="pytest",
            )
            succeeded_job = JobRun(
                job_type=JobType.LISTING_SOURCE_RUN,
                payload_json={"source_name": "example_public_page"},
                status=JobStatus.SUCCEEDED,
                run_at=datetime.now(UTC),
                next_run_at=datetime.now(UTC),
                requested_by="pytest",
            )
            session.add_all([source, queued_job, running_job, succeeded_job])
            session.commit()
            queued_job_id = queued_job.id
            running_job_id = running_job.id
            succeeded_job_id = succeeded_job.id

        with engine.begin() as connection:
            migration._backfill_example_public_page_interval(connection)
            migration._backfill_listing_source_run_dedupe_keys(connection)

        with Session(engine) as session:
            source = session.query(ListingSource).filter_by(name="example_public_page").one()
            assert source.refresh_policy_json["interval_hours"] == 24

            queued_job = session.get(JobRun, queued_job_id)
            assert queued_job is not None
            assert queued_job.payload_json["dedupe_key"] == "source:example_public_page"

            running_job = session.get(JobRun, running_job_id)
            assert running_job is not None
            assert running_job.payload_json["dedupe_key"] == "source:example_public_page"

            succeeded_job = session.get(JobRun, succeeded_job_id)
            assert succeeded_job is not None
            assert "dedupe_key" not in succeeded_job.payload_json
    finally:
        engine.dispose()
