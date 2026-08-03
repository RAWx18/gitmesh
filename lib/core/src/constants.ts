export const PROJECT_ORG_STATUSES = ["active", "paused", "archived"] as const;
export type ProjectOrgStatus = (typeof PROJECT_ORG_STATUSES)[number];

export const DEPLOYMENT_MODES = ["local_trusted", "authenticated"] as const;
export type DeploymentMode = (typeof DEPLOYMENT_MODES)[number];

export const DEPLOYMENT_EXPOSURES = ["private", "public"] as const;
export type DeploymentExposure = (typeof DEPLOYMENT_EXPOSURES)[number];

export const AUTH_BASE_URL_MODES = ["auto", "explicit"] as const;
export type AuthBaseUrlMode = (typeof AUTH_BASE_URL_MODES)[number];

export const AGENT_STATUSES = [
  "active",
  "paused",
  "idle",
  "running",
  "error",
  "pending_approval",
  "terminated",
] as const;
export type AgentStatus = (typeof AGENT_STATUSES)[number];

export const AGENT_ADAPTER_TYPES = [
  "process",
  "http",
  "claude_local",
  "codex_local",
  "opencode_local",
  "pi_local",
  "cursor",
  "gateway",
  "minimax",
] as const;
export type AgentAdapterType = (typeof AGENT_ADAPTER_TYPES)[number];

export const AGENT_ROLES = [
  "triage",
  "pr_review",
  "docs",
  "security",
  "community",
  "onboarding",
  "release",
  "general",
] as const;
export type AgentRole = (typeof AGENT_ROLES)[number];

export const AGENT_ROLE_LABELS: Record<AgentRole, string> = {
  triage: "Triage Agent",
  pr_review: "PR Review Agent",
  docs: "Docs Agent",
  security: "Security Agent",
  community: "Community Agent",
  onboarding: "Onboarding Agent",
  release: "Release Agent",
  general: "General Agent",
};

/** Default configurations for each OSS agent role */
export const OSS_ROLE_DEFAULTS: Record<AgentRole, {
  description: string;
  heartbeatSchedule: string;
  defaultBudgetMonthlyCents: number;
  requiresApproval: boolean;
}> = {
  triage: {
    description: "Reads incoming issues, labels, prioritizes, routes, asks clarifying questions, closes duplicates",
    heartbeatSchedule: "0 * * * *", // every hour
    defaultBudgetMonthlyCents: 5000,
    requiresApproval: false,
  },
  pr_review: {
    description: "Reviews opened PRs for style, test coverage, policy compliance",
    heartbeatSchedule: "on:pr_opened", // event-triggered
    defaultBudgetMonthlyCents: 10000,
    requiresApproval: false,
  },
  docs: {
    description: "Detects code changes without corresponding doc updates, drafts doc PRs",
    heartbeatSchedule: "0 0 * * *", // daily
    defaultBudgetMonthlyCents: 3000,
    requiresApproval: false,
  },
  security: {
    description: "Monitors dependency CVEs, assesses severity, drafts advisories - always human-gated",
    heartbeatSchedule: "0 9 * * 1", // every Monday morning
    defaultBudgetMonthlyCents: 5000,
    requiresApproval: true,
  },
  community: {
    description: "Monitors Discord and GitHub Discussions, routes questions, drafts responses",
    heartbeatSchedule: "0 */6 * * *", // every 6 hours
    defaultBudgetMonthlyCents: 3000,
    requiresApproval: false,
  },
  onboarding: {
    description: "Comments on first-time contributor PRs with contextual guidance",
    heartbeatSchedule: "on:first_pr", // event-triggered
    defaultBudgetMonthlyCents: 2000,
    requiresApproval: false,
  },
  release: {
    description: "Generates changelogs, bumps version files, drafts release notes",
    heartbeatSchedule: "manual", // maintainer trigger only
    defaultBudgetMonthlyCents: 2000,
    requiresApproval: true,
  },
  general: {
    description: "General purpose agent with no specific role",
    heartbeatSchedule: "0 * * * *",
    defaultBudgetMonthlyCents: 5000,
    requiresApproval: false,
  },
};

export const AGENT_ICON_NAMES = [
  "bot",
  "cpu",
  "brain",
  "zap",
  "rocket",
  "code",
  "terminal",
  "shield",
  "eye",
  "search",
  "wrench",
  "hammer",
  "lightbulb",
  "sparkles",
  "star",
  "heart",
  "flame",
  "bug",
  "cog",
  "database",
  "globe",
  "lock",
  "mail",
  "message-square",
  "file-code",
  "git-branch",
  "package",
  "puzzle",
  "target",
  "wand",
  "atom",
  "circuit-board",
  "radar",
  "swords",
  "telescope",
  "microscope",
  "crown",
  "gem",
  "hexagon",
  "pentagon",
  "fingerprint",
] as const;
export type AgentIconName = (typeof AGENT_ICON_NAMES)[number];

