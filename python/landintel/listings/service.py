import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from landintel.config import Settings
from landintel.connectors.base import ComplianceError, ConnectorContext, ConnectorRunOutput
from landintel.connectors.csv_import import CsvImportConnector
from landintel.connectors.html_snapshot import HtmlSnapshotFetcher
from landintel.connectors.manual_url import ManualUrlConnector
from landintel.connectors.public_page import GenericPublicPageConnector
from landintel.connectors.tabular_feed import GenericTabularFeedConnector
from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    DocumentType,
    JobType,
    ListingStatus,
    ListingType,
    SourceFreshnessStatus,
)
from landintel.domain.models import (
    AuditEvent,
    JobRun,
    ListingCluster,
    ListingClusterMember,
    ListingDocument,
    ListingItem,
    ListingSnapshot,
    ListingSource,
    RawAsset,
    SiteCandidate,
    SourceSnapshot,
)
from landintel.jobs.service import enqueue_cluster_rebuild_job
from landintel.listings.clustering import ClusterListingInput, build_clusters
from landintel.listings.documents import extract_pdf_text
from landintel.storage.base import StorageAdapter

UUID_NAMESPACE = uuid.UUID("ccf3ba74-c45d-4dd6-bfb4-db5747dca420")
AUTO_SITE_BUILD_TYPES = {
    ListingType.LAND,
    ListingType.LAND_WITH_BUILDING,
    ListingType.REDEVELOPMENT_SITE,
}
AUTO_SITE_BUILD_STATUSES = {
    ListingStatus.LIVE,
    ListingStatus.AUCTION,
}


@dataclass(slots=True)
class ConnectorPersistenceResult:
    source_snapshot_id: uuid.UUID
    listing_item_ids: list[uuid.UUID]


def execute_listing_job(
    *,
    session: Session,
    job: JobRun,
    settings: Settings,
    storage: StorageAdapter,
) -> ConnectorPersistenceResult:
    source = resolve_listing_source(session=session, job=job)
    connector = build_connector(source.connector_type, settings=settings)
    context = ConnectorContext(
        source_name=source.name,
        connector_type=source.connector_type,
        refresh_policy_json=source.refresh_policy_json,
        requested_by=job.requested_by,
    )
    enforce_compliance(source=source, job=job)
    output = connector.run(context=context, payload=job.payload_json)
    result = persist_connector_output(
        session=session,
        job=job,
        source=source,
        output=output,
        storage=storage,
    )
    enqueue_cluster_rebuild_job(session=session, requested_by=job.requested_by)
    return result


def resolve_listing_source(*, session: Session, job: JobRun) -> ListingSource:
    source_name = str(job.payload_json.get("source_name", "manual_url"))
    source = session.execute(
        select(ListingSource).where(ListingSource.name == source_name)
    ).scalar_one_or_none()
    if source is not None:
        return source

    if job.job_type == JobType.MANUAL_URL_SNAPSHOT:
        source = ListingSource(
            name=source_name,
            connector_type=ConnectorType.MANUAL_URL,
            compliance_mode=ComplianceMode.MANUAL_ONLY,
            refresh_policy_json={"run_mode": "manual"},
            active=True,
        )
        session.add(source)
        session.flush()
        return source

    if job.job_type == JobType.CSV_IMPORT_SNAPSHOT:
        source = ListingSource(
            name=source_name,
            connector_type=ConnectorType.CSV_IMPORT,
            compliance_mode=ComplianceMode.CSV_ONLY,
            refresh_policy_json={"run_mode": "manual"},
            active=True,
        )
        session.add(source)
        session.flush()
        return source

    raise ValueError(f"Listing source '{source_name}' not found.")


