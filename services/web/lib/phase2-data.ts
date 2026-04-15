import type {
  GeometryFeature,
  SiteDetail,
  SiteDocument,
  SiteGeometrySaveInput,
  SiteLpaLink,
  SiteMarketEvent,
  SiteSummary,
  SiteTitleLink
} from '@/lib/landintel-api';

function polygonFeature(
  coordinates: number[][][],
  properties: Record<string, unknown>
): GeometryFeature {
  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates
    },
    properties
  };
}

function squareAround(lon: number, lat: number, delta = 0.0012): GeometryFeature {
  return polygonFeature(
    [
      [
        [lon - delta, lat - delta],
        [lon + delta, lat - delta],
        [lon + delta, lat + delta],
        [lon - delta, lat + delta],
        [lon - delta, lat - delta]
      ]
    ],
    {}
  );
}

function ringAreaHint(siteId: string, area: number): string {
  return `${siteId} · ${area.toLocaleString('en-GB')} sqm`;
}

function makeDocument(input: Omit<SiteDocument, 'asset_id'> & { asset_id?: string | null }): SiteDocument {
  return {
    asset_id: input.asset_id ?? null,
    id: input.id,
    label: input.label,
    doc_type: input.doc_type,
    href: input.href,
    mime_type: input.mime_type,
    extraction_status: input.extraction_status ?? null,
    note: input.note
  };
}

function makeTitleLink(input: SiteTitleLink): SiteTitleLink {
  return input;
}

function makeLpaLink(input: SiteLpaLink): SiteLpaLink {
  return input;
}

function makeMarketEvent(input: SiteMarketEvent): SiteMarketEvent {
  return input;
}

function makeSummary(site: SiteDetail): SiteSummary {
  const {
    address_text: _address_text,
    description_text: _description_text,
    documents: _documents,
    geometry_editor_guidance: _geometry_editor_guidance,
    last_updated_at: _last_updated_at,
    lpa_links: _lpa_links,
    market_events: _market_events,
    revision_history: _revision_history,
    source_snapshot_id: _source_snapshot_id,
    source_snapshot_url: _source_snapshot_url,
    summary: _summary,
    title_links: _title_links,
    current_listing: _current_listing,
    ...summary
  } = site;

  void _address_text;
  void _description_text;
  void _documents;
  void _geometry_editor_guidance;
  void _last_updated_at;
  void _lpa_links;
  void _market_events;
  void _revision_history;
  void _source_snapshot_id;
  void _source_snapshot_url;
  void _summary;
  void _title_links;
  void _current_listing;

  return summary;
}

const currentTime = '2026-04-15T10:30:00Z';

const hackneyPolygon = polygonFeature(
  [
    [
      [-0.0712, 51.5476],
      [-0.0682, 51.5474],
      [-0.0672, 51.5492],
      [-0.0703, 51.5495],
      [-0.0712, 51.5476]
    ]
  ],
  { site_id: 'site-hackney-garage-court', label: 'Garage court off Example Road' }
);

const lambethPolygon = polygonFeature(
  [
    [
      [-0.1225, 51.4804],
      [-0.1187, 51.4802],
      [-0.1178, 51.4821],
      [-0.1219, 51.4824],
      [-0.1225, 51.4804]
    ]
  ],
  { site_id: 'site-lambeth-riverside-yard', label: 'Rear-yard infill opportunity' }
);

const southwarkEnvelope = squareAround(-0.0838, 51.4992, 0.0009);

const hackneyTitles = [
  makeTitleLink({
    title_ref: 'title-23-104394',
    title_number: 'NGL612938',
    address_text: 'Garage court off Example Road, Hackney',
    overlap_sqm: 382,
    overlap_pct: 84.6,
    confidence: 'HIGH',
    is_primary: true,
    indicative_only: true,
    evidence_note: 'Indicative INSPIRE polygon overlap from title reference only'
  }),
  makeTitleLink({
    title_ref: 'title-23-104395',
    title_number: 'NGL612939',
    address_text: 'Servitude strip to the north edge',
    overlap_sqm: 68,
    overlap_pct: 15.4,
    confidence: 'MEDIUM',
    is_primary: false,
    indicative_only: true,
    evidence_note: 'Secondary title touchpoint; legal parcel truth remains unresolved'
  })
];

