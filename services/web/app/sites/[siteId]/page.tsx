import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
import { SiteGeometryEditor } from '@/components/site-geometry-editor';
import { getSite } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function confidenceTone(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'HIGH') {
    return 'success';
  }

  if (value === 'MEDIUM') {
    return 'accent';
  }

  if (value === 'LOW') {
    return 'warning';
  }

  return 'danger';
}

export default async function SiteDetailPage({
  params
}: {
  params: { siteId: string };
}) {
  const { siteId } = params;
  const result = await getSite(siteId);
  const site = result.item;

  if (!site) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Phase 2"
          title="Site not found"
          summary={`No site record is available for ${siteId}. The page still renders as a stable empty state.`}
          actions={
            <Link className="button button--ghost" href="/sites">
              Back to site list
            </Link>
          }
        />
      </div>
    );
  }

  const currentRevision = site.revision_history.find((revision) => revision.is_current) ?? site.revision_history[0];
  const titleSummary = site.title_links.map((link) => `${link.title_number} (${link.overlap_pct ?? 0}%)`).join(' · ');

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 2"
        title={site.display_name}
        summary={site.summary || site.description_text}
        actions={
          <Link className="button button--ghost" href="/sites">
            Back to site list
          </Link>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone="accent">Geometry</Badge>
          <div className="stat-value">{site.geometry_source_type}</div>
          <p className="stat-detail">{site.geometry_confidence} confidence, revision {site.revision_count}</p>
        </div>
        <div className="stat-card">
          <Badge tone="success">Borough</Badge>
          <div className="stat-value">{site.borough_name}</div>
          <p className="stat-detail">{site.controlling_lpa_name} is the controlling LPA in this record</p>
        </div>
        <div className="stat-card">
          <Badge tone="warning">Warnings</Badge>
          <div className="stat-value">{site.warnings.length}</div>
          <p className="stat-detail">Warnings remain visible and cannot be hidden by the editor</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">Documents</Badge>
          <div className="stat-value">{site.documents.length}</div>
          <p className="stat-detail">Raw source docs remain immutable links only</p>
        </div>
      </section>

      <div className="split-grid">
        <Panel eyebrow="Listing summary" title="Current evidence">
          <DefinitionList
            items={[
              { label: 'Cluster', value: site.cluster_key },
              { label: 'Current listing', value: site.current_listing_headline },
              { label: 'Status', value: site.current_listing.latest_status },
              {
                label: 'Price',
                value: site.current_price_gbp === null ? 'Pending' : `£${site.current_price_gbp.toLocaleString('en-GB')}`
              },
              { label: 'Source snapshot', value: site.source_snapshot_id },
              {
                label: 'Source snapshot URL',
                value: site.source_snapshot_url ? (
                  <a className="inline-link" href={site.source_snapshot_url} target="_blank" rel="noreferrer">
                    Open raw snapshot
                  </a>
                ) : (
                  'Unavailable'
                )
              }
            ]}
          />
          <div className="mini-list" style={{ marginTop: 16 }}>
            {site.warnings.map((warning) => (
              <div className="mini-list__row" key={warning}>
                <span>{warning}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Geometry" title="Edit draft polygon">
          <SiteGeometryEditor site={site} />
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Borough" title="LPA assignment">
          <DefinitionList
            items={[
              { label: 'Controlling borough', value: site.borough_name },
              { label: 'Controlling LPA', value: site.controlling_lpa_name },
              {
                label: 'Manual clipping',
                value: site.lpa_links.some((link) => link.manual_clip_required) ? 'Required for part of this candidate' : 'Not required'
              },
              {
                label: 'Cross-LPA overlap',
                value: site.lpa_links.some((link) => link.cross_lpa_flag) ? 'Flagged' : 'None'
              }
            ]}
          />
          <div className="card-stack" style={{ marginTop: 16 }}>
            {site.lpa_links.map((link) => (
              <article className="mini-card" key={link.lpa_code}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{link.lpa_name}</div>
                    <div className="table-secondary">{link.lpa_code}</div>
                  </div>
                  <Badge tone={link.controlling ? 'success' : 'warning'}>{link.controlling ? 'Controlling' : 'Cross-LPA'}</Badge>
                </div>
                <div className="mini-card__footer">
                  {link.overlap_pct === null ? 'Overlap pending' : `${link.overlap_pct.toFixed(1)}% · ${link.overlap_sqm?.toLocaleString('en-GB') ?? '0'} sqm`}
                </div>
                <div className="table-secondary">{link.note}</div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Title linkage" title="Indicative HMLR evidence">
          <p className="empty-note">
            Title polygons remain indicative evidence only. They help confirm the site geometry but they are not treated as legal parcel truth.
          </p>
          <div className="mini-list" style={{ marginTop: 16 }}>
            {site.title_links.map((link) => (
              <div className="mini-list__row" key={link.title_ref}>
                <div>
                  <div className="table-primary">{link.title_number}</div>
                  <div className="table-secondary">{link.address_text}</div>
                  <div className="table-secondary">{link.evidence_note}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <Badge tone={confidenceTone(link.confidence)}>{link.confidence}</Badge>
                  <div className="table-secondary">{link.overlap_pct === null ? 'Overlap pending' : `${link.overlap_pct.toFixed(1)}% · ${link.overlap_sqm?.toLocaleString('en-GB') ?? '0'} sqm`}</div>
                  <div className="table-secondary">{link.is_primary ? 'Primary link' : 'Secondary link'}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="table-secondary" style={{ marginTop: 12 }}>
            {titleSummary || 'No title links are available for this site.'}
          </div>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Source documents" title="Raw source links">
          <div className="mini-list">
            {site.documents.map((document) => (
              <div className="mini-list__row" key={document.id}>
                <div>
                  <div className="table-primary">
                    <a className="inline-link" href={document.href} target="_blank" rel="noreferrer">
                      {document.label}
                    </a>
                  </div>
                  <div className="table-secondary">
                    {document.doc_type} · {document.mime_type}
                  </div>
                  <div className="table-secondary">{document.note}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <Badge tone={document.extraction_status === 'EXTRACTED' ? 'success' : 'warning'}>{document.extraction_status ?? 'UNKNOWN'}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Revision history" title="Geometry revision summary">
          <div className="card-stack">
            {site.revision_history.map((revision) => (
              <article className="mini-card" key={revision.revision_id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{revision.revision_id}</div>
                    <div className="table-secondary">{revision.created_at} · {revision.created_by}</div>
                  </div>
                  <Badge tone={revision.is_current ? 'success' : 'neutral'}>{revision.is_current ? 'Current' : 'Previous'}</Badge>
                </div>
                <DefinitionList
                  items={[
                    { label: 'Source type', value: revision.geom_source_type },
                    { label: 'Confidence', value: revision.geom_confidence },
                    { label: 'Area', value: revision.site_area_sqm === null ? 'Pending' : `${revision.site_area_sqm.toLocaleString('en-GB')} sqm` },
                    { label: 'Hash', value: revision.geom_hash },
                    { label: 'Note', value: revision.note || 'No note supplied' }
                  ]}
                />
              </article>
            ))}
          </div>
          {currentRevision ? (
            <div className="table-secondary" style={{ marginTop: 12 }}>
              Current revision: {currentRevision.revision_id}
            </div>
          ) : null}
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Market" title="Linked market events">
          <div className="mini-list">
            {site.market_events.map((event) => (
              <div className="mini-list__row" key={event.event_id}>
                <div>
                  <div className="table-primary">{event.event_type}</div>
                  <div className="table-secondary">{event.event_at}</div>
                  <div className="table-secondary">{event.note}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="table-primary">
                    {event.price_gbp === null ? 'Price pending' : `£${event.price_gbp.toLocaleString('en-GB')}`}
                  </div>
                  <div className="table-secondary">{event.price_basis_type ?? 'No basis type'}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Warnings" title="Visible caveats">
          <div className="mini-list">
            {site.review_flags.map((flag) => (
              <div className="mini-list__row" key={flag}>
                <span>{flag}</span>
              </div>
            ))}
          </div>
          <div className="table-secondary" style={{ marginTop: 12 }}>
            {site.geometry_editor_guidance}
          </div>
        </Panel>
      </div>
    </div>
  );
}
