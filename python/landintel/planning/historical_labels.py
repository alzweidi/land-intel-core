from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import (
    GeomConfidence,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    HistoricalLabelDecision,
    ProposalForm,
)
from landintel.domain.models import (
    AuditEvent,
    HistoricalCaseLabel,
    PlanningApplication,
)
from landintel.features.build import (
    FEATURE_VERSION,
    build_designation_profile_for_geometry,
    derive_archetype_key,
    planning_application_area_sqm,
    planning_application_geometry,
)

POSITIVE_DECISION_MAP = {
    "APPROVED": HistoricalLabelDecision.APPROVE,
    "APPROVE": HistoricalLabelDecision.APPROVE,
    "GRANTED": HistoricalLabelDecision.APPROVE,
    "CONDITIONAL APPROVE": HistoricalLabelDecision.CONDITIONAL_APPROVE,
    "CONDITIONAL APPROVAL": HistoricalLabelDecision.CONDITIONAL_APPROVE,
    "CONDITIONAL GRANT": HistoricalLabelDecision.CONDITIONAL_APPROVE,
    "RESOLVE TO GRANT": HistoricalLabelDecision.RESOLVE_TO_GRANT,
    "MINDED TO GRANT": HistoricalLabelDecision.RESOLVE_TO_GRANT,
}
NEGATIVE_DECISION_MAP = {
    "REFUSED": HistoricalLabelDecision.REFUSE,
    "REFUSE": HistoricalLabelDecision.REFUSE,
}
EXCLUDED_STATUS_MAP = {
    "WITHDRAWN": HistoricalLabelDecision.WITHDRAWN,
    "INVALID": HistoricalLabelDecision.INVALID,
    "DUPLICATE": HistoricalLabelDecision.DUPLICATE,
}
NON_RELEVANT_ROUTE_PREFIXES = {"PRIOR_APPROVAL"}


@dataclass(slots=True)
class HistoricalLabelBuildSummary:
    total: int
    positive: int
    negative: int
    excluded: int
    censored: int


