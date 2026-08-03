> **Historical plan.** Superseded by `IMPLEMENTATION.md` for current
> GitMesh Agents context.

# Implementation Spec: Humans & Permissions (V1)

**Status** Draft &middot; **Owners** Server + UI + CLI + DB + Shared &middot; **Companion** [`doc/plans/humans-and-permissions.md`](./humans-and-permissions.md) &middot; **Drafted** 2026-02-21

This is the engineering implementation contract. It translates the
companion plan's product decisions into concrete schema, API,
middleware, UI, CLI, and test work. **If this document conflicts with
prior exploratory notes, this document wins for V1 execution.**

---

## A. Locked V1 decisions

The companion plan locked the following before implementation began.
They are non-negotiable here:

| # | Decision |
|---|----------|
| 1 | Two deployment modes remain: `local_trusted`, `cloud_hosted` |
| 2 | `local_trusted` &mdash; no login UX, implicit local instance admin actor, loopback-only bind, full admin/settings/invite/approval capabilities locally |
| 3 | `cloud_hosted` &mdash; Better Auth for humans, email/password only, no email verification in V1 |
| 4 | Permissions &mdash; one shared authz system for humans and agents; normalised grants table (`principal_permission_grants`); no separate "agent permissions engine" |
| 5 | Invites &mdash; copy-link only (no outbound email); unified `project_join` link supports human or agent; acceptance creates `pending_approval` join request; no access until admin approval |
| 6 | Join review metadata &mdash; source IP required; no GeoIP / country lookup in V1 |
| 7 | Agent API keys &mdash; indefinite by default; hash at rest; display once on claim; revoke / regenerate supported |
| 8 | Local ingress &mdash; public / untrusted ingress is out of scope for V1; no `--dangerous-agent-ingress` |

---

## B. Baseline vs. delta

What's there today (2026-02-21):

- Server actor model defaults to `operator` in `server/src/middleware/auth.ts`.
- Authorization is mostly `assertBoard` + project check (`server/src/routes/authz.ts`).
- No human auth / session tables in the local schema.
- No principal membership or grants tables.
- No invite or join-request lifecycle.

What V1 must add:

- Move from `operator-vs-agent` authz to **principal-based** authz.
- Better Auth integration in cloud mode.
- Membership / grants / invite / join-request persistence.
- Approval inbox signals and actions.
- Preserve the local no-login UX without weakening cloud security.

---

## C. Architecture

### C.1 Deployment-mode contract

`deployment.mode = local_trusted | cloud_hosted`. Stored in config
(`lib/core/src/config-schema.ts`), loaded in server config
(`server/src/config.ts`), surfaced in `/api/health`.

Startup guardrails:

- `local_trusted` &rarr; fail startup if bind host is not loopback.
- `cloud_hosted` &rarr; fail startup if Better Auth is not configured.

### C.2 Actor model

Replace implicit "operator" semantics with three explicit actor kinds:

- `user` &mdash; session-authenticated human;
- `agent` &mdash; bearer API key;
- `local_implicit_admin` &mdash; only valid in `local_trusted`.

Implementation note: keep `req.actor` shape backward-compatible during
migration via a normaliser helper. Only remove hard-coded `"operator"`
checks once new authz helpers are in place.

### C.3 Authorization model

Authorization input tuple:
`(project_id, principal_type, principal_id, permission_key, scope_payload)`.

Principal types: `user`, `agent`. Role layers:

- `instance_admin` (instance-wide);
- project-scoped grants via `principal_permission_grants`.

Evaluation order:

1. Resolve principal from actor.
2. Resolve instance role (`instance_admin` short-circuits admin-only actions).
3. Resolve project membership (`active` required for project access).
4. Resolve grant + scope for the requested action.

---

## D. Data model

### D.1 Better Auth tables

Managed by Better Auth's adapter / migrations. Expected minimum tables:
`user`, `session`, `account`, `verification`. Use canonical Better Auth
table names and types &mdash; do not fork.

### D.2 New GitMesh tables

#### `instance_user_roles`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid | pk |
| `user_id` | text | not null |
| `role` | text | not null (`instance_admin`) |
| `created_at`, `updated_at` | timestamps | |

Unique index on `(user_id, role)`.

