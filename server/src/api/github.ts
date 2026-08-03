import { Router } from "express";
import { eq, and } from "@gitmesh/data";
import type { Db } from "@gitmesh/data";
import { authAccounts, projects } from "@gitmesh/data";
import { assertBoard, assertProjectAccess, getActorInfo } from "./authz.js";
import { logActivity, secretService, startPeriodicSync } from "../core/index.js";
import {
  ensureRepoCloned,
  ensureDefaultSubprojectId,
  upsertProjectWorkspace,
} from "../core/github-clone.js";

interface GitHubTokenInfo {
  token: string;
  source: "oauth" | "local_dev_pat";
}

/**
 * Resolve a GitHub token for the current request, with a local-dev fallback.
 *
 * Order:
 *   1. authAccounts row for the signed-in user (OAuth via better-auth)
 *   2. process.env.GITHUB_LOCAL_DEV_PAT (only when GITMESH_DEPLOYMENT_MODE=local_trusted)
 *
 * Returns null if neither is available.
 */
async function resolveGitHubToken(db: Db, userId: string | null): Promise<GitHubTokenInfo | null> {
  if (userId) {
    const accounts = await db
      .select()
      .from(authAccounts)
      .where(and(eq(authAccounts.userId, userId), eq(authAccounts.providerId, "github")));
    const githubAccount = accounts[0];
    if (githubAccount?.accessToken) {
      return { token: githubAccount.accessToken, source: "oauth" };
    }
  }

  const pat = process.env.GITHUB_LOCAL_DEV_PAT?.trim();
  const mode = process.env.GITMESH_DEPLOYMENT_MODE?.trim() ?? "local_trusted";
  if (pat && mode === "local_trusted") {
    return { token: pat, source: "local_dev_pat" };
  }
  return null;
}

const NO_TOKEN_MESSAGE =
  "No GitHub token available. Sign in with GitHub, or set GITHUB_LOCAL_DEV_PAT in .env for local development.";

