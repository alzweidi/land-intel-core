import {
  getPhase1AClusterById,
  getPhase1AListingById,
  phase1AListings,
  phase1ARuns,
  phase1ASources,
  type Phase1AClusterDetail,
  type Phase1AClusterSummary,
  type Phase1ADocument,
  type Phase1AListingDetail,
  type Phase1AListingSnapshot,
  type Phase1AListingSummary,
  type Phase1ARunRecord,
  type Phase1ASource
} from '@/lib/phase1a-data';
import {
  applyLocalSiteGeometry,
  getPhase2SiteById,
  phase2SiteSummaries
} from '@/lib/phase2-data';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
const REQUEST_TIMEOUT_MS = 2500;

type QueryValue = string | number | boolean | null | undefined;

type ListingsQuery = {
  q?: string;
  source?: string;
  status?: string;
  type?: string;
  cluster?: string;
};

export type GeometrySourceType =
  | 'SOURCE_POLYGON'
  | 'SOURCE_MAP_DIGITISED'
  | 'TITLE_UNION'
  | 'ANALYST_DRAWN'
  | 'APPROXIMATE_BBOX'
  | 'POINT_ONLY';

export type GeometryConfidence = 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT';

export type GeometryPolygon = {
  type: 'Polygon';
  coordinates: number[][][];
};

export type GeometryPoint = {
  type: 'Point';
  coordinates: [number, number];
};

export type GeometryMultiPolygon = {
  type: 'MultiPolygon';
  coordinates: number[][][][];
};

export type GeometryShape = GeometryPoint | GeometryPolygon | GeometryMultiPolygon;

export type GeometryFeature = {
  type: 'Feature';
  geometry: GeometryShape;
  properties: Record<string, unknown>;
};

export type SiteDocument = {
  id: string;
  label: string;
  doc_type: 'source_snapshot' | 'raw_asset' | 'html_snapshot' | 'brochure_pdf';
  href: string;
  asset_id: string | null;
  mime_type: string;
  extraction_status: string | null;
  note: string;
};

export type SiteTitleLink = {
  title_ref: string;
  title_number: string;
  address_text: string;
  overlap_sqm: number | null;
  overlap_pct: number | null;
  confidence: GeometryConfidence;
  is_primary: boolean;
  indicative_only: boolean;
  evidence_note: string;
};

export type SiteLpaLink = {
  lpa_code: string;
  lpa_name: string;
  overlap_sqm: number | null;
  overlap_pct: number | null;
  controlling: boolean;
  manual_clip_required: boolean;
  cross_lpa_flag: boolean;
  note: string;
};

export type SiteMarketEvent = {
  event_id: string;
  event_type: string;
  event_at: string;
  price_gbp: number | null;
  price_basis_type: string | null;
  note: string;
  source_listing_id: string | null;
};

export type SiteRevision = {
  revision_id: string;
  created_at: string;
  created_by: string;
  geom_source_type: GeometrySourceType;
  geom_confidence: GeometryConfidence;
  geom_hash: string;
  site_area_sqm: number | null;
  note: string;
  is_current: boolean;
  geometry_geojson_4326: GeometryFeature;
};

export type SiteSummary = {
  site_id: string;
  display_name: string;
  cluster_id: string;
  cluster_key: string;
  borough_name: string;
  controlling_lpa_name: string;
  geometry_source_type: GeometrySourceType;
  geometry_confidence: GeometryConfidence;
  site_area_sqm: number | null;
  current_listing_id: string;
  current_listing_headline: string;
  current_price_gbp: number | null;
  current_price_basis_type: string | null;
  warnings: string[];
  review_flags: string[];
  revision_count: number;
  document_count: number;
  title_link_count: number;
  lpa_link_count: number;
  geometry_geojson_4326: GeometryFeature;
  centroid_4326: {
    lat: number;
    lon: number;
  };
};

export type SiteDetail = SiteSummary & {
  address_text: string;
  summary: string;
  description_text: string;
  source_snapshot_id: string;
  source_snapshot_url: string | null;
  current_listing: {
    id: string;
    headline: string;
    source_key: string;
    canonical_url: string;
    latest_status: string;
    parse_status: string;
    price_display: string;
    observed_at: string;
  };
  revision_history: SiteRevision[];
  title_links: SiteTitleLink[];
  lpa_links: SiteLpaLink[];
  documents: SiteDocument[];
  market_events: SiteMarketEvent[];
  geometry_editor_guidance: string;
  last_updated_at: string;
};

export type SitesQuery = {
  q?: string;
  borough?: string;
  confidence?: GeometryConfidence | '';
  cluster?: string;
};

export type SiteGeometrySaveInput = {
  geometry_geojson_4326: GeometryFeature;
  geom_source_type: GeometrySourceType;
  geom_confidence: GeometryConfidence;
  revision_note?: string;
};

