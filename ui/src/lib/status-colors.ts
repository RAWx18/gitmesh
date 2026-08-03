/**
 * GitMesh status & priority token system.
 *
 * Render-time color decisions go through a typed token registry keyed by
 * status/priority string. Components use `getStatusTokens` and
 * `getPriorityTokens` rather than ad hoc record literals.
 *
 * Legacy `Record<string, string>` exports remain for code that imports
 * them by name; prefer the helpers in new code.
 */

// ---------------------------------------------------------------------------
// Token shape
// ---------------------------------------------------------------------------

export interface StatusTokens {
  /** classes for `StatusBadge` (background + text) */
  badge: string;
  /** classes for `StatusIcon` ring (border + text color) */
  ring: string;
  /** classes for solid agent dot */
  dot: string;
  /** classes for monochrome text */
  text: string;
}

export interface PriorityTokens {
  /** classes for the priority icon glyph */
  icon: string;
}

// ---------------------------------------------------------------------------
// Reusable palette atoms - one source of truth for hue choices
// ---------------------------------------------------------------------------

const ATOM = {
  muted: {
    badge: "bg-muted text-muted-foreground",
    ring: "text-muted-foreground border-muted-foreground",
    dot: "bg-neutral-400",
    text: "text-muted-foreground",
  },
  neutral: {
    badge: "bg-muted text-muted-foreground",
    ring: "text-neutral-500 border-neutral-500",
    dot: "bg-neutral-400",
    text: "text-neutral-500",
  },
  blue: {
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
    ring: "text-blue-600 border-blue-600 dark:text-blue-400 dark:border-blue-400",
    dot: "bg-blue-400",
    text: "text-blue-600 dark:text-blue-400",
  },
  cyan: {
    badge: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300",
    ring: "text-cyan-600 border-cyan-600 dark:text-cyan-400 dark:border-cyan-400",
    dot: "bg-cyan-400 animate-pulse",
    text: "text-cyan-600 dark:text-cyan-400",
  },
  yellow: {
    badge: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/50 dark:text-yellow-300",
    ring: "text-yellow-600 border-yellow-600 dark:text-yellow-400 dark:border-yellow-400",
    dot: "bg-yellow-400",
    text: "text-yellow-600 dark:text-yellow-400",
  },
  violet: {
    badge: "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300",
    ring: "text-violet-600 border-violet-600 dark:text-violet-400 dark:border-violet-400",
    dot: "bg-violet-400",
    text: "text-violet-600 dark:text-violet-400",
  },
  green: {
    badge: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
    ring: "text-green-600 border-green-600 dark:text-green-400 dark:border-green-400",
    dot: "bg-green-400",
    text: "text-green-600 dark:text-green-400",
  },
  amber: {
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
    ring: "text-amber-600 border-amber-600 dark:text-amber-400 dark:border-amber-400",
    dot: "bg-amber-400",
    text: "text-amber-600 dark:text-amber-400",
  },
  orange: {
    badge: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
    ring: "text-orange-600 border-orange-600 dark:text-orange-400 dark:border-orange-400",
    dot: "bg-orange-400",
    text: "text-orange-600 dark:text-orange-400",
  },
  red: {
    badge: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
    ring: "text-red-600 border-red-600 dark:text-red-400 dark:border-red-400",
    dot: "bg-red-400",
    text: "text-red-600 dark:text-red-400",
  },
} as const satisfies Record<string, StatusTokens>;

// ---------------------------------------------------------------------------
// Status registry - every known status maps to a single atom
// ---------------------------------------------------------------------------

const STATUS_REGISTRY = {
  // Issue / task
  backlog: ATOM.muted,
  todo: ATOM.blue,
  in_progress: ATOM.yellow,
  in_review: ATOM.violet,
  done: ATOM.green,
  cancelled: ATOM.neutral,
  blocked: ATOM.red,

  // Agent
  active: ATOM.green,
  running: ATOM.cyan,
  paused: ATOM.orange,
  idle: ATOM.yellow,
  archived: ATOM.muted,

  // Goals / milestones
  planned: ATOM.muted,
  achieved: ATOM.green,
  completed: ATOM.green,

  // Run lifecycle
  failed: ATOM.red,
  timed_out: ATOM.orange,
  succeeded: ATOM.green,
  error: ATOM.red,
  terminated: ATOM.red,
  pending: ATOM.amber,

  // Approvals
  pending_approval: ATOM.amber,
  revision_requested: ATOM.blue,
  approved: ATOM.green,
  rejected: ATOM.red,
} as const satisfies Record<string, StatusTokens>;

export type KnownStatus = keyof typeof STATUS_REGISTRY;

const FALLBACK_STATUS_TOKENS: StatusTokens = ATOM.muted;

/** Single helper - returns the full token bundle for any status string. */
export function getStatusTokens(status: string | null | undefined): StatusTokens {
  if (!status) return FALLBACK_STATUS_TOKENS;
  return (STATUS_REGISTRY as Record<string, StatusTokens>)[status] ?? FALLBACK_STATUS_TOKENS;
}

// ---------------------------------------------------------------------------
// Priority registry
// ---------------------------------------------------------------------------

const PRIORITY_REGISTRY = {
  critical: { icon: ATOM.red.text },
  high: { icon: ATOM.orange.text },
  medium: { icon: ATOM.yellow.text },
  low: { icon: ATOM.blue.text },
} as const satisfies Record<string, PriorityTokens>;

export type KnownPriority = keyof typeof PRIORITY_REGISTRY;

const FALLBACK_PRIORITY_TOKENS: PriorityTokens = { icon: ATOM.yellow.text };

export function getPriorityTokens(priority: string | null | undefined): PriorityTokens {
  if (!priority) return FALLBACK_PRIORITY_TOKENS;
  return (PRIORITY_REGISTRY as Record<string, PriorityTokens>)[priority] ?? FALLBACK_PRIORITY_TOKENS;
}

// ---------------------------------------------------------------------------
// Backward-compat exports - derived from the registry so they never drift
// ---------------------------------------------------------------------------

function project<K extends keyof StatusTokens>(field: K): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, tokens] of Object.entries(STATUS_REGISTRY)) {
    out[key] = (tokens as StatusTokens)[field];
  }
  return out;
}

export const statusBadge: Record<string, string> = project("badge");
export const statusBadgeDefault: string = FALLBACK_STATUS_TOKENS.badge;

export const issueStatusIcon: Record<string, string> = project("ring");
export const issueStatusIconDefault: string = FALLBACK_STATUS_TOKENS.ring;

export const issueStatusText: Record<string, string> = project("text");
export const issueStatusTextDefault: string = FALLBACK_STATUS_TOKENS.text;

export const agentStatusDot: Record<string, string> = project("dot");
export const agentStatusDotDefault: string = FALLBACK_STATUS_TOKENS.dot;

export const priorityColor: Record<string, string> = Object.fromEntries(
  Object.entries(PRIORITY_REGISTRY).map(([k, v]) => [k, v.icon]),
);
export const priorityColorDefault: string = FALLBACK_PRIORITY_TOKENS.icon;