export function githubRoutes(_db: Db) {
  const router = Router();

  // GET /api/github/repos - list the authenticated user's GitHub repos
  router.get("/github/repos", async (req, res) => {
    const userId = req.actor?.userId ?? null;
    const tokenInfo = await resolveGitHubToken(_db, userId);
    if (!tokenInfo) {
      res.status(400).json({ error: NO_TOKEN_MESSAGE });
      return;
    }

    const { Octokit } = await import("@octokit/rest");
    const octokit = new Octokit({ auth: tokenInfo.token });

    try {
      const { data } = await octokit.rest.repos.listForAuthenticatedUser({
        sort: "updated",
        per_page: 100,
        affiliation: "owner,collaborator,organization_member",
      });
      res.json(
        data.map((r) => ({
          id: r.id,
          name: r.name,
          full_name: r.full_name,
          owner: { login: r.owner.login },
          private: r.private,
          html_url: r.html_url,
          default_branch: r.default_branch,
          updated_at: r.updated_at,
          description: r.description,
        })),
      );
    } catch (err) {
      console.error("GitHub repos fetch error:", err);
      res.status(500).json({ error: "Failed to fetch repos from GitHub" });
    }
  });

  // GET /api/github/user - get the authenticated user's GitHub info
  router.get("/github/user", async (req, res) => {
    const userId = req.actor?.userId ?? null;
    const tokenInfo = await resolveGitHubToken(_db, userId);
    if (!tokenInfo) {
      res.status(400).json({ error: NO_TOKEN_MESSAGE });
      return;
    }

    const { Octokit } = await import("@octokit/rest");
    const octokit = new Octokit({ auth: tokenInfo.token });

    try {
      const { data } = await octokit.rest.users.getAuthenticated();
      res.json({
        login: data.login,
        name: data.name,
        avatar_url: data.avatar_url,
        html_url: data.html_url,
        token_source: tokenInfo.source,
      });
    } catch (err) {
      console.error("GitHub user fetch error:", err);
      res.status(500).json({ error: "Failed to fetch user from GitHub" });
    }
  });

  /**
   * POST /api/github/connect-project
   *
   * Connects a GitHub repo to a project end-to-end:
   *   1. Resolves a GitHub token (OAuth or local-dev PAT)
   *   2. Stores it as a project secret (rotates if it already exists)
   *   3. Updates project.forgeProvider/forgeOwner/forgeRepo
   *   4. Clones the repo to disk and creates a project_workspaces row so
   *      agent runs actually see the source code (the previous behavior
   *      left adapters with an empty fallback directory).
   *   5. Starts periodic issue sync.
   */
  router.post("/github/connect-project", async (req, res) => {
    if (!req.actor) {
      res.status(401).json({ error: "Not authenticated" });
      return;
    }

    const { projectId, forgeOwner, forgeRepo, ref } = req.body as {
      projectId?: string;
      forgeOwner?: string;
      forgeRepo?: string;
      ref?: string;
    };

    if (!projectId || !forgeOwner || !forgeRepo) {
      res.status(400).json({ error: "projectId, forgeOwner, and forgeRepo are required" });
      return;
    }

    assertBoard(req);
    assertProjectAccess(req, projectId);

    const tokenInfo = await resolveGitHubToken(_db, req.actor.userId ?? null);
    if (!tokenInfo) {
      res.status(400).json({ error: NO_TOKEN_MESSAGE });
      return;
    }

    const secrets = secretService(_db);
    const actor = getActorInfo(req);
    const existingSecret = await secrets.getByName(projectId, "github_token");
    let secretId: string;

    if (existingSecret) {
      await secrets.rotate(
        existingSecret.id,
        { value: tokenInfo.token },
        { userId: actor.actorId ?? "operator", agentId: actor.agentId ?? null },
      );
      secretId = existingSecret.id;
    } else {
      const created = await secrets.create(
        projectId,
        {
          name: "github_token",
          provider: "local_encrypted",
          value: tokenInfo.token,
          description:
            tokenInfo.source === "local_dev_pat"
              ? "GitHub Personal Access Token (local-dev)"
              : "GitHub OAuth Access Token",
        },
        { userId: actor.actorId ?? "operator", agentId: actor.agentId ?? null },
      );
      secretId = created.id;
    }

    const updated = await _db
      .update(projects)
      .set({
        forgeProvider: "github",
        forgeOwner,
        forgeRepo,
        repoUrl: `https://github.com/${forgeOwner}/${forgeRepo}.git`,
        updatedAt: new Date(),
      })
      .where(eq(projects.id, projectId))
      .returning()
      .then((rows) => rows[0] ?? null);

    if (!updated) {
      res.status(404).json({ error: "Project not found" });
      return;
    }

    // Clone the repo and register a workspace so agents have actual source files.
    let cloneCwd: string | null = null;
    let cloneWarning: string | null = null;
    try {
      const cloneResult = await ensureRepoCloned({
        projectId,
        forgeOwner,
        forgeRepo,
        token: tokenInfo.token,
        ref: ref ?? null,
      });
      cloneCwd = cloneResult.cwd;
      cloneWarning = cloneResult.warning ?? null;

      const subprojectId = await ensureDefaultSubprojectId(_db, projectId);
      await upsertProjectWorkspace({
        db: _db,
        projectId,
        subprojectId,
        cwd: cloneResult.cwd,
        repoUrl: cloneResult.repoUrl,
        repoRef: ref ?? null,
        name: forgeRepo,
      });
    } catch (err) {
      cloneWarning = err instanceof Error ? err.message : String(err);
      console.error("[github] connect-project clone failed:", cloneWarning);
    }

    await logActivity(_db, {
      projectId,
      actorType: actor.actorType,
      actorId: actor.actorId,
      action: "forge.connected",
      entityType: "project",
      entityId: projectId,
      details: {
        forgeProvider: "github",
        forgeOwner,
        forgeRepo,
        tokenSource: tokenInfo.source,
        cloneCwd,
        cloneWarning,
      },
    });

    // Start periodic pull-based sync (issues + state transitions).
    await startPeriodicSync(_db, projectId);

    res.json({
      ok: true,
      forgeOwner,
      forgeRepo,
      secretId,
      cloneCwd,
      cloneWarning,
      tokenSource: tokenInfo.source,
    });
  });

  return router;
}
