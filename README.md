<div align="center">

<picture>
   <source srcset="public/light_logo.png" media="(prefers-color-scheme: dark)">
   <img src="public/dark_logo.png" alt="GitMesh Logo" width="250">
</picture>

# GitMesh Community Edition

[![OpenSource License](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge)](LICENSE)
[![Contributors](https://img.shields.io/github/contributors/LF-Decentralized-Trust-labs/gitmesh.svg?style=for-the-badge&logo=git)](https://github.com/LF-Decentralized-Trust-labs/gitmesh/graphs/contributors)
[![OpenSSF Best Practices](https://img.shields.io/badge/OpenSSF-Silver%20Best%20Practices-silver.svg?style=for-the-badge&logo=opensourceinitiative)](https://www.bestpractices.dev/projects/10972)
<img src="public/mossp.png" alt="Mintlify Open Source Program" width="180" style="border-radius: 12px;" />

[![Join Weekly Dev Call](https://img.shields.io/badge/Join_Weekly_Dev_Call-000000?style=flat&logo=zoom&logoColor=white)](https://zoom-lfx.platform.linuxfoundation.org/meeting/96608771523?password=211b9c60-b73a-4545-8913-75ef933f9365)

</div>

---

## What is GitMesh?

**GitMesh Community Edition** is an open-source multi-agent orchestration runtime and governed MCP server purpose-built for open source projects. It enables AI agent teams — Triage, PR Review, Docs, Security, Community, Onboarding, and Release — to handle maintainer work autonomously, with every connected tool (Claude Code, Copilot, Cursor, Codex, Gemini CLI, and more) governed by a single maintainer-defined Policy-as-Code layer via OPA.

GitMesh combines an orchestration engine (atomic task checkout, persistent agent context, heartbeat scheduling, budget enforcement) with native GitHub/GitLab integration, and distributes governance over MCP and ACP so any compatible AI coding tool is covered. Adoption requires one YAML file and one CI step.

### Core Capabilities

- **Multi-Agent Orchestration** — Pre-defined OSS agent roles (Triage, PR Review, Docs, Security, Community, Onboarding, Release) with configurable heartbeat schedules, token budgets, and permission scopes
- **Policy-as-Code via OPA** — Maintainers define governance rules in simple YAML that auto-compiles to Rego. No agent merges a PR, modifies CI/CD files, or publishes a security advisory without human approval
- **GitHub/GitLab Native Sync** — Bidirectional issue and PR synchronization via webhooks. Agent actions (label, comment, review) push directly to the forge
- **MCP Server** — Any MCP-compatible IDE (VS Code, Cursor, JetBrains) connects once and every AI tool is automatically governed by the project's policy
- **ACP Orchestrator** — JSON-RPC 2.0 agent-to-agent coordination. Multiple agents work simultaneously without conflicts, double work, or runaway costs
- **Immutable Audit Log** — Every action logged with actor, policy version, and outcome (allowed/blocked). Filterable and exportable as JSON/CSV
- **Project Templates** — Pre-configured agent teams for CLI tools, JS libraries, DevOps projects, CNCF sandboxes, and solo maintainers

### Three-View Dashboard

| View | Purpose |
|------|---------|
| **Active Agents** | Agent status, budget consumption, current work. Pause, terminate, or reconfigure |
| **Pending Approvals** | Mobile-first approval queue — merge PRs, CVE disclosures, issue closures |
| **Audit Log** | Chronological action history with policy outcome filtering |

---

## Installation

### Prerequisites

- **Node.js 20+**
- **pnpm 9+** (the setup script can install it via Corepack if missing)
- **Docker** — optional; only required if you use Docker for PostgreSQL instead of the embedded database

### One-command setup (macOS / Linux / Windows)

From the repo root:

| Platform | Command |
| -------- | ------- |
| macOS / Linux | `./setup.sh` |
| Windows (PowerShell) | `./setup.ps1` |
| Windows (cmd) | `setup.cmd` |

These wrappers run `scripts/setup.mjs`, which checks Node, ensures pnpm, copies `.env.example` → `.env` when missing, installs dependencies, and builds the workspace.

Useful flags (all platforms):

```bash
node scripts/setup.mjs --start          # install + build + pnpm dev
node scripts/setup.mjs --with-docker-db # also start Docker Compose Postgres on localhost:5433
```

### Manual setup

```bash
git clone https://github.com/LF-Decentralized-Trust-labs/gitmesh.git
cd gitmesh
pnpm install --no-frozen-lockfile   # first clone; CI uses frozen lockfile
pnpm dev                            # API + UI — see below
```

### Database (embedded vs external)

GitMesh uses **PostgreSQL** (via Drizzle). For local development you have two common paths:

**1. Embedded PostgreSQL (default, no extra install)**

- **Do not set** `DATABASE_URL` (leave it unset, or keep it commented out in `.env`).
- The dev server starts an **embedded** PostgreSQL instance and stores data under  
  `~/.gitmesh-agents/instances/default/db/` (overridable with `GITMESH_HOME` / `GITMESH_INSTANCE_ID`).
- This works for **most** developers on a normal machine with disk space and a writable home directory.
- It is **not universal**: unusual environments (strict permissions, missing native binaries for your OS/arch, incomplete installs) may fail. In those cases use path **2**.

**2. External PostgreSQL (`DATABASE_URL`)**

- Set `DATABASE_URL` to a real server (local Docker, cloud, etc.).
- Apply migrations when needed:  
  `DATABASE_URL='postgres://...' pnpm db:migrate`  
  (same connection string the app uses).
- If you copy `.env.example` to `.env` and **uncomment** a URL such as  
  `postgres://gitmesh:gitmesh@localhost:5433/gitmesh`, you must **run Postgres on that host and port** first (for example `pnpm db:up`, or `node scripts/setup.mjs --with-docker-db`). Otherwise the app will fail to connect (for example `ECONNREFUSED` on port 5433).

Authoritative detail: **`doc/DEVELOPING.md`**, **`doc/DATABASE.md`**.

### Start the platform

```bash
pnpm dev
```

In development, the **API and the maintainer UI share one origin**:

- **http://localhost:3100** — REST API (`/api/...`) and UI

For a single run without file watching:

```bash
pnpm dev:once
```

Optional: `pnpm gitmesh-agents run` — onboarding, `doctor --repair`, and start when checks pass.

### Docker images

- **`Dockerfile`** — production-style image; persistent state under `GITMESH_HOME` (volume `/gitmesh-agents`), embedded PostgreSQL by default in typical deployments. See **`doc/DOCKER.md`**.
- **`Dockerfile.e2e`** — installs/runs `gitmesh-agents` from npm for E2E-style bootstrap inside a container.

### Configuration

See **`.env.example`** for a full template. Highlights:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | When set, uses that PostgreSQL server; when unset, embedded PostgreSQL is used (see [Database (embedded vs external)](#database-embedded-vs-external) above). |
| `PORT` | HTTP port (often `3100`). |

Deployment mode, auth, and GitHub integration are documented in **`.env.example`** and **`doc/DEVELOPING.md`**.

---

## Adoption Path

| Stage | What Happens | Time |
|-------|-------------|------|
| **1. Zero-config entry** | Add `gitmesh/agent-gate` to CI — contributions are policy-checked immediately | 5 min |
| **2. First agent** | Add `.gitmesh/agents.yaml`, enable Triage Agent, approve onboarding | 15 min |
| **3. Connect tools** | Each developer adds GitMesh MCP server URL to their IDE config once | 2 min/dev |
| **4. Expand the team** | Enable PR Review, Docs, Security agents as the project grows | On demand |
| **5. Publish a template** | Share your agent configuration for other projects to adopt | Optional |

---

## Contributing

[![LFX Active Contributors](https://insights.linuxfoundation.org/api/badge/active-contributors?project=lf-decentralized-trust-labs&repos=https://github.com/LF-Decentralized-Trust-labs/gitmesh)](https://insights.linuxfoundation.org/project/lf-decentralized-trust-labs/repository/lf-decentralized-trust-labs-gitmesh)
[![GitMesh CE Governance](https://img.shields.io/github/actions/workflow/status/LF-Decentralized-Trust-labs/gitmesh/gov-sync.yml?label=GitMesh%20CE%20Governance)](https://github.com/LF-Decentralized-Trust-labs/gitmesh/actions/workflows/gov-sync.yml)

1. Fork the repository
2. Create a branch: `git checkout -b type/branch-name`
3. Commit with sign-off (DCO is enforced): `git commit -s -m "feat: add ..."`
4. Push the branch: `git push origin type/branch-name`
5. Open a pull request

See the [Contributing Guide](CONTRIBUTING.md) for the full workflow.

---

## Maintainers

<table width="100%">
  <tr align="center">
    <td valign="top" width="33%">
      <a href="https://github.com/parvm1102" target="_blank">
        <img src="https://avatars.githubusercontent.com/parvm1102?s=150" width="120" alt="parvm1102"/><br/>
        <strong>parvm1102</strong>
      </a>
      <p>
        <a href="https://github.com/parvm1102" target="_blank">
          <img src="https://img.shields.io/badge/GitHub-100000?style=flat&logo=github&logoColor=white" alt="GitHub"/>
        </a>
        <a href="https://linkedin.com/in/mittal-parv" target="_blank">
          <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white" alt="LinkedIn"/>
        </a>
        <a href="mailto:mittal@gitmesh.dev">
          <img src="https://img.shields.io/badge/Email-D14836?style=flat&logo=gmail&logoColor=white" alt="Email"/>
        </a>
      </p>
    </td>
    <td valign="top" width="33%">
      <a href="https://github.com/Ronit-Raj9" target="_blank">
        <img src="https://avatars.githubusercontent.com/Ronit-Raj9?s=150" width="120" alt="Ronit-Raj9"/><br/>
        <strong>Ronit-Raj9</strong>
      </a>
      <p>
        <a href="https://github.com/Ronit-Raj9" target="_blank">
          <img src="https://img.shields.io/badge/GitHub-100000?style=flat&logo=github&logoColor=white" alt="GitHub"/>
        </a>
        <a href="https://www.linkedin.com/in/ronitraj-ai" target="_blank">
          <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=flat&logo=linkedin&logoColor=white" alt="LinkedIn"/>
        </a>
        <a href="mailto:ronii@gitmesh.dev">
          <img src="https://img.shields.io/badge/Email-D14836?style=flat&logo=gmail&logoColor=white" alt="Email"/>
        </a>
      </p>
    </td>
  </tr>
</table>

## License

Licensed under the **Apache License 2.0**. See the [`LICENSE`](LICENSE) file in this repository for the full text.

---

<div align="center">

<a href="https://www.lfdecentralizedtrust.org/">
  <img src="https://www.lfdecentralizedtrust.org/hubfs/LF%20Decentralized%20Trust/lfdt-horizontal-white.png" alt="Supported by the Linux Foundation Decentralized Trust" width="220"/>
</a>

**A Lab under the [Linux Foundation Decentralized Trust](https://www.lfdecentralizedtrust.org/)**

</div>
