import { Command } from "commander";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve, join } from "node:path";

const DEFAULT_AGENTS_YAML = `# .gitmesh/agents.yaml - Agent configuration for this project
# Docs: https://gitmesh.dev/docs/config
version: 1

project:
  name: "{PROJECT_NAME}"
  forge: {FORGE}
  owner: "{OWNER}"
  repo: "{REPO}"

agents:
  triage:
    enabled: true
    schedule: "0 * * * *"  # every hour
    budget_monthly_cents: 5000
    adapter: claude_local
    auto_approve: false

  pr_review:
    enabled: true
    schedule: null  # event-triggered only
    budget_monthly_cents: 10000
    adapter: claude_local
    auto_approve: false

  docs:
    enabled: false  # enable when ready
    schedule: null
    budget_monthly_cents: 3000
    adapter: claude_local
    auto_approve: false

  security:
    enabled: false
    schedule: "0 0 * * *"  # daily
    budget_monthly_cents: 2000
    adapter: claude_local
    auto_approve: false  # always human-gated

  community:
    enabled: false
    schedule: "*/30 * * * *"  # every 30 min
    budget_monthly_cents: 3000
    adapter: claude_local
    auto_approve: false

  onboarding:
    enabled: false
    schedule: null  # event-triggered
    budget_monthly_cents: 2000
    adapter: claude_local
    auto_approve: false

  release:
    enabled: false
    schedule: null  # manual trigger
    budget_monthly_cents: 5000
    adapter: claude_local
    auto_approve: false

policy:
  extends: default
  overrides: []
`;

const DEFAULT_POLICY_YAML = `# .gitmesh/policy.yaml - Policy rules for agent governance
# Docs: https://gitmesh.dev/docs/policy
version: "1"

review:
  required_approvals: 1
  auto_merge: false
  require_ci_pass: true

security:
  auto_fix_dependencies: false
  advisory_approval_required: true
  disclosure_timeline_days: 90

triage:
  auto_label: true
  stale_days: 14
  auto_close_stale: false

release:
  cadence: manual  # manual | weekly | on-merge
  require_changelog: true
  require_approval: true

community:
  welcome_new_contributors: true
  response_time_hours: 24

agents:
  max_concurrent: 3
  budget_alert_percent: 80
  require_human_approval:
    - merge
    - release
    - security_advisory
    - agent_enable
`;

export function registerInitCommand(program: Command): void {
  program
    .command("init")
    .description("Initialize Gitmesh configuration for this project")
    .option("--name <name>", "Project name")
    .option("--forge <forge>", "Forge provider (github | gitlab)", "github")
    .option("--owner <owner>", "Repository owner/organization")
    .option("--repo <repo>", "Repository name")
    .option("--dir <dir>", "Project root directory", ".")
    .option("--no-policy", "Skip creating policy.yaml")
    .option("-y, --yes", "Accept defaults without prompting")
    .action(async (opts) => {
      const projectDir = resolve(opts.dir);
      const gitmeshDir = join(projectDir, ".gitmesh");

      // Derive defaults from current directory name
      const dirName = projectDir.split("/").pop() || "my-project";
      const projectName = opts.name || dirName;
      const owner = opts.owner || "my-org";
      const repo = opts.repo || dirName;
      const forge = opts.forge || "github";

      // Check if already initialized
      const agentsYamlPath = join(gitmeshDir, "agents.yaml");
      if (existsSync(agentsYamlPath)) {
        console.error(
          `  ✗  ${agentsYamlPath} already exists. Use 'gitmesh-agents configure' to modify.`,
        );
        process.exit(1);
      }

      // Create .gitmesh directory
      if (!existsSync(gitmeshDir)) {
        mkdirSync(gitmeshDir, { recursive: true });
      }

      // Write agents.yaml
      const agentsContent = DEFAULT_AGENTS_YAML
        .replace("{PROJECT_NAME}", projectName)
        .replace("{FORGE}", forge)
        .replace("{OWNER}", owner)
        .replace("{REPO}", repo);

      writeFileSync(agentsYamlPath, agentsContent, "utf8");
      console.log(`  ✓  Created ${agentsYamlPath}`);

      // Write policy.yaml (unless --no-policy)
      if (opts.policy !== false) {
        const policyPath = join(gitmeshDir, "policy.yaml");
        if (!existsSync(policyPath)) {
          writeFileSync(policyPath, DEFAULT_POLICY_YAML, "utf8");
          console.log(`  ✓  Created ${policyPath}`);
        } else {
          console.log(`  ℹ  ${policyPath} already exists, skipping.`);
        }
      }

      console.log("");
      console.log("  Gitmesh initialized! Next steps:");
      console.log("  1. Review .gitmesh/agents.yaml and enable the agents you want");
      console.log("  2. Review .gitmesh/policy.yaml to customize governance rules");
      console.log("  3. Run 'gitmesh-agents project connect' to link your forge");
      console.log("  4. Add the gitmesh/agent-gate GitHub Action to your CI");
    });
}
