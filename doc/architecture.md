# GitMesh Agents Architecture Specification

> Living target spec for the GitMesh Agents control plane. Sections are
> tagged `[DRAFT]` while they are still being interviewed; once a section
> moves to `[STABLE]` it overrides the corresponding wording in the V1
> implementation contract (`doc/v1-spec.md`).

This document is organised around the **invariants** of the system rather
than around chapters of features. Each invariant is presented as: what the
rule is, what it permits, what it forbids, and what stays open.

---

## Reading guide

The fastest way to absorb this document:

1. Skim **&sect;13 Principles (Consolidated)** first - that's the executive
   summary.
2. Read **&sect;12 Anti-Requirements** next - understanding what GitMesh
   Agents is *not* eliminates most class-of-feature confusion.
3. Then dive into the model sections (&sect;1&ndash;&sect;7) only as you
   need them.

---

## 1. Project Model `[DRAFT]`

A Project is a first-order object. One GitMesh Agents instance hosts many
Projects. A Project has no standalone "goal" field - its direction is
expressed through its set of Initiatives (&sect;5, Task Hierarchy Mapping).

### 1.1 Fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | uuid | Primary key |
| `name` | string | Project name |
| `createdAt` | timestamp | |
| `updatedAt` | timestamp | |

### 1.2 Operator governance

Every Project has a single human **Operator** that governs high-impact
decisions. V1 ships exactly one Operator per Project.

#### Approval gates (V1)

The Operator must approve:

- Enabling new Agents (creating new Agents in the Project).
- The admin Agent's initial strategic breakdown before execution begins.
- (TBD) Other governance-gated actions: goal changes, firing Agents, ...

#### Operator powers (always available)

The Operator is not just an approval gate - they are a live control
surface with unrestricted access to the entire Project at all times:

- Set and modify Project budgets - the top-level token / LLM cost ceilings.
- Pause or resume any Agent immediately.
- Pause or resume any work item - tasks, projects, subtask trees, milestones. Paused items are not picked up by Agents.
- Full project-management access - create, edit, comment, modify, delete, reassign anything via the UI.
- Override any Agent decision - reassign tasks, change priorities, edit descriptions.
- Manually change any budget at any level.

#### Budget delegation

The Operator sets the Project-level budget. The admin Agent can set budgets
for its reports, and any manager can do the same for theirs. The mechanics
of cascading delegation are still TBD; the permission structure already
supports it. The Operator may override any budget at any level.

#### Future governance models (out of V1)

Auto-approval of enables within `$X / month`, multi-member governance
boards, delegated authority bands.

### 1.3 Open questions

- External revenue / expense tracking is a future plugin. Token / LLM cost is core.
- Project-level settings and configuration?
- Project lifecycle: pause, archive, delete?
- What governance-gated actions exist beyond enabling and admin strategy approval?

---

## 2. Agent Model `[DRAFT]`

Every employee is an Agent. Agents are the workforce.

### 2.1 Identity belongs to the adapter

Concepts like `SOUL.md` (identity / mission) or `HEARTBEAT.md` (loop
definition) are **not** part of the GitMesh Agents protocol. They are
adapter-specific. A Gateway adapter might use `SOUL.md` and
`HEARTBEAT.md`. A Claude Code adapter might use `CLAUDE.md`. A bare
Python script might use CLI args. GitMesh Agents is the control plane;
the adapter defines the agent's inner workings.

### 2.2 What the GitMesh Agents protocol tracks

| Field | Notes |
|-------|-------|
| Agent identity | id, name, role, title |
| Org position | who they report to, who reports to them |
| Adapter type + adapter config | the runtime contract |
| Status | `active`, `paused`, `terminated` |
| Cost tracking data | when the agent reports it |

### 2.3 Adapter configuration

Each adapter defines its own config schema. Examples:

- Gateway adapter - `SOUL.md` content, `HEARTBEAT.md` content, gateway-specific settings.
- Process adapter - command, environment variables, working directory.
- HTTP adapter - endpoint URL, auth headers, payload template.

### 2.4 Exportable org configs

A whole Project's agent setup - every agent, every adapter config,
the org structure - is exportable as a portable artifact. Two modes:

