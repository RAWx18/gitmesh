# ADR-002: No server, no database, no network in the default path

- **Status:** Accepted
- **Date:** 2026-07-22
- **Pivot references:** `doc/pivot/pivot.md` §2.1, §8.6, §10.1 (principle 1), §10.8

## Context

The pre-pivot product required a server, a Postgres database, webhooks, an
agents.yaml, and an MCP endpoint before delivering any value - five adoption
cliffs, and the empirical result was zero retained users (pivot §2.1). The
pivot's entire adoption thesis is `npx gitmesh doctor` delivering value in
under two minutes with zero risk.

## Decision

The Agent Workspace Compiler is **files in, files out**:

- No server, daemon, login, or database in any new code path.
- No network calls in `doctor`, `apply`, or `check`; the only sanctioned
  network operation is an explicit `gitmesh skill add` fetch. No telemetry.
- `doctor` never writes files. Tests enforce no-write and no-network with
  spies (E1, T1.17).
- Determinism: same inputs → byte-identical outputs. No timestamps,
  wallclock values, or nondeterministic ordering in emitted files.
- Nothing in `lib/workspace-core` or the workspace adapter packages may
  import from `server/**`, Drizzle, or Postgres client libraries - enforced
  since T0.4 by the ESLint boundary rule (`eslint.config.mjs`) in CI, with
  guard tests in `scripts/__tests__/import-boundaries.test.ts`.

The legacy server stack stays in-tree, frozen, reachable only through
`gitmesh legacy` (pivot §9.2), until its planned extraction.

## Consequences

- Every new feature must be expressible as reading and writing repo files;
  if a task seems to need a server, the task is misread (pivot §8.6).
- CI can run the full new-product test suite with no services, containers,
  or credentials.
- A future hosted offering (post-G3, pivot §17.6) would be convenience-only
  and must not become a dependency of any CLI feature.