type ApiCollectionResponse<T> =
  | T[]
  | {
      items?: T[];
      results?: T[];
      data?: T[];
      listings?: T[];
      clusters?: T[];
      runs?: T[];
      sources?: T[];
    }
  | null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function pickCollection<T>(value: ApiCollectionResponse<T>): T[] {
  if (Array.isArray(value)) {
    return value;
  }

  if (!value || !isRecord(value)) {
    return [];
  }

  const maybeCollections = [
    value.items,
    value.results,
    value.data,
    value.listings,
    value.clusters,
    value.runs,
    value.sources
  ];

  for (const item of maybeCollections) {
    if (Array.isArray(item)) {
      return item as T[];
    }
  }

  return [];
}

function toStringValue(value: unknown, fallback = ''): string {
  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  return fallback;
}

function toNumberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function buildQueryString(params: Record<string, QueryValue>): string {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') {
      continue;
    }

    query.set(key, String(value));
  }

  const output = query.toString();
  return output ? `?${output}` : '';
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown | null> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        ...(init?.headers ?? {})
      },
      ...init,
      signal: controller.signal
    });

    if (!response.ok) {
      return null;
    }

    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('application/json')) {
      return null;
    }

    return (await response.json()) as unknown;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function mapListingSummary(value: unknown): Phase1AListingSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid listing summary');
  }

  return {
    id: toStringValue(value.id),
    source_id: toStringValue(value.source_id ?? value.sourceId),
    source_key: toStringValue(value.source_key ?? value.sourceKey),
    source_name: toStringValue(value.source_name ?? value.sourceName),
    source_listing_id: toStringValue(value.source_listing_id ?? value.sourceListingId),
    canonical_url: toStringValue(value.canonical_url ?? value.canonicalUrl),
    listing_type: toStringValue(value.listing_type ?? value.listingType, 'UNKNOWN'),
    headline: toStringValue(value.headline ?? value.title),
    borough: toStringValue(value.borough, 'Unknown'),
    latest_status: toStringValue(value.latest_status ?? value.status, 'UNKNOWN'),
    parse_status: (toStringValue(value.parse_status ?? value.parseStatus, 'PARTIAL') as Phase1AListingSummary['parse_status']),
    cluster_id: value.cluster_id === null || value.cluster_id === undefined ? null : toStringValue(value.cluster_id),
    cluster_key: value.cluster_key === null || value.cluster_key === undefined ? null : toStringValue(value.cluster_key),
    first_seen_at: toStringValue(value.first_seen_at ?? value.firstSeenAt),
    last_seen_at: toStringValue(value.last_seen_at ?? value.lastSeenAt),
    price_display: toStringValue(value.price_display ?? value.priceDisplay, 'No price recorded'),
    coverage_note: toStringValue(value.coverage_note ?? value.coverageNote, '')
  };
}

function getRecord(value: Record<string, unknown>, key: string): Record<string, unknown> | null {
  const candidate = value[key];
  return isRecord(candidate) ? candidate : null;
}

function mapSnapshot(value: unknown): Phase1AListingSnapshot {
  if (!isRecord(value)) {
    throw new Error('Invalid snapshot');
  }

  return {
    id: toStringValue(value.id),
    observed_at: toStringValue(value.observed_at ?? value.observedAt),
    headline: toStringValue(value.headline ?? value.title),
    description_text: toStringValue(value.description_text ?? value.descriptionText),
    guide_price_gbp: toStringValue(value.guide_price_gbp ?? value.guidePriceGbp),
    price_basis_type: toStringValue(value.price_basis_type ?? value.priceBasisType),
    status: toStringValue(value.status),
    auction_date: value.auction_date === null || value.auction_date === undefined ? null : toStringValue(value.auction_date),
    address_text: toStringValue(value.address_text ?? value.addressText),
    lat: toNumberValue(value.lat),
    lon: toNumberValue(value.lon),
    brochure_asset_id: value.brochure_asset_id === null || value.brochure_asset_id === undefined ? null : toStringValue(value.brochure_asset_id),
    map_asset_id: value.map_asset_id === null || value.map_asset_id === undefined ? null : toStringValue(value.map_asset_id),
    raw_record_json: isRecord(value.raw_record_json) ? value.raw_record_json : {}
  };
}

function mapDocument(value: unknown): Phase1ADocument {
  if (!isRecord(value)) {
    throw new Error('Invalid document');
  }

  return {
    id: toStringValue(value.id),
    doc_type: toStringValue(value.doc_type ?? value.docType, 'html_snapshot') as Phase1ADocument['doc_type'],
    filename: toStringValue(value.filename ?? value.name, 'asset'),
    page_count: value.page_count === null || value.page_count === undefined ? null : toNumberValue(value.page_count),
    extraction_status: (toStringValue(value.extraction_status ?? value.extractionStatus, 'PENDING') as Phase1ADocument['extraction_status']),
    extracted_text: value.extracted_text === null || value.extracted_text === undefined ? null : toStringValue(value.extracted_text),
    asset_id: toStringValue(value.asset_id ?? value.assetId)
  };
}

