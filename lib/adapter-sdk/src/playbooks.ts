/**
 * getPlaybooksForRole - Maps an agent role to the set of playbook directories
 * that should be injected into its runtime.
 *
 * Every agent gets the base `core` playbook (heartbeat, API, rules).
 * Role-specific playbooks are added on top based on the agent's role field.
 */

/** All known OSS agent roles */
export type AgentRole =
  | "triage"
  | "pr_review"
  | "docs"
  | "security"
  | "community"
  | "onboarding"
  | "release"
  | "admin"
  | "general";

/** Mapping from role to additional playbook directory names (beyond core) */
const ROLE_PLAYBOOK_MAP: Record<AgentRole, string[]> = {
  triage: ["triage"],
  pr_review: ["pr-review"],
  docs: ["docs"],
  security: ["security"],
  community: ["community"],
  onboarding: ["onboarding"],
  release: ["release-agent"],
  admin: ["agent-setup", "policy-guide"],
  general: [],
};

/**
 * Returns the list of playbook directory names that should be injected for the given role.
 * Always includes `core` (the base playbook) and `policy-guide` as the base set.
 *
 * @param role - The agent's role (e.g., "triage", "pr_review", "docs")
 * @returns Array of playbook directory names to inject (e.g., ["core", "policy-guide", "triage"])
 */
export function getPlaybooksForRole(role: string): string[] {
  const base = ["core", "policy-guide"];
  const rolePlaybooks = ROLE_PLAYBOOK_MAP[role as AgentRole] ?? [];

  // Deduplicate (policy-guide is already in base, and also in admin role)
  const all = [...base, ...rolePlaybooks];
  return [...new Set(all)];
}

/** @deprecated Use getPlaybooksForRole instead */
export const getSkillsForRole = getPlaybooksForRole;
