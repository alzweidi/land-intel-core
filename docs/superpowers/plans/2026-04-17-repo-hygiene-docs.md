# Repository Hygiene And Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove tracked repository clutter, strengthen ignore rules, and bring the project documentation back in line with the actual codebase and repo layout.

**Architecture:** Treat this as a repository-maintenance pass, not a feature phase. First inventory tracked generated artifacts and documentation drift, then remove non-essential files, expand ignore coverage for Python/Next.js/Playwright tooling, and finally reorganize/update docs so the repository points to current canonical guidance.

**Tech Stack:** Git, Python, FastAPI, Alembic, Next.js, Playwright, Markdown documentation

---

## Assumptions

- Scope is limited to repository hygiene and documentation maintenance; no product-phase work starts here.
- Generated screenshots, Playwright traces, caches, local storage dumps, and similar local-only artifacts are not required as committed fixtures.
- The controlling specification remains necessary, but its current duplicate-style filename should be normalized.
- Operational and usage docs should live under `docs/` so the documentation tree is coherent.

## Workstreams

### 1. Inventory tracked clutter
- Identify tracked artifacts that are local, generated, or redundant:
  - `.playwright-cli/`
  - `.tmp/`
  - `output/playwright/`
  - `services/.tmp/`
  - `test-results/`
  - any tracked logs, screenshots, local storage dumps, or duplicate filenames
- Confirm whether any tracked config or env files should remain committed as examples only.

### 2. Ignore-rule hardening
- Expand the root `.gitignore` to cover:
  - Python caches, coverage, virtualenvs, build outputs, test artifacts
  - Next.js build outputs and cache directories
  - Playwright output, screenshots, traces, and local debugging folders
  - IDE/editor metadata and OS detritus
  - local env overrides and temporary output folders
- Keep committed example env files and repo-owned source assets unignored.

### 3. Documentation cleanup
- Normalize the docs tree so canonical docs live under `docs/`:
  - `docs/specs/`
  - `docs/guides/`
  - `docs/operations/`
  - `docs/superpowers/plans/`
- Rename or move outdated/awkward doc locations and update internal links.
- Verify README, usage, deploy, and operations guidance against the current repo layout, scripts, routes, and service commands.

### 4. Verification
- Re-run `git status --short` to confirm only intended changes remain.
- Spot-check docs link targets and referenced commands.
- Summarize deleted artifacts, new ignore coverage, and documentation updates.
