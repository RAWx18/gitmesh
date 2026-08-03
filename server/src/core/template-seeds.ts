/**
 * Default Project Template Seed Data
 *
 * Pre-seeds the project_templates table with 5 archetype templates
 * on first boot. Makes GitMesh immediately useful for new projects.
 */

import type { Db } from "@gitmesh/data";
import { projectTemplates, eq } from "@gitmesh/data";

export interface TemplateAgentConfig {
    role: string;
    name: string;
    schedule?: string;
    triggers?: string[];
    budget: number;
}

export interface TemplatePolicyConfig {
    name: string;
    actionPattern: string;
    conditions?: Record<string, unknown>;
    effect: string;
    priority?: number;
}

const CLI_TOOL_TEMPLATE = {
    name: "CLI Tool",
    description: "Minimal agent team for command-line tools and utilities. Covers triage, code review, documentation sync, and release automation.",
    archetype: "cli_tool",
    agents: [
        { role: "triage", name: "Issue Triage", schedule: "0 * * * *", budget: 5000 },
        { role: "pr_review", name: "PR Review", triggers: ["pr_opened"], budget: 10000 },
        { role: "docs", name: "Docs Sync", schedule: "0 2 * * *", budget: 3000 },
        { role: "release", name: "Release Agent", budget: 5000 },
    ] as TemplateAgentConfig[],
    policies: [
        { name: "Require approval for merge", actionPattern: "merge_pr", effect: "require_approval", priority: 10 },
        { name: "Allow triage actions", actionPattern: "close_issue|add_label|assign_issue", conditions: { agentRole: ["triage"] }, effect: "allow", priority: 50 },
        { name: "Default allow", actionPattern: "*", effect: "allow", priority: 1000 },
    ] as TemplatePolicyConfig[],
};

const JS_LIBRARY_TEMPLATE = {
    name: "JavaScript Library",
    description: "Full agent team for JavaScript/TypeScript libraries. Includes security monitoring and community engagement on top of the CLI Tool template.",
    archetype: "js_library",
    agents: [
        { role: "triage", name: "Issue Triage", schedule: "0 * * * *", budget: 5000 },
        { role: "pr_review", name: "PR Review", triggers: ["pr_opened"], budget: 10000 },
        { role: "docs", name: "Docs Sync", schedule: "0 2 * * *", budget: 3000 },
        { role: "security", name: "Security Agent", schedule: "0 9 * * 1", budget: 8000 },
        { role: "community", name: "Community Agent", triggers: ["issue_opened", "issue_comment"], budget: 3000 },
        { role: "release", name: "Release Agent", budget: 5000 },
    ] as TemplateAgentConfig[],
    policies: [
        { name: "Require approval for merge", actionPattern: "merge_pr", effect: "require_approval", priority: 10 },
        { name: "Require approval for security advisories", actionPattern: "publish_advisory", effect: "require_approval", priority: 20 },
        { name: "Block push to main", actionPattern: "push", conditions: { targetBranch: ["main", "master"] }, effect: "block", priority: 30 },
        { name: "Allow triage actions", actionPattern: "close_issue|add_label", conditions: { agentRole: ["triage"] }, effect: "allow", priority: 50 },
        { name: "Default allow", actionPattern: "*", effect: "allow", priority: 1000 },
    ] as TemplatePolicyConfig[],
};

const INFRASTRUCTURE_TEMPLATE = {
    name: "Infrastructure / DevOps",
    description: "All 7 agent roles with elevated security scrutiny on CI/workflow files. Ideal for infrastructure projects, Terraform modules, and Kubernetes operators.",
    archetype: "infrastructure",
    agents: [
        { role: "triage", name: "Issue Triage", schedule: "0 * * * *", budget: 5000 },
        { role: "pr_review", name: "PR Review", triggers: ["pr_opened"], budget: 10000 },
        { role: "docs", name: "Docs Sync", schedule: "0 2 * * *", budget: 3000 },
        { role: "security", name: "Security Agent", schedule: "0 9 * * 1", budget: 10000 },
        { role: "community", name: "Community Agent", schedule: "0 */6 * * *", budget: 3000 },
        { role: "onboarding", name: "Onboarding Agent", triggers: ["pr_opened"], budget: 2000 },
        { role: "release", name: "Release Agent", budget: 5000 },
    ] as TemplateAgentConfig[],
    policies: [
        { name: "Require approval for merge", actionPattern: "merge_pr", effect: "require_approval", priority: 10 },
        { name: "Require approval for security advisories", actionPattern: "publish_advisory", effect: "require_approval", priority: 20 },
        { name: "Block push to main", actionPattern: "push", conditions: { targetBranch: ["main", "master"] }, effect: "block", priority: 25 },
        { name: "Block CI modification without approval", actionPattern: "modify_file", conditions: { filePath: [".github/workflows/*", ".gitlab-ci.yml", "Jenkinsfile", ".tekton/*"] }, effect: "require_approval", priority: 30 },
        { name: "Default allow", actionPattern: "*", effect: "allow", priority: 1000 },
    ] as TemplatePolicyConfig[],
};

