# Compose Notes

- `../../docker-compose.yml` is the local/dev stack with PostGIS, a one-shot `migrate` job, local filesystem storage, and the signed-session web shell.
- `docker-compose.vps.yml` is the VPS backend shape for `api`, `worker`, `scheduler`, and `caddy`, with env-driven Supabase Postgres/PostGIS and Storage integration.
- `Caddyfile` is the reverse-proxy config for `api.<domain>`, TLS termination, backend auth, and public health endpoints.
- Netlify should host `services/web`; the VPS compose file intentionally does not run the frontend.