def build_connector(connector_type: ConnectorType, *, settings: Settings):
    fetcher = HtmlSnapshotFetcher(settings)
    if connector_type == ConnectorType.MANUAL_URL:
        return ManualUrlConnector(fetcher)
    if connector_type == ConnectorType.CSV_IMPORT:
        return CsvImportConnector(fetcher)
    if connector_type == ConnectorType.PUBLIC_PAGE:
        return GenericPublicPageConnector(fetcher)
    if connector_type == ConnectorType.TABULAR_FEED:
        return GenericTabularFeedConnector(settings)
    raise ValueError(f"Unsupported connector type: {connector_type}")


def enforce_compliance(*, source: ListingSource, job: JobRun) -> None:
    if not source.active:
        raise ComplianceError(f"Listing source '{source.name}' is inactive.")

    if job.job_type == JobType.MANUAL_URL_SNAPSHOT:
        allowed_modes = {
            ComplianceMode.MANUAL_ONLY,
            ComplianceMode.COMPLIANT_AUTOMATED,
        }
        if source.compliance_mode not in allowed_modes:
            raise ComplianceError(
                "Manual URL intake is blocked for source "
                f"'{source.name}' with mode {source.compliance_mode}."
            )
        return

    if job.job_type == JobType.CSV_IMPORT_SNAPSHOT:
        allowed_modes = {
            ComplianceMode.CSV_ONLY,
            ComplianceMode.MANUAL_ONLY,
        }
        if source.compliance_mode not in allowed_modes:
            raise ComplianceError(
                "CSV import is blocked for source "
                f"'{source.name}' with mode {source.compliance_mode}."
            )
        return

    if job.job_type == JobType.LISTING_SOURCE_RUN:
        if source.compliance_mode != ComplianceMode.COMPLIANT_AUTOMATED:
            raise ComplianceError(
                "Automated connector runs are blocked unless "
                "compliance_mode is COMPLIANT_AUTOMATED."
            )
        return

    raise ValueError(f"Unsupported listing job type: {job.job_type}")