- **Template export** (default) - structure only: agent definitions,
  org chart, adapter configs, role descriptions. Optionally seeds a few
  starter tasks. The blueprint for spinning up a fresh project.
- **Snapshot export**: structure plus current state: tasks, progress,
  agent status. A complete picture you can restore or fork.

The usual workflow is: export template &rarr; create new Project from it
&rarr; add a couple of initial tasks &rarr; go.

### 2.5 Context delivery

Configurable per agent, anywhere on this spectrum:

- **Fat payload**: GitMesh bundles relevant context (current tasks,
  messages, project state, metrics) into the heartbeat invocation. Suits
  simple, stateless agents that can't call back to GitMesh Agents.
- **Thin ping**: the heartbeat is just a wake signal; the agent
  pulls whatever context it needs via the API. Suits sophisticated agents
  that manage their own state.

### 2.6 Minimum contract & integration levels

The minimum requirement to be a GitMesh Agents agent is **be callable**.
GitMesh can invoke you via command or webhook; you are not required to
report back. Liveness is inferred from process state where possible.

Beyond the minimum, integration deepens in three steps:

1. Callable - GitMesh can start you.
2. Status reporting - you report success / failure / in-progress after execution.
3. Fully instrumented - you also report cost / token usage, task updates, and logs.

The shipped default agents are fully instrumented and double as reference
implementations. They depend on the **GitMesh Agents Playbook** (a Claude
Code skill) for API interactions.

---

## 3. Org Structure `[DRAFT]`

Hierarchical reporting tree. The admin sits at the top; reports cascade
down.

### 3.1 Visibility

Every agent can see the entire org chart, every task, every other agent.
The org structure encodes **reporting and delegation lines**, not access
control. Each agent publishes a short description of their
responsibilities and capabilities - a "when I'm relevant" pitch -
so other agents can discover who handles what.

### 3.2 Cross-team work

Agents may create tasks and assign them outside their reporting line. The
rules are mostly encoded in the `playbook.md` shared with all agents;
GitMesh enforces tooling and a small amount of governance.

#### Task acceptance

When an agent receives a task from outside their team, they have three
choices:

| Situation | Required action |
|-----------|-----------------|
| Appropriate + can do it | Complete it directly |
| Appropriate + can't do it | Mark as blocked |
| Worth doing is in question | **Cannot cancel.** Reassign to own manager with explanation; manager decides accept / reassign / escalate. |

#### Manager escalation protocol

Any manager owns understanding why their reports are blocked and resolving
the block:

0. Decide whether the work is worth doing.
1. Delegate down to someone else under them.
2. Failing that, escalate up to their own manager.

#### Request depth

Cross-team tasks track a `depth` integer - how many delegation hops from
the original requester. This lights up how far work has cascaded.

#### Billing codes

Tasks carry a billing code so token spend during execution attributes back
upstream. When Agent A asks Agent B to do work, B's cost lands on A's
request. This enables cross-team cost attribution.

### 3.3 Open questions

- Strict tree, or can agents report to multiple managers?
- Can org structure change at runtime (reassignments, restructures)?
- Do agents inherit any configuration from their manager?
- Billing code format - simple string or hierarchical?

---

## 4. Heartbeat System `[DRAFT]`

The heartbeat is a protocol, not a runtime. GitMesh defines how to start
an agent's cycle. What the agent does with that cycle - how long it runs,
whether it is task-scoped or continuous - is entirely up to the agent.

### 4.1 Initial adapters

| Adapter | Mechanism | Example |
|---------|-----------|---------|
| `process` | Spawn a child process | `python run_agent.py --agent-id {id}` |
| `http` | Send an HTTP request | `POST https://gateway.example.com/hook/{id}` |

These ship as defaults. Additional adapters arrive via the plugin system
(&sect;7.4).

### 4.2 Adapter contract

Three methods, full stop:

- `invoke(agentConfig, context?) -> void`: start the cycle.
- `status(agentConfig) -> AgentStatus`: running / finished / errored?
- `cancel(agentConfig) -> void`: graceful stop signal (powers pause).

Cost reporting and task updates are optional and flow through the
GitMesh Agents REST API.

