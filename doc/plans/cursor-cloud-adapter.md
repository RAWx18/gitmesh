> **Historical plan.** Superseded by `IMPLEMENTATION.md` for current
> GitMesh Agents context. Retained as the V1 design reference for the
> Cursor Cloud adapter.

# Cursor Cloud Adapter - V1 Design

## Why this adapter is different

Unlike `claude_local` and `codex_local`, this adapter is **not** a local
subprocess. It is a remote orchestration adapter: launch and follow-up
go over HTTP, status arrives via webhook with polling fallback, and the
adapter synthesises stdout events so the rest of GitMesh's UI / CLI
sees a familiar event stream.

References (all upstream Cursor docs):

- <https://docs.cursor.com/background-agent/api/overview>
- <https://docs.cursor.com/background-agent/api>
- <https://docs.cursor.com/background-agent/api/webhooks>

## Five V1 decisions, up front

1. Cursor API auth = `Authorization: Bearer <CURSOR_API_KEY>`.
2. The callback URL must be publicly reachable from Cursor VMs - Tailscale URL locally; public server URL in prod.
3. Agent &rarr; GitMesh callback auth uses a **bootstrap exchange flow**. No long-lived GitMesh key in the prompt.
4. Webhooks are V1 primary. Polling is the fallback.
5. Skills are fetched on demand from GitMesh endpoints. The full playbook is **not** inlined into the prompt.

---

## 1. Cursor API surface (current)

Base URL: `https://api.cursor.com`. Auth header on every request:
`Authorization: Bearer <CURSOR_API_KEY>`.

Core endpoints used by the adapter:

| Endpoint | Method | Purpose |
|---|---|---|
| `/v0/agents` | POST | Launch agent |
| `/v0/agents/{id}` | GET | Agent status |
| `/v0/agents/{id}/conversation` | GET | Conversation history |
| `/v0/agents/{id}/followup` | POST | Follow-up prompt |
| `/v0/agents/{id}/stop` | POST | Stop / pause running agent |
| `/v0/models` | GET | Recommended model list |
| `/v0/me` | GET | API key metadata |
| `/v0/repositories` | GET | Accessible repos - **strictly rate-limited** |

### Status mapping (adapter policy)

- `CREATING`, `RUNNING`: non-terminal
- `FINISHED`: success terminal
- `ERROR`: failure terminal
- Unknown non-active - treat as failure terminal; preserve raw status in `resultJson`

### Webhook facts

- Event type used by V1: `statusChange`.
- Terminal webhook statuses include `ERROR` and `FINISHED`.
- Signatures: HMAC SHA256 in `X-Webhook-Signature: sha256=&hellip;`.

### Operational limits

- `/v0/repositories`: 1 req/user/min, 30 req/user/hour.
- MCP is not supported in Cursor background agents.

---

## 2. Package layout

```
lib/adapters/cursor-cloud/
├── package.json
├── tsconfig.json
└── src/
    ├── index.ts
    ├── api.ts
    ├── server/
    │   ├── index.ts
    │   ├── execute.ts
    │   ├── parse.ts
    │   ├── test.ts
    │   └── webhook.ts
    ├── ui/
    │   ├── index.ts
    │   ├── parse-stdout.ts
    │   └── build-config.ts
    └── cli/
        ├── index.ts
        └── format-event.ts
```

`package.json` uses the standard four exports (`.`, `./server`, `./ui`,
`./cli`).

---

## 3. API client (`src/api.ts`)

Typed wrapper. Required behaviours:

- Send `Authorization: Bearer &hellip;` on every request.
- Throw a typed `CursorApiError` carrying `status`, parsed body, and request context.
- Preserve unknown response fields in error metadata for debugging.

Core types:

