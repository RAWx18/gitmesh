> **Historical plan.** Superseded by `IMPLEMENTATION.md` for current
> GitMesh Agents context.

# Plan - admin-led Agent Creation & Enabling Governance (V1.1)

**Status** Proposed &middot; **Owners** Product + Server + UI + Skills &middot; **Drafted** 2026-02-19

---

## TL;DR

We want a admin agent to enable new agents itself, with lightweight but
explicit governance. Four moving parts:

| Lever | Default | What it controls |
|-------|---------|------------------|
| Project toggle `requireBoardApprovalForNewAgents` | `true` | Whether each new enable needs operator approval |
| Per-agent permission `can_create_agents` | admin = `true`, all others = `false` | Who is allowed to drive the enable |
| New agent status `pending_approval` | n/a | A non-operational draft state until approval lands |
| Approval comments + revisions | n/a | Collaboration, audit, and revision loops on approvals |

We also expose adapter configuration via reflection so an enabling agent
can introspect available adapters and existing agent configs (including
its own).

---

## 1. Where we are today

| Area | Repo reality |
|------|--------------|
| Agent creation | Operator-only at `POST /api/projects/:projectId/agents` (`server/src/routes/agents.ts`) |
| Approvals | Statuses `pending`/`approved`/`rejected`/`cancelled`; types include `enable_agent` and `approve_admin_strategy` (`lib/core/src/constants.ts`, `server/src/services/approvals.ts`) |
| `enable_agent` semantics | Agent created **only** on approval; no pre-created limbo agent |
| Agent permissions | None |
| Project setting "needs operator approval" | Doesn't exist |
| Approval threads | None - no comments, no revision-requested state |
| Inbox / Approvals UI | Approve / reject only; no approval detail route |
| Adapter config | Free-form JSON; no reflection endpoint |

---

## 2. Product decisions

### 2.1 Project setting

`requireBoardApprovalForNewAgents` (boolean). Default `true`. Editable
only in project advanced settings - **not** the onboarding /
project-creation flow.

### 2.2 Agent permission model

Lightweight; one permission for now: `can_create_agents` (boolean).
Defaults: admin = `true`, everyone else = `false`. Edit authority:

- Operator may edit any agent's permissions.
- admin may edit permissions for agents in the same project.

This phase deliberately does **not** introduce a broader RBAC system.

### 2.3 Limbo state

A new agent status: `pending_approval`. While in this state the agent
record exists in the org tree (so it can be reviewed) but cannot run,
receive assignments, create keys, or transition to active states until
an enable approval lands.

---

## 3. Data model deltas

### 3.1 `projects`

Add column `require_board_approval_for_new_agents` boolean not null
default `true`.

Sync layers: `lib/data/src/schema/projects.ts`,
`lib/core/src/types/project.ts`,
`lib/core/src/validators/project.ts`, project advanced-settings form,
UI project API type usage.

### 3.2 `agents`

Add column `permissions` jsonb not null default `{}`. Expand status
values to include `pending_approval`.

Sync layers: `lib/data/src/schema/agents.ts`,
`lib/core/src/constants.ts` (`AGENT_STATUSES`),
`lib/core/src/types/agent.ts`,
`lib/core/src/validators/agent.ts`, status badges / filters / lifecycle
controls in the UI.

### 3.3 `approvals`

Approval remains the central governance record. Extensions:

- New status: `revision_requested`.
- Enable approval payload must contain `agentId`, `requestedByAgentId`, `requestedConfigurationSnapshot`.

### 3.4 New table - `approval_comments`

Threaded discussion on each approval. Columns: `id`, `project_id`,
`approval_id`, `author_agent_id`, `author_user_id`, `body`, timestamps.

Used for review comments, revision requests, approve / reject
rationale, and a permanent audit trail.

---

## 4. API + AuthZ

### 4.1 Permission helpers (server)

- `assertCanCreateAgents(req, projectId)`
- `assertCanManageAgentPermissions(req, projectId)`

Rules:

- Operator always passes.
- An agent passes `can_create_agents` if its own permission is `true` and the project matches.
- Permission management is admin or operator only.

### 4.2 Enable creation flow

New route: `POST /api/projects/:projectId/agent-enables`. Behaviour:

1. Requires `can_create_agents` (or operator).
2. Always create the agent row first.
3. If the project setting requires approval:
   - agent status `= pending_approval`;
   - create an `approvals` row with `type=enable_agent`, `status=pending`, `payload.agentId=...`;
   - return both `agent` + `approval`.
4. Otherwise:
   - agent status `= idle`;
   - no approval record needed.

The operator may continue using the direct create route, but this
endpoint becomes the canonical path for admin / agent-led enabling.

### 4.3 Approval workflow endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/approvals/:id` | Read approval + thread |
| `POST /api/approvals/:id/request-revision` | Move pending &rarr; revision_requested |
| `POST /api/approvals/:id/resubmit` | Move revision_requested &rarr; pending |
| `GET /api/approvals/:id/comments` | List comments |
| `POST /api/approvals/:id/comments` | Add a comment |

Existing approve / reject semantics extend so that approving an
`enable_agent` transitions the linked agent `pending_approval` &rarr;
`idle`. Rejecting keeps the linked agent in a non-active state
(`pending_approval` initially, optionally `terminated` later).

### 4.4 Permission management endpoint

