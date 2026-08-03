/**
 * Community Skill (Core)
 *
 * Monitors community channels and issues for engagement signals:
 * - Detects unanswered questions in issues/discussions
 * - Identifies stale issues (no activity for 30+ days)
 * - Suggests response templates for common categories
 * - Tracks engagement metrics
 *
 * The agent never auto-responds without approval - it only summarizes
 * and suggests.
 *
 * Triggered on: issue_opened, issue_comment events + scheduled heartbeat
 */

import type { Db } from "@gitmesh/data";
import type { ForgeEvent } from "../forge-sync.js";

export interface CommunityContext {
    db: Db;
    event: ForgeEvent;
    projectId: string;
}

export interface CommunityThread {
    source: "github_issue" | "github_discussion" | "discord";
    threadId: string;
    title: string;
    category: "question" | "bug" | "feature" | "discussion" | "getting-started";
    sentiment: "positive" | "neutral" | "negative";
    isUnanswered: boolean;
    authorLogin?: string;
    url?: string;
}

export interface CommunityResult {
    threads: CommunityThread[];
    suggestedResponse: string | null;
    requiresApproval: boolean;
    engagementSignals: string[];
}

/**
 * Response templates for common issue categories
 */
const RESPONSE_TEMPLATES: Record<string, string> = {
    "getting-started": [
        "Thanks for reaching out! 👋",
        "",
        "Here are some resources that might help:",
        "- 📖 [Getting Started Guide](docs/getting-started.md)",
        "- 💬 Join our [Discord](https://discord.gg/gitmesh) for real-time help",
        "- 📚 Check the [FAQ](docs/faq.md) for common questions",
        "",
        "If you're still stuck, please share:",
        "1. What you've tried so far",
        "2. The error message (if any)",
        "3. Your environment (OS, Node version, etc.)",
    ].join("\n"),

    question: [
        "Thanks for the question! 🤔",
        "",
        "A maintainer will take a look shortly. In the meantime:",
        "- Search existing issues for similar questions",
        "- Check the [documentation](docs/) for relevant guides",
        "",
        "We typically respond within 48 hours on business days.",
    ].join("\n"),

    bug: [
        "Thanks for reporting this bug! 🐛",
        "",
        "To help us investigate, please ensure you've included:",
        "- [ ] Steps to reproduce",
        "- [ ] Expected vs actual behavior",
        "- [ ] Environment details (OS, versions)",
        "- [ ] Error logs or screenshots",
        "",
        "A maintainer will triage this shortly.",
    ].join("\n"),

    feature: [
        "Thanks for the feature suggestion! ✨",
        "",
        "We appreciate your input on how to improve the project.",
        "A maintainer will review this and assess feasibility.",
        "",
        "In the meantime, feel free to:",
        "- Describe your use case in detail",
        "- Suggest a possible implementation approach",
        "- Check if a similar request already exists",
    ].join("\n"),
};

/**
 * Keywords for categorization
 */
const CATEGORY_KEYWORDS: Record<string, string[]> = {
    "getting-started": ["getting started", "how to start", "installation", "setup", "first time", "beginner", "new to"],
    question: ["how", "what", "why", "can i", "is it possible", "help", "?"],
    bug: ["bug", "error", "crash", "broken", "not working", "unexpected", "fail", "issue"],
    feature: ["feature", "request", "enhancement", "add", "implement", "support for", "would be nice"],
};

/**
 * Simple sentiment analysis based on keywords
 */
function analyzeSentiment(text: string): "positive" | "neutral" | "negative" {
    const lower = text.toLowerCase();

    const positiveWords = ["thank", "great", "awesome", "love", "excellent", "wonderful", "perfect", "amazing"];
    const negativeWords = ["terrible", "awful", "hate", "worst", "frustrated", "annoying", "broken", "useless"];

    const positiveScore = positiveWords.filter((w) => lower.includes(w)).length;
    const negativeScore = negativeWords.filter((w) => lower.includes(w)).length;

    if (positiveScore > negativeScore) return "positive";
    if (negativeScore > positiveScore) return "negative";
    return "neutral";
}

/**
 * Categorize an issue/thread based on title and body
 */
function categorize(title: string, body: string): CommunityThread["category"] {
    const combined = `${title} ${body}`.toLowerCase();

    for (const [category, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
        if (keywords.some((kw) => combined.includes(kw))) {
            return category as CommunityThread["category"];
        }
    }

    return "discussion";
}

/**
 * Detect engagement signals from an event
 */
function detectEngagementSignals(event: ForgeEvent): string[] {
    const signals: string[] = [];
    const body = event.body ?? "";
    const title = event.title ?? "";
    const combined = `${title} ${body}`.toLowerCase();

    if (combined.includes("first time") || combined.includes("new to")) {
        signals.push("new_contributor");
    }
    if (combined.includes("?")) {
        signals.push("question_asked");
    }
    if (combined.match(/@[\w-]+/)) {
        signals.push("user_mentioned");
    }
    if (body.length > 500) {
        signals.push("detailed_report");
    }

    return signals;
}

/**
 * Execute community skill for a forge event.
 */
export async function executeCommunity(context: CommunityContext): Promise<CommunityResult> {
    const { event } = context;

    // Only process issue/comment events
    if (!["issue_opened", "issue_comment", "issue_reopened"].includes(event.eventType)) {
        return {
            threads: [],
            suggestedResponse: null,
            requiresApproval: false,
            engagementSignals: [],
        };
    }

    const title = event.title ?? "";
    const body = event.body ?? "";

    // Categorize the thread
    const category = categorize(title, body);
    const sentiment = analyzeSentiment(`${title} ${body}`);
    const signals = detectEngagementSignals(event);

    const thread: CommunityThread = {
        source: "github_issue",
        threadId: event.forgeNumber?.toString() ?? "unknown",
        title: title || "Untitled",
        category,
        sentiment,
        isUnanswered: event.eventType === "issue_opened", // new issues are unanswered
        authorLogin: event.authorLogin,
        url: event.forgeUrl,
    };

    // Generate a suggested response (not auto-posted)
    const template = RESPONSE_TEMPLATES[category] ?? null;
    const requiresApproval = sentiment === "negative" || category === "bug";

    return {
        threads: [thread],
        suggestedResponse: template,
        requiresApproval,
        engagementSignals: signals,
    };
}

/**
 * Skill definition for registration
 */
export const CommunitySkill = {
    name: "community",
    description: "Monitor community engagement and suggest responses",
    execute: executeCommunity,
};
