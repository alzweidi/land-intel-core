# Documentation Index

This repository keeps its canonical documentation under `docs/`.

## Core Docs

- [specs/london-land-intelligence-implementation-spec-v1.md](specs/london-land-intelligence-implementation-spec-v1.md): controlling Phase 8A implementation spec and non-negotiable rules
- [guides/local-usage.md](guides/local-usage.md): local bootstrap, login, intake, site, scenario, assessment, and opportunity workflow
- [operations/deployment.md](operations/deployment.md): private deployment guide for VPS + Netlify
- [operations/runbook.md](operations/runbook.md): recurring health checks, visibility controls, and recovery steps
- [superpowers/plans/](superpowers/plans/): execution plans and implementation notes for completed workstreams

## Current Auth Note

As of Phase 8A, the web app still uses the built-in local role adapter in `services/web/lib/auth/local-adapter.ts` with signed cookie sessions. Supabase Auth remains a planned/provisioned path in the spec, but it is not the active runtime authentication boundary in this repository yet.
