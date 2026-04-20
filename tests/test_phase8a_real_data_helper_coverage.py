from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from landintel.connectors import tabular_feed
from landintel.domain.enums import OpportunityBand, ScenarioStatus
from landintel.services import opportunities_readback
from openpyxl import Workbook


def _workbook_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    for row in rows:
        worksheet.append(row)
    payload = BytesIO()
    workbook.save(payload)
    return payload.getvalue()


def test_tabular_feed_helper_branches_cover_formats_and_type_inference() -> None:
    xlsx_payload = _workbook_bytes(
        [
            [" Name ", " Count "],
            ["Example", 3],
            ["", ""],
        ]
    )
    assert tabular_feed._load_rows(
        xlsx_payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        refresh_policy={"sheet_name": ""},
    ) == [{"Name": "Example", "Count": 3}]
    assert tabular_feed._load_rows(
        b'[{"a": 1}, {"b": 2}]',
        content_type="application/json",
        refresh_policy={},
    ) == [{"a": 1}, {"b": 2}]
    assert tabular_feed._load_rows(
        b'{"results":[{"a": 1}], "ignored": true}',
        content_type="application/json",
        refresh_policy={"feed_format": "json"},
    ) == [{"a": 1}]
    assert tabular_feed._load_xlsx_rows(_workbook_bytes([]), sheet_name="") == []

    with pytest.raises(ValueError, match="Unsupported tabular feed format"):
        tabular_feed._load_rows(
            b"example",
            content_type="application/octet-stream",
            refresh_policy={"feed_format": "yaml"},
        )

    with pytest.raises(ValueError, match="top-level row list"):
        tabular_feed._load_json_rows(b'{"results":"bad"}')
    with pytest.raises(ValueError, match="top-level row list"):
        tabular_feed._load_json_rows(b"42")

    assert tabular_feed._infer_feed_format("application/zip") == "xlsx"
    assert tabular_feed._infer_feed_format("text/plain") == "csv"
    assert tabular_feed._infer_feed_format("application/json") == "json"
    assert tabular_feed._infer_feed_format("application/octet-stream") == "xlsx"

    assert (
        tabular_feed._tabular_asset_type(
            "application/vnd.ms-excel",
            "https://x.test/feed.xls",
        )
        == "XLS"
    )
    assert tabular_feed._tabular_asset_type("application/json", "https://x.test/feed") == "JSON"
    assert tabular_feed._string_value(12) == "12"
    assert tabular_feed._float_value("bad-number") is None
    assert tabular_feed._json_safe_value(datetime(2026, 4, 20, 12, 0, tzinfo=UTC)).endswith(
        "+00:00"
    )


def test_tabular_feed_transform_branches_cover_listing_type_fallbacks() -> None:
    assert (
        tabular_feed._cabinet_office_listing_status("Under Offer")
        == tabular_feed.ListingStatus.UNDER_OFFER
    )
    assert (
        tabular_feed._cabinet_office_listing_type(
            {
                "Total Surplus Land Area": 0,
                "Total Surplus Floor Area": 0,
                "Land Usage": "Surplus Land",
                "Property Name": "Fallback",
                "Contract Name": "Lease",
            }
        )
        == tabular_feed.ListingType.LAND
    )
    assert (
        tabular_feed._cabinet_office_listing_type(
            {
                "Total Surplus Land Area": 0,
                "Total Surplus Floor Area": 10,
                "Land Usage": "Office",
                "Property Name": "Existing building",
                "Contract Name": "Dispose",
            }
        )
        == tabular_feed.ListingType.LAND_WITH_BUILDING
    )
    assert (
        tabular_feed._is_london_row(
            {"Local Authority": "County Council", "Region": "South East", "Town": "London"},
            authority_patterns=["LONDON BOROUGH"],
        )
        is False
    )
    assert tabular_feed._is_london_row(
        {"Local Authority": "County Council", "Region": "South East", "Town": "London"},
        authority_patterns=[],
    )
    assert tabular_feed._is_london_row(
        {
            "Local Authority": "Royal Borough of Kingston upon Thames",
            "Region": "South East",
            "Town": "Kingston",
        },
        authority_patterns=[],
    )
    assert (
        tabular_feed._cabinet_office_row_allowed(
            row={"Land Usage": "Surplus Land"},
            listing_type=tabular_feed.ListingType.LAND,
            refresh_policy={
                "allowed_land_usage_contains_any": ["Surplus Land", "Development land"],
                "allowed_listing_types": ["LAND"],
            },
        )
        is True
    )
    assert (
        tabular_feed._cabinet_office_row_allowed(
            row={"Land Usage": "Operational"},
            listing_type=tabular_feed.ListingType.LAND_WITH_BUILDING,
            refresh_policy={
                "allowed_land_usage_contains_any": ["Surplus Land", "Development land"],
                "allowed_listing_types": ["LAND"],
            },
        )
        is False
    )
    assert (
        tabular_feed._cabinet_office_row_allowed(
            row={"Land Usage": "Surplus Land"},
            listing_type=tabular_feed.ListingType.LAND_WITH_BUILDING,
            refresh_policy={"allowed_listing_types": ["", "NOT_A_TYPE", "LAND"]},
        )
        is False
    )
    assert (
        tabular_feed._cabinet_office_row_allowed(
            row={"Land Usage": "Surplus Land"},
            listing_type=tabular_feed.ListingType.LAND,
            refresh_policy={"allowed_listing_types": ["", "NOT_A_TYPE"]},
        )
        is True
    )
    assert (
        tabular_feed._cabinet_office_row_allowed(
            row={"Land Usage": "Operational", "Total Surplus Land Area": "0"},
            listing_type=tabular_feed.ListingType.LAND,
            refresh_policy={"require_positive_land_area": True},
        )
        is False
    )
    assert (
        tabular_feed._cabinet_office_row_allowed(
            row={
                "Land Usage": "Surplus Land",
                "Total Surplus Land Area": "10",
                "Total Surplus Floor Area": "1",
            },
            listing_type=tabular_feed.ListingType.LAND,
            refresh_policy={"max_surplus_floor_area_sqm": 0},
        )
        is False
    )
    with pytest.raises(ValueError, match="Unsupported row transform"):
        tabular_feed._transform_rows(
            rows=[],
            refresh_policy={},
            row_transform="unknown",
            feed_url="https://example.test/feed.csv",
            observed_at=datetime.now(UTC),
        )


