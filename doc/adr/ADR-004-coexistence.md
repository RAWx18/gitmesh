# ADR-004: Coexistence with third-party config managers

- **Status:** Accepted
- **Date:** 2026-07-22
- **Pivot references:** `doc/pivot/pivot.md` §4.4, §8.1, §10.1 (principle 6), §17.5

## Context

The config-sync category is saturated: fifteen-plus tools (Ruler, rulesync,
amtiYo `.agents/agents.json`, five distinct projects named "agentsync",
symlink managers like agentlink, plus `skills-lock.json` and mcp-lock pins)
already generate or manage the same files GitMesh compiles. Many repos
GitMesh meets will already be managed by one of them. Fighting another
manager for a file guarantees churn, broken repos, and a hostile ecosystem;
the pivot's stated posture is "interoperate to win migrations" (§4.4).

## Decision

- **Detect and respect.** Detectors recognize third-party manager territory
  — `.ruler/` + ruler.toml, `.rulesync/`, `.agents/agents.json`,
  agentsync-family state files, symlink topologies, `skills-lock.json`,
  mcp-lock records — and `doctor` labels those artifacts "managed by X"
  informationally. Managed-by-another-tool is never itself a finding.
- **Never write into another manager's territory.** `apply` treats it as
  out of bounds; `doctor` suggests nothing destructive there.
- **Migrate only on explicit command.** `gitmesh init` / `gitmesh migrate`
  import `.ruler/`, `.rulesync/`, and `.agents/agents.json` sources into the
  canonical source only when the user runs them, and say what came from
  where.
- **Reference, don't duplicate, existing pins.** An existing
  `skills-lock.json` or mcp-lock record counts as a valid pin (GM004) and
  `.gitmesh/lock.json` stores a reference plus verified hash, never a
  competing pin (pivot §4.7, Δ3).

## Consequences

- Every detector task (T1.7 and per-adapter detectors) carries fixtures for
  "repo managed by X" cases; the acceptance test is that doctor on a Ruler
  repo or a symlink-managed repo says so and proposes nothing destructive.
- Importers for competitor sources are maintained indefinitely (pivot
  §17.5) — migration toward GitMesh must stay free.
- Public communication never frames these tools as targets; the benchmark
  and scanners pages name neighbors accurately (honesty rules, §7).
