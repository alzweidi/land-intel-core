import type { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ListingClustersPage from '@/app/listing-clusters/page';
import { getAuthContext } from '@/lib/auth/server';
import { getClusters, getReadbackState } from '@/lib/landintel-api';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
}));

vi.mock('@/lib/auth/server', () => ({
  getAuthContext: vi.fn()
}));

vi.mock('@/lib/landintel-api', () => ({
  getClusters: vi.fn(),
  getReadbackState: vi.fn()
}));

describe('ListingClustersPage', () => {
  it('shows a truthful empty live state when the cluster API returns zero rows', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(getReadbackState).mockReturnValue('EMPTY');
    vi.mocked(getClusters).mockResolvedValue({
      apiAvailable: true,
      items: []
    } as never);

    render(await ListingClustersPage());

    expect(screen.getByText('Live API returned zero listing clusters. Run an approved automated source or wait for the cluster rebuild job to finish.')).toBeInTheDocument();
    expect(screen.getByText('Cluster to site progression')).toBeInTheDocument();
  });

  it('marks fallback cluster rows explicitly instead of pretending they are live', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'admin',
      session: null,
      user: null
    } as never);
    vi.mocked(getReadbackState).mockReturnValue('FALLBACK');
    vi.mocked(getClusters).mockResolvedValue({
      apiAvailable: false,
      items: [
        {
          id: 'cluster-1',
          cluster_key: 'camden-yard',
          cluster_status: 'ACTIVE',
          created_at: '2026-04-20T09:00:00Z',
          member_count: 2,
          canonical_headline: 'Camden yard',
          borough: 'Camden',
          coverage_note: 'Fallback data'
        }
      ]
    } as never);

    render(await ListingClustersPage());

    expect(screen.getByText('Fallback')).toBeInTheDocument();
    expect(screen.getByText('camden-yard')).toBeInTheDocument();
    expect(screen.getByText('Connector runs')).toBeInTheDocument();
  });

  it('renders live cluster rows with the live queue posture', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: null,
      session: null,
      user: null
    } as never);
    vi.mocked(getReadbackState).mockReturnValue('LIVE');
    vi.mocked(getClusters).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'cluster-2',
          cluster_key: 'live-yard',
          cluster_status: 'REVIEW',
          created_at: '2026-04-20T09:00:00Z',
          member_count: 3,
          canonical_headline: 'Live yard',
          borough: 'Hackney',
          coverage_note: 'Review pending'
        },
        {
          id: 'cluster-3',
          cluster_key: 'archived-yard',
          cluster_status: 'ARCHIVED',
          created_at: '2026-04-20T10:00:00Z',
          member_count: 1,
          canonical_headline: 'Archived yard',
          borough: 'Camden',
          coverage_note: 'Archived fallback'
        }
      ]
    } as never);

    render(await ListingClustersPage());

    expect(screen.getByText('Current duplicate groups in the live review queue')).toBeInTheDocument();
    expect(screen.getByText('Live API')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'live-yard' })).toBeInTheDocument();
    expect(screen.getByText('ARCHIVED')).toBeInTheDocument();
  });

  it('renders explicit fallback empty messaging when no cluster rows are available', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(getReadbackState).mockReturnValue('FALLBACK');
    vi.mocked(getClusters).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);

    render(await ListingClustersPage());

    expect(screen.getByText('No live cluster rows were returned, so the page is not inventing fixture review groups.')).toBeInTheDocument();
  });
});
