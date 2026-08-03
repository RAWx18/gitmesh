/**
 * Dashboard - the "Mesh" view (forge instrumentation, not company dashboard).
 *
 * Intentional layout choices:
 *   - No four-up KPI band, no chart grid, no editorial hero header.
 *   - The persistent left MeshSpine carries the ledger; this main pane is
 *     for what's *running now* and what *needs the operator* - both
 *     rendered as a Datadog-style trace waterfall + a single dense list.
 *   - Numbers are mono ticker cells. Chrome is hairlines, not cards.
 */
import { useEffect, useMemo } from "react";
import { Link } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "../../api/dashboard";
import { issuesApi } from "../../api/issues";
import { agentsApi } from "../../api/agents";
import { heartbeatsApi } from "../../api/heartbeats";
import { useProject } from "../../context/ProjectContext";
import { useDialog } from "../../context/DialogContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { EmptyState } from "../../components/EmptyState";
import { GitHubReposPanel } from "@/features/GitHubReposPanel";
import { PriorityIcon } from "../../components/PriorityIcon";
import { StatusIcon } from "../../components/StatusIcon";
import { timeAgo } from "../../lib/timeAgo";
import { cn, formatCents } from "../../lib/utils";
import { Network, Bot } from "lucide-react";
import { PageSkeleton } from "../../components/PageSkeleton";
import type { Issue } from "@gitmesh/core";

