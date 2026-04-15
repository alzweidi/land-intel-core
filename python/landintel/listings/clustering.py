import hashlib
import math
import re
import uuid
from dataclasses import dataclass, field
from itertools import combinations

from landintel.domain.enums import ListingClusterStatus

CLUSTER_NAMESPACE = uuid.UUID("f9d3f27e-f0a0-4826-8af7-cfa551d2b5f7")


@dataclass(slots=True)
class ClusterListingInput:
    listing_item_id: uuid.UUID
    canonical_url: str
    normalized_address: str | None
    headline: str | None
    guide_price_gbp: int | None
    lat: float | None
    lon: float | None
    document_hashes: tuple[str, ...] = ()


@dataclass(slots=True)
class ClusterEdge:
    left_listing_id: uuid.UUID
    right_listing_id: uuid.UUID
    confidence: float
    reasons: list[str]


@dataclass(slots=True)
class ClusterMemberResult:
    listing_item_id: uuid.UUID
    confidence: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ListingClusterResult:
    cluster_id: uuid.UUID
    cluster_key: str
    cluster_status: ListingClusterStatus
    members: list[ClusterMemberResult]


def build_clusters(listings: list[ClusterListingInput]) -> list[ListingClusterResult]:
    if not listings:
        return []

    listing_map = {listing.listing_item_id: listing for listing in listings}
    edges = generate_cluster_edges(listings)
    parent = {listing.listing_item_id: listing.listing_item_id for listing in listings}

    def find(node: uuid.UUID) -> uuid.UUID:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: uuid.UUID, right: uuid.UUID) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        parent[max(left_root, right_root, key=str)] = min(left_root, right_root, key=str)

    for edge in edges:
        union(edge.left_listing_id, edge.right_listing_id)

    buckets: dict[uuid.UUID, list[uuid.UUID]] = {}
    for listing_id in listing_map:
        buckets.setdefault(find(listing_id), []).append(listing_id)

    edge_lookup: dict[tuple[uuid.UUID, uuid.UUID], ClusterEdge] = {
        tuple(sorted((edge.left_listing_id, edge.right_listing_id), key=str)): edge
        for edge in edges
    }

    results: list[ListingClusterResult] = []
    ordered_buckets = sorted(
        buckets.values(),
        key=lambda ids: [str(value) for value in sorted(ids, key=str)],
    )
    for member_ids in ordered_buckets:
        ordered_ids = sorted(member_ids, key=str)
        cluster_key = _build_cluster_key(ordered_ids)
        members: list[ClusterMemberResult] = []
        for listing_id in ordered_ids:
            related_edges = [
                edge
                for other_id in ordered_ids
                if other_id != listing_id
                if (
                    edge := edge_lookup.get(tuple(sorted((listing_id, other_id), key=str)))
                )
                is not None
            ]
            if related_edges:
                confidence = max(edge.confidence for edge in related_edges)
                reasons = sorted({reason for edge in related_edges for reason in edge.reasons})
            else:
                confidence = 1.0
                reasons = ["singleton"]
            members.append(
                ClusterMemberResult(
                    listing_item_id=listing_id,
                    confidence=round(confidence, 3),
                    reasons=reasons,
                )
            )

        results.append(
            ListingClusterResult(
                cluster_id=uuid.uuid5(CLUSTER_NAMESPACE, cluster_key),
                cluster_key=cluster_key,
                cluster_status=(
                    ListingClusterStatus.SINGLETON
                    if len(ordered_ids) == 1
                    else ListingClusterStatus.ACTIVE
                ),
                members=members,
            )
        )

    return results


def generate_cluster_edges(listings: list[ClusterListingInput]) -> list[ClusterEdge]:
    edges: list[ClusterEdge] = []
    ordered_listings = sorted(listings, key=lambda listing: str(listing.listing_item_id))
    for left, right in combinations(ordered_listings, 2):
        edge = _compare_pair(left, right)
        if edge is not None:
            edges.append(edge)
    return edges


def _compare_pair(left: ClusterListingInput, right: ClusterListingInput) -> ClusterEdge | None:
    reasons: list[str] = []
    confidence = 0.0

    if left.canonical_url and left.canonical_url == right.canonical_url:
        confidence = 1.0
        reasons.append("canonical_url_exact")

    shared_hashes = sorted(set(left.document_hashes).intersection(right.document_hashes))
    if shared_hashes:
        confidence = max(confidence, 0.98)
        reasons.append("document_hash_exact")

    headline_similarity = _headline_similarity(left.headline, right.headline)
    prices_close = _prices_close(left.guide_price_gbp, right.guide_price_gbp)
    coordinates_close = _coordinates_close(left.lat, left.lon, right.lat, right.lon)

    if left.normalized_address and left.normalized_address == right.normalized_address:
        score = 0.72
        reasons.append("normalized_address_exact")
        if headline_similarity >= 0.75:
            score += 0.12
            reasons.append("headline_similarity")
        if prices_close:
            score += 0.1
            reasons.append("guide_price_close")
        if coordinates_close or _coordinate_missing_pair(left, right):
            score += 0.08
            reasons.append("coordinates_consistent")
        confidence = max(confidence, score)

    if confidence < 0.82 and coordinates_close and headline_similarity >= 0.85:
        confidence = max(confidence, 0.84)
        reasons.extend(["coordinates_close", "headline_similarity"])

    if confidence < 0.82:
        return None

    return ClusterEdge(
        left_listing_id=left.listing_item_id,
        right_listing_id=right.listing_item_id,
        confidence=round(min(confidence, 0.995), 3),
        reasons=sorted(set(reasons)),
    )


def _build_cluster_key(member_ids: list[uuid.UUID]) -> str:
    payload = "|".join(str(member_id) for member_id in member_ids)
    digest = hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"listing-cluster:{digest}"


def _headline_similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]


def _prices_close(left: int | None, right: int | None) -> bool:
    if left is None or right is None:
        return False
    baseline = max(left, right)
    return abs(left - right) / baseline <= 0.05


def _coordinates_close(
    left_lat: float | None,
    left_lon: float | None,
    right_lat: float | None,
    right_lon: float | None,
) -> bool:
    if None in {left_lat, left_lon, right_lat, right_lon}:
        return False
    return _haversine_meters(left_lat, left_lon, right_lat, right_lon) <= 75


def _coordinate_missing_pair(left: ClusterListingInput, right: ClusterListingInput) -> bool:
    return (
        (left.lat is None and left.lon is None)
        or (right.lat is None and right.lon is None)
    )


def _haversine_meters(
    left_lat: float,
    left_lon: float,
    right_lat: float,
    right_lon: float,
) -> float:
    radius_m = 6_371_000
    phi1 = math.radians(left_lat)
    phi2 = math.radians(right_lat)
    delta_phi = math.radians(right_lat - left_lat)
    delta_lambda = math.radians(right_lon - left_lon)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c
