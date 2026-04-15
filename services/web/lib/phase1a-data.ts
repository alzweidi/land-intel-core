export type ListingComplianceMode = 'BLOCKED' | 'MANUAL_ONLY' | 'COMPLIANT_AUTOMATED';

export type Phase1ASource = {
  id: string;
  source_key: string;
  name: string;
  connector_type: 'manual_url' | 'csv_import' | 'public_page';
  compliance_mode: ListingComplianceMode;
  active: boolean;
  refresh_policy: string;
  coverage_note: string;
};

export type Phase1AListingSnapshot = {
  id: string;
  observed_at: string;
  headline: string;
  description_text: string;
  guide_price_gbp: string;
  price_basis_type: string;
  status: string;
  auction_date: string | null;
  address_text: string;
  lat: number | null;
  lon: number | null;
  brochure_asset_id: string | null;
  map_asset_id: string | null;
  raw_record_json: Record<string, unknown>;
};

export type Phase1ADocument = {
  id: string;
  doc_type: 'brochure_pdf' | 'html_snapshot' | 'map_image';
  filename: string;
  page_count: number | null;
  extraction_status: 'PENDING' | 'EXTRACTED' | 'FAILED';
  extracted_text: string | null;
  asset_id: string;
};

export type Phase1AListingSummary = {
  id: string;
  source_id: string;
  source_key: string;
  source_name: string;
  source_listing_id: string;
  canonical_url: string;
  listing_type: string;
  headline: string;
  borough: string;
  latest_status: string;
  parse_status: 'PARSED' | 'PARTIAL' | 'FAILED';
  cluster_id: string | null;
  cluster_key: string | null;
  first_seen_at: string;
  last_seen_at: string;
  price_display: string;
  coverage_note: string;
};

export type Phase1AListingDetail = Phase1AListingSummary & {
  snapshots: Phase1AListingSnapshot[];
  documents: Phase1ADocument[];
  normalized_fields: {
    headline: string;
    description_text: string;
    guide_price_gbp: string;
    price_basis_type: string;
    status: string;
    auction_date: string | null;
    address_text: string;
    lat: number | null;
    lon: number | null;
  };
  raw_record_json: Record<string, unknown>;
};

export type Phase1AClusterMember = {
  id: string;
  listing_item_id: string;
  listing_headline: string;
  source_name: string;
  canonical_url: string;
  confidence: number;
  latest_status: string;
  created_at: string;
};

export type Phase1AClusterSummary = {
  id: string;
  cluster_key: string;
  cluster_status: 'ACTIVE' | 'REVIEW' | 'ARCHIVED';
  created_at: string;
  member_count: number;
  canonical_headline: string;
  borough: string;
  coverage_note: string;
};

export type Phase1AClusterDetail = Phase1AClusterSummary & {
  members: Phase1AClusterMember[];
};

export type Phase1ARunRecord = {
  id: string;
  source_key: string;
  source_name: string;
  connector_type: Phase1ASource['connector_type'];
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  coverage_note: string;
  parse_status: string;
  created_at: string;
  updated_at: string;
};

export const phase1ASources: Phase1ASource[] = [
  {
    id: 'source-manual',
    source_key: 'manual_url',
    name: 'Manual URL intake',
    connector_type: 'manual_url',
    compliance_mode: 'MANUAL_ONLY',
    active: true,
    refresh_policy: 'Analyst-triggered only',
    coverage_note: 'Always allowed for analyst-pasted URLs'
  },
  {
    id: 'source-broker-drop',
    source_key: 'broker_drop',
    name: 'CSV / broker drop',
    connector_type: 'csv_import',
    compliance_mode: 'MANUAL_ONLY',
    active: true,
    refresh_policy: 'Manual import only',
    coverage_note: 'Approved for internal CSV and email broker drops'
  },
  {
    id: 'source-approved-public',
    source_key: 'approved_public_page',
    name: 'Approved public-page connector',
    connector_type: 'public_page',
    compliance_mode: 'COMPLIANT_AUTOMATED',
    active: true,
    refresh_policy: '6-hour refresh',
    coverage_note: 'Approved after compliance review'
  },
  {
    id: 'source-blocked-public',
    source_key: 'blocked_public_page',
    name: 'Unapproved public-page connector',
    connector_type: 'public_page',
    compliance_mode: 'BLOCKED',
    active: false,
    refresh_policy: 'Blocked pending review',
    coverage_note: 'Must remain blocked until approved'
  }
];

