# Production Deployment

This repo now has the minimum deployment assets for a private single-owner production deployment:

- Supabase for Postgres/PostGIS, Storage, and future Auth readiness
- one VPS for `api`, `worker`, `scheduler`, and `caddy`
- Netlify for `services/web`

The production privacy model is:

- Netlify site protection on `app.<domain>`
- Caddy basic auth on `api.<domain>` for `/api/*`
- the current Next.js app still uses the built-in local role accounts in `services/web/lib/auth/local-adapter.ts` with a signed cookie session, so site protection and backend basic auth remain the real deployment boundary until app auth is replaced

## Commands To Run First

On your workstation, before doing anything else:

```bash
cp .env.production.example .env.production
cp .env.netlify.example .env.netlify
```

Then generate the backend basic-auth password hash on any machine with Docker:

```bash
docker run --rm caddy:2.10-alpine caddy hash-password --plaintext 'change-this-password'
```

Put the resulting hash into `.env.production` as `BACKEND_BASIC_AUTH_PASSWORD_HASH`.

## 1. Supabase Project Setup

Create a new Supabase project in the region closest to the VPS.

### 1.1 Enable PostGIS

In the Supabase SQL editor, run:

```sql
create extension if not exists postgis;
```

### 1.2 Create the private Storage bucket

In the Supabase dashboard:

1. Open `Storage`.
2. Create bucket `raw-assets`.
3. Set it to private.

### 1.3 Collect production credentials

From the Supabase dashboard, collect:

- project URL, for `SUPABASE_URL`
- service role key, for `SUPABASE_SERVICE_ROLE_KEY`
- anon key, for `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- auth JWKS URL:
  - `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`
- pooled Postgres connection string for `DATABASE_URL`

Use the pooled connection string format:

```text
postgresql+psycopg://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

### 1.4 Prepare one owner account and close open signup

In the Supabase dashboard:

1. Open `Authentication -> Providers`.
2. Disable any open signup mode you do not want.
3. Open `Authentication -> Users`.
4. Create or invite exactly one owner account for future readiness.

Do this now even though the current app does not yet enforce Supabase Auth.

## 2. VPS Setup

The steps below assume a fresh Ubuntu/Debian-style VPS.

### 2.1 Log in as root

```bash
ssh root@<vps-ip>
```

### 2.2 Install Docker, Compose plugin, rsync, jq, and unzip

On the VPS:

```bash
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release rsync jq unzip
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
  | tee /etc/apt/sources.list.d/docker.list >/dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker --version
docker compose version
```

### 2.3 Create a deploy user and switch to SSH keys

On the VPS:

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
```

On your workstation, copy your public key:

```bash
ssh-copy-id deploy@<vps-ip>
```

Then verify:

```bash
ssh deploy@<vps-ip>
docker ps
```

After key auth works, disable password SSH login in `/etc/ssh/sshd_config` and restart SSH:

```bash
sudo sed -i 's/^#\\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
```

### 2.4 Create the deployment directory

On the VPS:

```bash
sudo mkdir -p /srv/land-intel-core
sudo chown deploy:deploy /srv/land-intel-core
```

## 3. DNS Setup

Create these records:

- `A` record:
  - host: `api`
  - value: `<vps-ip>`
- Netlify custom domain:
  - host: `app`
  - target: the Netlify-assigned hostname for your site

Wait until both resolve publicly.

## 4. Backend Environment Setup

On your workstation, fill `.env.production` with real values from Supabase and your chosen domain:

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+psycopg://...
STORAGE_BACKEND=supabase
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_BUCKET=raw-assets
SUPABASE_AUTH_JWKS_URL=https://.../auth/v1/.well-known/jwks.json
API_DOMAIN=api.example.com
ACME_EMAIL=ops@example.com
BACKEND_BASIC_AUTH_USER=backend-ops
BACKEND_BASIC_AUTH_PASSWORD_HASH=<caddy-password-hash>
```

Copy it to the VPS:

```bash
scp .env.production deploy@<vps-ip>:/srv/land-intel-core/.env.production
```

## 5. Netlify Setup

Create a Netlify site from this repo with:

- base directory: `services/web`
- build command: `npm run build`
- publish directory: `.next`

