import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SiteScenarioEditor } from '@/components/site-scenario-editor';
import {
  confirmScenario,
  getScenario,
  suggestSiteScenarios,
  type ScenarioDetail,
  type ScenarioSummary,
  type SiteDetail
} from '@/lib/landintel-api';

vi.mock('@/lib/landintel-api', () => ({
  confirmScenario: vi.fn(),
  getScenario: vi.fn(),
  suggestSiteScenarios: vi.fn()
}));

const site = {
  site_id: 'site-1'
} as SiteDetail;

const scenarioSummary: ScenarioSummary = {
  id: 'scenario-1',
  site_id: 'site-1',
  template_key: 'resi_5_9_full',
  template_version: 'v1',
  proposal_form: 'REDEVELOPMENT',
  units_assumed: 8,
  route_assumed: 'FULL',
  height_band_assumed: 'MID_RISE',
  net_developable_area_pct: 0.72,
  red_line_geom_hash: '1234567890abcdef',
  scenario_source: 'AUTO',
  status: 'SUGGESTED',
  supersedes_id: null,
  is_current: true,
  is_headline: true,
  heuristic_rank: 1,
  manual_review_required: false,
  stale_reason: null,
  housing_mix_assumed_json: {},
  parking_assumption: null,
  affordable_housing_assumption: null,
  access_assumption: null,
  reason_codes: [],
  missing_data_flags: [],
  warning_codes: []
};

const scenarioDetail: ScenarioDetail = {
  ...scenarioSummary,
  template: null,
  review_history: [],
  evidence: null,
  baseline_pack: null,
  site_summary: null
};

const scenarioDetailWithEvidence: ScenarioDetail = {
  ...scenarioDetail,
  reason_codes: [
    {
      code: 'PLAN_POLICY',
      message: 'Policy support is present.',
      source_label: 'Local plan',
      source_url: 'https://example.com/reason',
      source_snapshot_id: null,
      raw_asset_id: null
    },
    {
      code: 'NO_URL_REASON',
      message: 'This reason has no source link.',
      source_label: null,
      source_url: null,
      source_snapshot_id: null,
      raw_asset_id: null
    }
  ],
  warning_codes: ['REVIEW_GAP'],
  evidence: {
    for: [
      {
        polarity: 'FOR',
        claim_text: 'Policy supports the scheme',
        topic: 'planning',
        importance: 'high',
        source_class: 'AUTHORITATIVE',
        source_label: 'Local plan',
        source_url: 'https://example.com/for',
        source_snapshot_id: null,
        raw_asset_id: null,
        excerpt_text: null,
        verified_status: 'VERIFIED'
      },
      {
        polarity: 'FOR',
        claim_text: 'No source link on this item',
        topic: 'access',
        importance: 'medium',
        source_class: 'ANALYST_DERIVED',
        source_label: 'Site note',
        source_url: null,
        source_snapshot_id: null,
        raw_asset_id: null,
        excerpt_text: null,
        verified_status: 'UNVERIFIED'
      }
    ],
    against: [
      {
        polarity: 'AGAINST',
        claim_text: 'Flood risk needs review',
        topic: 'flood',
        importance: 'high',
        source_class: 'OFFICIAL_INDICATIVE',
        source_label: 'EA register',
        source_url: 'https://example.com/against',
        source_snapshot_id: null,
        raw_asset_id: null,
        excerpt_text: null,
        verified_status: 'VERIFIED'
      }
    ],
    unknown: []
  }
};

