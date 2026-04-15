export const homeStats = [
  {
    label: 'Route shells',
    value: '10',
    detail: 'All Phase 0 surfaces are represented'
  },
  {
    label: 'Backend coupling',
    value: '0',
    detail: 'No live API dependence in the web stub'
  },
  {
    label: 'Job queue contract',
    value: '1',
    detail: 'Frontend assumes Postgres-backed job state'
  },
  {
    label: 'Scoring logic',
    value: '0',
    detail: 'No probability or valuation logic included'
  }
] as const;

export const discoveryRows = [
  {
    id: 'cand-018',
    name: 'Garage court off Example Road',
    borough: 'Hackney',
    state: 'Needs geometry review',
    source: 'Manual URL intake',
    note: 'Map/list shell only'
  },
  {
    id: 'cand-021',
    name: 'Yard plot behind the high street',
    borough: 'Lambeth',
    state: 'Review required',
    source: 'Compliance connector',
    note: 'Snapshot placeholder'
  },
  {
    id: 'cand-026',
    name: 'Mews-side redevelopment parcel',
    borough: 'Southwark',
    state: 'Candidate only',
    source: 'Auction page',
    note: 'Awaiting site candidate build'
  }
] as const;

export const listingRows = [
  {
    id: 'L-1042',
    title: 'Land at Example Road',
    borough: 'Hackney',
    source: 'Manual URL',
    status: 'QUEUED',
    note: 'HTML snapshot pending'
  },
  {
    id: 'L-1043',
    title: 'Rear yard off Riverside Walk',
    borough: 'Lambeth',
    source: 'Approved connector',
    status: 'RUNNING',
    note: 'Raw asset stored'
  },
  {
    id: 'L-1044',
    title: 'Former workshop plot',
    borough: 'Southwark',
    source: 'Auction catalogue',
    status: 'SUCCEEDED',
    note: 'Ready for clustering later'
  }
] as const;

export const siteRows = [
  {
    id: 'site-001',
    name: 'Garage court off Example Road',
    borough: 'Hackney',
    geom: 'MEDIUM',
    permission: 'No active permission found',
    scenario: 'resi_5_9_full'
  },
  {
    id: 'site-002',
    name: 'Rear-yard infill opportunity',
    borough: 'Lambeth',
    geom: 'LOW',
    permission: 'Needs manual review',
    scenario: 'resi_1_4_full'
  },
  {
    id: 'site-003',
    name: 'Workshop renewal parcel',
    borough: 'Southwark',
    geom: 'HIGH',
    permission: 'No active permission found',
    scenario: 'resi_10_49_outline'
  }
] as const;

export const scenarioRows = [
  {
    key: 'resi_1_4_full',
    units: '1-4',
    route: 'FULL',
    status: 'SUGGESTED',
    note: 'Small infill shell'
  },
  {
    key: 'resi_5_9_full',
    units: '5-9',
    route: 'FULL',
    status: 'ANALYST_REQUIRED',
    note: 'Primary scaffold scenario'
  },
  {
    key: 'resi_10_49_outline',
    units: '10-49',
    route: 'OUTLINE',
    status: 'ANALYST_CONFIRMED',
    note: 'Future flow placeholder'
  }
] as const;

export const assessmentRows = [
  {
    id: 'assess-001',
    site: 'site-001',
    scenario: 'resi_5_9_full',
    probability: 'Hidden',
    quality: 'Stub',
    state: 'Queued for later phases'
  },
  {
    id: 'assess-002',
    site: 'site-002',
    scenario: 'resi_1_4_full',
    probability: 'Hidden',
    quality: 'Stub',
    state: 'Frozen run shell'
  }
] as const;

export const reviewRows = [
  {
    item: 'site-002',
    reason: 'Low geometry confidence',
    priority: 'High',
    bucket: 'Manual review required'
  },
  {
    item: 'site-004',
    reason: 'Borough source gap',
    priority: 'Medium',
    bucket: 'Borough-failing case'
  },
  {
    item: 'site-006',
    reason: 'Changed source snapshot',
    priority: 'Low',
    bucket: 'Recent change'
  }
] as const;

export const healthRows = [
  {
    family: 'Listings',
    freshness: '6h',
    coverage: 'Stubbed',
    gap: 'Manual intake only'
  },
  {
    family: 'Planning registers',
    freshness: '24h',
    coverage: 'Pending',
    gap: 'No live sync yet'
  },
  {
    family: 'Policy layers',
    freshness: '7d',
    coverage: 'Pending',
    gap: 'No enrichment pipeline'
  }
] as const;

export const adminChecks = [
  {
    name: 'API',
    state: 'Stubbed',
    detail: 'Health endpoints are scaffolded'
  },
  {
    name: 'Worker',
    state: 'Stubbed',
    detail: 'Queue loop is not part of this task'
  },
  {
    name: 'Scheduler',
    state: 'Stubbed',
    detail: 'Cron shell is reserved for later'
  },
  {
    name: 'Auth',
    state: 'Supabase-ready',
    detail: 'Frontend expects Supabase environment variables'
  }
] as const;
