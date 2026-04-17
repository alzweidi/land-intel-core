# PR 3 Merge Readiness Review Plan

## Scope

- Work only on PR `#3` (`codex/production-readiness-remediation-2026-04-17`).
- Address all unresolved actionable GitHub/Codex review threads before final review.
- Re-verify merge readiness without expanding Phase 8A scope.

## Assumptions

- The intended PR is `alzweidi/land-intel-core#3`; the URL provided with `alzheimers/...` does not resolve.
- Existing local branch `codex/production-readiness-remediation-2026-04-17` matches the open PR head unless new commits are pushed during review.

## Steps

- Fix unresolved review findings in:
  - `python/landintel/listings/service.py`
  - `python/landintel/storage/supabase.py`
  - `services/worker/app/main.py`
  - `services/web/lib/landintel-api.ts`
- Add or extend regression coverage for cluster rebuild membership moves, storage error handling, and worker claim visibility.
- Run targeted backend checks, then repo-wide verification appropriate for the touched code.
- Perform a full findings-first review of the resulting PR diff, then commit and push only if the branch is merge ready.
