/**
 * GitLab Client Factory
 *
 * Provides GitLab API client instances using native fetch,
 * with token management from the project_secret_versions table.
 */

/**
 * Cache for GitLab clients to avoid re-instantiating for every call.
 * Key: `projectId`, Value: { token, baseUrl }
 */
const clientCache = new Map<string, { token: string; baseUrl: string }>();

export interface GitLabClient {
  token: string;
  baseUrl: string;
}

/**
 * Get or create a GitLab client for a project.
 * Loads the GitLab token from project_secret_versions table.
 *
 * @param db - Database instance
 * @param projectId - Project ID
 * @returns GitLab client instance, or null if no token found
 */
export async function getGitLabClient(
  db: import("@gitmesh/data").Db,
  projectId: string,
): Promise<GitLabClient | null> {
  if (clientCache.has(projectId)) {
    return clientCache.get(projectId)!;
  }

  const { eq, and } = await import("@gitmesh/data");
  const { projectSecrets, projectSecretVersions } = await import("@gitmesh/data");

  // Look up GitLab token secret metadata
  const secretRows = await db
    .select()
    .from(projectSecrets)
    .where(eq(projectSecrets.projectId, projectId));

  // Find the GitLab token secret (gitlab_token or GITLAB_TOKEN)
  const tokenSecret = secretRows.find(
    (s) => s.name === "gitlab_token" || s.name === "GITLAB_TOKEN",
  );

  if (!tokenSecret) {
    console.warn(`No GitLab token secret found for project ${projectId}`);
    return null;
  }

  // Get the latest version of the secret
  const secretVersionRows = await db
    .select()
    .from(projectSecretVersions)
    .where(
      and(
        eq(projectSecretVersions.secretId, tokenSecret.id),
        eq(projectSecretVersions.version, tokenSecret.latestVersion),
      ),
    );

  if (secretVersionRows.length === 0 || !secretVersionRows[0].material) {
    const fallbackRows = await db
      .select()
      .from(projectSecretVersions)
      .where(eq(projectSecretVersions.secretId, tokenSecret.id));
    if (fallbackRows.length === 0 || !fallbackRows[0].material) {
      console.warn(`No secret material found for GitLab token in project ${projectId}`);
      return null;
    }

    const fallbackMaterial = fallbackRows[0].material as Record<string, unknown>;
    const fallbackToken =
      (fallbackMaterial.token as string) ||
      (fallbackMaterial.gitlab_token as string) ||
      (fallbackMaterial.GITLAB_TOKEN as string) ||
      Object.values(fallbackMaterial)[0];

    if (!fallbackToken || typeof fallbackToken !== "string") {
      console.warn(`Invalid GitLab token material for project ${projectId}`);
      return null;
    }

    const baseUrl =
      (fallbackMaterial.baseUrl as string) ||
      (fallbackMaterial.gitlab_url as string) ||
      "https://gitlab.com";

    const fallbackClient = { token: fallbackToken, baseUrl };
    clientCache.set(projectId, fallbackClient);
    return fallbackClient;
  }

  if (!secretVersionRows[0].material) {
    console.warn(`No secret material found for GitLab token in project ${projectId}`);
    return null;
  }

  // Extract the token and base URL from the material
  const material = secretVersionRows[0].material as Record<string, unknown>;
  const token =
    (material.token as string) ||
    (material.gitlab_token as string) ||
    (material.GITLAB_TOKEN as string) ||
    Object.values(material)[0];

  if (!token || typeof token !== "string") {
    console.warn(`Invalid GitLab token material for project ${projectId}`);
    return null;
  }

  const baseUrl =
    (material.baseUrl as string) ||
    (material.gitlab_url as string) ||
    "https://gitlab.com";

  // Create and cache the client
  const gitlabClient = { token, baseUrl };
  clientCache.set(projectId, gitlabClient);
  return gitlabClient;
}

/**
 * Invalidate cached client (e.g., after token rotation)
 */
export function invalidateGitLabClientCache(projectId: string): void {
  clientCache.delete(projectId);
}

// ─── GitLab API Operations ─────────────────────────────────────────────────────

/**
 * Post a comment on a GitLab issue or merge request.
 */
export async function postGitLabComment(
  client: GitLabClient,
  owner: string,
  repo: string,
  iid: number, // GitLab uses `iid` not `number`
  body: string,
): Promise<{ commentId: number } | null> {
  const projectPath = encodeURIComponent(`${owner}/${repo}`);

  try {
    const response = await fetch(
      `${client.baseUrl}/api/v4/projects/${projectPath}/issues/${iid}/notes`,
      {
        method: "POST",
        headers: {
          "PRIVATE-TOKEN": client.token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ body }),
      },
    );

    if (!response.ok) {
      const errText = await response.text();
      console.error(
        `Failed to post comment on ${owner}/${repo}#${iid}: ${response.status} ${errText}`,
      );
      return null;
    }

    const data = (await response.json()) as { id: number };
    return { commentId: data.id };
  } catch (error) {
    console.error(
      `Failed to post comment on ${owner}/${repo}#${iid}:`,
      error,
    );
    return null;
  }
}

