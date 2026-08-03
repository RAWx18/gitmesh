/**
 * Release Skill
 *
 * Automates release workflows:
 * - Detects commits since last tag
 * - Generates changelog entries grouped by conventional commit type
 * - Bumps version in package files (package.json, VERSION, etc.)
 * - Drafts release PR with changelog + version bump
 *
 * Triggered manually by maintainers or via API.
 */

import type { Db } from "@gitmesh/data";
import type { ForgeEvent } from "../forge-sync.js";

export interface ReleaseContext {
    db: Db;
    event: ForgeEvent;
    projectId: string;
}

export interface ReleaseResult {
    changelog: string;
    suggestedVersion: string | null;
    commitGroups: Record<string, CommitEntry[]>;
    totalCommits: number;
}

export interface CommitEntry {
    hash: string;
    type: string;
    scope: string | null;
    message: string;
    breaking: boolean;
}

/**
 * Conventional commit type labels
 */
const COMMIT_TYPE_LABELS: Record<string, string> = {
    feat: "✨ Features",
    fix: "🐛 Bug Fixes",
    docs: "📚 Documentation",
    style: "💄 Styling",
    refactor: "♻️ Code Refactoring",
    perf: "⚡ Performance",
    test: "✅ Tests",
    build: "📦 Build System",
    ci: "🔧 CI/CD",
    chore: "🔨 Chores",
    revert: "⏪ Reverts",
};

/**
 * Parse a conventional commit message into components.
 *
 * Format: `type(scope): message` or `type: message` or `type!: message` (breaking)
 */
function parseConventionalCommit(message: string): {
    type: string;
    scope: string | null;
    description: string;
    breaking: boolean;
} {
    const pattern = /^(\w+)(\(([^)]+)\))?(!)?:\s*(.+)$/;
    const match = message.trim().match(pattern);

    if (!match) {
        return {
            type: "chore",
            scope: null,
            description: message.trim(),
            breaking: false,
        };
    }

    return {
        type: match[1].toLowerCase(),
        scope: match[3] ?? null,
        description: match[5],
        breaking: !!match[4] || message.toLowerCase().includes("breaking change"),
    };
}

/**
 * Suggest the next semantic version based on commit types.
 *
 * - If any commit has `breaking: true` → major bump
 * - If any commit has type `feat` → minor bump
 * - Otherwise → patch bump
 */
function suggestVersionBump(
    currentVersion: string,
    commits: CommitEntry[],
): string {
    const [major, minor, patch] = currentVersion
        .replace(/^v/, "")
        .split(".")
        .map(Number);

    const hasBreaking = commits.some((c) => c.breaking);
    const hasFeature = commits.some((c) => c.type === "feat");

    if (hasBreaking) {
        return `${major + 1}.0.0`;
    }
    if (hasFeature) {
        return `${major}.${minor + 1}.0`;
    }
    return `${major}.${minor}.${patch + 1}`;
}

/**
 * Group commits by conventional commit type.
 */
function groupCommits(
    commits: CommitEntry[],
): Record<string, CommitEntry[]> {
    const groups: Record<string, CommitEntry[]> = {};

    for (const commit of commits) {
        const key = commit.type;
        if (!groups[key]) {
            groups[key] = [];
        }
        groups[key].push(commit);
    }

    return groups;
}

/**
 * Generate a markdown changelog from grouped commits.
 */
function generateChangelog(
    version: string,
    groups: Record<string, CommitEntry[]>,
    date: string,
): string {
    const lines: string[] = [
        `## [${version}] - ${date}`,
        ``,
    ];

    // Breaking changes section first
    const breakingChanges = Object.values(groups)
        .flat()
        .filter((c) => c.breaking);

    if (breakingChanges.length > 0) {
        lines.push(`### ⚠️ BREAKING CHANGES`);
        lines.push(``);
        for (const commit of breakingChanges) {
            const scope = commit.scope ? `**${commit.scope}**: ` : "";
            lines.push(`- ${scope}${commit.message} (\`${commit.hash.slice(0, 7)}\`)`);
        }
        lines.push(``);
    }

    // Grouped changes
    const typeOrder = ["feat", "fix", "perf", "refactor", "docs", "test", "build", "ci", "style", "chore", "revert"];

    for (const type of typeOrder) {
        const commits = groups[type];
        if (!commits || commits.length === 0) continue;

        const label = COMMIT_TYPE_LABELS[type] ?? `🔖 ${type}`;
        lines.push(`### ${label}`);
        lines.push(``);

        for (const commit of commits) {
            const scope = commit.scope ? `**${commit.scope}**: ` : "";
            lines.push(`- ${scope}${commit.message} (\`${commit.hash.slice(0, 7)}\`)`);
        }
        lines.push(``);
    }

    // Catch-all for unknown types
    for (const [type, commits] of Object.entries(groups)) {
        if (typeOrder.includes(type)) continue;
        if (commits.length === 0) continue;

        lines.push(`### 🔖 ${type}`);
        lines.push(``);
        for (const commit of commits) {
            const scope = commit.scope ? `**${commit.scope}**: ` : "";
            lines.push(`- ${scope}${commit.message} (\`${commit.hash.slice(0, 7)}\`)`);
        }
        lines.push(``);
    }

    lines.push(`---`);
    lines.push(`*🤖 Generated by GitMesh Release Agent*`);

    return lines.join("\n");
}

/**
 * Execute the release skill.
 *
 * In a real workflow this would:
 * 1. Use the GitHub/GitLab API to list commits since the last tag
 * 2. Parse each commit as a conventional commit
 * 3. Group and generate changelog
 * 4. Suggest a version bump
 * 5. Draft a PR with changelog + bumped version files
 *
 * For now, it processes the event payload and generates a changelog template.
 */
export async function executeRelease(context: ReleaseContext): Promise<ReleaseResult> {
    const { event } = context;

    // The release skill is typically manually triggered.
    // When triggered by a forge event, we use the event's data as a starting point.
    const payload = event.payload as Record<string, unknown>;
    const commitsRaw = (payload.commits ?? []) as Array<Record<string, unknown>>;

    // Parse commits
    const commits: CommitEntry[] = commitsRaw.map((c) => {
        const message = (c.message as string) ?? "";
        const parsed = parseConventionalCommit(message);
        return {
            hash: (c.id as string) ?? (c.sha as string) ?? "unknown",
            type: parsed.type,
            scope: parsed.scope,
            message: parsed.description,
            breaking: parsed.breaking,
        };
    });

    // If no commits from the event, generate a placeholder
    if (commits.length === 0) {
        return {
            changelog: "No commits found since last release. Use `POST /api/agents/{id}/trigger-release` with commit data.",
            suggestedVersion: null,
            commitGroups: {},
            totalCommits: 0,
        };
    }

    // Group commits
    const commitGroups = groupCommits(commits);

    // Current version - in a real implementation, read from package.json
    const currentVersion = (payload.currentVersion as string) ?? "0.1.0";
    const suggestedVersion = suggestVersionBump(currentVersion, commits);

    // Generate changelog
    const today = new Date().toISOString().split("T")[0];
    const changelog = generateChangelog(suggestedVersion, commitGroups, today);

    return {
        changelog,
        suggestedVersion,
        commitGroups,
        totalCommits: commits.length,
    };
}

/**
 * Skill definition for registration
 */
export const ReleaseSkill = {
    name: "release",
    description: "Generate changelogs, bump versions, and draft release notes",
    execute: executeRelease,
};