const lambethTitles = [
  makeTitleLink({
    title_ref: 'title-24-002218',
    title_number: 'LN123044',
    address_text: 'Rear-yard infill opportunity, Lambeth',
    overlap_sqm: 520,
    overlap_pct: 61.2,
    confidence: 'HIGH',
    is_primary: true,
    indicative_only: true,
    evidence_note: 'Primary title candidate from visible title polygon overlap'
  }),
  makeTitleLink({
    title_ref: 'title-24-002219',
    title_number: 'LN123045',
    address_text: 'Mews access strip',
    overlap_sqm: 329,
    overlap_pct: 38.8,
    confidence: 'MEDIUM',
    is_primary: false,
    indicative_only: true,
    evidence_note: 'Adjacent indicative title link; useful evidence, not parcel truth'
  })
];

const southwarkTitles = [
  makeTitleLink({
    title_ref: 'title-24-005500',
    title_number: 'SS912345',
    address_text: 'Workshop plot behind Kent Road',
    overlap_sqm: 92,
    overlap_pct: 100,
    confidence: 'LOW',
    is_primary: true,
    indicative_only: true,
    evidence_note: 'Point-level evidence only; title linkage is indicative'
  })
];

const hackneyLpas = [
  makeLpaLink({
    lpa_code: 'E09000012',
    lpa_name: 'Hackney',
    overlap_sqm: 456,
    overlap_pct: 100,
    controlling: true,
    manual_clip_required: false,
    cross_lpa_flag: false,
    note: 'Controlling borough'
  })
];

const lambethLpas = [
  makeLpaLink({
    lpa_code: 'E09000022',
    lpa_name: 'Lambeth',
    overlap_sqm: 621,
    overlap_pct: 96.4,
    controlling: true,
    manual_clip_required: false,
    cross_lpa_flag: true,
    note: 'Minor Southwark overlap below material threshold; keep Lambeth and flag the overlap'
  }),
  makeLpaLink({
    lpa_code: 'E09000028',
    lpa_name: 'Southwark',
    overlap_sqm: 23,
    overlap_pct: 3.6,
    controlling: false,
    manual_clip_required: false,
    cross_lpa_flag: true,
    note: 'Trivial cross-LPA overlap only'
  })
];

const southwarkLpas = [
  makeLpaLink({
    lpa_code: 'E09000028',
    lpa_name: 'Southwark',
    overlap_sqm: 92,
    overlap_pct: 71.7,
    controlling: true,
    manual_clip_required: true,
    cross_lpa_flag: true,
    note: 'Material overlap with Lewisham requires manual clipping and analyst confirmation'
  }),
  makeLpaLink({
    lpa_code: 'E09000023',
    lpa_name: 'Lewisham',
    overlap_sqm: 36,
    overlap_pct: 28.3,
    controlling: false,
    manual_clip_required: true,
    cross_lpa_flag: true,
    note: 'Overlap is material enough that automated assignment should not freeze the boundary'
  })
];

const hackneyDocuments = [
  makeDocument({
    id: 'doc-site-hackney-html',
    label: 'Source snapshot HTML',
    doc_type: 'html_snapshot',
    href: 'https://example.com/raw/site-hackney-garage-court/source.html',
    mime_type: 'text/html',
    extraction_status: 'EXTRACTED',
    note: 'Immutable HTML snapshot captured for the source run'
  }),
  makeDocument({
    id: 'doc-site-hackney-pdf',
    label: 'Brochure PDF',
    doc_type: 'brochure_pdf',
    href: 'https://example.com/raw/site-hackney-garage-court/brochure.pdf',
    mime_type: 'application/pdf',
    extraction_status: 'EXTRACTED',
    note: 'Brochure stored immutably and text extracted via PyMuPDF in backend phase'
  })
];

