# Spec: Agent Runs

**Status** Draft &middot; **Audience** Product + Engineering &middot; **Last revised** 2026-02-17

This spec narrows the V1 baseline (`doc/v1-spec.md`) to the runtime that
actually executes agents: adapter protocol, wakeup orchestration, persisted
state, and live status delivery to the browser. Where this document conflicts
with current behaviour in code, this document is the target.

---

## TL;DR for reviewers

- The agent-execution path is split across six cooperating components - an adapter registry, a wakeup coordinator, a run executor, a runtime-state store, a run-log store, and a realtime event hub.
- All adapters speak `agent-run/v1`. `claude_local` and `codex_local` ship as built-ins; `process` and `http` remain available unchanged.
- Resumable session state lives per `(project, agent, adapter, task_key)` row, not on the agent itself.
- Wakeups always pass through `enqueueWakeup({source, ...})`. Direct adapter invocation is forbidden.
- Full run logs live in a pluggable `RunLogStore`. Only excerpts and lightweight events go into Postgres.
- The browser receives state changes via a per-project websocket; SSE/polling are fallbacks only.

---

## 1. Captured intent

The numbered intentions below are reproduced verbatim from the originating
request and are non-negotiable: any change to these requires a follow-up spec.

1. GitMesh Agents is adapter-agnostic. The key is a protocol, not a specific runtime.
2. We still need default built-ins to make the system useful immediately.
3. First two built-ins are `claude-local` and `codex-local`.
4. Those adapters run local CLIs directly on the host machine, unsandboxed.
5. Agent config includes working directory and initial/default prompt.
6. Heartbeats run the configured adapter process, GitMesh Agents manages lifecycle, and on exit GitMesh Agents parses JSON output and updates state.
7. Session IDs and token usage must be persisted so later heartbeats can resume.
8. Adapters should support status updates (short message + color) and optional streaming logs.
9. UI should support prompt template "pills" for variable insertion.
10. CLI errors must be visible in full (or as much as possible) in the UI.
11. Status changes must live-update across task and agent views via server push.
12. Wakeup triggers must be centralised by a heartbeat/wakeup service that supports timer interval, wake on assignment, and explicit ping/request.

---

## 2. Goals & non-goals

| In scope | Out of scope (this phase) |
|---|---|
| Stable adapter protocol covering multiple runtimes | Distributed execution across multiple worker hosts |
| Production-usable `claude-local` and `codex-local` | Third-party adapter marketplace / public plugin SDK |
| Persisted runtime state (sessions, usage, last error) | Cost reconciliation for providers that don't emit cost |
| One queue/wakeup abstraction across all triggers | Long-term log archival beyond basic retention |
| Realtime push to the browser for run/task/agent state | &nbsp; |
| Pluggable storage for full stdout/stderr | &nbsp; |
| Project scoping + existing governance invariants | &nbsp; |

---

## 3. Baseline: what exists, what's missing

What's already in the tree (as of 2026-02-17): an `agents` table with
`adapterType` + `adapterConfig`, `heartbeat_runs` with basic status tracking,
an in-process `heartbeatService` that handles `process` and `http`, and
cancellation endpoints for active runs.

The deltas this spec closes:

- No persisted per-agent runtime state &rarr; **&sect;6**
- No queue/wakeup abstraction (invoke is immediate) &rarr; **&sect;5**
- No assignment- or timer-triggered centralised wakeups &rarr; **&sect;5**
- No websocket/SSE push to the browser &rarr; **&sect;8**
- No persisted run-event timeline / external full-log storage &rarr; **&sect;6, &sect;9**
- No typed contracts for Claude/Codex session and usage extraction &rarr; **&sect;4**
- No prompt-template variable system &rarr; **&sect;7**
- No deployment-aware run-log adapter &rarr; **&sect;6**

---

## 4. Adapter protocol - `agent-run/v1`

All adapters - built-in or otherwise - conform to one TypeScript surface.
Behaviour requirements live alongside the shapes.

### Top-level types