function mapClusterSummary(value: unknown): Phase1AClusterSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid cluster');
  }

  return {
    id: toStringValue(value.id),
    cluster_key: toStringValue(value.cluster_key ?? value.clusterKey),
    cluster_status: (toStringValue(value.cluster_status ?? value.clusterStatus, 'REVIEW') as Phase1AClusterSummary['cluster_status']),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    member_count: toNumberValue(value.member_count ?? value.memberCount) ?? 0,
    canonical_headline: toStringValue(value.canonical_headline ?? value.headline ?? value.title, 'Untitled cluster'),
    borough: toStringValue(value.borough, 'Unknown'),
    coverage_note: toStringValue(value.coverage_note ?? value.coverageNote, '')
  };
}

function mapRun(value: unknown): Phase1ARunRecord {
  if (!isRecord(value)) {
    throw new Error('Invalid run record');
  }

  return {
    id: toStringValue(value.id),
    source_key: toStringValue(value.source_key ?? value.sourceKey),
    source_name: toStringValue(value.source_name ?? value.sourceName),
    connector_type: toStringValue(value.connector_type ?? value.connectorType, 'manual_url') as Phase1ARunRecord['connector_type'],
    status: (toStringValue(value.status, 'QUEUED') as Phase1ARunRecord['status']),
    coverage_note: toStringValue(value.coverage_note ?? value.coverageNote, ''),
    parse_status: toStringValue(value.parse_status ?? value.parseStatus, 'PENDING'),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    updated_at: toStringValue(value.updated_at ?? value.updatedAt)
  };
}

async function queryApiCollection<T>(
  path: string,
  mapper: (value: unknown) => T
): Promise<{ items: T[]; apiAvailable: boolean }> {
  const payload = await requestJson(path);
  const items = pickCollection<T>(payload as ApiCollectionResponse<T>);
  return {
    items: items.map(mapper),
    apiAvailable: payload !== null
  };
}

function filterListings(items: Phase1AListingSummary[], query: ListingsQuery): Phase1AListingSummary[] {
  const normalizedQuery = query.q?.trim().toLowerCase();
  return items.filter((item) => {
    if (query.source && item.source_key !== query.source) {
      return false;
    }

    if (query.status && item.latest_status !== query.status) {
      return false;
    }

    if (query.type && item.listing_type !== query.type) {
      return false;
    }

    if (query.cluster && item.cluster_key !== query.cluster && item.cluster_id !== query.cluster) {
      return false;
    }

    if (!normalizedQuery) {
      return true;
    }

    const haystack = [
      item.headline,
      item.canonical_url,
      item.source_name,
      item.borough,
      item.coverage_note,
      item.source_listing_id
    ]
      .join(' ')
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });
}

export async function getListingSources(): Promise<{ items: Phase1ASource[]; apiAvailable: boolean }> {
  const fallback = { items: phase1ASources, apiAvailable: false };
  const result = await queryApiCollection('/api/listings/sources', (value) => value as Phase1ASource);
  return result.items.length > 0 ? result : fallback;
}

export async function getListings(query: ListingsQuery = {}): Promise<{ items: Phase1AListingSummary[]; apiAvailable: boolean }> {
  const url = `/api/listings${buildQueryString(query)}`;
  const result = await queryApiCollection(url, mapListingSummary);
  const base = result.items.length > 0 ? result.items : phase1AListings;
  return {
    items: filterListings(base, query),
    apiAvailable: result.apiAvailable
  };
}

