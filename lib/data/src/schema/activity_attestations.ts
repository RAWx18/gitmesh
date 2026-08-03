import { pgTable, uuid, text, timestamp, integer, index, uniqueIndex } from "drizzle-orm/pg-core";
import { projects } from "./projects.js";
import { activityLog } from "./activity_log.js";

/**
 * Cryptographic attestations sidecar for `activity_log`.
 *
 * Each row carries a project-scoped Ed25519 signature over a canonical
 * JSON payload (the "attested fact" the public verification endpoint
 * exposes). Sidecar rather than column so:
 *   - the audit-log insert path remains synchronous and signature-free
 *   - signature absence vs failure is distinguishable
 *   - rotation and re-signing live in their own table
 */
export const activityAttestations = pgTable(
  "activity_attestations",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    activityId: uuid("activity_id")
      .notNull()
      .references(() => activityLog.id, { onDelete: "cascade" }),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    signingKeyVersion: integer("signing_key_version").notNull(),
    /** Canonical JSON of (actionId, agentId, projectId, policyId, policyVersion, policyOutcome, timestamp, payloadHash) */
    signedPayload: text("signed_payload").notNull(),
    /** sha256(signedPayload) - hex */
    payloadHash: text("payload_hash").notNull(),
    /** base64url Ed25519 signature over the payload bytes */
    signature: text("signature").notNull(),
    /** Algorithm identifier; reserved for future rotation to a new alg. */
    algorithm: text("algorithm").notNull().default("ed25519"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    uniqByActivity: uniqueIndex("activity_attestations_activity_uniq").on(table.activityId),
    byProject: index("activity_attestations_project_created_idx").on(table.projectId, table.createdAt),
  }),
);

/**
 * Pending-sign queue for the attestation worker. Rows are inserted by
 * `logActivity()` and drained by a background worker; the worker
 * deletes the queue row after it writes the corresponding
 * `activity_attestations` row.
 */
export const activityAttestationQueue = pgTable(
  "activity_attestation_queue",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    activityId: uuid("activity_id")
      .notNull()
      .references(() => activityLog.id, { onDelete: "cascade" }),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    attempts: integer("attempts").notNull().default(0),
    lastError: text("last_error"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    nextAttemptAt: timestamp("next_attempt_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (table) => ({
    uniqByActivity: uniqueIndex("activity_attestation_queue_activity_uniq").on(table.activityId),
    byNext: index("activity_attestation_queue_next_idx").on(table.nextAttemptAt),
  }),
);