`RunOutcome` is one of `succeeded`, `failed`, `cancelled`, `timed_out`. A
status update carries one of five colours: `neutral`, `blue`, `green`,
`yellow`, `red`.

Token usage:

```ts
interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cachedInputTokens?: number;
  cachedOutputTokens?: number;
}
```

### `AdapterInvokeInput`

What the executor hands the adapter:

```ts
interface AdapterInvokeInput {
  protocolVersion: "agent-run/v1";
  projectId: string;
  agentId: string;
  runId: string;
  wakeupSource: "timer" | "assignment" | "on_demand" | "automation";
  triggerDetail?: "manual" | "ping" | "callback" | "system";
  cwd: string;
  prompt: string;
  adapterConfig: Record<string, unknown>;
  runtimeState: Record<string, unknown>;
  env: Record<string, string>;
  timeoutSec: number;
}
```

### `AdapterHooks`

Optional async sinks the adapter calls during execution:

- `status({ message, color? })`: surface short progress text
- `log({ stream, chunk })`: live log chunk for `stdout` / `stderr` / `system`
- `usage(usage)`: emit a usage update mid-run
- `event(eventType, payload)`: structured custom events

### `AdapterInvokeResult`

```ts
interface AdapterInvokeResult {
  outcome: RunOutcome;
  exitCode: number | null;
  errorMessage?: string | null;
  summary?: string | null;
  sessionId?: string | null;
  usage?: TokenUsage | null;
  provider?: string | null;
  model?: string | null;
  costUsd?: number | null;
  runtimeStatePatch?: Record<string, unknown>;
  rawResult?: Record<string, unknown> | null;
}
```

### `AgentRunAdapter`

Each registered adapter exposes:

- `type`: matches `agents.adapter_type`
- `protocolVersion`: always `"agent-run/v1"`
- `capabilities`: `{ resumableSession, statusUpdates, logStreaming, tokenUsage }`
- `validateConfig(config)`: runs before save and before invoke
- `invoke(input, hooks, signal)`: returns an `AdapterInvokeResult`

### Behaviour rules

Required:

1. `validateConfig` runs before saving or invoking.
2. `invoke` is deterministic for a given `(config, runtimeState, prompt)` triple.
3. Adapters never mutate the database. State changes flow back through the result and event hooks only.
4. Errors carry enough context to debug. If `invoke` throws, the executor records the run as `failed` with the captured text.

Optional:

- Adapters may omit `status` and `log` hooks. The runtime still emits the
  built-in lifecycle statuses (`queued`, `running`, `finished`).

### Adapter identity

The V1 adapter set is closed:

| Adapter | Notes |
|---------|-------|
| `claude_local` | Typed wrapper around Claude CLI - not a thin `process` shim |
| `codex_local` | Typed wrapper around Codex CLI - not a thin `process` shim |
| `process` | Generic existing behaviour |
| `http` | Generic existing behaviour |

---

## 5. Wakeup coordinator

Everything that wants to run an agent enqueues; the coordinator decides what
runs next. There is exactly one entrypoint:

```ts
enqueueWakeup({
  projectId,
  agentId,
  source,           // "timer" | "assignment" | "on_demand" | "automation"
  triggerDetail,    // "manual" | "ping" | "callback" | "system" (optional)
  reason,
  payload,
  requestedBy,
  idempotencyKey?,
});
```

### Queue semantics

- An agent has at most one active run at any time.
- New wakeups for an agent that already has a `queued` or `running` request are coalesced. `coalescedCount` increments; the latest reason and source metadata wins.
- The queue is DB-backed so a server restart does not drop pending work.
- Default ordering is FIFO by `requested_at`. Optional priority: `on_demand` > `assignment` > `timer` / `automation`.

### Trigger integration

- Timer - a worker interval enqueues every agent whose timer is due.
- Assignment - the issue assignment mutation enqueues the new assignee when `wakeOnAssignment` is true.
- On-demand - the dedicated endpoint enqueues with `source = on_demand` and `triggerDetail` of `manual` or `ping`.
- Automation - callback / system flows enqueue with `source = automation` and `triggerDetail` of `callback` or `system`.
- Paused, terminated, and hard-budget-stopped agents do not receive new wakeups.

