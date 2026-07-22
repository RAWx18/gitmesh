# gitmesh-cli

> **Status: pre-release scaffold.** Published under the `next` dist-tag while
> the Agent Workspace Compiler is under construction. Subcommands currently
> print "not implemented"; the first real release is `gitmesh doctor`.

GitMesh audits and governs every coding agent from your repo — Claude Code,
Codex, Cursor, Copilot, Gemini/Antigravity, OpenCode, and more. One
git-versioned source of truth for instructions, tools, and guardrails:
audited (`doctor`), compiled to each agent's native config files (`apply`),
drift-checked in CI (`check`), and enforced through each agent's own
mechanisms (`policy`). No server, no login, no telemetry — pure file
operations.

```console
$ npx gitmesh-cli@next --help
```

Installs a `gitmesh` binary:

| Command | Does |
|---|---|
| `gitmesh doctor` | Audit agent configuration across coding agents |
| `gitmesh init` | Create `.gitmesh/` workspace config from existing agent files |
| `gitmesh migrate` | Migrate existing per-tool configs into the canonical source |
| `gitmesh apply` | Compile canonical config to each agent's native files |
| `gitmesh check` | Verify generated configs are in sync (CI drift gate) |
| `gitmesh policy` | Manage policy packs and permission rules |
| `gitmesh legacy …` | The previous GitMesh Agents server/orchestration CLI (maintenance mode) |

The npm package name is `gitmesh-cli` (the unscoped name `gitmesh` belongs to
an unrelated project); the installed binary is `gitmesh`.

Apache-2.0 · [repository](https://github.com/LF-Decentralized-Trust-labs/gitmesh) · a Linux Foundation Decentralized Trust lab