```ts
interface CursorClientConfig {
  apiKey: string;
  baseUrl?: string; // default https://api.cursor.com
}

interface CursorAgent {
  id: string;
  name: string;
  status: "CREATING" | "RUNNING" | "FINISHED" | "ERROR" | string;
  source: { repository: string; ref: string };
  target: {
    branchName?: string;
    prUrl?: string;
    url?: string;
    autoCreatePr?: boolean;
    openAsCursorGithubApp?: boolean;
    skipReviewerRequest?: boolean;
  };
  summary?: string;
  createdAt: string;
}
```

---

## 4. Adapter config contract (`src/index.ts`)

Adapter identity: `type = "cursor_cloud"`, `label = "Cursor Cloud Agent"`.

V1 config fields:

| Field | Required? | Default | Notes |
|-------|-----------|---------|-------|
| `repository` | yes | - | GitHub repo URL |
| `ref` | optional | `main` | |
| `model` | optional | empty | Empty = auto |
| `autoCreatePr` | optional | `false` | |
| `branchName` | optional | - | |
| `promptTemplate` | yes | - | |
| `pollIntervalSec` | optional | `10` | |
| `timeoutSec` | optional | `0` | |
| `graceSec` | optional | `20` | |
| `gitmesh-agentsPublicUrl` | optional | falls back to `GITMESH_PUBLIC_URL` env | |
| `enableWebhooks` | optional | `true` | |
| `env.CURSOR_API_KEY` | yes | - | secret_ref preferred |
| `env.CURSOR_WEBHOOK_SECRET` | yes when webhooks on | - | min length 32 |

> Important: do **not** stash the Cursor key in a top-level `apiKey` field.
> Use `adapterConfig.env` so the existing secret-reference resolution flow
> applies.

---

## 5. Auth & callback flow

Cursor agents run remotely, so we cannot inject local env like
`GITMESH_API_KEY`. The adapter has to give the remote agent a way to
call us back.

### Public URL resolution

The adapter resolves a callback base URL in this order:

1. `adapterConfig.gitmesh-agentsPublicUrl`
2. `process.env.GITMESH_PUBLIC_URL`

If neither is set, `testEnvironment` and runtime execution must fail
with a clear error.

### Bootstrap exchange

The goal is to keep long-lived GitMesh credentials out of prompt text.

1. Before launch / follow-up, GitMesh mints a one-time bootstrap token bound to `agentId`, `projectId`, `runId`, with a short TTL (e.g. 10 minutes).
2. The adapter includes only `gitmesh-agentsPublicUrl`, the exchange endpoint path, and the bootstrap token in the prompt.
3. The Cursor agent calls `POST /api/agent-auth/exchange`.
4. GitMesh validates the bootstrap token and returns a run-scoped bearer JWT.
5. The Cursor agent uses that JWT for all GitMesh API calls.

This keeps long-lived keys out of prompts and supports clean revocation
via TTL.

---

## 6. Skills delivery

Don't inline `playbook.md` content. Instead:

1. The prompt includes a compact instruction to fetch skills from GitMesh.
2. After auth exchange, the agent fetches:
   - `GET /api/playbooks/index`
   - `GET /api/playbooks/gitmesh-agents`
   - `GET /api/playbooks/gitmesh-agents-create-agent` when needed
3. The agent loads full skill content on demand.

This avoids prompt bloat, keeps skill docs centrally updatable, and
lines up with how local adapters expose skills as discoverable
procedures.

---

## 7. Execution flow (`src/server/execute.ts`)

Six steps in order:

### 7.1 Resolve config + secrets

- Parse via `asString` / `asBoolean` / `asNumber` / `parseObject`.
- Resolve `env.CURSOR_API_KEY`.
- Resolve `gitmesh-agentsPublicUrl`.
- Validate webhook secret when webhooks are enabled.

### 7.2 Session resolution

Session identity = Cursor `agentId`, persisted in `sessionParams`.
Reuse only when the **repository matches** the previous session.

### 7.3 Render prompt

Render the template normally, then append a compact callback block:

