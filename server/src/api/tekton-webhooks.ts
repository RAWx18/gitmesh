/**
 * Tekton Webhook Routes
 *
 * Handles incoming webhook events from Tekton CI/CD pipelines.
 * Stores results, triggers agent wakeups, and enforces policy gates.
 *
 * Routes:
 * - POST /api/forge/webhook/tekton  - receive Tekton PipelineRun/TaskRun webhooks
 */

import { Router } from "express";
import type { Db } from "@gitmesh/data";
import { eq, and, forgeWebhooks, projects } from "@gitmesh/data";
import { logActivity, policyEngineService } from "../core/index.js";

export function tektonWebhookRoutes(db: Db) {
    const router = Router();

    /**
     * POST /api/forge/webhook/tekton
     * Handle incoming Tekton CloudEvent / webhook payloads.
     *
     * Tekton sends CloudEvents when PipelineRuns/TaskRuns complete.
     * Expected payload structure (CloudEvent envelope):
     * {
     *   type: "dev.tekton.event.pipelinerun.successful" | "...failed" | etc.
     *   source: "/tekton/...",
     *   data: {
     *     pipelineRun: { metadata: { name, labels, annotations }, status: ... }
     *   }
     * }
     */
    router.post("/forge/webhook/tekton", async (req, res) => {
        try {
            const payload = req.body as Record<string, unknown>;

            // Parse CloudEvent headers or body
            const ceType = (req.headers["ce-type"] as string) ?? (payload.type as string) ?? "";
            const ceSource = (req.headers["ce-source"] as string) ?? (payload.source as string) ?? "";
            const data = (payload.data as Record<string, unknown>) ?? payload;

            // Extract pipeline/task info
            const pipelineRun = (data.pipelineRun ?? data.taskRun ?? data) as Record<string, unknown>;
            const metadata = (pipelineRun.metadata ?? {}) as Record<string, unknown>;
            const labels = (metadata.labels ?? {}) as Record<string, string>;
            const annotations = (metadata.annotations ?? {}) as Record<string, string>;
            const status = (pipelineRun.status ?? {}) as Record<string, unknown>;

            // Resolve project
            const projectId = labels["gitmesh.io/project-id"]
                ?? annotations["gitmesh.io/project-id"]
                ?? await resolveProjectFromTekton(db, labels, annotations);

            if (!projectId) {
                res.status(200).json({ ignored: true, reason: "No project mapping found" });
                return;
            }

            // Determine status
            const pipelineStatus = deriveTektonStatus(ceType, status);
            const pipelineName = (metadata.name as string) ?? "unknown-pipeline";
            const logsUrl = annotations["tekton.dev/log-url"] ?? annotations["dashboard.tekton.dev/url"] ?? null;

            // Store webhook delivery
            await storeTektonDelivery(db, projectId, payload, "received");

            // Log activity
            await logActivity(db, {
                projectId,
                actorType: "system",
                actorId: "tekton",
                action: "ci_result",
                entityType: "pipeline_run",
                entityId: pipelineName,
                details: {
                    pipeline: pipelineName,
                    status: pipelineStatus,
                    logsUrl,
                    ceType,
                    ceSource,
                },
            });

            // If failure + policy rule exists for blocking merges on CI failure,
            // evaluate the policy and create an approval requirement if needed
            if (pipelineStatus === "failed") {
                const policyEngine = policyEngineService(db);

                try {
                    const policyResult = await policyEngine.evaluate({
                        projectId,
                        agentId: "tekton-ci",
                        action: "ci_failed",
                        context: {
                            pipeline: pipelineName,
                            status: pipelineStatus,
                            ceType,
                        },
                    });

                    if (policyResult.effect === "block") {
                        await logActivity(db, {
                            projectId,
                            actorType: "system",
                            actorId: "tekton",
                            action: "ci_merge_blocked",
                            entityType: "pipeline_run",
                            entityId: pipelineName,
                            details: {
                                reason: policyResult.reason,
                                policyName: policyResult.policyName,
                                policyVersion: policyResult.policyVersion,
                                policyOutcome: "block",
                            },
                        });
                    }
                } catch {
                    // Policy evaluation failure should not block webhook processing
                }
            }

            await storeTektonDelivery(db, projectId, payload, "processed");

            res.json({
                ok: true,
                pipeline: pipelineName,
                status: pipelineStatus,
            });
        } catch (error) {
            console.error("Tekton webhook processing error:", error);
            res.status(500).json({ error: "Tekton webhook processing failed" });
        }
    });

    return router;
}

/**
 * Map Tekton CloudEvent type or status to a simple status string.
 */
function deriveTektonStatus(
    ceType: string,
    status: Record<string, unknown>,
): "succeeded" | "failed" | "running" | "unknown" {
    // CloudEvent type-based
    if (ceType.includes("successful") || ceType.includes("done")) return "succeeded";
    if (ceType.includes("failed")) return "failed";
    if (ceType.includes("started") || ceType.includes("running")) return "running";

    // Status conditions-based (Tekton uses Kubernetes-style conditions)
    const conditions = (status.conditions ?? []) as Array<Record<string, unknown>>;
    for (const cond of conditions) {
        if (cond.type === "Succeeded") {
            if (cond.status === "True") return "succeeded";
            if (cond.status === "False") return "failed";
            return "running";
        }
    }

    return "unknown";
}

/**
 * Try to resolve a project from Tekton labels/annotations
 * by matching repo URLs or project names.
 */
async function resolveProjectFromTekton(
    db: Db,
    labels: Record<string, string>,
    annotations: Record<string, string>,
): Promise<string | null> {
    // Try by repo URL annotation
    const repoUrl = annotations["tekton.dev/git-url"]
        ?? annotations["pipelinesascode.tekton.dev/repo-url"]
        ?? labels["triggers.tekton.dev/repo-url"];

    if (repoUrl) {
        const rows = await db
            .select({ id: projects.id })
            .from(projects)
            .where(eq(projects.repoUrl, repoUrl));

        if (rows.length > 0) return rows[0].id;
    }

    return null;
}

/**
 * Store Tekton webhook delivery in forge_webhooks table.
 */
async function storeTektonDelivery(
    db: Db,
    projectId: string,
    payload: Record<string, unknown>,
    status: "received" | "processed" | "failed",
) {
    const rows = await db
        .select({ id: forgeWebhooks.id })
        .from(forgeWebhooks)
        .where(
            and(
                eq(forgeWebhooks.projectId, projectId),
                eq(forgeWebhooks.forgeProvider, "tekton"),
                eq(forgeWebhooks.active, true),
            ),
        );

    if (rows.length === 0) return;

    await db
        .update(forgeWebhooks)
        .set({
            rawPayload: JSON.stringify(payload),
            deliveryStatus: status,
            lastDeliveredAt: status === "processed" ? new Date() : undefined,
            updatedAt: new Date(),
        })
        .where(eq(forgeWebhooks.id, rows[0].id));
}
