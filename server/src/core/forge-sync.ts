/**
 * Forge Sync Service
 *
 * Handles bidirectional synchronization between GitMesh Agents and forge providers
 * (GitHub, GitLab, Forgejo). Responsibilities:
 *
 * 1. Webhook registration & lifecycle (register/unregister/rotate secrets)
 * 2. Inbound: process incoming forge events (issue opened, PR opened, comment added, etc.)
 * 3. Outbound: push agent actions back to the forge (comments, status updates)
 * 4. Issue/PR sync: map forge entities ↔ GitMesh issues
 * 5. Agent wakeup: trigger agent wakeup requests in response to forge events
 */

import { eq, and } from "@gitmesh/data";
import type { Db } from "@gitmesh/data";
import {
  projects,
  issues,
  issueComments,
  forgeWebhooks,
  agents,
} from "@gitmesh/data";
import crypto from "node:crypto";
import type { ForgeProvider } from "@gitmesh/core";
import { OSS_ROLE_DEFAULTS } from "@gitmesh/core";
import {
  getGitHubClient,
  postGitHubComment,
  addGitHubLabels,
  requestGitHubReviewers,
  updateGitHubState,
} from "./github-client.js";
import {
  getGitLabClient,
  postGitLabComment,
  postGitLabMrComment,
  addGitLabLabels,
  requestGitLabReviewers,
  updateGitLabState,
} from "./gitlab-client.js";
import { executeSkillsForRole } from "./skill-registry.js";
import { policyEngineService } from "./policy-engine.js";
import { logActivity } from "./index.js";
import { heartbeatService } from "./heartbeat.js";

// ─── Forge Event Types ───────────────────────────────────────────────────────

export type ForgeEventType =
  | "issue_opened"
  | "issue_closed"
  | "issue_reopened"
  | "issue_comment"
  | "pr_opened"
  | "pr_closed"
  | "pr_merged"
  | "pr_review_requested"
  | "pr_review_submitted"
  | "pr_comment"
  | "push"
  | "release_published"
  | "security_advisory";

export interface ForgeEvent {
  provider: ForgeProvider;
  eventType: ForgeEventType;
  projectId: string;
  /** Raw payload from the forge webhook */
  payload: Record<string, unknown>;
  /** Forge-specific identifiers */
  forgeOwner: string;
  forgeRepo: string;
  /** Issue or PR number on the forge */
  forgeNumber?: number;
  /** URL to the forge entity */
  forgeUrl?: string;
  /** Author of the event */
  authorLogin?: string;
  /** Title (for issue/PR events) */
  title?: string;
  /** Body text (for comment events) */
  body?: string;
}

export interface WebhookRegistration {
  projectId: string;
  forgeProvider: ForgeProvider;
  forgeOwner: string;
  forgeRepo: string;
  events: string[];
}

// ─── Service Factory ─────────────────────────────────────────────────────────

