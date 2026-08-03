/**
 * `agent` subcommands.
 *
 * `agent local-cli` is the heaviest subcommand here - it bundles a few
 * unrelated side effects (mint API key + symlink playbooks + emit shell
 * exports). The implementation pulls each of those into its own helper so
 * `run()` reads as a thin orchestration layer instead of one long function.
 */
import { Command } from "commander";
import type { Agent } from "@gitmesh/core";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  defineClientCommand,
  formatInlineRecord,
  printOutput,
} from "../_shared/define.js";
import type { BaseClientOptions } from "./common.js";

interface AgentListOpts extends BaseClientOptions {}

interface AgentLocalCliOpts extends BaseClientOptions {
  keyName?: string;
  installPlaybooks?: boolean;
}

interface CreatedAgentKey {
  id: string;
  name: string;
  token: string;
  createdAt: string;
}

interface PlaybooksInstallSummary {
  tool: "codex" | "claude";
  target: string;
  linked: string[];
  skipped: string[];
  failed: Array<{ name: string; error: string }>;
}

// ---------------------------------------------------------------------------
// Playbook install pipeline
// ---------------------------------------------------------------------------

const __moduleDir = path.dirname(fileURLToPath(import.meta.url));
const PLAYBOOK_DIR_CANDIDATES = [
  path.resolve(__moduleDir, "../../../../../playbooks"),
  path.resolve(process.cwd(), "playbooks"),
];

interface PlaybookTarget {
  tool: "codex" | "claude";
  envVar: string;
  defaultDir: string;
}

const PLAYBOOK_TARGETS: PlaybookTarget[] = [
  {
    tool: "codex",
    envVar: "CODEX_HOME",
    defaultDir: path.join(os.homedir(), ".codex"),
  },
  {
    tool: "claude",
    envVar: "CLAUDE_HOME",
    defaultDir: path.join(os.homedir(), ".claude"),
  },
];

function resolveToolHome(target: PlaybookTarget): string {
  const fromEnv = process.env[target.envVar]?.trim();
  const base = fromEnv && fromEnv.length > 0 ? fromEnv : target.defaultDir;
  return path.join(base, "skills");
}

async function findPlaybooksDir(): Promise<string | null> {
  for (const candidate of PLAYBOOK_DIR_CANDIDATES) {
    const isDir = await fs
      .stat(candidate)
      .then((stat) => stat.isDirectory())
      .catch(() => false);
    if (isDir) return candidate;
  }
  return null;
}

