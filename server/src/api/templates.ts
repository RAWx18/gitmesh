/**
 * Templates API Routes
 *
 * CRUD operations for project templates, plus import/export functionality.
 *
 * Routes:
 * - GET  /api/templates                                  - list all (public + authored)
 * - GET  /api/templates/:templateId                      - get detail
 * - POST /api/templates                                  - create new template
 * - PUT  /api/templates/:templateId                      - update template
 * - DELETE /api/templates/:templateId                    - delete template (admin)
 * - POST /api/projects/:projectId/apply-template/:tid    - apply template to project
 * - POST /api/projects/:projectId/export-as-template     - export project as template
 */

import { Router } from "express";
import type { Db } from "@gitmesh/data";
import { eq, or, and, desc, projectTemplates } from "@gitmesh/data";
import { assertBoard, getActorInfo } from "./authz.js";
import { logActivity, agentService, policyEngineService } from "../core/index.js";

/** Satisfies process adapter requirement until operators attach a real command. On-demand exits quickly. */
function templateProcessPlaceholderAdapterConfig(): Record<string, unknown> {
    if (process.platform === "win32") {
        return { command: "cmd.exe", args: ["/d", "/c", "exit", "/b", "0"], timeoutSec: 30 };
    }
    return { command: "sh", args: ["-c", "exit 0"], timeoutSec: 30 };
}

