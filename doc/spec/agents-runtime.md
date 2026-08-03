# Operator Guide: Agent Runtime

> **Audience** Operators standing up and running agents in GitMesh Agents.
> **Updated** 2026-02-17.

## Quickstart (minimal viable agent)

1. Pick an adapter: `claude_local` or `codex_local`.
2. Set `cwd` to the workspace you want the agent to work in.
3. Write a prompt template (the default is fine; see [Prompts](#prompts)).
4. Decide your wakeup policy - timer, on-assignment, or both.
5. Trigger one manual wakeup; confirm the run completes and that token usage / session state were recorded.
6. Watch the live UI updates and iterate.

That's it. The rest of this guide explains what each of those pieces is doing.

---

## Mental model

Agents in GitMesh Agents are **not long-running processes**. The control
plane wakes them, lets them work, and shuts them back down. One wake = one
heartbeat. A heartbeat:

- starts the configured agent adapter (Claude CLI, Codex CLI, ...);
- hands it the current prompt and context;
- lets it run until it exits, times out, or is cancelled;
- records status, token usage, errors, and logs;
- pushes the result to your browser in real time.

If a new wakeup arrives while the agent is already running, the new request
is **coalesced** into the existing one rather than launching a duplicate.

---

## Wakeup sources

| Source | When it fires |
|--------|---------------|
| `timer` | A scheduled interval (e.g. every 5 minutes) |
| `assignment` | Work has been assigned or checked out to this agent |
| `on_demand` | A button click or API ping - explicitly user-initiated |
| `automation` | A system or callback-triggered wake (future automation hooks) |

---

## Configuration map

The agent's settings split into three separate concerns. The fastest way to
read each agent is to look at the three blocks in order.

### 1. Adapter choice (which runtime?)

| Adapter | What it runs |
|---------|---|
| `claude_local` | Your local `claude` CLI (must be installed and authenticated on the host) |
| `codex_local` | Your local `codex` CLI (must be installed and authenticated on the host) |
| `process` | A generic shell command |
| `http` | A POST to an external endpoint |

### 2. Runtime / heartbeat policy

These knobs control _when_ the agent runs:

- `enabled`: allow scheduled heartbeats at all
- `intervalSec`: timer interval (`0` disables timer wakes)
- `wakeOnAssignment`: wake when work is assigned
- `wakeOnOnDemand`: allow ping-style on-demand wakes
- `wakeOnAutomation`: allow system-automation wakes

### 3. Local-adapter execution settings

These knobs control _how_ the local CLI is invoked:

- `cwd`: working directory
- `timeoutSec`: max runtime per heartbeat
- `graceSec`: time before force-kill after timeout/cancel
- `env`: optional environment overrides
- `extraArgs`: optional CLI args appended to every invocation

---

## Prompts

You set one field, `promptTemplate`. It is used for every run - first
run and resumed runs alike. Templates support variables such as
`{{agent.id}}`, `{{agent.name}}`, plus run-context values
(`{{run.source}}`, `{{heartbeat.reason}}`, `{{project.name}}`, ...).

Treat the template editor as a small DSL: the variables become "pills"
inserted from the form. Save-time validation rejects unknown variables.

---

## Sessions

Sessions let an agent resume the same conversation across heartbeats.
GitMesh Agents stores resumable state per
`(agent, taskKey, adapterType)`. The `taskKey` is derived from wakeup
context - explicit `taskKey`, otherwise `taskId`, otherwise `issueId`.

Behaviour:

- Heartbeats for the **same task key** reuse the previous session.
- Heartbeats for **different task keys** keep separate state.
- If a restore fails, adapters retry once with a fresh session and continue.
- You can reset all sessions for an agent or just one task session by key.

Reset sessions when:

- you significantly changed the prompt strategy;
- the agent is stuck in a bad loop;
- you want a clean restart.

---

## Logs, status, and run history

Every run gives you:

- run status - one of `queued`, `running`, `succeeded`, `failed`, `timed_out`, `cancelled`;
- error text plus stderr / stdout excerpts;
- token usage and cost (when the adapter reports it);
- full logs - stored outside the core run row, optimised for large output.

In local / dev setups, full logs land on disk under the configured run-log
path.

---

## Realtime updates

GitMesh Agents pushes runtime and activity changes to the browser as they
happen. You should see live updates for:

- agent status;
- heartbeat run status;
- task and activity changes caused by agent work;
- dashboard, cost, and activity panels (where relevant).

If the connection drops, the UI reconnects automatically.

---

## Operating patterns

These three patterns cover most setups. Pick the closest and tweak.

### Autonomous loop (steady-state)

- Timer enabled at e.g. 300s.
- `wakeOnAssignment` on.
- A focused, narrow prompt template.
- Watch logs; iterate prompt + config over time.

### Event-driven (less polling)

- Timer disabled (or set very long).
- `wakeOnAssignment` on.
- Use on-demand wakeups for manual nudges.

### Safety-first (high-risk environments)

- Short `timeoutSec`.
- Conservative prompt.
- Monitor errors; cancel quickly when needed.
- Reset sessions whenever drift appears.

---

## Troubleshooting

When runs keep failing, walk this list in order. Stop at the first thing
that turns out to be the cause:

1. Is the adapter CLI (`claude` / `codex`) installed and authenticated on the host?
2. Does `cwd` exist and is the server user permitted to enter it?
3. What does the run's error code + stderr excerpt say? (then open the full log)
4. Is `timeoutSec` too low for what you're asking?
5. Reset the session and retry.
6. Pause the agent if it's making bad updates faster than you can fix them.

Most failures map to one of: CLI not installed / authenticated, wrong cwd,
malformed args / env, prompt too broad, or process timeout.

---

## Security notes

Local CLI adapters run **unsandboxed** on the host. Practical implications:

- Prompt instructions are part of your trust boundary.
- Configured env vars and credentials are sensitive.
- Working-directory permissions matter.

Start with least privilege. Avoid baking secrets into broad reusable
prompts unless that's deliberate.
