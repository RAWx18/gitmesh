# ADR-005: npm package is `gitmesh-cli`, binary is `gitmesh`

- **Status:** Accepted
- **Date:** 2026-07-22
- **Pivot references:** `doc/pivot/pivot.md` §7 (naming), §10.8; task T0.6

## Context

Pivot §7 planned to publish the CLI as the npm package **`gitmesh`**, with
`gitmesh-agents` continuing as the legacy alias. Registry reality on
2026-07-22 (T0.6): the unscoped npm name `gitmesh` is owned by an unrelated,
actively maintained project (neil-ji/git-mesh — git-worktree orchestration;
eleven releases since 2026-07-12, latest 2026-07-18). `gitmesh-agents` has
never actually been published (npm 404), and nothing under a `@gitmesh`
scope exists.

## Decision

- The published npm package is **`gitmesh-cli`** (unscoped, free at decision
  time). The installed binary remains **`gitmesh`**, so every documented
  command (`gitmesh doctor`, `gitmesh apply`, …) is unchanged.
- The zero-install wedge invocation is `npx gitmesh-cli@next` (dist-tag
  `next` until the doctor launch, then `latest`).
- `gitmesh-cli` is a thin publishable shell: it bundles the same
  `cli/src/gitmesh.ts` entry the monorepo runs, owns the `gitmesh` bin
  exclusively (removed from `gitmesh-agents`), and joins the Changesets
  fixed version group.
- No npm dispute or purchase is pursued now; if the `gitmesh` name ever
  becomes available, adopting it is a follow-up decision, not an
  assumption.

## Consequences

- Launch copy (E2) must consistently say `npx gitmesh-cli doctor` — never
  `npx gitmesh`, which runs a stranger's package. This substitution applies
  wherever pivot documents say "npm `gitmesh`".
- The name-collision risk cuts both ways: docs should note the distinction
  once, factually, and never disparage the other project.
- Publishing requires an npm account owning `gitmesh-cli`; the release
  workflow (`.github/workflows/release-cli.yml`) needs its `NPM_TOKEN`
  secret and publishes with provenance.
