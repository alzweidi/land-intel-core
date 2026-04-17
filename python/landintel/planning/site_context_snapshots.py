from __future__ import annotations

from typing import Any

from landintel.domain.models import (
    PlanningApplication,
    PlanningApplicationDocument,
    PlanningConstraintFeature,
    PolicyArea,
    RawAsset,
    SiteConstraintFact,
    SitePlanningLink,
    SitePolicyFact,
)


def snapshot_raw_asset(asset: RawAsset | None) -> dict[str, Any] | None:
    if asset is None:
        return None
    return {
        "id": str(asset.id),
        "storage_path": asset.storage_path,
        "asset_type": asset.asset_type,
        "original_url": asset.original_url,
        "mime_type": asset.mime_type,
        "content_sha256": asset.content_sha256,
        "size_bytes": asset.size_bytes,
        "fetched_at": asset.fetched_at.isoformat(),
    }


def snapshot_planning_document(document: PlanningApplicationDocument) -> dict[str, Any]:
    return {
        "id": str(document.id),
        "asset_id": str(document.asset_id),
        "doc_type": document.doc_type,
        "doc_url": document.doc_url,
        "asset": snapshot_raw_asset(document.asset),
    }


def snapshot_planning_application(application: PlanningApplication) -> dict[str, Any]:
    return {
        "id": str(application.id),
        "borough_id": application.borough_id,
        "source_system": application.source_system,
        "source_snapshot_id": str(application.source_snapshot_id),
        "external_ref": application.external_ref,
        "application_type": application.application_type,
        "proposal_description": application.proposal_description,
        "valid_date": (
            None if application.valid_date is None else application.valid_date.isoformat()
        ),
        "decision_date": (
            None if application.decision_date is None else application.decision_date.isoformat()
        ),
        "decision": application.decision,
        "decision_type": application.decision_type,
        "status": application.status,
        "route_normalized": application.route_normalized,
        "units_proposed": application.units_proposed,
        "source_priority": application.source_priority,
        "source_url": application.source_url,
        "site_geom_4326": application.site_geom_4326,
        "site_point_4326": application.site_point_4326,
        "raw_record_json": dict(application.raw_record_json or {}),
        "documents": [snapshot_planning_document(document) for document in application.documents],
    }


def snapshot_policy_area(area: PolicyArea) -> dict[str, Any]:
    return {
        "id": str(area.id),
        "borough_id": area.borough_id,
        "policy_family": area.policy_family,
        "policy_code": area.policy_code,
        "name": area.name,
        "geom_4326": area.geom_4326,
        "legal_effective_from": (
            None if area.legal_effective_from is None else area.legal_effective_from.isoformat()
        ),
        "legal_effective_to": (
            None if area.legal_effective_to is None else area.legal_effective_to.isoformat()
        ),
        "source_snapshot_id": str(area.source_snapshot_id),
        "source_class": area.source_class.value,
        "source_url": area.source_url,
        "raw_record_json": dict(area.raw_record_json or {}),
    }


def snapshot_constraint_feature(feature: PlanningConstraintFeature) -> dict[str, Any]:
    return {
        "id": str(feature.id),
        "feature_family": feature.feature_family,
        "feature_subtype": feature.feature_subtype,
        "authority_level": feature.authority_level,
        "geom_4326": feature.geom_4326,
        "legal_status": feature.legal_status,
        "effective_from": (
            None if feature.effective_from is None else feature.effective_from.isoformat()
        ),
        "effective_to": (
            None if feature.effective_to is None else feature.effective_to.isoformat()
        ),
        "source_snapshot_id": str(feature.source_snapshot_id),
        "source_class": feature.source_class.value,
        "source_url": feature.source_url,
        "raw_record_json": dict(feature.raw_record_json or {}),
    }


def planning_application_snapshot(link: SitePlanningLink) -> dict[str, Any]:
    stored = getattr(link, "application_snapshot_json", None)
    if isinstance(stored, dict) and stored:
        return stored
    return snapshot_planning_application(link.planning_application)


def policy_area_snapshot(fact: SitePolicyFact) -> dict[str, Any]:
    stored = fact.policy_area_snapshot_json
    if isinstance(stored, dict) and stored:
        return stored
    return snapshot_policy_area(fact.policy_area)


def constraint_snapshot(fact: SiteConstraintFact) -> dict[str, Any]:
    stored = fact.constraint_snapshot_json
    if isinstance(stored, dict) and stored:
        return stored
    return snapshot_constraint_feature(fact.constraint_feature)