const sampleListingItems: Phase1AListingSummary[] = [
  {
    id: 'listing-manual-001',
    source_id: 'source-manual',
    source_key: 'manual_url',
    source_name: 'Manual URL intake',
    source_listing_id: 'https://example.com/listings/land-at-riverside-yard',
    canonical_url: 'https://example.com/listings/land-at-riverside-yard',
    listing_type: 'LAND',
    headline: 'Land at Riverside Yard',
    borough: 'Hackney',
    latest_status: 'LIVE',
    parse_status: 'PARSED',
    cluster_id: 'cluster-riverside-yard',
    cluster_key: 'riverside-yard',
    first_seen_at: '2026-04-15T08:12:00Z',
    last_seen_at: '2026-04-15T08:12:00Z',
    price_display: 'Guide price: GBP 1,250,000',
    coverage_note: 'Manual URL snapshot preserved'
  },
  {
    id: 'listing-public-001',
    source_id: 'source-approved-public',
    source_key: 'approved_public_page',
    source_name: 'Approved public-page connector',
    source_listing_id: 'APT-9917',
    canonical_url: 'https://land.example.org/opportunities/apt-9917',
    listing_type: 'LAND',
    headline: 'Riverside Yard, rear access plot',
    borough: 'Hackney',
    latest_status: 'LIVE',
    parse_status: 'PARSED',
    cluster_id: 'cluster-riverside-yard',
    cluster_key: 'riverside-yard',
    first_seen_at: '2026-04-15T09:00:00Z',
    last_seen_at: '2026-04-15T09:00:00Z',
    price_display: 'Guide price: GBP 1,250,000',
    coverage_note: 'Approved public page with brochure snapshot'
  },
  {
    id: 'listing-csv-001',
    source_id: 'source-broker-drop',
    source_key: 'broker_drop',
    source_name: 'CSV / broker drop',
    source_listing_id: 'broker-drop-17',
    canonical_url: 'https://broker.example.invalid/rows/17',
    listing_type: 'LAND',
    headline: 'Rear Yard off Albion Street',
    borough: 'Lambeth',
    latest_status: 'LIVE',
    parse_status: 'PARTIAL',
    cluster_id: 'cluster-albion-street',
    cluster_key: 'albion-street',
    first_seen_at: '2026-04-14T16:30:00Z',
    last_seen_at: '2026-04-15T07:45:00Z',
    price_display: 'Guide price: GBP 875,000',
    coverage_note: 'CSV import from broker drop'
  },
  {
    id: 'listing-public-002',
    source_id: 'source-approved-public',
    source_key: 'approved_public_page',
    source_name: 'Approved public-page connector',
    source_listing_id: 'PORTAL-4421',
    canonical_url: 'https://land.example.org/opportunities/portal-4421',
    listing_type: 'AUCTION',
    headline: 'Albion Street yard lot',
    borough: 'Lambeth',
    latest_status: 'UNDER OFFER',
    parse_status: 'PARSED',
    cluster_id: 'cluster-albion-street',
    cluster_key: 'albion-street',
    first_seen_at: '2026-04-14T17:10:00Z',
    last_seen_at: '2026-04-15T08:00:00Z',
    price_display: 'Guide price: GBP 875,000',
    coverage_note: 'Approved public page mirrors broker drop'
  }
];

const sampleSnapshotsByListingId: Record<string, Phase1AListingSnapshot[]> = {
  'listing-manual-001': [
    {
      id: 'snapshot-manual-001',
      observed_at: '2026-04-15T08:12:00Z',
      headline: 'Land at Riverside Yard',
      description_text:
        'Shallow commercial yard with visible access from the street and no planning claims inferred.',
      guide_price_gbp: '1250000',
      price_basis_type: 'GUIDE_PRICE',
      status: 'LIVE',
      auction_date: null,
      address_text: 'Riverside Yard, Hackney',
      lat: 51.545,
      lon: -0.058,
      brochure_asset_id: 'asset-brochure-manual-001',
      map_asset_id: 'asset-map-manual-001',
      raw_record_json: {
        source_kind: 'manual_url',
        compliance_mode: 'MANUAL_ONLY',
        canonical_url: 'https://example.com/listings/land-at-riverside-yard'
      }
    }
  ],
  'listing-public-001': [
    {
      id: 'snapshot-public-001',
      observed_at: '2026-04-15T09:00:00Z',
      headline: 'Riverside Yard, rear access plot',
      description_text:
        'Approved public-page listing with brochure and map references preserved in immutable assets.',
      guide_price_gbp: '1250000',
      price_basis_type: 'GUIDE_PRICE',
      status: 'LIVE',
      auction_date: null,
      address_text: 'Riverside Yard, Hackney',
      lat: 51.5451,
      lon: -0.0581,
      brochure_asset_id: 'asset-brochure-public-001',
      map_asset_id: 'asset-map-public-001',
      raw_record_json: {
        source_kind: 'public_page',
        compliance_mode: 'COMPLIANT_AUTOMATED',
        canonical_url: 'https://land.example.org/opportunities/apt-9917'
      }
    }
  ],
  'listing-csv-001': [
    {
      id: 'snapshot-csv-001',
      observed_at: '2026-04-14T16:30:00Z',
      headline: 'Rear Yard off Albion Street',
      description_text: 'Broker drop row imported from CSV with conservative parsing only.',
      guide_price_gbp: '875000',
      price_basis_type: 'GUIDE_PRICE',
      status: 'LIVE',
      auction_date: '2026-05-05',
      address_text: 'Albion Street rear yard, Lambeth',
      lat: 51.4738,
      lon: -0.1115,
      brochure_asset_id: 'asset-brochure-csv-001',
      map_asset_id: null,
      raw_record_json: {
        source_kind: 'csv_import',
        compliance_mode: 'MANUAL_ONLY',
        source_listing_id: 'broker-drop-17'
      }
    }
  ],
  'listing-public-002': [
    {
      id: 'snapshot-public-002',
      observed_at: '2026-04-15T08:00:00Z',
      headline: 'Albion Street yard lot',
      description_text: 'Public-page duplicate of the broker drop row, kept as a separate immutable snapshot.',
      guide_price_gbp: '875000',
      price_basis_type: 'GUIDE_PRICE',
      status: 'UNDER OFFER',
      auction_date: '2026-05-05',
      address_text: 'Albion Street rear yard, Lambeth',
      lat: 51.47375,
      lon: -0.1114,
      brochure_asset_id: 'asset-brochure-public-002',
      map_asset_id: null,
      raw_record_json: {
        source_kind: 'public_page',
        compliance_mode: 'COMPLIANT_AUTOMATED',
        source_listing_id: 'PORTAL-4421'
      }
    }
  ]
};

