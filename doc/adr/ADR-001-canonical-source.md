# ADR-001: Canonical source is AGENTS.md plus `.gitmesh/workspace.yaml`

- **Status:** Accepted
- **Date:** 2026-07-22
- **Pivot references:** `doc/pivot/pivot.md` §8.2, §10.1 (principle 2), §10.3

## Context

GitMesh compiles one source of truth into every coding agent's native config
files. The sync-tool census (pivot §4.4) shows fifteen-plus tools each
inventing a proprietary source format (`.ruler/`, `.rulesync/`,
`.agents/agents.json`, Liquid templates, …), which makes every one of them a
new lock-in surface. Meanwhile AGENTS.md is a Linux Foundation (AAIF)
standard adopted by 60,000+ projects - but it is instruction-only by design:
it deliberately covers no MCP servers, skills pins, commands, subagents, or
permissions.

## Decision

The canonical source of truth is:

1. **`AGENTS.md`**: all agent instructions, verbatim, as the standard
   defines it. GitMesh introduces **no proprietary instruction format** and
   never wraps instructions in its own syntax.
2. **`.gitmesh/workspace.yaml`**: only what no standard covers: MCP server
   definitions (env *references*, never secret values), skills with pins,
   commands, subagents, permission-policy references, per-agent overrides.
   Its JSON Schema is published (`$schema` header).

Standing commitment: if AAIF or another credible body standardizes something
`workspace.yaml` covers, GitMesh migrates to the standard and deprecates its
own field (pivot §10.1 principle 2).

## Consequences

- A repo that adopts GitMesh and later abandons it keeps a fully standard
  `AGENTS.md`; only `workspace.yaml` is GitMesh-specific, and it holds
  nothing that has a standard home.
- The Claude Code adapter must bridge the AGENTS.md gap (CLAUDE.md shim via
  `@AGENTS.md` import - the #6235 workaround as a product, pivot §8.2).
- Importers (Ruler, rulesync, agents-json, native files) all converge into
  this source; emitters only ever read from it.