def persist_connector_output(
    *,
    session: Session,
    job: JobRun,
    source: ListingSource,
    output: ConnectorRunOutput,
    storage: StorageAdapter,
) -> ConnectorPersistenceResult:
    source_snapshot_id = deterministic_uuid(job.id, "source_snapshot")
    existing_snapshot = session.get(SourceSnapshot, source_snapshot_id)
    if existing_snapshot is not None:
        listing_ids = [
            listing_snapshot.listing_item_id
            for listing_snapshot in session.execute(
                select(ListingSnapshot).where(
                    ListingSnapshot.source_snapshot_id == source_snapshot_id
                )
            ).scalars()
        ]
        return ConnectorPersistenceResult(
            source_snapshot_id=existing_snapshot.id,
            listing_item_ids=listing_ids,
        )

    stored_assets: dict[str, RawAsset] = {}
    asset_hashes: list[str] = []
    for asset in output.assets:
        raw_asset_id = deterministic_uuid(job.id, f"raw_asset:{asset.asset_key}")
        content_hash = sha256_hexdigest(asset.content)
        asset_hashes.append(content_hash)
        storage_path = build_storage_path(
            source_name=source.name,
            raw_asset_id=raw_asset_id,
            asset=asset,
        )
        _store_bytes_idempotently(
            storage,
            storage_path=storage_path,
            payload=asset.content,
            content_type=asset.content_type,
        )

        raw_asset = RawAsset(
            id=raw_asset_id,
            source_snapshot_id=source_snapshot_id,
            asset_type=asset.asset_type,
            original_url=asset.original_url,
            storage_path=storage_path,
            mime_type=asset.content_type,
            content_sha256=content_hash,
            size_bytes=len(asset.content),
            fetched_at=asset.fetched_at,
        )
        session.add(raw_asset)
        stored_assets[asset.asset_key] = raw_asset

    source_snapshot = SourceSnapshot(
        id=source_snapshot_id,
        source_family=output.source_family,
        source_name=output.source_name,
        source_uri=output.source_uri,
        acquired_at=output.observed_at,
        effective_from=None,
        effective_to=None,
        schema_hash=sha256_hexdigest(f"{output.source_family}:phase1a".encode()),
        content_hash=sha256_hexdigest("|".join(sorted(asset_hashes)).encode("utf-8")),
        coverage_note=output.coverage_note,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=output.parse_status,
        parse_error_text=None,
        manifest_json={
            **output.manifest_json,
            "job_id": str(job.id),
            "job_type": job.job_type.value,
            "source_id": str(source.id),
            "listing_count": len(output.listings),
            "asset_count": len(output.assets),
        },
    )
    session.add(source_snapshot)

    listing_item_ids: list[uuid.UUID] = []
    for listing in output.listings:
        listing_item = session.execute(
            select(ListingItem).where(
                ListingItem.source_id == source.id,
                ListingItem.source_listing_id == listing.source_listing_id,
            )
        ).scalar_one_or_none()
        if listing_item is None:
            listing_item = ListingItem(
                source_id=source.id,
                source_listing_id=listing.source_listing_id,
                canonical_url=listing.canonical_url,
                listing_type=listing.listing_type,
                first_seen_at=listing.observed_at,
                last_seen_at=listing.observed_at,
                latest_status=listing.status,
                current_snapshot_id=None,
                normalized_address=listing.normalized_address,
                search_text=listing.search_text,
            )
            session.add(listing_item)
            session.flush()
        else:
            listing_item.canonical_url = listing.canonical_url
            listing_item.listing_type = listing.listing_type
            listing_item.last_seen_at = max(listing_item.last_seen_at, listing.observed_at)
            listing_item.latest_status = listing.status
            listing_item.normalized_address = listing.normalized_address
            listing_item.search_text = listing.search_text

        listing_snapshot = ListingSnapshot(
            id=deterministic_uuid(job.id, f"listing_snapshot:{listing.source_listing_id}"),
            listing_item_id=listing_item.id,
            source_snapshot_id=source_snapshot_id,
            observed_at=listing.observed_at,
            headline=listing.headline,
            description_text=listing.description_text,
            guide_price_gbp=listing.guide_price_gbp,
            price_basis_type=listing.price_basis_type,
            status=listing.status,
            auction_date=listing.auction_date,
            address_text=listing.address_text,
            normalized_address=listing.normalized_address,
            lat=listing.lat,
            lon=listing.lon,
            brochure_asset_id=(
                stored_assets[listing.brochure_asset_key].id
                if listing.brochure_asset_key and listing.brochure_asset_key in stored_assets
                else None
            ),
            map_asset_id=(
                stored_assets[listing.map_asset_key].id
                if listing.map_asset_key and listing.map_asset_key in stored_assets
                else None
            ),
            raw_record_json=listing.raw_record_json,
            search_text=listing.search_text,
        )
        session.add(listing_snapshot)
        listing_item.current_snapshot_id = listing_snapshot.id
        listing_item_ids.append(listing_item.id)

        for asset_key in filter(None, [listing.brochure_asset_key, listing.map_asset_key]):
            raw_asset = stored_assets.get(asset_key)
            if raw_asset is None or raw_asset.asset_type != "PDF":
                continue

            extraction = extract_pdf_text(
                next(asset.content for asset in output.assets if asset.asset_key == asset_key)
            )
            asset_role = next(
                asset.role for asset in output.assets if asset.asset_key == asset_key
            )
            doc_type = (
                DocumentType.BROCHURE
                if asset_role == DocumentType.BROCHURE.value
                else DocumentType.MAP
            )
            listing_document = ListingDocument(
                id=deterministic_uuid(job.id, f"listing_document:{listing_item.id}:{asset_key}"),
                listing_item_id=listing_item.id,
                asset_id=raw_asset.id,
                doc_type=doc_type,
                page_count=extraction.page_count,
                extraction_status=extraction.extraction_status,
                extracted_text=extraction.extracted_text,
            )
            session.add(listing_document)

    session.flush()
    return ConnectorPersistenceResult(
        source_snapshot_id=source_snapshot_id,
        listing_item_ids=listing_item_ids,
    )


