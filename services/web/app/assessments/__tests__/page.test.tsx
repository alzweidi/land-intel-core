import type { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AssessmentsPage from '@/app/assessments/page';
import { getAuthContext } from '@/lib/auth/server';
import { getAssessments } from '@/lib/landintel-api';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
}));

vi.mock('@/components/assessment-run-builder', () => ({
  AssessmentRunBuilder: ({
    initialScenarioId,
    initialSiteId
  }: {
    initialScenarioId?: string;
    initialSiteId?: string;
  }) => <div data-testid="assessment-builder">{`${initialSiteId}:${initialScenarioId}`}</div>
}));

vi.mock('@/lib/auth/server', () => ({
  getAuthContext: vi.fn()
}));

vi.mock('@/lib/landintel-api', () => ({
  getAssessments: vi.fn()
}));

describe('AssessmentsPage', () => {
  it('renders reviewer actions and populated assessment history', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'reviewer',
      session: null,
      user: null
    } as never);
    vi.mocked(getAssessments).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'assessment-1',
          state: 'READY',
          estimate_status: 'ESTIMATE_AVAILABLE_MANUAL_REVIEW_REQUIRED',
          review_status: 'REQUIRED',
          manual_review_required: true,
          site_id: 'site-1',
          scenario_id: 'scenario-1',
          as_of_date: '2026-04-15',
          idempotency_key: 'key-1',
          requested_by: 'pytest',
          started_at: null,
          finished_at: null,
          error_text: null,
          created_at: '2026-04-15T00:00:00Z',
          updated_at: '2026-04-15T00:00:00Z',
          site_summary: {
            display_name: 'Camden Yard',
            borough_name: 'Camden'
          },
          scenario_summary: {
            template_key: 'resi_5_9_full',
            units_assumed: 8,
            proposal_form: 'REDEVELOPMENT'
          }
        }
      ]
    } as never);

    render(
      await AssessmentsPage({
        searchParams: { scenarioId: 'scenario-1', siteId: 'site-1' }
      })
    );

    expect(screen.getByText('Frozen assessment runs')).toBeInTheDocument();
    expect(screen.getByText('Open review queue')).toBeInTheDocument();
    expect(screen.getByText('Camden Yard')).toBeInTheDocument();
    expect(screen.getByText('REQUIRED')).toBeInTheDocument();
    expect(screen.getByText('See detail')).toBeInTheDocument();
    expect(screen.getByTestId('assessment-builder')).toHaveTextContent('site-1:scenario-1');
  });

  it('renders admin-only releases and fallback table content', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: 'admin',
      session: null,
      user: null
    } as never);
    vi.mocked(getAssessments).mockResolvedValue({
      apiAvailable: true,
      items: [
        {
          id: 'assessment-1',
          state: 'READY',
          estimate_status: 'ESTIMATE_AVAILABLE',
          review_status: 'NOT_REQUIRED',
          manual_review_required: false,
          site_id: 'site-1',
          scenario_id: 'scenario-1',
          as_of_date: '2026-04-15',
          idempotency_key: 'key-1',
          requested_by: 'pytest',
          started_at: null,
          finished_at: null,
          error_text: null,
          created_at: '2026-04-15T00:00:00Z',
          updated_at: '2026-04-15T00:00:00Z',
          site_summary: {
            display_name: 'Camden Yard',
            borough_name: 'Camden'
          },
          scenario_summary: {
            template_key: 'resi_5_9_full',
            units_assumed: 8,
            proposal_form: 'REDEVELOPMENT'
          }
        },
        {
          id: 'assessment-2',
          state: 'QUEUED',
          estimate_status: 'NONE',
          review_status: 'PENDING',
          manual_review_required: true,
          site_id: 'site-2',
          scenario_id: 'scenario-2',
          as_of_date: '2026-04-16',
          idempotency_key: 'key-2',
          requested_by: 'pytest',
          started_at: null,
          finished_at: null,
          error_text: null,
          created_at: '2026-04-16T00:00:00Z',
          updated_at: '2026-04-16T00:00:00Z'
        }
      ]
    } as never);

    render(
      await AssessmentsPage({
        searchParams: { scenarioId: 'scenario-1', siteId: 'site-1' }
      })
    );

    expect(screen.getByText('Open review queue')).toBeInTheDocument();
    expect(screen.getByText('Model releases')).toBeInTheDocument();
    expect(screen.getByText('Live API. Reviewer/admin users can append ?mode=hidden for internal probability readback.')).toBeInTheDocument();
    expect(screen.getByText('NOT_REQUIRED')).toBeInTheDocument();
    expect(screen.getByText('PENDING')).toBeInTheDocument();
    expect(screen.getByText('Pre-score only')).toBeInTheDocument();
    expect(screen.getByText('See detail')).toBeInTheDocument();
    expect(screen.getByText('Unknown borough')).toBeInTheDocument();
    expect(screen.getByText('Scenario summary unavailable')).toBeInTheDocument();
  });

  it('renders the empty state for analyst users when the API is unavailable', async () => {
    vi.mocked(getAuthContext).mockResolvedValue({
      isAuthenticated: true,
      role: null,
      session: null,
      user: null
    } as never);
    vi.mocked(getAssessments).mockResolvedValue({
      apiAvailable: false,
      items: []
    } as never);

    render(await AssessmentsPage({}));

    expect(screen.getByText('API unavailable, showing the current query result only.')).toBeInTheDocument();
    expect(screen.getByText('No assessment runs exist yet. Create one from a confirmed scenario using the form above or from site detail.')).toBeInTheDocument();
    expect(screen.queryByText('Open review queue')).toBeNull();
    expect(screen.queryByText('Model releases')).toBeNull();
    expect(screen.getByTestId('assessment-builder')).toHaveTextContent(':');
  });
});
