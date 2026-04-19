import type { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SourceRunsPage from '@/app/admin/source-runs/page';
import { readSessionTokenFromCookies } from '@/lib/auth/server';
import { getAdminJobs, getListingSources } from '@/lib/landintel-api';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
}));

vi.mock('@/components/listing-run-panel', () => ({
  ListingRunPanel: ({ sourceOptions }: { sourceOptions: Array<{ source_key: string }> }) => (
    <div data-testid="listing-run-panel">{sourceOptions.map((source) => source.source_key).join(',')}</div>
  )
}));

vi.mock('@/lib/auth/server', () => ({
  readSessionTokenFromCookies: vi.fn()
}));

vi.mock('@/lib/landintel-api', () => ({
  getAdminJobs: vi.fn(),
  getListingSources: vi.fn()
}));

describe('SourceRunsPage', () => {
  it('renders live source metadata and counts listing run jobs from admin jobs', async () => {
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue('signed-session');
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
    vi.mocked(getAdminJobs).mockResolvedValue({
      apiAvailable: true,
      items: [
        { id: 'job-1', job_type: 'LISTING_SOURCE_RUN', status: 'QUEUED', requested_by: 'scheduler' },
        { id: 'job-2', job_type: 'MANUAL_URL_SNAPSHOT', status: 'SUCCEEDED', requested_by: 'web-ui' },
        { id: 'job-3', job_type: 'SITE_BUILD_REFRESH', status: 'SUCCEEDED', requested_by: 'worker' }
      ]
    } as never);

    render(await SourceRunsPage());

    expect(getAdminJobs).toHaveBeenCalledWith({ sessionToken: 'signed-session' });
    expect(screen.getByText('Live API')).toBeInTheDocument();
    expect(screen.getByText('Every 24h')).toBeInTheDocument();
    expect(screen.getByTestId('listing-run-panel')).toHaveTextContent('example_public_page');
  });

  it('renders an explicit empty state when live source metadata is unavailable', async () => {
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue(null);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);
    vi.mocked(getAdminJobs).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);

    render(await SourceRunsPage());

    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.getByText('No live listing-source metadata was returned. Seed approved sources and retry.')).toBeInTheDocument();
    expect(screen.getByTestId('listing-run-panel')).toHaveTextContent('');
  });

  it('marks the API mode as partial when only one live data source responds', async () => {
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue('signed-session');
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: true,
      items: []
    } as never);
    vi.mocked(getAdminJobs).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);

    render(await SourceRunsPage());

    expect(screen.getByText('Partial')).toBeInTheDocument();
  });

  it('renders blocked sources with non-success compliance badges and inactive state', async () => {
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue(null);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'source-2',
          source_key: 'manual_url',
          name: 'manual_url',
          connector_type: 'manual_url',
          compliance_mode: 'BLOCKED',
          active: false,
          refresh_policy: 'Manual only',
          coverage_note: 'Manual only'
        }
      ]
    } as never);
    vi.mocked(getAdminJobs).mockResolvedValue({
      apiAvailable: true,
      items: []
    } as never);

    render(await SourceRunsPage());

    expect(screen.getByText('BLOCKED')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
  });

  it('renders manual-only sources with the warning compliance path', async () => {
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue(null);
    vi.mocked(getListingSources).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'source-3',
          source_key: 'csv_import',
          name: 'csv_import',
          connector_type: 'csv_import',
          compliance_mode: 'MANUAL_ONLY',
          active: true,
          refresh_policy: 'Manual only',
          coverage_note: 'Manual only'
        }
      ]
    } as never);
    vi.mocked(getAdminJobs).mockResolvedValue({
      apiAvailable: true,
      items: []
    } as never);

    render(await SourceRunsPage());

    expect(screen.getByText('MANUAL_ONLY')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
  });
});