const CNCF_SANDBOX_TEMPLATE = {
    name: "CNCF Sandbox",
    description: "Full governance for CNCF sandbox projects. All 7 agent roles with strict policy enforcement and compliance-oriented defaults.",
    archetype: "cncf_sandbox",
    agents: [
        { role: "triage", name: "Issue Triage", schedule: "0 * * * *", budget: 5000 },
        { role: "pr_review", name: "PR Review", triggers: ["pr_opened"], budget: 10000 },
        { role: "docs", name: "Docs Sync", schedule: "0 2 * * *", budget: 3000 },
        { role: "security", name: "Security Agent", schedule: "0 9 * * 1", budget: 10000 },
        { role: "community", name: "Community Agent", schedule: "0 */6 * * *", budget: 3000 },
        { role: "onboarding", name: "Onboarding Agent", triggers: ["pr_opened"], budget: 2000 },
        { role: "release", name: "Release Agent", budget: 5000 },
    ] as TemplateAgentConfig[],
    policies: [
        { name: "Require approval for merge", actionPattern: "merge_pr", effect: "require_approval", priority: 10 },
        { name: "Require approval for security advisories", actionPattern: "publish_advisory", effect: "require_approval", priority: 15 },
        { name: "Block push to main", actionPattern: "push", conditions: { targetBranch: ["main", "master", "release/*"] }, effect: "block", priority: 20 },
        { name: "Block CI modification", actionPattern: "modify_file", conditions: { filePath: [".github/workflows/*", ".gitlab-ci.yml", ".tekton/*"] }, effect: "require_approval", priority: 25 },
        { name: "Require approval for closing issues", actionPattern: "close_issue", conditions: { priority: ["critical", "high"] }, effect: "require_approval", priority: 40 },
        { name: "Allow triage actions", actionPattern: "add_label|assign_issue", conditions: { agentRole: ["triage"] }, effect: "allow", priority: 50 },
        { name: "Default allow", actionPattern: "*", effect: "allow", priority: 1000 },
    ] as TemplatePolicyConfig[],
};

const SOLO_MAINTAINER_TEMPLATE = {
    name: "Solo Maintainer",
    description: "Minimal, conservative template for solo-maintained projects. Only triage and PR review, with all actions requiring approval by default.",
    archetype: "solo_maintainer",
    agents: [
        { role: "triage", name: "Issue Triage", schedule: "0 */2 * * *", budget: 2000 },
        { role: "pr_review", name: "PR Review", triggers: ["pr_opened"], budget: 3000 },
    ] as TemplateAgentConfig[],
    policies: [
        { name: "Require approval for all agent actions", actionPattern: "*", effect: "require_approval", priority: 10 },
        { name: "Allow labeling", actionPattern: "add_label", conditions: { agentRole: ["triage"] }, effect: "allow", priority: 5 },
    ] as TemplatePolicyConfig[],
};

const ALL_TEMPLATES = [
    CLI_TOOL_TEMPLATE,
    JS_LIBRARY_TEMPLATE,
    INFRASTRUCTURE_TEMPLATE,
    CNCF_SANDBOX_TEMPLATE,
    SOLO_MAINTAINER_TEMPLATE,
];

/**
 * Seed default templates into the database.
 * Idempotent - skips if templates already exist.
 */
export async function seedDefaultTemplates(db: Db): Promise<{ seeded: number; skipped: number }> {
    let seeded = 0;
    let skipped = 0;

    for (const tpl of ALL_TEMPLATES) {
        // Check if template already exists by name + archetype
        const existing = await db
            .select({ id: projectTemplates.id })
            .from(projectTemplates)
            .where(eq(projectTemplates.archetype, tpl.archetype));

        if (existing.length > 0) {
            skipped++;
            continue;
        }

        await db.insert(projectTemplates).values({
            name: tpl.name,
            description: tpl.description,
            archetype: tpl.archetype,
            agents: tpl.agents,
            policies: tpl.policies,
            version: "1.0.0",
            authorId: null,
            communityContributed: true,
            featured: true,
            downloadCount: 0,
        });

        seeded++;
    }

    return { seeded, skipped };
}