### 4.3 What GitMesh controls vs. what it doesn't

| GitMesh controls | GitMesh does *not* control |
|---|---|
| When to fire the heartbeat (schedule / frequency, per agent) | How long the agent runs |
| How to fire it (adapter selection + config) | What the agent does during its cycle |
| What context to include (thin ping vs. fat payload, per agent) | Whether the agent is task-scoped, time-windowed, or continuous |

### 4.4 Pause behaviour

When the operator (or system) pauses an agent:

1. Send a graceful termination signal to the running process / session.
2. Wait the configured grace period for the agent to wrap up, save state, report final status.
3. Force-kill if it doesn't stop within the grace period.
4. Stop firing future heartbeats until the agent is resumed.

Net: graceful signal + stop future heartbeats. The current run gets a
chance to land cleanly.

### 4.5 Open questions

- Heartbeat frequency - fixed, per-agent, cron-like?
- What happens when a heartbeat invocation itself fails (process crash, HTTP 500)?
- Health monitoring - how do we distinguish "stuck" from "working on a long task"?
- Can agents self-trigger their next heartbeat (`I'm done, wake me again in 5 min`)?
- Grace period duration: fixed or per-agent?

---

## 5. Inter-Agent Communication `[DRAFT]`

All agent communication flows through the **task system**. There is no
separate messaging or chat system - tasks are the channel.

| What you want | How it works |
|---------------|--------------|
| Delegation | Create a task and assign it to another agent |
| Coordination | Comment on tasks |
| Status updates | Update task fields |

This keeps every conversation attached to the work it relates to, which
gives free audit trails.

Implications:

- An agent's "inbox" is the union of tasks assigned to them and comments on tasks they're involved in.
- The admin delegates by creating tasks assigned to the pr_review.
- The pr_review breaks those into sub-tasks for engineers.
- Discussion happens in task comments.
- Escalations are comments on the parent task or reassignments.

### 5.1 Task hierarchy mapping

Full hierarchy: **Initiative** (project goal) &rarr; Projects &rarr;
Milestones &rarr; Issues &rarr; Sub-issues. Everything traces back to an
Initiative; the "project goal" is just the first / primary Initiative.

---

## 6. Cost Tracking `[DRAFT]`

Token / LLM cost budgeting is core. External revenue and expense tracking
is a future plugin.

### 6.1 Reporting layers

Fully-instrumented agents report token / API usage back to GitMesh.
Aggregations happen at every level: per Agent, per task, per project, per
Project. Costs are denominated in both **tokens and dollars**. Billing
codes (&sect;3.2) roll spend across teams.

### 6.2 Three control tiers

1. **Visibility**: dashboards at each level (Agent, task, project, Project).
2. **Soft alerts**: configurable thresholds (e.g. warn at 80% of budget).
3. **Hard ceiling**: auto-pause the Agent when budget is hit; Operator notified, may override.

Budgets may be set to **unlimited** (no ceiling).

### 6.3 Open questions

- Cost reporting API schema?
- Which metrics matter most at each dashboard level?
- Budget period: per-day / per-week / per-month / rolling?

---

## 7. Default Agents, Bootstrap, and Architecture

### 7.1 Bootstrap sequence

How a Project goes from "created" to "running":

1. Human creates the Project and its initial Initiatives.
2. Human defines initial top-level tasks.
3. Human creates the admin Agent (default template or custom).
4. admin's first heartbeat reviews Initiatives and tasks; proposes a strategic breakdown (org structure, sub-tasks, enabling plan).
5. Operator approves the strategic plan.
6. admin begins execution - creating tasks, proposing enables, delegating.

### 7.2 Default agents

GitMesh ships templates:

- **Default Agent**: basic Claude Code or Codex loop. Knows the GitMesh Agents Playbook, so it can interact with the task system, read Project context, report status.
- **Default admin**: Default Agent + admin behaviour: strategic planning, delegation to reports, progress review, Operator communication.

These are starting points; users may customise or replace them entirely.
The default agent loop is **config-driven**: the adapter config holds the
instructions that define what the agent does each cycle. There is no
hardcoded standard loop.

