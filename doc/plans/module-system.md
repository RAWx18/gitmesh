> **Historical plan.** Superseded by `IMPLEMENTATION.md` for current
> GitMesh Agents context. Retained as the design reference for the module
> + template + store system.

# Module System - Design Reference

GitMesh Agents extends without forking via two distinct, complementary
artifacts:

| Artifact | Carries code? | Purpose |
|----------|---------------|---------|
| **Module** | yes | Adds routes, UI pages, tables, services, hook handlers |
| **Project Template** | no - JSON only | Bootstraps a new project's agents, goals, projects, issues |

Both are surfaced through the **Project Store** (browse / install / import).

A small glossary upfront:

- **Hook**: named event the core emits for modules to subscribe to.
- **Slot**: exclusive category (only one active module per slot, e.g. `observability`).
- **Project Store**: registry that indexes modules + templates.

---

## Section 1 - Module shape

### 1.1 Layout on disk

Modules live at the repo root under `modules/<id>/`. Each is a pnpm
workspace package:

```
modules/observability/
  gitmesh-agents.module.json     manifest (required)
  src/
    index.ts                     entry point - default export = register()
    routes.ts                    Express router
    hooks.ts                     hook handlers
    schema.ts                    Drizzle table definitions (prefixed mod_<id>_)
    migrations/                  drizzle-kit-generated SQL
    ui/
      index.ts                   page + widget exports (lazy-loaded by shell)
      TokenDashboard.tsx
```

### 1.2 Manifest fields (`gitmesh-agents.module.json`)

| Field | Required | Purpose |
|-------|----------|---------|
| `id` | yes | Unique id; doubles as npm package suffix (`@gitmesh/mod-<id>`) |
| `name`, `description`, `version`, `author` | yes | Catalogue metadata |
| `slot` | optional | Exclusive category. If set, only one active module may claim it. Omit for free-coexistence modules. |
| `hooks` | yes | Array of hook event names this module subscribes to. Declared upfront so core knows what to emit. |
| `routes.prefix` + `routes.entry` | optional | Mounted at `/api/modules/<prefix>`; module owns the namespace |
| `ui.pages[]` | optional | Sidebar entries; each is `{ path, label, entry }`. Lazy-loaded React components. |
| `ui.widgets[]` | optional | Slot injection into existing pages; each is `{ id, label, placement, entry }` |
| `schema` | optional | Path to Drizzle table definitions for module-owned tables |
| `configSchema` | optional | JSON Schema validating module config |
| `requires.core` | optional | semver range; e.g. `">=0.1.0"` |

A worked example for `observability`:

```json
{
  "id": "observability",
  "name": "Observability",
  "description": "Token tracking, cost metrics, and agent performance instrumentation",
  "version": "0.1.0",
  "author": "gitmesh-agents",
  "slot": "observability",
  "hooks": [
    "agent:heartbeat",
    "agent:created",
    "issue:status_changed",
    "budget:threshold_crossed"
  ],
  "routes": { "prefix": "/observability", "entry": "./src/routes.ts" },
  "ui": {
    "pages": [
      { "path": "/observability", "label": "Observability", "entry": "./src/ui/index.ts" }
    ],
    "widgets": [
      { "id": "token-burn-rate", "label": "Token Burn Rate", "placement": "dashboard", "entry": "./src/ui/index.ts" }
    ]
  },
  "schema": "./src/schema.ts",
  "configSchema": {
    "type": "object",
    "properties": {
      "retentionDays": { "type": "number", "default": 30 },
      "enablePrometheus": { "type": "boolean", "default": false },
      "prometheusPort": { "type": "number", "default": 9090 }
    }
  },
  "requires": { "core": ">=0.1.0" }
}
```

### 1.3 Entry point

`src/index.ts` exports a default `register(api: ModuleAPI)`. It is the
**only** runtime contact point between the module and the core:

