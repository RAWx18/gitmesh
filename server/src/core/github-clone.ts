/**
 * GitHub clone-on-connect helper
 *
 * When a project is connected to a GitHub repo, materializes the source on
 * disk so adapters (claude, codex, cursor, opencode, pi) actually have files
 * to operate on. The `connect-project` route used to update only metadata
 * (forgeOwner/forgeRepo) and start a periodic issue poll - agents would then
 * spawn in an empty fallback directory with no repo content.
 *
 * Repos are cloned to:
 *   ~/.gitmesh-agents/instances/<id>/repos/<projectId>/<repo>
 *
 * A row is upserted into project_workspaces so heartbeat.resolveWorkspaceForRun
 * picks the path up automatically. We also create a default subproject if the
 * project doesn't have one yet, since project_workspaces.subproject_id is NOT NULL.
 */

import path from "node:path";
import os from "node:os";
import fs from "node:fs/promises";
import { spawn } from "node:child_process";
import { and, eq } from "drizzle-orm";
import type { Db } from "@gitmesh/data";
import {
  projectWorkspaces,
  subprojects,
} from "@gitmesh/data";
import { resolveGitmeshAgentsInstanceRoot } from "../home-paths.js";

const SAFE_SEGMENT_RE = /^[A-Za-z0-9._-]+$/;

function assertSafeSegment(name: string, label: string): void {
  if (!SAFE_SEGMENT_RE.test(name)) {
    throw new Error(`Invalid ${label} '${name}': only [A-Za-z0-9._-] allowed`);
  }
}

export function resolveProjectRepoCloneRoot(): string {
  const override = process.env.GITMESH_REPO_CLONE_ROOT?.trim();
  if (override) {
    if (override.startsWith("~/")) {
      return path.resolve(os.homedir(), override.slice(2));
    }
    return path.resolve(override);
  }
  return path.resolve(resolveGitmeshAgentsInstanceRoot(), "repos");
}

export function resolveProjectRepoClonePath(projectId: string, repoName: string): string {
  assertSafeSegment(repoName, "repo name");
  // projectId is a UUID - characters won't include path separators but assert
  // anyway to be defensive against future ID format changes.
  if (!/^[A-Za-z0-9._-]+$/.test(projectId)) {
    throw new Error(`Invalid project id for clone path: ${projectId}`);
  }
  return path.resolve(resolveProjectRepoCloneRoot(), projectId, repoName);
}

interface RunGitOptions {
  cwd?: string;
  env?: Record<string, string | undefined>;
  timeoutMs?: number;
}

function runGit(args: string[], opts: RunGitOptions = {}): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn("git", args, {
      cwd: opts.cwd,
      env: { ...process.env, ...opts.env },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    const timer = opts.timeoutMs
      ? setTimeout(() => {
          child.kill("SIGKILL");
          reject(new Error(`git ${args[0]} timed out after ${opts.timeoutMs}ms`));
        }, opts.timeoutMs)
      : null;
    child.on("error", (err) => {
      if (timer) clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code) => {
      if (timer) clearTimeout(timer);
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        reject(new Error(`git ${args.join(" ")} exited with ${code}: ${stderr.trim() || stdout.trim()}`));
      }
    });
  });
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.stat(p);
    return true;
  } catch {
    return false;
  }
}

async function isGitRepo(p: string): Promise<boolean> {
  return pathExists(path.join(p, ".git"));
}

/**
 * Build an authenticated clone URL. GitHub accepts
 * https://x-access-token:<TOKEN>@github.com/<owner>/<repo>.git for both
 * OAuth tokens and PATs.
 */
function buildAuthenticatedRepoUrl(owner: string, repo: string, token: string | null): string {
  if (token) {
    return `https://x-access-token:${encodeURIComponent(token)}@github.com/${owner}/${repo}.git`;
  }
  return `https://github.com/${owner}/${repo}.git`;
}

export interface CloneResult {
  cwd: string;
  repoUrl: string;
  cloned: boolean;
  fetched: boolean;
  warning?: string;
}