/**
 * Post a comment on a GitLab merge request.
 */
export async function postGitLabMrComment(
  client: GitLabClient,
  owner: string,
  repo: string,
  mrIid: number,
  body: string,
): Promise<{ commentId: number } | null> {
  const projectPath = encodeURIComponent(`${owner}/${repo}`);

  try {
    const response = await fetch(
      `${client.baseUrl}/api/v4/projects/${projectPath}/merge_requests/${mrIid}/notes`,
      {
        method: "POST",
        headers: {
          "PRIVATE-TOKEN": client.token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ body }),
      },
    );

    if (!response.ok) {
      const errText = await response.text();
      console.error(
        `Failed to post MR comment on ${owner}/${repo}!${mrIid}: ${response.status} ${errText}`,
      );
      return null;
    }

    const data = (await response.json()) as { id: number };
    return { commentId: data.id };
  } catch (error) {
    console.error(
      `Failed to post MR comment on ${owner}/${repo}!${mrIid}:`,
      error,
    );
    return null;
  }
}

/**
 * Add labels to a GitLab issue or MR.
 */
export async function addGitLabLabels(
  client: GitLabClient,
  owner: string,
  repo: string,
  iid: number,
  labels: string[],
  type: "issue" | "merge_request" = "issue",
): Promise<boolean> {
  if (labels.length === 0) return true;

  const projectPath = encodeURIComponent(`${owner}/${repo}`);
  const endpoint =
    type === "merge_request"
      ? `/api/v4/projects/${projectPath}/merge_requests/${iid}`
      : `/api/v4/projects/${projectPath}/issues/${iid}`;

  try {
    // GitLab uses add_labels as a body parameter on update
    const response = await fetch(`${client.baseUrl}${endpoint}`, {
      method: "PUT",
      headers: {
        "PRIVATE-TOKEN": client.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ add_labels: labels.join(",") }),
    });

    if (!response.ok) {
      const errText = await response.text();
      console.error(
        `Failed to add labels to ${owner}/${repo}${type === "merge_request" ? "!" : "#"}${iid}: ${response.status} ${errText}`,
      );
      return false;
    }

    return true;
  } catch (error) {
    console.error(
      `Failed to add labels to ${owner}/${repo}${type === "merge_request" ? "!" : "#"}${iid}:`,
      error,
    );
    return false;
  }
}

/**
 * Request reviewers on a GitLab merge request.
 */
export async function requestGitLabReviewers(
  client: GitLabClient,
  owner: string,
  repo: string,
  mrIid: number,
  reviewers: string[],
): Promise<boolean> {
  if (reviewers.length === 0) return true;

  const projectPath = encodeURIComponent(`${owner}/${repo}`);

  try {
    // GitLab merge request reviewers are set via the reviewers field
    const response = await fetch(
      `${client.baseUrl}/api/v4/projects/${projectPath}/merge_requests/${mrIid}`,
      {
        method: "PUT",
        headers: {
          "PRIVATE-TOKEN": client.token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ reviewer_ids: reviewers }),
      },
    );

    if (!response.ok) {
      const errText = await response.text();
      console.error(
        `Failed to request reviewers on ${owner}/${repo}!${mrIid}: ${response.status} ${errText}`,
      );
      return false;
    }

    return true;
  } catch (error) {
    console.error(
      `Failed to request reviewers on ${owner}/${repo}!${mrIid}:`,
      error,
    );
    return false;
  }
}

/**
 * Update GitLab issue or MR state (open/closed).
 */
export async function updateGitLabState(
  client: GitLabClient,
  owner: string,
  repo: string,
  iid: number,
  state: "open" | "closed",
  type: "issue" | "merge_request" = "issue",
): Promise<boolean> {
  const projectPath = encodeURIComponent(`${owner}/${repo}`);

  // Map open/closed to GitLab's state_event
  const stateEvent = state === "closed" ? "close" : "reopen";

  const endpoint =
    type === "merge_request"
      ? `/api/v4/projects/${projectPath}/merge_requests/${iid}`
      : `/api/v4/projects/${projectPath}/issues/${iid}`;

  try {
    const response = await fetch(`${client.baseUrl}${endpoint}`, {
      method: "PUT",
      headers: {
        "PRIVATE-TOKEN": client.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ state_event: stateEvent }),
    });

    if (!response.ok) {
      const errText = await response.text();
      console.error(
        `Failed to update ${type} state on ${owner}/${repo}${type === "merge_request" ? "!" : "#"}${iid}: ${response.status} ${errText}`,
      );
      return false;
    }

    return true;
  } catch (error) {
    console.error(
      `Failed to update ${type} state on ${owner}/${repo}${type === "merge_request" ? "!" : "#"}${iid}:`,
      error,
    );
    return false;
  }
}