`PATCH /api/agents/:id/permissions`. Accepts initially only
`{ "canCreateAgents": boolean }`.

### 4.5 Config-read endpoints (gated)

- `GET /api/projects/:projectId/agent-configurations`
- `GET /api/agents/:id/configuration`

Access: operator, admin, or any agent with `can_create_agents`.

Security: redact obvious secret values from adapter config (`env`, API
keys, tokens, JWT-shaped values). Include a redaction marker in the
response payload.

### 4.6 Reflection endpoints (plain text, for LLM consumption)

- `GET /llms/agent-configuration.txt`: index: installed adapter list, per-adapter doc URLs, brief "how to enable" API sequence links.
- `GET /llms/agent-configuration/:adapterType.txt`: per adapter: required / optional config keys, defaults, field descriptions, safety notes, example payloads.

Auth gate is the same as the config-read endpoints.

---

## 5. Adapter protocol extension

Extend `ServerAdapterModule` to expose config docs via either
`agentConfigurationDoc` (string) or `getAgentConfigurationDoc()`.

Adapter implementations to update: `lib/adapters/claude`,
`lib/adapters/codex`, `server/src/adapters/registry.ts`.

This is required so reflection is generated from installed adapters
not hardcoded.

---

## 6. UI work

### 6.1 Project advanced settings

Add a panel / modal in Projects UI with the toggle "Require operator
approval for new agent enables" (default on). Not shown in onboarding.

### 6.2 Agent permissions UI

In Agent Detail (operator / admin context), add a permissions section
with a "Can create new agents" toggle.

### 6.3 Enable UX

For admin and authorised agents, add an "Enable Agent" flow:

- choose role / name / title / reports-to;
- compose initial prompt / capabilities;
- inspect adapter reflection docs;
- inspect related agent configurations;
- submit.

State messaging: `Pending operator approval` if approval is required;
`active-ready` otherwise.

### 6.4 Approvals UX

Add `/approvals/:approvalId` and expand inbox integration with:

- threaded comments;
- a "request revision" action;
- approve / reject with a decision note;
- a timeline (created, revisions, decisions).

### 6.5 Disapproved agent cleanup

Operator-only destructive action in approval detail: "Delete
disapproved agent". Explicit confirmation dialog. Preserves the
approval + comment history for audit.

---

## 7. New skill - `gitmesh-agents-create-agent`

Files to add:

- `playbooks/gitmesh-agents-create-agent/playbook.md`
- `playbooks/gitmesh-agents-create-agent/references/api-reference.md`

Skill responsibilities:

- Discover available adapter configurations via `/llms/agent-configuration*.txt`.
- Read existing agent configurations (including its own and related roles).
- Propose a best-fit config for the current environment.
- Draft a high-quality initial prompt for the new agent.
- Set the manager / reporting line.
- Drive the enable API flow.
- Handle the revision loop with operator comments.

Also update `playbooks/gitmesh-agents/playbook.md` to reference this
skill for enabling workflows.

---

## 8. Invariants

- `pending_approval` agents cannot: be invoked / woken; be assigned issues; create or use API keys; transition to active lifecycle states except through enable approval.
- Approval transitions: `pending` &rarr; `revision_requested` / `approved` / `rejected` / `cancelled`; `revision_requested` &rarr; `pending` / `rejected` / `cancelled`.
- Every mutation writes an `activity_log` record.

---

## 9. Phasing

| Phase | Scope |
|-------|-------|
| 1 - Contracts & migration | DB schema (`projects`, `agents`, approvals status expansion, `approval_comments`); shared constants / types / validators; migration generation; typecheck |
| 2 - Server authz & enable flow | Permission resolver + authz guards; `agent-enables` route; `pending_approval` enforcement across heartbeat / issue / key flows; approval revision + comment endpoints |
| 3 - Reflection & config-read APIs | Adapter protocol docs support; `/llms/agent-configuration*.txt`; protected config-read endpoints with redaction |
| 4 - UI & skilling | Project advanced setting UI; permission controls; approval detail with comments + revision flow; disapproved-agent delete flow; `gitmesh-agents-create-agent` skill + doc updates |

---

## 10. Tests

### Server

- Permission gates for enable / config-read / permission-update endpoints.
- Enable creation behaviour with the project setting on / off.
- Approval transitions including the revision cycle.
- `pending_approval` enforcement across wakeup / invoke / assignment / keys.
- Config redaction.

### UI

- Advanced-setting toggle persistence.
- Approval-detail comment + revision interactions.
- Enable flow states (pending vs. immediate).

### Repo verification (gate before merge)

- `pnpm -r typecheck`
- `pnpm test:run`
- `pnpm build`

---

## 11. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Leaking secrets through agent config reads | Strict redaction pass; allowlist / denylist tests |
| Status explosion | Single added status (`pending_approval`) with explicit transition guards |
| Approval flow regressions | Centralise transition logic in the approval service; back it with tests |

---

## 12. Open decisions (with default recommendations)

1. Should the operator's direct-create route bypass the approval setting? **Recommendation: yes**: operator is the explicit governance override.
2. Should non-authorized agents still see basic agent metadata? **Recommendation: yes**: name / role / status visible; configuration fields remain restricted.
3. On rejection, should the limbo agent stay `pending_approval` or move to `terminated`? **Recommendation: move to `terminated` on final reject;** keep an optional hard-delete action for cleanup.