export const ISSUE_STATUSES = [
  "backlog",
  "todo",
  "in_progress",
  "in_review",
  "done",
  "blocked",
  "cancelled",
] as const;
export type IssueStatus = (typeof ISSUE_STATUSES)[number];

export const ISSUE_PRIORITIES = ["critical", "high", "medium", "low"] as const;
export type IssuePriority = (typeof ISSUE_PRIORITIES)[number];

export const GOAL_LEVELS = ["project", "milestone", "issue", "task"] as const;
export type GoalLevel = (typeof GOAL_LEVELS)[number];

export const GOAL_STATUSES = ["planned", "active", "achieved", "cancelled"] as const;
export type GoalStatus = (typeof GOAL_STATUSES)[number];

export const PROJECT_STATUSES = [
  "backlog",
  "planned",
  "in_progress",
  "completed",
  "cancelled",
] as const;
export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export const PROJECT_COLORS = [
  "#6366f1", // indigo
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#ef4444", // red
  "#f97316", // orange
  "#eab308", // yellow
  "#22c55e", // green
  "#14b8a6", // teal
  "#06b6d4", // cyan
  "#3b82f6", // blue
] as const;

export const APPROVAL_TYPES = ["enable_agent", "approve_admin_strategy", "merge_pr", "close_issue", "publish_advisory"] as const;
export type ApprovalType = (typeof APPROVAL_TYPES)[number];

export const APPROVAL_STATUSES = [
  "pending",
  "revision_requested",
  "approved",
  "rejected",
  "cancelled",
] as const;
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number];

export const SECRET_PROVIDERS = [
  "local_encrypted",
  "aws_secrets_manager",
  "gcp_secret_manager",
  "vault",
] as const;
export type SecretProvider = (typeof SECRET_PROVIDERS)[number];

export const STORAGE_PROVIDERS = ["local_disk", "s3"] as const;
export type StorageProvider = (typeof STORAGE_PROVIDERS)[number];

export const HEARTBEAT_INVOCATION_SOURCES = [
  "timer",
  "assignment",
  "on_demand",
  "automation",
] as const;
export type HeartbeatInvocationSource = (typeof HEARTBEAT_INVOCATION_SOURCES)[number];

export const WAKEUP_TRIGGER_DETAILS = ["manual", "ping", "callback", "system"] as const;
export type WakeupTriggerDetail = (typeof WAKEUP_TRIGGER_DETAILS)[number];

export const WAKEUP_REQUEST_STATUSES = [
  "queued",
  "deferred_issue_execution",
  "claimed",
  "coalesced",
  "skipped",
  "completed",
  "failed",
  "cancelled",
] as const;
export type WakeupRequestStatus = (typeof WAKEUP_REQUEST_STATUSES)[number];

export const HEARTBEAT_RUN_STATUSES = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
] as const;
export type HeartbeatRunStatus = (typeof HEARTBEAT_RUN_STATUSES)[number];

export const LIVE_EVENT_TYPES = [
  "heartbeat.run.queued",
  "heartbeat.run.status",
  "heartbeat.run.event",
  "heartbeat.run.log",
  "agent.status",
  "activity.logged",
] as const;
export type LiveEventType = (typeof LIVE_EVENT_TYPES)[number];

export const PRINCIPAL_TYPES = ["user", "agent"] as const;
export type PrincipalType = (typeof PRINCIPAL_TYPES)[number];

export const MEMBERSHIP_STATUSES = ["pending", "active", "suspended"] as const;
export type MembershipStatus = (typeof MEMBERSHIP_STATUSES)[number];

export const INSTANCE_USER_ROLES = ["instance_admin"] as const;
export type InstanceUserRole = (typeof INSTANCE_USER_ROLES)[number];

export const INVITE_TYPES = ["project_join", "bootstrap_agent"] as const;
export type InviteType = (typeof INVITE_TYPES)[number];

export const INVITE_JOIN_TYPES = ["human", "agent", "both"] as const;
export type InviteJoinType = (typeof INVITE_JOIN_TYPES)[number];

export const JOIN_REQUEST_TYPES = ["human", "agent"] as const;
export type JoinRequestType = (typeof JOIN_REQUEST_TYPES)[number];

export const JOIN_REQUEST_STATUSES = ["pending_approval", "approved", "rejected"] as const;
export type JoinRequestStatus = (typeof JOIN_REQUEST_STATUSES)[number];

export const PERMISSION_KEYS = [
  "agents:create",
  "users:invite",
  "users:manage_permissions",
  "tasks:assign",
  "tasks:assign_scope",
  "joins:approve",
] as const;
export type PermissionKey = (typeof PERMISSION_KEYS)[number];