def rebuild_historical_case_labels(
    *,
    session: Session,
    requested_by: str | None,
) -> HistoricalLabelBuildSummary:
    applications = (
        session.execute(
            select(PlanningApplication)
            .options(
                selectinload(PlanningApplication.documents),
                selectinload(PlanningApplication.historical_labels),
            )
            .order_by(
                PlanningApplication.source_priority.desc(),
                PlanningApplication.valid_date.asc().nullslast(),
                PlanningApplication.external_ref.asc(),
            )
        )
        .scalars()
        .all()
    )

    existing_rows = (
        session.execute(
            select(HistoricalCaseLabel).where(HistoricalCaseLabel.label_version == FEATURE_VERSION)
        )
        .scalars()
        .all()
    )
    existing_by_application = {row.planning_application_id: row for row in existing_rows}
    seen_application_ids: set[str] = set()
    stronger_cases: list[PlanningApplication] = []
    counts = {
        HistoricalLabelClass.POSITIVE: 0,
        HistoricalLabelClass.NEGATIVE: 0,
        HistoricalLabelClass.EXCLUDED: 0,
        HistoricalLabelClass.CENSORED: 0,
    }

    for application in applications:
        seen_application_ids.add(str(application.id))
        payload = _build_label_payload(
            session=session,
            application=application,
            stronger_cases=stronger_cases,
        )
        row = existing_by_application.get(application.id)
        if row is None:
            row = HistoricalCaseLabel(
                planning_application_id=application.id,
                label_version=FEATURE_VERSION,
            )
            session.add(row)

        existing_review = {
            "review_status": row.review_status,
            "review_notes": row.review_notes,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
            "notable_policy_issues_json": list(row.notable_policy_issues_json or []),
            "extant_permission_outcome": row.extant_permission_outcome,
            "site_geometry_confidence": row.site_geometry_confidence,
        }

        row.borough_id = application.borough_id
        row.template_key = payload["template_key"]
        row.proposal_form = payload["proposal_form"]
        row.route_normalized = application.route_normalized
        row.units_proposed = application.units_proposed
        row.site_area_sqm = payload["site_area_sqm"]
        row.label_class = payload["label_class"]
        row.label_decision = payload["label_decision"]
        row.label_reason = payload["label_reason"]
        row.valid_date = application.valid_date
        row.first_substantive_decision_date = payload["first_substantive_decision_date"]
        row.label_window_end = payload["label_window_end"]
        row.source_priority_used = application.source_priority
        row.archetype_key = payload["archetype_key"]
        row.designation_profile_json = payload["designation_profile_json"]
        row.provenance_json = payload["provenance_json"]
        row.source_snapshot_ids_json = payload["source_snapshot_ids_json"]
        row.raw_asset_ids_json = payload["raw_asset_ids_json"]
        row.review_status = existing_review["review_status"] or GoldSetReviewStatus.PENDING
        row.review_notes = existing_review["review_notes"]
        row.reviewed_by = existing_review["reviewed_by"]
        row.reviewed_at = existing_review["reviewed_at"]
        row.notable_policy_issues_json = existing_review["notable_policy_issues_json"]
        row.extant_permission_outcome = existing_review["extant_permission_outcome"]
        row.site_geometry_confidence = (
            existing_review["site_geometry_confidence"] or payload["site_geometry_confidence"]
        )

        counts[row.label_class] += 1
        if row.label_class in {HistoricalLabelClass.POSITIVE, HistoricalLabelClass.NEGATIVE}:
            stronger_cases.append(application)

    for row in existing_rows:
        if str(row.planning_application_id) in seen_application_ids:
            continue
        session.delete(row)

    session.add(
        AuditEvent(
            action="historical_labels_rebuilt",
            entity_type="historical_case_label",
            entity_id=FEATURE_VERSION,
            before_json=None,
            after_json={
                "requested_by": requested_by,
                "version": FEATURE_VERSION,
                "total": len(applications),
                "positive": counts[HistoricalLabelClass.POSITIVE],
                "negative": counts[HistoricalLabelClass.NEGATIVE],
                "excluded": counts[HistoricalLabelClass.EXCLUDED],
                "censored": counts[HistoricalLabelClass.CENSORED],
            },
        )
    )
    session.flush()
    return HistoricalLabelBuildSummary(
        total=len(applications),
        positive=counts[HistoricalLabelClass.POSITIVE],
        negative=counts[HistoricalLabelClass.NEGATIVE],
        excluded=counts[HistoricalLabelClass.EXCLUDED],
        censored=counts[HistoricalLabelClass.CENSORED],
    )


def list_historical_label_cases(
    *,
    session: Session,
    review_status: GoldSetReviewStatus | None = None,
    template_key: str | None = None,
) -> list[HistoricalCaseLabel]:
    stmt = (
        select(HistoricalCaseLabel)
        .where(HistoricalCaseLabel.label_version == FEATURE_VERSION)
        .options(selectinload(HistoricalCaseLabel.planning_application))
        .order_by(
            HistoricalCaseLabel.review_status.asc(),
            HistoricalCaseLabel.first_substantive_decision_date.desc().nullslast(),
            HistoricalCaseLabel.valid_date.desc().nullslast(),
        )
    )
    if review_status is not None:
        stmt = stmt.where(HistoricalCaseLabel.review_status == review_status)
    if template_key is not None:
        stmt = stmt.where(HistoricalCaseLabel.template_key == template_key)
    return session.execute(stmt).scalars().all()


def get_historical_label_case(
    *,
    session: Session,
    case_id,
) -> HistoricalCaseLabel | None:
    return session.execute(
        select(HistoricalCaseLabel)
        .where(HistoricalCaseLabel.id == case_id)
        .options(
            selectinload(HistoricalCaseLabel.planning_application).selectinload(
                PlanningApplication.documents
            )
        )
    ).scalar_one_or_none()


