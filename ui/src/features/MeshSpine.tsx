/**
 * MeshSpine - the signature persistent left timeline.
 *
 * Renders the project's activity log as a vertical commit-graph-style
 * thread. Each node is colored by policy outcome (verdict: allow / block /
 * require_approval) and shows the action verb + entity + attestation
 * status inline. A short list of *currently running* heartbeats sits at
 * the top as a Datadog-style mini-waterfall.
 *
 * Instead of a stacked deck of cards (overview / activity / runs / charts),
 * the operator sees everything that happened and is happening as one
 * dense thread.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@/lib/router";
import type { ActivityEvent } from "@gitmesh/core";
import { useProject } from "../context/ProjectContext";
import { auditLogApi } from "../api/audit-log";
import { heartbeatsApi, type LiveRunForIssue } from "../api/heartbeats";
import {
  attestationsApi,
  type AttestationStatusBulkResponse,
} from "../api/attestations";
import { queryKeys } from "../lib/queryKeys";
import { timeAgo } from "../lib/timeAgo";
import { AttestationBadge } from "./AttestationBadge";

type Verdict = "allow" | "block" | "require_approval" | "pending" | "neutral";

function deriveVerdict(event: ActivityEvent): Verdict {
  const outcome = event.policyOutcome;
  if (outcome === "allowed") return "allow";
  if (outcome === "blocked") return "block";
  if (outcome === "require_approval") return "require_approval";
  if (event.action.includes("blocked") || event.action.includes("error") || event.action.includes("failed")) return "block";
  if (event.action.includes("approval") || event.action.includes("pending")) return "pending";
  return "neutral";
}

function compactVerb(action: string): string {
  // shorten action token for the spine ("issue.checked_out" -> "checkout")
  const last = action.split(".").pop() ?? action;
  return last.replace(/_/g, " ");
}

function entityLabel(event: ActivityEvent): string {
  if (event.entityType && event.entityId) {
    const idShort = event.entityId.slice(0, 8);
    if (event.entityType === "agent_policy") return `policy ${idShort}`;
    if (event.entityType === "policy_evaluation") return `decision ${idShort}`;
    if (event.entityType === "issue") return `issue ${idShort}`;
    if (event.entityType === "agent") return `worker ${idShort}`;
    if (event.entityType === "heartbeat_run") return `run ${idShort}`;
    return `${event.entityType} ${idShort}`;
  }
  return "-";
}

export function MeshSpine() {
  const { selectedProjectId } = useProject();

  const { data: events = [] } = useQuery<ActivityEvent[]>({
    queryKey: queryKeys.auditLog(selectedProjectId!),
    queryFn: () => auditLogApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
    refetchInterval: 5_000,
  });

  const { data: liveRuns = [] } = useQuery<LiveRunForIssue[]>({
    queryKey: queryKeys.liveRuns(selectedProjectId!),
    queryFn: () => heartbeatsApi.liveRunsForProject(selectedProjectId!),
    enabled: !!selectedProjectId,
    refetchInterval: 3_000,
  });

  const recentEvents = useMemo(() => events.slice(0, 80), [events]);

  const recentEventIds = useMemo(
    () => recentEvents.map((e) => e.id).filter((id): id is string => Boolean(id)),
    [recentEvents],
  );

  // Bulk-fetch attestation status for everything currently visible. One
  // round-trip replaces the previous N per-row 404s.
  const { data: attestationStatuses } = useQuery<AttestationStatusBulkResponse>({
    queryKey: ["attestation-status", selectedProjectId, recentEventIds],
    queryFn: () => attestationsApi.bulkStatus(selectedProjectId!, recentEventIds),
    enabled: !!selectedProjectId && recentEventIds.length > 0,
    staleTime: 30_000,
    refetchInterval: (q) =>
      q.state.data && Object.values(q.state.data.statuses).some((s) => s === "pending")
        ? 5_000
        : false,
  });

  if (!selectedProjectId) {
    return (
      <aside className="mesh-spine flex h-full w-[340px] shrink-0 items-center justify-center px-6 text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-text-tertiary">
          Select a project
        </p>
      </aside>
    );
  }

  return (
    <aside className="mesh-spine flex h-full w-[340px] shrink-0 flex-col">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.20em] text-text-tertiary">
          Mesh - live ledger
        </span>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-[var(--verdict-attested)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--verdict-attested)] gm-pulse-dot" />
          {liveRuns.length} live
        </span>
      </header>

      {/* Live waterfall - sticky band at the top of the spine */}
      {liveRuns.length > 0 && (
        <div className="border-b border-border bg-[color:color-mix(in_oklab,var(--verdict-attested)_4%,transparent)]">
          {liveRuns.slice(0, 4).map((run) => (
            <div key={run.id} className="px-4 py-2">
              <div className="flex items-center justify-between">
                <span className="truncate font-mono text-[11px] text-foreground">
                  {run.agentName ?? run.agentId.slice(0, 8)}
                </span>
                <span className="font-mono text-[10px] text-text-tertiary">
                  {run.status}
                </span>
              </div>
              <div className="mt-1 gm-waterfall-bar" data-state="running">
                <span style={{ left: 0, right: "8%" }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Event spine */}
      <div className="gitmesh-scrollbar flex-1 overflow-y-auto">
        {recentEvents.length === 0 && (
          <div className="px-4 py-8 text-center font-mono text-[11px] uppercase tracking-[0.18em] text-text-tertiary">
            No activity yet
          </div>
        )}
        <ol className="m-0 list-none space-y-0 p-0 px-4">
          {recentEvents.map((event) => {
            const verdict = deriveVerdict(event);
            return (
              <li key={event.id} className="flex gap-3 py-2">
                <div className="flex w-7 shrink-0 justify-center pt-3">
                  <span
                    className="mesh-node"
                    data-verdict={verdict === "neutral" ? "" : verdict}
                  />
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] uppercase tracking-wide text-text-secondary">
                      {compactVerb(event.action)}
                    </span>
                    {verdict !== "neutral" && (
                      <span className="verdict-chip" data-verdict={verdict}>
                        {verdict.replace("_", " ")}
                      </span>
                    )}
                  </div>
                  <Link
                    to={`/audit#${event.id}`}
                    className="truncate font-mono text-[11px] text-text-tertiary hover:text-foreground"
                  >
                    {entityLabel(event)}
                  </Link>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-text-tertiary">
                      {timeAgo(event.createdAt)}
                    </span>
                    {event.id && (
                      <AttestationBadge
                        projectId={selectedProjectId}
                        activityId={event.id}
                        status={attestationStatuses?.statuses[event.id]}
                        size="xs"
                      />
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </aside>
  );
}
