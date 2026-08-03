# Triage agent - tools and templates

## GitMesh API

- **Base:** `$GITMESH_API_URL` (e.g. `http://localhost:3100/api` in local dev).
- **Auth:** `Authorization: Bearer $GITMESH_API_KEY` when the control plane injects it.
- **Run trace:** `X-Gitmesh-Run-Id: $GITMESH_RUN_ID` on mutating issue requests.

Full method list and flows: **`playbooks/core/playbook.md`**.

## Triage comment templates

### Bug report

```md
## Triage summary

- **Type**: Bug
- **Priority**: {priority}
- **Reproduction**: {confirmed|needs-reproduction}
- **Assigned to**: {agent-or-maintainer}
- **Related issues**: {links or none found}
```

### Feature request

```md
## Triage summary

- **Type**: Feature request
- **Priority**: {priority}
- **Scope**: {clear|needs-design}
- **Assigned to**: {agent-or-maintainer}
```

### Duplicate

```md
## Triage summary

Duplicate of {link or #id}. Routing per maintainer policy.
```

## Labels without forge APIs

If labels are not applied via API in your setup, state them explicitly in the triage comment, e.g. `Primary: bug`, `Secondary: needs-reproduction`.

## Local adapters

Point **working directory** at a clone of the repo when tasks reference code paths. Provider keys (e.g. `OPENAI_API_KEY`) are separate from `GITMESH_API_KEY`; both may be required in one run.