def review_historical_label_case(
    *,
    session: Session,
    case: HistoricalCaseLabel,
    review_status: GoldSetReviewStatus,
    review_notes: str | None,
    notable_policy_issues: list[str],
    extant_permission_outcome: str | None,
    site_geometry_confidence: GeomConfidence | None,
    reviewed_by: str | None,
) -> HistoricalCaseLabel:
    before_json = _case_payload(case)
    case.review_status = review_status
    case.review_notes = review_notes
    case.notable_policy_issues_json = notable_policy_issues
    case.extant_permission_outcome = extant_permission_outcome
    case.site_geometry_confidence = site_geometry_confidence
    case.reviewed_by = reviewed_by
    case.reviewed_at = datetime.now(UTC)
    session.add(
        AuditEvent(
            action="historical_label_reviewed",
            entity_type="historical_case_label",
            entity_id=str(case.id),
            before_json=before_json,
            after_json=_case_payload(case),
        )
    )
    session.flush()
    return case


def _build_label_payload(
    *,
    session: Session,
    application: PlanningApplication,
    stronger_cases: list[PlanningApplication],
) -> dict[str, Any]:
    geometry = planning_application_geometry(application)
    site_area_sqm = planning_application_area_sqm(application) or None
    relevant, non_relevant_reason = _is_relevant_application(application)
    template_key = _map_template_key(application)
    label_window_end = (
        None if application.valid_date is None else _add_months(application.valid_date, 18)
    )

    source_snapshot_ids = {str(application.source_snapshot_id)}
    raw_asset_ids = {str(document.asset_id) for document in application.documents}
    designation_profile_json: dict[str, Any] = {}
    site_geometry_confidence = GeomConfidence.INSUFFICIENT

    if geometry is not None and site_area_sqm is not None:
        designation_profile_json, designation_source_ids = build_designation_profile_for_geometry(
            session=session,
            geometry=geometry,
            area_sqm=site_area_sqm if site_area_sqm > 0 else 1.0,
            as_of_date=application.valid_date or application.decision_date or date.today(),
        )
        source_snapshot_ids.update(designation_source_ids)
        site_geometry_confidence = (
            GeomConfidence.MEDIUM
            if geometry.geom_type in {"Polygon", "MultiPolygon"}
            else GeomConfidence.LOW
        )

    proposal_form = _map_proposal_form(
        application=application,
        designation_profile=designation_profile_json,
    )
    archetype_key = (
        None
        if template_key is None
        else derive_archetype_key(
            template_key=template_key,
            proposal_form=proposal_form,
            designation_profile=designation_profile_json,
        )
    )
    stronger_source = _find_stronger_source(application=application, stronger_cases=stronger_cases)
    normalized_decision = _normalized_decision(application)

    label_class = HistoricalLabelClass.CENSORED
    label_decision = HistoricalLabelDecision.UNDETERMINED
    label_reason = None
    first_substantive_decision_date = application.decision_date

    if stronger_source is not None:
        label_class = HistoricalLabelClass.EXCLUDED
        label_decision = HistoricalLabelDecision.DUPLICATE
        label_reason = (
            f"Stronger source {stronger_source.source_system}:{stronger_source.external_ref} "
            "represents the same historical case."
        )
    elif not relevant:
        label_class = HistoricalLabelClass.EXCLUDED
        label_decision = HistoricalLabelDecision.NON_RELEVANT
        label_reason = non_relevant_reason
    elif template_key is None:
        label_class = HistoricalLabelClass.EXCLUDED
        label_decision = HistoricalLabelDecision.NON_RELEVANT
        label_reason = "Enabled templates do not cover this units/route combination."
    elif normalized_decision in POSITIVE_DECISION_MAP:
        if (
            application.decision_date is not None
            and label_window_end is not None
            and application.decision_date <= label_window_end
        ):
            label_class = HistoricalLabelClass.POSITIVE
            label_decision = POSITIVE_DECISION_MAP[normalized_decision]
        else:
            label_class = HistoricalLabelClass.CENSORED
            label_decision = POSITIVE_DECISION_MAP[normalized_decision]
            label_reason = "Positive decision fell outside the 18-month label window."
    elif normalized_decision in NEGATIVE_DECISION_MAP:
        if (
            application.decision_date is not None
            and label_window_end is not None
            and application.decision_date <= label_window_end
        ):
            label_class = HistoricalLabelClass.NEGATIVE
            label_decision = NEGATIVE_DECISION_MAP[normalized_decision]
        else:
            label_class = HistoricalLabelClass.CENSORED
            label_decision = NEGATIVE_DECISION_MAP[normalized_decision]
            label_reason = "Negative decision fell outside the 18-month label window."
    elif normalized_decision in EXCLUDED_STATUS_MAP:
        label_class = HistoricalLabelClass.EXCLUDED
        label_decision = EXCLUDED_STATUS_MAP[normalized_decision]
        label_reason = f"Application marked {normalized_decision.lower()}."
    else:
        label_class = HistoricalLabelClass.CENSORED
        label_decision = HistoricalLabelDecision.UNDETERMINED
        label_reason = (
            "Application is pending, undetermined, administrative, or otherwise censored "
            "for label construction."
        )

    return {
        "template_key": template_key,
        "proposal_form": proposal_form,
        "site_area_sqm": site_area_sqm,
        "label_class": label_class,
        "label_decision": label_decision,
        "label_reason": label_reason,
        "first_substantive_decision_date": first_substantive_decision_date,
        "label_window_end": label_window_end,
        "archetype_key": archetype_key,
        "designation_profile_json": designation_profile_json,
        "provenance_json": {
            "transform_version": FEATURE_VERSION,
            "normalized_decision": normalized_decision,
            "stronger_source_external_ref": (
                None if stronger_source is None else stronger_source.external_ref
            ),
            "source_priority": application.source_priority,
            "route_normalized": application.route_normalized,
            "application_type": application.application_type,
            "decision_type": application.decision_type,
        },
        "source_snapshot_ids_json": sorted(source_snapshot_ids),
        "raw_asset_ids_json": sorted(raw_asset_ids),
        "site_geometry_confidence": site_geometry_confidence,
    }


