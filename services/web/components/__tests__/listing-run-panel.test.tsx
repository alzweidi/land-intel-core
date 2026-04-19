import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ListingRunPanel } from '@/components/listing-run-panel';
import { runConnector, runCsvImport, runManualUrlIntake } from '@/lib/landintel-api';

vi.mock('@/lib/landintel-api', () => ({
  runConnector: vi.fn(),
  runCsvImport: vi.fn(),
  runManualUrlIntake: vi.fn()
}));

const automatedSources = [
  {
    id: 'manual',
    source_key: 'manual_url',
    name: 'manual_url',
    connector_type: 'manual_url',
    compliance_mode: 'MANUAL_ONLY',
    active: true,
    refresh_policy: 'Manual only',
    coverage_note: 'Manual only'
  },
  {
    id: 'auto',
    source_key: 'example_public_page',
    name: 'example_public_page',
    connector_type: 'public_page',
    compliance_mode: 'COMPLIANT_AUTOMATED',
    active: true,
    refresh_policy: 'Every 24h',
    coverage_note: 'Every 24h'
  }
] as const;

describe('ListingRunPanel', () => {
  beforeEach(() => {
    vi.mocked(runManualUrlIntake).mockReset();
    vi.mocked(runCsvImport).mockReset();
    vi.mocked(runConnector).mockReset();
  });

  it('renders a file-only CSV flow and defaults to the live automated source', () => {
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    expect(screen.queryByLabelText('CSV text')).toBeNull();
    expect(screen.getByDisplayValue('example_public_page')).toBeInTheDocument();
  });

  it('shows an error when CSV submit is attempted without a file', async () => {
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/import/csv' }));

    expect(await screen.findByText('Select a CSV file before submitting the import.')).toBeInTheDocument();
    expect(runCsvImport).not.toHaveBeenCalled();
  });

  it('submits manual URL runs and reports null payloads as API errors', async () => {
    vi.mocked(runManualUrlIntake).mockResolvedValue(null);
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/intake/url' }));

    await waitFor(() => {
      expect(runManualUrlIntake).toHaveBeenCalledWith({
        url: 'https://example.com/listings/land-at-riverside-yard',
        coverage_note: 'Internal analyst run'
      });
    });
    expect(await screen.findByText('API unavailable or returned a non-JSON response.')).toBeInTheDocument();
  });

  it('surfaces request failures from manual URL submissions', async () => {
    vi.mocked(runManualUrlIntake).mockRejectedValue(new Error('boom'));
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/intake/url' }));

    expect(await screen.findByText('boom')).toBeInTheDocument();
  });

  it('falls back to the generic failure message for non-Error rejections', async () => {
    vi.mocked(runManualUrlIntake).mockRejectedValue('boom');
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/intake/url' }));

    expect(await screen.findByText('Unexpected request failure')).toBeInTheDocument();
  });

  it('renders string responses without JSON formatting', async () => {
    vi.mocked(runManualUrlIntake).mockResolvedValue('accepted');
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/intake/url' }));

    expect(await screen.findByText('accepted')).toBeInTheDocument();
  });

  it('submits file uploads for CSV imports', async () => {
    vi.mocked(runCsvImport).mockResolvedValue({ ok: true });
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.change(screen.getByLabelText('CSV file'), {
      target: {
        files: [new File(['headline,address\nSite,1 Test Road'], 'listings.csv', { type: 'text/csv' })]
      }
    });
    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/import/csv' }));

    await waitFor(() => {
      expect(runCsvImport).toHaveBeenCalledTimes(1);
    });
  });

  it('treats an emptied CSV file picker as no selected file', async () => {
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.change(screen.getByLabelText('CSV file'), {
      target: {
        files: []
      }
    });
    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/import/csv' }));

    expect(await screen.findByText('Select a CSV file before submitting the import.')).toBeInTheDocument();
  });

  it('submits connector runs with the default automated source', async () => {
    vi.mocked(runConnector).mockResolvedValue({ ok: true });
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/connectors/{source_key}/run' }));

    await waitFor(() => {
      expect(runConnector).toHaveBeenCalledWith('example_public_page', {
        coverage_note: 'Internal analyst run'
      });
    });
  });

  it('updates manual URL, source key, and coverage note before submission', async () => {
    vi.mocked(runManualUrlIntake).mockResolvedValue({ ok: true });
    vi.mocked(runConnector).mockResolvedValue({ ok: true });
    render(<ListingRunPanel sourceOptions={[...automatedSources]} />);

    fireEvent.change(screen.getByLabelText('Listing URL'), {
      target: { value: 'https://example.com/listings/updated-yard' }
    });
    fireEvent.change(screen.getByLabelText('Coverage note'), {
      target: { value: 'Updated note' }
    });
    fireEvent.change(screen.getByLabelText('Source key'), {
      target: { value: 'approved_public_page' }
    });

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/intake/url' }));
    await waitFor(() => {
      expect(runManualUrlIntake).toHaveBeenCalledWith({
        url: 'https://example.com/listings/updated-yard',
        coverage_note: 'Updated note'
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Post /api/listings/connectors/{source_key}/run' }));
    await waitFor(() => {
      expect(runConnector).toHaveBeenCalledWith('approved_public_page', {
        coverage_note: 'Updated note'
      });
    });
  });

  it('disables connector runs when no active compliant automated source exists', () => {
    render(
      <ListingRunPanel
        sourceOptions={[
          {
            id: 'manual',
            source_key: 'manual_url',
            name: 'manual_url',
            connector_type: 'manual_url',
            compliance_mode: 'MANUAL_ONLY',
            active: true,
            refresh_policy: 'Manual only',
            coverage_note: 'Manual only'
          }
        ]}
      />
    );

    expect(screen.getByText('No active compliant automated source is currently available.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Post /api/listings/connectors/{source_key}/run' })
    ).toBeDisabled();
  });
});
