import type { Phase1ASource } from '@/lib/phase1a-data';

export type ListingConsoleJob = {
  job_type: string;
};

const LEGACY_SOURCE_KEY_ALIASES: Record<string, string> = {
  approved_public_page: 'example_public_page'
};

const DEFAULT_LIVE_AUTOMATED_SOURCE_KEY = 'bidwells_land_development';
const PREFERRED_LIVE_AUTOMATED_SOURCE_KEYS = [
  'bidwells_land_development',
  'ideal_land_current_sites',
  'cabinet_office_surplus_property'
];

const LISTING_CONSOLE_JOB_TYPES = new Set([
  'MANUAL_URL_SNAPSHOT',
  'CSV_IMPORT_SNAPSHOT',
  'LISTING_SOURCE_RUN'
]);

export function normalizeListingSourceKey(sourceKey: string): string {
  const normalized = sourceKey.trim();
  return LEGACY_SOURCE_KEY_ALIASES[normalized] ?? normalized;
}

export function selectDefaultAutomatedSourceKey(sources: Phase1ASource[]): string {
  const preferredSourceKey = PREFERRED_LIVE_AUTOMATED_SOURCE_KEYS.find((candidate) =>
    sources.some(
      (source) =>
        normalizeListingSourceKey(source.source_key) === candidate &&
        source.active &&
        source.compliance_mode === 'COMPLIANT_AUTOMATED'
    )
  );
  if (preferredSourceKey) {
    return preferredSourceKey;
  }

  const automatedSource = sources.find(
    (source) => source.active && source.compliance_mode === 'COMPLIANT_AUTOMATED'
  );
  const fallbackSource =
    automatedSource?.source_key ?? sources[0]?.source_key ?? DEFAULT_LIVE_AUTOMATED_SOURCE_KEY;
  return normalizeListingSourceKey(fallbackSource);
}

export function countListingConsoleRuns(jobs: ListingConsoleJob[]): number {
  return jobs.filter((job) => LISTING_CONSOLE_JOB_TYPES.has(job.job_type)).length;
}
