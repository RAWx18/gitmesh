import { pgTable, uuid, text, timestamp, boolean, index } from "drizzle-orm/pg-core";
import { projects } from "./projects.js";
import { authUsers } from "./auth.js";

/**
 * Stores push notification tokens for users across devices.
 * Used for sending mobile push notifications for approvals and other events.
 */
export const userPushNotificationTokens = pgTable(
  "user_push_notification_tokens",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: text("user_id").notNull().references(() => authUsers.id),
    projectId: uuid("project_id").notNull().references(() => projects.id),
    /** Push provider: fcm (Firebase Cloud Messaging) or apns (Apple Push) */
    provider: text("provider").notNull().default("fcm"),
    /** The device token / endpoint */
    token: text("token").notNull(),
    /** Human-readable device name for management UI */
    deviceName: text("device_name"),
    /** Whether notifications are enabled for this token */
    enabled: boolean("enabled").notNull().default(true),
    /** Last time a notification was sent to this token */
    lastNotifiedAt: timestamp("last_notified_at", { withTimezone: true }),
    /** When this token was registered */
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    userProjectIdx: index("push_tokens_user_project_idx").on(table.userId, table.projectId),
    tokenIdx: index("push_tokens_token_idx").on(table.token),
    userEnabledIdx: index("push_tokens_user_enabled_idx").on(table.userId, table.enabled),
  }),
);
