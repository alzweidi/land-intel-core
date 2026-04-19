import { describe, expect, it } from 'vitest';

import {
  countListingConsoleRuns,
  normalizeListingSourceKey,
  selectDefaultAutomatedSourceKey
} from '@/lib/listing-source-console';

describe('listing-source-console helpers', () => {
  it('normalizes legacy source keys and preserves canonical keys', () => {
    expect(normalizeListingSourceKey('approved_public_page')).toBe('example_public_page');
    expect(normalizeListingSourceKey('example_public_page')).toBe('example_public_page');
  });

  it('selects the first active compliant automated source as the default', () => {
    expect(
      selectDefaultAutomatedSourceKey([
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
          source_key: 'approved_public_page',
          name: 'example_public_page',
          connector_type: 'public_page',
          compliance_mode: 'COMPLIANT_AUTOMATED',
          active: true,
          refresh_policy: 'Every 24h',
          coverage_note: 'Every 24h'
        }
      ])
    ).toBe('example_public_page');
  });

  it('falls back to the canonical automated source key when no sources are available', () => {
    expect(selectDefaultAutomatedSourceKey([])).toBe('example_public_page');
  });

  it('counts only listing console job types', () => {
    expect(
      countListingConsoleRuns([
        { job_type: 'MANUAL_URL_SNAPSHOT' },
        { job_type: 'CSV_IMPORT_SNAPSHOT' },
        { job_type: 'LISTING_SOURCE_RUN' },
        { job_type: 'SITE_BUILD_REFRESH' }
      ])
    ).toBe(3);
  });
});
