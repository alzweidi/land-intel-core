import type { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SitesPage from '@/app/sites/page';
import { getReadbackState, getSites } from '@/lib/landintel-api';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
}));

vi.mock('@/components/site-map', () => ({
  SiteMap: ({ sites }: { sites: Array<{ site_id: string }> }) => (
    <div data-testid="site-map">{sites.map((site) => site.site_id).join(',')}</div>
  )
}));

vi.mock('@/lib/landintel-api', () => ({
  getSites: vi.fn(),
  getReadbackState: vi.fn()
}));

describe('SitesPage', () => {
  it('shows a truthful empty live state when the API returns no sites', async () => {
    vi.mocked(getReadbackState).mockReturnValue('EMPTY');
    vi.mocked(getSites).mockResolvedValue({
      apiAvailable: true,
      items: []
    } as never);

    render(await SitesPage({}));

    expect(screen.getByText('Empty')).toBeInTheDocument();
    expect(screen.getByText('No live site rows matched the current filter set.')).toBeInTheDocument();
    expect(screen.getByText('No site candidate is available in the current filter set.')).toBeInTheDocument();
  });

  it('marks fallback data as hold/manual review instead of live truth', async () => {
    vi.mocked(getReadbackState).mockReturnValue('FALLBACK');
    vi.mocked(getSites).mockResolvedValue({
      apiAvailable: false,
      items: [
        {
          site_id: 'site-1',
          display_name: 'Fallback site',
          cluster_id: 'cluster-1',
          cluster_key: 'fallback-cluster',
          borough_name: 'Camden',
          controlling_lpa_name: 'Camden',
          geometry_source_type: 'ANALYST_DRAWN',
          geometry_confidence: 'LOW',
          site_area_sqm: 100,
          current_listing_id: 'listing-1',
          current_listing_headline: 'Fallback listing',
          current_listing_canonical_url: 'https://example.com/fallback-site',
          current_price_gbp: null,
          current_price_basis_type: null,
          warnings: ['Coverage gap'],
          review_flags: ['Manual review'],
          revision_count: 1,
          document_count: 0,
          title_link_count: 0,
          lpa_link_count: 0,
          geometry_geojson_4326: {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [0, 0] },
            properties: {}
          },
          centroid_4326: { lat: 51.5, lon: -0.1 }
        }
      ]
    } as never);

    render(await SitesPage({}));

    expect(screen.getByText('Hold/manual review')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Fallback site' })).toBeInTheDocument();
    expect(
      screen
        .getAllByRole('link', { name: 'Open live source' })
        .every((link) => link.getAttribute('href') === 'https://example.com/fallback-site')
    ).toBe(true);
    expect(screen.getByTestId('site-map')).toHaveTextContent('site-1');
  });

  it('renders live sites with the live registry posture', async () => {
    vi.mocked(getReadbackState).mockReturnValue('LIVE');
    vi.mocked(getSites).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          site_id: 'site-live',
          display_name: 'Live site',
          cluster_id: 'cluster-live',
          cluster_key: 'live-cluster',
          borough_name: 'Hackney',
          controlling_lpa_name: 'Hackney',
          geometry_source_type: 'SOURCE_POLYGON',
          geometry_confidence: 'HIGH',
          site_area_sqm: 250,
          current_listing_id: 'listing-live',
          current_listing_headline: 'Live listing',
          current_listing_canonical_url: 'https://idealland.co.uk/properties/fishponds-road-tooting-sw17',
          current_price_gbp: 250000,
          current_price_basis_type: 'GUIDE_PRICE',
          warnings: [],
          review_flags: [],
          revision_count: 1,
          document_count: 1,
          title_link_count: 1,
          lpa_link_count: 1,
          geometry_geojson_4326: {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [0, 0] },
            properties: {}
          },
          centroid_4326: { lat: 51.52, lon: -0.08 }
        },
        {
          site_id: 'site-held',
          display_name: 'Held site',
          cluster_id: 'cluster-held',
          cluster_key: 'held-cluster',
          borough_name: 'Camden',
          controlling_lpa_name: 'Camden',
          geometry_source_type: 'POINT_ONLY',
          geometry_confidence: 'INSUFFICIENT',
          site_area_sqm: null,
          current_listing_id: 'listing-held',
          current_listing_headline: 'Held listing',
          current_listing_canonical_url: null,
          current_price_gbp: null,
          current_price_basis_type: null,
          warnings: [],
          review_flags: [],
          revision_count: 1,
          document_count: 0,
          title_link_count: 0,
          lpa_link_count: 0,
          geometry_geojson_4326: {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [0, 0] },
            properties: {}
          },
          centroid_4326: { lat: 51.53, lon: -0.09 }
        },
        {
          site_id: 'site-medium',
          display_name: 'Medium site',
          cluster_id: 'cluster-medium',
          cluster_key: 'medium-cluster',
          borough_name: 'Southwark',
          controlling_lpa_name: 'Southwark',
          geometry_source_type: 'TITLE_UNION',
          geometry_confidence: 'MEDIUM',
          site_area_sqm: 180,
          current_listing_id: 'listing-medium',
          current_listing_headline: 'Medium listing',
          current_listing_canonical_url: null,
          current_price_gbp: 300000,
          current_price_basis_type: 'GUIDE_PRICE',
          warnings: [],
          review_flags: [],
          revision_count: 1,
          document_count: 1,
          title_link_count: 1,
          lpa_link_count: 1,
          geometry_geojson_4326: {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [0, 0] },
            properties: {}
          },
          centroid_4326: { lat: 51.5, lon: -0.1 }
        }
      ]
    } as never);

    render(
      await SitesPage({
        searchParams: {
          q: ['site'],
          borough: ['Hackney'],
          confidence: ['HIGH'],
          selected: ['site-held']
        }
      })
    );

    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.getByText('Loaded from the API')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Live site' })).toBeInTheDocument();
    expect(screen.getByDisplayValue('site')).toBeInTheDocument();
    expect(
      screen
        .getAllByRole('link', { name: 'Open live source' })
        .every(
          (link) =>
            link.getAttribute('href') ===
            'https://idealland.co.uk/properties/fishponds-road-tooting-sw17'
        )
    ).toBe(true);
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
  });

  it('holds the registry in fallback mode when no site rows are available', async () => {
    vi.mocked(getReadbackState).mockReturnValue('FALLBACK');
    vi.mocked(getSites).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);

    render(
      await SitesPage({
        searchParams: {
          q: [],
          borough: [],
          confidence: []
        }
      })
    );

    expect(screen.getByText('Hold/manual review')).toBeInTheDocument();
    expect(
      screen.getByText('Live site data is unavailable, so the registry is held in fallback mode.')
    ).toBeInTheDocument();
  });
});
