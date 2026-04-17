# Documentation Index

This repository keeps its canonical documentation under `docs/`.

## Core Docs

- [specs/london-land-intelligence-implementation-spec-v1.md](specs/london-land-intelligence-implementation-spec-v1.md): controlling Phase 8A implementation spec and non-negotiable rules
- [guides/local-usage.md](guides/local-usage.md): local bootstrap, login, intake, site, scenario, assessment, and opportunity workflow
- [operations/deployment.md](operations/deployment.md): private deployment guide for VPS + Netlify
- [operations/runbook.md](operations/runbook.md): recurring health checks, visibility controls, and recovery steps
- [superpowers/plans/README.md](superpowers/plans/README.md): execution-plan notes and historical implementation-plan guidance

## Current Auth Note

As of Phase 8A, the web app still uses the built-in local role adapter in `services/web/lib/auth/local-adapter.ts` with signed cookie sessions. Supabase Auth remains a planned/provisioned path in the spec, but it is not the active runtime authentication boundary in this repository yet.

Route gating in the current web app is role-based:

- analyst: main workflow surfaces
- reviewer/admin: `/review-queue`
- admin only: `/admin/*`

## Surface Status Notes

- `/admin/health` is the primary operational health dashboard in the current web app.
- `/discovery` and `/data-health` still exist as shell/placeholder routes and should not be treated as canonical workflow documentation.
