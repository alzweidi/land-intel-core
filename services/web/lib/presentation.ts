type ListingLike = {
  headline?: string | null;
  canonical_url?: string | null;
  source_listing_id?: string | null;
  id?: string | null;
};

function toTitleCase(value: string): string {
  return value
    .split(' ')
    .filter(Boolean)
    .map((part) => {
      if (/^[A-Z0-9]{2,}$/.test(part)) {
        return part.toUpperCase();
      }

      return `${part.charAt(0).toUpperCase()}${part.slice(1)}`;
    })
    .join(' ');
}

function humanizeUrlPath(url: string): string | null {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split('/').filter(Boolean);
    const rawSlug = parts.at(-1);
    if (!rawSlug) {
      return null;
    }

    const withoutNumericTail = rawSlug.replace(/-\d+$/, '');
    const normalized = withoutNumericTail
      .replace(/[-_]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    return normalized ? toTitleCase(normalized) : null;
  } catch {
    return null;
  }
}

export function getListingLabel(listing: ListingLike): string {
  const headline = listing.headline?.trim();
  if (headline) {
    return headline;
  }

  const urlLabel = listing.canonical_url ? humanizeUrlPath(listing.canonical_url) : null;
  if (urlLabel) {
    return urlLabel;
  }

  if (listing.source_listing_id?.trim()) {
    return listing.source_listing_id.trim();
  }

  if (listing.id?.trim()) {
    return `Listing ${listing.id.trim().slice(0, 8)}`;
  }

  return 'Untitled listing';
}

export function getSourceLabel(
  sourceName: string | null | undefined,
  sourceKey: string | null | undefined
): string {
  if (sourceName?.trim()) {
    return sourceName.trim();
  }

  if (sourceKey?.trim()) {
    return sourceKey.trim();
  }

  return 'Source unavailable';
}

export function getClusterLabel(
  canonicalHeadline: string | null | undefined,
  clusterKey: string | null | undefined,
  clusterId: string | null | undefined
): string {
  if (canonicalHeadline?.trim() && canonicalHeadline.trim().toLowerCase() !== 'untitled cluster') {
    return canonicalHeadline.trim();
  }

  if (clusterKey?.trim()) {
    return clusterKey.trim();
  }

  if (clusterId?.trim()) {
    return `Cluster ${clusterId.trim().slice(0, 8)}`;
  }

  return 'Untitled cluster';
}