```typescript
import type { ModuleAPI } from "@gitmesh/core";
import { createRouter } from "./routes.js";
import { onHeartbeat, onBudgetThreshold } from "./hooks.js";

export default function register(api: ModuleAPI) {
  api.registerRoutes(createRouter(api.db, api.config));
  api.on("agent:heartbeat", onHeartbeat);
  api.on("budget:threshold_crossed", onBudgetThreshold);

  api.registerService({
    name: "metrics-aggregator",
    interval: 60_000,
    async run(ctx) {
      await aggregateMetrics(ctx.db);
    },
  });
}
```

### 1.4 `ModuleAPI` surface

```typescript
interface ModuleAPI {
  moduleId: string;
  config: Record<string, unknown>;        // validated against configSchema
  db: Db;                                  // shared Drizzle client

  registerRoutes(router: Router): void;
  on(event: HookEvent, handler: HookHandler): void;
  registerService(service: ServiceDef): void;

  logger: Logger;                          // module-scoped
  core: {                                  // read-only helpers
    agents: AgentService;
    issues: IssueService;
    projects: ProjectService;
    goals: GoalService;
    activity: ActivityService;
  };
}
```

Modules get the shared DB, a scoped logger, and **read** access to core
services. They register routes and hook handlers; they do **not**
monkey-patch core.

---

## Section 2 - Hook system

### 2.1 Catalogue of core hooks

| Hook | Payload | Fired |
|------|---------|-------|
| `server:started` | `{ port }` | After Express begins listening |
| `agent:created` | `{ agent }` | After insert |
| `agent:updated` | `{ agent, changes }` | After update |
| `agent:deleted` | `{ agent }` | After delete |
| `agent:heartbeat` | `{ agentId, timestamp, meta }` | On check-in. `meta` carries `tokensUsed`, `costCents`, `model`, latency, &hellip; |
| `agent:status_changed` | `{ agent, from, to }` | On status transition |
| `issue:created` | `{ issue }` | After insert |
| `issue:status_changed` | `{ issue, from, to }` | On status change |
| `issue:assigned` | `{ issue, agent }` | On assignment |
| `goal:created` | `{ goal }` | After insert |
| `goal:completed` | `{ goal }` | When status flips to complete |
| `budget:spend_recorded` | `{ agentId, amount, total }` | After spend incremented |
| `budget:threshold_crossed` | `{ agentId, budget, spent, percent }` | When agent crosses 80% / 90% / 100% |

### 2.2 Execution rules (non-negotiable)

- **Post-commit only.** Hooks fire after the database write succeeds. Modules cannot veto core operations.
- **Fire-and-forget.** A failing handler never crashes or blocks the core.
- **Concurrent.** All handlers for an event run in parallel via `Promise.allSettled`.
- **Immutable payload.** Handlers receive a copy, not a mutable reference.

Implementation sketch:

```typescript
class HookBus {
  private handlers = new Map<string, HookHandler[]>();

  register(event: string, handler: HookHandler) {
    const list = this.handlers.get(event) ?? [];
    list.push(handler);
    this.handlers.set(event, list);
  }

  async emit(event: string, payload: unknown) {
    const handlers = this.handlers.get(event) ?? [];
    await Promise.allSettled(handlers.map((h) => h(payload)));
  }
}
```

If pre-commit validation is ever needed (e.g. veto a budget change),
that's a separate middleware mechanism - **not** the hook bus.

### 2.3 Worked example - the observability heartbeat handler

```typescript
// modules/observability/src/hooks.ts
import type { Db } from "@gitmesh/data";
import { tokenMetrics } from "./schema.js";

export function createHeartbeatHandler(db: Db) {
  return async (payload: {
    agentId: string;
    timestamp: Date;
    meta: { tokensUsed?: number; costCents?: number; model?: string };
  }) => {
    const { agentId, timestamp, meta } = payload;
    if (meta.tokensUsed != null) {
      await db.insert(tokenMetrics).values({
        agentId,
        tokensUsed: meta.tokensUsed,
        costCents: meta.costCents ?? 0,
        model: meta.model ?? "unknown",
        recordedAt: timestamp,
      });
    }
  };
}
```

