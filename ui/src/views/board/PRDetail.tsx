import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "@/lib/router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { pullRequestsApi } from "../../api/pull-requests";
import { issuesApi } from "../../api/issues";
import { auditLogApi } from "../../api/audit-log";
import { agentsApi } from "../../api/agents";
import { useProject } from "../../context/ProjectContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { relativeTime, cn } from "../../lib/utils";
import { Identity } from "../../components/Identity";
import { StatusBadge } from "../../components/StatusBadge";
import { CommentThread } from "../../features/CommentThread";
import { EmptyState } from "../../components/EmptyState";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  GitPullRequest,
  GitMerge,
  XCircle,
  ExternalLink,
  ChevronDown,
  MessageSquare,
  Activity,
  ListTree,
} from "lucide-react";
import type { Agent } from "@gitmesh/core";
import type { RunForIssue } from "../../api/audit-log";
import type { PullRequestStatus } from "../../api/pull-requests";

const STATUS_CLASSES: Record<PullRequestStatus, string> = {
  open: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  merged: "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  closed: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
};

const STATUS_ICONS: Record<PullRequestStatus, typeof GitPullRequest> = {
  open: GitPullRequest,
  merged: GitMerge,
  closed: XCircle,
};

const ACTION_LABELS: Record<string, string> = {
  "pr.opened": "opened the pull request",
  "pr.updated": "updated the pull request",
  "pr.merged": "merged the pull request",
  "pr.closed": "closed the pull request",
  "issue.comment_added": "added a comment",
  "issue.updated": "updated the issue",
};

function formatAction(action: string): string {
  return ACTION_LABELS[action] ?? action.replace(/[._]/g, " ");
}

function ActorIdentity({
  evt,
  agentMap,
}: {
  evt: { actorId: string; actorType: string };
  agentMap: Map<string, Agent>;
}) {
  const id = evt.actorId;
  if (evt.actorType === "agent") {
    const agent = agentMap.get(id);
    return <Identity name={agent?.name ?? id.slice(0, 8)} size="sm" />;
  }
  if (evt.actorType === "system") return <Identity name="System" size="sm" />;
  if (evt.actorType === "user") return <Identity name="Maintainer" size="sm" />;
  return <Identity name={id || "Unknown"} size="sm" />;
}

