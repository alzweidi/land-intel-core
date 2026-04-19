# Operations Runbook

This deployment is private and low-ops by design:

- Netlify hosts the frontend
- one VPS runs `api`, `worker`, `scheduler`, and `caddy`
- Supabase hosts Postgres/PostGIS, Storage, and future Auth readiness

## Current Auth Posture

- Netlify site protection and backend basic auth are the effective deployment boundary today.
- The web app still signs users in through the built-in local role adapter in `services/web/lib/auth/local-adapter.ts`.
- Reviewer/admin authorization is derived from the signed app session. Backend basic auth protects the VPS API origin, but it does not by itself grant reviewer/admin privileges.
- Do not treat the current app login as a production-grade auth control until it is replaced with a real identity provider flow.
- `/admin/health` is the primary operator dashboard. `/data-health` remains a shell-only placeholder route and should not be used as the canonical health surface.

## Operator API Session

For privileged API calls, authenticate through the app proxy and reuse the signed cookie:

```bash
export OPS_COOKIE_JAR=/tmp/landintel-admin.cookies
curl -c "${OPS_COOKIE_JAR}" \
  -X POST https://app.<domain>/api/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=admin@landintel.local' \
  --data-urlencode 'password=admin-demo' \
  --data-urlencode 'next=/admin/health'
```

Use `https://app.<domain>/api/...` for privileged checks after that. Do not rely on body fields such as `actor_role`; they are audit metadata only.

## Daily Checks

On the VPS:

```bash
cd /srv/land-intel-core
docker compose -f infra/compose/docker-compose.vps.yml ps
docker compose -f infra/compose/docker-compose.vps.yml logs --tail=100 api
docker compose -f infra/compose/docker-compose.vps.yml logs --tail=100 worker
docker compose -f infra/compose/docker-compose.vps.yml logs --tail=100 scheduler
```

From your workstation:

```bash
export BACKEND_BASIC_AUTH_USER='<backend-basic-auth-user>'
export BACKEND_BASIC_AUTH_PASSWORD='<backend-basic-auth-password>'
export APP_AUTH_EMAIL='<reviewer-or-admin-email>'
export APP_AUTH_PASSWORD='<reviewer-or-admin-password>'
./scripts/smoke_prod.sh https://app.<domain> https://api.<domain>
```

Inspect the health surfaces:

```bash
curl -b "${OPS_COOKIE_JAR}" https://app.<domain>/api/health/data
curl -b "${OPS_COOKIE_JAR}" https://app.<domain>/api/health/model
```

## Weekly Checks

1. Run a Storage backup:

```bash
export SUPABASE_URL='https://<project-ref>.supabase.co'
export SUPABASE_SERVICE_ROLE_KEY='<service-role-key>'
export SUPABASE_STORAGE_BUCKET='raw-assets'
./scripts/backup_storage.sh ./backups
```

2. Confirm Supabase database backup/PITR posture in the dashboard.
3. Review stale coverage, incidents, and blocked scopes in the admin UI.
4. Review `manual_review_required`, `blocked`, and `Hold` rates for anything unexpected.

## Keep Visible Probability Hidden By Default

Leave all active scopes at `HIDDEN_ONLY`.

Check model releases:

```bash
curl -b "${OPS_COOKIE_JAR}" https://app.<domain>/api/admin/model-releases
```

If you need to force a scope back to hidden-only:

```bash
curl -b "${OPS_COOKIE_JAR}" \
  -X POST https://app.<domain>/api/admin/release-scopes/<scope_key>/visibility \
  -H 'Content-Type: application/json' \
  -d '{
    "requested_by": "ops",
    "visibility_mode": "HIDDEN_ONLY",
    "reason": "Return scope to the default non-speaking state."
  }'
```

## Activate A Scope Safely Later

Do not enable `VISIBLE_REVIEWER_ONLY` unless all of these are true:

1. the scope is borough-scoped
2. the borough baseline pack is signed off
3. the borough rulepack for the template is signed off
4. the model release is active and not `NOT_READY`
5. no incident is open for the scope

Then switch the scope:

```bash
curl -b "${OPS_COOKIE_JAR}" \
  -X POST https://app.<domain>/api/admin/release-scopes/<scope_key>/visibility \
  -H 'Content-Type: application/json' \
  -d '{
    "requested_by": "ops",
    "visibility_mode": "VISIBLE_REVIEWER_ONLY",
    "reason": "Signed-off reviewer-only pilot enablement."
  }'
```

Immediately verify:

1. reviewer/admin contexts can see the intended reviewer-only output
2. standard analyst contexts remain redacted or non-speaking
3. no incident is open

## Recover From Failed Migration Or Bad Release

### Bad release, but DB is fine

1. Retire or roll back the release:

```bash
curl -b "${OPS_COOKIE_JAR}" \
  -X POST https://app.<domain>/api/admin/model-releases/<release_id>/retire \
  -H 'Content-Type: application/json' \
  -d '{
    "requested_by": "ops"
  }'
```

2. If needed, block visibility immediately:

```bash
curl -b "${OPS_COOKIE_JAR}" \
  -X POST https://app.<domain>/api/admin/release-scopes/<scope_key>/incident \
  -H 'Content-Type: application/json' \
  -d '{
    "requested_by": "ops",
    "action": "OPEN",
    "reason": "Kill visible publication while investigating."
  }'
```

3. Redeploy the last known good revision from your workstation:

```bash
git checkout <last-known-good-commit>
./scripts/deploy_prod.sh deploy@<vps-ip> /srv/land-intel-core
```

### Migration failed or damaged state

1. Stop backend services if you need a clean hold:

```bash
ssh deploy@<vps-ip> '
  cd /srv/land-intel-core &&
  docker compose -f infra/compose/docker-compose.vps.yml down
'
```

2. Restore Supabase Postgres from PITR or your approved backup path.
3. Redeploy the last known good revision.
4. Rerun:

```bash
export BACKEND_BASIC_AUTH_USER='<backend-basic-auth-user>'
export BACKEND_BASIC_AUTH_PASSWORD='<backend-basic-auth-password>'
export APP_AUTH_EMAIL='<reviewer-or-admin-email>'
export APP_AUTH_PASSWORD='<reviewer-or-admin-password>'
./scripts/smoke_prod.sh https://app.<domain> https://api.<domain>
```

## What Remains Operational Rather Than Code-Complete

- Netlify site protection setup is still a manual operator step.
- Supabase Auth is provisioned in the target architecture, but the current app still uses the built-in local role adapter instead of enforcing Supabase sessions/roles.
- Reviewer-visible rollout remains a manual signoff decision.
- Database restore and PITR operations remain Supabase-admin tasks.
