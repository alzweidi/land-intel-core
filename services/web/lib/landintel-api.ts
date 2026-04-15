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
