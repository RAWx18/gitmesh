/**
 * Security Skill (Core)
 *
 * Lightweight heartbeat-driven security checks:
 * - Scans PR diffs for hardcoded secrets and insecure patterns
 * - Detects CI/workflow file modifications that require approval
 * - Flags weak crypto and eval() usage
 *
 * All security actions require human approval - the agent never
 * auto-remediates.
 *
 * Triggered on: pr_opened events + weekly scheduled heartbeat
 */

import type { Db } from "@gitmesh/data";
import type { ForgeEvent } from "../forge-sync.js";

export interface SecurityContext {
    db: Db;
    event: ForgeEvent;
    projectId: string;
}

export interface SecurityViolation {
    checkName: string;
    severity: "critical" | "high" | "medium" | "low";
    message: string;
    filePath?: string;
    line?: number;
    requiresApproval: boolean;
}

export interface SecurityResult {
    violations: SecurityViolation[];
    summary: string;
    requiresApproval: boolean;
}

/**
 * Patterns to detect hardcoded secrets
 */
const SECRET_PATTERNS: Array<{ name: string; pattern: RegExp; severity: "critical" | "high" }> = [
    { name: "AWS Access Key", pattern: /AKIA[0-9A-Z]{16}/g, severity: "critical" },
    { name: "GitHub Token", pattern: /gh[ps]_[A-Za-z0-9_]{36,}/g, severity: "critical" },
    { name: "Private Key Header", pattern: /-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----/g, severity: "critical" },
    { name: "Generic Secret", pattern: /['"][A-Za-z0-9/+=]{40,}['"]/g, severity: "high" },
    { name: "API Key Assignment", pattern: /(?:api[_-]?key|apikey|secret|password|token)\s*[:=]\s*['"][^'"]{8,}['"]/gi, severity: "high" },
];

/**
 * Insecure patterns checklist
 */
const INSECURE_PATTERNS: Array<{ name: string; pattern: RegExp; severity: "critical" | "high" | "medium"; message: string }> = [
    {
        name: "eval_usage",
        pattern: /\beval\s*\(/g,
        severity: "high",
        message: "Usage of eval() detected - potential code injection vulnerability",
    },
    {
        name: "weak_crypto_md5",
        pattern: /\b(createHash|digest)\s*\(\s*['"]md5['"]\s*\)/gi,
        severity: "high",
        message: "MD5 hash detected - use SHA-256 or stronger",
    },
    {
        name: "weak_crypto_sha1",
        pattern: /\b(createHash|digest)\s*\(\s*['"]sha1?['"]\s*\)/gi,
        severity: "medium",
        message: "SHA-1 hash detected - use SHA-256 or stronger",
    },
    {
        name: "insecure_http",
        pattern: /http:\/\/(?!localhost|127\.0\.0\.1|0\.0\.0\.0)/g,
        severity: "medium",
        message: "Insecure HTTP URL detected - use HTTPS",
    },
    {
        name: "excessive_permissions",
        pattern: /0o?777|chmod\s+777/g,
        severity: "high",
        message: "Excessive file permissions (777) detected",
    },
    {
        name: "sql_injection_risk",
        pattern: /\$\{.*\}.*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\b/gi,
        severity: "critical",
        message: "Potential SQL injection - use parameterized queries",
    },
];

/**
 * CI/workflow file patterns that need extra scrutiny
 */
const CI_FILE_PATTERNS = [
    /\.github\/workflows\/.+\.ya?ml$/,
    /\.gitlab-ci\.ya?ml$/,
    /Jenkinsfile$/,
    /\.tekton\//,
    /\.circleci\//,
];

/**
 * Check if a file path corresponds to a CI/workflow file
 */
function isCIFile(filePath: string): boolean {
    return CI_FILE_PATTERNS.some((p) => p.test(filePath));
}

/**
 * Scan content for security violations
 */
function scanContent(content: string, filePath?: string): SecurityViolation[] {
    const violations: SecurityViolation[] = [];

    // Check for hardcoded secrets
    for (const { name, pattern, severity } of SECRET_PATTERNS) {
        const cloned = new RegExp(pattern.source, pattern.flags);
        if (cloned.test(content)) {
            violations.push({
                checkName: `hardcoded_secret:${name.toLowerCase().replace(/\s+/g, "_")}`,
                severity,
                message: `Potential hardcoded ${name} detected`,
                filePath,
                requiresApproval: true,
            });
        }
    }

    // Check for insecure patterns
    for (const { name, pattern, severity, message } of INSECURE_PATTERNS) {
        const cloned = new RegExp(pattern.source, pattern.flags);
        if (cloned.test(content)) {
            violations.push({
                checkName: name,
                severity,
                message,
                filePath,
                requiresApproval: severity === "critical",
            });
        }
    }

    // Check if CI file is being modified
    if (filePath && isCIFile(filePath)) {
        violations.push({
            checkName: "ci_file_modification",
            severity: "high",
            message: `CI/workflow file modified: ${filePath} - requires maintainer approval`,
            filePath,
            requiresApproval: true,
        });
    }

    return violations;
}

/**
 * Generate a summary comment for security scan results
 */
function generateSummary(violations: SecurityViolation[]): string {
    if (violations.length === 0) {
        return "🛡️ **Security Scan**: No issues found. All checks passed.";
    }

    const critical = violations.filter((v) => v.severity === "critical").length;
    const high = violations.filter((v) => v.severity === "high").length;
    const medium = violations.filter((v) => v.severity === "medium").length;
    const needsApproval = violations.some((v) => v.requiresApproval);

    const lines = [
        `🛡️ **Security Scan Report**`,
        ``,
        `| Severity | Count |`,
        `|----------|-------|`,
        ...(critical > 0 ? [`| 🔴 Critical | ${critical} |`] : []),
        ...(high > 0 ? [`| 🟠 High | ${high} |`] : []),
        ...(medium > 0 ? [`| 🟡 Medium | ${medium} |`] : []),
        ``,
        `### Findings`,
        ``,
    ];

    for (const v of violations) {
        const icon = v.severity === "critical" ? "🔴" : v.severity === "high" ? "🟠" : "🟡";
        const file = v.filePath ? ` in \`${v.filePath}\`` : "";
        lines.push(`- ${icon} **${v.checkName}**${file}: ${v.message}`);
    }

    if (needsApproval) {
        lines.push(``);
        lines.push(`> ⚠️ **This PR requires maintainer approval** due to security findings.`);
    }

    lines.push(``);
    lines.push(`---`);
    lines.push(`*🤖 Scanned by GitMesh Security Agent. All security changes require human approval.*`);

    return lines.join("\n");
}

/**
 * Execute security scan for a forge event.
 */
export async function executeSecurity(context: SecurityContext): Promise<SecurityResult> {
    const { event } = context;

    // Only scan PR events - scheduled scans are handled differently
    if (!["pr_opened", "pr_comment"].includes(event.eventType)) {
        return {
            violations: [],
            summary: "Security skill: not applicable for this event type",
            requiresApproval: false,
        };
    }

    const payload = event.payload as Record<string, unknown>;
    const pr = payload.pull_request as Record<string, unknown> | undefined;

    // Scan the PR body for secrets (basic heuristic)
    const allViolations: SecurityViolation[] = [];

    // Scan PR body
    const body = event.body ?? "";
    if (body.length > 0) {
        const bodyViolations = scanContent(body, "PR description");
        allViolations.push(...bodyViolations);
    }

    // Scan PR title
    const title = event.title ?? "";
    if (title.length > 0) {
        const titleViolations = scanContent(title, "PR title");
        allViolations.push(...titleViolations);
    }

    // Check files changed (if available in payload)
    const files = (pr?.changed_files as number) ?? 0;
    const filesPayload = payload.files as Array<Record<string, unknown>> | undefined;
    if (filesPayload) {
        for (const file of filesPayload) {
            const filename = file.filename as string;
            const patch = (file.patch as string) ?? "";
            const fileViolations = scanContent(patch, filename);
            allViolations.push(...fileViolations);
        }
    }

    const requiresApproval = allViolations.some((v) => v.requiresApproval);
    const summary = generateSummary(allViolations);

    return {
        violations: allViolations,
        summary,
        requiresApproval,
    };
}

/**
 * Skill definition for registration
 */
export const SecuritySkill = {
    name: "security",
    description: "Scan PRs for security vulnerabilities, secrets, and CI file changes",
    execute: executeSecurity,
};