Every heartbeat lands in `mod_observability_token_metrics`. The core
neither knows nor cares.

---

## Section 3 - Database & migrations

### 3.1 Namespacing

Module tables are prefixed `mod_<moduleId>_`. Example:

```typescript
import { pgTable, uuid, integer, text, timestamp, boolean } from "drizzle-orm/pg-core";

export const tokenMetrics = pgTable("mod_observability_token_metrics", {
  id: uuid("id").primaryKey().defaultRandom(),
  agentId: uuid("agent_id").notNull(),
  tokensUsed: integer("tokens_used").notNull(),
  costCents: integer("cost_cents").notNull().default(0),
  model: text("model").notNull(),
  recordedAt: timestamp("recorded_at", { withTimezone: true }).notNull().defaultNow(),
});

export const alertRules = pgTable("mod_observability_alert_rules", {
  id: uuid("id").primaryKey().defaultRandom(),
  agentId: uuid("agent_id"),
  metricName: text("metric_name").notNull(),
  threshold: integer("threshold").notNull(),
  enabled: boolean("enabled").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
```

### 3.2 Migration discipline

- Each module owns its `src/migrations/`.
- Core migrations run first, always.
- Module migrations run in dependency order.
- Each module's migrations are tracked in a `mod_migrations` table keyed by module id.
- `pnpm db:migrate` runs everything; `pnpm db:migrate --module observability` runs one.

### 3.3 Reference direction

Strictly one-way: module tables MAY foreign-key to core tables; core
tables NEVER reference module tables.

---

## Section 4 - Loading, configuration, and lifecycle

### 4.1 Boot sequence

On server startup:

1. Scan `modules/` for `gitmesh-agents.module.json` manifests.
2. Validate each manifest (JSON Schema check on `configSchema`, required fields).
3. Check for slot conflicts (error if two active modules claim the same slot).
4. Topological sort by declared dependencies.
5. For each module, in order:
   1. Validate config against `configSchema`.
   2. Run pending migrations.
   3. Import the entry point and call `register(api)`.
   4. Mount routes at `/api/modules/<prefix>`.
   5. Start background services.
6. Emit `server:started`.

### 4.2 Configuration

Module config lives in the server environment or `gitmesh-agents.config.json`:

```jsonc
{
  "modules": {
    "enabled": ["observability", "revenue", "notifications"],
    "config": {
      "observability": {
        "retentionDays": 90,
        "enablePrometheus": true
      },
      "revenue": {
        "stripeSecretKey": "$STRIPE_SECRET_KEY"
      }
    }
  }
}
```

`$ENV_VAR` references resolve at load time. Secrets never go directly in
the file.

### 4.3 Disabling

When a module is disabled (set `enabled` &rarr; false):

- Background services stop.
- Routes unmount (return 404).
- Hook handlers unsubscribe.
- Tables are **not** dropped - data survives. Re-enabling resumes where
  it left off.

---

## Section 5 - UI integration

### 5.1 Shell responsibilities

The core UI shell provides:

- a sidebar with slots for module-contributed nav items;
- a dashboard with widget mount points;
- a module settings page.

### 5.2 How the shell loads module UI

Modules declare pages and widgets in the manifest. The shell turns those
into lazy routes / widget mounts:

```typescript
// ui/src/modules/loader.ts
import { lazy } from "react";

// generated from manifests
export const modulePages = [
  {
    path: "/observability",
    label: "Observability",
    component: lazy(() => import("@gitmesh/mod-observability/ui")),
  },
];

export const dashboardWidgets = [
  {
    id: "token-burn-rate",
    label: "Token Burn Rate",
    placement: "dashboard",
    component: lazy(() =>
      import("@gitmesh/mod-observability/ui").then((m) => ({ default: m.TokenBurnRateWidget })),
    ),
  },
];
```

### 5.3 Module UI contract

The module's UI entry exports named components:

