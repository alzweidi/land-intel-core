import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AssessmentRunBuilder } from '@/components/assessment-run-builder';
import { createAssessment } from '@/lib/landintel-api';

const push = vi.fn();
const refresh = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push,
    refresh
  })
}));

vi.mock('@/lib/landintel-api', () => ({
  createAssessment: vi.fn()
}));

describe('AssessmentRunBuilder', () => {
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    vi.mocked(createAssessment).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('uses today when no as-of date is provided', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-18T12:00:00.000Z'));

    render(<AssessmentRunBuilder initialScenarioId="scenario-1" initialSiteId="site-1" />);

    expect(screen.getByLabelText('As-of date')).toHaveValue('2026-04-18');
  });

  it('requires the key identifiers before submitting', () => {
    render(<AssessmentRunBuilder initialAsOfDate="2026-04-15" />);

    fireEvent.click(screen.getByRole('button', { name: 'Create assessment' }));

    expect(
      screen.getByText('Enter a site ID, confirmed scenario ID, and as-of date.')
    ).toBeInTheDocument();
    expect(createAssessment).not.toHaveBeenCalled();
  });

  it('shows a failure message when assessment creation does not return an item', async () => {
    vi.mocked(createAssessment).mockResolvedValue({
      apiAvailable: true,
      item: null
    });

    render(
      <AssessmentRunBuilder
        initialAsOfDate="2026-04-15"
        initialScenarioId="scenario-1"
        initialSiteId="site-1"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Create assessment' }));

    await waitFor(() => {
      expect(
        screen.getByText('Assessment creation failed. Check that the scenario is current and confirmed.')
      ).toBeInTheDocument();
    });
    expect(push).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  it('submits an assessment request and redirects to the created run', async () => {
    vi.mocked(createAssessment).mockResolvedValue({
      apiAvailable: true,
      item: { id: 'assessment-1' } as never
    });

    render(
      <AssessmentRunBuilder
        initialAsOfDate="2026-04-15"
        initialScenarioId="scenario-1"
        initialSiteId="site-1"
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Create assessment' }));

    await waitFor(() => {
      expect(createAssessment).toHaveBeenCalledWith({
        site_id: 'site-1',
        scenario_id: 'scenario-1',
        as_of_date: '2026-04-15',
        requested_by: 'web-ui',
        hidden_mode: false
      });
    });
    expect(push).toHaveBeenCalledWith('/assessments/assessment-1');
    expect(refresh).toHaveBeenCalled();
  });

  it('updates all editable inputs before submitting', async () => {
    vi.mocked(createAssessment).mockResolvedValue({
      apiAvailable: true,
      item: { id: 'assessment-2' } as never
    });

    render(<AssessmentRunBuilder initialAsOfDate="2026-04-17" />);

    fireEvent.change(screen.getByLabelText('Site ID'), { target: { value: ' site-2 ' } });
    fireEvent.change(screen.getByLabelText('Confirmed scenario ID'), {
      target: { value: ' scenario-2 ' }
    });
    fireEvent.change(screen.getByLabelText('As-of date'), { target: { value: '2026-04-18' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create assessment' }));

    await waitFor(() => {
      expect(createAssessment).toHaveBeenCalledWith({
        site_id: 'site-2',
        scenario_id: 'scenario-2',
        as_of_date: '2026-04-18',
        requested_by: 'web-ui',
        hidden_mode: false
      });
    });
  });
});
