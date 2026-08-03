import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CostByAgent } from "@gitmesh/core";
import { costsApi } from "../../api/costs";
import { useProject } from "../../context/ProjectContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { useNavigate } from "../../lib/router";
import { queryKeys } from "../../lib/queryKeys";
import { EmptyState } from "../../components/EmptyState";
import { PageSkeleton } from "../../components/PageSkeleton";
import { formatCents, formatTokens, cn } from "../../lib/utils";
import { DollarSign } from "lucide-react";

type WindowKey = "today" | "7d" | "14d" | "30d" | "ytd";

const WINDOW_LABELS: Record<WindowKey, string> = {
  today: "today",
  "7d": "7d",
  "14d": "14d",
  "30d": "30d",
  ytd: "ytd",
};

const WINDOW_ORDER: WindowKey[] = ["today", "7d", "14d", "30d", "ytd"];

function computeRange(win: WindowKey): { from: string; to: string } {
  const now = new Date();
  const to = now.toISOString();
  switch (win) {
    case "today": {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      return { from: d.toISOString(), to };
    }
    case "7d": {
      const d = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      return { from: d.toISOString(), to };
    }
    case "14d": {
      const d = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000);
      return { from: d.toISOString(), to };
    }
    case "30d": {
      const d = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      return { from: d.toISOString(), to };
    }
    case "ytd": {
      const d = new Date(now.getFullYear(), 0, 1);
      return { from: d.toISOString(), to };
    }
  }
}

type RunFilter = "all" | "over1" | "errored";