### Per-agent heartbeat policy

These knobs live in the agent's `runtime_config` (separate from
`adapter_config`):

```json
{
  "heartbeat": {
    "enabled": true,
    "intervalSec": 300,
    "wakeOnAssignment": true,
    "wakeOnOnDemand": true,
    "wakeOnAutomation": true,
    "cooldownSec": 10
  }
}
```

Defaults: `enabled = true`, `intervalSec = null` (no timer until set; product
default of `300` may be applied globally), all `wakeOn*` flags `true`.

---

## 6. Persistence model

All tables remain project-scoped.

### `agents` (modifications)

- `adapter_type` domain extends to include `claude_local` and `codex_local`.
- `adapter_config` continues to hold adapter-owned values (CLI flags, cwd, prompt templates, env overrides).
- New `runtime_config` jsonb column holds the heartbeat policy (interval, wake-on-* flags, cooldown).

The `adapter_config` / `runtime_config` split keeps adapter behaviour
runtime-agnostic while the heartbeat service applies one policy model
everywhere.

### New table: `agent_runtime_state` (one row per agent)

| Column | Type | Notes |
|--------|------|-------|
| `agent_id` | uuid pk fk `agents.id` | |
| `project_id` | uuid fk | not null |
| `adapter_type` | text | not null |
| `session_id` | text | nullable; legacy aggregate session pointer |
| `state_json` | jsonb | not null, default `{}` |
| `last_run_id` | uuid fk `heartbeat_runs.id` | nullable |
| `last_run_status` | text | nullable |
| `total_input_tokens` | bigint | not null, default 0 |
| `total_output_tokens` | bigint | not null, default 0 |
| `total_cached_input_tokens` | bigint | not null, default 0 |
| `total_cost_cents` | bigint | not null, default 0 |
| `last_error` | text | nullable |
| `updated_at` | timestamptz | not null |

Invariant: exactly one row per agent.

### New table: `agent_task_sessions`

One row per `(project_id, agent_id, adapter_type, task_key)`. Columns:

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid pk | |
| `project_id` | uuid fk | not null |
| `agent_id` | uuid fk | not null |
| `adapter_type` | text | not null |
| `task_key` | text | not null |
| `session_params_json` | jsonb | adapter-defined shape |
| `session_display_id` | text | for UI/debug |
| `last_run_id` | uuid fk `heartbeat_runs.id` | nullable |
| `last_error` | text | nullable |
| `created_at` | timestamptz | not null |
| `updated_at` | timestamptz | not null |

Unique on `(project_id, agent_id, adapter_type, task_key)`.

### New table: `agent_wakeup_requests`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid pk | |
| `project_id` | uuid fk | not null |
| `agent_id` | uuid fk | not null |
| `source` | text | `timer` &#124; `assignment` &#124; `on_demand` &#124; `automation` |
| `trigger_detail` | text | `manual` &#124; `ping` &#124; `callback` &#124; `system` |
| `reason` | text | nullable |
| `payload` | jsonb | nullable |
| `status` | text | `queued` &#124; `claimed` &#124; `coalesced` &#124; `skipped` &#124; `completed` &#124; `failed` &#124; `cancelled` |
| `coalesced_count` | int | not null, default 0 |
| `requested_by_actor_type` | text | `user` &#124; `agent` &#124; `system` |
| `requested_by_actor_id` | text | nullable |
| `idempotency_key` | text | nullable |
| `run_id` | uuid fk `heartbeat_runs.id` | nullable |
| `requested_at` | timestamptz | not null |
| `claimed_at` | timestamptz | nullable |
| `finished_at` | timestamptz | nullable |
| `error` | text | nullable |

### New table: `heartbeat_run_events`

Append-only lightweight per-run timeline (no full stream chunks).