def _is_relevant_application(application: PlanningApplication) -> tuple[bool, str | None]:
    route = (application.route_normalized or application.application_type or "").upper()
    decision_type = (application.decision_type or "").upper()
    dwelling_use = str((application.raw_record_json or {}).get("dwelling_use") or "").upper()
    if any(route.startswith(prefix) for prefix in NON_RELEVANT_ROUTE_PREFIXES):
        return False, "Prior approval and non-template routes are excluded from Phase 5A labels."
    if "APPEAL" in route or "APPEAL" in decision_type:
        return False, "Appeal-only outcomes are excluded from Phase 5A labels."
    if decision_type and "RESIDENTIAL" not in decision_type and dwelling_use != "C3":
        return False, "Non-residential application type is excluded from the enabled templates."
    return True, None


def _map_template_key(application: PlanningApplication) -> str | None:
    units = application.units_proposed
    if units is None or units < 1:
        return None
    route = (application.route_normalized or application.application_type or "").upper()
    if 1 <= units <= 4 and route == "FULL":
        return "resi_1_4_full"
    if 5 <= units <= 9 and route == "FULL":
        return "resi_5_9_full"
    if 10 <= units <= 49 and route == "OUTLINE":
        return "resi_10_49_outline"
    return None


def _map_proposal_form(
    *,
    application: PlanningApplication,
    designation_profile: dict[str, Any],
) -> ProposalForm:
    description = application.proposal_description.lower()
    if "backland" in description:
        return ProposalForm.BACKLAND
    if "infill" in description:
        return ProposalForm.INFILL
    if designation_profile.get("brownfield_part1") or designation_profile.get(
        "brownfield_part2_active"
    ):
        return ProposalForm.BROWNFIELD_REUSE
    if any(token in description for token in ("yard", "garage", "brownfield")):
        return ProposalForm.BROWNFIELD_REUSE
    return ProposalForm.REDEVELOPMENT


