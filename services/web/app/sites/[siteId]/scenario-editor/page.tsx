import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
import { scenarioRows } from '@/lib/mock-data';

export default function ScenarioEditorPage({
  params
}: {
  params: { siteId: string };
}) {
  const { siteId } = params;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Scenario editor"
        title={`Scenario shell for ${siteId}`}
        summary="The editor surface is present, but it does not normalize or score scenarios yet. It simply reserves the layout needed for later confirmation flows."
        actions={
          <Link className="button button--ghost" href={`/sites/${siteId}`}>
            Back to site detail
          </Link>
        }
      />

      <div className="split-grid">
        <Panel eyebrow="Templates" title="Enabled v1 shells">
          <div className="card-stack">
            {scenarioRows.map((scenario) => (
              <article className="mini-card" key={scenario.key}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{scenario.key}</div>
                    <div className="table-secondary">{scenario.note}</div>
                  </div>
                  <Badge tone={scenario.status === 'ANALYST_CONFIRMED' ? 'success' : scenario.status === 'ANALYST_REQUIRED' ? 'warning' : 'accent'}>
                    {scenario.status}
                  </Badge>
                </div>
                <DefinitionList
                  items={[
                    { label: 'Units', value: scenario.units },
                    { label: 'Route', value: scenario.route }
                  ]}
                />
              </article>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Editor" title="Scenario parameters">
          <DefinitionList
            items={[
              { label: 'Template key', value: 'resi_5_9_full' },
              { label: 'Proposal form', value: 'REDEVELOPMENT' },
              { label: 'Units assumed', value: '7' },
              { label: 'Route assumed', value: 'FULL' },
              { label: 'Scenario source', value: 'ANALYST' }
            ]}
          />
        </Panel>
      </div>
    </div>
  );
}
