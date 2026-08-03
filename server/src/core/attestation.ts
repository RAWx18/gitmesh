/**
 * Attestation Service
 *
 * Project-scoped Ed25519 signatures over `activity_log` rows. Designed
 * to satisfy the LFDT mentorship verifiable-trust deliverable while
 * staying within Node's built-in `crypto` module (no extra deps).
 *
 * Out of scope (deliberate):
 *   - per-agent identities / DIDs / AnonCreds
 *   - transparency log (Rekor-style) publishing
 *   - cross-project key sharing
 *
 * Design notes:
 *   - Signing is async via the `activity_attestation_queue` sidecar.
 *     Audit-log inserts stay synchronous; missing signatures show up
 *     in the UI as "pending attestation".
 *   - The private key lives in the existing project secret store under
 *     name `_attestation_signing_key`. The public key is plaintext on
 *     `projects.attestationPublicKey` (PEM SPKI).
 */
import {
  generateKeyPairSync,
  createPrivateKey,
  createPublicKey,
  sign as cryptoSign,
  verify as cryptoVerify,
  createHash,
  randomUUID,
} from "node:crypto";
import { eq, and, lte, asc, inArray } from "@gitmesh/data";
import type { Db } from "@gitmesh/data";
import {
  projects,
  activityLog,
  activityAttestations,
  activityAttestationQueue,
} from "@gitmesh/data";
import { secretService } from "./secrets.js";

const SIGNING_KEY_SECRET_NAME = "_attestation_signing_key";
const ATTESTATION_ALG = "ed25519" as const;

export interface AttestationPayload {
  activityId: string;
  agentId: string | null;
  projectId: string;
  policyId: string | null;
  policyVersion: number | null;
  policyOutcome: string | null;
  action: string;
  entityType: string;
  entityId: string;
  timestamp: string;
}

export interface SignedAttestation {
  activityId: string;
  projectId: string;
  signedPayload: string;
  payloadHash: string;
  signature: string;
  signingKeyVersion: number;
  algorithm: string;
}

export interface AttestationVerifyResult {
  valid: boolean;
  reason?: string;
  payload?: AttestationPayload;
  publicKey?: string;
  signingKeyVersion?: number;
}

