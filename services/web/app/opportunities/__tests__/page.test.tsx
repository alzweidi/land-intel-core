import type { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import OpportunitiesPage from '@/app/opportunities/page';
import { getAuthContext, readSessionTokenFromCookies } from '@/lib/auth/server';
import { getOpportunities, getReadbackState } from '@/lib/landintel-api';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
}));

vi.mock('@/lib/auth/server', () => ({
  getAuthContext: vi.fn(),
  readSessionTokenFromCookies: vi.fn()
}));

vi.mock('@/lib/landintel-api', () => ({
  getOpportunities: vi.fn(),
  getReadbackState: vi.fn()
}));

describe('OpportunitiesPage', () => {
  beforeEach(() => {
    vi.mocked(getReadbackState).mockReset();
    vi.mocked(getAuthContext).mockReset();
    vi.mocked(readSessionTokenFromCookies).mockReset();
    vi.mocked(getOpportunities).mockReset();
    vi.mocked(getReadbackState).mockImplementation((apiAvailable, itemCount) =>
      apiAvailable ? (itemCount > 0 ? 'LIVE' : 'EMPTY') : 'FALLBACK'
    );
  });

  it('keeps hidden probability gated for analyst users even when requested', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue('signed-session');
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: true,
      total: 1,
      items: [
        {
          site_id: 'site-1',
          display_name: 'Analyst site',
          borough_id: 'camden',
          borough_name: 'Camden',
          assessment_id: 'assessment-1',
          scenario_id: 'scenario-1',
          probability_band: 'Band A',
          hold_reason: null,
          ranking_reason: 'Strong planning support',
          hidden_mode_only: false,
          visibility: null,
          display_block_reason: null,
          eligibility_status: 'ELIGIBLE',
          estimate_status: 'READY',
          manual_review_required: false,
          valuation_quality: 'HIGH',
          asking_price_gbp: 1000000,
          asking_price_basis_type: 'PPD',
          auction_date: null,
          post_permission_value_mid: 1500000,
          uplift_mid: 500000,
          expected_uplift_mid: 500000,
          same_borough_support_count: 2,
          site_summary: null,
          scenario_summary: null
        }
      ]
    } as never);

    render(
      await OpportunitiesPage({
        searchParams: { includeHidden: 'true' }
      })
    );

    expect(getOpportunities).toHaveBeenCalledWith(
      expect.objectContaining({
        hidden_mode: false,
        viewer_role: 'analyst',
        sessionToken: 'signed-session'
      })
    );
    expect(screen.getByText('Standard redacted queue')).toBeInTheDocument();
    expect(screen.queryByText('Hidden/internal queue')).toBeNull();
    expect(screen.getByText('Hidden')).toBeInTheDocument();
  });

  it('shows hidden probability only when a reviewer explicitly opts in', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'reviewer',
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue('signed-session');
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: true,
      total: 1,
      items: [
        {
          site_id: 'site-2',
          display_name: 'Reviewer site',
          borough_id: 'camden',
          borough_name: 'Camden',
          assessment_id: 'assessment-2',
          scenario_id: 'scenario-2',
          probability_band: 'Band B',
          hold_reason: null,
          ranking_reason: 'Visible internal support',
          hidden_mode_only: true,
          visibility: null,
          display_block_reason: null,
          eligibility_status: 'ELIGIBLE',
          estimate_status: 'READY',
          manual_review_required: true,
          valuation_quality: 'HIGH',
          asking_price_gbp: 1000000,
          asking_price_basis_type: 'PPD',
          auction_date: null,
          post_permission_value_mid: 1500000,
          uplift_mid: 500000,
          expected_uplift_mid: 500000,
          same_borough_support_count: 2,
          site_summary: null,
          scenario_summary: null
        }
      ]
    } as never);

    render(
      await OpportunitiesPage({
        searchParams: { includeHidden: 'true' }
      })
    );

    expect(getOpportunities).toHaveBeenCalledWith(
      expect.objectContaining({
        hidden_mode: true,
        viewer_role: 'reviewer',
        sessionToken: 'signed-session'
      })
    );
    expect(screen.getByText('Hidden/internal queue')).toBeInTheDocument();
    expect(screen.getByText('£500,000')).toBeInTheDocument();
  });

  it('renders a truthful live-empty state when no opportunity rows are returned', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue(null);
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: true,
      total: 0,
      items: []
    } as never);

    render(await OpportunitiesPage({}));

    expect(screen.getByText('Empty')).toBeInTheDocument();
    expect(screen.getByText('No live opportunity rows matched the current filters.')).toBeInTheDocument();
  });

  it('renders fallback hold rows honestly without an assessment link', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'admin',
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue(null);
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: false,
      total: 1,
      items: [
        {
          site_id: 'site-3',
          display_name: null,
          borough_id: 'hackney',
          borough_name: null,
          assessment_id: null,
          scenario_id: null,
          probability_band: 'Hold',
          hold_reason: 'Await analyst review',
          ranking_reason: 'Planning evidence incomplete',
          hidden_mode_only: false,
          visibility: null,
          display_block_reason: null,
          eligibility_status: 'HOLD',
          estimate_status: 'PENDING',
          manual_review_required: true,
          valuation_quality: 'LOW',
          asking_price_gbp: null,
          asking_price_basis_type: null,
          auction_date: null,
          post_permission_value_mid: null,
          uplift_mid: null,
          expected_uplift_mid: null,
          same_borough_support_count: 0,
          site_summary: {
            display_name: 'Fallback summary site',
            current_listing_canonical_url:
              'https://idealland.co.uk/properties/fishponds-road-tooting-sw17'
          },
          scenario_summary: null
        }
      ]
    } as never);

    render(await OpportunitiesPage({}));

    expect(screen.getByText('Hold/manual review')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Model releases' })).toBeInTheDocument();
    expect(screen.getByText('Fallback summary site')).toBeInTheDocument();
    expect(screen.getByText('Await analyst review')).toBeInTheDocument();
    expect(screen.getByText('Basis unavailable')).toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open assessment' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Open live source' })).toHaveAttribute(
      'href',
      'https://idealland.co.uk/properties/fishponds-road-tooting-sw17'
    );
  });

  it('passes manual_review_required=false and renders neutral queue values when requested', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'reviewer',
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue('signed-session');
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: true,
      total: 1,
      items: [
        {
          site_id: 'site-4',
          display_name: 'Neutral site',
          borough_id: 'islington',
          borough_name: 'Islington',
          assessment_id: null,
          scenario_id: null,
          probability_band: 'Pending',
          hold_reason: null,
          ranking_reason: 'Waiting for model scope',
          hidden_mode_only: false,
          visibility: null,
          display_block_reason: null,
          eligibility_status: 'PENDING',
          estimate_status: 'WAITING',
          manual_review_required: false,
          valuation_quality: null,
          asking_price_gbp: null,
          asking_price_basis_type: null,
          auction_date: null,
          post_permission_value_mid: null,
          uplift_mid: null,
          expected_uplift_mid: null,
          same_borough_support_count: 0,
          site_summary: null,
          scenario_summary: null
        },
        {
          site_id: 'site-5',
          display_name: 'Band C site',
          borough_id: 'camden',
          borough_name: 'Camden',
          assessment_id: null,
          scenario_id: null,
          probability_band: 'Band C',
          hold_reason: null,
          ranking_reason: 'Needs planning clarification',
          hidden_mode_only: false,
          visibility: null,
          display_block_reason: null,
          eligibility_status: 'WATCH',
          estimate_status: 'PARTIAL',
          manual_review_required: false,
          valuation_quality: 'MEDIUM',
          asking_price_gbp: 500000,
          asking_price_basis_type: 'GUIDE',
          auction_date: null,
          post_permission_value_mid: 800000,
          uplift_mid: 300000,
          expected_uplift_mid: 250000,
          same_borough_support_count: 1,
          site_summary: null,
          scenario_summary: null
        }
      ]
    } as never);

    render(
      await OpportunitiesPage({
        searchParams: { manual_review_required: 'false' }
      })
    );

    expect(getOpportunities).toHaveBeenCalledWith(
      expect.objectContaining({
        manual_review_required: false,
        viewer_role: 'reviewer',
        sessionToken: 'signed-session'
      })
    );
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getAllByText('Band C')).not.toHaveLength(0);
    expect(screen.getAllByText('Unknown')).not.toHaveLength(0);
  });

  it('renders the fallback empty queue message when live data is unavailable', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'analyst',
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue(null);
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: false,
      total: 0,
      items: []
    } as never);

    render(await OpportunitiesPage({}));

    expect(
      screen.getByText('The opportunity queue is held because live data is unavailable.')
    ).toBeInTheDocument();
  });

  it('passes manual_review_required=true and falls back to site id and unknown borough when needed', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'reviewer',
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue('signed-session');
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: true,
      total: 1,
      items: [
        {
          site_id: 'site-fallback-id',
          display_name: null,
          borough_id: null,
          borough_name: null,
          assessment_id: null,
          scenario_id: null,
          probability_band: 'Band D',
          hold_reason: null,
          ranking_reason: 'Fallback identity row',
          hidden_mode_only: false,
          visibility: null,
          display_block_reason: null,
          eligibility_status: 'WATCH',
          estimate_status: 'PARTIAL',
          manual_review_required: true,
          valuation_quality: 'LOW',
          asking_price_gbp: null,
          asking_price_basis_type: null,
          auction_date: null,
          post_permission_value_mid: null,
          uplift_mid: null,
          expected_uplift_mid: null,
          same_borough_support_count: 0,
          site_summary: null,
          scenario_summary: null
        }
      ]
    } as never);

    render(
      await OpportunitiesPage({
        searchParams: {
          manual_review_required: 'true',
          valuation_quality: 'LOW'
        }
      })
    );

    expect(getOpportunities).toHaveBeenCalledWith(
      expect.objectContaining({
        manual_review_required: true,
        valuation_quality: 'LOW',
        viewer_role: 'reviewer',
        sessionToken: 'signed-session'
      })
    );
    expect(screen.getByRole('link', { name: 'site-fallback-id' })).toBeInTheDocument();
    expect(screen.getByText('Unknown borough')).toBeInTheDocument();
  });

  it('defaults the role to analyst and forwards borough and probability-band filters', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: null,
      session: null,
      user: null
    } as never);
    vi.mocked(readSessionTokenFromCookies).mockResolvedValue('signed-session');
    vi.mocked(getOpportunities).mockResolvedValue({
      apiAvailable: true,
      total: 0,
      items: []
    } as never);

    render(
      await OpportunitiesPage({
        searchParams: {
          borough: 'camden',
          probability_band: 'Band B'
        }
      })
    );

    expect(getOpportunities).toHaveBeenCalledWith(
      expect.objectContaining({
        borough: 'camden',
        probability_band: 'Band B',
        viewer_role: 'analyst',
        sessionToken: 'signed-session'
      })
    );
  });
});