```typescript
// modules/observability/src/ui/index.ts
export { default } from "./ObservabilityPage";
export { TokenBurnRateWidget } from "./TokenBurnRateWidget";
```

Standard props:

```typescript
interface ModulePageProps {
  moduleId: string;
  config: Record<string, unknown>;
}

interface ModuleWidgetProps {
  moduleId: string;
  config: Record<string, unknown>;
  className?: string;
}
```

Module UI fetches data exclusively from its own
`/api/modules/<id>/&hellip;` namespace.

---

## Section 6 - Project Templates

### 6.1 Format

A project template is a single JSON file describing a full project
structure. Refs (string keys) are used internally; on import they map to
generated UUIDs.

```json
{
  "id": "startup-in-a-box",
  "name": "Startup in a Box",
  "description": "A 5-agent startup team with engineering, product, and ops",
  "version": "1.0.0",
  "author": "gitmesh-agents",
  "agents": [
    { "ref": "ceo", "name": "admin Agent", "role": "pm", "budgetCents": 100000, "metadata": { "responsibilities": "Strategy, fundraising, enabling" } },
    { "ref": "eng-lead", "name": "Engineering Lead", "role": "engineer", "reportsTo": "ceo", "budgetCents": 50000 },
    { "ref": "eng-1", "name": "Engineer", "role": "engineer", "reportsTo": "eng-lead", "budgetCents": 30000 },
    { "ref": "designer", "name": "Designer", "role": "designer", "reportsTo": "ceo", "budgetCents": 20000 },
    { "ref": "ops", "name": "Ops Agent", "role": "devops", "reportsTo": "ceo", "budgetCents": 20000 }
  ],
  "goals": [
    { "ref": "north-star", "title": "Launch MVP", "level": "project" },
    { "ref": "build-product", "title": "Build the product", "level": "team", "parentRef": "north-star", "ownerRef": "eng-lead" },
    { "ref": "design-brand", "title": "Establish brand identity", "level": "agent", "parentRef": "north-star", "ownerRef": "designer" }
  ],
  "projects": [
    { "ref": "mvp", "name": "MVP", "description": "The first shippable version" }
  ],
  "issues": [
    { "title": "Set up CI/CD pipeline", "status": "todo", "priority": "high", "projectRef": "mvp", "assigneeRef": "ops", "goalRef": "build-product" },
    { "title": "Design landing page", "status": "todo", "priority": "medium", "projectRef": "mvp", "assigneeRef": "designer", "goalRef": "design-brand" }
  ]
}
```

### 6.2 Import flow

1. Parse and validate the template JSON.
2. Check ref uniqueness; reject dangling references.
3. Insert agents (topological by `reportsTo`).
4. Insert goals (topological by `parentRef`).
5. Insert projects.
6. Insert issues, resolving `projectRef` / `assigneeRef` / `goalRef` to real ids.
7. Emit activity log events for every insertion.

### 6.3 Export

`GET /api/templates/export` &rarr; downloads the current project as a
template JSON. This makes projects shareable and clonable.

---

## Section 7 - Project Store

The Project Store is a registry for modules and templates. **V1** = a
curated GitHub repo with a JSON index. Later it could become a hosted
service.

### 7.1 Index format

```json
{
  "modules": [
    {
      "id": "observability",
      "name": "Observability",
      "description": "Token tracking, cost metrics, and agent performance",
      "repo": "github:gitmesh-agents/mod-observability",
      "version": "0.1.0",
      "tags": ["metrics", "monitoring", "tokens"]
    }
  ],
  "templates": [
    {
      "id": "startup-in-a-box",
      "name": "Startup in a Box",
      "description": "5-agent startup team",
      "url": "https://store.gitmesh-agents.ing/templates/startup-in-a-box.json",
      "tags": ["startup", "team"]
    }
  ]
}
```

### 7.2 CLI surface

```bash
pnpm gitmesh-agents store list                    # browse modules and templates
pnpm gitmesh-agents store install <module-id>     # install a module
pnpm gitmesh-agents store import <template-id>    # import a project template
pnpm gitmesh-agents store export                  # export current project as template
```