function getRecentIssues(issues: Issue[]): Issue[] {
  return [...issues].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

export function Dashboard() {
  const { selectedProject, selectedProjectId, projects } = useProject();
  const { openOnboarding } = useDialog();
  const { setBreadcrumbs } = useBreadcrumbs();

  useEffect(() => {
    setBreadcrumbs([{ label: "Mesh" }]);
  }, [setBreadcrumbs]);

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.dashboard(selectedProjectId!),
    queryFn: () => dashboardApi.summary(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: issues } = useQuery({
    queryKey: queryKeys.issues.list(selectedProjectId!),
    queryFn: () => issuesApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: liveRuns = [] } = useQuery({
    queryKey: queryKeys.liveRuns(selectedProjectId!),
    queryFn: () => heartbeatsApi.liveRunsForProject(selectedProjectId!),
    enabled: !!selectedProjectId,
    refetchInterval: 3_000,
  });

  const recentIssues = useMemo(() => (issues ? getRecentIssues(issues) : []), [issues]);
  const blockedIssues = useMemo(
    () => (issues ?? []).filter((i) => i.status === "blocked").slice(0, 6),
    [issues],
  );

  if (!selectedProjectId) {
    if (projects.length === 0) {
      return (
        <EmptyState
          icon={Network}
          message="GitMesh - forge instrumentation. Connect a repo to start the mesh."
          action="Get started"
          onAction={openOnboarding}
        />
      );
    }
    return <EmptyState icon={Network} message="Select a project to bring up the mesh." />;
  }

  if (isLoading) return <PageSkeleton variant="dashboard" />;

  const hasNoAgents = agents !== undefined && agents.length === 0;
  const budgetUtilization = selectedProject?.budgetMonthlyCents
    ? Math.round((selectedProject.spentMonthlyCents / selectedProject.budgetMonthlyCents) * 100)
    : null;

  return (
    <div className="-mx-4 -my-5 md:-mx-6 md:-my-6 lg:-mx-8 flex flex-col">
      {error && (
        <div className="border-b border-[var(--verdict-block)]/40 bg-[var(--verdict-block)]/10 px-4 py-2 font-mono text-[11px] text-[var(--verdict-block)]">
          {(error as Error).message}
        </div>
      )}

      {hasNoAgents && (
        <div className="flex items-center justify-between gap-3 border-b border-[var(--verdict-pending)]/40 bg-[var(--verdict-pending)]/8 px-4 py-2 font-mono text-[11px]">
          <div className="flex items-center gap-2">
            <Bot className="h-3.5 w-3.5 shrink-0 text-[var(--verdict-pending)]" />
            <span className="text-foreground">No workers enabled. The forge is silent.</span>
          </div>
          <button
            onClick={() => openOnboarding({ initialStep: 2, projectId: selectedProjectId! })}
            className="shrink-0 uppercase tracking-[0.10em] text-foreground underline decoration-[var(--verdict-pending)] underline-offset-2 hover:decoration-foreground"
          >
            create one
          </button>
        </div>
      )}

      {data && (
        <>
          {/* ── Header strip - mono, terminal-style ──────────────────────── */}
          <header className="border-b border-border px-4 py-3 md:px-6">
            <div className="flex items-baseline justify-between gap-4">
              <div className="min-w-0">
                <h1 className="font-mono text-[15px] font-semibold tracking-tight text-foreground">
                  {selectedProject?.name ?? "mesh"}
                </h1>
                <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.10em] text-text-tertiary">
                  {selectedProject?.forgeOwner && selectedProject.forgeRepo
                    ? `${selectedProject.forgeOwner}/${selectedProject.forgeRepo}`
                    : "no forge linked"}
                </p>
              </div>
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary">
                {selectedProject?.requireOperatorApprovalForNewAgents && (
                  <span className="verdict-chip" data-verdict="require_approval">
                    operator gate
                  </span>
                )}
                {liveRuns.length > 0 && (
                  <span className="verdict-chip" data-verdict="attested">
                    {liveRuns.length} live
                  </span>
                )}
              </div>
            </div>
          </header>

          {/* ── Ticker ─────────────────────────────────────────────────────── */}
          <div className="gm-ticker">
            <Link to="/agents" className="gm-ticker-cell hover:bg-surface-2">
              <span className="gm-ticker-label">running</span>
              <span
                className={cn(
                  "gm-ticker-value",
                  data.agents.running > 0 && "text-[var(--verdict-attested)]",
                )}
              >
                {data.agents.running}
              </span>
            </Link>
            <Link to="/issues" className="gm-ticker-cell hover:bg-surface-2">
              <span className="gm-ticker-label">open tasks</span>
              <span className="gm-ticker-value">{data.tasks.open}</span>
            </Link>
            <Link to="/approvals" className="gm-ticker-cell hover:bg-surface-2">
              <span className="gm-ticker-label">at gate</span>
              <span
                className={cn(
                  "gm-ticker-value",
                  data.pendingApprovals > 0 && "text-[var(--verdict-pending)]",
                )}
              >
                {data.pendingApprovals}
              </span>
            </Link>
            <Link to="/costs" className="gm-ticker-cell hover:bg-surface-2">
              <span className="gm-ticker-label">budget</span>
              <span
                className={cn(
                  "gm-ticker-value",
                  budgetUtilization != null && budgetUtilization > 85 && "text-[var(--verdict-block)]",
                  budgetUtilization != null && budgetUtilization > 60 && budgetUtilization <= 85 && "text-[var(--verdict-pending)]",
                )}
              >
                {budgetUtilization != null ? `${budgetUtilization}%` : "-"}
              </span>
            </Link>
            <div className="gm-ticker-cell">
              <span className="gm-ticker-label">month spend</span>
              <span className="gm-ticker-value">{formatCents(data.costs.monthSpendCents)}</span>
            </div>
          </div>

          {/* ── Trace waterfall - running heartbeats ─────────────────────── */}
          <section className="border-b border-border">
            <header className="flex items-center justify-between px-4 py-2 md:px-6">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
                live trace · {liveRuns.length}
              </h2>
              <Link
                to="/agents/active"
                className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary hover:text-foreground"
              >
                workers →
              </Link>
            </header>
            {liveRuns.length === 0 ? (
              <div className="px-4 py-6 md:px-6">
                <p className="font-mono text-[11px] text-text-tertiary">
                  Mesh is quiet. No heartbeats running.
                </p>
              </div>
            ) : (
              <div>
                {liveRuns.slice(0, 8).map((run) => {
                  const startedAt = run.startedAt ? new Date(run.startedAt).getTime() : null;
                  const elapsedMs = startedAt ? Date.now() - startedAt : 0;
                  const widthPct = Math.max(2, Math.min(96, (elapsedMs / 60_000) * 12));
                  return (
                    <div key={run.id} className="gm-waterfall-row">
                      <Link
                        to={`/agents/${run.agentId}`}
                        className="truncate text-foreground hover:text-[var(--verdict-attested)]"
                      >
                        {run.agentName ?? run.agentId.slice(0, 8)}
                      </Link>
                      <div className="gm-waterfall-bar" data-state="running">
                        <span style={{ left: 0, width: `${widthPct}%` }} />
                      </div>
                      <span className="text-right text-text-tertiary">
                        {Math.round(elapsedMs / 1000)}s
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* ── Blocked + recent - two-column terminal lists ─────────────── */}
          <section className="grid grid-cols-1 gap-0 border-b border-border md:grid-cols-2">
            <div className="border-b border-border md:border-b-0 md:border-r md:border-border">
              <header className="flex items-center justify-between px-4 py-2 md:px-6">
                <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
                  blocked · {blockedIssues.length}
                </h2>
                <Link
                  to="/issues"
                  className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary hover:text-foreground"
                >
                  all →
                </Link>
              </header>
              {blockedIssues.length === 0 ? (
                <div className="px-4 py-6 md:px-6">
                  <p className="font-mono text-[11px] text-text-tertiary">No blocked tasks.</p>
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {blockedIssues.map((issue) => (
                    <li key={issue.id}>
                      <Link
                        to={`/issues/${issue.identifier ?? issue.id}`}
                        className="flex items-center gap-3 px-4 py-2 font-mono text-[12px] hover:bg-surface-2 md:px-6"
                      >
                        <PriorityIcon priority={issue.priority} />
                        <span className="text-text-tertiary shrink-0">
                          {issue.identifier ?? issue.id.slice(0, 6)}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-foreground">{issue.title}</span>
                        <span className="text-[10px] text-text-tertiary">{timeAgo(issue.updatedAt)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <header className="flex items-center justify-between px-4 py-2 md:px-6">
                <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
                  recent · {Math.min(recentIssues.length, 8)}
                </h2>
                <Link
                  to="/issues"
                  className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary hover:text-foreground"
                >
                  all →
                </Link>
              </header>
              {recentIssues.length === 0 ? (
                <div className="px-4 py-6 md:px-6">
                  <p className="font-mono text-[11px] text-text-tertiary">No tasks yet - press C to create one.</p>
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {recentIssues.slice(0, 8).map((issue) => (
                    <li key={issue.id}>
                      <Link
                        to={`/issues/${issue.identifier ?? issue.id}`}
                        className="flex items-center gap-3 px-4 py-2 font-mono text-[12px] hover:bg-surface-2 md:px-6"
                      >
                        <StatusIcon status={issue.status} />
                        <span className="text-text-tertiary shrink-0">
                          {issue.identifier ?? issue.id.slice(0, 6)}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-foreground">{issue.title}</span>
                        <span className="text-[10px] text-text-tertiary">{timeAgo(issue.updatedAt)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          {/* ── Forge connect (kept; styling inherits) ───────────────────── */}
          <section className="px-4 py-5 md:px-6 md:py-6">
            <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
              forge
            </h2>
            <GitHubReposPanel project={selectedProject!} />
          </section>
        </>
      )}
    </div>
  );
}