const sampleDocumentsByListingId: Record<string, Phase1ADocument[]> = {
  'listing-manual-001': [
    {
      id: 'document-manual-brochure',
      doc_type: 'brochure_pdf',
      filename: 'riverside-yard-brochure.pdf',
      page_count: 6,
      extraction_status: 'EXTRACTED',
      extracted_text: 'Riverside Yard brochure text extracted with PyMuPDF during connector run.',
      asset_id: 'asset-brochure-manual-001'
    },
    {
      id: 'document-manual-html',
      doc_type: 'html_snapshot',
      filename: 'riverside-yard.html',
      page_count: null,
      extraction_status: 'EXTRACTED',
      extracted_text: 'HTML snapshot text preserved for auditability.',
      asset_id: 'asset-html-manual-001'
    }
  ],
  'listing-public-001': [
    {
      id: 'document-public-brochure',
      doc_type: 'brochure_pdf',
      filename: 'riverside-yard-public.pdf',
      page_count: 8,
      extraction_status: 'EXTRACTED',
      extracted_text: 'Public page brochure extracted successfully.',
      asset_id: 'asset-brochure-public-001'
    },
    {
      id: 'document-public-map',
      doc_type: 'map_image',
      filename: 'riverside-yard-map.png',
      page_count: null,
      extraction_status: 'EXTRACTED',
      extracted_text: 'Map image preserved as an immutable asset.',
      asset_id: 'asset-map-public-001'
    }
  ],
  'listing-csv-001': [
    {
      id: 'document-csv-brochure',
      doc_type: 'brochure_pdf',
      filename: 'albion-street-broker-drop.pdf',
      page_count: 4,
      extraction_status: 'FAILED',
      extracted_text: null,
      asset_id: 'asset-brochure-csv-001'
    }
  ],
  'listing-public-002': [
    {
      id: 'document-public-002-brochure',
      doc_type: 'brochure_pdf',
      filename: 'albion-street-public.pdf',
      page_count: 4,
      extraction_status: 'EXTRACTED',
      extracted_text: 'Duplicate brochure text captured from approved public connector.',
      asset_id: 'asset-brochure-public-002'
    }
  ]
};