- public GitMesh URL
- bootstrap exchange endpoint
- bootstrap token
- skill index endpoint
- required run-header behaviour

### 7.4 Launch / follow-up

- On resume: `POST /v0/agents/{id}/followup`.
- Otherwise: `POST /v0/agents`.
- When webhooks are enabled, include a webhook block:
  - `url: <gitmesh-agentsPublicUrl>/api/adapters/cursor-cloud/webhooks`
  - `secret: CURSOR_WEBHOOK_SECRET`

### 7.5 Progress + completion

Hybrid strategy:

- Webhook events are the primary status signal.
- Polling is the fallback and the source for transcript content (`/conversation`).

Synthesise stdout events for the rest of GitMesh: `init`, `status`,
`assistant`, `user`, `result`.

Completion logic:

- success &rarr; `status === FINISHED`
- failure &rarr; `status === ERROR` or unknown terminal
- timeout &rarr; stop the agent, mark `timedOut`

### 7.6 Result mapping

Populate `AdapterExecutionResult`:

- `exitCode`: `0` on success, `1` on terminal failure
- `errorMessage`: populated on failure / timeout
- `sessionParams`: `{ agentId, repository }`
- `provider`: `"cursor"`
- `usage`, `costUsd`: `null` (Cursor doesn't expose them)
- `resultJson`: include raw `status`, `target`, conversation snapshot

Always emit a `result` event to stdout before returning.

---

## 8. Webhook handling (`src/server/webhook.ts` + server route)

Add a server endpoint to receive Cursor webhook deliveries.
Responsibilities:

1. Verify the HMAC signature in `X-Webhook-Signature`.
2. Deduplicate by `X-Webhook-ID`.
3. Validate event type (`statusChange`).
4. Route by Cursor `agentId` to the active GitMesh run context.
5. Append `heartbeat_run_events` entries for audit / debug.
6. Update an in-memory run signal so the execute loop can short-circuit quickly.

Security:

- Reject invalid signature with `401`.
- Reject malformed payload with `400`.
- Always return promptly after persistence (`2xx`).

---

## 9. Environment test (`src/server/test.ts`)

Checks:

1. `CURSOR_API_KEY` is present.
2. Key validity via `GET /v0/me`.
3. Repository configured and URL shape valid.
4. Model exists (when set) via `/v0/models`.
5. `gitmesh-agentsPublicUrl` is present and shape-valid.
6. Webhook secret present and length-valid when webhooks are enabled.

Repository-access verification via `/v0/repositories` should be optional
because of the strict rate limits - only when an explicit
`verifyRepositoryAccess` option is set, and only as a `warn`-level check.

---

## 10. UI + CLI

### UI parser (`src/ui/parse-stdout.ts`)

Handle event types: `init`, `status`, `assistant`, `user`, `result`,
fallback to `stdout`. On failure results, set `isError=true` and include
the error text.

### Config builder (`src/ui/build-config.ts`)

- Map `CreateConfigValues.url` &rarr; `repository`.
- Preserve env-binding shape (`plain` / `secret_ref`).
- Apply defaults: `pollIntervalSec`, `timeoutSec`, `graceSec`, `enableWebhooks`.

### Adapter fields (`ui/src/adapters/cursor-cloud/config-fields.tsx`)

Controls for: `repository`, `ref`, `model`, `autoCreatePr`,
`branchName`, poll interval, `timeoutSec` / `graceSec`, GitMesh public
URL override, `enableWebhooks`, env bindings for `CURSOR_API_KEY` and
`CURSOR_WEBHOOK_SECRET`.

### CLI formatter (`src/cli/format-event.ts`)

Format synthetic events similarly to local adapters; highlight terminal
failures clearly.

---

## 11. Cross-layer registration

Adapter package registration:

- `server/src/adapters/registry.ts`
- `ui/src/adapters/registry.ts`
- `cli/src/adapters/registry.ts`

Shared contract updates (required - without them, create / edit flows
will reject the new adapter even with the package code in place):

- Add `cursor_cloud` to `lib/core/src/constants.ts` (`AGENT_ADAPTER_TYPES`).
- Ensure validators accept it in `lib/core/src/validators/agent.ts`.
- Update UI labels / maps wherever adapter names are enumerated:
  - `ui/src/components/agent-config-primitives.tsx`
  - `ui/src/components/AgentProperties.tsx`
  - `ui/src/pages/Agents.tsx`
- Consider onboarding wizard support for adapter selection in `ui/src/components/OnboardingWizard.tsx`.

---

## 12. Cancellation

Long-polling HTTP adapters need run cancellation. V1 requirement:

- Register a cancellation handler per running adapter invocation.
- `cancelRun` invokes that handler - abort fetch / poll loop, plus an optional Cursor stop call.

The current process-only cancellation maps are not enough by themselves
for Cursor.

---

## 13. Local vs. cloud comparison

| Aspect | `claude_local` | `cursor_cloud` |
|---|---|---|
| Execution model | local subprocess | remote API |
| Updates | stream-json stdout | webhook + polling + synthesised stdout |
| Session id | Claude session id | Cursor agent id |
| Skill delivery | local skill dir injection | authenticated fetch from GitMesh playbook endpoints |
| GitMesh auth | injected local run JWT env | bootstrap token exchange &rarr; run JWT |
| Cancellation | OS signals | abort polling + Cursor stop endpoint |
| Usage / cost | rich | unavailable |

---

## 14. V1 limitations

- No token / cost usage in API responses.
- Conversation stream is text-only (`user_message` / `assistant_message`).
- No MCP / tool-call granularity.
- Webhooks deliver status-change events only, not full transcript deltas.

---

## 15. Future enhancements

- Reduce polling frequency further once webhook reliability proves out.
- Attach image payloads from GitMesh context.
- Surface richer PR metadata in the GitMesh UI.
- Add a webhook replay UI for debugging.

---

## 16. Implementation checklist

### Adapter package

- [ ] `lib/adapters/cursor-cloud/package.json`: exports wired
- [ ] `lib/adapters/cursor-cloud/tsconfig.json`
- [ ] `src/index.ts`: metadata + configuration doc
- [ ] `src/api.ts`: bearer-auth client + typed errors
- [ ] `src/server/execute.ts`: hybrid webhook / poll orchestration
- [ ] `src/server/parse.ts`: stream parser + not-found detection
- [ ] `src/server/test.ts`: env diagnostics
- [ ] `src/server/webhook.ts`: signature verification + payload helpers
- [ ] `src/server/index.ts`: exports + session codec
- [ ] `src/ui/parse-stdout.ts`
- [ ] `src/ui/build-config.ts`
- [ ] `src/ui/index.ts`
- [ ] `src/cli/format-event.ts`
- [ ] `src/cli/index.ts`

### App integration

- [ ] Register adapter in server / UI / CLI registries.
- [ ] Add `cursor_cloud` to shared adapter constants and validators.
- [ ] Add adapter labels in UI surfaces.
- [ ] Add Cursor webhook route on server (`/api/adapters/cursor-cloud/webhooks`).
- [ ] Add auth exchange route (`/api/agent-auth/exchange`).
- [ ] Add skill serving routes (`/api/playbooks/index`, `/api/playbooks/:name`).
- [ ] Add a generic cancellation hook for non-subprocess adapters.

### Tests

- [ ] API client auth + error mapping
- [ ] Terminal status mapping (`FINISHED`, `ERROR`, unknown terminal)
- [ ] Session codec round-trip
- [ ] Config builder env-binding handling
- [ ] Webhook signature verification + dedupe
- [ ] Bootstrap exchange happy path + expired / invalid token

### Verification

- [ ] `pnpm -r typecheck`
- [ ] `pnpm test:run`
- [ ] `pnpm build`