Columns: `id` (bigserial pk), `project_id` fk, `run_id` fk, `agent_id` fk,
`seq` int, `event_type` (`lifecycle` &#124; `status` &#124; `usage` &#124; `error` &#124; `structured`),
`stream` (`system` &#124; `stdout` &#124; `stderr`: summarised events only),
`level` (`info` &#124; `warn` &#124; `error`), `color`, `message`, `payload` jsonb,
`created_at`.

### `heartbeat_runs` (column additions)

- `wakeup_request_id` uuid fk, nullable
- `exit_code` int, nullable
- `signal` text, nullable
- `usage_json` jsonb, nullable
- `result_json` jsonb, nullable
- `session_id_before` text, nullable
- `session_id_after` text, nullable
- `log_store` text, nullable (`local_file` &#124; `object_store` &#124; `postgres`)
- `log_ref` text, nullable (opaque path / key / uri / row id)
- `log_bytes` bigint, nullable
- `log_sha256` text, nullable
- `log_compressed` boolean, not null, default false
- `stderr_excerpt` text, nullable
- `stdout_excerpt` text, nullable
- `error_code` text, nullable

The `log_*` columns keep per-run diagnostics queryable without parking full
logs in Postgres.

### Run-log storage protocol

Full logs are managed by a separate pluggable store (not by the adapter).

```ts
type RunLogStoreType = "local_file" | "object_store" | "postgres";

interface RunLogHandle {
  store: RunLogStoreType;
  logRef: string; // opaque provider reference (path | key | uri | row id)
}

interface RunLogStore {
  begin(input: { projectId: string; agentId: string; runId: string }): Promise<RunLogHandle>;
  append(handle: RunLogHandle, event: { stream: "stdout" | "stderr" | "system"; chunk: string; ts: string }): Promise<void>;
  finalize(handle: RunLogHandle, summary: { bytes: number; sha256?: string; compressed: boolean }): Promise<void>;
  read(handle: RunLogHandle, opts?: { offset?: number; limitBytes?: number }): Promise<{ content: string; nextOffset?: number }>;
  delete?(handle: RunLogHandle): Promise<void>;
}
```

V1 deployment defaults:

- Dev / local: `local_file` (writes to `data/run-logs/...`)
- Cloud / serverless: `object_store` (S3 / R2 / GCS-compatible)
- Optional fallback: `postgres` with strict size caps

Configuration shape (deployment-level, not per-agent):

```json
{
  "runLogStore": {
    "type": "local_file | object_store | postgres",
    "basePath": "./data/run-logs",
    "bucket": "gitmesh-agents-run-logs",
    "prefix": "runs/",
    "compress": true,
    "maxInlineExcerptBytes": 32768
  }
}
```

Rules:

1. `log_ref` is opaque and provider-neutral at API boundaries.
2. UI / API code must not assume local filesystem semantics.
3. Provider credentials live in server config, never in agent config.

---

## 7. Built-in adapters - phase 1

### `claude-local`

Runs the local `claude` CLI. Config:

```json
{
  "cwd": "/absolute/or/relative/path",
  "promptTemplate": "You are agent {{agent.id}} ...",
  "model": "optional-model-id",
  "maxTurnsPerRun": 80,
  "dangerouslySkipPermissions": true,
  "env": {"KEY": "VALUE"},
  "extraArgs": [],
  "timeoutSec": 1800,
  "graceSec": 20
}
```

Invocation:

- Base: `claude --print <prompt> --output-format json`
- Resume: append `--resume <sessionId>` when `runtimeState` carries one
- Unsandboxed: append `--dangerously-skip-permissions` when enabled

Output parsing:

1. Parse stdout JSON object.
2. Read `session_id` for resume.
3. Read usage: `usage.input_tokens`, `usage.cache_read_input_tokens` (if present), `usage.output_tokens`.
4. Read `total_cost_usd` when present.
5. On non-zero exit: still attempt parse. If parse succeeds, keep the extracted state; mark the run failed unless the adapter explicitly reports success.

### `codex-local`

Runs the local `codex` CLI. Config:

```json
{
  "cwd": "/absolute/or/relative/path",
  "promptTemplate": "You are agent {{agent.id}} ...",
  "model": "optional-model-id",
  "search": false,
  "dangerouslyBypassApprovalsAndSandbox": true,
  "env": {"KEY": "VALUE"},
  "extraArgs": [],
  "timeoutSec": 1800,
  "graceSec": 20
}
```

Invocation:

- Base: `codex exec --json <prompt>`
- Resume: `codex exec --json resume <sessionId> <prompt>`
- Unsandboxed: append `--dangerously-bypass-approvals-and-sandbox`
- Optional search mode: append `--search`

Output (JSONL, one event per line). Extract:

1. `thread.started.thread_id` &rarr; session id
2. `item.completed` where item type is `agent_message` &rarr; output text
3. `turn.completed.usage` &rarr; `input_tokens`, `cached_input_tokens`, `output_tokens`

Codex JSONL may not include cost. Persist token usage; leave cost null when
unavailable.

### Common process handling

Both local adapters must:

1. Use `spawn(command, args, { shell: false, stdio: "pipe" })`.
2. Capture stdout/stderr in stream chunks and forward to `RunLogStore`.
3. Maintain rolling stdout / stderr tail excerpts in memory for DB diagnostic columns.
4. Emit live log events to websocket subscribers (throttling/chunking optional).
5. Cancel gracefully: `SIGTERM`, then `SIGKILL` after `graceSec`.
6. Enforce `timeoutSec`.
7. Return exit code, parsed result, and diagnostic stderr.

---

## 8. Prompt template & pill system

### Format

- Mustache-style placeholders: `{{path.to.value}}`
- No code execution
- Unknown variable on save = validation error

### Variable catalog (initial)

`project.id`, `project.name`, `agent.id`, `agent.name`, `agent.role`,
`agent.title`, `run.id`, `run.source`, `run.startedAt`, `heartbeat.reason`,
`gitmesh-agents.skill`, `credentials.apiBaseUrl`, `credentials.apiKey`
(sensitive).

### Prompt fields

`promptTemplate` is used on every wakeup - first run and resumed runs alike
and may include run source / reason pills.

### UI requirements

- The agent setup / edit form ships prompt editors with pill insertion.
- Variables render as clickable pills.
- Save-time validation flags unknown or missing variables.
- Sensitive pills (`credentials.*`) carry an explicit warning badge.

### Credentials in prompts

- Allowed for early simplicity, discouraged in practice.
- Preferred transport is environment vars (`GITMESH_*`) injected at runtime.
- Prompt previews and logs always redact sensitive values.

---

## 9. Realtime delivery

### Transport

Per-project websocket. Endpoint: `GET /api/projects/:projectId/events/ws`.
Auth: operator session or project-bound agent API key.

### Envelope

```json
{
  "eventId": "uuid-or-monotonic-id",
  "projectId": "uuid",
  "type": "heartbeat.run.status",
  "entityType": "heartbeat_run",
  "entityId": "uuid",
  "occurredAt": "2026-02-17T12:00:00Z",
  "payload": {}
}
```

### Required event types

- `agent.status.changed`
- `heartbeat.run.queued`
- `heartbeat.run.started`
- `heartbeat.run.status`: short colour + message updates
- `heartbeat.run.log`: optional live chunks; full persistence stays in `RunLogStore`
- `heartbeat.run.finished`
- `issue.updated`
- `issue.comment.created`
- `activity.appended`

### UI behaviour

- Agent detail view streams the run timeline live.
- Task operator reflects assignment / status / comment changes from agent activity without refresh.
- Org and agent lists update status changes live.
- On disconnect, the client falls back to short polling until reconnect.

---

## 10. Errors, diagnostics, recovery

### Error class enum

`adapter_not_installed`, `invalid_working_directory`, `spawn_failed`,
`timeout`, `cancelled`, `nonzero_exit`, `output_parse_error`,
`resume_session_invalid`, `budget_blocked`.

### Logging requirements

1. Persist full stdout / stderr to the configured `RunLogStore`.
2. Postgres carries lightweight metadata and events only (`heartbeat_runs`, `heartbeat_run_events`).
3. Bounded `stdout_excerpt` and `stderr_excerpt` columns hold quick-look diagnostics.
4. Truncation is marked explicitly when excerpts are capped.
5. Secrets are redacted from logs, excerpts, and websocket payloads.

### Retention & lifecycle

- `RunLogStore` retention is deployment-configurable (e.g. 7/30/90 days).
- Postgres run metadata may outlive full log objects.
- Pruning jobs handle orphaned metadata / log-object references safely.
- If the full log object is gone, APIs still return metadata + excerpts with a `log_unavailable` status.

### Restart recovery

On server startup:

1. Find stale `queued` or `running` runs.
2. Mark them `failed` with `error_code = control_plane_restart`.
3. Set the affected non-paused / non-terminated agents to `error` (or `idle`, per policy).
4. Emit recovery events to websocket and activity log.

---

## 11. API surface

### Endpoints (new + updated)

| Method & path | Purpose |
|---|---|
| `POST /agents/:agentId/wakeup` | Enqueue a wakeup with source / reason |
| `POST /agents/:agentId/heartbeat/invoke` | Backward-compatible alias for the wakeup API |
| `GET /agents/:agentId/runtime-state` | Operator-only debug view |
| `GET /agents/:agentId/task-sessions` | Operator-only list of task-scoped adapter sessions |
| `POST /agents/:agentId/runtime-state/reset-session` | Clear all task sessions; clear one when `taskKey` is supplied |
| `GET /heartbeat-runs/:runId/events?afterSeq=:n` | Fetch the persisted lightweight timeline |
| `GET /heartbeat-runs/:runId/log` | Read the full log via `RunLogStore` (may redirect / presign) |
| `GET /api/projects/:projectId/events/ws` | The realtime websocket |

### Required `activity_log` events

Every wakeup or run state mutation writes one of:
`wakeup.requested`, `wakeup.coalesced`, `heartbeat.started`,
`heartbeat.finished`, `heartbeat.failed`, `heartbeat.cancelled`,
`runtime_state.updated`.

---

## 12. Implementation plan

| Phase | Output |
|-------|--------|
| 1 - contracts & schema | New tables / columns (`agent_runtime_state`, `agent_wakeup_requests`, `heartbeat_run_events`, `heartbeat_runs.log_*`); `RunLogStore` interface and config wiring; shared types / constants / validators; existing routes stay functional during migration |
| 2 - wakeup coordinator | DB-backed wakeup queue; convert invoke / wake routes to enqueue with `source = on_demand`; worker loop to claim and execute |
| 3 - local adapters | `claude-local` and `codex-local`; session-id and token-usage parsing; cancel / timeout / grace |
| 4 - realtime push | Project websocket hub; publish run / agent / issue events; UI subscribes and invalidates |
| 5 - prompt pills & config UX | Adapter-specific config editor; pill insertion + variable validation; sensitive-variable warnings + redaction |
| 6 - hardening | Failure / restart recovery sweeps; metadata + full-log retention policies and pruning jobs; integration / e2e coverage for triggers and live updates |

---

## 13. Acceptance criteria

- An agent with `claude-local` or `codex-local` runs, exits, and persists its run result.
- Session parameters are persisted per task scope and reused automatically for same-task resumes.
- Token usage is persisted per run and accumulated in the agent's runtime state.
- Timer, assignment, on-demand, and automation wakeups all enqueue through one coordinator.
- Pause / terminate interrupts the running local process and prevents new wakeups.
- The browser receives live websocket updates for run status / logs and task / agent changes.
- Failed runs expose rich CLI diagnostics in the UI - excerpts immediately, full logs retrievable via `RunLogStore`.
- Every action remains project-scoped and auditable.

---

## 14. Open questions

1. Default timer: `null` (off until enabled) or `300` seconds globally?
2. Default retention for full log objects vs. Postgres metadata?
3. Should agent API credentials be allowed in prompt templates by default, or require an explicit opt-in toggle?
4. Is websocket the only realtime channel, or should we also expose SSE for simpler clients?
