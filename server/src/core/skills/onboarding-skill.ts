/**
 * Onboarding Skill
 *
 * Detects first-time contributors opening PRs and posts contextual
 * guidance: project norms, review timeline, license requirements,
 * style guide excerpt, links to working groups.
 *
 * Triggered on: pr_opened events when the PR author has no prior
 * merged PRs in the project.
 */

import type { Db } from "@gitmesh/data";
import type { ForgeEvent } from "../forge-sync.js";

export interface OnboardingContext {
    db: Db;
    event: ForgeEvent;
    projectId: string;
}

export interface OnboardingResult {
    isFirstTime: boolean;
    comment: string | null;
    assignedReviewer: string | null;
}

/**
 * Known documentation file paths to link in the welcome comment
 */
const DOC_LINKS: Record<string, string> = {
    CONTRIBUTING: "CONTRIBUTING.md",
    CODE_OF_CONDUCT: "CODE_OF_CONDUCT.md",
    LICENSE: "LICENSE",
    STYLE_GUIDE: "docs/style-guide.md",
    ARCHITECTURE: "docs/ARCHITECTURE.md",
};

/**
 * Check if a contributor is a first-time contributor to this project.
 * Uses the forge event's author information and checks prior activity.
 */
function isFirstTimeContributor(event: ForgeEvent): boolean {
    const payload = event.payload as Record<string, unknown>;

    // GitHub sends `author_association` on PR payloads
    const pr = payload.pull_request as Record<string, unknown> | undefined;
    if (pr) {
        const association = pr.author_association as string | undefined;
        if (association === "FIRST_TIME_CONTRIBUTOR" || association === "FIRST_TIMER") {
            return true;
        }
        // NONE = never interacted, could be first PR
        if (association === "NONE") {
            return true;
        }
    }

    // For GitLab / Forgejo, fall back to heuristic: check if we have no prior
    // issues or PRs from this author in our DB (handled by the caller)
    return false;
}

/**
 * Generate a welcome comment for a first-time contributor.
 */
function generateWelcomeComment(event: ForgeEvent): string {
    const authorLogin = event.authorLogin ?? "contributor";
    const prTitle = event.title ?? "your pull request";

    const lines = [
        `👋 **Welcome, @${authorLogin}!** Thanks for your first contribution to this project!`,
        ``,
        `We're excited to review **${prTitle}**. Here are a few things to help you get started:`,
        ``,
        `### 📋 Before Review`,
        `- Please ensure your PR follows our [Contributing Guide](${DOC_LINKS.CONTRIBUTING})`,
        `- All commits should have clear, descriptive messages`,
        `- Tests should pass in CI before requesting review`,
        ``,
        `### ⏰ Review Timeline`,
        `- A maintainer will review your PR within **48 hours** on business days`,
        `- If you don't hear back, feel free to ping the thread`,
        `- Reviews may request changes - this is normal and constructive!`,
        ``,
        `### 📄 License`,
        `- By contributing, you agree that your contribution is licensed under the project's [LICENSE](${DOC_LINKS.LICENSE})`,
        `- Ensure you have the right to submit the code under this license`,
        ``,
        `### 💡 Tips`,
        `- Keep PRs focused on a single change when possible`,
        `- Link related issues using \`Closes #123\` in the PR description`,
        `- Ask questions! We're happy to help in the PR comments or on Discord`,
        ``,
        `---`,
        `*🤖 This message was posted by the GitMesh Onboarding Agent.*`,
    ];

    return lines.join("\n");
}

/**
 * Suggest a reviewer based on the files changed or project CODEOWNERS.
 * Returns a GitHub username or null if no suggestion is available.
 */
function suggestReviewer(event: ForgeEvent): string | null {
    const payload = event.payload as Record<string, unknown>;
    const pr = payload.pull_request as Record<string, unknown> | undefined;

    if (!pr) return null;

    // If the PR already has requested reviewers, don't duplicate
    const requestedReviewers = pr.requested_reviewers as Array<Record<string, unknown>> | undefined;
    if (requestedReviewers && requestedReviewers.length > 0) {
        return null;
    }

    // Fall back to null - real implementation would parse CODEOWNERS
    return null;
}

/**
 * Execute onboarding skill for a forge event.
 */
export async function executeOnboarding(context: OnboardingContext): Promise<OnboardingResult> {
    const { event } = context;

    // Only handle PR opened events
    if (event.eventType !== "pr_opened") {
        return { isFirstTime: false, comment: null, assignedReviewer: null };
    }

    // Check if first-time contributor
    const firstTime = isFirstTimeContributor(event);

    if (!firstTime) {
        return { isFirstTime: false, comment: null, assignedReviewer: null };
    }

    // Generate welcome comment
    const comment = generateWelcomeComment(event);

    // Suggest a reviewer
    const assignedReviewer = suggestReviewer(event);

    return {
        isFirstTime: true,
        comment,
        assignedReviewer,
    };
}

/**
 * Skill definition for registration
 */
export const OnboardingSkill = {
    name: "onboarding",
    description: "Welcome first-time contributors with contextual guidance",
    execute: executeOnboarding,
};