async function linkSinglePlaybook(
  source: string,
  target: string,
  summary: PlaybooksInstallSummary,
  name: string,
): Promise<void> {
  const existing = await fs.lstat(target).catch(() => null);
  if (existing) {
    summary.skipped.push(name);
    return;
  }
  try {
    await fs.symlink(source, target);
    summary.linked.push(name);
  } catch (err) {
    summary.failed.push({
      name,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

async function installPlaybooks(
  sourceDir: string,
  target: PlaybookTarget,
): Promise<PlaybooksInstallSummary> {
  const targetDir = resolveToolHome(target);
  const summary: PlaybooksInstallSummary = {
    tool: target.tool,
    target: targetDir,
    linked: [],
    skipped: [],
    failed: [],
  };

  await fs.mkdir(targetDir, { recursive: true });
  const entries = await fs.readdir(sourceDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const source = path.join(sourceDir, entry.name);
    const target = path.join(targetDir, entry.name);
    await linkSinglePlaybook(source, target, summary, entry.name);
  }

  return summary;
}

async function installAllPlaybooks(): Promise<PlaybooksInstallSummary[]> {
  const sourceDir = await findPlaybooksDir();
  if (!sourceDir) {
    throw new Error(
      "Could not locate local GitMesh Agents playbooks directory. Expected ./playbooks in the repo checkout.",
    );
  }
  const summaries: PlaybooksInstallSummary[] = [];
  for (const target of PLAYBOOK_TARGETS) {
    summaries.push(await installPlaybooks(sourceDir, target));
  }
  return summaries;
}

// ---------------------------------------------------------------------------
// Shell-export rendering
// ---------------------------------------------------------------------------

function shellEscape(value: string): string {
  return value.replace(/'/g, "'\"'\"'");
}

function renderShellExports(input: {
  apiBase: string;
  projectId: string;
  agentId: string;
  apiKey: string;
}): string {
  const lines = [
    ["GITMESH_API_URL", input.apiBase],
    ["GITMESH_PROJECT_ID", input.projectId],
    ["GITMESH_AGENT_ID", input.agentId],
    ["GITMESH_API_KEY", input.apiKey],
  ];
  return lines.map(([key, value]) => `export ${key}='${shellEscape(value)}'`).join("\n");
}

// ---------------------------------------------------------------------------
// Subcommand specs
// ---------------------------------------------------------------------------

function renderAgentRow(agent: Agent): string {
  return formatInlineRecord({
    id: agent.id,
    name: agent.name,
    role: agent.role,
    status: agent.status,
    reportsTo: agent.reportsTo,
    budgetMonthlyCents: agent.budgetMonthlyCents,
    spentMonthlyCents: agent.spentMonthlyCents,
  });
}

export function registerAgentCommands(program: Command): void {
  const agent = program.command("agent").description("Agent operations");

  defineClientCommand<AgentListOpts>(agent, {
    name: "list",
    describe: "List agents for a project",
    options: [{ flag: "-P, --project-id <id>", desc: "Project ID", required: true }],
    requireProject: true,
    async run(ctx) {
      const rows = (await ctx.resources.agents.list<Agent[]>(ctx.projectId!)) ?? [];

      if (ctx.json) {
        printOutput(rows, { json: true });
        return;
      }
      if (rows.length === 0) {
        printOutput([], { json: false });
        return;
      }
      for (const row of rows) console.log(renderAgentRow(row));
    },
  });

  defineClientCommand<BaseClientOptions>(agent, {
    name: "get",
    describe: "Get one agent",
    positional: [{ name: "agentId", desc: "Agent ID" }],
    async run(ctx, { positional }) {
      const [agentId] = positional;
      const row = await ctx.resources.agents.get<Agent>(agentId);
      printOutput(row, { json: ctx.json });
    },
  });

  defineClientCommand<AgentLocalCliOpts>(agent, {
    name: "local-cli",
    describe:
      "Create an agent API key, install local GitMesh Agents playbooks for Codex/Claude, and print shell exports",
    positional: [{ name: "agentRef", desc: "Agent ID or shortname/url-key" }],
    options: [
      { flag: "-P, --project-id <id>", desc: "Project ID", required: true },
      { flag: "--key-name <name>", desc: "API key label", defaultValue: "local-cli" },
      {
        flag: "--no-install-playbooks",
        desc: "Skip installing Gitmesh playbooks into ~/.codex/skills and ~/.claude/skills",
      },
    ],
    requireProject: true,
    async run(ctx, { positional, options }) {
      const [agentRef] = positional;
      const query = new URLSearchParams({ projectId: ctx.projectId ?? "" });
      const agentRow = await ctx.api.get<Agent>(
        `/api/agents/${encodeURIComponent(agentRef)}?${query.toString()}`,
      );
      if (!agentRow) {
        throw new Error(`Agent not found: ${agentRef}`);
      }

      const now = new Date().toISOString().replaceAll(":", "-");
      const keyName = options.keyName?.trim() ? options.keyName.trim() : `local-cli-${now}`;
      const key = await ctx.api.post<CreatedAgentKey>(`/api/agents/${agentRow.id}/keys`, {
        name: keyName,
      });
      if (!key) {
        throw new Error("Failed to create API key");
      }

      const installSummaries =
        options.installPlaybooks !== false ? await installAllPlaybooks() : [];

      const exportsText = renderShellExports({
        apiBase: ctx.api.apiBase,
        projectId: agentRow.projectId,
        agentId: agentRow.id,
        apiKey: key.token,
      });

      if (ctx.json) {
        printOutput(
          {
            agent: {
              id: agentRow.id,
              name: agentRow.name,
              urlKey: agentRow.urlKey,
              projectId: agentRow.projectId,
            },
            key: {
              id: key.id,
              name: key.name,
              createdAt: key.createdAt,
              token: key.token,
            },
            playbooks: installSummaries,
            exports: exportsText,
          },
          { json: true },
        );
        return;
      }

      console.log(`Agent: ${agentRow.name} (${agentRow.id})`);
      console.log(`API key created: ${key.name} (${key.id})`);
      for (const summary of installSummaries) {
        console.log(
          `${summary.tool}: linked=${summary.linked.length} skipped=${summary.skipped.length} failed=${summary.failed.length} target=${summary.target}`,
        );
        for (const failed of summary.failed) {
          console.log(`  failed ${failed.name}: ${failed.error}`);
        }
      }
      console.log("");
      console.log("# Run this in your shell before launching codex/claude:");
      console.log(exportsText);
    },
  });
}