export async function ensureRepoCloned(input: {
  projectId: string;
  forgeOwner: string;
  forgeRepo: string;
  token: string | null;
  ref?: string | null;
}): Promise<CloneResult> {
  const { projectId, forgeOwner, forgeRepo, token, ref } = input;
  assertSafeSegment(forgeOwner, "forge owner");
  assertSafeSegment(forgeRepo, "forge repo");

  const targetDir = resolveProjectRepoClonePath(projectId, forgeRepo);
  const publicUrl = `https://github.com/${forgeOwner}/${forgeRepo}.git`;
  const authedUrl = buildAuthenticatedRepoUrl(forgeOwner, forgeRepo, token);

  await fs.mkdir(path.dirname(targetDir), { recursive: true });

  if (await isGitRepo(targetDir)) {
    // Existing checkout - update remote URL (token may have rotated) and fetch.
    try {
      await runGit(["remote", "set-url", "origin", authedUrl], { cwd: targetDir, timeoutMs: 30_000 });
      await runGit(["fetch", "--all", "--prune"], { cwd: targetDir, timeoutMs: 120_000 });
      if (ref) {
        await runGit(["checkout", ref], { cwd: targetDir, timeoutMs: 30_000 });
      }
      return { cwd: targetDir, repoUrl: publicUrl, cloned: false, fetched: true };
    } catch (err) {
      return {
        cwd: targetDir,
        repoUrl: publicUrl,
        cloned: false,
        fetched: false,
        warning: `git fetch failed: ${err instanceof Error ? err.message : String(err)}`,
      };
    }
  }

  // Fresh clone.
  if (await pathExists(targetDir)) {
    // Directory exists but is not a git repo - refuse to clobber.
    return {
      cwd: targetDir,
      repoUrl: publicUrl,
      cloned: false,
      fetched: false,
      warning: `Path already exists and is not a git repo: ${targetDir}. Skipping clone.`,
    };
  }

  await runGit(
    ["clone", "--depth", "50", authedUrl, targetDir],
    { timeoutMs: 5 * 60_000 },
  );
  if (ref) {
    await runGit(["checkout", ref], { cwd: targetDir, timeoutMs: 30_000 });
  }
  return { cwd: targetDir, repoUrl: publicUrl, cloned: true, fetched: false };
}

/**
 * Find the primary subproject for a project, creating a default one if none
 * exists. Returns the subproject id.
 */
export async function ensureDefaultSubprojectId(db: Db, projectId: string): Promise<string> {
  const existing = await db
    .select({ id: subprojects.id })
    .from(subprojects)
    .where(eq(subprojects.projectId, projectId))
    .limit(1);
  if (existing[0]?.id) return existing[0].id;

  const inserted = await db
    .insert(subprojects)
    .values({
      projectId,
      name: "Main",
      description: "Default subproject created when connecting a forge repo",
      status: "in_progress",
    })
    .returning({ id: subprojects.id });
  return inserted[0].id;
}

/**
 * Upsert a project_workspaces row pointing at the cloned repo.
 */
export async function upsertProjectWorkspace(input: {
  db: Db;
  projectId: string;
  subprojectId: string;
  cwd: string;
  repoUrl: string;
  repoRef?: string | null;
  name?: string;
}): Promise<string> {
  const { db, projectId, subprojectId, cwd, repoUrl, repoRef, name } = input;

  const existing = await db
    .select({ id: projectWorkspaces.id })
    .from(projectWorkspaces)
    .where(
      and(
        eq(projectWorkspaces.projectId, projectId),
        eq(projectWorkspaces.subprojectId, subprojectId),
      ),
    )
    .limit(1);

  if (existing[0]?.id) {
    await db
      .update(projectWorkspaces)
      .set({
        cwd,
        repoUrl,
        repoRef: repoRef ?? null,
        updatedAt: new Date(),
      })
      .where(eq(projectWorkspaces.id, existing[0].id));
    return existing[0].id;
  }

  const inserted = await db
    .insert(projectWorkspaces)
    .values({
      projectId,
      subprojectId,
      name: name ?? "primary",
      cwd,
      repoUrl,
      repoRef: repoRef ?? null,
      isPrimary: true,
    })
    .returning({ id: projectWorkspaces.id });
  return inserted[0].id;
}
