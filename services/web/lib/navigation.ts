import type { AppRole } from '@/lib/auth/types';

export type NavItem = {
  href: string;
  label: string;
  description: string;
  requiredRole?: AppRole;
};

export type NavGroup = {
  title: string;
  items: NavItem[];
};

export type RouteMeta = {
  group: string;
  label: string;
  description: string;
  href: string;
};

export const navGroups: NavGroup[] = [
  {
    title: 'Intake',
    items: [
      {
        href: '/',
        label: 'Dashboard',
        description: 'Live queues, health, and release posture'
      },
      {
        href: '/listings',
        label: 'Listings',
        description: 'Manual intake and immutable snapshots'
      },
      {
        href: '/listing-clusters',
        label: 'Clusters',
        description: 'Deterministic duplicate review'
      },
      {
        href: '/admin/source-runs',
        label: 'Source runs',
        description: 'Connector operations and compliance'
      }
    ]
  },
  {
    title: 'Delivery',
    items: [
      {
        href: '/sites',
        label: 'Sites',
        description: 'Geometry, planning context, and evidence'
      },
      {
        href: '/scenarios',
        label: 'Scenarios',
        description: 'Scenario hypotheses and confirmation'
      },
      {
        href: '/assessments',
        label: 'Assessments',
        description: 'Frozen runs, valuation, and provenance'
      },
      {
        href: '/opportunities',
        label: 'Opportunities',
        description: 'Planning-first acquisition queue'
      }
    ]
  },
  {
    title: 'Review',
    items: [
      {
        href: '/review-queue',
        label: 'Review queue',
        description: 'Manual review, blocked cases, and gold set',
        requiredRole: 'reviewer'
      }
    ]
  },
  {
    title: 'Control',
    items: [
      {
        href: '/admin/health',
        label: 'Admin health',
        description: 'Data, model, and economic health',
        requiredRole: 'admin'
      },
      {
        href: '/admin/model-releases',
        label: 'Model releases',
        description: 'Hidden releases, visibility, and incidents',
        requiredRole: 'admin'
      }
    ]
  }
];

const routeMeta: RouteMeta[] = [
  { href: '/', group: 'Intake', label: 'Dashboard', description: 'Live queues, health, and release posture' },
  { href: '/listings', group: 'Intake', label: 'Listings', description: 'Manual intake and immutable snapshots' },
  { href: '/listing-clusters', group: 'Intake', label: 'Clusters', description: 'Deterministic dedupe and cluster review' },
  { href: '/admin/source-runs', group: 'Intake', label: 'Source runs', description: 'Connector operations and compliance' },
  { href: '/sites', group: 'Delivery', label: 'Sites', description: 'Geometry, planning context, and evidence' },
  { href: '/scenarios', group: 'Delivery', label: 'Scenarios', description: 'Scenario hypotheses and confirmation' },
  { href: '/assessments', group: 'Delivery', label: 'Assessments', description: 'Frozen runs, valuation, and replay-safe provenance' },
  { href: '/opportunities', group: 'Delivery', label: 'Opportunities', description: 'Planning-first acquisition queue' },
  { href: '/review-queue', group: 'Review', label: 'Review queue', description: 'Manual review, blocked cases, and gold set' },
  { href: '/admin/health', group: 'Control', label: 'Admin health', description: 'Data, model, and economic health' },
  { href: '/admin/model-releases', group: 'Control', label: 'Model releases', description: 'Hidden releases, visibility, and incidents' }
];

export const surfaceCatalog = [
  {
    href: '/listings',
    title: 'Listing search',
    summary: 'Browse live listings, inspect immutable snapshots, and jump into intake details.',
    tag: 'intake'
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
    summary: 'Inspect frozen runs with evidence, comparables, provenance, replay metadata, hidden internal scoring, and valuation.',
    tag: 'hidden score'
  },
  {
    href: '/opportunities',
    title: 'Opportunity ranking',
    summary: 'Review planning-first opportunity bands, valuation quality, uplift, and honest HOLD states.',
    tag: 'ranking'
  },
  {
    href: '/review-queue',
    title: 'Review queue',
    summary: 'Review historical label candidates and record minimal gold-set adjudication notes.',
    tag: 'gold set'
  },
  {
    href: '/admin/health',
    title: 'Admin health',
    summary: 'Check source freshness, model calibration, and economic-health warnings in one control panel.',
    tag: 'health'
  }
] as const;

export function getRouteMeta(pathname: string): RouteMeta {
  const match = routeMeta.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));

  if (match) {
    return match;
  }

  if (pathname.startsWith('/sites/') && pathname.endsWith('/scenario-editor')) {
    return {
      href: '/scenarios',
      group: 'Delivery',
      label: 'Scenario editor',
      description: 'Deterministic scenario hypotheses and confirmation'
    };
  }

  if (pathname.startsWith('/sites/')) {
    return {
      href: '/sites',
      group: 'Delivery',
      label: 'Site detail',
      description: 'Confirmed site geometry, planning context, and evidence'
    };
  }

  if (pathname.startsWith('/assessments/')) {
    return {
      href: '/assessments',
      group: 'Delivery',
      label: 'Assessment detail',
      description: 'Eligibility, evidence, valuation, comparables, and audit state'
    };
  }

  if (pathname.startsWith('/listing-clusters/')) {
    return {
      href: '/listing-clusters',
      group: 'Intake',
      label: 'Cluster detail',
      description: 'Duplicate cluster review and member confidence'
    };
  }

  return {
    href: pathname,
    group: 'Internal',
    label: 'Internal workspace',
    description: 'Connected product shell'
  };
}