export function attestationService(db: Db) {
  const secrets = secretService(db);

  /**
   * Idempotently provision the project's signing keypair. Returns the
   * project's current public key + version. Safe to call on every
   * signActivity invocation.
   */
  async function ensureProjectKey(projectId: string): Promise<{
    publicKey: string;
    privateKeyPem: string;
    version: number;
  }> {
    const projectRow = await db
      .select()
      .from(projects)
      .where(eq(projects.id, projectId))
      .then((rows) => rows[0] ?? null);

    if (!projectRow) {
      throw new Error(`attestation: project ${projectId} not found`);
    }

    const existingSecret = await secrets.getByName(projectId, SIGNING_KEY_SECRET_NAME);

    if (projectRow.attestationPublicKey && existingSecret) {
      const privateKeyPem = await secrets.resolveSecretValue(
        projectId,
        existingSecret.id,
        "latest",
      );
      return {
        publicKey: projectRow.attestationPublicKey,
        privateKeyPem,
        version: projectRow.attestationKeyVersion ?? 1,
      };
    }

    // Generate a fresh keypair. Persist the private key in the secret store
    // and the public key on the project row.
    const { publicKey, privateKey } = generateKeyPairSync("ed25519");
    const publicPem = publicKey.export({ format: "pem", type: "spki" }).toString();
    const privatePem = privateKey.export({ format: "pem", type: "pkcs8" }).toString();

    if (existingSecret) {
      await secrets.rotate(existingSecret.id, { value: privatePem });
    } else {
      await secrets.create(projectId, {
        name: SIGNING_KEY_SECRET_NAME,
        provider: "local_encrypted",
        value: privatePem,
        description: "GitMesh attestation signing key (Ed25519). Do not edit by hand.",
      });
    }

    await db
      .update(projects)
      .set({
        attestationPublicKey: publicPem,
        attestationKeyVersion: projectRow.attestationKeyVersion ?? 1,
        updatedAt: new Date(),
      })
      .where(eq(projects.id, projectId));

    return {
      publicKey: publicPem,
      privateKeyPem: privatePem,
      version: projectRow.attestationKeyVersion ?? 1,
    };
  }

  /**
   * Build the canonical payload that gets signed. Order of keys is fixed
   * for byte-stable signatures across language clients.
   */
  function buildPayload(row: typeof activityLog.$inferSelect): AttestationPayload {
    return {
      activityId: row.id,
      agentId: row.agentId,
      projectId: row.projectId,
      policyId: extractPolicyId(row.entityType, row.entityId, row.details),
      policyVersion: row.policyVersion,
      policyOutcome: row.policyOutcome,
      action: row.action,
      entityType: row.entityType,
      entityId: row.entityId,
      timestamp: row.createdAt.toISOString(),
    };
  }

  function canonicalize(payload: AttestationPayload): string {
    // Stable key order - JSON.stringify with explicit key list.
    const ordered: AttestationPayload = {
      activityId: payload.activityId,
      agentId: payload.agentId,
      projectId: payload.projectId,
      policyId: payload.policyId,
      policyVersion: payload.policyVersion,
      policyOutcome: payload.policyOutcome,
      action: payload.action,
      entityType: payload.entityType,
      entityId: payload.entityId,
      timestamp: payload.timestamp,
    };
    return JSON.stringify(ordered);
  }

  async function signActivity(activityId: string): Promise<SignedAttestation | null> {
    const activityRow = await db
      .select()
      .from(activityLog)
      .where(eq(activityLog.id, activityId))
      .then((rows) => rows[0] ?? null);

    if (!activityRow) return null;

    const existing = await db
      .select()
      .from(activityAttestations)
      .where(eq(activityAttestations.activityId, activityId))
      .then((rows) => rows[0] ?? null);
    if (existing) {
      return {
        activityId: existing.activityId,
        projectId: existing.projectId,
        signedPayload: existing.signedPayload,
        payloadHash: existing.payloadHash,
        signature: existing.signature,
        signingKeyVersion: existing.signingKeyVersion,
        algorithm: existing.algorithm,
      };
    }

    const key = await ensureProjectKey(activityRow.projectId);
    const payload = buildPayload(activityRow);
    const canonical = canonicalize(payload);
    const payloadHash = createHash("sha256").update(canonical).digest("hex");
    const privateKey = createPrivateKey({ key: key.privateKeyPem, format: "pem" });
    const signatureBytes = cryptoSign(null, Buffer.from(canonical, "utf8"), privateKey);
    const signature = signatureBytes.toString("base64url");

    const inserted = await db
      .insert(activityAttestations)
      .values({
        id: randomUUID(),
        activityId,
        projectId: activityRow.projectId,
        signingKeyVersion: key.version,
        signedPayload: canonical,
        payloadHash,
        signature,
        algorithm: ATTESTATION_ALG,
      })
      .returning();

    return {
      activityId,
      projectId: activityRow.projectId,
      signedPayload: canonical,
      payloadHash,
      signature,
      signingKeyVersion: inserted[0]?.signingKeyVersion ?? key.version,
      algorithm: ATTESTATION_ALG,
    };
  }

  async function verifyActivity(activityId: string): Promise<AttestationVerifyResult> {
    const attestationRow = await db
      .select()
      .from(activityAttestations)
      .where(eq(activityAttestations.activityId, activityId))
      .then((rows) => rows[0] ?? null);

    if (!attestationRow) {
      return { valid: false, reason: "no attestation found" };
    }

    const projectRow = await db
      .select()
      .from(projects)
      .where(eq(projects.id, attestationRow.projectId))
      .then((rows) => rows[0] ?? null);

    if (!projectRow?.attestationPublicKey) {
      return { valid: false, reason: "project public key missing" };
    }

    const verified = verifySignedPayload(
      attestationRow.signedPayload,
      attestationRow.signature,
      projectRow.attestationPublicKey,
    );

    let parsedPayload: AttestationPayload | undefined;
    try {
      parsedPayload = JSON.parse(attestationRow.signedPayload) as AttestationPayload;
    } catch {
      // leave undefined
    }

    return {
      valid: verified,
      payload: parsedPayload,
      publicKey: projectRow.attestationPublicKey,
      signingKeyVersion: attestationRow.signingKeyVersion,
      reason: verified ? undefined : "signature did not verify",
    };
  }

  async function queueSign(input: { activityId: string; projectId: string }): Promise<void> {
    await db
      .insert(activityAttestationQueue)
      .values({
        id: randomUUID(),
        activityId: input.activityId,
        projectId: input.projectId,
      })
      .onConflictDoNothing();
  }

  async function drainQueueOnce(opts?: { batchSize?: number; maxAttempts?: number }): Promise<{
    signed: number;
    failed: number;
  }> {
    const batchSize = opts?.batchSize ?? 32;
    const maxAttempts = opts?.maxAttempts ?? 5;
    const now = new Date();

    const pending = await db
      .select()
      .from(activityAttestationQueue)
      .where(lte(activityAttestationQueue.nextAttemptAt, now))
      .orderBy(asc(activityAttestationQueue.nextAttemptAt))
      .limit(batchSize);

    let signed = 0;
    let failed = 0;

    for (const row of pending) {
      try {
        await signActivity(row.activityId);
        await db.delete(activityAttestationQueue).where(eq(activityAttestationQueue.id, row.id));
        signed += 1;
      } catch (err) {
        failed += 1;
        const message = err instanceof Error ? err.message : String(err);
        const attempts = (row.attempts ?? 0) + 1;
        const giveUp = attempts >= maxAttempts;
        if (giveUp) {
          await db.delete(activityAttestationQueue).where(eq(activityAttestationQueue.id, row.id));
        } else {
          await db
            .update(activityAttestationQueue)
            .set({
              attempts,
              lastError: message,
              nextAttemptAt: new Date(Date.now() + Math.min(60_000, 2 ** attempts * 1_000)),
            })
            .where(eq(activityAttestationQueue.id, row.id));
        }
      }
    }

    return { signed, failed };
  }

  /**
   * Start a polling worker that drains the queue every `intervalMs`.
   * Returns a stop function.
   */
  function startWorker(opts?: { intervalMs?: number }): () => void {
    const intervalMs = opts?.intervalMs ?? 1_500;
    let stopped = false;
    let timer: NodeJS.Timeout | null = null;

    async function tick() {
      if (stopped) return;
      try {
        await drainQueueOnce();
      } catch (err) {
        // Workers must not crash the process.
        // eslint-disable-next-line no-console
        console.warn("[attestation] worker tick failed:", err instanceof Error ? err.message : err);
      }
      if (!stopped) {
        timer = setTimeout(tick, intervalMs);
        timer.unref?.();
      }
    }

    timer = setTimeout(tick, intervalMs);
    timer.unref?.();

    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }

  async function getProjectPublicKey(projectId: string): Promise<{
    publicKey: string;
    keyVersion: number;
  } | null> {
    const projectRow = await db
      .select()
      .from(projects)
      .where(eq(projects.id, projectId))
      .then((rows) => rows[0] ?? null);
    if (!projectRow?.attestationPublicKey) return null;
    return {
      publicKey: projectRow.attestationPublicKey,
      keyVersion: projectRow.attestationKeyVersion ?? 1,
    };
  }

  async function getAttestationByActivityId(
    activityId: string,
  ): Promise<{
    activityId: string;
    projectId: string;
    signedPayload: string;
    payloadHash: string;
    signature: string;
    signingKeyVersion: number;
    algorithm: string;
    createdAt: string;
  } | null> {
    const row = await db
      .select()
      .from(activityAttestations)
      .where(eq(activityAttestations.activityId, activityId))
      .then((rows) => rows[0] ?? null);
    if (!row) return null;
    return {
      activityId: row.activityId,
      projectId: row.projectId,
      signedPayload: row.signedPayload,
      payloadHash: row.payloadHash,
      signature: row.signature,
      signingKeyVersion: row.signingKeyVersion,
      algorithm: row.algorithm,
      createdAt: row.createdAt.toISOString(),
    };
  }

  async function isAttestationPending(activityId: string): Promise<boolean> {
    const row = await db
      .select()
      .from(activityAttestationQueue)
      .where(eq(activityAttestationQueue.activityId, activityId))
      .then((rows) => rows[0] ?? null);
    return Boolean(row);
  }

  /**
   * Bulk status lookup so the operator timeline can fetch attestation
   * state for an entire activity batch in a single round-trip instead
   * of N per-row 404s. Activities outside `projectId` are reported as
   * `missing` rather than leaking cross-project existence.
   */
  async function getBulkStatus(
    projectId: string,
    activityIds: string[],
  ): Promise<Record<string, "attested" | "pending" | "missing">> {
    const result: Record<string, "attested" | "pending" | "missing"> = {};
    if (activityIds.length === 0) return result;

    const unique = Array.from(new Set(activityIds));
    for (const id of unique) result[id] = "missing";

    const attestedRows = await db
      .select({
        activityId: activityAttestations.activityId,
        projectId: activityAttestations.projectId,
      })
      .from(activityAttestations)
      .where(
        and(
          eq(activityAttestations.projectId, projectId),
          inArray(activityAttestations.activityId, unique),
        ),
      );
    for (const row of attestedRows) result[row.activityId] = "attested";

    const stillUnknown = unique.filter((id) => result[id] === "missing");
    if (stillUnknown.length > 0) {
      const queuedRows = await db
        .select({
          activityId: activityAttestationQueue.activityId,
          projectId: activityAttestationQueue.projectId,
        })
        .from(activityAttestationQueue)
        .where(
          and(
            eq(activityAttestationQueue.projectId, projectId),
            inArray(activityAttestationQueue.activityId, stillUnknown),
          ),
        );
      for (const row of queuedRows) result[row.activityId] = "pending";
    }

    return result;
  }

  return {
    ensureProjectKey,
    signActivity,
    verifyActivity,
    queueSign,
    drainQueueOnce,
    startWorker,
    getProjectPublicKey,
    getAttestationByActivityId,
    isAttestationPending,
    getBulkStatus,
  };
}

/**
 * Pure verification helper. Used by both the server and the CLI's
 * `attest verify` subcommand - same code, no DB.
 */
export function verifySignedPayload(
  signedPayload: string,
  signatureBase64Url: string,
  publicKeyPem: string,
): boolean {
  try {
    const publicKey = createPublicKey({ key: publicKeyPem, format: "pem" });
    const signatureBuf = Buffer.from(signatureBase64Url, "base64url");
    const messageBuf = Buffer.from(signedPayload, "utf8");
    return cryptoVerify(null, messageBuf, publicKey, signatureBuf);
  } catch {
    return false;
  }
}

function extractPolicyId(
  entityType: string,
  entityId: string,
  details: Record<string, unknown> | null,
): string | null {
  if (entityType === "agent_policy") return entityId;
  if (entityType === "policy_evaluation" && entityId !== "default") return entityId;
  if (details && typeof (details as { policyId?: unknown }).policyId === "string") {
    return String((details as { policyId?: unknown }).policyId);
  }
  return null;
}

const _ALG = ATTESTATION_ALG;
export { _ALG as ATTESTATION_ALGORITHM };
