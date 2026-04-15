# Compose Notes

- `../../docker-compose.yml` is the local/dev stack with PostGIS, local filesystem storage, and the web shell.
- `docker-compose.vps.yml` is the VPS backend shape for `api`, `worker`, and `scheduler`, with env-driven Supabase Postgres/PostGIS, Storage, and Auth integration.
- Netlify should host `services/web`; the VPS compose file intentionally does not run the frontend.

