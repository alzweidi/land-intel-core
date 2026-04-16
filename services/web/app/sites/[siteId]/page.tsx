import Link from 'next/link';

import {
  Badge,
  DefinitionList,
  EvidenceList,
  PageHeader,
  Panel,
  ProvenanceList,
  StatCard,
  TableShell
} from '@/components/ui';
import { SiteGeometryEditor } from '@/components/site-geometry-editor';
import { SitePlanningMap } from '@/components/site-planning-map';
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

function permissionTone(value: string | undefined): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (!value) {
    return 'neutral';
  }
  if (value === 'NO_ACTIVE_PERMISSION_FOUND') {
    return 'success';
  }
  if (value === 'ACTIVE_EXTANT_PERMISSION_FOUND') {
    return 'danger';
  }
  if (value.includes('UNRESOLVED') || value.includes('REQUIRED') || value.includes('ABSTAIN')) {
    return 'warning';
  }
  return 'accent';
}

function currency(value: number | null): string {
  if (value === null) {
    return 'Unavailable';
  }
  return `£${Math.round(value).toLocaleString('en-GB')}`;
}

export default async function SiteDetailPage({
  params
}: {
  params: Promise<{ siteId: string }> | { siteId: string };
}) {
  const { siteId } = await Promise.resolve(params);
  const result = await getSite(siteId);
  const site = result.item;

  if (!site) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Sites"
          title="Site not found"
          summary={`No site record is available for ${siteId}.`}
          actions={
            <Link className="button button--ghost" href="/sites">
              Back to site list
            </Link>
          }
        />
      </div>
    );
  }

  const currentRevision =
    site.revision_history.find((revision) => revision.is_current) ?? site.revision_history[0];
  const extant = site.extant_permission;
  const scenarios = site.scenarios ?? [];
  const headlineScenario = scenarios.find((scenario) => scenario.is_headline) ?? scenarios[0] ?? null;
  const planningHistory = site.planning_history ?? [];
  const policyFacts = site.policy_facts ?? [];
  const constraintFacts = site.constraint_facts ?? [];
  const sourceCoverage = site.source_coverage ?? [];
  const evidence = site.evidence ?? { for: [], against: [], unknown: [] };
  const rawSourceLinks = [
    ...site.documents.map((document) => ({
      label: document.label,
      value: (
        <a className="inline-link" href={document.href} rel="noreferrer" target="_blank">
          {document.note}
        </a>
      )
    })),
    ...(site.source_snapshots ?? []).map((snapshot) => ({
      label: snapshot.source_name,
      value: (
        <a className="inline-link" href={snapshot.source_uri} rel="noreferrer" target="_blank">
          {snapshot.source_family}
        </a>
      )
    }))
  ];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Site detail"
        title={site.display_name}
        summary={extant?.summary ?? site.summary ?? 'Confirmed site geometry, planning context, and evidence.'}
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/sites">
              Back to sites
            </Link>
            <Link className="button button--ghost" href={`/sites/${siteId}/scenario-editor`}>
              Open scenario editor
            </Link>
            {headlineScenario &&
            (headlineScenario.status === 'ANALYST_CONFIRMED' ||
              headlineScenario.status === 'AUTO_CONFIRMED') ? (
              <Link
                className="button button--solid"
                href={`/assessments?siteId=${site.site_id}&scenarioId=${headlineScenario.id}`}
              >
                Create assessment
              </Link>
            ) : null}
          </div>
        }
        badges={
          <div className="status-strip">
            <Badge tone={confidenceTone(site.geometry_confidence)}>{site.geometry_confidence}</Badge>
            <Badge tone={permissionTone(extant?.status)}>{extant?.eligibility_status ?? 'UNSCREENED'}</Badge>
            <Badge tone={headlineScenario ? 'accent' : 'warning'}>
              {headlineScenario ? headlineScenario.status : 'No confirmed scenario'}
            </Badge>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard
          tone={confidenceTone(site.geometry_confidence)}
          label="Geometry"
          value={site.geometry_source_type}
          detail={`${site.geometry_confidence} confidence · ${site.site_area_sqm?.toLocaleString('en-GB') ?? 'Area pending'} sqm`}
        />
        <StatCard
          tone={permissionTone(extant?.status)}
          label="Eligibility"
          value={extant?.eligibility_status ?? 'UNSET'}
          detail={extant?.status ?? 'Extant-permission result unavailable'}
        />
        <StatCard
          tone="accent"
          label="Planning context"
          value={String(planningHistory.length)}
          detail={`${policyFacts.length} policy rows · ${constraintFacts.length} constraints`}
        />
        <StatCard
          tone="warning"
          label="Coverage gaps"
          value={String(extant?.coverage_gaps.length ?? sourceCoverage.filter((item) => item.coverage_status !== 'COMPLETE').length)}
          detail="Missing or partial source families stay visible"
        />
      </section>

      <div className="detail-layout">
        <div className="detail-main">
          <Panel
            eyebrow="Planning context"
            title="Map and current geometry"
            note="Indicative overlays only. Site geometry, planning history, policy, and constraints are working evidence layers."
          >
            <SitePlanningMap site={site} />
          </Panel>

          <div className="split-grid">
            <Panel eyebrow="Geometry" title="Revision summary">
              <DefinitionList
                items={[
                  { label: 'Current source type', value: currentRevision?.geom_source_type ?? site.geometry_source_type },
                  { label: 'Current confidence', value: currentRevision?.geom_confidence ?? site.geometry_confidence },
                  { label: 'Current hash', value: currentRevision?.geom_hash ?? 'Unavailable' },
                  { label: 'Area', value: site.site_area_sqm ? `${site.site_area_sqm.toLocaleString('en-GB')} sqm` : 'Unavailable' },
                  { label: 'Revision count', value: String(site.revision_count) },
                  { label: 'Guidance', value: site.geometry_editor_guidance }
                ]}
              />
            </Panel>

            <Panel eyebrow="Borough and titles" title="Deterministic linkage">
              <DefinitionList
                items={[
                  { label: 'Borough / LPA', value: `${site.borough_name} / ${site.controlling_lpa_name}` },
                  { label: 'LPA links', value: String(site.lpa_link_count) },
                  { label: 'Title links', value: String(site.title_link_count) },
                  { label: 'Current listing', value: site.current_listing.headline },
                  { label: 'Current price', value: currency(site.current_price_gbp) },
                  { label: 'Price basis', value: site.current_price_basis_type ?? 'Unavailable' }
                ]}
              />
            </Panel>
          </div>

          <Panel eyebrow="Geometry editor" title="Analyst-editable revision history">
            <SiteGeometryEditor site={site} />
          </Panel>

          <div className="split-grid">
            <Panel eyebrow="Evidence for" title="Supportive evidence">
              <EvidenceList
                emptyLabel="No supportive evidence is currently attached."
                items={evidence.for.map((item) => ({
                  label: item.topic,
                  note: item.claim_text,
                  tone: 'success',
                  meta: (
                    <span className="table-secondary">
                      {item.source_label} · {item.verified_status}
                    </span>
                  )
                }))}
              />
            </Panel>

            <Panel eyebrow="Evidence against" title="Weakening evidence">
              <EvidenceList
                emptyLabel="No weakening evidence is currently attached."
                items={evidence.against.map((item) => ({
                  label: item.topic,
                  note: item.claim_text,
                  tone: 'danger',
                  meta: (
                    <span className="table-secondary">
                      {item.source_label} · {item.verified_status}
                    </span>
                  )
                }))}
              />
            </Panel>
          </div>

          <Panel eyebrow="Unknowns" title="Coverage gaps and unresolved questions">
            <EvidenceList
              emptyLabel="No unknown or gap evidence is currently attached."
              items={evidence.unknown.map((item) => ({
                label: item.topic,
                note: item.claim_text,
                tone: 'warning',
                meta: (
                  <span className="table-secondary">
                    {item.source_label} · {item.verified_status}
                  </span>
                )
              }))}
            />
          </Panel>

          <TableShell
            title="Planning history"
            note="Linked records on or near the site with deterministic match metadata."
          >
            <div className="dense-table">
              <table className="table-shell">
                <thead>
                  <tr>
                    <th>Application</th>
                    <th>Status</th>
                    <th>Decision</th>
                    <th>Match</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {planningHistory.map((record) => (
                    <tr key={record.id}>
                      <td>
                        <div className="table-primary">{record.planning_application.external_ref}</div>
                        <div className="table-secondary">{record.planning_application.proposal_description}</div>
                      </td>
                      <td>
                        <Badge tone="accent">{record.planning_application.status}</Badge>
                        <div className="table-secondary">{record.planning_application.route_normalized ?? 'Route unavailable'}</div>
                      </td>
                      <td>
                        <div className="table-primary">{record.planning_application.decision ?? 'Pending'}</div>
                        <div className="table-secondary">{record.planning_application.decision_date ?? 'No decision date'}</div>
                      </td>
                      <td>
                        <div className="table-primary">{record.link_type}</div>
                        <div className="table-secondary">
                          {record.distance_m ? `${Math.round(record.distance_m)}m` : 'Distance unavailable'} ·{' '}
                          {record.overlap_pct ? `${Math.round(record.overlap_pct)}% overlap` : 'Overlap unavailable'}
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">{record.planning_application.source_system}</div>
                        <div className="table-secondary">{record.match_confidence}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </TableShell>
        </div>

        <div className="detail-rail">
          <Panel eyebrow="Current listing" title="Market evidence" compact>
            <DefinitionList
              compact
              items={[
                { label: 'Listing', value: site.current_listing.headline },
                { label: 'URL', value: site.current_listing.canonical_url },
                { label: 'Status', value: site.current_listing.latest_status },
                { label: 'Observed', value: site.current_listing.observed_at },
                { label: 'Price', value: currency(site.current_price_gbp) },
                { label: 'Price basis', value: site.current_price_basis_type ?? 'Unavailable' }
              ]}
            />
          </Panel>

          <Panel eyebrow="Permission state" title="Extant-permission screen" compact>
            {extant ? (
              <>
                <DefinitionList
                  compact
                  items={[
                    { label: 'Status', value: extant.status },
                    { label: 'Eligibility', value: extant.eligibility_status },
                    { label: 'Manual review', value: extant.manual_review_required ? 'Required' : 'Not required' },
                    { label: 'Reason count', value: String(extant.reasons.length) }
                  ]}
                />
                <div className="mini-list">
                  {extant.reasons.map((reason) => (
                    <div className="mini-list__row" key={reason}>
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="empty-note">No extant-permission result is available.</p>
            )}
          </Panel>

          <Panel eyebrow="Scenarios" title="Current hypotheses" compact>
            <div className="card-stack">
              {scenarios.length === 0 ? (
                <p className="empty-note">No scenarios stored yet.</p>
              ) : (
                scenarios.map((scenario) => (
                  <article className="mini-card" key={scenario.id}>
                    <div className="mini-card__top">
                      <div>
                        <div className="table-primary">
                          {scenario.template_key} · {scenario.units_assumed} units
                        </div>
                        <div className="table-secondary">
                          {scenario.proposal_form} · {scenario.route_assumed}
                        </div>
                      </div>
                      <Badge tone={scenario.is_headline ? 'accent' : 'neutral'}>{scenario.status}</Badge>
                    </div>
                    <div className="table-secondary">{scenario.stale_reason ?? 'Current geometry hash matched at save time.'}</div>
                  </article>
                ))
              )}
            </div>
          </Panel>

          <Panel eyebrow="Titles and LPA" title="Linked evidence" compact>
            <div className="card-stack">
              {site.lpa_links.map((item) => (
                <article className="mini-card" key={item.lpa_code}>
                  <div className="table-primary">{item.lpa_name}</div>
                  <div className="table-secondary">
                    {item.overlap_pct ?? 0}% overlap · {item.controlling ? 'Controlling LPA' : 'Secondary'}
                  </div>
                </article>
              ))}
              {site.title_links.map((item) => (
                <article className="mini-card" key={item.title_ref}>
                  <div className="table-primary">{item.title_number}</div>
                  <div className="table-secondary">
                    {item.address_text} · {item.confidence} confidence
                  </div>
                </article>
              ))}
            </div>
          </Panel>

          <Panel eyebrow="Provenance" title="Raw source links" compact>
            <ProvenanceList items={rawSourceLinks} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
