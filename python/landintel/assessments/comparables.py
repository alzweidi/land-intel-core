from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import exp

from landintel.domain.enums import ComparableOutcome, GoldSetReviewStatus, HistoricalLabelClass
from landintel.domain.models import (
    AssessmentRun,
    ComparableCaseMember,
    ComparableCaseSet,
    HistoricalCaseLabel,
    PlanningApplication,
    SiteCandidate,
    SiteScenario,
)
from landintel.features.build import FEATURE_VERSION
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

MAX_COMPARABLES_PER_OUTCOME = 3


@dataclass(slots=True)
class ComparableMatch:
    label: HistoricalCaseLabel
    planning_application: PlanningApplication
    outcome: ComparableOutcome
    similarity_score: float
    fallback_path: str
    match_json: dict[str, object]


@dataclass(slots=True)
class ComparableBuildResult:
    comparable_case_set: ComparableCaseSet
    approved_members: list[ComparableCaseMember]
    refused_members: list[ComparableCaseMember]
    source_snapshot_ids: list[str]
    raw_asset_ids: list[str]


def build_comparable_case_set(
    *,
    session: Session,
    assessment_run: AssessmentRun,
    site: SiteCandidate,
    scenario: SiteScenario,
    as_of_date: date,
    feature_json: dict[str, object],
) -> ComparableBuildResult:
    label_rows = (
        session.execute(
            select(HistoricalCaseLabel)
            .where(HistoricalCaseLabel.label_version == FEATURE_VERSION)
            .where(
                HistoricalCaseLabel.label_class.in_(
                    [HistoricalLabelClass.POSITIVE, HistoricalLabelClass.NEGATIVE]
                )
            )
            .options(
                selectinload(HistoricalCaseLabel.planning_application).selectinload(
                    PlanningApplication.documents
                )
            )
            .order_by(
                HistoricalCaseLabel.first_substantive_decision_date.desc().nullslast(),
                HistoricalCaseLabel.valid_date.desc().nullslast(),
            )
        )
        .scalars()
        .all()
    )

    linked_application_ids = {link.planning_application_id for link in site.planning_links}
    site_area_sqm = float((feature_json.get("values") or {}).get("site_area_sqm") or 0.0)
    site_archetype = str((feature_json.get("values") or {}).get("designation_archetype_key") or "")
    site_designation_profile = dict(feature_json.get("designation_profile") or {})
    scenario_form = scenario.proposal_form
    scenario_template = scenario.template_key

    positive_candidates: list[HistoricalCaseLabel] = []
    negative_candidates: list[HistoricalCaseLabel] = []
    for row in label_rows:
        if row.planning_application_id in linked_application_ids:
            continue
        if row.template_key != scenario_template:
            continue
        if row.valid_date is not None and row.valid_date > as_of_date:
            continue
        if (
            row.first_substantive_decision_date is not None
            and row.first_substantive_decision_date > as_of_date
        ):
            continue
        if row.review_status == GoldSetReviewStatus.EXCLUDED:
            continue
        if row.label_class == HistoricalLabelClass.POSITIVE:
            positive_candidates.append(row)
        elif row.label_class == HistoricalLabelClass.NEGATIVE:
            negative_candidates.append(row)

    approved = _select_members(
        site=site,
        scenario=scenario,
        site_area_sqm=site_area_sqm,
        site_archetype=site_archetype,
        site_designation_profile=site_designation_profile,
        scenario_form_value=scenario_form.value,
        rows=positive_candidates,
        outcome=ComparableOutcome.APPROVED,
        as_of_date=as_of_date,
    )
    refused = _select_members(
        site=site,
        scenario=scenario,
        site_area_sqm=site_area_sqm,
        site_archetype=site_archetype,
        site_designation_profile=site_designation_profile,
        scenario_form_value=scenario_form.value,
        rows=negative_candidates,
        outcome=ComparableOutcome.REFUSED,
        as_of_date=as_of_date,
    )

    comparable_case_set = assessment_run.comparable_case_set or ComparableCaseSet(
        assessment_run_id=assessment_run.id,
        strategy="template_then_borough_form_archetype",
    )
    comparable_case_set.same_borough_count = sum(
        1 for item in [*approved, *refused] if item.fallback_path == "same_borough_same_template"
    )
    comparable_case_set.london_count = sum(
        1 for item in [*approved, *refused] if item.fallback_path == "london_same_template"
    )
    comparable_case_set.approved_count = len(approved)
    comparable_case_set.refused_count = len(refused)
    session.add(comparable_case_set)
    session.flush()

    comparable_case_set.members.clear()
    source_snapshot_ids: set[str] = set()
    raw_asset_ids: set[str] = set()
    persisted_members: list[ComparableCaseMember] = []
    outcome_ranks = {
        ComparableOutcome.APPROVED: 0,
        ComparableOutcome.REFUSED: 0,
    }
    for item in [*approved, *refused]:
        outcome_ranks[item.outcome] += 1
        member = ComparableCaseMember(
            comparable_case_set_id=comparable_case_set.id,
            planning_application_id=item.planning_application.id,
            similarity_score=item.similarity_score,
            outcome=item.outcome,
            rank=outcome_ranks[item.outcome],
            fallback_path=item.fallback_path,
            match_json=item.match_json,
        )
        comparable_case_set.members.append(member)
        persisted_members.append(member)
        source_snapshot_ids.update(item.label.source_snapshot_ids_json or [])
        raw_asset_ids.update(item.label.raw_asset_ids_json or [])

    session.flush()
    return ComparableBuildResult(
        comparable_case_set=comparable_case_set,
        approved_members=[
            member for member in persisted_members if member.outcome == ComparableOutcome.APPROVED
        ],
        refused_members=[
            member for member in persisted_members if member.outcome == ComparableOutcome.REFUSED
        ],
        source_snapshot_ids=sorted(source_snapshot_ids),
        raw_asset_ids=sorted(raw_asset_ids),
    )


