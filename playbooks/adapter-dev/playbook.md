---
name: create-agent-adapter
description: >
  Reference playbook for adding a new agent adapter to GitMesh Agents. Triggered
  whenever an operator wires up a new AI coding tool (CLI, HTTP service, or
  custom process), modifies the adapter SDK, or audits an existing adapter for
  conformance. Concrete examples come from the shipped claude-local and
  codex-local adapters.
---

# Adapter Development Playbook

> An adapter is the seam between the GitMesh control-plane and a specific agent
> runtime. It must satisfy three independent registries (server, UI, CLI) from
> a single package.

## Quick map

| You want to... | Jump to |
|----------------|---------|
| Scaffold a new adapter package | [Scaffold](#scaffold) |
| Understand the SDK contracts | [Contracts](#contracts) |
| Wire up environment diagnostics | [Diagnostics](#diagnostics) |
| Manage long-running sessions | [Sessions](#sessions) |
| Inject GitMesh skills into the runtime | [Skills injection](#skills-injection) |
| Lock down secrets and untrusted output | [Hardening](#hardening) |
| Confirm you're done | [Conformance checklist](#conformance-checklist) |

---

## Scaffold

A finished adapter lives at `lib/adapters/<kebab-name>/` and exposes four entry
points from a single `package.json`. The directory layout is fixed:

- `src/index.ts`: pure metadata (`type`, `label`, `models`, `agentConfigurationDoc`). No Node, no React.
- `src/server/{index,execute,parse,test}.ts`: runtime adapter, environment test, output parser.
- `src/ui/{index,parse-stdout,build-config}.ts`: transcript parser and config builder for the operator UI.
- `src/cli/{index,format-event}.ts`: terminal event formatter for `gitmesh-agents run --watch`.

`package.json` must declare these exports verbatim:

- `"."` &rarr; `./src/index.ts`
- `"./server"` &rarr; `./src/server/index.ts`
- `"./ui"` &rarr; `./src/ui/index.ts`
- `"./cli"` &rarr; `./src/cli/index.ts`

The package name follows `@gitmesh/adapter-<kebab-name>`. The adapter
`type` is `snake_case` and globally unique inside `agents.adapter_type`.

Required runtime dependencies: `@gitmesh/adapter-sdk` (workspace) and `picocolors` for CLI coloring.

### Metadata file (`src/index.ts`)

Four named exports are mandatory:

- `type`: string key persisted on the agent row
- `label`: human-readable name shown in the UI
- `models`: array of `{ id, label }` shown in the agent creation form
- `agentConfigurationDoc`: markdown describing every `adapterConfig` field

Treat `agentConfigurationDoc` as routing logic, not marketing. Frame it around
"use when" and "don't use when" so an LLM configuring another agent can pick
the correct adapter from the description alone. One concrete anti-pattern
("Don't use when the agent doesn't need conversational context - the process
adapter is simpler") outperforms three paragraphs of prose.

---

## Contracts

All TypeScript shapes ship from `@gitmesh/adapter-sdk` (types) and
`@gitmesh/adapter-sdk/server-utils` (runtime helpers). The minimum surface an
adapter touches:

### Execution surface

`AdapterExecutionContext` (input):

- `runId`
- `agent`: `{ id, projectId, name, adapterType, adapterConfig }`
- `runtime`: `{ sessionId, sessionParams, sessionDisplayId, taskKey }`
- `config`: opaque `Record<string, unknown>` (the agent's `adapterConfig` blob)
- `context`: runtime details (`taskId`, `wakeReason`, `approvalId`, ...)
- `onLog(stream, chunk)`: async stdout/stderr sink
- `onMeta(meta)`: async invocation metadata sink (optional)
- `authToken`: optional bearer for outbound API calls

`AdapterExecutionResult` (output): `exitCode`, `signal`, `timedOut`, optional
`errorMessage`, `usage` (`{ inputTokens, outputTokens, cachedInputTokens? }`),
`sessionId` (legacy) or `sessionParams` (preferred), `sessionDisplayId`,
`provider`, `model`, `costUsd`, `resultJson`, `summary`, and `clearSession`
(set true to wipe a stale session).

### Module shapes

| Registry path | Interface | Required exports |
|---|---|---|
| `server/src/adapters/registry.ts` | `ServerAdapterModule` | `type`, `execute`, `testEnvironment`, `sessionCodec?`, `supportsLocalAgentJwt?`, `models?`, `agentConfigurationDoc?` |
| `ui/src/adapters/registry.ts` | `UIAdapterModule` | `type`, `label`, `parseStdoutLine`, `ConfigFields`, `buildAdapterConfig` |
| `cli/src/adapters/registry.ts` | `CLIAdapterModule` | `type`, `formatStdoutEvent` |

### `AdapterSessionCodec`

- `deserialize(raw)`: DB JSON &rarr; typed params or `null`
- `serialize(params)`: typed params &rarr; storable JSON or `null`
- `getDisplayId(params)`: human-readable session id (optional)

### Server-side helpers

Pulled from `@gitmesh/adapter-sdk/server-utils`:

- Type-safe extractors: `asString`, `asNumber`, `asBoolean`, `asStringArray`, `parseObject`, `parseJson`
- Templating: `renderTemplate(tmpl, data)`: `{{path.to.value}}` syntax
- Environment: `buildGitMesh AgentsEnv(agent)`, `redactEnvForLogs(env)`, `ensurePathInEnv(env)`
- Filesystem & process: `ensureAbsoluteDirectory(cwd)`, `ensureCommandResolvable(cmd, cwd, env)`, `runChildProcess(runId, cmd, args, opts)`

### Server env vars the runtime always injects

Every spawned agent process receives, on top of the operator-supplied env:

- `GITMESH_AGENT_ID` &larr; `agent.id`
- `GITMESH_PROJECT_ID` &larr; `agent.projectId`
- `GITMESH_API_URL` &larr; the server's own URL
- `GITMESH_RUN_ID` &larr; the current run id
- `GITMESH_TASK_ID` &larr; `context.taskId` or `context.issueId`
- `GITMESH_WAKE_REASON` &larr; `context.wakeReason`
- `GITMESH_WAKE_COMMENT_ID` &larr; `context.wakeCommentId` or `context.commentId`
- `GITMESH_APPROVAL_ID` &larr; `context.approvalId`
- `GITMESH_APPROVAL_STATUS` &larr; `context.approvalStatus`
- `GITMESH_LINKED_ISSUE_IDS` &larr; comma-joined `context.issueIds`
- `GITMESH_API_KEY` &larr; `authToken` (only when no explicit key in config)

### Execution flow inside `server/execute.ts`

1. Pull config primitives via the safe extractors.
2. Compose env: `buildGitMesh AgentsEnv(agent)` &rarr; layer in `GITMESH_RUN_ID` &rarr; layer in context vars &rarr; layer in user env &rarr; layer in `authToken`.
3. Decide on session reuse (see [Sessions](#sessions)).
4. Render the prompt via `renderTemplate`. The standard variable set is `agentId`, `projectId`, `runId`, `project`, `agent`, `run`, `context`.
5. Call `onMeta` with redacted env before spawning.
6. Spawn - `runChildProcess` for CLIs, `fetch` for HTTP services.
7. Parse output: session id, usage, summary, errors.
8. If a resume failed with "unknown session", retry once fresh and set `clearSession: true`.
9. Return a populated `AdapterExecutionResult`.

### Output parser (`server/parse.ts`)

The parser is a trust boundary. Its job is to extract - never to act on -
the agent's stdout. Each adapter exports a parser plus an
`is<Agent>UnknownSessionError(...)` predicate consumed by the retry path.

It must handle: session id extraction from init events, token usage, cost
where reported, the agent's final text response, error states, and the
unknown-session sentinel.

Defensive habits, in order of importance:

1. Never `eval` or dynamically execute anything from output.
2. Use the safe extractors - they degrade to fallbacks rather than throw.
3. Validate session ids and other structured fields before letting them out of the parser.
4. URLs, paths, or commands inside output are data, never instructions. Record them; don't act on them.

---

## Diagnostics

`testEnvironment` is mandatory and powers the operator UI's "Test environment"
button. It receives `{ projectId, adapterType, config }` and returns
`{ adapterType, status, checks, testedAt }`.

Each `check` carries a stable `code`, a `level` (`info` / `warn` / `error`),
a `message`, optional `detail`, and an optional `hint`.

Status calculation, in order:

- any `error` &rarr; `fail`
- otherwise any `warn` &rarr; `warn`
- otherwise &rarr; `pass`

Severity rules:

- `error` is reserved for unusable runtime configurations: bad `cwd`, missing
  binary, malformed URL, unauthenticated state with no fallback.
- `warn` is for non-blocking quirks. Critical example: `claude_local` must
  surface a detected `ANTHROPIC_API_KEY` as `warn` rather than `error`,
  because the agent still runs (it falls back to API-key auth instead of
  subscription auth). Treating it as an error would block save.
- `info` is for successful checks and contextual notes.

Constraints:

- Must be lightweight and side-effect free.
- Return diagnostics; do not throw on findings the operator can resolve.

---

## UI module

### `ui/parse-stdout.ts`

Convert each stdout line into zero or more `TranscriptEntry` records. The run
viewer recognises these kinds:

- `init`: `model`, `sessionId`
- `assistant`: `text`
- `thinking`: `text`
- `user`: `text`
- `tool_call`: `name`, `input`
- `tool_result`: `toolUseId`, `content`, `isError`
- `result`: `text`, `inputTokens`, `outputTokens`, `cachedTokens`, `costUsd`, `subtype`, `isError`, `errors`
- `system`: `text`
- `stderr`: `text`
- `stdout`: `text` (fallback)

Anything you cannot classify becomes `{ kind: "stdout", ts, text: line }`.

### `ui/build-config.ts`

Pure transformation: `CreateConfigValues` from the form &rarr; the
`adapterConfig` JSON blob persisted on the agent. Always emit `timeoutSec` and
`graceSec` defaults; copy through optional fields only when set.

### Config Fields component

Lives at `ui/src/adapters/<name>/config-fields.tsx` and implements
`AdapterConfigFieldsProps`. It must render in two modes:

- create mode - reads/writes via `values` / `set`
- edit mode - reads/writes via `config` / `eff` / `mark`

Use the shared primitives from `ui/src/components/agent-config-primitives`:
`Field`, `ToggleField`, `DraftInput`, `DraftNumberInput`, and `help` for the
standard hint text.

---

## CLI module

`cli/format-event.ts` exports `formatStdoutEvent(line, debug)`. It pretty-prints
for `gitmesh-agents run --watch` using `picocolors`:

- blue - system / init
- green - assistant text
- yellow - tool calls
- gray (debug only) - unrecognised lines

---

## Registration

After scaffolding, each adapter module must be added to all three registries.
Using `my_agent` / `@gitmesh/adapter-my-agent` as a template:

- `server/src/adapters/registry.ts`: import `execute`, `sessionCodec` from `@gitmesh/adapter-my-agent/server`, plus `agentConfigurationDoc`, `models` from `@gitmesh/adapter-my-agent`. Build a `ServerAdapterModule` and add it to the `adaptersByType` map. Set `supportsLocalAgentJwt: true` if the agent can call the GitMesh Agents API.
- `ui/src/adapters/my-agent/index.ts`: assemble a `UIAdapterModule { type, label, parseStdoutLine, ConfigFields, buildAdapterConfig }` from `@gitmesh/adapter-my-agent/ui` plus the local `MyAgentConfigFields`.
- `ui/src/adapters/registry.ts`: import the assembled module and add to the map.
- `cli/src/adapters/registry.ts`: import `printMyAgentStreamEvent` from `@gitmesh/adapter-my-agent/cli` and add a `CLIAdapterModule` to the map.

The `pnpm-workspace.yaml` glob already covers `lib/adapters/*`: no edit needed unless the new package lives outside that path.

---

## Sessions

Long runs are the default, not an optimisation. An agent processing an issue
may be woken many times (initial assignment, approval callbacks, manual
nudges, re-assignments). Every wake should resume the same conversation so
the agent retains its context, file reads, and prior decisions. Starting
fresh wastes tokens and risks contradictory output.

Mechanics:

- `sessionParams` is an opaque `Record<string, unknown>` persisted per task.
- `sessionCodec.serialize(params)`: from execution result &rarr; storable JSON.
- `sessionCodec.deserialize(raw)`: from DB &rarr; typed params for the next run.
- `sessionCodec.getDisplayId(params)`: human-readable session id for the UI.

Two non-negotiable rules:

- **cwd-aware resume.** If the stored session was created in a different
  `cwd` than the current config, do not resume. Cross-project session
  contamination is worse than re-priming.
- **Unknown-session retry.** If a resume fails with the agent's
  "session not found" sentinel, retry once with a fresh session and return
  `clearSession: true` so GitMesh wipes the stale params.

If the runtime offers context compaction (Claude Code's automatic
management, Codex's `previous_response_id` chaining, etc.), let it run.
Adapters that support resume get compaction for free.

Reference pattern, used by both `claude-local` and `codex-local`:

- compute `canResumeSession` as `runtimeSessionId.length > 0 && (runtimeSessionCwd.length === 0 || path.resolve(runtimeSessionCwd) === path.resolve(cwd))`
- choose `sessionId = canResumeSession ? runtimeSessionId : null`
- run the attempt
- on non-zero exit with `isUnknownSessionError(output)`, run again with `null` and pass `clearSessionOnMissingSession: true` into your `toResult` helper

---

## Skills injection

GitMesh ships shared playbooks at the repo root (`playbooks/`). Agents need
them at runtime - for example the `gitmesh-agents` API skill or the
`gitmesh-enable-agent` workflow skill. Each adapter is responsible for making
those discoverable inside its runtime **without writing into the operator's
project checkout**.

The cwd is the user's repo. Writing `.claude/playbooks/` (or anything else)
into it would dirty git status, leak GitMesh internals into commits, and
contaminate the project. Choose an injection strategy based on what the
runtime supports:

| Strategy | When to use | Side effects |
|----------|-------------|--------------|
| Tmpdir + flag (claude-local) | Runtime supports an "additional dir" CLI flag | None - tmpdir is removed in `finally` |
| Global config dir (codex-local) | Runtime has its own config dir separate from the project | Writes to runtime's config dir; skip existing entries |
| Env var path | Runtime reads a skills/plugins path from env | Reads the repo's `playbooks/` directly |
| Prompt inlining | Runtime has no plugin system at all | Token cost, but zero filesystem effect |

`claude-local` flow (preferred):

1. `mkdtemp` &rarr; `gitmesh-agents-skills-*`.
2. `mkdir -p <tmp>/.claude/skills`.
3. For every entry in the repo's `playbooks/`, `symlink` it into the tmp tree.
4. Pass `--add-dir <tmp>` to Claude Code.
5. `fs.rm` the tmpdir in a `finally`.

`codex-local` flow (acceptable):

1. Resolve `$CODEX_HOME/skills` (default `~/.codex/skills`).
2. `mkdir -p` it.
3. For each repo skill, only symlink if the target does not already exist
   never overwrite operator customisations.

Skills are loaded procedures, not prompt bloat. The agent sees only each
playbook's frontmatter (`name` + `description`) until it decides to invoke
one; only then is the full body loaded. Do not inline skill content into
`agentConfigurationDoc` or prompt templates - let runtime discovery do
the work.

For mandatory procedures (e.g. an agent that must report status via the
`gitmesh-agents` skill), use explicit prompt instructions like "use the
gitmesh-agents skill to report progress." Fuzzy routing (model picks based
on description) is acceptable for exploratory tasks but unreliable for
required steps.

---

## Hardening

Adapters sit on the boundary between orchestration and arbitrary agent
execution - treat them as security surface.

- **Untrusted output.** The agent process executes LLM-driven code that
  reads external files and fetches URLs. Its output may carry prompt
  injection. The parse layer validates everything and executes nothing.
- **Secrets via environment, not prompts.** `GITMESH_API_KEY` and
  user-provided `config.env` values flow as process environment, never
  through the prompt template. Any redaction in `onMeta` logs goes through
  `redactEnvForLogs(env)`, which masks any key matching
  `/(key|token|secret|password|authorization|cookie)/i`.
- **Network policy.** Prefer minimal allowlists (e.g. GitMesh API + the
  forge) over open egress. Skills that teach HTTP requests + open egress =
  exfiltration path. Constrain at least one side. If the runtime supports
  layered policies, wire org-level defaults into the adapter and let
  per-agent config narrow further - never widen.
- **Process isolation.** CLI adapters inherit the server user's
  permissions; `cwd` and `env` define what the agent can touch. Flags like
  `dangerouslySkipPermissions` exist for development; the
  `agentConfigurationDoc` must mark them as dangerous and they should not
  run in production.
- **Always enforce timeouts.** `timeoutSec` and `graceSec` are safety
  rails. A runaway process without them consumes unbounded resources.

---

## Conventions

| Topic | Rule |
|-------|------|
| Adapter type | snake_case, globally unique |
| Package name | `@gitmesh/adapter-<kebab>` |
| Package directory | `lib/adapters/<kebab>/` |
| Config parsing | always go through `asString` / `asNumber` / `asBoolean`: never use `config[k]` raw |
| Defaults | every optional field gets a sensible default, documented in `agentConfigurationDoc` |
| Prompt template | always supported; default `"You are agent {{agent.id}} ({{agent.name}}). Continue your GitMesh Agents work."` |
| Errors | distinguish timeout vs process error vs parse failure; always set `errorMessage`; include raw stdout/stderr in `resultJson` on parse failure; handle "command not found" |
| Logging | `onLog("stdout", ...)` and `onLog("stderr", ...)` for every byte of process output; `onMeta(...)` once before spawn (with redacted env) |

---

## Tests

Co-locate tests under `server/src/__tests__/<adapter-name>-adapter.test.ts`.
Cover, at minimum:

- output parsing - feed sample stdout, assert structured output
- unknown-session detection - the predicate returns true on the agent's sentinel string
- config building - `buildConfig(formValues)` produces the right blob
- session codec - serialize/deserialize round-trips

---

## Conformance checklist

Use this as the gate before opening a PR. Every box must be ticked.

- [ ] `lib/adapters/<name>/package.json` declares `.`, `./server`, `./ui`, `./cli`
- [ ] `src/index.ts` exports `type`, `label`, `models`, `agentConfigurationDoc`
- [ ] `src/server/execute.ts` consumes `AdapterExecutionContext` and returns `AdapterExecutionResult`
- [ ] `src/server/test.ts` consumes `AdapterEnvironmentTestContext` and returns `AdapterEnvironmentTestResult`
- [ ] `src/server/parse.ts` exports the output parser plus `is<Agent>UnknownSessionError`
- [ ] `src/server/index.ts` exports `execute`, `testEnvironment`, `sessionCodec`, parse helpers
- [ ] `src/ui/parse-stdout.ts` exports a stdout-line parser
- [ ] `src/ui/build-config.ts` exports a `CreateConfigValues -> adapterConfig` builder
- [ ] `ui/src/adapters/<name>/config-fields.tsx` renders the create + edit form
- [ ] `ui/src/adapters/<name>/index.ts` assembles the `UIAdapterModule`
- [ ] `src/cli/format-event.ts` exports the terminal formatter
- [ ] `src/cli/index.ts` re-exports it
- [ ] Module added to `server/src/adapters/registry.ts`
- [ ] Module added to `ui/src/adapters/registry.ts`
- [ ] Module added to `cli/src/adapters/registry.ts`
- [ ] Workspace covers the new package (default `lib/adapters/*` glob is enough)
- [ ] Tests cover parsing, session codec, and config building