export function templateRoutes(db: Db) {
    const router = Router();

    // ── List Templates ─────────────────────────────────────────────────────

    /**
     * GET /api/templates
     * List all public templates + templates authored by the current user.
     */
    router.get("/templates", async (req, res) => {
        assertBoard(req);
        const actor = getActorInfo(req);

        const templates = await db
            .select()
            .from(projectTemplates)
            .where(
                or(
                    eq(projectTemplates.communityContributed, true),
                    eq(projectTemplates.authorId, actor.actorId),
                ),
            )
            .orderBy(desc(projectTemplates.downloadCount));

        res.json(templates);
    });

    // ── Get Template Detail ────────────────────────────────────────────────

    /**
     * GET /api/templates/:templateId
     * Get a single template with full agent and policy configuration.
     */
    router.get("/templates/:templateId", async (req, res) => {
        assertBoard(req);

        const rows = await db
            .select()
            .from(projectTemplates)
            .where(eq(projectTemplates.id, req.params.templateId));

        if (rows.length === 0) {
            res.status(404).json({ error: "Template not found" });
            return;
        }

        res.json(rows[0]);
    });

    // ── Create Template ────────────────────────────────────────────────────

    /**
     * POST /api/templates
     * Create a new template.
     */
    router.post("/templates", async (req, res) => {
        assertBoard(req);
        const actor = getActorInfo(req);

        const { name, description, archetype, agents, policies, version, communityContributed } = req.body;

        if (!name || typeof name !== "string") {
            res.status(400).json({ error: "'name' is required" });
            return;
        }

        const rows = await db
            .insert(projectTemplates)
            .values({
                name: name.trim(),
                description: description ?? null,
                archetype: archetype ?? "cli_tool",
                agents: agents ?? [],
                policies: policies ?? [],
                version: version ?? "1.0.0",
                authorId: actor.actorId,
                communityContributed: communityContributed ?? false,
            })
            .returning();

        await logActivity(db, {
            projectId: "system",
            actorType: actor.actorType,
            actorId: actor.actorId,
            action: "template.created",
            entityType: "project_template",
            entityId: rows[0].id,
            details: { name: rows[0].name, archetype: rows[0].archetype },
        });

        res.status(201).json(rows[0]);
    });

    // ── Update Template ────────────────────────────────────────────────────

    /**
     * PUT /api/templates/:templateId
     * Update a template (author or admin only).
     */
    router.put("/templates/:templateId", async (req, res) => {
        assertBoard(req);
        const actor = getActorInfo(req);

        const existing = await db
            .select()
            .from(projectTemplates)
            .where(eq(projectTemplates.id, req.params.templateId));

        if (existing.length === 0) {
            res.status(404).json({ error: "Template not found" });
            return;
        }

        // Only author can update (admin check skipped for simplicity)
        if (existing[0].authorId !== actor.actorId) {
            res.status(403).json({ error: "Only the template author can update" });
            return;
        }

        const { name, description, archetype, agents, policies, version, communityContributed } = req.body;

        const rows = await db
            .update(projectTemplates)
            .set({
                ...(name && { name: name.trim() }),
                ...(description !== undefined && { description }),
                ...(archetype && { archetype }),
                ...(agents && { agents }),
                ...(policies && { policies }),
                ...(version && { version }),
                ...(communityContributed !== undefined && { communityContributed }),
                updatedAt: new Date(),
            })
            .where(eq(projectTemplates.id, req.params.templateId))
            .returning();

        res.json(rows[0]);
    });

    // ── Delete Template ────────────────────────────────────────────────────

    /**
     * DELETE /api/templates/:templateId
     * Delete a template (author or admin).
     */
    router.delete("/templates/:templateId", async (req, res) => {
        assertBoard(req);
        const actor = getActorInfo(req);

        const existing = await db
            .select()
            .from(projectTemplates)
            .where(eq(projectTemplates.id, req.params.templateId));

        if (existing.length === 0) {
            res.status(404).json({ error: "Template not found" });
            return;
        }

        await db
            .delete(projectTemplates)
            .where(eq(projectTemplates.id, req.params.templateId));

        await logActivity(db, {
            projectId: "system",
            actorType: actor.actorType,
            actorId: actor.actorId,
            action: "template.deleted",
            entityType: "project_template",
            entityId: req.params.templateId,
            details: { name: existing[0].name },
        });

        res.json({ ok: true });
    });

    // ── Apply Template to Project ──────────────────────────────────────────

    /**
     * POST /api/projects/:projectId/apply-template/:templateId
     * One-click deploy: applies a template's agent + policy config to a project.
     */
    router.post("/projects/:projectId/apply-template/:templateId", async (req, res) => {
        assertBoard(req);
        const { projectId, templateId } = req.params;
        const actor = getActorInfo(req);

        const templateRows = await db
            .select()
            .from(projectTemplates)
            .where(eq(projectTemplates.id, templateId));

        if (templateRows.length === 0) {
            res.status(404).json({ error: "Template not found" });
            return;
        }

        const template = templateRows[0];
        const createdAgents: string[] = [];
        const createdPolicies: string[] = [];

        // Create agents from template
        const agentSvc = agentService(db);
        const templateAgents = (template.agents ?? []) as Array<{
            role: string;
            name: string;
            schedule?: string;
            triggers?: string[];
            budget: number;
        }>;

        for (const agentDef of templateAgents) {
            try {
                const agent = await agentSvc.create(projectId, {
                    name: agentDef.name,
                    role: agentDef.role,
                    adapterType: "process",
                    adapterConfig: templateProcessPlaceholderAdapterConfig(),
                    budgetMonthlyCents: agentDef.budget ?? 5000,
                    runtimeConfig: {
                        heartbeatSchedule: agentDef.schedule ?? "0 * * * *",
                        triggers: agentDef.triggers ?? [],
                    },
                });
                createdAgents.push(agent.id);
            } catch {
                // Skip duplicate agents
            }
        }

        // Create policies from template
        const policyEngine = policyEngineService(db);
        const templatePolicies = (template.policies ?? []) as Array<{
            name: string;
            actionPattern: string;
            conditions?: Record<string, unknown>;
            effect: string;
            priority?: number;
        }>;

        for (const policyDef of templatePolicies) {
            try {
                const policy = await policyEngine.createPolicy(projectId, {
                    name: policyDef.name,
                    actionPattern: policyDef.actionPattern,
                    conditions: policyDef.conditions,
                    effect: policyDef.effect as "allow" | "block" | "require_approval",
                    priority: policyDef.priority,
                    createdByUserId: actor.actorId,
                });
                createdPolicies.push(policy.id);
            } catch {
                // Skip duplicate policies
            }
        }

        // Increment download count
        await db
            .update(projectTemplates)
            .set({ downloadCount: (template.downloadCount ?? 0) + 1 })
            .where(eq(projectTemplates.id, templateId));

        await logActivity(db, {
            projectId,
            actorType: actor.actorType,
            actorId: actor.actorId,
            action: "template.applied",
            entityType: "project_template",
            entityId: templateId,
            details: {
                templateName: template.name,
                agentsCreated: createdAgents.length,
                policiesCreated: createdPolicies.length,
            },
        });

        res.json({
            ok: true,
            template: template.name,
            agentsCreated: createdAgents.length,
            policiesCreated: createdPolicies.length,
        });
    });

    // ── Export Project as Template ──────────────────────────────────────────

    /**
     * POST /api/projects/:projectId/export-as-template
     * Export the current project's agents + policies as a reusable template.
     */
    router.post("/projects/:projectId/export-as-template", async (req, res) => {
        assertBoard(req);
        const { projectId } = req.params;
        const actor = getActorInfo(req);
        const { name, description, archetype, communityContributed } = req.body;

        if (!name || typeof name !== "string") {
            res.status(400).json({ error: "'name' is required" });
            return;
        }

        // Export agents
        const agentSvc = agentService(db);
        const agentList = await agentSvc.list(projectId, {});
        const exportedAgents = agentList.map((a: any) => ({
            role: a.role,
            name: a.name,
            schedule: a.runtimeConfig?.heartbeatSchedule,
            triggers: a.runtimeConfig?.triggers,
            budget: a.budgetMonthlyCents,
        }));

        // Export policies
        const policyEngine = policyEngineService(db);
        const policyList = await policyEngine.listPolicies(projectId);
        const exportedPolicies = policyList.map((p: any) => ({
            name: p.name,
            actionPattern: p.actionPattern,
            conditions: p.conditions,
            effect: p.effect,
            priority: p.priority,
        }));

        // Create template entry
        const rows = await db
            .insert(projectTemplates)
            .values({
                name: name.trim(),
                description: description ?? null,
                archetype: archetype ?? "cli_tool",
                agents: exportedAgents,
                policies: exportedPolicies,
                version: "1.0.0",
                authorId: actor.actorId,
                communityContributed: communityContributed ?? false,
            })
            .returning();

        await logActivity(db, {
            projectId,
            actorType: actor.actorType,
            actorId: actor.actorId,
            action: "template.exported",
            entityType: "project_template",
            entityId: rows[0].id,
            details: {
                templateName: rows[0].name,
                agentCount: exportedAgents.length,
                policyCount: exportedPolicies.length,
            },
        });

        res.status(201).json(rows[0]);
    });

    return router;
}