#### `project_memberships`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid | pk |
| `project_id` | uuid | fk `projects.id`, not null |
| `principal_type` | text | not null (`user` &#124; `agent`) |
| `principal_id` | text | not null |
| `status` | text | not null (`pending` &#124; `active` &#124; `suspended`) |
| `membership_role` | text | nullable |
| `created_at`, `updated_at` | timestamps | |

Indexes: unique `(project_id, principal_type, principal_id)`; secondary
`(principal_type, principal_id, status)`.

#### `principal_permission_grants`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid | pk |
| `project_id` | uuid | fk `projects.id`, not null |
| `principal_type` | text | not null (`user` &#124; `agent`) |
| `principal_id` | text | not null |
| `permission_key` | text | not null |
| `scope` | jsonb | nullable |
| `granted_by_user_id` | text | nullable |
| `created_at`, `updated_at` | timestamps | |

Indexes: unique `(project_id, principal_type, principal_id, permission_key)`;
secondary `(project_id, permission_key)`.

#### `invites`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid | pk |
| `project_id` | uuid | fk `projects.id`, not null |
| `invite_type` | text | not null (`project_join` &#124; `bootstrap_ceo`) |
| `token_hash` | text | not null |
| `allowed_join_types` | text | not null (`human` &#124; `agent` &#124; `both`) for `project_join` |
| `defaults_payload` | jsonb | nullable |
| `expires_at` | timestamptz | not null |
| `invited_by_user_id` | text | nullable |
| `revoked_at` | timestamptz | nullable |
| `accepted_at` | timestamptz | nullable |
| `created_at` | timestamptz | not null, default `now()` |

Indexes: unique `(token_hash)`; secondary `(project_id, invite_type, revoked_at, expires_at)`.

#### `join_requests`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid | pk |
| `invite_id` | uuid | fk `invites.id`, not null |
| `project_id` | uuid | fk `projects.id`, not null |
| `request_type` | text | not null (`human` &#124; `agent`) |
| `status` | text | not null (`pending_approval` &#124; `approved` &#124; `rejected`) |
| `request_ip` | text | not null |
| `requesting_user_id` | text | nullable |
| `request_email_snapshot` | text | nullable |
| `agent_name` | text | nullable |
| `adapter_type` | text | nullable |
| `capabilities` | text | nullable |
| `agent_defaults_payload` | jsonb | nullable |
| `created_agent_id` | uuid | fk `agents.id`, nullable |
| `approved_by_user_id` | text | nullable |
| `approved_at` | timestamptz | nullable |
| `rejected_by_user_id` | text | nullable |
| `rejected_at` | timestamptz | nullable |
| `created_at`, `updated_at` | timestamps | |

Indexes: secondary `(project_id, status, request_type, created_at desc)`;
unique `(invite_id)` to enforce one request per consumed invite.

### D.3 Existing-table changes

- `issues` &mdash; add `assignee_user_id` text null. Enforce single-assignee invariant: at most one of `assignee_agent_id` and `assignee_user_id` is non-null.
- `agents` &mdash; keep existing `permissions` JSON for transition only; mark deprecated in code path once principal grants are live.

### D.4 Migration ordering

1. Add new tables / columns / indexes.
2. Backfill minimum memberships / grants for existing data:
   - In local mode, the implicit admin membership context is created at runtime &mdash; **not** persisted as a Better Auth user.
   - In cloud mode, bootstrap creates the first admin user role on acceptance.
3. Switch authz reads to the new tables.
4. Remove legacy operator-only checks.

---

## E. API contract (new + changed)

All routes live under `/api`.

### E.1 Health

`GET /api/health` adds `deploymentMode`, `authReady`, and
`bootstrapStatus` (`ready` &#124; `bootstrap_pending`).

### E.2 Invites

| Method & path | Behaviour |
|---|---|
| `POST /api/projects/:projectId/invites` | Create a `project_join` invite. Copy-link value returned exactly once. |
| `GET /api/invites/:token` | Validate the token; return invite landing payload (includes `allowedJoinTypes`). |
| `POST /api/invites/:token/accept` | Body: `requestType: human` &#124; `agent`. Human path = no extra payload beyond authenticated user. Agent path = `agentName`, `adapterType`, `capabilities`, optional adapter defaults. Consumes the token; creates `join_requests(status=pending_approval)`. |
| `POST /api/invites/:inviteId/revoke` | Revoke a non-consumed invite. |

### E.3 Join requests

| Method & path | Behaviour |
|---|---|
| `GET /api/projects/:projectId/join-requests?status=pending_approval&requestType=...` | List filtered join requests |
| `POST /api/projects/:projectId/join-requests/:requestId/approve` | Human &rarr; create / activate `project_memberships` and apply default grants. Agent &rarr; create `agents` row, create pending claim context for API key, create / activate agent membership, apply default grants. |
| `POST /api/projects/:projectId/join-requests/:requestId/reject` | Reject a join request |
| `POST /api/join-requests/:requestId/claim-api-key` | Approved agent requests only. Returns plaintext key once; stores hash in `agent_api_keys`. |

### E.4 Membership and grants

| Method & path | Behaviour |
|---|---|
| `GET /api/projects/:projectId/members` | Returns both principal types |
| `PATCH /api/projects/:projectId/members/:memberId/permissions` | Upsert / remove grants |
| `PUT /api/admin/users/:userId/project-access` | Instance admin only |
| `GET /api/admin/users/:userId/project-access` | Read accessible projects |
| `POST /api/admin/users/:userId/promote-instance-admin` | Instance admin promotion |
| `POST /api/admin/users/:userId/demote-instance-admin` | Instance admin demotion |

### E.5 Inbox

`GET /api/projects/:projectId/inbox` adds pending-join-request alert
items when the actor can `joins:approve`. Each item carries inline
action metadata: join request id, request type, source IP, and human
email snapshot when applicable.

---

## F. Server implementation

### F.1 Config + startup

Files: `lib/core/src/config-schema.ts`, `server/src/config.ts`,
`server/src/index.ts`, `server/src/startup-banner.ts`.

Changes: add deployment mode + bind-host settings; enforce loopback-only
for `local_trusted`; enforce Better Auth readiness in `cloud_hosted`;
banner shows mode and bootstrap status.

### F.2 Better Auth integration

Files: `server/package.json` (dependency), `server/src/auth/*` (new),
`server/src/app.ts` (mount auth handler endpoints + session middleware).

Changes: add Better Auth server instance; cookie / session handling for
cloud mode; no-op session auth in local mode.

### F.3 Actor middleware

Files: `server/src/middleware/auth.ts`, `server/src/routes/authz.ts`,
`server/src/middleware/operator-mutation-guard.ts`.

Changes:

- Stop defaulting every request to operator in cloud mode.
- Map local requests to `local_implicit_admin` actor in local mode.
- Map Better Auth session to `user` actor in cloud mode.
- Preserve agent bearer path.
- Replace `assertBoard` with permission-oriented helpers:
  - `requireInstanceAdmin(req)`
  - `requireProjectAccess(req, projectId)`
  - `requireProjectPermission(req, projectId, permissionKey, scope?)`

### F.4 Authorization services

Files (new): `server/src/services/{memberships,permissions,invites,join-requests,instance-admin}.ts`.

Changes: centralised permission evaluation; centralised membership
resolution; one place for principal-type branching.

### F.5 Routes

Files: `server/src/routes/index.ts` and new modules
`{auth,invites,join-requests,members,instance-admin,inbox}.ts`.

Changes: add the endpoints listed above; apply project + permission
checks consistently; log all mutations through the activity-log
service.

### F.6 Activity log

Files: `server/src/services/activity-log.ts` plus call sites in
invite / join / member / admin routes.

Required actions to log:

- `invite.created`, `invite.revoked`
- `join.requested`, `join.approved`, `join.rejected`
- `membership.activated`
- `permission.granted`, `permission.revoked`
- `instance_admin.promoted`, `instance_admin.demoted`
- `agent_api_key.claimed`, `agent_api_key.revoked`

### F.7 Realtime + inbox propagation

Files: `server/src/services/live-events.ts`,
`server/src/realtime/live-events-ws.ts`, inbox data-source endpoints.

Changes: emit join-request events; ensure the inbox refresh path
includes join alerts.

---

## G. CLI

Files: `cli/src/index.ts`, `cli/src/commands/onboard.ts`,
`cli/src/commands/configure.ts`, `cli/src/prompts/server.ts`.

Commands:

- `gitmesh-agents auth bootstrap-ceo` &mdash; create a bootstrap invite; print the one-time URL.
- `gitmesh-agents onboard` &mdash; in cloud mode with `bootstrap_pending`, print bootstrap URL and next steps; in local mode, skip the bootstrap requirement.

Config additions: deployment mode, bind host (validated against mode).

---

## H. UI

Files:

- Routing &mdash; `ui/src/App.tsx`.
- API clients &mdash; `ui/src/api/*`.
- New pages / components:
  - `AuthLogin` / `AuthSignup` (cloud mode)
  - `BootstrapPending` page
  - `InviteLanding` page
  - `InstanceSettings` page
  - join-approval components in `Inbox`
  - member / grant management in project settings

UX requirements:

| Context | Behaviour |
|---------|-----------|
| Cloud, unauthenticated | Redirect to login / signup |
| Cloud, bootstrap pending | Block app with setup-command guidance |
| Invite landing | Choose human vs. agent path (respect `allowedJoinTypes`); submit join request; show pending-approval confirmation |
| Inbox | Show join approval cards with approve / reject actions; include source IP and human email snapshot when applicable |
| Local mode | No login prompts; full settings / invite / approval UI available |

---

## I. Security

| Topic | Control |
|-------|---------|
| Token handling | Invite tokens hashed at rest; API keys hashed at rest; one-time plaintext key reveal only |
| Local mode isolation | Loopback bind enforcement; startup hard-fail on non-loopback host |
| Cloud auth | No implicit operator fallback; session auth mandatory for human mutations |
| Join workflow hardening | One request per invite token; pending request has no data access; approval required before membership activation |
| Abuse controls | Rate-limit invite-accept and key-claim endpoints; structured logging for join + claim failures |

---

## J. Migration & compatibility

### Runtime

- Keep existing operator-dependent routes functional while migrating authz helper usage.
- Phase out `assertBoard` calls only after permission helpers cover all routes.

### Data

- Do not delete `agents.permissions` in V1.
- Stop reading it once grants are wired.
- Remove in a post-V1 cleanup migration.

### Better Auth user IDs

- Treat `user.id` as text end-to-end.
- Existing `created_by_user_id` and similar text fields remain valid.

---

## K. Tests

### K.1 Unit

- Permission evaluator: instance-admin bypass; grant checks; scope checks.
- Join-approval state machine.
- Invite-token lifecycle.

### K.2 Integration

- Cloud-mode unauthenticated mutation &rarr; `401`.
- Local-mode implicit-admin mutation &rarr; success.
- Invite accept &rarr; pending join &rarr; no access.
- Join approve (human) &rarr; membership / grants active.
- Join approve (agent) &rarr; key claim once.
- Cross-project access denied for both user and agent principals.
- Local-mode non-loopback bind &rarr; startup failure.

### K.3 UI

- Cloud login gate.
- Bootstrap pending screen.
- Invite landing choose-path UX.
- Inbox join alert approve / reject flows.

### K.4 Regression

- Existing agent-API-key flows still work.
- Task-assignment and atomic-checkout invariants unchanged.
- Activity logging still emitted for all mutations.

---

## L. Delivery phases

| Phase | Scope |
|-------|-------|
| **A &mdash; Foundations** | Config mode / bind-host support; startup guardrails; Better Auth integration skeleton; actor type expansion |
| **B &mdash; Schema and authz core** | Membership / grants / invite / join tables; permission service + helpers; project / member / instance-admin checks |
| **C &mdash; Invite + join backend** | Invite create / revoke; invite accept &rarr; pending request; approve / reject + key claim; activity log + live events |
| **D &mdash; UI + CLI** | Cloud login / bootstrap screens; invite landing; inbox join-approval actions; instance settings + member permissions; bootstrap CLI command + onboarding updates |
| **E &mdash; Hardening** | Full integration / e2e coverage; docs updates (`SPEC-implementation`, `DEVELOPING`, `CLI`); cleanup of legacy operator-only codepaths |

---

## M. Verification gate

Before handoff:

```sh
pnpm -r typecheck
pnpm test:run
pnpm build
```

If any command is skipped, record exactly what was skipped and why.

---

## N. Done criteria

1. Behaviour matches the locked V1 decisions in this doc and `doc/plans/humans-and-permissions.md`.
2. Cloud mode requires auth; local mode has no login UX.
3. Unified invite + pending-approval flow works for both humans and agents.
4. Shared principal membership + permission system is live for both users and agents.
5. Local mode remains loopback-only and fails otherwise.
6. Inbox shows actionable join approvals.
7. All new mutating paths are activity-logged.