def test_tabular_feed_transform_skips_rows_that_fail_live_source_fit_filters() -> None:
    rows = [
        {
            "In Site Disposal Reference": "A1",
            "Status of Sale": "On the Market",
            "Local Authority": "London Borough of Camden",
            "Region": "Greater London",
            "Latitude": "51.501",
            "Longitude": "-0.124",
            "Property Name": "Operational building",
            "Contract Name": "Exclude me",
            "Land Usage": "Operational",
            "Total Surplus Land Area": "0",
            "Total Surplus Floor Area": "120",
            "Property Number": "1",
            "Street Name": "Example Road",
            "Town": "London",
            "Postcode": "NW1 1AA",
        }
    ]

    assert (
        tabular_feed._transform_rows(
            rows=rows,
            refresh_policy={
                "status_of_sale_values": ["On the Market"],
                "local_authority_contains_any": ["LONDON BOROUGH"],
                "allowed_land_usage_contains_any": ["Surplus Land", "Development land"],
                "allowed_listing_types": ["LAND"],
                "max_surplus_floor_area_sqm": 0,
                "require_positive_land_area": True,
            },
            row_transform="cabinet_office_surplus_property_v1",
            feed_url="https://example.test/feed.csv",
            observed_at=datetime.now(UTC),
        )
        == []
    )


def test_unassessed_opportunity_hold_reason_branches() -> None:
    site_summary = SimpleNamespace(
        warnings=[],
        manual_review_required=False,
    )
    analyst_required = SimpleNamespace(
        status=ScenarioStatus.ANALYST_REQUIRED,
        missing_data_flags=[],
        manual_review_required=True,
    )
    assert (
        opportunities_readback._unassessed_hold_reason(
            site_summary=site_summary,
            scenario_summary=analyst_required,
        )
        == "Analyst confirmation required before assessment can run."
    )

    draft_summary = SimpleNamespace(
        status=ScenarioStatus.REJECTED,
        missing_data_flags=[],
        manual_review_required=False,
    )
    assert opportunities_readback._unassessed_hold_reason(
        site_summary=site_summary,
        scenario_summary=draft_summary,
    ) == "Scenario is not yet assessable: REJECTED."

    warning_site_summary = SimpleNamespace(
        warnings=[
            SimpleNamespace(code="TITLE_LINK_INDICATIVE", message="ignore"),
            SimpleNamespace(code="BOROUGH_REGISTER_GAP", message="Coverage warning"),
        ],
        manual_review_required=False,
    )
    assert (
        opportunities_readback._unassessed_hold_reason(
            site_summary=warning_site_summary,
            scenario_summary=None,
        )
        == "Coverage warning"
    )

    manual_review_site_summary = SimpleNamespace(
        warnings=[],
        manual_review_required=True,
    )
    assert (
        opportunities_readback._unassessed_hold_reason(
            site_summary=manual_review_site_summary,
            scenario_summary=None,
        )
        == "Manual review is required before assessment can run."
    )

    empty_summary = SimpleNamespace(warnings=[], manual_review_required=False)
    assert (
        opportunities_readback._unassessed_hold_reason(
            site_summary=empty_summary,
            scenario_summary=None,
        )
        == "No ready assessment is available yet."
    )


def test_ranking_output_blocked_allows_hash_captured_replay_only() -> None:
    blocked_visibility = SimpleNamespace(
        blocked=True,
        blocked_reason_codes=["REPLAY_FAILED"],
    )
    replay_captured_run = SimpleNamespace(
        prediction_ledger=SimpleNamespace(replay_verification_status="HASH_CAPTURED")
    )
    assert (
        opportunities_readback._ranking_output_blocked(
            run=replay_captured_run,
            visibility=blocked_visibility,
        )
        is False
    )

    assert (
        opportunities_readback._ranking_output_blocked(
            run=SimpleNamespace(prediction_ledger=None),
            visibility=blocked_visibility,
        )
        is True
    )
    assert (
        opportunities_readback._ranking_output_blocked(
            run=replay_captured_run,
            visibility=SimpleNamespace(blocked=False, blocked_reason_codes=[]),
        )
        is False
    )

    hold_summary = SimpleNamespace(
        probability_band=OpportunityBand.HOLD,
        hold_reason="Need review",
        expected_uplift_mid=None,
        valuation_quality=None,
        asking_price_gbp=None,
        auction_date=None,
        same_borough_support_count=0,
    )
    factors = opportunities_readback._ranking_factors(
        run=SimpleNamespace(id=uuid4(), result=SimpleNamespace(estimate_status=None)),
        summary=hold_summary,
    )
    assert factors["probability_band"] == "Hold"
    assert factors["hold_reason"] == "Need review"