export function forgeSyncService(db: Db) {
  const policyEngine = policyEngineService(db);
  const service = {
    // ── Webhook Management ─────────────────────────────────────────────

    /**
     * Register a webhook with the forge for the given project.
     * Calls the forge API (GitHub) to create the webhook, then stores
     * metadata (including the returned forgeWebhookId) in forge_webhooks table.
     */
    async registerWebhook(registration: WebhookRegistration): Promise<{ id: string; webhookSecret: string }> {
      const secret = generateWebhookSecret();

      // Determine the webhook callback URL from the current server environment
      const baseUrl =
        process.env.GITMESH_PUBLIC_BASE_URL ??
        process.env.API_BASE_URL ??
        `http://localhost:${process.env.PORT ?? 3000}`;
      const webhookCallbackUrl = `${baseUrl.replace(/\/$/, "")}/api/forge/webhook/${registration.forgeProvider}`;

      let forgeWebhookId: string | null = null;
      let registrationError: string | null = null;

      // GitHub rejects callback URLs pointing at localhost / 127.x - skip
      // registration in that case and rely on the periodic poll-based sync.
      // Operators can set GITMESH_PUBLIC_BASE_URL to a tunnel (e.g. cloudflared,
      // smee.io) to opt back into real webhooks.
      const callbackHost = (() => {
        try {
          return new URL(webhookCallbackUrl).hostname.toLowerCase();
        } catch {
          return "";
        }
      })();
      const isLocalCallback =
        callbackHost === "localhost" ||
        callbackHost === "127.0.0.1" ||
        callbackHost === "::1" ||
        callbackHost.endsWith(".local");
      const skipRemoteRegistration = isLocalCallback || process.env.GITHUB_LOCAL_DEV_PAT;

      if (registration.forgeProvider === "github" && !skipRemoteRegistration) {
        const client = await getGitHubClient(db, registration.projectId);
        if (client) {
          try {
            const eventNames = registration.events.map(normalizeEventName);
            const result = await (client as any).repos.createWebhook({
              owner: registration.forgeOwner,
              repo: registration.forgeRepo,
              url: webhookCallbackUrl,
              secret,
              events: eventNames,
              active: true,
            });
            forgeWebhookId = result.data?.id != null ? String(result.data.id) : null;
          } catch (error) {
            registrationError = error instanceof Error ? error.message : String(error);
            console.error(
              `Failed to register GitHub webhook for ${registration.forgeOwner}/${registration.forgeRepo}:`,
              error,
            );
            // Continue - record in DB so the UI can show the failure state
          }
        }
      } else if (skipRemoteRegistration) {
        registrationError = isLocalCallback
          ? "skipped: callback URL is localhost (using polling sync instead)"
          : "skipped: local-dev mode (using polling sync instead)";
      }

      const rows = await db
        .insert(forgeWebhooks)
        .values({
          projectId: registration.projectId,
          forgeProvider: registration.forgeProvider,
          forgeOwner: registration.forgeOwner,
          forgeRepo: registration.forgeRepo,
          forgeWebhookId,
          webhookSecret: secret,
          events: registration.events,
          active: true,
          lastError: registrationError,
          deliveryStatus: forgeWebhookId
            ? "registered"
            : registrationError
              ? skipRemoteRegistration
                ? "skipped_local"
                : "registration_failed"
              : "unknown",
        })
        .returning();

      return { id: rows[0].id, webhookSecret: secret };
    },

    /**
     * Deactivate a webhook (marks as inactive, optionally calls forge API to unregister).
     */
    async deactivateWebhook(webhookId: string): Promise<void> {
      await db
        .update(forgeWebhooks)
        .set({ active: false, updatedAt: new Date() })
        .where(eq(forgeWebhooks.id, webhookId));
    },

    /**
     * Rotate the webhook secret for a given webhook.
     * Generates a new secret using crypto.randomBytes, updates it on the forge
     * (GitHub API), persists it in the DB, and logs an activity event.
     */
    async rotateWebhookSecret(
      webhookId: string,
      projectId: string,
      actorType: string,
      actorId: string,
    ): Promise<{ id: string; webhookSecret: string }> {
      // Look up the existing webhook
      const rows = await db
        .select()
        .from(forgeWebhooks)
        .where(
          and(
            eq(forgeWebhooks.id, webhookId),
            eq(forgeWebhooks.projectId, projectId),
          ),
        );

      if (rows.length === 0) {
        throw new Error("Webhook not found");
      }

      const webhook = rows[0];

      // Generate a new secret using crypto.randomBytes
      const newSecret = crypto.randomBytes(32).toString("hex");

      // Update the secret on GitHub if this is a GitHub webhook with a forgeWebhookId
      if (webhook.forgeProvider === "github" && webhook.forgeWebhookId) {
        const client = await getGitHubClient(db, projectId);
        if (client) {
          try {
            await (client as any).repos.updateWebhook({
              owner: webhook.forgeOwner,
              repo: webhook.forgeRepo,
              hook_id: webhook.forgeWebhookId,
              secret: newSecret,
            });
          } catch (error) {
            console.error(
              `Failed to update GitHub webhook secret for ${webhook.forgeOwner}/${webhook.forgeRepo}:`,
              error,
            );
            // Continue - DB will still be updated so the UI is consistent
          }
        }
      }

      // Persist the new secret in the database
      const updated = await db
        .update(forgeWebhooks)
        .set({ webhookSecret: newSecret, updatedAt: new Date() })
        .where(eq(forgeWebhooks.id, webhookId))
        .returning();

      await logActivity(db, {
        projectId,
        actorType: actorType as "user" | "agent" | "system",
        actorId,
        action: "forge.webhook_secret_rotated",
        entityType: "forge_webhook",
        entityId: webhookId,
        details: { forgeProvider: webhook.forgeProvider },
      });

      return { id: updated[0].id, webhookSecret: newSecret };
    },

    /**
     * List active webhooks for a project.
     */
    async listWebhooks(projectId: string) {
      return db
        .select()
        .from(forgeWebhooks)
        .where(and(eq(forgeWebhooks.projectId, projectId), eq(forgeWebhooks.active, true)));
    },

    // ── Inbound Event Processing ───────────────────────────────────────

    /**
     * Process an incoming forge event (webhook payload).
     * Maps the event to a GitMesh issue/action and triggers agent wakeups as needed.
     */
    async processEvent(event: ForgeEvent): Promise<{ issueId: string | null; wakeupIds: string[] }> {
      let issueId: string | null = null;
      const wakeupIds: string[] = [];

      // Sync the forge entity to a local issue
      if (event.forgeNumber) {
        issueId = await syncForgeIssue(db, event);
      }

      // Determine which agents should be woken up based on their role defaults
      const projectAgents = await db
        .select()
        .from(agents)
        .where(eq(agents.projectId, event.projectId));

      const heartbeat = heartbeatService(db);

      for (const agent of projectAgents) {
        const roleDef = OSS_ROLE_DEFAULTS[agent.role as keyof typeof OSS_ROLE_DEFAULTS];
        if (!roleDef) continue;

        const triggerPattern = resolveAgentTriggerPattern(agent, roleDef.heartbeatSchedule);
        if (shouldWakeForEvent(triggerPattern, event.eventType)) {
          // Route through heartbeatService.wakeup so a heartbeat_runs row is created
          // and the run loop actually picks the work up. A direct insert into
          // agent_wakeup_requests leaves the request orphaned (no run, no execution).
          let wakeupRunId: string | null = null;
          try {
            const run = await heartbeat.wakeup(agent.id, {
              source: "webhook",
              triggerDetail: event.eventType,
              reason: `forge.${event.eventType}`,
              payload: event.payload,
              requestedByActorType: "system",
              contextSnapshot: {
                source: "forge_webhook",
                eventType: event.eventType,
                forgeProvider: event.provider,
                forgeOwner: event.forgeOwner,
                forgeRepo: event.forgeRepo,
                forgeNumber: event.forgeNumber ?? null,
                issueId: issueId ?? null,
              },
            });
            if (run?.id) {
              wakeupRunId = run.id;
              wakeupIds.push(run.id);
            }
          } catch (err) {
            // wakeup throws on bad agent state (paused, terminated, pending_approval).
            // Log and continue - other agents may still be wakeable.
            console.warn(
              `[forge-sync] wakeup failed for agent ${agent.id} on ${event.eventType}:`,
              err instanceof Error ? err.message : err,
            );
          }
          // Avoid an unused-var lint hit while keeping the var available for future use.
          void wakeupRunId;

          if (issueId) {
            const skillResults = await executeSkillsForRole(agent.role, {
              db,
              event,
              projectId: event.projectId,
            });

            for (const skillResult of skillResults) {
              if (skillResult.error || !skillResult.result || typeof skillResult.result !== "object") {
                continue;
              }

              const payload = skillResult.result as Record<string, unknown>;

              const labels = Array.isArray(payload.labels)
                ? payload.labels.filter((value): value is string => typeof value === "string" && value.length > 0)
                : [];
              if (labels.length > 0) {
                await service.addForgeLabel(event.projectId, issueId, labels, agent.id);
              }

              const comment = typeof payload.comment === "string" ? payload.comment.trim() : "";
              if (comment.length > 0) {
                await service.postForgeComment(event.projectId, issueId, comment, agent.id);
              }

              const reviewers = Array.isArray(payload.reviewers)
                ? payload.reviewers.filter((value): value is string => typeof value === "string" && value.length > 0)
                : [];
              if (reviewers.length > 0) {
                await service.requestForgeReview(event.projectId, issueId, reviewers, agent.id);
              }

              const state = payload.state === "open" || payload.state === "closed" ? payload.state : null;
              if (state) {
                await service.updateForgeIssueState(event.projectId, issueId, state, agent.id);
              }
            }
          }
        }
      }

      return { issueId, wakeupIds };
    },

    // ── Outbound Actions ───────────────────────────────────────────────

    /**
     * Post a comment from an agent back to the forge.
     */
    async postForgeComment(
      projectId: string,
      issueId: string,
      body: string,
      agentId: string,
    ): Promise<{ forgeCommentId: string | null }> {
      // Look up the issue's forge details
      const issueRows = await db
        .select()
        .from(issues)
        .where(and(eq(issues.id, issueId), eq(issues.projectId, projectId)));

      const issue = issueRows[0];
      if (!issue?.forgeIssueNumber && !issue?.forgePrNumber) {
        return { forgeCommentId: null };
      }

      // Look up forge credentials and project info
      const projectRows = await db
        .select()
        .from(projects)
        .where(eq(projects.id, projectId));

      const project = projectRows[0];
      if (!project?.forgeProvider || !project?.forgeOwner || !project?.forgeRepo) {
        return { forgeCommentId: null };
      }

      // Policy check before posting comment
      const commentPolicy = await policyEngine.evaluate({
        projectId,
        agentId,
        action: "post_comment",
        context: { issueId, forgeNumber: issue.forgeIssueNumber ?? issue.forgePrNumber },
      });
      if (commentPolicy.effect === "block") {
        console.warn(
          `postForgeComment blocked by policy "${commentPolicy.policyName}": ${commentPolicy.reason}`,
        );
        return { forgeCommentId: null };
      }
      if (commentPolicy.effect === "require_approval") {
        console.warn(
          `postForgeComment requires approval from policy "${commentPolicy.policyName}": ${commentPolicy.reason}`,
        );
        // TODO: queue approval request via approvalService
        return { forgeCommentId: null };
      }

      // Get GitHub client
      if (project.forgeProvider !== "github") {
        // Delegate to GitLab client for gitlab provider
        const gitlabClient = await getGitLabClient(db, projectId);
        if (!gitlabClient) {
          console.warn(`No GitLab client available for project ${projectId}`);
          return { forgeCommentId: null };
        }

        const issueNumber = issue.forgeIssueNumber || issue.forgePrNumber;
        if (!issueNumber) {
          return { forgeCommentId: null };
        }

        const result = issue.forgePrNumber
          ? await postGitLabMrComment(gitlabClient, project.forgeOwner, project.forgeRepo, issueNumber, body)
          : await postGitLabComment(gitlabClient, project.forgeOwner, project.forgeRepo, issueNumber, body);

        const forgeCommentId = result?.commentId.toString() ?? null;

        await db.insert(issueComments).values({
          projectId,
          issueId,
          authorAgentId: agentId,
          body,
          forgeCommentId,
          syncDirection: "outbound",
        });

        return { forgeCommentId };
      }

      const client = await getGitHubClient(db, projectId);
      if (!client) {
        console.warn(`No GitHub client available for project ${projectId}`);
        return { forgeCommentId: null };
      }

      const issueNumber = issue.forgeIssueNumber || issue.forgePrNumber;
      if (!issueNumber) {
        return { forgeCommentId: null };
      }

      // Post the comment
      const result = await postGitHubComment(
        client,
        project.forgeOwner,
        project.forgeRepo,
        issueNumber,
        body,
      );

      const forgeCommentId = result?.commentId.toString() ?? null;

      // Record the outbound comment
      await db.insert(issueComments).values({
        projectId,
        issueId,
        authorAgentId: agentId,
        body,
        forgeCommentId,
        syncDirection: "outbound",
      });

      return { forgeCommentId };
    },

    /**
     * Update an issue's forge state (e.g., close or reopen on the forge).
     */
    async updateForgeIssueState(
      projectId: string,
      issueId: string,
      state: "open" | "closed",
      agentId?: string,
    ): Promise<boolean> {
      const issueRows = await db
        .select()
        .from(issues)
        .where(and(eq(issues.id, issueId), eq(issues.projectId, projectId)));

      const issue = issueRows[0];
      if (!issue?.forgeIssueNumber && !issue?.forgePrNumber) return false;

      // Look up project info
      const projectRows = await db
        .select()
        .from(projects)
        .where(eq(projects.id, projectId));

      const project = projectRows[0];
      if (!project?.forgeProvider || !project?.forgeOwner || !project?.forgeRepo) {
        return false;
      }

      // Policy check before changing forge state
      if (agentId) {
        const stateAction = state === "closed" ? "close_issue" : "reopen_issue";
        const statePolicy = await policyEngine.evaluate({
          projectId,
          agentId,
          action: stateAction,
          context: {
            issueId,
            forgeNumber: issue.forgeIssueNumber ?? issue.forgePrNumber,
            isPr: !!issue.forgePrNumber,
          },
        });
        if (statePolicy.effect === "block") {
          console.warn(
            `updateForgeIssueState(${stateAction}) blocked by policy "${statePolicy.policyName}": ${statePolicy.reason}`,
          );
          return false;
        }
        if (statePolicy.effect === "require_approval") {
          console.warn(
            `updateForgeIssueState(${stateAction}) requires approval from policy "${statePolicy.policyName}": ${statePolicy.reason}`,
          );
          // TODO: queue approval request via approvalService
          return false;
        }
      }

      // Support GitHub and GitLab for state updates
      if (project.forgeProvider === "github") {
        const client = await getGitHubClient(db, projectId);
        if (!client) {
          console.warn(`No GitHub client available for project ${projectId}`);
          return false;
        }

        const issueNumber = issue.forgeIssueNumber || issue.forgePrNumber;
        if (!issueNumber) return false;

        const success = await updateGitHubState(client, project.forgeOwner, project.forgeRepo, issueNumber, state);

        if (success) {
          await db
            .update(issues)
            .set({ forgeState: state, lastSyncedAt: new Date(), updatedAt: new Date() })
            .where(eq(issues.id, issueId));
        }

        return success;
      } else if (project.forgeProvider === "gitlab") {
        const client = await getGitLabClient(db, projectId);
        if (!client) {
          console.warn(`No GitLab client available for project ${projectId}`);
          return false;
        }

        const issueNumber = issue.forgeIssueNumber || issue.forgePrNumber;
        if (!issueNumber) return false;

        const isPr = !!issue.forgePrNumber;
        const success = await updateGitLabState(
          client,
          project.forgeOwner,
          project.forgeRepo,
          issueNumber,
          state,
          isPr ? "merge_request" : "issue",
        );

        if (success) {
          await db
            .update(issues)
            .set({ forgeState: state, lastSyncedAt: new Date(), updatedAt: new Date() })
            .where(eq(issues.id, issueId));
        }

        return success;
      }

      return false;
    },

    /**
     * Add labels to a GitHub issue or PR.
     */
    async addForgeLabel(
      projectId: string,
      issueId: string,
      labels: string[],
      agentId?: string,
    ): Promise<boolean> {
      if (labels.length === 0) return true;

      const issueRows = await db
        .select()
        .from(issues)
        .where(and(eq(issues.id, issueId), eq(issues.projectId, projectId)));

      const issue = issueRows[0];
      if (!issue?.forgeIssueNumber && !issue?.forgePrNumber) return false;

      const projectRows = await db
        .select()
        .from(projects)
        .where(eq(projects.id, projectId));

      const project = projectRows[0];
      if (!project?.forgeProvider || !project?.forgeOwner || !project?.forgeRepo) {
        return false;
      }

      // Policy check before adding labels
      if (agentId) {
        const labelPolicy = await policyEngine.evaluate({
          projectId,
          agentId,
          action: "add_label",
          context: {
            issueId,
            labels,
            forgeNumber: issue.forgeIssueNumber ?? issue.forgePrNumber,
            isPr: !!issue.forgePrNumber,
          },
        });
        if (labelPolicy.effect === "block") {
          console.warn(
            `addForgeLabel blocked by policy "${labelPolicy.policyName}": ${labelPolicy.reason}`,
          );
          return false;
        }
        if (labelPolicy.effect === "require_approval") {
          console.warn(
            `addForgeLabel requires approval from policy "${labelPolicy.policyName}": ${labelPolicy.reason}`,
          );
          // TODO: queue approval request via approvalService
          return false;
        }
      }

      if (project.forgeProvider === "github") {
        const client = await getGitHubClient(db, projectId);
        if (!client) {
          return false;
        }

        const issueNumber = issue.forgeIssueNumber || issue.forgePrNumber;
        if (!issueNumber) return false;

        return await addGitHubLabels(client, project.forgeOwner, project.forgeRepo, issueNumber, labels);
      } else if (project.forgeProvider === "gitlab") {
        const client = await getGitLabClient(db, projectId);
        if (!client) {
          return false;
        }

        const issueNumber = issue.forgeIssueNumber || issue.forgePrNumber;
        if (!issueNumber) return false;

        const isPr = !!issue.forgePrNumber;
        return await addGitLabLabels(
          client,
          project.forgeOwner,
          project.forgeRepo,
          issueNumber,
          labels,
          isPr ? "merge_request" : "issue",
        );
      }

      return false;
    },

    /**
     * Request reviewers on a GitHub PR.
     */
    async requestForgeReview(
      projectId: string,
      issueId: string,
      reviewers: string[],
      agentId?: string,
    ): Promise<boolean> {
      if (reviewers.length === 0) return true;

      const issueRows = await db
        .select()
        .from(issues)
        .where(and(eq(issues.id, issueId), eq(issues.projectId, projectId)));

      const issue = issueRows[0];
      if (!issue?.forgePrNumber) return false; // Only for PRs

      const projectRows = await db
        .select()
        .from(projects)
        .where(eq(projects.id, projectId));

      const project = projectRows[0];
      if (!project?.forgeProvider || !project?.forgeOwner || !project?.forgeRepo) {
        return false;
      }

      // Policy check before requesting review
      if (agentId) {
        const reviewPolicy = await policyEngine.evaluate({
          projectId,
          agentId,
          action: "request_review",
          context: {
            issueId,
            reviewers,
            forgeNumber: issue.forgePrNumber,
          },
        });
        if (reviewPolicy.effect === "block") {
          console.warn(
            `requestForgeReview blocked by policy "${reviewPolicy.policyName}": ${reviewPolicy.reason}`,
          );
          return false;
        }
        if (reviewPolicy.effect === "require_approval") {
          console.warn(
            `requestForgeReview requires approval from policy "${reviewPolicy.policyName}": ${reviewPolicy.reason}`,
          );
          // TODO: queue approval request via approvalService
          return false;
        }
      }

      if (project.forgeProvider === "github") {
        const client = await getGitHubClient(db, projectId);
        if (!client) {
          return false;
        }

        return await requestGitHubReviewers(
          client,
          project.forgeOwner,
          project.forgeRepo,
          issue.forgePrNumber,
          reviewers,
        );
      } else if (project.forgeProvider === "gitlab") {
        if (!issue.forgePrNumber) return false; // Only for MRs

        const client = await getGitLabClient(db, projectId);
        if (!client) {
          return false;
        }

        return await requestGitLabReviewers(
          client,
          project.forgeOwner,
          project.forgeRepo,
          issue.forgePrNumber,
          reviewers,
        );
      }

      return false;
    },
  };

  return service;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateWebhookSecret(): string {
  // Use crypto.randomBytes for unpredictable secrets. Math.random is not a CSPRNG
  // and would let an attacker who can guess timing predict webhook secrets.
  return crypto.randomBytes(40).toString("hex");
}

/**
 * Determine if an agent with a given heartbeat schedule trigger should
 * be woken for a specific forge event type.
 */
function shouldWakeForEvent(triggerPattern: string, eventType: ForgeEventType): boolean {
  // Schedule patterns like "on:pr_opened" match specific events
  if (triggerPattern.startsWith("on:")) {
    const pattern = triggerPattern.slice(3);
    // Support comma-separated event lists: "on:pr_opened,pr_review_requested"
    const triggers = pattern.split(",");
    return triggers.some((t) => eventType.startsWith(t.trim()));
  }
  // Non-event-driven schedules (hourly, daily, etc.) don't trigger on forge events
  return false;
}

function resolveAgentTriggerPattern(
  agent: { runtimeConfig: Record<string, unknown> | null; metadata: Record<string, unknown> | null },
  fallback: string,
): string {
  const runtimeConfig =
    typeof agent.runtimeConfig === "object" && agent.runtimeConfig !== null ? agent.runtimeConfig : {};
  const metadata = typeof agent.metadata === "object" && agent.metadata !== null ? agent.metadata : {};

  const heartbeat =
    typeof runtimeConfig.heartbeat === "object" && runtimeConfig.heartbeat !== null
      ? (runtimeConfig.heartbeat as Record<string, unknown>)
      : {};

  const runtimeSchedule = typeof heartbeat.schedule === "string" ? heartbeat.schedule.trim() : "";
  if (runtimeSchedule) return runtimeSchedule;

  const metadataSchedule =
    typeof metadata.heartbeatSchedule === "string" ? metadata.heartbeatSchedule.trim() : "";
  if (metadataSchedule) return metadataSchedule;

  return fallback;
}

/**
 * Sync a forge issue/PR to a local GitMesh issue.
 * Creates the issue if it doesn't exist, or updates its forge metadata.
 */
async function syncForgeIssue(db: Db, event: ForgeEvent): Promise<string | null> {
  if (!event.forgeNumber) return null;

  const projectId = event.projectId;
  const isIssue = event.eventType.startsWith("issue_");
  const isPr = event.eventType.startsWith("pr_");

  // Look for existing issue mapped to this forge number
  const existing = await db
    .select()
    .from(issues)
    .where(
      and(
        eq(issues.projectId, projectId),
        isIssue
          ? eq(issues.forgeIssueNumber, event.forgeNumber)
          : eq(issues.forgePrNumber, event.forgeNumber),
      ),
    );

  if (existing.length > 0) {
    // Update forge state
    const forgeState = deriveForgeState(event.eventType);
    if (forgeState) {
      await db
        .update(issues)
        .set({
          forgeState,
          forgeUrl: event.forgeUrl ?? existing[0].forgeUrl,
          lastSyncedAt: new Date(),
          updatedAt: new Date(),
        })
        .where(eq(issues.id, existing[0].id));
    }
    return existing[0].id;
  }

  // Create a new issue for this forge entity
  if (event.eventType === "issue_opened" || event.eventType === "pr_opened") {
    const rows = await db
      .insert(issues)
      .values({
        projectId,
        title: event.title ?? `${isPr ? "PR" : "Issue"} #${event.forgeNumber}`,
        description: event.body ?? null,
        status: "backlog",
        priority: "medium",
        forgeIssueNumber: isIssue ? event.forgeNumber : null,
        forgePrNumber: isPr ? event.forgeNumber : null,
        forgeUrl: event.forgeUrl ?? null,
        forgeState: "open",
        lastSyncedAt: new Date(),
      })
      .returning();
    return rows[0]?.id ?? null;
  }

  return null;
}

function deriveForgeState(eventType: ForgeEventType): string | null {
  switch (eventType) {
    case "issue_opened":
    case "issue_reopened":
    case "pr_opened":
      return "open";
    case "issue_closed":
    case "pr_closed":
      return "closed";
    case "pr_merged":
      return "merged";
    default:
      return null;
  }
}

// ─── Periodic Pull-Based Sync ─────────────────────────────────────────────────

const syncIntervals = new Map<string, ReturnType<typeof setInterval>>();

/**
 * Start periodic polling to pull latest issues from the forge for a project.
 * Runs immediately once, then repeats at the given interval (default 5 minutes).
 * Returns a cleanup function to stop polling.
 */
export async function startPeriodicSync(db: Db, projectId: string, intervalMs = 5 * 60 * 1000): Promise<() => void> {
  if (syncIntervals.has(projectId)) return () => {};

  // Run once immediately
  try {
    await syncProjectIssues(db, projectId);
  } catch (err) {
    console.error(`[forge-sync] Initial periodic sync failed for project ${projectId}:`, err);
  }

  const interval = setInterval(async () => {
    try {
      await syncProjectIssues(db, projectId);
      console.log(`[forge-sync] Periodic sync completed for project ${projectId}`);
    } catch (err) {
      console.error(`[forge-sync] Periodic sync failed for project ${projectId}:`, err);
    }
  }, intervalMs);

  syncIntervals.set(projectId, interval);
  return () => {
    clearInterval(interval);
    syncIntervals.delete(projectId);
  };
}

/**
 * Pull all open issues from GitHub and upsert them into the issues table.
 */
export async function syncProjectIssues(db: Db, projectId: string) {
  const projectRows = await db
    .select()
    .from(projects)
    .where(eq(projects.id, projectId));
  const project = projectRows[0];
  if (!project?.forgeOwner || !project?.forgeRepo) return;

  const octokit = await getGitHubClient(db, projectId);
  if (!octokit) return;

  // Pre-fetch existing local issue states so we can detect transitions and
  // only fire processEvent (= wake agents) on actual changes. Without this,
  // every 5-minute poll would re-fire wakeups for every open issue.
  const existingIssues = await db
    .select({
      id: issues.id,
      forgeIssueNumber: issues.forgeIssueNumber,
      forgeState: issues.forgeState,
    })
    .from(issues)
    .where(eq(issues.projectId, projectId));
  const existingByNumber = new Map<number, { id: string; forgeState: string | null }>();
  for (const row of existingIssues) {
    if (row.forgeIssueNumber !== null) {
      existingByNumber.set(row.forgeIssueNumber, { id: row.id, forgeState: row.forgeState });
    }
  }

  const svc = forgeSyncService(db);

  try {
    const { data: ghIssues } = await octokit.rest.issues.listForRepo({
      owner: project.forgeOwner,
      repo: project.forgeRepo,
      per_page: 100,
      state: "all",
    });

    for (const ghIssue of ghIssues) {
      // Filter out pull requests (they appear in the issues endpoint too)
      if ("pull_request" in ghIssue && ghIssue.pull_request) continue;
      // Filter out very old closed issues
      if (ghIssue.state === "closed" && ghIssue.closed_at) {
        const closedAt = new Date(ghIssue.closed_at).getTime();
        const thirtyDaysAgo = Date.now() - 30 * 24 * 60 * 60 * 1000;
        if (closedAt < thirtyDaysAgo) continue;
      }

      const newState = ghIssue.state === "open" ? "open" : "closed";
      const prior = existingByNumber.get(ghIssue.number);
      const isNew = !prior;
      const stateChanged = prior !== undefined && prior.forgeState !== newState;
      const eventType: ForgeEventType =
        ghIssue.state === "open"
          ? prior && prior.forgeState === "closed"
            ? "issue_reopened"
            : "issue_opened"
          : "issue_closed";

      if (isNew || stateChanged) {
        // Drive the full pipeline (upsert + agent wakeup) for transitions.
        await svc.processEvent({
          provider: "github",
          eventType,
          projectId,
          payload: ghIssue as unknown as Record<string, unknown>,
          forgeOwner: project.forgeOwner,
          forgeRepo: project.forgeRepo,
          forgeNumber: ghIssue.number,
          forgeUrl: ghIssue.html_url,
          authorLogin: ghIssue.user?.login ?? "unknown",
          title: ghIssue.title,
          body: ghIssue.body ?? "",
        });
      } else {
        // No transition - just refresh local mirror without waking agents.
        await syncForgeIssue(db, {
          provider: "github",
          eventType,
          projectId,
          payload: ghIssue as unknown as Record<string, unknown>,
          forgeOwner: project.forgeOwner,
          forgeRepo: project.forgeRepo,
          forgeNumber: ghIssue.number,
          forgeUrl: ghIssue.html_url,
          authorLogin: ghIssue.user?.login ?? "unknown",
          title: ghIssue.title,
          body: ghIssue.body ?? "",
        });
      }
    }

    await db
      .update(projects)
      .set({ lastSyncedAt: new Date() })
      .where(eq(projects.id, projectId));
  } catch (err) {
    console.error("[forge-sync] syncProjectIssues error:", err);
  }
}

/**
 * Map an internal forge event name to the wire format expected by the forge API.
 * E.g. "issue_opened" → "issues", "pr_opened" → "pull_request", etc.
 */
function normalizeEventName(event: string): string {
  switch (event) {
    case "issue_opened":
    case "issue_closed":
    case "issue_reopened":
      return "issues";
    case "issue_comment":
      return "issue_comment";
    case "pr_opened":
    case "pr_closed":
    case "pr_merged":
    case "pr_review_requested":
    case "pr_review_submitted":
    case "pr_comment":
      return "pull_request";
    case "push":
      return "push";
    case "release_published":
      return "release";
    case "security_advisory":
      return "security_advisories";
    default:
      return event;
  }
}
