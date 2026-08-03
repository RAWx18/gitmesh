import { pgTable, uuid, text, timestamp, jsonb, integer, boolean, index, uniqueIndex } from "drizzle-orm/pg-core";
import { projects } from "./projects.js";

/**
 * Defines governance policies for agent actions within a project.
 * Policies can allow, block, or require approval for specific actions
 * based on configurable rules and conditions.
 */
export const agentPolicies = pgTable(
  "agent_policies",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    projectId: uuid("project_id").notNull().references(() => projects.id),
    /** Human-readable policy name */
    name: text("name").notNull(),
    /** Detailed description of what this policy does */
    description: text("description"),
    /** Policy version - incremented on each update */
    version: integer("version").notNull().default(1),
    /** Whether this policy is currently active */
    enabled: boolean("enabled").notNull().default(true),
    /** Priority for evaluation order (lower = evaluated first) */
    priority: integer("priority").notNull().default(100),
    /**
     * Action pattern this policy applies to (glob-style or exact match).
     * e.g., "merge_pr", "close_issue", "publish_advisory", "*"
     */
    actionPattern: text("action_pattern").notNull(),
    /**
     * Conditions that must be true for this policy to apply.
     * JSON structure with field matchers, e.g.:
     * { "agentRole": ["security"], "targetBranch": ["main", "release/*"] }
     */
    conditions: jsonb("conditions").$type<Record<string, unknown>>(),
    /**
     * Policy effect: what happens when this policy matches.
     * - allow: action is permitted
     * - block: action is denied
     * - require_approval: action requires human approval before proceeding
     */
    effect: text("effect").notNull().default("allow"),
    /**
     * Optional configuration for the effect.
     * For require_approval: { "approverRoles": ["maintainer"], "timeout": "24h" }
     * For block: { "message": "Reason for blocking" }
     */
    effectConfig: jsonb("effect_config").$type<Record<string, unknown>>(),
    /** Who created this policy */
    createdByUserId: text("created_by_user_id"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    projectEnabledPriorityIdx: index("agent_policies_project_enabled_priority_idx").on(
      table.projectId,
      table.enabled,
      table.priority,
    ),
    projectActionIdx: index("agent_policies_project_action_idx").on(
      table.projectId,
      table.actionPattern,
    ),
    projectNameVersionIdx: uniqueIndex("agent_policies_project_name_version_idx").on(
      table.projectId,
      table.name,
      table.version,
    ),
  }),
);