def rebuild_listing_clusters(session: Session) -> list[ListingCluster]:
    existing_cluster_ids = {
        cluster_id
        for cluster_id in session.execute(select(ListingCluster.id)).scalars().all()
    }

    current_snapshots = session.execute(
        select(ListingItem)
        .options(
            selectinload(ListingItem.documents).joinedload(ListingDocument.asset),
            selectinload(ListingItem.source),
            selectinload(ListingItem.snapshots),
        )
        .order_by(ListingItem.first_seen_at.asc())
    ).scalars().all()

    inputs: list[ClusterListingInput] = []
    for item in current_snapshots:
        current_snapshot = next(
            (snapshot for snapshot in item.snapshots if snapshot.id == item.current_snapshot_id),
            None,
        )
        if current_snapshot is None:
            continue
        document_hashes = tuple(
            sorted(
                document.asset.content_sha256
                for document in item.documents
                if document.asset is not None
            )
        )
        inputs.append(
            ClusterListingInput(
                listing_item_id=item.id,
                canonical_url=item.canonical_url,
                normalized_address=current_snapshot.normalized_address or item.normalized_address,
                headline=current_snapshot.headline,
                guide_price_gbp=current_snapshot.guide_price_gbp,
                lat=current_snapshot.lat,
                lon=current_snapshot.lon,
                document_hashes=document_hashes,
            )
        )

    cluster_results = build_clusters(inputs)
    listing_cluster_by_item_id = {
        member.listing_item_id: cluster.cluster_id
        for cluster in cluster_results
        for member in cluster.members
    }
    rebuilt_listing_item_ids = list(listing_cluster_by_item_id)

    if rebuilt_listing_item_ids:
        # Clear prior memberships before reinserting rebuilt cluster rows so listings that move
        # into a different cluster ID do not trip the unique constraint on listing_item_id.
        session.execute(
            delete(ListingClusterMember).where(
                ListingClusterMember.listing_item_id.in_(rebuilt_listing_item_ids)
            )
        )
        session.flush()

    cluster_models: list[ListingCluster] = []
    for cluster in cluster_results:
        cluster_model = session.get(ListingCluster, cluster.cluster_id)
        if cluster_model is None:
            cluster_model = ListingCluster(
                id=cluster.cluster_id,
                cluster_key=cluster.cluster_key,
                cluster_status=cluster.cluster_status,
            )
            session.add(cluster_model)
        else:
            cluster_model.cluster_key = cluster.cluster_key
            cluster_model.cluster_status = cluster.cluster_status
        cluster_models.append(cluster_model)
        for member in cluster.members:
            session.add(
                ListingClusterMember(
                    id=deterministic_uuid(cluster.cluster_id, str(member.listing_item_id)),
                    listing_cluster_id=cluster.cluster_id,
                    listing_item_id=member.listing_item_id,
                    confidence=member.confidence,
                    rules_json={"reasons": member.reasons},
                )
            )

    session.flush()

    sites = session.execute(
        select(SiteCandidate).options(selectinload(SiteCandidate.current_listing))
    ).scalars().all()
    for site in sites:
        if site.current_listing_id is None:
            continue
        new_cluster_id = listing_cluster_by_item_id.get(site.current_listing_id)
        if new_cluster_id is None or new_cluster_id == site.listing_cluster_id:
            continue
        before_json = _site_cluster_audit_payload(site)
        site.listing_cluster_id = new_cluster_id
        after_json = _site_cluster_audit_payload(site)
        session.add(
            AuditEvent(
                action="site_cluster_relinked",
                entity_type="site_candidate",
                entity_id=str(site.id),
                before_json=before_json,
                after_json=after_json,
            )
        )
    session.flush()

    referenced_cluster_ids = {
        cluster_id
        for cluster_id in session.execute(select(SiteCandidate.listing_cluster_id)).scalars().all()
        if cluster_id is not None
    }
    obsolete_cluster_ids = sorted(
        existing_cluster_ids.difference({cluster.cluster_id for cluster in cluster_results})
        - referenced_cluster_ids,
        key=str,
    )
    if obsolete_cluster_ids:
        session.execute(
            delete(ListingClusterMember).where(
                ListingClusterMember.listing_cluster_id.in_(obsolete_cluster_ids)
            )
        )
        session.execute(delete(ListingCluster).where(ListingCluster.id.in_(obsolete_cluster_ids)))
        session.flush()

    return cluster_models


