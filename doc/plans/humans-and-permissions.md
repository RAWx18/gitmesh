> **Historical plan.** Superseded by `IMPLEMENTATION.md` for current
> GitMesh Agents context.

# Humans, Permissions, and Onboarding &mdash; Plan

**Status** Draft &middot; **Owners** Server + UI + Shared + DB &middot; **Drafted** 2026-02-21

---

## Why this exists

V1 was designed for a single operator. We need first-class human users
and permissions while keeping two coexisting deployment shapes &mdash; an
instant local mode (`npx gitmesh-agents run` and you're in) and a safe
cloud mode where authentication is mandatory.

What we're adding:

- multi-human collaboration with per-user permissions;
- safe cloud defaults (no accidental loginless production);
- a local mode that still feels instant;
- agent-to-human task delegation, with a human inbox;
- one user account spanning multiple projects in one deployment;
- instance admins who manage cross-project access for the deployment;
- join approvals as actionable inbox alerts (not buried in admin pages);
- a single invite-and-approve onboarding path that works for **both** humans and agents;
- one shared membership and permission model covering humans and agents.

## Constraints we will not break

1. Project scoping is strict for every new table, endpoint, and check.
2. Existing control-plane invariants stay intact:
   - single-assignee task model;
   - approval gates;
   - budget hard-stop behaviour;
   - mutation activity logging.
3. Local mode stays trusted and easy. Cloud posture must never become unsafe by default.

---

## Deployment modes

### `local_trusted`

| Topic | Behaviour |
|-------|-----------|
| Login UI | none |
| Browser flow | opens directly into operator context |
| Storage | embedded DB and local storage defaults remain |
| Implicit actor | a local human actor is auto-provisioned for attribution |
| Implicit actor authority | effective `instance_admin` for that instance |
| Invite / approval / permission UI | available; agent enrollment supported |

Guardrails: server binds to loopback by default; non-loopback bind in
this mode is a startup failure; the UI shows a persistent "Local
trusted mode" badge.

### `cloud_hosted`

| Topic | Behaviour |
|-------|-----------|
| Login | required for all human endpoints |
| Auth provider | Better Auth |
| Initial method | email + password |
| Email verification | not required for V1 |
| Storage | hosted DB + remote deployment supported |
| Sessions | multi-user with role and permission enforcement |

Guardrails: missing auth provider / session config &rarr; startup
failure. Insecure auth-bypass flag &rarr; startup failure. The health
payload includes mode and auth readiness.

---

## Authentication choice

Better Auth, email/password only at first. No email confirmation in V1.
Implementation must be structured so social / SSO providers can plug in
later without changing membership or permission semantics.

---

## Actor model

A single resolved actor per request:

- `user` &mdash; authenticated human
- `agent` &mdash; API key
- `local_board_implicit` &mdash; only valid in `local_trusted`

Resolution rules:

- In `cloud_hosted`, only `user` and `agent` are valid actors.
- In `local_trusted`, unauthenticated browser / API requests resolve to `local_board_implicit`.
- `local_board_implicit` is authorized as an instance-admin principal for local operations.
- Every mutating action continues to write `activity_log` with actor type and id.

---

## First-admin bootstrap

Cloud deployments need a safe, explicit way to plant the first human
admin. `local_trusted` does not need this &mdash; the implicit local
instance admin already exists.

Flow:

1. If no `instance_admin` user exists for the deployment, the instance is in `bootstrap_pending`.
2. CLI: `pnpm gitmesh-agents auth bootstrap-ceo` mints a one-time admin onboarding invite URL for that instance.
3. `pnpm gitmesh-agents onboard` runs this check and prints the URL automatically when `bootstrap_pending`.
4. Visiting the app while `bootstrap_pending` shows a blocking setup page that names the exact CLI command to run.
5. Accepting the admin invite creates the first admin user and exits bootstrap mode.

Security rules:

- Bootstrap invite is single-use, short-lived, with the token hash stored at rest.
- Only one active bootstrap invite per instance at a time (regeneration revokes any prior token).
- All bootstrap actions are audited in `activity_log`.

---

## Data model

### New tables

#### `users`

Identity record for humans (email-based). Optional instance-level role
field (or companion table) for admin rights.

#### `project_memberships`

`project_id`, `principal_type` (`user` &#124; `agent`), `principal_id`,
`status` (`pending` &#124; `active` &#124; `suspended`), role metadata.
Stores effective access state for both humans and agents. **Many-to-many**
&mdash; one principal can belong to multiple projects.

#### `invites`

`project_id`, `invite_type` (`project_join` &#124; `bootstrap_ceo`), token
hash, `expires_at`, `invited_by`, `revoked_at`, `accepted_at`.
One-time share link &mdash; no pre-bound invite email.
`allowed_join_types` (`human` &#124; `agent` &#124; `both`) gates which
paths a `project_join` link permits.
Optional defaults payload keyed by join type:

- human defaults: initial permissions / membership role
- agent defaults: proposed role / title / adapter defaults

#### `principal_permission_grants`

`project_id`, `principal_type` (`user` &#124; `agent`), `principal_id`,
`permission_key`. Explicit grants such as `agents:create`. Includes a
scope payload for chain-of-command limits. **Normalised table**, not a
JSON blob &mdash; for auditable grant / revoke history.

#### `join_requests`

`invite_id`, `project_id`, `request_type` (`human` &#124; `agent`), and
`status` (`pending_approval` &#124; `approved` &#124; `rejected`).

| Group | Fields |
|-------|--------|
| Common review metadata | `request_ip`, `approved_by_user_id`, `approved_at`, `rejected_by_user_id`, `rejected_at` |
| Human request fields | `requesting_user_id`, `request_email_snapshot` |
| Agent request fields | `agent_name`, `adapter_type`, `capabilities`, `created_agent_id` (nullable until approved) |

Each consumed invite creates exactly one join request after the join
type is selected.

### `issues` extension

Add `assignee_user_id` (nullable). Preserve the single-assignee
invariant via XOR check: exactly zero or one of `assignee_agent_id` /
`assignee_user_id`.

### Compatibility

- Existing `created_by_user_id` / `author_user_id` fields stay and become fully active.
- Agent API keys remain auth credentials; membership + grants remain the authorization source.

---

## Permission model

### Principle

Humans and agents go through the **same** membership + grant evaluation
engine. Permission checks resolve against
`(project_id, principal_type, principal_id)` for both actor types. No
separate authz codepath.

### Role layers

- `instance_admin` &mdash; deployment-wide admin; can access and manage all projects + user-project access mapping.
- `project_member` &mdash; project-scoped permissions only.

### Initial grant set

| Grant | Allows |
|-------|--------|
| `agents:create` | Create agents in the project |
| `users:invite` | Create invite links |
| `users:manage_permissions` | Grant / revoke project permissions |
| `tasks:assign` | Assign tasks to people / agents |
| `tasks:assign_scope` | Assign within an org-constrained scope |
| `joins:approve` | Approve / reject human + agent join requests |

Behavioural rules:

- Instance admins can promote / demote instance admins and manage user access across projects.
- Operator-level users can manage project grants inside projects they control.
- Non-admin principals only act within explicit grants.
- Assignment checks apply to both agent and human assignees.

### Chain-of-command scope

Initial approach: assignment scope is an allow-rule over the org
hierarchy. Examples: `subtree:<agentId>` (can assign into that
manager's subtree), `exclude:<agentId>` (cannot assign to protected
roles such as admin).

Enforcement:

1. Resolve the target assignee's org position.
2. Evaluate allow / deny scope rules before the assignment mutation.
3. Return `403` for out-of-scope assignments.

---

## Invite + signup flow

Steps:

1. An authorised user creates one `project_join` invite share link with optional defaults + expiry.
2. System produces an invite URL with a one-time token.
3. The invite landing page presents two paths: `Join as human` or `Join as agent` (filtered by `allowed_join_types`).
4. The requester picks a path and submits the required data.
5. Submission consumes the token and creates a `pending_approval` join request &mdash; **no access yet**.
6. The join request captures review metadata: human &rarr; authenticated email; agent &rarr; proposed metadata; both &rarr; source IP.
7. A project admin / instance admin reviews and approves or rejects.
8. On approval:
   - human &rarr; activate `project_membership` and apply permission grants;
   - agent &rarr; create the agent record and enable the API-key claim flow.
9. The link is one-time; it cannot be reused.
10. The inviter or an admin can revoke the invite before acceptance.

Security rules:

- Invite tokens are stored hashed at rest.
- One-time use; short expiry.
- All invite lifecycle events go to `activity_log`.
- Pending users cannot read or mutate any project data until approved.

---

## Approval inboxes

### Join approval inbox

- Join requests generate inbox alerts for eligible approvers (`joins:approve` or admin).
- Alerts appear in both the global / project inbox feed and the dedicated pending-approvals UI.
- Alerts include inline approve / reject actions &mdash; no context switch required.
- Alert payload must include: requester email when `request_type=human`, source IP, request type.

### Human inbox + agent &rarr; human delegation

- Agents may assign tasks to humans when policy permits.
- Humans see assigned tasks in their inbox view (including in `local_trusted`).
- Comment and status transitions follow the same issue lifecycle guards.

---

## Agent join path (via the unified invite link)

1. An authorised user shares one `project_join` invite link whose `allowed_join_types` includes `agent`.
2. The agent operator opens the link, picks `Join as agent`, and submits a join payload (name, role, adapter metadata).
3. The system creates a `pending_approval` agent join request and captures source IP.
4. The approver sees an inbox alert and approves or rejects.
5. On approval, the server creates the agent record and mints a long-lived API key.
6. The API key is shown exactly once via a secure claim flow with explicit "save now" instruction.

### Long-lived token policy

- Long-lived, revocable API keys by default. Hash stored at rest.
- Plaintext key shown once.
- Immediate revoke / regenerate from the admin UI.
- Optional expirations / rotation policy can be added later without changing the join flow.

---

## API additions (proposed)

| Path | Purpose |
|------|---------|
| `GET /projects/:projectId/inbox` | Human-actor scoped to self; tasks + pending join-approval alerts when authorised |
| `POST /projects/:projectId/issues/:issueId/assign-user` | Assign an issue to a human |
| `POST /projects/:projectId/invites` | Create a `project_join` invite |
| `GET /invites/:token` | Invite landing payload with `allowed_join_types` |
| `POST /invites/:token/accept` | Body includes `requestType=human|agent` plus request metadata |
| `POST /invites/:inviteId/revoke` | Revoke a pending invite |
| `GET /projects/:projectId/join-requests?status=pending_approval&requestType=human|agent` | List join requests |
| `POST /projects/:projectId/join-requests/:requestId/approve` | Approve a request |
| `POST /projects/:projectId/join-requests/:requestId/reject` | Reject a request |
| `POST /join-requests/:requestId/claim-api-key` | Approved agent requests only |
| `GET /projects/:projectId/members` | Returns both human and agent principals |
| `PATCH /projects/:projectId/members/:memberId/permissions` | Grant / revoke per-member permissions |
| `POST /admin/users/:userId/promote-instance-admin` | Instance admin promotion |
| `POST /admin/users/:userId/demote-instance-admin` | Instance admin demotion |
| `PUT /admin/users/:userId/project-access` | Set accessible projects for a user |
| `GET /admin/users/:userId/project-access` | Read accessible projects for a user |

---

## Local mode UX policy

- No login prompt or account setup required.
- A local implicit operator user is auto-provisioned for audit attribution.
- The local operator can use instance settings and project settings as effective instance admin.
- Invite, join-approval, and permission-management UI is available in local mode.
- Agent onboarding is expected in local mode &mdash; including creating invite links and approving join requests.
- Public / untrusted network ingress is out of scope for V1 local mode.

## Cloud agents in this model

- Cloud agents continue authenticating via `agent_api_keys`.
- Same-project boundary checks remain mandatory.
- Agent ability to assign human tasks is permission-gated, not implicit.

## Instance settings surface

This plan introduces instance-level concerns (bootstrap state, instance
admins, invite defaults, token policy) and there is no dedicated UI
today.

V1 approach:

- Add a minimal `Instance Settings` page for instance admins.
- Expose key instance settings via API + CLI (`gitmesh-agents configure`, `gitmesh-agents onboard`).
- Show read-only instance status indicators in the main UI until the full settings UX exists.

---

## Implementation phasing

### Phase 1 &mdash; Mode and guardrails

- Explicit deployment-mode config (`local_trusted` &#124; `cloud_hosted`).
- Startup safety checks; health visibility.
- Local-implicit-operator actor resolution &rarr; instance-admin authorization context.
- Bootstrap status signal in health / config (`ready` &#124; `bootstrap_pending`).
- Minimal instance settings API / CLI surface and read-only UI indicators.

### Phase 2 &mdash; Human identity & memberships

- Schema + migrations for users / memberships / invites.
- Auth middleware for cloud mode.
- Membership lookup + project access checks.
- Better Auth email / password (no email verification).
- First-admin bootstrap invite command + onboard integration.
- One-time share-link invite acceptance flow with `pending_approval` join requests.

### Phase 3 &mdash; Permissions & assignment scope

- Shared principal grant model + enforcement helpers.
- Chain-of-command scope checks for assignment APIs.
- Tests for forbidden assignment (e.g. cannot assign to admin).
- Instance-admin promotion / demotion + global project-access management APIs.
- `joins:approve` permission checks for human + agent join approvals.

### Phase 4 &mdash; Invite workflow

- Unified `project_join` create / landing / accept / revoke endpoints.
- Join request approve / reject endpoints with review metadata.
- One-time token security and revocation semantics.
- UI for invite management, pending join approvals, membership permissions.
- Inbox alert generation for pending join requests.
- Invite + approval UX is enabled in **both** modes.

### Phase 5 &mdash; Human inbox + assignment updates

- Extend issue assignee model for human users.
- Inbox API + UI: task assignments, pending join-approval alerts with inline approve / reject.
- Agent &rarr; human assignment flow with policy checks.

### Phase 6 &mdash; Agent self-join + token claim

- Agent join path on unified invite landing page.
- Capture agent join requests + admin approval flow.
- One-time API-key claim flow after approval (display once).

---

## Acceptance criteria

1. `local_trusted` starts with no login; operator UI is shown immediately.
2. `local_trusted` does not expose optional human login UX in V1.
3. The `local_trusted` implicit actor can manage instance settings, invite links, join approvals, and permission grants.
4. `cloud_hosted` cannot start without auth configured.
5. No request in `cloud_hosted` can mutate data without an authenticated actor.
6. If no initial admin exists, the app shows bootstrap instructions with the CLI command.
7. `pnpm gitmesh-agents onboard` outputs an admin onboarding invite URL when bootstrap is pending.
8. One `project_join` link supports both human and agent onboarding via join-type selection on the landing page.
9. Invite delivery in V1 is copy-link only (no built-in email delivery).
10. Share-link acceptance creates a pending join request &mdash; it does not grant immediate access.
11. Pending join requests appear as inbox alerts with inline approve / reject actions.
12. The admin review view includes join metadata before decision (human email when applicable, source IP, agent metadata for agent requests).
13. Only approved join requests unlock access:
    - human &rarr; active project membership + permission grants;
    - agent &rarr; agent creation + API-key claim eligibility.
14. Agent enrollment follows the same link &rarr; pending approval &rarr; approve flow.
15. Approved agents can claim a long-lived API key exactly once with plaintext display-once semantics.
16. Agent API keys are indefinite by default in V1 and revocable / regenerable by admins.
17. Public / untrusted ingress for `local_trusted` is not supported in V1 (loopback-only local server).
18. One user can hold memberships in multiple projects.
19. Instance admins can promote another user to instance admin.
20. Instance admins can manage which projects each user can access.
21. Permissions can be granted / revoked per member principal (human or agent) through the shared grant system.
22. Assignment scope prevents out-of-hierarchy or protected-role assignments.
23. Agents can assign tasks to humans only when allowed.
24. Humans can view assigned tasks in inbox and act on them per permissions.
25. All new mutations are project-scoped and logged in `activity_log`.

---

## V1 decisions (locked)

1. `local_trusted` will not support login UX in V1 &mdash; implicit local operator actor only.
2. Permissions use a normalised shared table (`principal_permission_grants`) with scoped grants.
3. Invite delivery is copy-link only in V1 &mdash; no built-in email.
4. Bootstrap invite creation requires local shell access only (CLI path; **no** HTTP bootstrap endpoint).
5. Approval review shows source IP only &mdash; no GeoIP / country lookup in V1.
6. Agent API-key lifetime is indefinite by default in V1, with explicit revoke / regenerate controls.
7. Local mode keeps full admin / settings / invite capabilities through the implicit local instance-admin actor.
8. Public / untrusted ingress for local mode is out of scope for V1 &mdash; no `--dangerous-agent-ingress` in V1.
