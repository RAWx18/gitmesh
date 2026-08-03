import type { Command } from "commander";
import pc from "picocolors";
import { resolveCommandContext, addCommonClientOptions, handleCommandError } from "./common.js";
import { parseRepoUrl, type ParsedRepoUrl } from "../../lib/repo-url.js";
import { installPlaybooks } from "./playbook-install.js";

interface ConnectOptions {
  projectId?: string;
  apiBase?: string;
  apiKey?: string;
  context?: string;
  profile?: string;
  name?: string;
  noAgent?: boolean;
  noPolicies?: boolean;
  noSkillInstall?: boolean;
  noWebhook?: boolean;
  json?: boolean;
}

const DEFAULT_WEBHOOK_EVENTS = [
  "issue_opened",
  "issue_comment",
  "pr_opened",
  "pr_comment",
  "pr_review_submitted",
];

export function registerProjectConnectCommand(program: Command): void {
  const project = program.commands.find((c) => c.name() === "project");
  const target = project || program;

  const cmd = target
    .command("connect")
    .description("Connect a project to its forge in one step (OAuth + webhook + default policies + triage agent + skill install)")
    .argument("[repo-url]", "Repository URL - https://github.com/owner/repo, git@github.com:owner/repo.git, or owner/repo. If omitted, falls back to --owner/--repo flags.")
    .option("--owner <owner>", "(legacy) repository owner - used only if <repo-url> is omitted")
    .option("--repo <repo>", "(legacy) repository name - used only if <repo-url> is omitted")
    .option("--provider <provider>", "(legacy) forge provider when using --owner/--repo", "github")
    .option("--name <name>", "Override the auto-derived project name")
    .option("--no-agent", "Skip creating the default triage agent")
    .option("--no-policies", "Skip seeding default policies")
    .option("--no-skill-install", "Skip installing the playbook into ~/.claude/skills and ~/.codex/skills")
    .option("--no-webhook", "Skip auto-registering the forge webhook (use the polling fallback instead)");

  addCommonClientOptions(cmd, { includeProject: true });

  cmd.action(async (repoUrlArg: string | undefined, opts: ConnectOptions & { owner?: string; repo?: string; provider?: string; agent?: boolean; policies?: boolean; skillInstall?: boolean; webhook?: boolean }) => {
    try {
      const parsed = resolveRepoTarget(repoUrlArg, opts);
      const ctx = resolveCommandContext(opts);
      const apiBase = ctx.api.apiBase;

      console.log(pc.bold(pc.cyan(`\nConnecting ${parsed.provider}:${parsed.owner}/${parsed.repo}\n`)));

      // ── 1. Project ────────────────────────────────────────────────────
      let projectId = ctx.projectId;
      if (!projectId) {
        const projectName = opts.name?.trim() || `${parsed.owner}/${parsed.repo}`;
        const created = await ctx.api.post<{ id: string; name: string }>("/api/projects", {
          name: projectName,
          repoUrl: parsed.cloneUrl,
          forgeProvider: parsed.provider,
          forgeOwner: parsed.owner,
          forgeRepo: parsed.repo,
        });
        if (!created?.id) throw new Error("Server did not return a project id");
        projectId = created.id;
        console.log(pc.green(`  ✓  created project "${projectName}" (${projectId})`));
      } else {
        console.log(pc.dim(`  ↷  reusing project ${projectId}`));
      }

      // ── 2. Forge connect (token + clone + polling fallback) ───────────
      if (parsed.provider === "github") {
        await ctx.api.post("/api/github/connect-project", {
          projectId,
          forgeOwner: parsed.owner,
          forgeRepo: parsed.repo,
        });
        console.log(pc.green("  ✓  github token resolved + repo cloned + periodic sync started"));
      } else {
        await ctx.api.post(`/api/projects/${projectId}/forge`, {
          provider: parsed.provider,
          owner: parsed.owner,
          repo: parsed.repo,
        }, { ignoreNotFound: true });
        console.log(pc.dim(`  ↷  forge metadata recorded (provider=${parsed.provider}); manual webhook setup may be required.`));
      }

      // ── 3. Webhook ────────────────────────────────────────────────────
      if (opts.webhook !== false) {
        if (isLoopbackBase(apiBase) && !process.env.GITMESH_PUBLIC_BASE_URL) {
          console.log(pc.dim("  ↷  api base is loopback; skipping webhook (polling sync is active instead)."));
        } else {
          try {
            await ctx.api.post(`/api/projects/${projectId}/forge/webhooks`, {
              forgeProvider: parsed.provider,
              forgeOwner: parsed.owner,
              forgeRepo: parsed.repo,
              events: DEFAULT_WEBHOOK_EVENTS,
            });
            console.log(pc.green("  ✓  webhook registered on forge"));
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            console.log(pc.yellow(`  ⚠  webhook auto-register failed: ${msg}`));
            console.log(pc.dim("     polling sync still works; you can retry with `gitmesh-agents project connect ... --project-id ...`."));
          }
        }
      } else {
        console.log(pc.dim("  ↷  skipping webhook auto-register (--no-webhook)"));
      }

      // ── 4. Default policies ───────────────────────────────────────────
      if (opts.policies !== false) {
        // POST /api/projects auto-initializes defaults on creation; this call is
        // safe (initializeDefaults() short-circuits if any policies already exist).
        await ctx.api.post(`/api/projects/${projectId}/policies/initialize`, {});
        console.log(pc.green("  ✓  default policies seeded (open Settings → Policies → Templates to install more)"));
      } else {
        console.log(pc.dim("  ↷  skipping default policies (--no-policies)"));
      }

      // ── 5. Triage agent ───────────────────────────────────────────────
      let triageAgent: { id: string; name: string } | null = null;
      if (opts.agent !== false) {
        try {
          triageAgent = await ctx.api.post<{ id: string; name: string }>(
            `/api/projects/${projectId}/agents`,
            {
              name: "Triage Bot",
              role: "triage",
              adapterType: "claude_local",
              adapterConfig: {},
              budgetMonthlyCents: 5000,
            },
          );
          if (triageAgent?.id) {
            console.log(pc.green(`  ✓  triage agent "${triageAgent.name}" created (${triageAgent.id})`));
          }
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          console.log(pc.yellow(`  ⚠  triage agent creation failed: ${msg}`));
          console.log(pc.dim("     create one manually from Settings → Agents."));
        }
      } else {
        console.log(pc.dim("  ↷  skipping default triage agent (--no-agent)"));
      }

      // ── 6. Playbook install ───────────────────────────────────────────
      if (opts.skillInstall !== false) {
        try {
          const roles = ["core"];
          if (triageAgent) roles.push("triage");
          await installPlaybooks({
            api: ctx.api,
            apiBase,
            roles,
            targets: ["claude", "codex"],
            silent: false,
          });
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          console.log(pc.yellow(`  ⚠  playbook install failed: ${msg}`));
        }
      } else {
        console.log(pc.dim("  ↷  skipping playbook install (--no-skill-install)"));
      }

      // ── 7. Done ───────────────────────────────────────────────────────
      const projectUrl = `${apiBase}/projects/${projectId}`;
      console.log(pc.bold(`\n→ ${projectUrl}\n`));
      console.log(pc.dim("  next: trigger an issue or PR on your repo to see the activity log light up.\n"));

      if (opts.json) {
        console.log(JSON.stringify({ projectId, repo: parsed, projectUrl, agentId: triageAgent?.id ?? null }, null, 2));
      }
    } catch (err) {
      handleCommandError(err);
    }
  });
}

function resolveRepoTarget(
  repoUrlArg: string | undefined,
  opts: { owner?: string; repo?: string; provider?: string },
): ParsedRepoUrl {
  if (repoUrlArg && repoUrlArg.trim()) {
    return parseRepoUrl(repoUrlArg);
  }
  if (opts.owner && opts.repo) {
    const provider = (opts.provider ?? "github").toLowerCase();
    if (provider !== "github" && provider !== "gitlab" && provider !== "forgejo") {
      throw new Error(`Unsupported provider "${opts.provider}". Use github, gitlab, or forgejo.`);
    }
    const host = provider === "github" ? "github.com" : provider === "gitlab" ? "gitlab.com" : opts.owner;
    return {
      provider,
      owner: opts.owner,
      repo: opts.repo,
      host,
      cloneUrl: `https://${host}/${opts.owner}/${opts.repo}.git`,
    };
  }
  throw new Error(
    "A repository URL is required. Pass it as a positional argument:\n" +
      "  gitmesh-agents project connect https://github.com/<owner>/<repo>",
  );
}

function isLoopbackBase(apiBase: string): boolean {
  try {
    const url = new URL(apiBase);
    return url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "::1";
  } catch {
    return true;
  }
}