const sampleClusters: Phase1AClusterDetail[] = [
  {
    id: 'cluster-riverside-yard',
    cluster_key: 'riverside-yard',
    cluster_status: 'ACTIVE',
    created_at: '2026-04-15T09:05:00Z',
    member_count: 2,
    canonical_headline: 'Land at Riverside Yard',
    borough: 'Hackney',
    coverage_note: 'Manual URL and approved public-page sources align on address and brochure hash',
    members: [
      {
        id: 'member-riverside-001',
        listing_item_id: 'listing-manual-001',
        listing_headline: 'Land at Riverside Yard',
        source_name: 'Manual URL intake',
        canonical_url: 'https://example.com/listings/land-at-riverside-yard',
        confidence: 0.98,
        latest_status: 'LIVE',
        created_at: '2026-04-15T09:05:00Z'
      },
      {
        id: 'member-riverside-002',
        listing_item_id: 'listing-public-001',
        listing_headline: 'Riverside Yard, rear access plot',
        source_name: 'Approved public-page connector',
        canonical_url: 'https://land.example.org/opportunities/apt-9917',
        confidence: 0.94,
        latest_status: 'LIVE',
        created_at: '2026-04-15T09:05:00Z'
      }
    ]
  },
  {
    id: 'cluster-albion-street',
    cluster_key: 'albion-street',
    cluster_status: 'REVIEW',
    created_at: '2026-04-15T09:10:00Z',
    member_count: 2,
    canonical_headline: 'Rear Yard off Albion Street',
    borough: 'Lambeth',
    coverage_note: 'CSV broker drop and public page cluster on address and headline similarity',
    members: [
      {
        id: 'member-albion-001',
        listing_item_id: 'listing-csv-001',
        listing_headline: 'Rear Yard off Albion Street',
        source_name: 'CSV / broker drop',
        canonical_url: 'https://broker.example.invalid/rows/17',
        confidence: 0.96,
        latest_status: 'LIVE',
        created_at: '2026-04-15T09:10:00Z'
      },
      {
        id: 'member-albion-002',
        listing_item_id: 'listing-public-002',
        listing_headline: 'Albion Street yard lot',
        source_name: 'Approved public-page connector',
        canonical_url: 'https://land.example.org/opportunities/portal-4421',
        confidence: 0.91,
        latest_status: 'UNDER OFFER',
        created_at: '2026-04-15T09:10:00Z'
      }
    ]
  }
];

export const phase1AListings = sampleListingItems;

export const phase1ARuns: Phase1ARunRecord[] = [
  {
    id: 'run-manual-001',
    source_key: 'manual_url',
    source_name: 'Manual URL intake',
    connector_type: 'manual_url',
    status: 'SUCCEEDED',
    coverage_note: 'Immutable raw snapshot stored',
    parse_status: 'PARSED',
    created_at: '2026-04-15T08:12:00Z',
    updated_at: '2026-04-15T08:12:20Z'
  },
  {
    id: 'run-csv-001',
    source_key: 'broker_drop',
    source_name: 'CSV / broker drop',
    connector_type: 'csv_import',
    status: 'SUCCEEDED',
    coverage_note: 'Broker CSV imported and clustered',
    parse_status: 'PARTIAL',
    created_at: '2026-04-14T16:30:00Z',
    updated_at: '2026-04-14T16:31:00Z'
  },
  {
    id: 'run-public-001',
    source_key: 'approved_public_page',
    source_name: 'Approved public-page connector',
    connector_type: 'public_page',
    status: 'RUNNING',
    coverage_note: 'Compliance gate passed',
    parse_status: 'PARSED',
    created_at: '2026-04-15T09:00:00Z',
    updated_at: '2026-04-15T09:00:10Z'
  },
  {
    id: 'run-blocked-001',
    source_key: 'blocked_public_page',
    source_name: 'Unapproved public-page connector',
    connector_type: 'public_page',
    status: 'FAILED',
    coverage_note: 'Blocked by compliance mode',
    parse_status: 'BLOCKED',
    created_at: '2026-04-15T09:12:00Z',
    updated_at: '2026-04-15T09:12:00Z'
  }
];

export function getPhase1AListingById(listingId: string): Phase1AListingDetail | null {
  const listing = phase1AListings.find((item) => item.id === listingId);

  if (!listing) {
    return null;
  }

  return {
    ...listing,
    snapshots: sampleSnapshotsByListingId[listingId] ?? [],
    documents: sampleDocumentsByListingId[listingId] ?? [],
    normalized_fields: {
      headline: sampleSnapshotsByListingId[listingId]?.[0]?.headline ?? listing.headline,
      description_text: sampleSnapshotsByListingId[listingId]?.[0]?.description_text ?? '',
      guide_price_gbp: sampleSnapshotsByListingId[listingId]?.[0]?.guide_price_gbp ?? '',
      price_basis_type: sampleSnapshotsByListingId[listingId]?.[0]?.price_basis_type ?? 'UNKNOWN',
      status: sampleSnapshotsByListingId[listingId]?.[0]?.status ?? listing.latest_status,
      auction_date: sampleSnapshotsByListingId[listingId]?.[0]?.auction_date ?? null,
      address_text: sampleSnapshotsByListingId[listingId]?.[0]?.address_text ?? '',
      lat: sampleSnapshotsByListingId[listingId]?.[0]?.lat ?? null,
      lon: sampleSnapshotsByListingId[listingId]?.[0]?.lon ?? null
    },
    raw_record_json: sampleSnapshotsByListingId[listingId]?.[0]?.raw_record_json ?? {}
  };
}

export function getPhase1AClusterById(clusterId: string): Phase1AClusterDetail | null {
  return sampleClusters.find((cluster) => cluster.id === clusterId) ?? null;
}