const lambethDocuments = [
  makeDocument({
    id: 'doc-site-lambeth-html',
    label: 'Source snapshot HTML',
    doc_type: 'html_snapshot',
    href: 'https://example.com/raw/site-lambeth-riverside-yard/source.html',
    mime_type: 'text/html',
    extraction_status: 'EXTRACTED',
    note: 'Immutable HTML snapshot captured for the approved public-page connector'
  }),
  makeDocument({
    id: 'doc-site-lambeth-map',
    label: 'Embedded map image',
    doc_type: 'raw_asset',
    href: 'https://example.com/raw/site-lambeth-riverside-yard/map.png',
    mime_type: 'image/png',
    extraction_status: 'NOT_APPLICABLE',
    note: 'Display-only map capture reference'
  })
];

const southwarkDocuments = [
  makeDocument({
    id: 'doc-site-southwark-html',
    label: 'CSV import record',
    doc_type: 'raw_asset',
    href: 'https://example.com/raw/site-southwark-kent-road/import.csv',
    mime_type: 'text/csv',
    extraction_status: 'NOT_APPLICABLE',
    note: 'Broker drop record retained as immutable raw asset'
  })
];

export const phase2Sites: SiteDetail[] = [
  {
    site_id: 'site-hackney-garage-court',
    display_name: 'Garage court off Example Road',
    cluster_id: 'cluster-riverside-yard',
    cluster_key: 'riverside-yard',
    borough_name: 'Hackney',
    controlling_lpa_name: 'Hackney',
    geometry_source_type: 'SOURCE_POLYGON',
    geometry_confidence: 'HIGH',
    site_area_sqm: 456,
    current_listing_id: 'listing-hackney-001',
    current_listing_headline: 'Garage court off Example Road',
    current_price_gbp: 1850000,
    current_price_basis_type: 'GUIDE_PRICE',
    warnings: [
      'Indicative title polygons are evidence only and must not be treated as legal parcel truth.',
      'No planning or extant-permission inference is shown on this screen.'
    ],
    review_flags: ['TITLE_EVIDENCE_ONLY'],
    revision_count: 2,
    document_count: 2,
    title_link_count: 2,
    lpa_link_count: 1,
    geometry_geojson_4326: hackneyPolygon,
    centroid_4326: { lat: 51.5485, lon: -0.0693 },
    address_text: 'Garage court off Example Road, Hackney, London',
    summary: ringAreaHint('site-hackney-garage-court', 456),
    description_text: 'Small yard opportunity with a confirmed polygon draft and strong title evidence.',
    source_snapshot_id: 'snapshot-site-hackney-001',
    source_snapshot_url: 'https://example.com/raw/site-hackney-garage-court/source.html',
    current_listing: {
      id: 'listing-hackney-001',
      headline: 'Garage court off Example Road',
      source_key: 'manual_url',
      canonical_url: 'https://example.com/listings/garage-court-example-road',
      latest_status: 'LIVE',
      parse_status: 'PARSED',
      price_display: 'Guide price £1.85m',
      observed_at: currentTime
    },
    revision_history: [
      {
        revision_id: 'geomrev-site-hackney-002',
        created_at: currentTime,
        created_by: 'analyst@landintel.local',
        geom_source_type: 'ANALYST_DRAWN',
        geom_confidence: 'HIGH',
        geom_hash: 'geom-hackney-002',
        site_area_sqm: 456,
        note: 'Analyst-adjusted draft after reviewing title evidence and the source brochure.',
        is_current: true,
        geometry_geojson_4326: hackneyPolygon
      },
      {
        revision_id: 'geomrev-site-hackney-001',
        created_at: '2026-04-15T09:50:00Z',
        created_by: 'system',
        geom_source_type: 'SOURCE_POLYGON',
        geom_confidence: 'MEDIUM',
        geom_hash: 'geom-hackney-001',
        site_area_sqm: 452,
        note: 'Initial cluster-derived draft geometry.',
        is_current: false,
        geometry_geojson_4326: hackneyPolygon
      }
    ],
    title_links: hackneyTitles,
    lpa_links: hackneyLpas,
    documents: hackneyDocuments,
    market_events: [
      makeMarketEvent({
        event_id: 'site-hackney-event-001',
        event_type: 'SITE_CREATED',
        event_at: '2026-04-15T09:50:00Z',
        price_gbp: 1850000,
        price_basis_type: 'GUIDE_PRICE',
        note: 'Created from cluster evidence and live listing snapshot',
        source_listing_id: 'listing-hackney-001'
      })
    ],
    geometry_editor_guidance: 'Use the polygon editor to adjust the confirmed site boundary. Do not widen beyond the documented evidence.',
    last_updated_at: currentTime
  },
  {
    site_id: 'site-lambeth-riverside-yard',
    display_name: 'Rear-yard infill opportunity',
    cluster_id: 'cluster-riverside-yard',
    cluster_key: 'riverside-yard',
    borough_name: 'Lambeth',
    controlling_lpa_name: 'Lambeth',
    geometry_source_type: 'TITLE_UNION',
    geometry_confidence: 'MEDIUM',
    site_area_sqm: 642,
    current_listing_id: 'listing-lambeth-021',
    current_listing_headline: 'Rear-yard infill opportunity',
    current_price_gbp: 920000,
    current_price_basis_type: 'GUIDE_PRICE',
    warnings: [
      'Cross-LPA overlap is trivial, so Lambeth remains the controlling borough but the overlap should stay flagged.',
      'Title polygons are indicative only and do not prove legal parcel truth.'
    ],
    review_flags: ['CROSS_LPA_FLAGGED'],
    revision_count: 1,
    document_count: 2,
    title_link_count: 2,
    lpa_link_count: 2,
    geometry_geojson_4326: lambethPolygon,
    centroid_4326: { lat: 51.4813, lon: -0.1202 },
    address_text: 'Rear-yard infill opportunity, Lambeth, London',
    summary: ringAreaHint('site-lambeth-riverside-yard', 642),
    description_text: 'Draft geometry assembled from linked title evidence with a minor borough crossover.',
    source_snapshot_id: 'snapshot-site-lambeth-001',
    source_snapshot_url: 'https://example.com/raw/site-lambeth-riverside-yard/source.html',
    current_listing: {
      id: 'listing-lambeth-021',
      headline: 'Rear-yard infill opportunity',
      source_key: 'compliant_public_page',
      canonical_url: 'https://example.com/listings/rear-yard-infill',
      latest_status: 'LIVE',
      parse_status: 'PARSED',
      price_display: 'Guide price £920k',
      observed_at: currentTime
    },
    revision_history: [
      {
        revision_id: 'geomrev-site-lambeth-001',
        created_at: '2026-04-15T08:30:00Z',
        created_by: 'system',
        geom_source_type: 'TITLE_UNION',
        geom_confidence: 'MEDIUM',
        geom_hash: 'geom-lambeth-001',
        site_area_sqm: 642,
        note: 'Title union created from two indicative INSPIRE polygons.',
        is_current: true,
        geometry_geojson_4326: lambethPolygon
      }
    ],
    title_links: lambethTitles,
    lpa_links: lambethLpas,
    documents: lambethDocuments,
    market_events: [
      makeMarketEvent({
        event_id: 'site-lambeth-event-001',
        event_type: 'SITE_CREATED',
        event_at: '2026-04-15T08:30:00Z',
        price_gbp: 920000,
        price_basis_type: 'GUIDE_PRICE',
        note: 'Created from approved public-page connector evidence',
        source_listing_id: 'listing-lambeth-021'
      })
    ],
    geometry_editor_guidance: 'This draft is title-derived evidence only. Any edit that expands into Southwark must be reviewed carefully.',
    last_updated_at: currentTime
  },
  {
    site_id: 'site-southwark-kent-road',
    display_name: 'Workshop plot behind Kent Road',
    cluster_id: 'cluster-kent-road',
    cluster_key: 'kent-road',
    borough_name: 'Southwark',
    controlling_lpa_name: 'Southwark',
    geometry_source_type: 'POINT_ONLY',
    geometry_confidence: 'INSUFFICIENT',
    site_area_sqm: null,
    current_listing_id: 'listing-southwark-007',
    current_listing_headline: 'Workshop plot behind Kent Road',
    current_price_gbp: 375000,
    current_price_basis_type: 'AUCTION_GUIDE',
    warnings: [
      'Geometry is only point-level evidence at this stage; the editor should not imply a legal boundary.',
      'Title linkage is indicative and requires manual confirmation before downstream use.'
    ],
    review_flags: ['POINT_EVIDENCE_ONLY', 'MANUAL_CLIP_REQUIRED'],
    revision_count: 1,
    document_count: 1,
    title_link_count: 1,
    lpa_link_count: 2,
    geometry_geojson_4326: southwarkEnvelope,
    centroid_4326: { lat: 51.4992, lon: -0.0838 },
    address_text: 'Workshop plot behind Kent Road, Southwark, London',
    summary: ringAreaHint('site-southwark-kent-road', 92),
    description_text: 'Low-confidence point evidence with a display-only envelope to keep the candidate visible for review.',
    source_snapshot_id: 'snapshot-site-southwark-001',
    source_snapshot_url: 'https://example.com/raw/site-southwark-kent-road/import.csv',
    current_listing: {
      id: 'listing-southwark-007',
      headline: 'Workshop plot behind Kent Road',
      source_key: 'csv_import',
      canonical_url: 'https://example.com/listings/workshop-plot-kent-road',
      latest_status: 'UNDER OFFER',
      parse_status: 'PARSED',
      price_display: 'Guide price £375k',
      observed_at: currentTime
    },
    revision_history: [
      {
        revision_id: 'geomrev-site-southwark-001',
        created_at: '2026-04-15T07:10:00Z',
        created_by: 'system',
        geom_source_type: 'POINT_ONLY',
        geom_confidence: 'INSUFFICIENT',
        geom_hash: 'geom-southwark-001',
        site_area_sqm: null,
        note: 'Display-only envelope around point evidence. Analyst confirmation required before use.',
        is_current: true,
        geometry_geojson_4326: southwarkEnvelope
      }
    ],
    title_links: southwarkTitles,
    lpa_links: southwarkLpas,
    documents: southwarkDocuments,
    market_events: [
      makeMarketEvent({
        event_id: 'site-southwark-event-001',
        event_type: 'SITE_CREATED',
        event_at: '2026-04-15T07:10:00Z',
        price_gbp: 375000,
        price_basis_type: 'AUCTION_GUIDE',
        note: 'Created from broker drop evidence',
        source_listing_id: 'listing-southwark-007'
      })
    ],
    geometry_editor_guidance: 'This site only has point evidence. Keep edits conservative and convert to a proper polygon only with explicit analyst judgment.',
    last_updated_at: currentTime
  }
];