def _select_members(
    *,
    site: SiteCandidate,
    scenario: SiteScenario,
    site_area_sqm: float,
    site_archetype: str,
    site_designation_profile: dict[str, object],
    scenario_form_value: str,
    rows: list[HistoricalCaseLabel],
    outcome: ComparableOutcome,
    as_of_date: date,
) -> list[ComparableMatch]:
    selected: list[ComparableMatch] = []
    seen_ids: set[str] = set()
    tiers = (
        (
            "same_borough_same_template",
            lambda row: row.borough_id is not None and row.borough_id == site.borough_id,
        ),
        (
            "london_same_template",
            lambda row: (
                (row.proposal_form.value if row.proposal_form else None) == scenario_form_value
            ),
        ),
        (
            "archetype_same_template",
            lambda row: bool(site_archetype) and row.archetype_key == site_archetype,
        ),
    )

    for fallback_path, predicate in tiers:
        tier_rows = [row for row in rows if str(row.id) not in seen_ids and predicate(row)]
        tier_rows.sort(
            key=lambda row: (
                -_similarity_score(
                    site=site,
                    scenario=scenario,
                    site_area_sqm=site_area_sqm,
                    site_archetype=site_archetype,
                    site_designation_profile=site_designation_profile,
                    label=row,
                    as_of_date=as_of_date,
                ),
                row.first_substantive_decision_date or date.min,
                row.valid_date or date.min,
                str(row.id),
            )
        )
        for row in tier_rows:
            if len(selected) >= MAX_COMPARABLES_PER_OUTCOME:
                break
            score = _similarity_score(
                site=site,
                scenario=scenario,
                site_area_sqm=site_area_sqm,
                site_archetype=site_archetype,
                site_designation_profile=site_designation_profile,
                label=row,
                as_of_date=as_of_date,
            )
            selected.append(
                ComparableMatch(
                    label=row,
                    planning_application=row.planning_application,
                    outcome=outcome,
                    similarity_score=score,
                    fallback_path=fallback_path,
                    match_json=_match_json(
                        site=site,
                        scenario=scenario,
                        site_area_sqm=site_area_sqm,
                        site_archetype=site_archetype,
                        site_designation_profile=site_designation_profile,
                        label=row,
                        as_of_date=as_of_date,
                        similarity_score=score,
                    ),
                )
            )
            seen_ids.add(str(row.id))
    return selected