describe('SiteScenarioEditor', () => {
  beforeEach(() => {
    vi.mocked(confirmScenario).mockReset();
    vi.mocked(getScenario).mockReset();
    vi.mocked(suggestSiteScenarios).mockReset();
  });

  it('shows the editor empty state when no scenario is selected', () => {
    render(<SiteScenarioEditor initialScenarios={[]} site={site} />);

    expect(screen.getByText('Select or generate a scenario to edit its parameters.')).toBeInTheDocument();
  });

  it('renders status badges for the supported tone branches', () => {
    const scenarios: ScenarioSummary[] = [
      { ...scenarioSummary, id: 'confirmed', status: 'ANALYST_CONFIRMED' },
      { ...scenarioSummary, id: 'review', status: 'ANALYST_REQUIRED' },
      { ...scenarioSummary, id: 'rejected', status: 'REJECTED' }
    ];

    render(<SiteScenarioEditor initialScenarios={scenarios} site={site} />);

    expect(screen.getByText('ANALYST_CONFIRMED')).toBeInTheDocument();
    expect(screen.getByText('ANALYST_REQUIRED')).toBeInTheDocument();
    expect(screen.getByText('REJECTED')).toBeInTheDocument();
  });

  it('renders supporting/manual-review summary values for a non-headline scenario', () => {
    render(
      <SiteScenarioEditor
        initialScenarios={[
          {
            ...scenarioSummary,
            id: 'scenario-supporting',
            is_headline: false,
            manual_review_required: true,
            stale_reason: 'Geometry revised'
          }
        ]}
        site={site}
      />
    );

    expect(screen.getByText('Supporting scenario · Geometry revised')).toBeInTheDocument();
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('refreshes suggestions and loads the new headline scenario detail', async () => {
    vi.mocked(suggestSiteScenarios).mockResolvedValue({
      apiAvailable: true,
      item: {
        site_id: 'site-1',
        headline_scenario_id: 'scenario-2',
        items: [{ ...scenarioSummary, id: 'scenario-2', units_assumed: 9 }],
        excluded_templates: [
          {
            template_key: 'resi_1_4_full',
            reasons: [],
            missing_data_flags: [],
            warning_codes: []
          }
        ]
      } as never
    });
    vi.mocked(getScenario).mockResolvedValue({
      apiAvailable: true,
      item: { ...scenarioDetailWithEvidence, id: 'scenario-2', units_assumed: 9 }
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestions' }));

    await waitFor(() => {
      expect(suggestSiteScenarios).toHaveBeenCalledWith('site-1', { requested_by: 'web-ui' });
    });
    expect(getScenario).toHaveBeenCalledWith('scenario-2');
    expect(
      screen.getByText('1 scenario(s) suggested, 1 template(s) excluded.')
    ).toBeInTheDocument();
    expect(screen.getByText('REVIEW_GAP')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Open source' })).toHaveLength(3);
  });

  it('refreshes suggestions without excluded templates', async () => {
    vi.mocked(suggestSiteScenarios).mockResolvedValue({
      apiAvailable: true,
      item: {
        site_id: 'site-1',
        headline_scenario_id: 'scenario-1',
        items: [scenarioSummary],
        excluded_templates: []
      } as never
    });
    vi.mocked(getScenario).mockResolvedValue({
      apiAvailable: true,
      item: scenarioDetail
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestions' }));

    await waitFor(() => {
      expect(suggestSiteScenarios).toHaveBeenCalledWith('site-1', { requested_by: 'web-ui' });
    });
    expect(screen.getByText('1 scenario(s) suggested.')).toBeInTheDocument();
  });

  it('uses the first returned scenario when no headline id is provided', async () => {
    vi.mocked(suggestSiteScenarios).mockResolvedValue({
      apiAvailable: true,
      item: {
        site_id: 'site-1',
        headline_scenario_id: null,
        items: [{ ...scenarioSummary, id: 'scenario-4', units_assumed: 11 }],
        excluded_templates: []
      } as never
    });
    vi.mocked(getScenario).mockResolvedValue({
      apiAvailable: true,
      item: { ...scenarioDetail, id: 'scenario-4', units_assumed: 11 }
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestions' }));

    await waitFor(() => {
      expect(getScenario).toHaveBeenCalledWith('scenario-4');
    });
  });

  it('handles an empty suggestion set without opening detail', async () => {
    vi.mocked(suggestSiteScenarios).mockResolvedValue({
      apiAvailable: true,
      item: {
        site_id: 'site-1',
        headline_scenario_id: null,
        items: [],
        excluded_templates: []
      } as never
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestions' }));

    await waitFor(() => {
      expect(screen.getByText('0 scenario(s) suggested.')).toBeInTheDocument();
    });
    expect(getScenario).not.toHaveBeenCalled();
    expect(screen.getByText('No scenarios are stored for this site yet.')).toBeInTheDocument();
  });

  it('reports a failed suggestion request when the API does not return a payload', async () => {
    vi.mocked(suggestSiteScenarios).mockResolvedValue({
      apiAvailable: true,
      item: null
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestions' }));

    await waitFor(() => {
      expect(
        screen.getByText('Scenario suggestion did not return an API payload.')
      ).toBeInTheDocument();
    });
  });

  it('confirms the selected scenario with edited parameters', async () => {
    vi.mocked(confirmScenario).mockResolvedValue({
      apiAvailable: true,
      item: { ...scenarioDetail, status: 'ANALYST_CONFIRMED' }
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.change(screen.getByLabelText('Proposal form'), { target: { value: 'INFILL' } });
    fireEvent.change(screen.getByLabelText('Units assumed'), { target: { value: '12' } });
    fireEvent.change(screen.getByLabelText('Route assumed'), { target: { value: 'PARTIAL' } });
    fireEvent.change(screen.getByLabelText('Height band'), { target: { value: 'LOW_RISE' } });
    fireEvent.change(screen.getByLabelText('Net developable area %'), { target: { value: '0.81' } });
    fireEvent.change(screen.getByLabelText('Parking assumption'), {
      target: { value: 'Shared parking court' }
    });
    fireEvent.change(screen.getByLabelText('Affordable housing assumption'), {
      target: { value: '15 percent affordable' }
    });
    fireEvent.change(screen.getByLabelText('Access assumption'), {
      target: { value: 'Access from the east edge' }
    });
    fireEvent.change(screen.getByLabelText('Review notes'), {
      target: { value: 'Reviewed with transport and planning context.' }
    });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm scenario' }));

    await waitFor(() => {
      expect(confirmScenario).toHaveBeenCalledWith(
        'scenario-1',
        expect.objectContaining({
          action: 'CONFIRM',
          requested_by: 'web-ui',
          proposal_form: 'INFILL',
          units_assumed: 12,
          route_assumed: 'PARTIAL',
          height_band_assumed: 'LOW_RISE',
          net_developable_area_pct: 0.81,
          parking_assumption: 'Shared parking court',
          affordable_housing_assumption: '15 percent affordable',
          access_assumption: 'Access from the east edge',
          review_notes: 'Reviewed with transport and planning context.'
        })
      );
    });
    expect(
      screen.getByText('Scenario confirmed with the edited parameters.')
    ).toBeInTheDocument();
  });

  it('marks a superseded scenario as supporting after confirm', async () => {
    vi.mocked(confirmScenario).mockResolvedValue({
      apiAvailable: true,
      item: {
        ...scenarioDetail,
        id: 'scenario-2',
        units_assumed: 12,
        is_current: true,
        is_headline: true,
        status: 'ANALYST_CONFIRMED',
        supersedes_id: 'scenario-1'
      }
    });

    render(
      <SiteScenarioEditor
        initialScenarios={[
          scenarioSummary,
          {
            ...scenarioSummary,
            id: 'scenario-3',
            units_assumed: 5,
            is_headline: false,
            is_current: true
          }
        ]}
        site={site}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Confirm scenario' }));

    await waitFor(() => {
      expect(screen.getByText('Scenario confirmed with the edited parameters.')).toBeInTheDocument();
    });

    const supersededCard = screen.getByText('resi_5_9_full · 8 units').closest('article');
    expect(supersededCard).not.toBeNull();
    expect(within(supersededCard!).getByText('Supporting scenario')).toBeInTheDocument();
    expect(screen.getByText('resi_5_9_full · 5 units')).toBeInTheDocument();
  });

  it('rejects the selected scenario and omits editable assumptions', async () => {
    vi.mocked(confirmScenario).mockResolvedValue({
      apiAvailable: true,
      item: { ...scenarioDetail, status: 'REJECTED' }
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Reject scenario' }));

    await waitFor(() => {
      expect(confirmScenario).toHaveBeenCalledWith(
        'scenario-1',
        expect.objectContaining({
          action: 'REJECT',
          requested_by: 'web-ui',
          units_assumed: undefined,
          route_assumed: undefined,
          height_band_assumed: undefined,
          net_developable_area_pct: undefined,
          parking_assumption: undefined,
          affordable_housing_assumption: undefined,
          access_assumption: undefined
        })
      );
    });
    expect(
      screen.getByText('Scenario rejected and removed from the current headline set.')
    ).toBeInTheDocument();
  });

  it('reports a failed confirm request when the API does not return a scenario', async () => {
    vi.mocked(confirmScenario).mockResolvedValue({
      apiAvailable: true,
      item: null
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Confirm scenario' }));

    await waitFor(() => {
      expect(screen.getByText('Scenario confirm request failed.')).toBeInTheDocument();
    });
  });

  it('reports an unavailable scenario detail when opening fails', async () => {
    vi.mocked(getScenario).mockResolvedValue({
      apiAvailable: true,
      item: null
    });

    render(<SiteScenarioEditor initialScenarios={[scenarioSummary]} site={site} />);

    fireEvent.click(screen.getByRole('button', { name: 'Open' }));

    await waitFor(() => {
      expect(screen.getByText('Scenario detail is unavailable.')).toBeInTheDocument();
    });
  });
});