export async function getListing(listingId: string): Promise<{ item: Phase1AListingDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/listings/${encodeURIComponent(listingId)}`);
  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      const snapshots = pickCollection<Phase1AListingSnapshot>(record.snapshots as ApiCollectionResponse<Phase1AListingSnapshot>);
      const documents = pickCollection<Phase1ADocument>(record.documents as ApiCollectionResponse<Phase1ADocument>);
      const normalizedFields = getRecord(record, 'normalized_fields');
      const mappedListing = mapListingSummary(record);
      return {
        apiAvailable: true,
        item: {
          ...mappedListing,
          snapshots: snapshots.map(mapSnapshot),
          documents: documents.map(mapDocument),
          normalized_fields: {
            headline: toStringValue(normalizedFields?.headline ?? record.headline ?? record.title, mappedListing.headline),
            description_text: toStringValue(normalizedFields?.description_text ?? record.description_text ?? record.descriptionText),
            guide_price_gbp: toStringValue(normalizedFields?.guide_price_gbp ?? record.guide_price_gbp ?? ''),
            price_basis_type: toStringValue(normalizedFields?.price_basis_type ?? record.price_basis_type ?? 'UNKNOWN'),
            status: toStringValue(normalizedFields?.status ?? record.status ?? mappedListing.latest_status),
            auction_date:
              normalizedFields?.auction_date === null || normalizedFields?.auction_date === undefined
                ? null
                : toStringValue(normalizedFields?.auction_date),
            address_text: toStringValue(normalizedFields?.address_text ?? record.address_text ?? ''),
            lat: toNumberValue(normalizedFields?.lat ?? record.lat),
            lon: toNumberValue(normalizedFields?.lon ?? record.lon)
          },
          raw_record_json: isRecord(record.raw_record_json) ? record.raw_record_json : {}
        }
      };
    }
  }

  return {
    apiAvailable: false,
    item: getPhase1AListingById(listingId)
  };
}

export async function getClusters(): Promise<{ items: Phase1AClusterSummary[]; apiAvailable: boolean }> {
  const result = await queryApiCollection('/api/listing-clusters', mapClusterSummary);
  return {
    items: result.items.length > 0 ? result.items : phase1AClusters.map((cluster) => stripClusterMembers(cluster)),
    apiAvailable: result.apiAvailable
  };
}

const phase1AClusters: Phase1AClusterDetail[] = [
  getPhase1AClusterById('cluster-riverside-yard')!,
  getPhase1AClusterById('cluster-albion-street')!
];

function stripClusterMembers(cluster: Phase1AClusterDetail): Phase1AClusterSummary {
  const { members, ...summary } = cluster;
  void members;
  return summary;
}

export async function getCluster(clusterId: string): Promise<{ item: Phase1AClusterDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/listing-clusters/${encodeURIComponent(clusterId)}`);
  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      const cluster = mapClusterSummary(record);
      const members = pickCollection(record.members as ApiCollectionResponse<unknown>).map((member) => {
        if (!isRecord(member)) {
          throw new Error('Invalid cluster member');
        }

        return {
          id: toStringValue(member.id),
          listing_item_id: toStringValue(member.listing_item_id ?? member.listingItemId),
          listing_headline: toStringValue(member.listing_headline ?? member.listingHeadline),
          source_name: toStringValue(member.source_name ?? member.sourceName),
          canonical_url: toStringValue(member.canonical_url ?? member.canonicalUrl),
          confidence: toNumberValue(member.confidence) ?? 0,
          latest_status: toStringValue(member.latest_status ?? member.latestStatus),
          created_at: toStringValue(member.created_at ?? member.createdAt)
        };
      });

      return {
        apiAvailable: true,
        item: {
          ...cluster,
          members
        }
      };
    }
  }

  return {
    apiAvailable: false,
    item: getPhase1AClusterById(clusterId)
  };
}

export async function getSourceRuns(): Promise<{ items: Phase1ARunRecord[]; apiAvailable: boolean }> {
  const result = await queryApiCollection('/api/listings/runs', mapRun);
  return {
    items: result.items.length > 0 ? result.items : phase1ARuns,
    apiAvailable: result.apiAvailable
  };
}

