from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.models import (
    BoroughBaselinePack,
    ScenarioTemplate,
    SiteCandidate,
    SiteConstraintFact,
    SitePlanningLink,
    SitePolicyFact,
    SiteScenario,
)
from landintel.domain.schemas import (
    ScenarioReasonRead,
    ScenarioReviewRead,
    SiteScenarioDetailRead,
    SiteScenarioListResponse,
    SiteScenarioSummaryRead,
)
from landintel.evidence.assemble import assemble_scenario_evidence, assemble_site_evidence
from landintel.planning.enrich import get_borough_baseline_pack
from landintel.planning.extant_permission import evaluate_site_extant_permission


def list_site_scenarios(*, session: Session, site_id: UUID) -> SiteScenarioListResponse:
    rows = session.execute(
        select(SiteScenario)
        .where(SiteScenario.site_id == site_id)
        .options(
            selectinload(SiteScenario.reviews),
            selectinload(SiteScenario.geometry_revision),
            selectinload(SiteScenario.site),
        )
        .order_by(
            SiteScenario.is_headline.desc(),
            SiteScenario.is_current.desc(),
            SiteScenario.updated_at.desc(),
        )
    ).scalars().all()
    site = rows[0].site if rows else session.get(SiteCandidate, site_id)
    baseline_pack = (
        get_borough_baseline_pack(session=session, borough_id=site.borough_id) if site else None
    )
    return SiteScenarioListResponse(
        items=[
            serialize_site_scenario_summary(
                session=session,
                scenario=row,
                baseline_pack=baseline_pack,
                site=site,
            )
            for row in rows
        ],
        total=len(rows),
    )


def get_scenario_detail(*, session: Session, scenario_id: UUID) -> SiteScenarioDetailRead | None:
    row = session.execute(
        select(SiteScenario)
        .where(SiteScenario.id == scenario_id)
        .options(
            selectinload(SiteScenario.reviews),
            selectinload(SiteScenario.geometry_revision),
            selectinload(SiteScenario.site)
            .selectinload(SiteCandidate.planning_links)
            .selectinload(SitePlanningLink.planning_application),
            selectinload(SiteScenario.site).selectinload(SiteCandidate.policy_facts).selectinload(
                SitePolicyFact.policy_area
            ),
            selectinload(SiteScenario.site)
            .selectinload(SiteCandidate.constraint_facts)
            .selectinload(SiteConstraintFact.constraint_feature),
            selectinload(SiteScenario.site).selectinload(SiteCandidate.scenarios),
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    baseline_pack = get_borough_baseline_pack(session=session, borough_id=row.site.borough_id)
    return serialize_site_scenario_detail(
        session=session,
        scenario=row,
        baseline_pack=baseline_pack,
    )


def serialize_site_scenario_summary(
    *,
    session: Session,
    scenario: SiteScenario,
    baseline_pack: BoroughBaselinePack | None,
    site: SiteCandidate | None,
) -> SiteScenarioSummaryRead:
    del session
    del baseline_pack
    del site
    rationale = dict(scenario.rationale_json or {})
    return SiteScenarioSummaryRead(
        id=scenario.id,
        site_id=scenario.site_id,
        template_key=scenario.template_key,
        template_version=scenario.template_version,
        proposal_form=scenario.proposal_form,
        units_assumed=scenario.units_assumed,
        route_assumed=scenario.route_assumed,
        height_band_assumed=scenario.height_band_assumed,
        net_developable_area_pct=scenario.net_developable_area_pct,
        red_line_geom_hash=scenario.red_line_geom_hash,
        scenario_source=scenario.scenario_source,
        status=scenario.status,
        supersedes_id=scenario.supersedes_id,
        is_current=scenario.is_current,
        is_headline=scenario.is_headline,
        heuristic_rank=scenario.heuristic_rank,
        manual_review_required=scenario.manual_review_required,
        stale_reason=scenario.stale_reason,
        housing_mix_assumed_json=dict(scenario.housing_mix_assumed_json or {}),
        parking_assumption=scenario.parking_assumption,
        affordable_housing_assumption=scenario.affordable_housing_assumption,
        access_assumption=scenario.access_assumption,
        reason_codes=[
            ScenarioReasonRead.model_validate(item)
            for item in list(rationale.get("reason_codes") or [])
        ],
        missing_data_flags=list(rationale.get("missing_data_flags") or []),
        warning_codes=list(rationale.get("warning_codes") or []),
    )


def serialize_site_scenario_detail(
    *,
    session: Session,
    scenario: SiteScenario,
    baseline_pack: BoroughBaselinePack | None,
) -> SiteScenarioDetailRead:
    from landintel.services.sites_readback import _serialize_baseline_pack, serialize_site_summary

    site = scenario.site
    extant_permission = evaluate_site_extant_permission(session=session, site=site)
    site_evidence = assemble_site_evidence(
        session=session,
        site=site,
        extant_permission=extant_permission,
    )
    evidence = assemble_scenario_evidence(
        session=session,
        site=site,
        scenario=scenario,
        site_evidence=site_evidence,
        extant_permission=extant_permission,
        baseline_pack=baseline_pack,
    )

    template = session.execute(
        select(ScenarioTemplate)
        .where(
            ScenarioTemplate.key == scenario.template_key,
            ScenarioTemplate.version == scenario.template_version,
        )
        .limit(1)
    ).scalar_one_or_none()

    return SiteScenarioDetailRead(
        **serialize_site_scenario_summary(
            session=session,
            scenario=scenario,
            baseline_pack=baseline_pack,
            site=site,
        ).model_dump(),
        template=(
            None
            if template is None
            else {
                "id": template.id,
                "key": template.key,
                "version": template.version,
                "enabled": template.enabled,
                "config_json": template.config_json,
            }
        ),
        review_history=[
            ScenarioReviewRead(
                id=review.id,
                review_status=review.review_status,
                review_notes=review.review_notes,
                reviewed_by=review.reviewed_by,
                reviewed_at=review.reviewed_at,
            )
            for review in scenario.reviews
        ],
        evidence=evidence,
        baseline_pack=_serialize_baseline_pack(baseline_pack),
        site_summary=serialize_site_summary(site),
    )
