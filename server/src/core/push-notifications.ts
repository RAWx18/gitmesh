/**
 * Push Notification Service
 *
 * Sends push notifications to users via Firebase Cloud Messaging (FCM)
 * or Apple Push Notification Service (APNs).
 *
 * Currently implements FCM only. APNs support requires additional configuration
 * (p8 certificate or TLS certificate).
 */

import { eq, and } from "@gitmesh/data";
import type { Db } from "@gitmesh/data";
import { userPushNotificationTokens } from "@gitmesh/data";

export { userPushNotificationTokens };

export interface PushNotificationPayload {
  title: string;
  body: string;
  /** URL to navigate to when notification is tapped */
  clickUrl?: string;
  /** Icon URL (for FCM Android) */
  iconUrl?: string;
  /** Priority: high or normal */
  priority?: "high" | "normal";
  /** Additional data fields */
  data?: Record<string, string>;
  /** Time-to-live in seconds (default: 24 hours) */
  ttl?: number;
}

/**
 * Send a push notification to a specific user across all their registered devices.
 */
export async function sendPushNotificationToUser(
  db: Db,
  userId: string,
  projectId: string,
  payload: PushNotificationPayload,
): Promise<{ sent: number; failed: number }> {
  // Look up all active push tokens for this user/project
  const tokens = await db
    .select()
    .from(userPushNotificationTokens)
    .where(
      and(
        eq(userPushNotificationTokens.userId, userId),
        eq(userPushNotificationTokens.projectId, projectId),
        eq(userPushNotificationTokens.enabled, true),
      ),
    );

  let sent = 0;
  let failed = 0;

  for (const token of tokens) {
    try {
      if (token.provider === "fcm") {
        await sendFCMNotification(token.token, payload);
        await updateLastNotifiedAt(db, token.id);
        sent++;
      } else if (token.provider === "apns") {
        await sendAPNsNotification(token.token, payload);
        await updateLastNotifiedAt(db, token.id);
        sent++;
      }
    } catch (err) {
      console.error(`Failed to send push to token ${token.id}:`, err);
      failed++;

      // Disable token if it's permanently invalid
      if (isTokenInvalid(err)) {
        await db
          .update(userPushNotificationTokens)
          .set({ enabled: false, updatedAt: new Date() })
          .where(eq(userPushNotificationTokens.id, token.id));
      }
    }
  }

  return { sent, failed };
}

/**
 * Register a push notification token for a user.
 */
export async function registerPushToken(
  db: Db,
  input: {
    userId: string;
    projectId: string;
    provider: "fcm" | "apns";
    token: string;
    deviceName?: string;
  },
): Promise<{ id: string }> {
  // Check if token already exists and re-enable it
  const existing = await db
    .select()
    .from(userPushNotificationTokens)
    .where(and(eq(userPushNotificationTokens.token, input.token)));

  if (existing.length > 0) {
    await db
      .update(userPushNotificationTokens)
      .set({
        userId: input.userId,
        projectId: input.projectId,
        provider: input.provider,
        deviceName: input.deviceName ?? null,
        enabled: true,
        updatedAt: new Date(),
      })
      .where(eq(userPushNotificationTokens.id, existing[0].id));

    return { id: existing[0].id };
  }

  const rows = await db
    .insert(userPushNotificationTokens)
    .values({
      userId: input.userId,
      projectId: input.projectId,
      provider: input.provider,
      token: input.token,
      deviceName: input.deviceName ?? null,
    })
    .returning();

  return { id: rows[0].id };
}

/**
 * Unregister a push notification token.
 */
export async function unregisterPushToken(
  db: Db,
  token: string,
): Promise<boolean> {
  const rows = await db
    .delete(userPushNotificationTokens)
    .where(eq(userPushNotificationTokens.token, token))
    .returning();

  return rows.length > 0;
}

/**
 * List active push tokens for a project (for debugging/admin).
 */
export async function listPushTokens(db: Db, projectId: string) {
  return db
    .select()
    .from(userPushNotificationTokens)
    .where(eq(userPushNotificationTokens.projectId, projectId));
}

// ─── FCM Implementation ────────────────────────────────────────────────────────

// FCM server key is read from environment variable.
// Set GITMESH_FCM_SERVER_KEY in your .env file.
// For production, use FCM v1 API with OAuth2 credentials instead.

