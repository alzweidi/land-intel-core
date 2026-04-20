from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

from landintel.domain.enums import (
    JobStatus,
    JobType,
    ListingStatus,
    ListingType,
    PriceBasisType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
)
from landintel.domain.models import (
    JobRun,
    ListingCluster,
    ListingClusterMember,
    ListingItem,
    ListingSnapshot,
)
from landintel.domain.schemas import (
    ScenarioReasonRead,
    SiteScenarioSuggestResponse,
    SiteScenarioSummaryRead,
)
from landintel.listings import service as listings_service

from services.worker.app.jobs.connectors import dispatch_connector_job
from services.worker.app.jobs.scenarios import run_site_scenario_suggest_refresh_job
from services.worker.app.jobs.site_build import run_site_build_job


def test_list_auto_site_build_cluster_ids_only_returns_live_land_clusters(
    db_session,
    seed_listing_sources,
):
    source = seed_listing_sources["example_public_page"]
    now = datetime.now(UTC)

    eligible_listing = ListingItem(
        source_id=source.id,
        source_listing_id="eligible",
        canonical_url="https://example.test/eligible",
        listing_type=ListingType.LAND,
        first_seen_at=now,
        last_seen_at=now,
    )
    ineligible_listing = ListingItem(
        source_id=source.id,
        source_listing_id="ineligible",
        canonical_url="https://example.test/ineligible",
        listing_type=ListingType.UNKNOWN,
        first_seen_at=now,
        last_seen_at=now,
    )
    db_session.add_all([eligible_listing, ineligible_listing])
    db_session.flush()

    eligible_snapshot = ListingSnapshot(
        listing_item_id=eligible_listing.id,
        source_snapshot_id=uuid.uuid4(),
        observed_at=now,
        headline="Eligible land listing",
        description_text="Land",
        guide_price_gbp=1_000_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        address_text="1 Land Road, London",
        normalized_address="1 land road london",
        lat=51.5,
        lon=-0.1,
        raw_record_json={},
        search_text="eligible",
    )
    ineligible_snapshot = ListingSnapshot(
        listing_item_id=ineligible_listing.id,
        source_snapshot_id=uuid.uuid4(),
        observed_at=now,
        headline="Withdrawn unknown listing",
        description_text="Withdrawn",
        guide_price_gbp=950_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.WITHDRAWN,
        address_text="2 Example Road, London",
        normalized_address="2 example road london",
        lat=51.51,
        lon=-0.11,
        raw_record_json={},
        search_text="ineligible",
    )
    db_session.add_all([eligible_snapshot, ineligible_snapshot])
    db_session.flush()
    eligible_listing.current_snapshot_id = eligible_snapshot.id
    ineligible_listing.current_snapshot_id = ineligible_snapshot.id

    eligible_cluster = ListingCluster(
        id=uuid.uuid4(),
        cluster_key="eligible-cluster",
        cluster_status="ACTIVE",
    )
    ineligible_cluster = ListingCluster(
        id=uuid.uuid4(),
        cluster_key="ineligible-cluster",
        cluster_status="ACTIVE",
    )
    db_session.add_all([eligible_cluster, ineligible_cluster])
    db_session.flush()
    db_session.add_all(
        [
            ListingClusterMember(
                id=uuid.uuid4(),
                listing_cluster_id=eligible_cluster.id,
                listing_item_id=eligible_listing.id,
                confidence=1.0,
                rules_json={"reasons": ["test"]},
            ),
            ListingClusterMember(
                id=uuid.uuid4(),
                listing_cluster_id=ineligible_cluster.id,
                listing_item_id=ineligible_listing.id,
                confidence=1.0,
                rules_json={"reasons": ["test"]},
            ),
        ]
    )
    db_session.commit()

    cluster_ids = listings_service.list_auto_site_build_cluster_ids(db_session)

    assert cluster_ids == [eligible_cluster.id]