def list_auto_site_build_cluster_ids(session: Session) -> list[uuid.UUID]:
    clusters = session.execute(
        select(ListingCluster).options(
            selectinload(ListingCluster.members)
            .selectinload(ListingClusterMember.listing_item)
            .selectinload(ListingItem.snapshots)
        )
    ).scalars().all()
    eligible_cluster_ids: list[uuid.UUID] = []
    for cluster in clusters:
        current_listing, current_snapshot = _cluster_current_listing(cluster)
        if current_listing is None or current_snapshot is None:
            continue
        if current_listing.listing_type not in AUTO_SITE_BUILD_TYPES:
            continue
        if current_snapshot.status not in AUTO_SITE_BUILD_STATUSES:
            continue
        eligible_cluster_ids.append(cluster.id)
    return eligible_cluster_ids


def list_listing_sources(session: Session) -> list[ListingSource]:
    stmt = select(ListingSource).order_by(ListingSource.name.asc())
    return list(session.execute(stmt).scalars().all())


def build_storage_path(*, source_name: str, raw_asset_id: uuid.UUID, asset) -> str:
    extension = {
        "HTML": ".html",
        "PDF": ".pdf",
        "CSV": ".csv",
    }.get(asset.asset_type.upper(), Path(asset.original_url).suffix or "")
    return f"raw/{_safe_storage_source_name(source_name)}/{raw_asset_id}{extension}"


def deterministic_uuid(namespace_seed: uuid.UUID, suffix: str) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, f"{namespace_seed}:{suffix}")


def sha256_hexdigest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_storage_source_name(source_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", source_name.strip())
    normalized = normalized.strip("._-")
    if not normalized:
        normalized = "source"
    if len(normalized) <= 64:
        return normalized
    digest = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:12]
    return f"{normalized[:48]}-{digest}"


def _store_bytes_idempotently(
    storage,
    *,
    storage_path: str,
    payload: bytes,
    content_type: str,
) -> None:
    try:
        existing_payload = storage.get_bytes(storage_path)
    except FileNotFoundError:
        storage.put_bytes(storage_path, payload, content_type=content_type)
        return

    if existing_payload != payload:
        raise ValueError(f"Refusing to overwrite immutable raw asset at {storage_path}")


def _site_cluster_audit_payload(site: SiteCandidate) -> dict[str, object]:
    return {
        "site_id": str(site.id),
        "listing_cluster_id": (
            None if site.listing_cluster_id is None else str(site.listing_cluster_id)
        ),
        "current_listing_id": (
            None if site.current_listing_id is None else str(site.current_listing_id)
        ),
        "display_name": site.display_name,
    }


def _cluster_current_listing(
    cluster: ListingCluster,
) -> tuple[ListingItem | None, ListingSnapshot | None]:
    members = sorted(
        cluster.members,
        key=lambda member: (
            member.listing_item.last_seen_at,
            member.confidence,
            str(member.listing_item_id),
        ),
        reverse=True,
    )
    if not members:
        return None, None

    listing_item = members[0].listing_item
    current_snapshot = next(
        (
            snapshot
            for snapshot in listing_item.snapshots
            if snapshot.id == listing_item.current_snapshot_id
        ),
        None,
    )
    return listing_item, current_snapshot