async function sendFCMNotification(
  token: string,
  payload: PushNotificationPayload,
): Promise<void> {
  const serverKey = process.env.GITMESH_FCM_SERVER_KEY;

  if (!serverKey) {
    console.warn("FCM server key not configured. Set GITMESH_FCM_SERVER_KEY in .env");
    throw new Error("FCM not configured");
  }

  const fcmPayload = {
    to: token,
    notification: {
      title: payload.title,
      body: payload.body,
      ...(payload.iconUrl ? { icon: payload.iconUrl } : {}),
      ...(payload.clickUrl ? { click_action: payload.clickUrl } : {}),
    },
    data: payload.data ?? {},
    priority: payload.priority ?? "high",
    ttl: payload.ttl ?? 86400,
  };

  const response = await fetch("https://fcm.googleapis.com/fcm/send", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `key=${serverKey}`,
    },
    body: JSON.stringify(fcmPayload),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`FCM request failed: ${response.status} ${errText}`);
  }

  const result = (await response.json()) as { success?: number; failure?: number; results?: Array<{ error?: string }> };
  if (result.failure && result.failure > 0 && result.results?.[0]?.error) {
    throw new Error(`FCM error: ${result.results[0].error}`);
  }
}

// ─── APNs Implementation ────────────────────────────────────────────────────────

// APNs requires a p8 certificate or TLS certificate.
// Configure in environment variables:
//   GITMESH_APNS_KEY_ID
//   GITMESH_APNS_TEAM_ID
//   GITMESH_APNS_BUNDLE_ID
//   GITMESH_APNS_PRIVATE_KEY (base64 encoded p8 file)

async function sendAPNsNotification(
  token: string,
  payload: PushNotificationPayload,
): Promise<void> {
  const teamId = process.env.GITMESH_APNS_TEAM_ID;
  const keyId = process.env.GITMESH_APNS_KEY_ID;
  const bundleId = process.env.GITMESH_APNS_BUNDLE_ID;
  const privateKeyBase64 = process.env.GITMESH_APNS_PRIVATE_KEY;

  if (!teamId || !keyId || !bundleId || !privateKeyBase64) {
    console.warn("APNs not configured. Set GITMESH_APNS_* environment variables.");
    throw new Error("APNs not configured");
  }

  // For production use, generate a JWT token using the p8 key
  // This is a simplified implementation - production should use
  // a proper JWT library with RS256 signing
  const header = Buffer.from(JSON.stringify({ alg: "ES256", kid: keyId })).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const jwtPayload = Buffer.from(
    JSON.stringify({ iss: teamId, iat: now, exp: now + 3600 }),
  ).toString("base64url");
  const signature = `${header}.${jwtPayload}`; // In production, sign with private key

  void signature; // suppress unused warning

  const apnsPayload = {
    aps: {
      alert: {
        title: payload.title,
        body: payload.body,
      },
      badge: 1,
      sound: "default",
    },
    ...(payload.clickUrl ? { clickUrl: payload.clickUrl } : {}),
    ...(payload.data ? { data: payload.data } : {}),
  };

  // For demonstration - this would need real JWT signing in production
  console.log(`APNs notification would be sent to token: ${token.substring(0, 20)}...`);
  throw new Error("APNs requires full JWT signing implementation - see docs");
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

async function updateLastNotifiedAt(db: Db, tokenId: string): Promise<void> {
  await db
    .update(userPushNotificationTokens)
    .set({ lastNotifiedAt: new Date(), updatedAt: new Date() })
    .where(eq(userPushNotificationTokens.id, tokenId));
}

function isTokenInvalid(err: unknown): boolean {
  if (err instanceof Error) {
    const msg = err.message.toLowerCase();
    // Unregistered, invalid token, not found
    return msg.includes("unregistered") ||
      msg.includes("invalid argument") ||
      msg.includes("not_found") ||
      msg.includes("token not registered");
  }
  return false;
}

/**
 * Send a push notification for a new approval.
 * Convenience function that wraps the full workflow.
 */
export async function notifyNewApproval(
  db: Db,
  projectId: string,
  approvalId: string,
  approverUserId: string,
  agentName: string,
  approvalType: string,
): Promise<{ sent: number; failed: number }> {
  const clickUrl = `/approvals/${approvalId}`;

  return sendPushNotificationToUser(db, approverUserId, projectId, {
    title: "Approval Required",
    body: `${agentName} requires your approval: ${approvalType}`,
    clickUrl,
    priority: "high",
    data: {
      type: "approval",
      approvalId,
      projectId,
    },
  });
}