def test_dispatch_cluster_rebuild_enqueues_site_build_jobs(
    monkeypatch,
    db_session,
    test_settings,
    storage,
):
    cluster_id = uuid.uuid4()
    job = JobRun(
        id=uuid.uuid4(),
        job_type=JobType.LISTING_CLUSTER_REBUILD,
        status=JobStatus.QUEUED,
        payload_json={},
        requested_by="pytest",
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr(
        "services.worker.app.jobs.connectors.rebuild_listing_clusters",
        lambda session: [],
    )
    monkeypatch.setattr(
        "services.worker.app.jobs.connectors.list_auto_site_build_cluster_ids",
        lambda session: [cluster_id],
    )

    handled = dispatch_connector_job(db_session, job, test_settings, storage)

    queued = db_session.query(JobRun).filter(JobRun.job_type == JobType.SITE_BUILD_REFRESH).all()
    assert handled is True
    assert len(queued) == 1
    assert queued[0].payload_json["cluster_id"] == str(cluster_id)


def test_run_site_build_job_enqueues_scenario_suggest(monkeypatch, db_session):
    site_id = uuid.uuid4()
    monkeypatch.setattr(
        "services.worker.app.jobs.site_build.build_or_refresh_site_from_cluster",
        lambda **kwargs: SimpleNamespace(id=site_id),
    )
    job = SimpleNamespace(payload_json={"cluster_id": str(uuid.uuid4())}, requested_by="pytest")

    run_site_build_job(session=db_session, job=job)

    queued = (
        db_session.query(JobRun)
        .filter(JobRun.job_type == JobType.SITE_SCENARIO_SUGGEST_REFRESH)
        .all()
    )
    assert len(queued) == 1
    assert queued[0].payload_json["site_id"] == str(site_id)


def test_run_site_scenario_suggest_refresh_job_builds_assessment_for_auto_confirmed(
    monkeypatch,
    db_session,
):
    scenario_id = uuid.uuid4()
    site_id = uuid.uuid4()
    called: dict[str, object] = {}

    monkeypatch.setattr(
        "services.worker.app.jobs.scenarios.suggest_scenarios_for_site",
        lambda **kwargs: SiteScenarioSuggestResponse(
            site_id=site_id,
            headline_scenario_id=scenario_id,
            items=[
                SiteScenarioSummaryRead(
                    id=scenario_id,
                    site_id=site_id,
                    template_key="resi-small-infill",
                    template_version="v1",
                    proposal_form=ProposalForm.INFILL,
                    units_assumed=6,
                    route_assumed="FULL",
                    height_band_assumed="LOW",
                    net_developable_area_pct=0.7,
                    red_line_geom_hash="geom-hash",
                    scenario_source=ScenarioSource.AUTO,
                    status=ScenarioStatus.AUTO_CONFIRMED,
                    supersedes_id=None,
                    is_current=True,
                    is_headline=True,
                    heuristic_rank=1,
                    manual_review_required=False,
                    stale_reason=None,
                    reason_codes=[ScenarioReasonRead(code="AUTO", message="Auto confirmed")],
                    missing_data_flags=[],
                    warning_codes=[],
                )
            ],
            excluded_templates=[],
        ),
    )

    def _build(**kwargs):
        called.update(kwargs)
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(
        "services.worker.app.jobs.scenarios.create_or_refresh_assessment_run",
        _build,
    )
    job = SimpleNamespace(payload_json={"site_id": str(site_id)}, requested_by="pytest")

    run_site_scenario_suggest_refresh_job(session=db_session, job=job, storage=object())

    assert called["site_id"] == site_id
    assert called["scenario_id"] == scenario_id
    assert called["as_of_date"] == date.today()


def test_run_site_scenario_suggest_refresh_job_skips_non_auto_confirmed(monkeypatch, db_session):
    scenario_id = uuid.uuid4()
    site_id = uuid.uuid4()
    called = False

    monkeypatch.setattr(
        "services.worker.app.jobs.scenarios.suggest_scenarios_for_site",
        lambda **kwargs: SiteScenarioSuggestResponse(
            site_id=site_id,
            headline_scenario_id=scenario_id,
            items=[
                SiteScenarioSummaryRead(
                    id=scenario_id,
                    site_id=site_id,
                    template_key="resi-small-infill",
                    template_version="v1",
                    proposal_form=ProposalForm.INFILL,
                    units_assumed=6,
                    route_assumed="FULL",
                    height_band_assumed="LOW",
                    net_developable_area_pct=0.7,
                    red_line_geom_hash="geom-hash",
                    scenario_source=ScenarioSource.AUTO,
                    status=ScenarioStatus.ANALYST_REQUIRED,
                    supersedes_id=None,
                    is_current=True,
                    is_headline=True,
                    heuristic_rank=1,
                    manual_review_required=True,
                    stale_reason=None,
                    reason_codes=[],
                    missing_data_flags=["NO_BASELINE_PACK"],
                    warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
                )
            ],
            excluded_templates=[],
        ),
    )

    def _build(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("assessment build should not run")

    monkeypatch.setattr(
        "services.worker.app.jobs.scenarios.create_or_refresh_assessment_run",
        _build,
    )
    job = SimpleNamespace(payload_json={"site_id": str(site_id)}, requested_by="pytest")

    run_site_scenario_suggest_refresh_job(session=db_session, job=job, storage=object())

    assert called is False
