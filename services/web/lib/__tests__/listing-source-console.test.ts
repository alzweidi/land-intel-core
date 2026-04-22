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

  it('prefers the configured live acquisition source when it is active', () => {
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
          source_key: 'cabinet_office_surplus_property',
          name: 'cabinet_office_surplus_property',
          connector_type: 'public_page',
          compliance_mode: 'COMPLIANT_AUTOMATED',
          active: true,
          refresh_policy: 'Every 24h',
          coverage_note: 'Every 24h'
        },
        {
          id: 'preferred',
          source_key: 'bidwells_land_development',
          name: 'bidwells_land_development',
          connector_type: 'public_page',
          compliance_mode: 'COMPLIANT_AUTOMATED',
          active: true,
          refresh_policy: 'Every 24h',
          coverage_note: 'Every 24h'
        },
        {
          id: 'secondary',
          source_key: 'ideal_land_current_sites',
          name: 'ideal_land_current_sites',
          connector_type: 'public_page',
          compliance_mode: 'COMPLIANT_AUTOMATED',
          active: true,
          refresh_policy: 'Every 24h',
          coverage_note: 'Every 24h'
        }
      ])
    ).toBe('bidwells_land_development');
  });

  it('falls back to the canonical automated source key when no sources are available', () => {
    expect(selectDefaultAutomatedSourceKey([])).toBe('bidwells_land_development');
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