Set public env vars from `.env.netlify.example`:

```text
NEXT_PUBLIC_APP_NAME
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_API_BASE_URL=https://app.<domain>
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_MAP_STYLE_URL
```

`NEXT_PUBLIC_API_BASE_URL` should stay on `https://app.<domain>`, not `https://api.<domain>`. Browser requests go through the same-origin Next.js proxy route and should not call the protected VPS API origin directly.

Set these Netlify secret env vars as well:

```text
BACKEND_API_ORIGIN=https://api.<domain>
BACKEND_BASIC_AUTH_USER=<same value as VPS>
BACKEND_BASIC_AUTH_PASSWORD=<plaintext password used to generate the Caddy hash>
LANDINTEL_WEB_AUTH_SECRET=<openssl rand -base64 32>
LANDINTEL_WEB_PUBLIC_ORIGIN=https://app.<domain>
```

`BACKEND_API_ORIGIN` is the upstream target for `services/web/app/api/[...path]/route.ts`, which adds backend basic auth and forwards browser-originated API traffic to the VPS API.

Do not leave `LANDINTEL_WEB_AUTH_SECRET` unset in production. The local fallback is only acceptable for local/dev.

Enable Netlify site protection so the frontend stays private:

1. Open Netlify site settings.
2. Open site access / password protection.
3. Turn site protection on.
4. Save the single-owner password.

The app login behind that outer layer is still the built-in role adapter today. Treat it as an internal convenience, not a production-grade auth boundary.

## 6. First Deploy

From your workstation:

```bash
./scripts/deploy_prod.sh deploy@<vps-ip> /srv/land-intel-core
```

Then trigger a Netlify deploy:

- use the Netlify UI, or
- run your normal Netlify deploy flow if you already have one

## 7. Manual Migration Run

If you need to rerun migrations manually on the VPS:

```bash
ssh deploy@<vps-ip> '
  cd /srv/land-intel-core &&
  docker compose -f infra/compose/docker-compose.vps.yml run --rm api alembic upgrade head
'
```

## 8. Smoke Checks

From your workstation:

```bash
export BACKEND_BASIC_AUTH_USER='<backend-basic-auth-user>'
export BACKEND_BASIC_AUTH_PASSWORD='<backend-basic-auth-password>'
./scripts/smoke_prod.sh https://app.<domain> https://api.<domain>
```

Then manually confirm:

1. Open `https://app.<domain>`.
2. Pass Netlify site protection.
3. Log into the private frontend.
4. Verify the dashboard loads and calls succeed through the same-origin frontend proxy.

## 9. Rollback

### 9.1 Code rollback

On your workstation, check out the last known good revision and redeploy it:

```bash
git checkout <last-known-good-commit>
./scripts/deploy_prod.sh deploy@<vps-ip> /srv/land-intel-core
```

### 9.2 Failed migration rollback

If a migration fails or damages runtime behavior:

1. Stop making changes.
2. Disable any visible scope if needed using the existing admin controls.
3. Restore Supabase Postgres from PITR or your chosen DB backup workflow.
4. Redeploy the last known good revision.

If you need to stop backend services first:

```bash
ssh deploy@<vps-ip> '
  cd /srv/land-intel-core &&
  docker compose -f infra/compose/docker-compose.vps.yml down
'
```

## 10. Storage Backup

From any trusted machine with the service-role key available:

```bash
export SUPABASE_URL='https://<project-ref>.supabase.co'
export SUPABASE_SERVICE_ROLE_KEY='<service-role-key>'
export SUPABASE_STORAGE_BUCKET='raw-assets'
./scripts/backup_storage.sh ./backups
```

The script writes:

- a timestamped download directory
- a `manifest.json` with object paths, sizes, and timestamps

## 11. Notes That Matter In Production

- Do not run the Phase 2 through Phase 8 fixture bootstrap commands in production.
- Keep `RUN_DB_MIGRATIONS=false` in `.env.production`; migrations stay explicit and manual.
- The frontend proxy route is the production path for browser API calls. Do not point the frontend directly at the public VPS API origin.
- Visible probability stays off by default. Do not enable reviewer-visible scopes until the borough/template signoff conditions are honestly met.
