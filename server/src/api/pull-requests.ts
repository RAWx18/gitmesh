import { Router } from "express";
import { eq, and, isNotNull, sql } from "@gitmesh/data";
import type { Db } from "@gitmesh/data";
import { issues } from "@gitmesh/data";
import { assertProjectAccess } from "./authz.js";
import { getActorInfo } from "./authz.js";
import { logActivity } from "../core/index.js";
import { forgeSyncService } from "../core/forge-sync.js";

export function pullRequestRoutes(db: Db) {
  const router = Router();

  /**
   * Derive a human-readable PR status from the forgeState field.
   */
  function derivePrStatus(forgeState: string | null): "open" | "merged" | "closed" {
    if (forgeState === "merged") return "merged";
    if (forgeState === "closed") return "closed";
    return "open";
  }

  /**
   * GET /projects/:projectId/pull-requests
   * List PRs for a project (issues where forgePrNumber is not null).
   */
  router.get("/projects/:projectId/pull-requests", async (req, res) => {
    const projectId = req.params.projectId as string;
    assertProjectAccess(req, projectId);

    const statusFilter = req.query.status as string | undefined;
    let query = db
      .select()
      .from(issues)
      .where(and(eq(issues.projectId, projectId), isNotNull(issues.forgePrNumber)));

    const rows = await query;

    let prs = rows.map((row) => ({
      id: row.id,
      title: row.title,
      description: row.description,
      status: derivePrStatus(row.forgeState),
      forgeState: row.forgeState,
      forgePrNumber: row.forgePrNumber,
      forgeUrl: row.forgeUrl,
      identifier: row.identifier,
      projectId: row.projectId,
      subprojectId: row.subprojectId,
      authorUserId: row.createdByUserId,
      authorAgentId: row.createdByAgentId,
      assigneeAgentId: row.assigneeAgentId,
      assigneeUserId: row.assigneeUserId,
      labelIds: (row as unknown as { labelIds?: string[] }).labelIds ?? [],
      labels: (row as unknown as { labels?: unknown[] }).labels ?? [],
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
      lastSyncedAt: row.lastSyncedAt,
    }));

    if (statusFilter && statusFilter !== "all") {
      prs = prs.filter((pr) => pr.status === statusFilter);
    }

    // Sort: open first, then merged, then closed; within each group by createdAt desc
    prs.sort((a, b) => {
      const order = { open: 0, merged: 1, closed: 2 };
      const statusDiff = order[a.status] - order[b.status];
      if (statusDiff !== 0) return statusDiff;
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
    });

    res.json(prs);
  });

  /**
   * GET /pull-requests/:id
   * Get a single PR by its issue id (which has forgePrNumber set).
   */
  router.get("/pull-requests/:id", async (req, res) => {
    const id = req.params.id as string;

    const rows = await db
      .select()
      .from(issues)
      .where(eq(issues.id, id));

    const row = rows[0];
    if (!row) {
      res.status(404).json({ error: "Pull request not found" });
      return;
    }

    assertProjectAccess(req, row.projectId);

    // Fetch linked issues (issues that reference this PR in description or are child issues)
    // For now, fetch all issues in the same project that have a forgePrNumber - this gives
    // us all PRs, and the UI can link issues to PRs via labels or a separate linking table.
    // A proper implementation would use a dedicated pr_issues junction table.
    const linkedIssueRows = await db
      .select()
      .from(issues)
      .where(
        and(
          eq(issues.projectId, row.projectId),
          sql`${issues.id} != ${row.id}`,
        ),
      );

    const linkedIssues = linkedIssueRows
      .filter((r) => {
        // Heuristic: include issues that mention this PR number in the description
        if (!r.description) return false;
        return r.description.includes(`#${row.forgePrNumber}`) || r.description.includes(`!${row.forgePrNumber}`);
      })
      .map((r) => ({
        id: r.id,
        identifier: r.identifier,
        title: r.title,
        status: r.status,
        priority: r.priority,
        forgeIssueNumber: r.forgeIssueNumber,
      }));

    const pr = {
      id: row.id,
      title: row.title,
      description: row.description,
      status: derivePrStatus(row.forgeState),
      forgeState: row.forgeState,
      forgePrNumber: row.forgePrNumber,
      forgeUrl: row.forgeUrl,
      identifier: row.identifier,
      projectId: row.projectId,
      subprojectId: row.subprojectId,
      goalId: row.goalId,
      authorUserId: row.createdByUserId,
      authorAgentId: row.createdByAgentId,
      assigneeAgentId: row.assigneeAgentId,
      assigneeUserId: row.assigneeUserId,
      labelIds: (row as unknown as { labelIds?: string[] }).labelIds ?? [],
      labels: (row as unknown as { labels?: unknown[] }).labels ?? [],
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
      lastSyncedAt: row.lastSyncedAt,
      startedAt: row.startedAt,
      completedAt: row.completedAt,
      linkedIssues,
    };

    res.json(pr);
  });

  /**
   * PATCH /pull-requests/:id
   * Update PR state (approve, request changes, merge).
   * Delegates to forge-sync service to push state changes back to the forge.
   */
  router.patch("/pull-requests/:id", async (req, res) => {
    const id = req.params.id as string;

    const rows = await db
      .select()
      .from(issues)
      .where(eq(issues.id, id));

    const row = rows[0];
    if (!row) {
      res.status(404).json({ error: "Pull request not found" });
      return;
    }

    assertProjectAccess(req, row.projectId);

    const { action } = req.body as { action?: string };

    const forgeSync = forgeSyncService(db);
    const actor = getActorInfo(req);

    if (action === "merge" || action === "close") {
      const state = action === "merge" ? "merged" : "closed";
      // Update local forgeState
      await db
        .update(issues)
        .set({ forgeState: state, lastSyncedAt: new Date(), updatedAt: new Date() })
        .where(eq(issues.id, id));

      // Push to forge
      await forgeSync.updateForgeIssueState(row.projectId, id, "closed", actor.agentId ?? undefined);

      if (action === "merge") {
        // Note: GitHub doesn't have a direct "merge" API state - this is handled by the forge.
        // For now, update the local state to merged.
        await db
          .update(issues)
          .set({ forgeState: "merged", updatedAt: new Date() })
          .where(eq(issues.id, id));
      }

      await logActivity(db, {
        projectId: row.projectId,
        actorType: actor.actorType,
        actorId: actor.actorId,
        agentId: actor.agentId,
        runId: actor.runId,
        action: `pr.${action}ed`,
        entityType: "pull_request",
        entityId: id,
        details: { forgePrNumber: row.forgePrNumber, forgeUrl: row.forgeUrl },
      });

      res.json({ ok: true, status: action === "merge" ? "merged" : "closed" });
      return;
    }

    res.status(400).json({ error: `Unknown action: ${action}` });
  });

  return router;
}