### 7.3 GitMesh Agents Playbook (`playbook.md`)

A Claude Code skill that teaches agents how to interact with GitMesh
Agents. Provides task CRUD, status reporting, project context, cost
reporting, and inter-agent communication rules. Adapter-agnostic - can
be loaded into Claude Code, injected into prompts, or used as API docs for
custom agents.

### 7.4 Deployment & extension

#### Deployment model

Single-tenant, self-hostable. **Not a SaaS.** One instance == one
operator's projects.

Progressive deployment path:

1. **Local dev**: one command to install and run; embedded Postgres; everything on your machine; agents run locally.
2. **Hosted**: deploy to Vercel / Supabase / AWS / anywhere. Remote agents connect to your server with a shared database. UI accessible via web.
3. **Open project**: optionally make parts public (e.g. a public job operator for an open project).

The constraint: it must be trivial to go from "trying this on my laptop"
to "agents running on remote servers talking to my GitMesh Agents instance."

#### Agent authentication

When an Agent is created, GitMesh generates a **connection string** -
server URL + API key + instructions. The human supplies that to the Agent
(adapter config, environment, ...); the Agent uses the key to call the
control plane.

#### Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | React + Vite |
| Backend | TypeScript + Hono (REST, not tRPC - non-TS clients matter) |
| Database | PostgreSQL (PGlite embedded for dev; Docker / hosted Supabase in production - see [doc/DATABASE.md](./DATABASE.md)) |
| Auth | [Better Auth](https://www.better-auth.com/) |

#### Concurrency: atomic task checkout

Single-assignee tasks with **atomic checkout**. The agent attempts to set
a task to `in_progress`; the API enforces this atomically. If another
agent already has it, the request fails with the offending agent
identified. If the task already belongs to the requester (from a previous
session), they may resume. No optimistic locking, no CRDTs - the design
prevents conflicts upstream.

#### Human in the loop

Agents may create tasks assigned to humans. The Operator (or any human
with access) completes them through the UI. When a human completes a task,
if the requesting agent's adapter supports **pingbacks** (e.g. gateway
hooks), GitMesh wakes that agent. Humans are rare but possible
participants. Agents are explicitly discouraged from assigning to humans
in the playbook, but it is sometimes unavoidable.

#### API design

**One unified REST API** for both UI and agents. Authentication
determines permissions: operator auth gets full access; agent API keys
are scoped (own tasks, cost reporting, project context). No separate
"agent API" vs. "operator API."

#### Work artifacts

Out of scope. GitMesh tracks tasks and costs. Code repos, file systems,
deployments, documents - all the agent's domain.

#### Crash recovery: manual, not automatic

When an agent crashes mid-task, GitMesh does **not** auto-reassign or
auto-release. Instead it surfaces stale tasks (`in_progress` with no
recent activity) through dashboards and reporting. The auditing and
visibility tools make problems obvious; recovery is handled by humans or
by emergent processes (e.g. a project-manager agent whose job is to spot
stale work).

> Principle: GitMesh reports problems, it does not silently fix them.
> Automatic recovery hides failures; good visibility lets the right
> entity decide what to do.

#### Plugin / extension architecture

Core must be extensible. Knowledge bases, external revenue tracking, new
Agent Adapters - all should be addable as plugins without modifying
core. Required ingredients:

- Well-defined API boundaries plugins can hook into.
- Event system / hooks for task and Agent lifecycle events.
- Agent Adapter plugins (new adapter types registered via the plugin system).
- Plugin-registrable UI components (future).

This isn't a V1 deliverable, but architectural choices must not paint us
into a corner.

#### Open architecture questions

- Realtime updates: WebSocket, SSE, or polling?
- Agent API key scoping: own tasks only, team's tasks, or whole Project?

---

## 8. Frontend / UI `[DRAFT]`

### 8.1 Primary views (each a distinct route)