def _normalized_decision(application: PlanningApplication) -> str:
    decision = (application.decision or application.status or "").strip().upper()
    if not decision:
        return "UNDETERMINED"
    if "CONDITIONAL" in decision and "APPROV" in decision:
        return "CONDITIONAL APPROVE"
    if "MINDED TO GRANT" in decision or "RESOLVE TO GRANT" in decision:
        return "RESOLVE TO GRANT"
    if decision in {"PENDING", "UNDETERMINED"}:
        return "UNDETERMINED"
    if "WITHDRAWN" in decision:
        return "WITHDRAWN"
    if "INVALID" in decision:
        return "INVALID"
    if "DUPLICATE" in decision:
        return "DUPLICATE"
    if "REFUS" in decision:
        return "REFUSED"
    if "APPROV" in decision or "GRANT" in decision:
        return "APPROVED"
    return decision


def _find_stronger_source(
    *,
    application: PlanningApplication,
    stronger_cases: list[PlanningApplication],
) -> PlanningApplication | None:
    for stronger in stronger_cases:
        if stronger.source_priority <= application.source_priority:
            continue
        if _same_case(application, stronger):
            return stronger
    return None


def _same_case(candidate: PlanningApplication, stronger: PlanningApplication) -> bool:
    if candidate.borough_id != stronger.borough_id:
        return False
    if candidate.units_proposed != stronger.units_proposed:
        return False
    candidate_route = (candidate.route_normalized or candidate.application_type or "").upper()
    stronger_route = (stronger.route_normalized or stronger.application_type or "").upper()
    if candidate_route != stronger_route:
        return False
    if not _dates_close(candidate.valid_date, stronger.valid_date, days=45):
        return False

    candidate_geometry = planning_application_geometry(candidate)
    stronger_geometry = planning_application_geometry(stronger)
    if candidate_geometry is not None and stronger_geometry is not None:
        if candidate_geometry.geom_type in {
            "Polygon",
            "MultiPolygon",
        } and stronger_geometry.geom_type in {
            "Polygon",
            "MultiPolygon",
        }:
            if not candidate_geometry.intersects(stronger_geometry):
                return False
            overlap = candidate_geometry.intersection(stronger_geometry).area
            smaller = min(candidate_geometry.area, stronger_geometry.area) or 1.0
            if overlap / smaller >= 0.5:
                return True
        if float(candidate_geometry.distance(stronger_geometry)) <= 30.0:
            return True

    return _description_signature(candidate.proposal_description) == _description_signature(
        stronger.proposal_description
    )


def _description_signature(text: str) -> tuple[str, ...]:
    stopwords = {
        "the",
        "and",
        "of",
        "to",
        "provide",
        "residential",
        "units",
        "unit",
        "site",
        "with",
        "at",
    }
    tokens = [
        token
        for token in "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()
        if token not in stopwords
    ]
    return tuple(sorted(tokens))


def _dates_close(left: date | None, right: date | None, *, days: int) -> bool:
    if left is None or right is None:
        return False
    return abs((left - right).days) <= days


def _add_months(value: date, months: int) -> date:
    year = value.year + ((value.month - 1 + months) // 12)
    month = ((value.month - 1 + months) % 12) + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _case_payload(case: HistoricalCaseLabel) -> dict[str, Any]:
    return {
        "review_status": case.review_status.value,
        "review_notes": case.review_notes,
        "reviewed_by": case.reviewed_by,
        "reviewed_at": None if case.reviewed_at is None else case.reviewed_at.isoformat(),
        "notable_policy_issues_json": list(case.notable_policy_issues_json or []),
        "extant_permission_outcome": case.extant_permission_outcome,
        "site_geometry_confidence": (
            None if case.site_geometry_confidence is None else case.site_geometry_confidence.value
        ),
    }
