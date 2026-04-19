import type { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ListingsPage from '@/app/listings/page';
import { getAuthContext } from '@/lib/auth/server';
import { getListingSources, getListings } from '@/lib/landintel-api';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
}));

vi.mock('@/lib/auth/server', () => ({
  getAuthContext: vi.fn()
}));

vi.mock('@/lib/landintel-api', () => ({
  getListingSources: vi.fn(),
  getListings: vi.fn()
}));

describe('ListingsPage', () => {
  it('renders live source posture for admin users', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'admin',
      session: null,
      user: null
    } as never);
    vi.mocked(getListings).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'listing-1',
          source_id: 'source-1',
          source_key: 'example_public_page',
          source_name: 'example_public_page',
          source_listing_id: 'listing-1',
          canonical_url: 'https://example.com/listing-1',
          listing_type: 'LAND',
          headline: 'Example listing',
          borough: 'Camden',
          latest_status: 'LIVE',
          parse_status: 'PARSED',
          cluster_id: null,
          cluster_key: null,
          first_seen_at: '2026-04-19T00:00:00Z',
          last_seen_at: '2026-04-19T00:00:00Z',
          price_display: 'Guide price: GBP 1,000,000',
          coverage_note: 'Snapshot preserved'
        }
      ]
    } as never);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'source-1',
          source_key: 'example_public_page',
          name: 'example_public_page',
          connector_type: 'public_page',
          compliance_mode: 'COMPLIANT_AUTOMATED',
          active: true,
          refresh_policy: 'Every 24h',
          coverage_note: 'Every 24h'
        }
      ]
    } as never);

    render(await ListingsPage({}));

    expect(screen.getByText('Run connector')).toBeInTheDocument();
    expect(screen.getAllByText(/COMPLIANT_AUTOMATED · Every 24h/)).toHaveLength(2);
    expect(screen.getByText('Example listing')).toBeInTheDocument();
  });

  it('renders explicit source metadata empty states without fixture fallback', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(getListings).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);

    render(await ListingsPage({}));

    expect(screen.getByText('No live source metadata was returned. Listing rows can still render, but source filters and posture are unavailable.')).toBeInTheDocument();
    expect(screen.getByText('No live listing-source metadata was returned for this environment.')).toBeInTheDocument();
    expect(screen.queryByText('Run connector')).toBeNull();
  });

  it('handles array search params and renders unclustered fallback source details', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(getListings).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'listing-2',
          source_id: 'source-2',
          source_key: null,
          source_name: 'manual_url',
          source_listing_id: 'listing-2',
          canonical_url: 'https://example.com/listing-2',
          listing_type: 'LAND',
          headline: 'Fallback borough listing',
          borough: 'Southwark',
          latest_status: 'UNDER OFFER',
          parse_status: 'PARSED',
          cluster_id: null,
          cluster_key: null,
          first_seen_at: '2026-04-19T00:00:00Z',
          last_seen_at: '2026-04-19T00:00:00Z',
          price_display: 'POA',
          coverage_note: 'Manual'
        }
      ]
    } as never);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'source-2',
          source_key: 'example_public_page',
          name: 'example_public_page',
          connector_type: 'public_page',
          compliance_mode: 'COMPLIANT_AUTOMATED',
          active: true,
          refresh_policy: 'Every 24h',
          coverage_note: 'Every 24h'
        }
      ]
    } as never);

    render(
      await ListingsPage({
        searchParams: {
          q: ['yard', 'ignored'],
          source: ['example_public_page'],
          status: ['LIVE'],
          type: ['LAND'],
          cluster: ['cluster-1']
        }
      })
    );

    expect(screen.getByDisplayValue('yard')).toBeInTheDocument();
    expect(screen.getByDisplayValue('example_public_page')).toBeInTheDocument();
    expect(screen.getByText('Southwark')).toBeInTheDocument();
    expect(screen.getByText('Unclustered')).toBeInTheDocument();
  });

  it('renders cluster links when listing rows include a cluster id', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(getListings).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'listing-3',
          source_id: 'source-3',
          source_key: 'example_public_page',
          source_name: 'example_public_page',
          source_listing_id: 'listing-3',
          canonical_url: 'https://example.com/listing-3',
          listing_type: 'LAND',
          headline: 'Clustered listing',
          borough: null,
          latest_status: 'LIVE',
          parse_status: 'PARSED',
          cluster_id: 'cluster-3',
          cluster_key: 'camden-yard',
          first_seen_at: '2026-04-19T00:00:00Z',
          last_seen_at: '2026-04-19T00:00:00Z',
          price_display: 'Guide price',
          coverage_note: 'Snapshot preserved'
        }
      ]
    } as never);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: true,
      items: []
    } as never);

    render(await ListingsPage({}));

    const clusterLink = screen.getByRole('link', { name: 'camden-yard' });
    expect(clusterLink).toHaveAttribute('href', '/listing-clusters/cluster-3');
    expect(screen.getByText('example_public_page · Unknown borough')).toBeInTheDocument();
  });

  it('uses analyst defaults, empty-array filters, and cluster-id fallback labels', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: null,
      session: null,
      user: null
    } as never);
    vi.mocked(getListings).mockResolvedValue({
      apiAvailable: false,
      items: [
        {
          id: 'listing-4',
          source_id: 'source-4',
          source_key: null,
          source_name: 'manual_url',
          source_listing_id: 'listing-4',
          canonical_url: 'https://example.com/listing-4',
          listing_type: 'LAND',
          headline: 'Fallback cluster key listing',
          borough: null,
          latest_status: 'SOLD',
          parse_status: 'PARSED',
          cluster_id: 'cluster-4',
          cluster_key: null,
          first_seen_at: '2026-04-19T00:00:00Z',
          last_seen_at: '2026-04-19T00:00:00Z',
          price_display: 'Sold',
          coverage_note: 'Fallback'
        }
      ]
    } as never);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'source-4',
          source_key: 'example_public_page',
          name: 'example_public_page',
          connector_type: 'public_page',
          compliance_mode: 'COMPLIANT_AUTOMATED',
          active: true,
          refresh_policy: 'Every 24h',
          coverage_note: 'Every 24h'
        }
      ]
    } as never);

    render(
      await ListingsPage({
        searchParams: {
          q: [],
          source: [],
          status: [],
          type: [],
          cluster: []
        }
      })
    );

    expect(screen.queryByText('Run connector')).toBeNull();
    expect(screen.getByText('All rows')).toBeInTheDocument();
    expect(screen.getByText('Unknown borough')).toBeInTheDocument();
    expect(screen.getAllByText('SOLD')).not.toHaveLength(0);
    const clusterLink = screen.getByRole('link', { name: 'cluster-4' });
    expect(clusterLink).toHaveAttribute('href', '/listing-clusters/cluster-4');
  });
});
