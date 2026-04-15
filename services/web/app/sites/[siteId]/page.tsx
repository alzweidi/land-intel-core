import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
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

  if (value.includes('MANUAL_REVIEW') || value.includes('UNRESOLVED') || value.includes('REQUIRED')) {
    return 'warning';
  }

  return 'accent';
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
          eyebrow="Phase 5A"
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

  const currentRevision =
    site.revision_history.find((revision) => revision.is_current) ?? site.revision_history[0];
  const extant = site.extant_permission;
  const evidence = site.evidence ?? { for: [], against: [], unknown: [] };
  const sourceCoverage = site.source_coverage ?? [];
  const planningHistory = site.planning_history ?? [];
  const brownfieldStates = site.brownfield_states ?? [];
  const policyFacts = site.policy_facts ?? [];
  const constraintFacts = site.constraint_facts ?? [];
  const scenarios = site.scenarios ?? [];
  const headlineScenario = scenarios.find((scenario) => scenario.is_headline) ?? scenarios[0] ?? null;
  const sourceSnapshots = site.source_snapshots ?? [];
  const rawLinks = [
    ...site.documents.map((document) => ({
      href: document.href,
      label: document.label,
      note: document.note
    })),
    ...planningHistory.flatMap((record) =>
      record.planning_application.documents.map((document) => ({
        href: document.doc_url,
        label: `${record.planning_application.external_ref} · ${document.doc_type}`,
        note: record.planning_application.source_system
      }))
    ),
    ...sourceSnapshots
      .map((snapshot) => ({
        href: snapshot.source_uri,
        label: snapshot.source_name,
        note: snapshot.source_family
      }))
      .filter((item) => item.href)
  ].filter((item, index, items) => items.findIndex((candidate) => candidate.href === item.href) === index);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 5A"
        title={site.display_name}
        summary={
          extant?.summary ??
          site.summary ??
          'Planning context, source coverage, and evidence are visible below.'
        }
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/sites">
              Back to site list
            </Link>
            <Link className="button button--ghost" href={`/sites/${siteId}/scenario-editor`}>
              Scenario editor
            </Link>
            {headlineScenario &&
            (headlineScenario.status === 'ANALYST_CONFIRMED' ||
              headlineScenario.status === 'AUTO_CONFIRMED') ? (
              <Link
                className="button button--ghost"
                href={`/assessments?siteId=${site.site_id}&scenarioId=${headlineScenario.id}`}
              >
                Create assessment
              </Link>
            ) : null}
          </div>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone="accent">Geometry</Badge>
          <div className="stat-value">{site.geometry_source_type}</div>
          <p className="stat-detail">
            {site.geometry_confidence} confidence, revision {site.revision_count}
          </p>
        </div>
        <div className="stat-card">
          <Badge tone={permissionTone(extant?.status)}>Permission</Badge>
          <div className="stat-value">{extant?.status ?? 'UNKNOWN'}</div>
          <p className="stat-detail">{extant?.eligibility_status ?? 'UNSET'} eligibility outcome</p>
        </div>
        <div className="stat-card">
          <Badge tone="warning">Coverage gaps</Badge>
          <div className="stat-value">
            {extant?.coverage_gaps.length ?? sourceCoverage.filter((item) => item.coverage_status !== 'COMPLETE').length}
          </div>
          <p className="stat-detail">Missing or partial source families stay visible</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">Planning context</Badge>
          <div className="stat-value">{planningHistory.length}</div>
          <p className="stat-detail">
            {policyFacts.length} policy facts · {constraintFacts.length} constraints
          </p>
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
                value:
                  site.current_price_gbp === null
                    ? 'Pending'
                    : `£${site.current_price_gbp.toLocaleString('en-GB')}`
              },
              { label: 'Address', value: site.address_text || 'Not parsed' },
              { label: 'Borough / LPA', value: `${site.borough_name} / ${site.controlling_lpa_name}` }
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

        <Panel eyebrow="Permission state" title="Extant-permission screen">
          {extant ? (
            <>
              <div className="mini-card">
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{extant.status}</div>
                    <div className="table-secondary">{extant.eligibility_status}</div>
                  </div>
                  <Badge tone={permissionTone(extant.status)}>
                    {extant.manual_review_required ? 'Manual review' : 'Deterministic'}
                  </Badge>
                </div>
                <div className="table-secondary">{extant.summary}</div>
              </div>
              <div className="mini-list" style={{ marginTop: 16 }}>
                {extant.reasons.map((reason) => (
                  <div className="mini-list__row" key={reason}>
                    <span>{reason}</span>
                  </div>
                ))}
                {extant.coverage_gaps.map((gap) => (
                  <div className="mini-list__row" key={gap.code}>
                    <div>
                      <div className="table-primary">{gap.code}</div>
                      <div className="table-secondary">{gap.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="empty-note">No extant-permission result is available for this site.</p>
          )}
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Scenarios" title="Scenario hypotheses">
          <div className="button-row" style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <Link className="button button--ghost" href={`/sites/${siteId}/scenario-editor`}>
              Open scenario editor
            </Link>
          </div>
          <div className="card-stack">
            {scenarios.length === 0 ? (
              <p className="empty-note">No scenarios are stored yet. Open the editor to seed suggestions.</p>
            ) : (
              scenarios.map((scenario) => (
                <article className="mini-card" key={scenario.id}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">
                        {scenario.template_key} · {scenario.units_assumed} units
                      </div>
                      <div className="table-secondary">
                        {scenario.proposal_form} · {scenario.route_assumed} · {scenario.height_band_assumed}
                      </div>
                    </div>
                    <Badge tone={permissionTone(scenario.status)}>
                      {scenario.status}
                    </Badge>
                  </div>
                  <div className="table-secondary">
                    {scenario.is_headline ? 'Headline scenario' : 'Supporting scenario'}
                    {scenario.stale_reason ? ` · ${scenario.stale_reason}` : ''}
                  </div>
                </article>
              ))
            )}
          </div>
        </Panel>

        <Panel eyebrow="Headline scenario" title="Current hypothesis">
          {headlineScenario ? (
            <DefinitionList
              items={[
                { label: 'Template', value: headlineScenario.template_key },
                { label: 'Status', value: headlineScenario.status },
                { label: 'Units', value: String(headlineScenario.units_assumed) },
                { label: 'Route', value: headlineScenario.route_assumed },
                { label: 'Proposal form', value: headlineScenario.proposal_form },
                {
                  label: 'Geometry hash',
                  value: headlineScenario.red_line_geom_hash.slice(0, 12)
                }
              ]}
            />
          ) : (
            <p className="empty-note">No headline scenario is available yet.</p>
          )}
        </Panel>
      </div>

      <div className="split-grid">
        <Panel
          eyebrow="Planning map"
          title="Planning context map"
          note="Site geometry, planning history, policy overlays, and constraint layers are working overlays only. Indicative geometries are not authoritative legal boundaries."
        >
          <SitePlanningMap site={site} />
        </Panel>

        <Panel eyebrow="Coverage" title="Source coverage and baseline pack">
          <DefinitionList
            items={[
              { label: 'Baseline pack', value: site.baseline_pack?.version ?? 'Not loaded' },
              { label: 'Baseline status', value: site.baseline_pack?.status ?? 'Missing' },
              {
                label: 'Rulepacks',
                value: String(site.baseline_pack?.rulepacks.length ?? 0)
              },
              {
                label: 'Manual review',
                value: extant?.manual_review_required ? 'Required' : 'Not currently required'
              }
            ]}
          />
          <div className="card-stack" style={{ marginTop: 16 }}>
            {sourceCoverage.map((coverage) => (
              <article className="mini-card" key={coverage.id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{coverage.source_family}</div>
                    <div className="table-secondary">{coverage.freshness_status}</div>
                  </div>
                  <Badge
                    tone={coverage.coverage_status === 'COMPLETE' ? 'success' : 'warning'}
                  >
                    {coverage.coverage_status}
                  </Badge>
                </div>
                <div className="table-secondary">{coverage.coverage_note ?? 'No note recorded.'}</div>
                {coverage.gap_reason ? (
                  <div className="table-secondary" style={{ marginTop: 8 }}>
                    Gap reason: {coverage.gap_reason}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Planning history" title="Applications on or near site">
          <div className="card-stack">
            {planningHistory.map((record) => (
              <article className="mini-card" key={record.id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{record.planning_application.external_ref}</div>
                    <div className="table-secondary">
                      {record.planning_application.source_system} · {record.planning_application.status}
                    </div>
                  </div>
                  <Badge tone={confidenceTone(record.match_confidence)}>
                    {record.match_confidence}
                  </Badge>
                </div>
                <div className="table-secondary">{record.planning_application.proposal_description}</div>
                <div className="table-secondary" style={{ marginTop: 8 }}>
                  {record.link_type}
                  {record.overlap_pct !== null ? ` · ${record.overlap_pct.toFixed(1)}% overlap` : ''}
                  {record.distance_m !== null ? ` · ${record.distance_m.toFixed(1)}m away` : ''}
                </div>
                <div className="mini-list" style={{ marginTop: 10 }}>
                  {record.planning_application.documents.map((document) => (
                    <div className="mini-list__row" key={document.id}>
                      <a className="inline-link" href={document.doc_url} target="_blank" rel="noreferrer">
                        {document.doc_type}
                      </a>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Policy and constraints" title="Intersecting layers">
          <div className="card-stack">
            {policyFacts.map((fact) => (
              <article className="mini-card" key={fact.id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{fact.policy_area.name}</div>
                    <div className="table-secondary">
                      {fact.policy_area.policy_family} · {fact.policy_area.policy_code}
                    </div>
                  </div>
                  <Badge tone={fact.importance === 'HIGH' ? 'success' : 'accent'}>
                    {fact.importance}
                  </Badge>
                </div>
                <div className="table-secondary">{fact.relation_type}</div>
              </article>
            ))}
            {constraintFacts.map((fact) => (
              <article className="mini-card" key={fact.id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{fact.constraint_feature.feature_subtype}</div>
                    <div className="table-secondary">
                      {fact.constraint_feature.feature_family} · {fact.constraint_feature.authority_level}
                    </div>
                  </div>
                  <Badge tone={fact.severity === 'HIGH' ? 'danger' : 'warning'}>
                    {fact.severity}
                  </Badge>
                </div>
                <div className="table-secondary">{fact.constraint_feature.legal_status ?? 'Status not supplied'}</div>
              </article>
            ))}
            {brownfieldStates.map((state) => (
              <article className="mini-card" key={state.id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{state.external_ref}</div>
                    <div className="table-secondary">{state.part}</div>
                  </div>
                  <Badge tone={state.part === 'PART_2' ? 'warning' : 'neutral'}>
                    {state.pip_status ?? state.tdc_status ?? 'Informative'}
                  </Badge>
                </div>
                <div className="table-secondary">
                  PiP {state.pip_status ?? 'none'} · TDC {state.tdc_status ?? 'none'}
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Evidence FOR" title={headlineScenario ? `Supportive evidence · ${headlineScenario.template_key}` : 'Supportive evidence'}>
          <div className="mini-list">
            {evidence.for.map((item) => (
              <div className="mini-list__row" key={`${item.topic}-${item.source_label}-${item.claim_text}`}>
                <div>
                  <div className="table-primary">{item.claim_text}</div>
                  <div className="table-secondary">
                    {item.topic} · {item.importance} · {item.source_label}
                  </div>
                  {item.source_url ? (
                    <a className="inline-link" href={item.source_url} target="_blank" rel="noreferrer">
                      Open source
                    </a>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Evidence AGAINST" title={headlineScenario ? `Constraining evidence · ${headlineScenario.template_key}` : 'Constraining evidence'}>
          <div className="mini-list">
            {evidence.against.map((item) => (
              <div className="mini-list__row" key={`${item.topic}-${item.source_label}-${item.claim_text}`}>
                <div>
                  <div className="table-primary">{item.claim_text}</div>
                  <div className="table-secondary">
                    {item.topic} · {item.importance} · {item.source_label}
                  </div>
                  {item.source_url ? (
                    <a className="inline-link" href={item.source_url} target="_blank" rel="noreferrer">
                      Open source
                    </a>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Evidence UNKNOWN" title={headlineScenario ? `Coverage caveats · ${headlineScenario.template_key}` : 'Coverage caveats and manual-review items'}>
          <div className="mini-list">
            {evidence.unknown.map((item) => (
              <div className="mini-list__row" key={`${item.topic}-${item.source_label}-${item.claim_text}`}>
                <div>
                  <div className="table-primary">{item.claim_text}</div>
                  <div className="table-secondary">
                    {item.topic} · {item.importance} · {item.source_label}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Raw sources" title="Source snapshots and raw document links">
          <div className="mini-list">
            {rawLinks.map((link) => (
              <div className="mini-list__row" key={link.href}>
                <div>
                  <a className="inline-link" href={link.href} target="_blank" rel="noreferrer">
                    {link.label}
                  </a>
                  <div className="table-secondary">{link.note}</div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Geometry" title="Edit draft polygon">
          <SiteGeometryEditor site={site} />
        </Panel>

        <Panel eyebrow="Revision history" title="Geometry revision summary">
          <div className="card-stack">
            {site.revision_history.map((revision) => (
              <article className="mini-card" key={revision.revision_id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{revision.revision_id}</div>
                    <div className="table-secondary">
                      {revision.created_at} · {revision.created_by}
                    </div>
                  </div>
                  <Badge tone={revision.is_current ? 'success' : 'neutral'}>
                    {revision.is_current ? 'Current' : 'Previous'}
                  </Badge>
                </div>
                <DefinitionList
                  items={[
                    { label: 'Source type', value: revision.geom_source_type },
                    { label: 'Confidence', value: revision.geom_confidence },
                    {
                      label: 'Area',
                      value:
                        revision.site_area_sqm === null
                          ? 'Pending'
                          : `${revision.site_area_sqm.toLocaleString('en-GB')} sqm`
                    },
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
    </div>
  );
}