def _similarity_score(
    *,
    site: SiteCandidate,
    scenario: SiteScenario,
    site_area_sqm: float,
    site_archetype: str,
    site_designation_profile: dict[str, object],
    label: HistoricalCaseLabel,
    as_of_date: date,
) -> float:
    unit_delta = abs((label.units_proposed or 0) - scenario.units_assumed)
    unit_base = max(scenario.units_assumed, 1)
    unit_score = max(0.0, 1.0 - (unit_delta / unit_base))

    candidate_area = float(label.site_area_sqm or 0.0)
    area_base = max(site_area_sqm, 1.0)
    area_score = (
        0.5
        if candidate_area <= 0.0
        else max(0.0, 1.0 - (abs(candidate_area - site_area_sqm) / area_base))
    )

    same_borough = label.borough_id is not None and label.borough_id == site.borough_id
    borough_score = 1.0 if same_borough else 0.0

    proposal_form_match = (
        label.proposal_form is not None and label.proposal_form == scenario.proposal_form
    )
    proposal_form_score = 1.0 if proposal_form_match else 0.0

    designation_similarity = _designation_similarity(
        left=site_archetype,
        right=label.archetype_key or "",
        left_profile=site_designation_profile,
        right_profile=label.designation_profile_json,
    )

    decision_date = label.first_substantive_decision_date or label.valid_date
    years_since = 10.0
    if decision_date is not None:
        years_since = max(0.0, (as_of_date - decision_date).days / 365.25)
    recency_score = max(0.0, min(1.0, exp(-years_since / 6.0)))

    weighted = (
        (borough_score * 25.0)
        + (proposal_form_score * 20.0)
        + (unit_score * 20.0)
        + (area_score * 15.0)
        + (designation_similarity * 10.0)
        + (recency_score * 10.0)
    )
    return round(weighted, 4)


def _designation_similarity(
    *,
    left: str,
    right: str,
    left_profile: dict[str, object],
    right_profile: dict[str, object],
) -> float:
    if left and right and left == right:
        return 1.0
    left_tokens = set(_profile_tokens(left_profile))
    right_tokens = set(_profile_tokens(right_profile))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _profile_tokens(profile: dict[str, object]) -> list[str]:
    tokens: list[str] = []
    for key, value in profile.items():
        if isinstance(value, bool) and value:
            tokens.append(key)
        elif isinstance(value, list):
            tokens.extend(f"{key}:{item}" for item in value)
    return sorted(set(tokens))


def _match_json(
    *,
    site: SiteCandidate,
    scenario: SiteScenario,
    site_area_sqm: float,
    site_archetype: str,
    site_designation_profile: dict[str, object],
    label: HistoricalCaseLabel,
    as_of_date: date,
    similarity_score: float,
) -> dict[str, object]:
    decision_date = label.first_substantive_decision_date or label.valid_date
    return {
        "borough_match": label.borough_id == site.borough_id,
        "proposal_form_match": label.proposal_form == scenario.proposal_form,
        "template_key": label.template_key,
        "units_delta": None
        if label.units_proposed is None
        else label.units_proposed - scenario.units_assumed,
        "site_area_delta_sqm": None
        if label.site_area_sqm is None
        else round(float(label.site_area_sqm) - site_area_sqm, 3),
        "designation_profile_overlap": round(
            _designation_similarity(
                left=site_archetype,
                right=label.archetype_key or "",
                left_profile=site_designation_profile,
                right_profile=label.designation_profile_json,
            ),
            4,
        ),
        "candidate_archetype_key": label.archetype_key,
        "site_archetype_key": site_archetype,
        "decision_date": None if decision_date is None else decision_date.isoformat(),
        "years_since_decision": None
        if decision_date is None
        else round((as_of_date - decision_date).days / 365.25, 3),
        "similarity_score": similarity_score,
    }
