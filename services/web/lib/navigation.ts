export type NavItem = {
  href: string;
  label: string;
  description: string;
};

export type NavGroup = {
  title: string;
  items: NavItem[];
};

export const navGroups: NavGroup[] = [
  {
    title: 'Explore',
    items: [
      {
        href: '/',
        label: 'Control room',
        description: 'Phase 1A landing shell and route index'
      },
      {
        href: '/listings',
        label: 'Listings',
        description: 'Listing search, detail, and intake'
      },
      {
        href: '/listing-clusters',
        label: 'Clusters',
        description: 'Deterministic dedupe and cluster review'
      },
      {
        href: '/admin/source-runs',
        label: 'Source runs',
        description: 'Manual intake and connector control'
      }
    ]
  },
  {
    title: 'Active phases',
    items: [
      {
        href: '/discovery',
        label: 'Discovery',
        description: 'Map and list placeholder'
      },
      {
        href: '/sites',
        label: 'Sites',
        description: 'Confirmed site registry'
      },
      {
        href: '/scenarios',
        label: 'Scenarios',
        description: 'Scenario templates and workflow entry'
      },
      {
        href: '/assessments',
        label: 'Assessments',
        description: 'Frozen assessments with hidden internal scoring'
      }
    ]
  },
  {
    title: 'Operations',
    items: [
      {
        href: '/review-queue',
        label: 'Review queue',
        description: 'Gold-set review and exception queue'
      },
      {
        href: '/data-health',
        label: 'Data health',
        description: 'Source freshness and coverage'
      }
    ]
  },
  {
    title: 'Admin',
    items: [
      {
        href: '/admin/health',
        label: 'Admin health',
        description: 'Jobs, auth, and service checks'
      },
      {
        href: '/admin/model-releases',
        label: 'Model releases',
        description: 'Hidden release registry and activation state'
      }
    ]
  }
];

export const surfaceCatalog = [
  {
    href: '/listings',
    title: 'Listing search',
    summary: 'Browse live listings, search by source or text, and jump into immutable snapshots.',
    tag: 'phase 1a'
  },
  {
    href: '/listing-clusters',
    title: 'Cluster review',
    summary: 'Inspect deterministic duplicate clusters and their confidence-scored members.',
    tag: 'dedupe'
  },
  {
    href: '/admin/source-runs',
    title: 'Connector control',
    summary: 'Trigger manual URL intake, broker CSV imports, and approved public-page connectors.',
    tag: 'compliance'
  },
  {
    href: '/discovery',
    title: 'Discovery map / list',
    summary: 'Browse current site candidates with map and list shell states.',
    tag: 'map + list'
  },
  {
    href: '/sites',
    title: 'Site registry',
    summary: 'Review confirmed site records, geometry placeholders, and linked evidence.',
    tag: 'site detail'
  },
  {
    href: '/scenarios',
    title: 'Scenario editor',
    summary: 'Generate, compare, and confirm deterministic scenario hypotheses for each site.',
    tag: 'scenario'
  },
  {
    href: '/assessments',
    title: 'Assessment view',
    summary: 'Inspect frozen runs with evidence, comparables, provenance, replay metadata, and hidden internal scoring mode.',
    tag: 'hidden score'
  },
  {
    href: '/review-queue',
    title: 'Review queue',
    summary: 'Review historical label candidates and record minimal gold-set adjudication notes.',
    tag: 'gold set'
  },
  {
    href: '/data-health',
    title: 'Data health dashboard',
    summary: 'Surface source freshness, connector failures, and borough coverage gaps.',
    tag: 'health'
  }
] as const;
