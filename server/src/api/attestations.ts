/**
 * Attestation Routes
 *
 * Public verification endpoints. These routes deliberately do NOT call
 * `assertBoard()` / `assertProjectAccess()`: they expose only signed
 * payloads + the project's public key. A consumer can verify the
 * signature with no GitMesh credentials, e.g. directly from a CI script.
 *
 * The attestation contains exactly the canonical fact GitMesh signed:
 *   { activityId, agentId, projectId, policyId, policyVersion,
 *     policyOutcome, action, entityType, entityId, timestamp }
 * which is the operator-visible audit fact, not adapter logs or PII.
 */
import { Router } from "express";
import type { Db } from "@gitmesh/data";
import { attestationService } from "../core/attestation.js";

export function attestationRoutes(db: Db) {
  const router = Router();
  const svc = attestationService(db);

  router.get("/projects/:projectId/attestations/public-key", async (req, res) => {
    const projectId = req.params.projectId as string;
    const key = await svc.getProjectPublicKey(projectId);
    if (!key) {
      res.status(404).json({ error: "Project public key not yet provisioned" });
      return;
    }
    res.json({
      projectId,
      algorithm: "ed25519",
      publicKey: key.publicKey,
      keyVersion: key.keyVersion,
    });
  });

  router.post("/projects/:projectId/attestations/status", async (req, res) => {
    const projectId = req.params.projectId as string;
    const body = req.body as { activityIds?: unknown };
    const ids = Array.isArray(body?.activityIds)
      ? body.activityIds.filter((v): v is string => typeof v === "string")
      : null;
    if (!ids) {
      res.status(400).json({ error: "activityIds must be an array of strings" });
      return;
    }
    if (ids.length > 500) {
      res.status(422).json({ error: "activityIds limited to 500 per request" });
      return;
    }
    const statuses = await svc.getBulkStatus(projectId, ids);
    res.json({ statuses });
  });

  router.get("/projects/:projectId/attestations/:activityId", async (req, res) => {
    const projectId = req.params.projectId as string;
    const activityId = req.params.activityId as string;

    const attestation = await svc.getAttestationByActivityId(activityId);
    if (!attestation) {
      const pending = await svc.isAttestationPending(activityId);
      res.status(404).json({
        error: pending ? "attestation pending" : "attestation not found",
        pending,
      });
      return;
    }

    if (attestation.projectId !== projectId) {
      res.status(404).json({ error: "attestation not found in this project" });
      return;
    }

    const key = await svc.getProjectPublicKey(projectId);
    if (!key) {
      res.status(500).json({ error: "Project public key missing" });
      return;
    }

    res.json({
      activityId: attestation.activityId,
      projectId: attestation.projectId,
      algorithm: attestation.algorithm,
      signedPayload: attestation.signedPayload,
      payloadHash: attestation.payloadHash,
      signature: attestation.signature,
      signingKeyVersion: attestation.signingKeyVersion,
      createdAt: attestation.createdAt,
      publicKey: key.publicKey,
      verifyInstructions: [
        "1. Compute sha256 of `signedPayload` and confirm it matches `payloadHash` (hex).",
        "2. Verify Ed25519 `signature` (base64url) over `signedPayload` (utf-8 bytes) using `publicKey` (PEM SPKI).",
        "3. The signed payload includes the canonical audit fact for this activity row.",
      ],
    });
  });

  return router;
}
