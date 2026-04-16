import Link from 'next/link';

import { PageHeader } from '@/components/ui';
import { SiteScenarioEditor } from '@/components/site-scenario-editor';
import { getSite, getSiteScenarios } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

export default async function ScenarioEditorPage({
  params
}: {
  params: Promise<{ siteId: string }> | { siteId: string };
}) {
  const { siteId } = await Promise.resolve(params);
  const [siteResult, scenariosResult] = await Promise.all([
    getSite(siteId),
    getSiteScenarios(siteId)
  ]);

  if (!siteResult.item) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Scenarios"
          title="Scenario editor unavailable"
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

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Scenario editor"
        title={`Scenario editor · ${siteResult.item.display_name}`}
        summary="Generate deterministic scenario hypotheses, compare assumptions side by side, and confirm or reject them with auditable review notes. No scoring or probability is shown here."
        actions={
          <div className="button-row" style={{ display: 'flex', gap: 12 }}>
            <Link className="button button--ghost" href={`/sites/${siteId}`}>
              Back to site detail
            </Link>
            <Link className="button button--ghost" href="/scenarios">
              Scenario index
            </Link>
          </div>
        }
      />
      <SiteScenarioEditor
        initialScenarios={scenariosResult.items}
        site={siteResult.item}
      />
    </div>
  );
}