export const phase2SiteSummaries = phase2Sites.map(makeSummary);

export function getPhase2SiteById(siteId: string): SiteDetail | null {
  return phase2Sites.find((site) => site.site_id === siteId) ?? null;
}

export function getPhase2SiteSummaryById(siteId: string): SiteSummary | null {
  return phase2SiteSummaries.find((site) => site.site_id === siteId) ?? null;
}

export function applyLocalSiteGeometry(
  siteId: string,
  input: SiteGeometrySaveInput
): SiteDetail | null {
  const site = getPhase2SiteById(siteId);
  if (!site) {
    return null;
  }

  const nextRevisionIndex = site.revision_history.length + 1;
  const nextRevision = {
    revision_id: `${siteId}-geomrev-${String(nextRevisionIndex).padStart(3, '0')}`,
    created_at: currentTime,
    created_by: 'local-fallback',
    geom_source_type: input.geom_source_type,
    geom_confidence: input.geom_confidence,
    geom_hash: `${siteId}-hash-${String(nextRevisionIndex).padStart(3, '0')}`,
    site_area_sqm: site.site_area_sqm,
    note: input.revision_note ?? 'Local fallback geometry save',
    is_current: true,
    geometry_geojson_4326: input.geometry_geojson_4326
  };

  return {
    ...site,
    geometry_source_type: input.geom_source_type,
    geometry_confidence: input.geom_confidence,
    revision_history: site.revision_history.map((revision) => ({
      ...revision,
      is_current: false
    })).concat(nextRevision),
    revision_count: site.revision_count + 1,
    last_updated_at: currentTime,
    warnings: site.warnings.concat([
      'Local fallback updated the preview data only. Refreshing the page will restore the checked-in fixture state.'
    ])
  };
}