1. **Org Chart**: the org tree with live status indicators per agent (running / idle / paused / error) and a realtime activity feed.
2. **Task Operator**: task management; kanban + list views; filter by team, agent, project, status.
3. **Dashboard**: high-level metrics (agent count, active tasks, cost, goal progress, burn rate). The "glance" view from `GOAL.md`.
4. **Agent Detail**: deep dive on one agent: tasks, activity, costs, configuration, status history.
5. **Project / Initiative Views**: progress tracking against milestones and goals.
6. **Cost Dashboard**: spend visualisation at every level (agent, task, project, Project).

### 8.2 Operator controls (available everywhere)

- Pause / resume agents (any view).
- Pause / resume tasks / projects (any view).
- Approve / reject pending actions (enabling, strategy proposals).
- Direct task creation, editing, commenting.

---

## 9. V1 Scope `[DRAFT]`

V1 demonstrates the complete GitMesh cycle end-to-end with one adapter,
even if narrow.

### 9.1 Must have

- [ ] Project CRUD - create a Project with Initiatives.
- [ ] Agent CRUD - create / edit / pause / resume Agents with Adapter config.
- [ ] Org chart - define reporting structure, visualise it.
- [ ] Process adapter - `invoke` / `status` / `cancel` for local child processes.
- [ ] Task management - full lifecycle with hierarchy (every task traces to a project goal).
- [ ] Atomic task checkout - single assignment, `in_progress` locking.
- [ ] Operator governance - approve enables, pause Agents, set budgets, full PM access.
- [ ] Cost tracking - Agents report token usage; per-Agent / task / Project visibility.
- [ ] Budget controls - soft alerts + hard ceiling with auto-pause.
- [ ] Default agent - basic Claude Code / Codex loop with the GitMesh Agents playbook.
- [ ] Default admin - strategic planning, delegation, operator communication.
- [ ] GitMesh Agents Playbook (`playbook.md`) - teaches agents to interact with the API.
- [ ] REST API - full API for agent interaction (Hono).
- [ ] Web UI - React / Vite: org chart, task operator, dashboard, cost views.
- [ ] Agent auth - connection string generation with URL + key + instructions.
- [ ] One-command dev setup - embedded PGlite, everything local.
- [ ] Multiple Adapter types (HTTP Adapter, Gateway Adapter).

### 9.2 Not V1

- Template export / import.
- Knowledge base (future plugin).
- Advanced governance models (enabling budgets, multi-member boards).
- Revenue / expense tracking beyond token costs (future plugin).
- Public job operator / open project features.

---

## 10. Knowledge Base - Anti-Goal for Core

Not part of GitMesh core; will be a plugin. The task system + comments +
agent descriptions provide enough shared context for V1. Architecture must
support adding a knowledge-base plugin later (clean API boundaries,
hookable lifecycle events) but core explicitly does not include one.

---

## 11. (Reserved for future invariant)

---

## 12. Anti-Requirements

Things GitMesh Agents explicitly does **not** do:

- Not an Agent runtime - GitMesh orchestrates, Agents run elsewhere.
- Not a knowledge base - no wiki / docs / vector DB in core (plugin territory).
- Not a SaaS - single-tenant, self-hosted.
- Not opinionated about Agent implementation - any language, framework, runtime.
- Not automatically self-healing - surfaces problems; does not silently fix them.
- Does not manage work artifacts - no repo management, deployment, file systems.
- Does not auto-reassign work - stale tasks are surfaced, not silently redistributed.
- Does not track external revenue / expenses - future plugin.

---

## 13. Principles (Consolidated)

1. **Unopinionated about how you run your Agents.** Any language, framework, runtime. GitMesh is the control plane, not the execution plane.
2. **Project is the unit of organisation.** Everything lives under a Project.
3. **Tasks are the communication channel.** All Agent communication flows through tasks + comments. No side channels.
4. **All work traces to the goal.** Hierarchical task management; nothing exists in isolation.
5. **Operator governs.** Humans retain control through the Operator. Conservative defaults - human approval required.
6. **Surface problems, don't hide them.** Good auditing and visibility. No silent auto-recovery.
7. **Atomic ownership.** Single assignee per task. Atomic checkout prevents conflicts.
8. **Progressive deployment.** Trivial to start local; straightforward to scale to hosted.
9. **Extensible core.** Clean boundaries so plugins can add capabilities (Adapters, knowledge base, revenue tracking) without modifying core.
