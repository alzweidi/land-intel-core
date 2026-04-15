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
        description: 'Landing shell and route index'
      },
      {
        href: '/discovery',
        label: 'Discovery',
        description: 'Map and list placeholder'
      },
      {
        href: '/listings',
        label: 'Listings',
        description: 'Manual intake and source registry'
      },
      {
        href: '/sites',
        label: 'Sites',
        description: 'Confirmed site registry'
      },
      {
        href: '/scenarios',
        label: 'Scenarios',
        description: 'Scenario template shell'
      },
      {
        href: '/assessments',
        label: 'Assessments',
        description: 'Frozen run history'
      }
    ]
  },
  {
    title: 'Operations',
    items: [
      {
        href: '/review-queue',
        label: 'Review queue',
        description: 'Manual review and exception queue'
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
      }
    ]
  }
];

export const surfaceCatalog = [
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
    summary: 'Inspect the scenario shell that will later host confirmed proposal inputs.',
    tag: 'scenario'
  },
  {
    href: '/assessments',
    title: 'Assessment view',
    summary: 'Render frozen assessment results, evidence blocks, and valuation bands.',
    tag: 'assessment'
  },
  {
    href: '/review-queue',
    title: 'Review queue',
    summary: 'Track manual-review-required and changed cases in a simple queue layout.',
    tag: 'ops'
  },
  {
    href: '/data-health',
    title: 'Data health dashboard',
    summary: 'Surface source freshness, connector failures, and borough coverage gaps.',
    tag: 'health'
  }
] as const;