export async function runManualUrlIntake(input: { url: string; coverage_note?: string }): Promise<unknown | null> {
  return requestJson('/api/listings/intake/url', {
    body: JSON.stringify({
      url: input.url,
      coverage_note: input.coverage_note
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
}

export async function runCsvImport(input: { file?: File | null; csv_text?: string; coverage_note?: string }): Promise<unknown | null> {
  if (input.file) {
    const formData = new FormData();
    formData.set('file', input.file);
    if (input.coverage_note) {
      formData.set('coverage_note', input.coverage_note);
    }
    return requestJson('/api/listings/import/csv', {
      body: formData,
      method: 'POST'
    });
  }

  return requestJson('/api/listings/import/csv', {
    body: JSON.stringify({
      csv_text: input.csv_text ?? '',
      coverage_note: input.coverage_note
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
}

export async function runConnector(sourceKey: string, input: { coverage_note?: string }): Promise<unknown | null> {
  return requestJson(`/api/listings/connectors/${encodeURIComponent(sourceKey)}/run`, {
    body: JSON.stringify({
      coverage_note: input.coverage_note
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
}

function mapSiteDocument(value: unknown): SiteDocument {
  if (!isRecord(value)) {
    throw new Error('Invalid site document');
  }

  const asset = getRecord(value, 'asset');
  const assetUrl = toStringValue(asset?.original_url ?? asset?.storage_path, '#');
  const mimeType = toStringValue(asset?.mime_type ?? value.mime_type, 'application/octet-stream');
  return {
    id: toStringValue(value.id),
    label: toStringValue(value.label ?? value.filename ?? value.title ?? value.doc_type, 'Document'),
    doc_type: (
      toStringValue(value.doc_type ?? value.docType, 'raw_asset') === 'BROCHURE'
        ? 'brochure_pdf'
        : toStringValue(value.doc_type ?? value.docType, 'raw_asset') === 'MAP'
          ? 'raw_asset'
          : 'html_snapshot'
    ) as SiteDocument['doc_type'],
    href: toStringValue(value.href ?? value.url, assetUrl),
    asset_id:
      value.asset_id === null || value.asset_id === undefined
        ? null
        : toStringValue(value.asset_id),
    mime_type: mimeType,
    extraction_status: value.extraction_status === null || value.extraction_status === undefined
      ? null
      : toStringValue(value.extraction_status),
    note: toStringValue(value.note ?? asset?.storage_path ?? '', '')
  };
}

function mapLpaLink(value: unknown): SiteLpaLink {
  if (!isRecord(value)) {
    throw new Error('Invalid LPA link');
  }

  return {
    lpa_code: toStringValue(value.lpa_code ?? value.lpaCode ?? value.lpa_id),
    lpa_name: toStringValue(value.lpa_name ?? value.lpaName),
    overlap_sqm: toNumberValue(value.overlap_sqm ?? value.overlapSqm),
    overlap_pct: toNumberValue(value.overlap_pct ?? value.overlapPct),
    controlling: Boolean(value.controlling ?? value.is_controlling ?? value.is_primary ?? false),
    manual_clip_required: Boolean(
      value.manual_clip_required ?? value.manualClipRequired ?? false
    ),
    cross_lpa_flag: Boolean(value.cross_lpa_flag ?? value.crossLpaFlag ?? false),
    note: toStringValue(value.note ?? '', '')
  };
}

function mapTitleLink(value: unknown): SiteTitleLink {
  if (!isRecord(value)) {
    throw new Error('Invalid title link');
  }

  return {
    title_ref: toStringValue(value.title_ref ?? value.titleRef ?? value.title_number ?? value.titleNumber),
    title_number: toStringValue(value.title_number ?? value.titleNumber),
    address_text: toStringValue(value.address_text ?? value.addressText, ''),
    overlap_sqm: toNumberValue(value.overlap_sqm ?? value.overlapSqm),
    overlap_pct: toNumberValue(value.overlap_pct ?? value.overlapPct),
    confidence: toStringValue(value.confidence, 'LOW') as SiteTitleLink['confidence'],
    is_primary: Boolean(value.is_primary ?? value.isPrimary ?? false),
    indicative_only: Boolean(value.indicative_only ?? value.indicativeOnly ?? true),
    evidence_note: toStringValue(
      value.evidence_note ?? value.evidenceNote,
      'Indicative HMLR INSPIRE title overlap only.'
    )
  };
}

function mapMarketEvent(value: unknown): SiteMarketEvent {
  if (!isRecord(value)) {
    throw new Error('Invalid site market event');
  }

  return {
    event_id: toStringValue(value.event_id ?? value.eventId),
    event_type: toStringValue(value.event_type ?? value.eventType, 'SITE_CREATED'),
    event_at: toStringValue(value.event_at ?? value.eventAt),
    price_gbp: value.price_gbp === null || value.price_gbp === undefined ? null : toNumberValue(value.price_gbp),
    price_basis_type:
      value.price_basis_type === null || value.price_basis_type === undefined
        ? null
        : toStringValue(value.price_basis_type),
    note: toStringValue(value.note ?? '', ''),
    source_listing_id:
      value.source_listing_id === null || value.source_listing_id === undefined
        ? null
        : toStringValue(value.source_listing_id)
  };
}

function mapGeometryFeature(value: unknown): GeometryFeature {
  if (!isRecord(value)) {
    throw new Error('Invalid geometry feature');
  }

  const geometry = isRecord(value.geometry) ? value.geometry : value;
  if (!geometry) {
    throw new Error('Missing geometry');
  }

  const geometryType = toStringValue(geometry.type);
  if (geometryType === 'Point') {
    return {
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: Array.isArray(geometry.coordinates)
          ? (geometry.coordinates as [number, number])
          : [0, 0]
      },
      properties: isRecord(value.properties) ? value.properties : {}
    };
  }

  if (geometryType === 'MultiPolygon') {
    return {
      type: 'Feature',
      geometry: {
        type: 'MultiPolygon',
        coordinates: Array.isArray(geometry.coordinates) ? (geometry.coordinates as number[][][][]) : []
      },
      properties: isRecord(value.properties) ? value.properties : {}
    };
  }

  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: Array.isArray(geometry.coordinates) ? (geometry.coordinates as number[][][]) : []
    },
    properties: isRecord(value.properties) ? value.properties : {}
  };
}

function mapSiteSummary(value: unknown): SiteSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid site summary');
  }

  const currentGeometry = getRecord(value, 'current_geometry');
  const featurePayload =
    value.geometry_geojson_4326 ??
    currentGeometry?.geom_4326 ??
    currentGeometry?.geometry_geojson_4326;
  const feature = isRecord(featurePayload) ? mapGeometryFeature(featurePayload) : null;
  const warnings = extractWarningMessages(value.warnings);
  const reviewFlags = extractReviewFlags(value, warnings);
  const geometrySourceType = toStringValue(
    value.geometry_source_type ?? value.geometrySourceType ?? currentGeometry?.geom_source_type,
    'POINT_ONLY'
  ) as SiteSummary['geometry_source_type'];
  const geometryConfidence = toStringValue(
    value.geometry_confidence ?? value.geometryConfidence ?? currentGeometry?.geom_confidence,
    'INSUFFICIENT'
  ) as SiteSummary['geometry_confidence'];
  const currentListing = getRecord(value, 'current_listing');
  const listingCluster = getRecord(value, 'listing_cluster');
  const siteArea = toNumberValue(
    value.site_area_sqm ?? value.siteAreaSqm ?? currentGeometry?.site_area_sqm
  );
  const centroid = feature ? centroidFromFeature(feature) : { lat: 0, lon: 0 };

  return {
    site_id: toStringValue(value.site_id ?? value.siteId ?? value.id),
    display_name: toStringValue(value.display_name ?? value.displayName, 'Untitled site'),
    cluster_id: toStringValue(
      value.cluster_id ?? value.clusterId ?? listingCluster?.id,
      ''
    ),
    cluster_key: toStringValue(
      value.cluster_key ?? value.clusterKey ?? listingCluster?.cluster_key,
      ''
    ),
    borough_name: toStringValue(value.borough_name ?? value.boroughName, 'Unknown'),
    controlling_lpa_name: toStringValue(
      value.controlling_lpa_name ??
        value.controllingLpaName ??
        value.borough_name ??
        value.boroughName,
      'Unknown'
    ),
    geometry_source_type: geometrySourceType,
    geometry_confidence: geometryConfidence,
    site_area_sqm: siteArea,
    current_listing_id: toStringValue(
      value.current_listing_id ?? value.currentListingId ?? currentListing?.id,
      ''
    ),
    current_listing_headline: toStringValue(
      value.current_listing_headline ??
        value.currentListingHeadline ??
        currentListing?.headline,
      ''
    ),
    current_price_gbp:
      value.current_price_gbp === null || value.current_price_gbp === undefined
        ? toNumberValue(currentListing?.guide_price_gbp)
        : toNumberValue(value.current_price_gbp),
    current_price_basis_type:
      value.current_price_basis_type === null || value.current_price_basis_type === undefined
        ? toStringValue(currentListing?.price_basis_type, '')
        : toStringValue(value.current_price_basis_type),
    warnings,
    review_flags: reviewFlags,
    revision_count: toNumberValue(value.revision_count ?? value.revisionCount) ?? 0,
    document_count: toNumberValue(value.document_count ?? value.documentCount) ?? 0,
    title_link_count: toNumberValue(value.title_link_count ?? value.titleLinkCount) ?? 0,
    lpa_link_count: toNumberValue(value.lpa_link_count ?? value.lpaLinkCount) ?? 0,
    geometry_geojson_4326:
      feature ?? {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [0, 0] },
        properties: {}
      },
    centroid_4326: isRecord(value.centroid_4326)
      ? {
          lat: toNumberValue(value.centroid_4326.lat) ?? centroid.lat,
          lon: toNumberValue(value.centroid_4326.lon) ?? centroid.lon
        }
      : centroid
  };
}

function mapSiteDetail(value: unknown): SiteDetail {
  if (!isRecord(value)) {
    throw new Error('Invalid site detail');
  }

  const summary = mapSiteSummary(value);
  const currentListing = getRecord(value, 'current_listing');
  const revisions = pickCollection(
    (value.geometry_revisions ?? value.revision_history) as ApiCollectionResponse<unknown>
  ).map((revision, index) => mapGeometryRevision(revision, summary.geometry_geojson_4326, summary, index));
  const sourceSnapshots = pickCollection(
    value.source_snapshots as ApiCollectionResponse<unknown>
  );
  const sourceSnapshot = isRecord(sourceSnapshots[0]) ? sourceSnapshots[0] : null;
  const documents = pickCollection(
    (value.source_documents ?? value.documents) as ApiCollectionResponse<unknown>
  ).map(mapSiteDocument);
  const titleLinks = pickCollection(value.title_links as ApiCollectionResponse<unknown>).map(
    (link, index) => mapTitleLinkWithContext(link, index)
  );
  const lpaLinksRaw = pickCollection(value.lpa_links as ApiCollectionResponse<unknown>);
  const materialCrossLpa = summary.review_flags.includes('CROSS_LPA_MATERIAL');

  return {
    ...summary,
    address_text: toStringValue(
      value.address_text ?? value.addressText ?? currentListing?.address_text,
      ''
    ),
    summary: toStringValue(
      value.summary,
      summary.site_area_sqm === null
        ? `${summary.display_name} · area pending`
        : `${summary.display_name} · ${summary.site_area_sqm.toLocaleString('en-GB')} sqm`
    ),
    description_text: toStringValue(value.description_text ?? value.descriptionText, ''),
    source_snapshot_id: toStringValue(
      value.source_snapshot_id ?? value.sourceSnapshotId ?? sourceSnapshot?.id,
      ''
    ),
    source_snapshot_url: sourceSnapshot
      ? toStringValue(sourceSnapshot.source_uri)
      : null,
    current_listing: currentListing
      ? {
        id: toStringValue(currentListing.id),
        headline: toStringValue(currentListing.headline ?? currentListing.title, ''),
        source_key: toStringValue(
          currentListing.source_key ?? currentListing.sourceKey ?? currentListing.source_name,
          ''
        ),
        canonical_url: toStringValue(currentListing.canonical_url ?? currentListing.canonicalUrl, ''),
        latest_status: toStringValue(currentListing.latest_status ?? currentListing.status, ''),
        parse_status: toStringValue(
          currentListing.parse_status ?? currentListing.parseStatus,
          'PARSED'
        ),
        price_display: formatPriceDisplay(
          toNumberValue(currentListing.guide_price_gbp),
          toStringValue(currentListing.price_basis_type)
        ),
        observed_at: toStringValue(
          currentListing.observed_at ?? currentListing.observedAt ?? sourceSnapshot?.acquired_at,
          ''
        )
      }
      : {
          id: '',
          headline: '',
          source_key: '',
          canonical_url: '',
          latest_status: '',
          parse_status: '',
          price_display: '',
          observed_at: ''
        },
    revision_history: revisions,
    title_links: titleLinks,
    lpa_links: lpaLinksRaw.map((link) =>
      mapLpaLinkWithContext(link, materialCrossLpa, lpaLinksRaw.length > 1)
    ),
    documents,
    market_events: pickCollection(value.market_events as ApiCollectionResponse<unknown>).map(mapMarketEvent),
    geometry_editor_guidance: toStringValue(
      value.geometry_editor_guidance ?? value.geometryEditorGuidance,
      'Draw conservatively, save explicit revisions, and treat indicative geometry as evidence only.'
    ),
    last_updated_at: toStringValue(
      value.last_updated_at ?? value.lastUpdatedAt ?? revisions[0]?.created_at,
      ''
    )
  };
}

function mapGeometryRevision(
  value: unknown,
  currentGeometry: GeometryFeature,
  summary: SiteSummary,
  index: number
): SiteDetail['revision_history'][number] {
  if (!isRecord(value)) {
    throw new Error('Invalid geometry revision');
  }

  const geometryPayload = value.geom_4326 ?? value.geometry_geojson_4326 ?? currentGeometry;
  return {
    revision_id: toStringValue(value.revision_id ?? value.revisionId ?? value.id),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    created_by: toStringValue(value.created_by ?? value.createdBy, ''),
    geom_source_type: toStringValue(
      value.geom_source_type ?? value.geomSourceType ?? value.source_type,
      summary.geometry_source_type
    ) as SiteDetail['revision_history'][number]['geom_source_type'],
    geom_confidence: toStringValue(
      value.geom_confidence ?? value.geomConfidence ?? value.confidence,
      summary.geometry_confidence
    ) as SiteDetail['revision_history'][number]['geom_confidence'],
    geom_hash: toStringValue(value.geom_hash ?? value.geomHash, ''),
    site_area_sqm:
      value.site_area_sqm === null || value.site_area_sqm === undefined
        ? toNumberValue(summary.site_area_sqm)
        : toNumberValue(value.site_area_sqm),
    note: toStringValue(value.note ?? value.reason ?? '', ''),
    is_current: Boolean(value.is_current ?? value.isCurrent ?? index === 0),
    geometry_geojson_4326: mapGeometryFeature(geometryPayload)
  };
}

function mapTitleLinkWithContext(value: unknown, index: number): SiteTitleLink {
  const mapped = mapTitleLink(value);
  return {
    ...mapped,
    is_primary: mapped.is_primary || index === 0
  };
}

function mapLpaLinkWithContext(
  value: unknown,
  materialCrossLpa: boolean,
  crossLpaFlag: boolean
): SiteLpaLink {
  const mapped = mapLpaLink(value);
  return {
    ...mapped,
    controlling: mapped.controlling,
    manual_clip_required: mapped.manual_clip_required || materialCrossLpa,
    cross_lpa_flag: mapped.cross_lpa_flag || crossLpaFlag,
    note:
      mapped.note ||
      (materialCrossLpa
        ? 'Material cross-LPA overlap requires manual clipping or analyst confirmation.'
        : crossLpaFlag
          ? 'Cross-LPA overlap is present but not currently material.'
          : 'Controlling borough assignment.')
  };
}

function extractWarningMessages(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((warning) => {
      if (isRecord(warning)) {
        return toStringValue(warning.message ?? warning.code);
      }
      return toStringValue(warning);
    })
    .filter((warning) => warning.length > 0);
}

function extractWarningCodes(record: Record<string, unknown>): string[] {
  const warningItems = Array.isArray(record.warnings) ? record.warnings : [];
  return warningItems
    .map((warning) => (isRecord(warning) ? toStringValue(warning.code) : ''))
    .filter((warning) => warning.length > 0);
}

function extractReviewFlags(record: Record<string, unknown>, warnings: string[]): string[] {
  const flags = new Set<string>();
  if (Boolean(record.manual_review_required)) {
    flags.add('MANUAL_REVIEW_REQUIRED');
  }

  for (const code of extractWarningCodes(record)) {
    flags.add(code);
  }

  if (warnings.length === 0 && flags.size === 0 && toStringValue(record.site_status) === 'ACTIVE') {
    return [];
  }

  return Array.from(flags);
}

function centroidFromFeature(feature: GeometryFeature): { lat: number; lon: number } {
  const geometry = feature.geometry;
  if (geometry.type === 'Point') {
    return { lon: geometry.coordinates[0], lat: geometry.coordinates[1] };
  }

  const points =
    geometry.type === 'Polygon'
      ? geometry.coordinates.flat()
      : geometry.coordinates.flatMap((polygon) => polygon.flat());
  if (points.length === 0) {
    return { lat: 0, lon: 0 };
  }

  const [lonSum, latSum] = points.reduce<[number, number]>(
    (acc, point) => [acc[0] + point[0], acc[1] + point[1]],
    [0, 0]
  );
  return { lon: lonSum / points.length, lat: latSum / points.length };
}

function formatPriceDisplay(price: number | null, basisType: string): string {
  if (price === null) {
    return 'Price pending';
  }
  const formatted = `£${price.toLocaleString('en-GB')}`;
  return basisType ? `${basisType} · ${formatted}` : formatted;
}

function filterSites(items: SiteSummary[], query: SitesQuery): SiteSummary[] {
  const normalizedQuery = query.q?.trim().toLowerCase();

  return items.filter((item) => {
    if (query.borough && item.borough_name !== query.borough) {
      return false;
    }

    if (query.confidence && item.geometry_confidence !== query.confidence) {
      return false;
    }

    if (query.cluster && item.cluster_id !== query.cluster && item.cluster_key !== query.cluster) {
      return false;
    }

    if (!normalizedQuery) {
      return true;
    }

    const haystack = [
      item.display_name,
      item.borough_name,
      item.controlling_lpa_name,
      item.cluster_key,
      item.current_listing_headline,
      item.current_listing_id,
      item.warnings.join(' '),
      item.review_flags.join(' ')
    ]
      .join(' ')
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });
}

export async function getSites(query: SitesQuery = {}): Promise<{ items: SiteSummary[]; apiAvailable: boolean }> {
  const result = await queryApiCollection(`/api/sites${buildQueryString(query)}`, mapSiteSummary);
  const base = result.items.length > 0 ? result.items : phase2SiteSummaries;
  return {
    items: filterSites(base, query),
    apiAvailable: result.apiAvailable
  };
}

export async function getSite(siteId: string): Promise<{ item: SiteDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/sites/${encodeURIComponent(siteId)}`);
  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      return {
        apiAvailable: true,
        item: mapSiteDetail(record)
      };
    }
  }

  return {
    apiAvailable: false,
    item: getPhase2SiteById(siteId)
  };
}

export async function saveSiteGeometry(
  siteId: string,
  input: SiteGeometrySaveInput
): Promise<{ item: SiteDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/sites/${encodeURIComponent(siteId)}/geometry`, {
    body: JSON.stringify({
      geom_4326: input.geometry_geojson_4326.geometry,
      source_type: input.geom_source_type,
      confidence: input.geom_confidence,
      reason: input.revision_note,
      created_by: 'web-ui'
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      return {
        apiAvailable: true,
        item: mapSiteDetail(record)
      };
    }
  }

  return {
    apiAvailable: false,
    item: applyLocalSiteGeometry(siteId, input)
  };
}