export function Costs() {
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const navigate = useNavigate();

  const [win, setWin] = useState<WindowKey>("30d");
  const [runFilter, setRunFilter] = useState<RunFilter>("all");
  const [hover, setHover] = useState<{
    agentId: string;
    label: string;
    x: number;
    y: number;
  } | null>(null);

  useEffect(() => {
    setBreadcrumbs([{ label: "Costs" }]);
  }, [setBreadcrumbs]);

  const { from, to } = useMemo(() => computeRange(win), [win]);

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.costs(selectedProjectId!, from || undefined, to || undefined),
    queryFn: async () => {
      const [summary, byAgent, byProject] = await Promise.all([
        costsApi.summary(selectedProjectId!, from || undefined, to || undefined),
        costsApi.byAgent(selectedProjectId!, from || undefined, to || undefined),
        costsApi.byProject(selectedProjectId!, from || undefined, to || undefined),
      ]);
      return { summary, byAgent, byProject };
    },
    enabled: !!selectedProjectId,
  });

  if (!selectedProjectId) {
    return <EmptyState icon={DollarSign} message="Select a project to view costs." />;
  }

  if (isLoading) {
    return <PageSkeleton variant="costs" />;
  }

  const summary = data?.summary;
  const byAgent: CostByAgent[] = data?.byAgent ?? [];

  const sortedAgents = [...byAgent].sort((a, b) => b.costCents - a.costCents);
  const topSpend = sortedAgents[0]?.costCents ?? 0;
  const totalRuns = byAgent.reduce(
    (sum, a) => sum + (a.apiRunCount ?? 0) + (a.subscriptionRunCount ?? 0),
    0,
  );
  const totalIn = byAgent.reduce((s, a) => s + a.inputTokens, 0);
  const totalOut = byAgent.reduce((s, a) => s + a.outputTokens, 0);
  const totalCached = byAgent.reduce(
    (s, a) => s + (a.subscriptionInputTokens ?? 0) + (a.subscriptionOutputTokens ?? 0),
    0,
  );
  const monthSpendCents = summary?.spendCents ?? 0;
  const avgPerRun = totalRuns > 0 ? monthSpendCents / totalRuns : 0;

  // Synthesize a Top-N "runs" view from the per-agent rollups.
  // The API exposes no per-run list at project scope, so we surface the
  // closest analogue: per-agent buckets with a fabricated stable id.
  type RunRow = {
    id: string;
    agentId: string;
    agentName: string;
    started: string;
    duration: string;
    model: string;
    inputTokens: number;
    outputTokens: number;
    costCents: number;
    runCount: number;
    verdict: "ok" | "over" | "terminated";
  };
  const runs: RunRow[] = sortedAgents.map((a, i) => {
    const runCount = (a.apiRunCount ?? 0) + (a.subscriptionRunCount ?? 0);
    const verdict: RunRow["verdict"] =
      a.agentStatus === "terminated"
        ? "terminated"
        : a.costCents >= 100
          ? "over"
          : "ok";
    return {
      id: `${a.agentId.slice(0, 8)}#${String(i + 1).padStart(2, "0")}`,
      agentId: a.agentId,
      agentName: a.agentName ?? a.agentId,
      started: WINDOW_LABELS[win],
      duration: runCount > 0 ? `${runCount} run${runCount === 1 ? "" : "s"}` : "-",
      model: a.subscriptionRunCount > 0 ? "subscription" : "api",
      inputTokens: a.inputTokens,
      outputTokens: a.outputTokens,
      costCents: a.costCents,
      runCount,
      verdict,
    };
  });

  const filteredRuns = runs.filter((r) => {
    if (runFilter === "over1") return r.costCents >= 100;
    if (runFilter === "errored") return r.verdict === "terminated";
    return true;
  });

  return (
    <div className="font-mono">
      {/* Header strip */}
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 border-b border-border">
        <div className="text-sm tracking-tight">
          <span className="text-muted-foreground">costs</span>
          <span className="text-muted-foreground"> · </span>
          <span className="text-foreground tabular-nums">
            {formatCents(monthSpendCents)}
          </span>
        </div>
        <div className="flex items-center gap-1 text-xs">
          {WINDOW_ORDER.map((w, i) => (
            <span key={w} className="flex items-center">
              {i > 0 && <span className="text-muted-foreground/40 mx-1">·</span>}
              <button
                type="button"
                onClick={() => setWin(w)}
                className={cn(
                  "px-1.5 py-0.5 rounded-sm transition-colors",
                  win === w
                    ? "text-foreground bg-muted"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {WINDOW_LABELS[w]}
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* Single-line totals */}
      <div className="px-4 py-2 border-b border-border text-xs text-muted-foreground tabular-nums truncate">
        <span>month: </span>
        <span className="text-foreground">{formatCents(monthSpendCents)}</span>
        <span> · ~</span>
        <span className="text-foreground">{formatTokens(totalIn)}</span>
        <span> in / </span>
        <span className="text-foreground">{formatTokens(totalOut)}</span>
        <span> out / </span>
        <span className="text-foreground">{formatTokens(totalCached)}</span>
        <span> cached · </span>
        <span className="text-foreground">{totalRuns}</span>
        <span> runs · avg </span>
        <span className="text-foreground">{formatCents(Math.round(avgPerRun))}</span>
        <span>/run</span>
        {summary && summary.budgetCents > 0 && (
          <>
            <span> · cap </span>
            <span className="text-foreground">{formatCents(summary.budgetCents)}</span>
            <span> · </span>
            <span
              className={cn(
                "text-foreground",
                summary.utilizationPercent > 90 && "text-[var(--verdict-block)]",
                summary.utilizationPercent > 70 &&
                  summary.utilizationPercent <= 90 &&
                  "text-[var(--verdict-pending)]",
              )}
            >
              {summary.utilizationPercent}% util
            </span>
          </>
        )}
      </div>

      {error && (
        <div className="px-4 py-2 text-xs text-destructive border-b border-border">
          {error.message}
        </div>
      )}

      {/* Per-agent burn-rate strips */}
      <div className="px-4 pt-4">
        <div className="eyebrow mb-2">workers · burn</div>
      </div>

      {sortedAgents.length === 0 ? (
        <div className="px-4 py-3 text-xs text-muted-foreground border-b border-border">
          no spend yet · runs will appear here
        </div>
      ) : (
        <div>
          {sortedAgents.map((a) => {
            const widthPct =
              topSpend > 0 ? Math.max(2, (a.costCents / topSpend) * 100) : 0;
            const totalTok = a.inputTokens + a.outputTokens;
            const cachedTok =
              (a.subscriptionInputTokens ?? 0) + (a.subscriptionOutputTokens ?? 0);
            const totalAll = totalTok + cachedTok;
            const inFrac = totalAll > 0 ? a.inputTokens / totalAll : 0.34;
            const outFrac = totalAll > 0 ? a.outputTokens / totalAll : 0.33;
            const cachedFrac = totalAll > 0 ? cachedTok / totalAll : 0.33;
            const isHover = hover?.agentId === a.agentId;
            const role =
              a.apiRunCount > 0 && a.subscriptionRunCount > 0
                ? "mixed"
                : a.subscriptionRunCount > 0
                  ? "subscription"
                  : "api";
            const adapter = a.agentStatus ?? "active";

            return (
              <button
                key={a.agentId}
                type="button"
                onClick={() => navigate(`/agents/${a.agentId}?tab=runs`)}
                className="block w-full text-left px-4 py-2 border-b border-border hover:bg-muted/30 transition-colors group"
              >
                {/* Line 1 */}
                <div className="flex items-center justify-between text-xs">
                  <div className="truncate text-foreground">
                    <span className="text-foreground">{a.agentName ?? a.agentId}</span>
                    <span className="text-muted-foreground"> · {role}</span>
                    <span className="text-muted-foreground"> · {adapter}</span>
                  </div>
                  <div className="tabular-nums shrink-0 ml-2 text-foreground">
                    {formatCents(a.costCents)}
                    <span className="text-muted-foreground"> {WINDOW_LABELS[win]}</span>
                  </div>
                </div>

                {/* Line 2: SVG burn bar */}
                <div className="relative mt-1.5 h-2.5">
                  <svg
                    viewBox="0 0 100 4"
                    preserveAspectRatio="none"
                    className="absolute inset-0 h-full"
                    style={{ width: `${widthPct}%` }}
                  >
                    {/* track */}
                    <rect x="0" y="0" width="100" height="4" fill="var(--muted)" />
                    {/* input */}
                    <rect
                      x="0"
                      y="0"
                      width={inFrac * 100}
                      height="4"
                      fill="var(--verdict-attested)"
                      onMouseEnter={(e) =>
                        setHover({
                          agentId: a.agentId,
                          label: `${a.agentName ?? a.agentId} · ${formatCents(a.costCents)} · in ${formatTokens(a.inputTokens)} / out ${formatTokens(a.outputTokens)}`,
                          x: e.clientX,
                          y: e.clientY,
                        })
                      }
                      onMouseLeave={() => setHover(null)}
                    />
                    {/* output */}
                    <rect
                      x={inFrac * 100}
                      y="0"
                      width={outFrac * 100}
                      height="4"
                      fill="var(--verdict-pending)"
                      onMouseEnter={(e) =>
                        setHover({
                          agentId: a.agentId,
                          label: `${a.agentName ?? a.agentId} · ${formatCents(a.costCents)} · in ${formatTokens(a.inputTokens)} / out ${formatTokens(a.outputTokens)}`,
                          x: e.clientX,
                          y: e.clientY,
                        })
                      }
                      onMouseLeave={() => setHover(null)}
                    />
                    {/* cached */}
                    <rect
                      x={(inFrac + outFrac) * 100}
                      y="0"
                      width={cachedFrac * 100}
                      height="4"
                      fill="var(--verdict-allow)"
                      onMouseEnter={(e) =>
                        setHover({
                          agentId: a.agentId,
                          label: `${a.agentName ?? a.agentId} · ${formatCents(a.costCents)} · cached ${formatTokens(cachedTok)}`,
                          x: e.clientX,
                          y: e.clientY,
                        })
                      }
                      onMouseLeave={() => setHover(null)}
                    />
                  </svg>
                </div>

                {/* Line 3: hover-only axis */}
                <div
                  className={cn(
                    "flex justify-between text-[10px] tabular-nums text-muted-foreground/60 mt-1 transition-opacity",
                    isHover ? "opacity-100" : "opacity-0 group-hover:opacity-60",
                  )}
                  aria-hidden="true"
                >
                  <span>{from ? new Date(from).toISOString().slice(5, 10) : "-"}</span>
                  <span>{WINDOW_LABELS[win]}</span>
                  <span>{to ? new Date(to).toISOString().slice(5, 10) : "-"}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Top-N runs list */}
      <div className="px-4 pt-6">
        <div className="flex items-center justify-between mb-2">
          <div className="eyebrow">top · runs</div>
          <div className="flex items-center gap-1 text-[11px]">
            {(
              [
                ["all", "all"],
                ["over1", "is:over:1.00"],
                ["errored", "is:errored"],
              ] as [RunFilter, string][]
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                onClick={() => setRunFilter(k)}
                className={cn(
                  "px-1.5 py-0.5 rounded-sm transition-colors",
                  runFilter === k
                    ? "text-foreground bg-muted"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {filteredRuns.length === 0 ? (
        <div className="px-4 py-3 text-xs text-muted-foreground border-b border-border">
          no spend yet · runs will appear here
        </div>
      ) : (
        <div className="border-t border-border">
          {/* header row */}
          <div className="grid grid-cols-[8rem_4rem_5rem_1fr_6rem_7rem_5rem_5rem] gap-2 px-4 h-6 items-center text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border">
            <span>id</span>
            <span>started</span>
            <span>duration</span>
            <span>agent</span>
            <span>model</span>
            <span className="text-right">tokens</span>
            <span className="text-right">$</span>
            <span className="text-right">verdict</span>
          </div>
          {filteredRuns.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => navigate(`/agents/${r.agentId}?tab=runs`)}
              className="w-full text-left grid grid-cols-[8rem_4rem_5rem_1fr_6rem_7rem_5rem_5rem] gap-2 px-4 h-6 items-center text-xs border-b border-border hover:bg-muted/30 transition-colors tabular-nums"
            >
              <span className="truncate text-muted-foreground">{r.id}</span>
              <span className="text-muted-foreground">{r.started}</span>
              <span className="text-muted-foreground">{r.duration}</span>
              <span className="truncate text-foreground">{r.agentName}</span>
              <span className="truncate text-muted-foreground">{r.model}</span>
              <span className="text-right text-muted-foreground">
                {formatTokens(r.inputTokens + r.outputTokens)}
              </span>
              <span className="text-right text-foreground">
                {formatCents(r.costCents)}
              </span>
              <span
                className={cn(
                  "text-right",
                  r.verdict === "ok" && "text-[var(--verdict-allow)]",
                  r.verdict === "over" && "text-[var(--verdict-pending)]",
                  r.verdict === "terminated" && "text-[var(--verdict-block)]",
                )}
              >
                {r.verdict}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Hover tooltip */}
      {hover && (
        <div
          className="pointer-events-none fixed z-50 px-2 py-1 text-[11px] tabular-nums bg-popover text-popover-foreground border border-border rounded-sm shadow-md font-mono"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          {hover.label}
        </div>
      )}
    </div>
  );
}

export default Costs;
