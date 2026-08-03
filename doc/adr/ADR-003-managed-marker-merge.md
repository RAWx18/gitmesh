# ADR-003: Managed-marker merge semantics

- **Status:** Accepted
- **Date:** 2026-07-22
- **Pivot references:** `doc/pivot/pivot.md` §8.2, §10.1 (principle 5), §10.4, E4/T4.8

## Context

`gitmesh apply` writes into files users also edit by hand (CLAUDE.md,
`.claude/settings.json`, `.cursor/rules/*.mdc`, …). A compiler that clobbers
hand edits destroys trust instantly; one that silently preserves everything
cannot guarantee its own output. Every credible sync tool that survived
contact with users (Ruler, rulesync) converged on explicit ownership
boundaries.

## Decision

- GitMesh owns **only** the content inside explicit managed markers
  (`<!-- gitmesh:managed -->` … `<!-- /gitmesh:managed -->`, or the
  format-appropriate equivalent per file type). Whole-file ownership exists
  only where an adapter's contract declares it (e.g. a generated hook
  script), and the file then carries a provenance header.
- Everything outside managed regions is human-owned: `apply` must preserve
  it byte-for-byte, in place.
- A hand edit **inside** a managed region is drift, never input: `check`
  reports it with the exact source file to edit instead; `apply` restores
  it (the edit is recoverable from git, and the plan output says what will
  be overwritten before it happens).
- A deleted managed file is recreated with a notice. A **symlinked** target
  (e.g. CLAUDE.md → AGENTS.md) is respected, reported as the healthy
  pattern it is, and never replaced with a regular file (pivot §10.4).
- Lossy projections - anything the target format cannot express - are
  always listed in `plan`/`apply` output, never dropped silently.

## Consequences

- Emitters must be marker-aware from their first version; the three-way
  merge cases (edited inside / edited outside / deleted / symlinked) are a
  dedicated conformance suite (T4.8) built on the T0.5 golden-fixture
  harness.
- `.gitmesh/lock.json` records emitted-file hashes and managed-region
  spans so `check` can distinguish "source changed" from "output tampered".
- Docs must disclose plainly that `apply` rewrites only inside markers
  (honesty rule, pivot §7).