---

## Section 8 - Module roadmap (candidate set)

### Tier 1 - build first (core extensions)

| Module | Purpose | Key hooks |
|--------|---------|-----------|
| **Observability** | Token usage, cost metrics, agent performance dashboards, Prometheus export | `agent:heartbeat`, `budget:spend_recorded` |
| **Revenue Tracking** | Stripe / crypto wallets, income, P&L vs. agent costs | `budget:spend_recorded` |
| **Notifications** | Slack / Discord / email alerts on configurable triggers | All hooks (configurable) |

### Tier 2 - high value

| Module | Purpose | Key hooks |
|--------|---------|-----------|
| **Analytics Dashboard** | Burn-rate trends, agent utilisation, goal velocity | `agent:heartbeat`, `issue:status_changed`, `goal:completed` |
| **Workflow Automation** | If/then rules ("when issue done, create follow-up"; "when budget at 90%, pause agent") | `issue:status_changed`, `budget:threshold_crossed` |
| **Knowledge Base** | Shared doc store, vector search, agent read/write of org knowledge | `agent:heartbeat` (context injection) |

### Tier 3 - nice to have

| Module | Purpose | Key hooks |
|--------|---------|-----------|
| **Audit & Compliance** | Immutable audit trail, approval workflows, spend authorization | All write hooks |
| **Agent Logs / Replay** | Full execution traces, token-by-token replay | `agent:heartbeat` |
| **Multi-tenant** | Multiple separate projects/orgs in one instance | `server:started` |

---

## Section 9 - Implementation plan

### Phase 1 - core infrastructure

In `@gitmesh/server`:

1. `HookBus`: emitter with `register()` and `emit()`, `Promise.allSettled` semantics.
2. Module loader - scans `modules/`, validates manifests, calls `register(api)`.
3. Module API object - `registerRoutes()`, `on()`, `registerService()`, scoped logger, core read access.
4. Module config - `gitmesh-agents.config.json` with per-module config and env-var interpolation.
5. Module migration runner - extends `db:migrate` to discover and run module migrations.
6. Emit hooks from existing core CRUD operations.

In `@gitmesh/agents-ui`:

7. Module page loader - reads manifests, generates lazy routes.
8. Dashboard widget slots - render module-contributed widgets on the Dashboard page.
9. Sidebar extension - dynamically add module nav items.

New package:

10. `@gitmesh/module-sdk`: TypeScript types for `ModuleAPI`, `HookEvent`, `HookHandler`, manifest schema.

### Phase 2 - first module (observability)

11. Build `modules/observability` as the reference implementation.
12. Token metrics table + migration.
13. Heartbeat hook handler recording token usage.
14. Dashboard widget showing burn rate.
15. API routes for querying metrics.

### Phase 3 - templates

16. `POST /api/templates/import`.
17. `GET /api/templates/export`.
18. First template: "Startup in a Box".

### Phase 4 - Project Store

19. GitHub-based store index.
20. CLI commands for browse / install / import.
21. UI page for browsing the store.

---

## Section 10 - Design principles

The seven invariants that govern this whole system. All code reviews
against module-system changes go through this list.

1. **Modules extend, never patch.** New routes, tables, hooks - never modifying core.
2. **Hooks are post-commit, fire-and-forget.** Module failures must never break core operations.
3. **One-way dependency.** Modules depend on core; core never depends on modules. Module tables may FK to core tables, never the reverse.
4. **Declarative manifest, imperative registration.** Static metadata in JSON (validatable without running code); runtime behaviour registered via the API.
5. **Namespace isolation.** Module routes under `/api/modules/<id>/`; tables prefixed `mod_<id>_`; config scoped by id.
6. **Graceful degradation.** A module failing to load logs the error; the rest of the system keeps working.
7. **Data survives disable.** Disabling stops code, preserves data. Re-enabling resumes.
