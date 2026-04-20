from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from landintel.connectors.base import ConnectorContext, FetchedAsset
from landintel.connectors.tabular_feed import GenericTabularFeedConnector
from landintel.domain.enums import (
    ConnectorType,
    JobStatus,
    JobType,
    ListingStatus,
    ListingType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
    SourceParseStatus,
)
from landintel.domain.models import JobRun
from landintel.domain.schemas import (
    ScenarioReasonRead,
    SiteScenarioSuggestResponse,
    SiteScenarioSummaryRead,
)

from services.worker.app.jobs.connectors import dispatch_connector_job
from services.worker.app.jobs.scenarios import run_site_scenario_suggest_refresh_job
from services.worker.app.jobs.site_build import run_site_build_job


def _csv_bytes(rows: list[dict[str, object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _tabular_feed_context(refresh_policy_json: dict[str, object]) -> ConnectorContext:
    return ConnectorContext(
        source_name="cabinet_office_surplus_feed",
        connector_type=ConnectorType.TABULAR_FEED,
        refresh_policy_json=refresh_policy_json,
        requested_by="pytest",
    )


def test_tabular_feed_connector_transforms_rows_and_limits_output(
    monkeypatch: pytest.MonkeyPatch,
    test_settings,
) -> None:
    now = datetime.now(UTC)
    feed_url = "https://example.test/tabular-feed.csv"
    final_url = "https://cdn.example.test/tabular-feed.csv?download=1"
    rows = [
        {
            "In Site Disposal Reference": "A1",
            "Status of Sale": "On the Market",
            "Local Authority": "London Borough of Camden",
            "Region": "Greater London",
            "Latitude": "51.501",
            "Longitude": "-0.124",
            "Property Name": "Camden Yard",
            "Contract Name": "Surplus land disposal",
            "Land Usage": "Surplus land",
            "Total Surplus Land Area": "12.4",
            "Total Surplus Floor Area": "0",
            "Property Number": "1",
            "Street Name": "Example Road",
            "Town": "London",
            "Postcode": "NW1 1AA",
        },
        {
            "In Site Disposal Reference": "A1",
            "Status of Sale": "On the Market",
            "Local Authority": "London Borough of Camden",
            "Region": "Greater London",
            "Latitude": "51.501",
            "Longitude": "-0.124",
            "Property Name": "Camden Yard duplicate",
            "Contract Name": "Surplus land disposal",
            "Land Usage": "Surplus land",
            "Total Surplus Land Area": "12.4",
            "Total Surplus Floor Area": "0",
            "Property Number": "1",
            "Street Name": "Example Road",
            "Town": "London",
            "Postcode": "NW1 1AA",
        },
        {
            "In Site Disposal Reference": "B2",
            "Status of Sale": "Under Offer",
            "Local Authority": "Royal Borough of Greenwich",
            "Region": "Greater London",
            "Latitude": "51.483",
            "Longitude": "0.000",
            "Property Name": "Greenwich Depot",
            "Contract Name": "Re-development opportunity",
            "Land Usage": "Depot",
            "Total Surplus Land Area": "0",
            "Total Surplus Floor Area": "18",
            "Property Number": "8",
            "Street Name": "Second Avenue",
            "Town": "London",
            "Postcode": "SE10 8XX",
        },
        {
            "In Site Disposal Reference": "C3",
            "Status of Sale": "Sold",
            "Local Authority": "City of Westminster",
            "Region": "Greater London",
            "Latitude": "51.500",
            "Longitude": "-0.130",
            "Property Name": "Filtered Sale",
            "Contract Name": "Should not appear",
            "Land Usage": "Land",
            "Total Surplus Land Area": "4",
            "Total Surplus Floor Area": "0",
            "Property Number": "10",
            "Street Name": "Filter Street",
            "Town": "London",
            "Postcode": "SW1A 1AA",
        },
        {
            "In Site Disposal Reference": "D4",
            "Status of Sale": "On the Market",
            "Local Authority": "London Borough of Lambeth",
            "Region": "Greater London",
            "Latitude": "",
            "Longitude": "",
            "Property Name": "Missing Co-ordinates",
            "Contract Name": "Should not appear",
            "Land Usage": "Land",
            "Total Surplus Land Area": "3",
            "Total Surplus Floor Area": "0",
            "Property Number": "99",
            "Street Name": "Missing Way",
            "Town": "London",
            "Postcode": "SE1 0AA",
        },
    ]
    payload = _csv_bytes(rows)

    monkeypatch.setattr(
        "landintel.connectors.tabular_feed.fetch_http_asset",
        lambda url, timeout_seconds: FetchedAsset(
            requested_url=url,
            final_url=final_url,
            content=payload,
            content_type="text/csv",
            status_code=200,
            fetched_at=now,
            headers={"content-type": "text/csv"},
            page_title=None,
        ),
    )

    connector = GenericTabularFeedConnector(test_settings)
    output = connector.run(
        context=_tabular_feed_context(
            {
                "feed_url": feed_url,
                "row_transform": "cabinet_office_surplus_property_v1",
                "feed_format": "csv",
                "max_listings": 2,
            }
        ),
        payload={},
    )

    assert output.source_uri == final_url
    assert output.source_family == "tabular_feed"
    assert output.parse_status is SourceParseStatus.PARSED
    assert output.coverage_note.startswith("Automated tabular feed captured")
    assert output.assets[0].asset_key == "tabular_feed_raw"
    assert output.assets[0].asset_type == "CSV"
    assert output.assets[0].role == "TABULAR_FEED"
    assert output.assets[0].metadata["row_count"] == 5
    assert output.assets[0].metadata["listing_count"] == 2
    assert output.manifest_json["feed_url"] == final_url
    assert output.manifest_json["listing_count"] == 2
    assert [listing.source_listing_id for listing in output.listings] == ["A1", "B2"]
    assert output.listings[0].listing_type is ListingType.LAND
    assert output.listings[0].status is ListingStatus.LIVE
    assert output.listings[0].canonical_url == f"{final_url}&disposal_id=A1"
    assert output.listings[1].listing_type is ListingType.REDEVELOPMENT_SITE
    assert output.listings[1].status is ListingStatus.UNDER_OFFER
    assert output.listings[1].canonical_url == f"{final_url}&disposal_id=B2"


@pytest.mark.parametrize(
    ("refresh_policy_json", "message"),
    [
        ({}, "feed_url"),
        (
            {"feed_url": "https://example.test/feed.csv", "row_transform": "unsupported"},
            "supported refresh_policy_json.row_transform",
        ),
    ],
)
def test_tabular_feed_connector_validates_configuration(
    test_settings,
    refresh_policy_json: dict[str, object],
    message: str,
) -> None:
    connector = GenericTabularFeedConnector(test_settings)

    with pytest.raises(ValueError, match=message):
        connector.run(
            context=_tabular_feed_context(refresh_policy_json),
            payload={},
        )


def test_connector_to_assessment_chain_promotes_cluster_site_and_assessment(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
    storage,
    test_settings,
) -> None:
    cluster_id = uuid.uuid4()
    site_id = uuid.uuid4()
    scenario_id = uuid.uuid4()
    connector_job = JobRun(
        id=uuid.uuid4(),
        job_type=JobType.LISTING_CLUSTER_REBUILD,
        status=JobStatus.QUEUED,
        payload_json={},
        requested_by="pytest",
    )
    db_session.add(connector_job)
    db_session.commit()

    rebuild_calls: list[object] = []
    build_calls: list[dict[str, object]] = []
    assessment_calls: dict[str, object] = {}

    monkeypatch.setattr(
        "services.worker.app.jobs.connectors.rebuild_listing_clusters",
        lambda session: rebuild_calls.append(session) or [],
    )
    monkeypatch.setattr(
        "services.worker.app.jobs.connectors.list_auto_site_build_cluster_ids",
        lambda session: [cluster_id],
    )

    handled = dispatch_connector_job(db_session, connector_job, test_settings, storage)
    assert handled is True
    assert rebuild_calls == [db_session]

    site_build_job = (
        db_session.query(JobRun)
        .filter(JobRun.job_type == JobType.SITE_BUILD_REFRESH)
        .one()
    )
    assert site_build_job.payload_json["cluster_id"] == str(cluster_id)

    monkeypatch.setattr(
        "services.worker.app.jobs.site_build.build_or_refresh_site_from_cluster",
        lambda **kwargs: build_calls.append(kwargs) or SimpleNamespace(id=site_id),
    )
    run_site_build_job(session=db_session, job=site_build_job)

    scenario_job = (
        db_session.query(JobRun)
        .filter(JobRun.job_type == JobType.SITE_SCENARIO_SUGGEST_REFRESH)
        .one()
    )
    assert scenario_job.payload_json["site_id"] == str(site_id)

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
    monkeypatch.setattr(
        "services.worker.app.jobs.scenarios.create_or_refresh_assessment_run",
        lambda **kwargs: assessment_calls.update(kwargs) or SimpleNamespace(id=uuid.uuid4()),
    )

    run_site_scenario_suggest_refresh_job(session=db_session, job=scenario_job, storage=storage)

    assert build_calls == [
        {
            "session": db_session,
            "cluster_id": cluster_id,
            "requested_by": "pytest",
        }
    ]
    assert assessment_calls["session"] == db_session
    assert assessment_calls["site_id"] == site_id
    assert assessment_calls["scenario_id"] == scenario_id
    assert assessment_calls["requested_by"] == "pytest"
    assert assessment_calls["storage"] is storage
    assert assessment_calls["as_of_date"] == date.today()


def test_setup_and_smoke_scripts_cover_phase8a_launch_flow() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    setup_script = (repo_root / "scripts" / "setup_local.sh").read_text()
    smoke_script = (repo_root / "scripts" / "smoke_prod.sh").read_text()

    assert "python -m landintel.geospatial.bootstrap" in setup_script
    assert "python -m landintel.planning.bootstrap" in setup_script
    assert "python -m landintel.valuation.bootstrap" in setup_script
    assert "build_hidden_model_releases" in setup_script
    assert "--requested-by local-setup" in setup_script
    assert "cabinet_office_surplus_property" in setup_script
    assert "/api/opportunities/" in setup_script

    assert '/api/health/data' in smoke_script
    assert '/api/health/model' in smoke_script
    assert '/api/listings/sources' in smoke_script
    assert '/api/listing-clusters' in smoke_script
    assert '/api/sites' in smoke_script
    assert '/api/opportunities' in smoke_script
    assert '/api/admin/jobs' in smoke_script
    assert 'cabinet_office_surplus_property' in smoke_script
    assert 'LISTING_SOURCE_RUN' in smoke_script