export function PRDetail() {
  const { prId } = useParams<{ prId: string }>();
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const queryClient = useQueryClient();
  const [detailTab, setDetailTab] = useState("comments");
  const [secondaryOpen, setSecondaryOpen] = useState({ runs: false });

  const { data: pr, isLoading, error } = useQuery({
    queryKey: queryKeys.pullRequests.detail(prId!),
    queryFn: () => pullRequestsApi.get(prId!),
    enabled: !!prId,
  });

  const projectId = pr?.projectId ?? selectedProjectId ?? "";

  const { data: comments } = useQuery({
    queryKey: queryKeys.issues.comments(prId!),
    queryFn: () => issuesApi.listComments(prId!),
    enabled: !!prId,
  });

  const { data: activity } = useQuery({
    queryKey: queryKeys.issues.activity(prId!),
    queryFn: () => auditLogApi.forIssue(prId!),
    enabled: !!prId,
  });

  const { data: linkedRuns } = useQuery({
    queryKey: queryKeys.issues.runs(prId!),
    queryFn: () => auditLogApi.runsForIssue(prId!),
    enabled: !!prId,
    refetchInterval: 5000,
  });

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(projectId),
    queryFn: () => agentsApi.list(projectId),
    enabled: !!projectId,
  });

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    for (const a of agents ?? []) map.set(a.id, a);
    return map;
  }, [agents]);

  const updatePr = useMutation({
    mutationFn: (data: { action: string }) => pullRequestsApi.update(prId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pullRequests.detail(prId!) });
      queryClient.invalidateQueries({ queryKey: queryKeys.pullRequests.list(selectedProjectId!) });
    },
  });

  useEffect(() => {
    if (!pr) return;
    setBreadcrumbs([
      { label: "Pull Requests", href: "/prs" },
      { label: pr.title },
    ]);
  }, [setBreadcrumbs, pr]);

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading...</p>;
  if (error) return <p className="text-sm text-destructive">{error.message}</p>;
  if (!pr) return null;

  const StatusIcon = STATUS_ICONS[pr.status] ?? GitPullRequest;
  const statusLabel = pr.status.charAt(0).toUpperCase() + pr.status.slice(1);

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3 min-w-0">
        <StatusIcon
          className={cn(
            "h-5 w-5 shrink-0 mt-1",
            pr.status === "open" && "text-green-600 dark:text-green-400",
            pr.status === "merged" && "text-purple-600 dark:text-purple-400",
            pr.status === "closed" && "text-red-600 dark:text-red-400",
          )}
          strokeWidth={1.75}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {pr.forgePrNumber && (
              <span className="font-mono text-sm text-muted-foreground shrink-0">!{pr.forgePrNumber}</span>
            )}
            {pr.identifier && (
              <span className="font-mono text-sm text-muted-foreground shrink-0">{pr.identifier}</span>
            )}
            <span
              className={cn(
                "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold capitalize tracking-wide",
                STATUS_CLASSES[pr.status],
              )}
            >
              {statusLabel}
            </span>
          </div>
          <h1 className="text-xl font-bold break-words">{pr.title}</h1>
          <div className="flex items-center gap-2 mt-1.5 text-xs text-muted-foreground flex-wrap">
            {pr.authorAgentId && (
              <Identity name={pr.authorAgentId.slice(0, 8)} size="xs" />
            )}
            {pr.authorUserId && (
              <Identity
                name={pr.authorUserId === "local-board" ? "Maintainer" : pr.authorUserId}
                size="xs"
              />
            )}
            <span>opened {relativeTime(pr.createdAt)}</span>
            {pr.lastSyncedAt && (
              <span className="text-muted-foreground/60">synced {relativeTime(pr.lastSyncedAt)}</span>
            )}
          </div>
        </div>

        {/* Forge link */}
        {pr.forgeUrl && (
          <a
            href={pr.forgeUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground border border-border rounded-md px-2 py-1 shrink-0"
          >
            <ExternalLink className="h-3 w-3" />
            View on forge
          </a>
        )}
      </div>

      {/* Labels */}
      {(pr.labels ?? []).length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          {(pr.labels ?? []).map((label) => (
            <span
              key={label.id}
              className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium"
              style={{
                borderColor: label.color,
                color: label.color,
                backgroundColor: `${label.color}1f`,
              }}
            >
              {label.name}
            </span>
          ))}
        </div>
      )}

      {/* Description */}
      {pr.description && (
        <div className="rounded-lg border border-border bg-card px-4 py-3">
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{pr.description}</p>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        {pr.status === "open" && (
          <>
            <Button
              size="sm"
              variant="default"
              className="bg-green-600 hover:bg-green-700"
              onClick={() => updatePr.mutate({ action: "merge" })}
              disabled={updatePr.isPending}
            >
              <GitMerge className="h-3.5 w-3.5 mr-1.5" />
              {updatePr.isPending ? "Merging..." : "Merge"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => updatePr.mutate({ action: "close" })}
              disabled={updatePr.isPending}
            >
              <XCircle className="h-3.5 w-3.5 mr-1.5" />
              Close
            </Button>
          </>
        )}
        {pr.status === "merged" && (
          <span className="flex items-center gap-1.5 text-sm text-purple-600 dark:text-purple-400">
            <GitMerge className="h-4 w-4" />
            This PR has been merged
          </span>
        )}
        {pr.status === "closed" && (
          <span className="flex items-center gap-1.5 text-sm text-red-600 dark:text-red-400">
            <XCircle className="h-4 w-4" />
            This PR is closed
          </span>
        )}
        {updatePr.error && (
          <p className="text-xs text-destructive">
            {(updatePr.error as Error).message}
          </p>
        )}
      </div>

      <Separator />

      {/* Tabs */}
      <Tabs value={detailTab} onValueChange={setDetailTab} className="space-y-3">
        <TabsList variant="line" className="w-full justify-start gap-1">
          <TabsTrigger value="comments" className="gap-1.5">
            <MessageSquare className="h-3.5 w-3.5" />
            Comments
          </TabsTrigger>
          <TabsTrigger value="linked-issues" className="gap-1.5">
            <ListTree className="h-3.5 w-3.5" />
            Linked Issues
          </TabsTrigger>
          <TabsTrigger value="activity" className="gap-1.5">
            <Activity className="h-3.5 w-3.5" />
            Activity
          </TabsTrigger>
        </TabsList>

        <TabsContent value="comments">
          {comments && comments.length > 0 ? (
            <CommentThread
              comments={comments}
              linkedRuns={[]}
              issueStatus="backlog"
              agentMap={agentMap}
              draftKey={`gitmesh-agents:pr-comment-draft:${pr.id}`}
              onAdd={async (_body, _reopen) => {
                // PR comments not yet wired - agents can post via forge-sync
              }}
            />
          ) : (
            <p className="text-xs text-muted-foreground">No comments yet.</p>
          )}
        </TabsContent>

        <TabsContent value="linked-issues">
          {(pr.linkedIssues ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No linked issues. Issues mentioning #{pr.forgePrNumber} in their description will appear here.
            </p>
          ) : (
            <div className="border border-border rounded-lg divide-y divide-border">
              {(pr.linkedIssues ?? []).map((issue) => (
                <Link
                  key={issue.id}
                  to={`/issues/${issue.identifier ?? issue.id}`}
                  className="flex items-center justify-between px-3 py-2 text-sm hover:bg-accent/20 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusBadge status={issue.status} />
                    <span className="font-mono text-muted-foreground shrink-0">
                      {issue.identifier ?? issue.id.slice(0, 8)}
                    </span>
                    <span className="truncate">{issue.title}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="activity">
          {!activity || activity.length === 0 ? (
            <p className="text-xs text-muted-foreground">No activity yet.</p>
          ) : (
            <div className="space-y-1.5">
              {activity.slice(0, 30).map((evt) => (
                <div
                  key={evt.id}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground"
                >
                  <ActorIdentity evt={evt} agentMap={agentMap} />
                  <span>{formatAction(evt.action)}</span>
                  <span className="ml-auto shrink-0">{relativeTime(evt.createdAt)}</span>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Agent runs */}
      {linkedRuns && linkedRuns.length > 0 && (
        <Collapsible
          open={secondaryOpen.runs}
          onOpenChange={(open) => setSecondaryOpen((prev) => ({ ...prev, runs: open }))}
          className="rounded-lg border border-border"
        >
          <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-left">
            <span className="text-sm font-medium text-muted-foreground">
              Agent Runs ({linkedRuns.length})
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 text-muted-foreground transition-transform",
                secondaryOpen.runs && "rotate-180",
              )}
            />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="border-t border-border divide-y divide-border">
              {linkedRuns.map((run) => (
                <div
                  key={run.runId}
                  className="flex items-center justify-between px-3 py-2 text-xs"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusBadge status={run.status} />
                    <span className="font-mono text-muted-foreground shrink-0">
                      {run.runId.slice(0, 8)}
                    </span>
                    <span className="truncate">{run.invocationSource}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {(() => {
                      const agentName = agentMap.get(run.agentId)?.name;
                      return agentName ? (
                        <Identity name={agentName} size="xs" />
                      ) : (
                        <span className="text-muted-foreground font-mono">
                          {run.agentId.slice(0, 8)}
                        </span>
                      );
                    })()}
                    <span className="text-muted-foreground">
                      {run.startedAt ? relativeTime(run.startedAt) : relativeTime(run.createdAt)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
