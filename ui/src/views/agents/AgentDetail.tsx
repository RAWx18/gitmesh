import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { useParams, useNavigate, Link, useBeforeUnload } from "@/lib/router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentsApi, type AgentKey, type ClaudeLoginResult } from "../../api/agents";
import { heartbeatsApi } from "../../api/heartbeats";
import { ApiError } from "../../api/client";
import { auditLogApi } from "../../api/audit-log";
import { issuesApi } from "../../api/issues";
import { usePanel } from "../../context/PanelContext";
import { useSidebar } from "../../context/SidebarContext";
import { useProject } from "../../context/ProjectContext";
import { useDialog } from "../../context/DialogContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { AgentConfigForm } from "../../features/AgentConfigForm";
import { adapterLabels, roleLabels } from "../../components/agent-config-primitives";
import { getUIAdapter, buildTranscript } from "../../adapters";
import { StatusBadge } from "../../components/StatusBadge";
import { CopyText } from "../../components/CopyText";
import { PageSkeleton } from "../../components/PageSkeleton";
import { formatCents, formatDate, relativeTime, formatTokens } from "../../lib/utils";
import { cn } from "../../lib/utils";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  MoreHorizontal,
  Play,
  Pause,
  Plus,
  Key,
  Eye,
  EyeOff,
  Copy,
  ChevronDown,
  ChevronRight,
  RotateCcw,
  Trash2,
  Settings,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { isUuidLike, type Agent, type HeartbeatRun, type HeartbeatRunEvent, type AgentRuntimeState, type AgentTaskSession, type LiveEvent } from "@gitmesh/core";
import { agentRouteRef } from "../../lib/utils";

const REDACTED_ENV_VALUE = "***REDACTED***";
const SECRET_ENV_KEY_RE =
  /(api[-_]?key|access[-_]?token|auth(?:_?token)?|authorization|bearer|secret|passwd|password|credential|jwt|private[-_]?key|cookie|connectionstring)/i;
const JWT_VALUE_RE = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?$/;

const LIVE_SCROLL_BOTTOM_TOLERANCE_PX = 32;
type ScrollContainer = Window | HTMLElement;

function isWindowContainer(c: ScrollContainer): c is Window { return c === window; }
function isElementScrollContainer(el: HTMLElement): boolean {
  const o = window.getComputedStyle(el).overflowY;
  return o === "auto" || o === "scroll" || o === "overlay";
}
function findScrollContainer(anchor: HTMLElement | null): ScrollContainer {
  let parent = anchor?.parentElement ?? null;
  while (parent) { if (isElementScrollContainer(parent)) return parent; parent = parent.parentElement; }
  return window;
}
function readScrollMetrics(c: ScrollContainer): { scrollHeight: number; distanceFromBottom: number } {
  if (isWindowContainer(c)) {
    const h = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
    const b = window.scrollY + window.innerHeight;
    return { scrollHeight: h, distanceFromBottom: Math.max(0, h - b) };
  }
  const b = c.scrollTop + c.clientHeight;
  return { scrollHeight: c.scrollHeight, distanceFromBottom: Math.max(0, c.scrollHeight - b) };
}
function scrollToContainerBottom(c: ScrollContainer, behavior: ScrollBehavior = "auto") {
  if (isWindowContainer(c)) {
    const h = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
    window.scrollTo({ top: h, behavior });
    return;
  }
  c.scrollTo({ top: c.scrollHeight, behavior });
}

function shouldRedactSecretValue(key: string, value: unknown): boolean {
  if (SECRET_ENV_KEY_RE.test(key)) return true;
  if (typeof value !== "string") return false;
  return JWT_VALUE_RE.test(value);
}

function redactEnvValue(key: string, value: unknown): string {
  if (typeof value === "object" && value !== null && !Array.isArray(value) && (value as { type?: unknown }).type === "secret_ref") return "***SECRET_REF***";
  if (shouldRedactSecretValue(key, value)) return REDACTED_ENV_VALUE;
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try { return JSON.stringify(value); } catch { return String(value); }
}
function formatEnvForDisplay(envValue: unknown): string {
  const env = asRecord(envValue);
  if (!env) return "<unable-to-parse>";
  const keys = Object.keys(env);
  if (keys.length === 0) return "<empty>";
  return keys.sort().map((k) => `${k}=${redactEnvValue(k, env[k])}`).join("\n");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}
function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const t = value.trim();
  return t.length > 0 ? t : null;
}

function usageNumber(usage: Record<string, unknown> | null, ...keys: string[]) {
  if (!usage) return 0;
  for (const k of keys) {
    const v = usage[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return 0;
}

function runMetrics(run: HeartbeatRun) {
  const usage = (run.usageJson ?? null) as Record<string, unknown> | null;
  const result = (run.resultJson ?? null) as Record<string, unknown> | null;
  const input = usageNumber(usage, "inputTokens", "input_tokens");
  const output = usageNumber(usage, "outputTokens", "output_tokens");
  const cached = usageNumber(usage, "cachedInputTokens", "cached_input_tokens", "cache_read_input_tokens");
  const cost = usageNumber(usage, "costUsd", "cost_usd", "total_cost_usd")
    || usageNumber(result, "total_cost_usd", "cost_usd", "costUsd");
  return { input, output, cached, cost, totalTokens: input + output };
}

type Verdict = "allow" | "block" | "pending" | "attested";

function runVerdict(run: HeartbeatRun): Verdict {
  switch (run.status) {
    case "succeeded": return "allow";
    case "failed":
    case "timed_out":
      return "block";
    case "running":
    case "queued":
    case "cancelled":
      return "pending";
    default:
      return "pending";
  }
}

function runDurationSec(run: HeartbeatRun): number | null {
  if (run.startedAt && run.finishedAt) {
    return Math.max(0, Math.round((new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime()) / 1000));
  }
  if (run.startedAt && (run.status === "running" || run.status === "queued")) {
    return Math.max(0, Math.round((Date.now() - new Date(run.startedAt).getTime()) / 1000));
  }
  return null;
}

function shortHash(id: string): string { return id.slice(0, 8); }

function formatDurationCompact(sec: number | null): string {
  if (sec === null) return "-";
  if (sec < 1) return "<1s";
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m < 60) return `${m}m${s ? ` ${s}s` : ""}`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function timeOfDay(date: Date | string): string {
  return new Date(date).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function AgentDetail() {
  const { projectPrefix, agentId, runId: urlRunId } = useParams<{
    projectPrefix?: string;
    agentId: string;
    tab?: string;
    runId?: string;
  }>();
  const { projects, selectedProjectId, setSelectedProjectId } = useProject();
  const { closePanel } = usePanel();
  const { openNewIssue } = useDialog();
  const { setBreadcrumbs } = useBreadcrumbs();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { isMobile } = useSidebar();

  const [actionError, setActionError] = useState<string | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [configSheetOpen, setConfigSheetOpen] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [configFooterOpen, setConfigFooterOpen] = useState(false);
  const [activeSessionsOpen, setActiveSessionsOpen] = useState(true);
  const saveConfigActionRef = useRef<(() => void) | null>(null);
  const cancelConfigActionRef = useRef<(() => void) | null>(null);
  const setSaveConfigAction = useCallback((fn: (() => void) | null) => { saveConfigActionRef.current = fn; }, []);
  const setCancelConfigAction = useCallback((fn: (() => void) | null) => { cancelConfigActionRef.current = fn; }, []);

  const routeAgentRef = agentId ?? "";
  const routeProjectId = useMemo(() => {
    if (!projectPrefix) return null;
    const p = projectPrefix.toUpperCase();
    return projects.find((proj) => proj.issuePrefix.toUpperCase() === p)?.id ?? null;
  }, [projects, projectPrefix]);
  const lookupProjectId = routeProjectId ?? selectedProjectId ?? undefined;
  const canFetchAgent = routeAgentRef.length > 0 && (isUuidLike(routeAgentRef) || Boolean(lookupProjectId));

  const { data: agent, isLoading, error } = useQuery({
    queryKey: [...queryKeys.agents.detail(routeAgentRef), lookupProjectId ?? null],
    queryFn: () => agentsApi.get(routeAgentRef, lookupProjectId),
    enabled: canFetchAgent,
  });
  const resolvedProjectId = agent?.projectId ?? selectedProjectId;
  const canonicalAgentRef = agent ? agentRouteRef(agent) : routeAgentRef;
  const agentLookupRef = agent?.id ?? routeAgentRef;
  const resolvedAgentId = agent?.id ?? null;

  const { data: runtimeState } = useQuery({
    queryKey: queryKeys.agents.runtimeState(resolvedAgentId ?? routeAgentRef),
    queryFn: () => agentsApi.runtimeState(resolvedAgentId!, resolvedProjectId ?? undefined),
    enabled: Boolean(resolvedAgentId),
  });

  const { data: heartbeats } = useQuery({
    queryKey: queryKeys.heartbeats(resolvedProjectId!, agent?.id ?? undefined),
    queryFn: () => heartbeatsApi.list(resolvedProjectId!, agent?.id ?? undefined),
    enabled: !!resolvedProjectId && !!agent?.id,
  });

  const { data: taskSessions } = useQuery({
    queryKey: queryKeys.agents.taskSessions(resolvedAgentId ?? routeAgentRef),
    queryFn: () => agentsApi.taskSessions(resolvedAgentId!, resolvedProjectId ?? undefined),
    enabled: Boolean(resolvedAgentId),
  });

  const { data: allIssues } = useQuery({
    queryKey: queryKeys.issues.list(resolvedProjectId!),
    queryFn: () => issuesApi.list(resolvedProjectId!),
    enabled: !!resolvedProjectId,
  });

  const { data: allAgents } = useQuery({
    queryKey: queryKeys.agents.list(resolvedProjectId!),
    queryFn: () => agentsApi.list(resolvedProjectId!),
    enabled: !!resolvedProjectId,
  });

  const assignedIssues = (allIssues ?? [])
    .filter((i) => i.assigneeAgentId === agent?.id)
    .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  const reportsToAgent = (allAgents ?? []).find((a) => a.id === agent?.reportsTo) ?? null;
  const directReports = (allAgents ?? []).filter((a) => a.reportsTo === agent?.id && a.status !== "terminated");

  useEffect(() => {
    if (!agent) return;
    if (routeAgentRef === canonicalAgentRef) return;
    if (urlRunId) {
      navigate(`/agents/${canonicalAgentRef}/runs/${urlRunId}`, { replace: true });
      return;
    }
    navigate(`/agents/${canonicalAgentRef}`, { replace: true });
  }, [agent, routeAgentRef, canonicalAgentRef, urlRunId, navigate]);

  useEffect(() => {
    if (!agent?.projectId || agent.projectId === selectedProjectId) return;
    setSelectedProjectId(agent.projectId, { source: "route_sync" });
  }, [agent?.projectId, selectedProjectId, setSelectedProjectId]);

  const agentAction = useMutation({
    mutationFn: async (action: "invoke" | "pause" | "resume" | "terminate") => {
      if (!agentLookupRef) return Promise.reject(new Error("No agent reference"));
      switch (action) {
        case "invoke": return agentsApi.invoke(agentLookupRef, resolvedProjectId ?? undefined);
        case "pause": return agentsApi.pause(agentLookupRef, resolvedProjectId ?? undefined);
        case "resume": return agentsApi.resume(agentLookupRef, resolvedProjectId ?? undefined);
        case "terminate": return agentsApi.terminate(agentLookupRef, resolvedProjectId ?? undefined);
      }
    },
    onSuccess: (data, action) => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(routeAgentRef) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(agentLookupRef) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.runtimeState(agentLookupRef) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.taskSessions(agentLookupRef) });
      if (resolvedProjectId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.agents.list(resolvedProjectId) });
        if (agent?.id) queryClient.invalidateQueries({ queryKey: queryKeys.heartbeats(resolvedProjectId, agent.id) });
      }
      if (action === "invoke" && data && typeof data === "object" && "id" in data) {
        navigate(`/agents/${canonicalAgentRef}/runs/${(data as HeartbeatRun).id}`);
      }
    },
    onError: (err) => { setActionError(err instanceof Error ? err.message : "Action failed"); },
  });

  const resetTaskSession = useMutation({
    mutationFn: (taskKey: string | null) =>
      agentsApi.resetSession(agentLookupRef, taskKey, resolvedProjectId ?? undefined),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.runtimeState(agentLookupRef) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.taskSessions(agentLookupRef) });
    },
    onError: (err) => { setActionError(err instanceof Error ? err.message : "Failed to reset session"); },
  });

  const updatePermissions = useMutation({
    mutationFn: (canCreateAgents: boolean) =>
      agentsApi.updatePermissions(agentLookupRef, { canCreateAgents }, resolvedProjectId ?? undefined),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(routeAgentRef) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(agentLookupRef) });
      if (resolvedProjectId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.agents.list(resolvedProjectId) });
      }
    },
    onError: (err) => { setActionError(err instanceof Error ? err.message : "Failed to update permissions"); },
  });

  useEffect(() => {
    const crumbs: { label: string; href?: string }[] = [{ label: "Workers", href: "/agents" }];
    const agentName = agent?.name ?? routeAgentRef ?? "Worker";
    if (urlRunId) {
      crumbs.push({ label: agentName, href: `/agents/${canonicalAgentRef}` });
      crumbs.push({ label: `trace ${urlRunId.slice(0, 8)}` });
    } else {
      crumbs.push({ label: agentName });
    }
    setBreadcrumbs(crumbs);
  }, [setBreadcrumbs, agent, routeAgentRef, canonicalAgentRef, urlRunId]);

  useEffect(() => {
    closePanel();
    return () => closePanel();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useBeforeUnload(
    useCallback((event) => {
      if (!configDirty) return;
      event.preventDefault();
      event.returnValue = "";
    }, [configDirty]),
  );

  if (isLoading) return <PageSkeleton variant="detail" />;
  if (error) return <p className="text-sm text-destructive">{error.message}</p>;
  if (!agent) return null;

  const isPendingApproval = agent.status === "pending_approval";
  const sortedRuns = [...(heartbeats ?? [])].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  );
  const activeSessions = (taskSessions ?? []).filter((s) => Boolean(s.lastRunId));
  const liveRun = sortedRuns.find((r) => r.status === "running" || r.status === "queued") ?? null;

  const selectedRun = urlRunId ? sortedRuns.find((r) => r.id === urlRunId) ?? null : null;

  return (
    <div className="space-y-0">
      <IdentityStrip
        agent={agent}
        canonicalAgentRef={canonicalAgentRef}
        liveRun={liveRun}
        runtimeState={runtimeState}
        isPendingApproval={isPendingApproval}
        isMutating={agentAction.isPending}
        onAssign={() => openNewIssue({ assigneeAgentId: agent.id })}
        onInvoke={() => agentAction.mutate("invoke")}
        onPause={() => agentAction.mutate("pause")}
        onResume={() => agentAction.mutate("resume")}
        onTerminate={() => agentAction.mutate("terminate")}
        onResetSessions={() => resetTaskSession.mutate(null)}
        onConfigure={() => setConfigSheetOpen(true)}
        moreOpen={moreOpen}
        setMoreOpen={setMoreOpen}
      />

      {actionError && (
        <p className="px-4 py-2 text-[11px] font-mono text-[var(--verdict-block)] border-b border-border">{actionError}</p>
      )}
      {isPendingApproval && (
        <p className="px-4 py-2 text-[11px] font-mono uppercase tracking-[0.10em] text-[var(--verdict-pending)] border-b border-border">
          worker awaiting maintainer attestation - invocation blocked
        </p>
      )}

      {urlRunId ? (
        <RunTraceSection
          agent={agent}
          runs={sortedRuns}
          selectedRun={selectedRun}
          urlRunId={urlRunId}
          canonicalAgentRef={canonicalAgentRef}
          adapterType={agent.adapterType}
          isMobile={isMobile}
        />
      ) : (
        <WorkerProfileBody
          agent={agent}
          runs={sortedRuns}
          assignedIssuesCount={assignedIssues.length}
          activeSessions={activeSessions}
          activeSessionsOpen={activeSessionsOpen}
          setActiveSessionsOpen={setActiveSessionsOpen}
          configFooterOpen={configFooterOpen}
          setConfigFooterOpen={setConfigFooterOpen}
          runtimeState={runtimeState}
          reportsToAgent={reportsToAgent}
          directReports={directReports}
          canonicalAgentRef={canonicalAgentRef}
          onResetSession={(taskKey) => resetTaskSession.mutate(taskKey)}
          onConfigure={() => setConfigSheetOpen(true)}
          onRetry={(runId) => navigate(`/agents/${canonicalAgentRef}/runs/${runId}`)}
        />
      )}

      <Sheet open={configSheetOpen} onOpenChange={(open) => {
        if (!open && configDirty) {
          if (!window.confirm("Discard unsaved configuration changes?")) return;
          cancelConfigActionRef.current?.();
        }
        setConfigSheetOpen(open);
      }}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-2xl sm:w-[640px] gitmesh-scrollbar overflow-y-auto"
        >
          <SheetHeader className="border-b border-border px-5 py-3">
            <div className="flex items-center justify-between gap-2">
              <SheetTitle className="font-mono text-[11px] uppercase tracking-[0.18em] text-text-tertiary">
                worker · configure
              </SheetTitle>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 font-mono text-[11px] uppercase tracking-[0.10em]"
                  onClick={() => cancelConfigActionRef.current?.()}
                  disabled={configSaving}
                >
                  cancel
                </Button>
                <Button
                  size="sm"
                  className="h-7 px-2 font-mono text-[11px] uppercase tracking-[0.10em]"
                  onClick={() => saveConfigActionRef.current?.()}
                  disabled={configSaving || !configDirty}
                >
                  {configSaving ? "saving…" : "save"}
                </Button>
              </div>
            </div>
          </SheetHeader>

          <div className="px-5 py-5 space-y-6">
            <ConfigureBlock
              agent={agent}
              projectId={resolvedProjectId ?? undefined}
              onDirtyChange={setConfigDirty}
              onSaveActionChange={setSaveConfigAction}
              onCancelActionChange={setCancelConfigAction}
              onSavingChange={setConfigSaving}
              updatePermissions={updatePermissions}
            />
            <KeysBlock agentId={agent.id} projectId={resolvedProjectId ?? undefined} />
            <RevisionsBlock agent={agent} projectId={resolvedProjectId ?? undefined} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

/* ── Identity Strip ───────────────────────────────────────────────────────── */

function IdentityStrip({
  agent,
  canonicalAgentRef,
  liveRun,
  runtimeState,
  isPendingApproval,
  isMutating,
  onAssign,
  onInvoke,
  onPause,
  onResume,
  onTerminate,
  onResetSessions,
  onConfigure,
  moreOpen,
  setMoreOpen,
}: {
  agent: Agent;
  canonicalAgentRef: string;
  liveRun: HeartbeatRun | null;
  runtimeState?: AgentRuntimeState;
  isPendingApproval: boolean;
  isMutating: boolean;
  onAssign: () => void;
  onInvoke: () => void;
  onPause: () => void;
  onResume: () => void;
  onTerminate: () => void;
  onResetSessions: () => void;
  onConfigure: () => void;
  moreOpen: boolean;
  setMoreOpen: (v: boolean) => void;
}) {
  const adapter = adapterLabels[agent.adapterType] ?? agent.adapterType;
  const role = roleLabels[agent.role] ?? agent.role;
  const lastActive = agent.lastHeartbeatAt ? relativeTime(agent.lastHeartbeatAt) : "never";
  const spentCents = runtimeState?.totalCostCents ?? agent.spentMonthlyCents ?? 0;
  const budgetCents = agent.budgetMonthlyCents ?? 0;
  const budgetPct = budgetCents > 0 ? Math.min(100, Math.round((spentCents / budgetCents) * 100)) : null;

  return (
    <div className="border-b border-border bg-[color-mix(in_oklab,var(--surface-2)_60%,transparent)]">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2 font-mono text-[11px]">
        <span className="eyebrow !text-[10px] !tracking-[0.20em]">
          worker · {agent.adapterType}
        </span>

        <span className="text-foreground font-medium tracking-tight text-[13px]">{agent.name}</span>

        <span className="flex items-center gap-1 text-text-tertiary uppercase tracking-[0.10em]">
          <span className="text-text-secondary">role</span>
          <span className="text-foreground">{role}</span>
        </span>

        <span className="flex items-center gap-1 text-text-tertiary uppercase tracking-[0.10em]">
          <span className="text-text-secondary">adapter</span>
          <span className="text-foreground">{adapter}</span>
        </span>

        <span className="flex items-center gap-1.5">
          <StatusBadge status={agent.status} />
        </span>

        <span className="flex items-center gap-2 text-text-tertiary uppercase tracking-[0.10em]">
          <span className="text-text-secondary">budget</span>
          {budgetPct === null ? (
            <span className="text-foreground tabular-nums">unlimited</span>
          ) : (
            <span className="flex items-center gap-2">
              <span className="relative h-[6px] w-[80px] bg-surface-3 rounded-[1px] overflow-hidden">
                <span
                  className={cn(
                    "absolute inset-y-0 left-0",
                    budgetPct >= 90 ? "bg-[var(--verdict-block)]" :
                      budgetPct >= 70 ? "bg-[var(--verdict-pending)]" :
                        "bg-[var(--verdict-attested)]",
                  )}
                  style={{ width: `${budgetPct}%` }}
                />
              </span>
              <span className="text-foreground tabular-nums">{budgetPct}%</span>
            </span>
          )}
        </span>

        <span className="flex items-center gap-1 text-text-tertiary uppercase tracking-[0.10em]">
          <span className="text-text-secondary">last</span>
          <span className="text-foreground">{lastActive}</span>
        </span>

        {liveRun && (
          <Link
            to={`/agents/${canonicalAgentRef}/runs/${liveRun.id}`}
            className="ml-auto flex items-center gap-1.5 px-2 py-0.5 border border-[var(--verdict-attested)] text-[var(--verdict-attested)] no-underline uppercase tracking-[0.12em] text-[10px]"
          >
            <span className="gm-pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--verdict-attested)]" />
            live · {shortHash(liveRun.id)}
          </Link>
        )}

        <div className={cn("flex items-center gap-1", !liveRun && "ml-auto")}>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
            onClick={onAssign}
          >
            <Plus className="h-3 w-3 mr-1" /> assign
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
            onClick={onInvoke}
            disabled={isMutating || isPendingApproval}
          >
            <Play className="h-3 w-3 mr-1" /> wake
          </Button>
          {agent.status === "paused" ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
              onClick={onResume}
              disabled={isMutating || isPendingApproval}
            >
              <Play className="h-3 w-3 mr-1" /> resume
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
              onClick={onPause}
              disabled={isMutating || isPendingApproval}
            >
              <Pause className="h-3 w-3 mr-1" /> pause
            </Button>
          )}
          <Popover open={moreOpen} onOpenChange={setMoreOpen}>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon-xs" className="h-7 w-7 border border-border rounded-none">
                <MoreHorizontal className="h-3.5 w-3.5" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-44 p-1 font-mono text-[11px]" align="end">
              <button
                className="flex items-center gap-2 w-full px-2 py-1.5 hover:bg-accent/50"
                onClick={() => { onConfigure(); setMoreOpen(false); }}
              >
                <Settings className="h-3 w-3" /> configure
              </button>
              <button
                className="flex items-center gap-2 w-full px-2 py-1.5 hover:bg-accent/50"
                onClick={() => { navigator.clipboard.writeText(agent.id); setMoreOpen(false); }}
              >
                <Copy className="h-3 w-3" /> copy id
              </button>
              <button
                className="flex items-center gap-2 w-full px-2 py-1.5 hover:bg-accent/50"
                onClick={() => { onResetSessions(); setMoreOpen(false); }}
              >
                <RotateCcw className="h-3 w-3" /> reset sessions
              </button>
              <button
                className="flex items-center gap-2 w-full px-2 py-1.5 hover:bg-accent/50 text-destructive"
                onClick={() => { onTerminate(); setMoreOpen(false); }}
              >
                <Trash2 className="h-3 w-3" /> terminate
              </button>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  );
}

/* ── Worker Profile Body ──────────────────────────────────────────────────── */

function WorkerProfileBody({
  agent,
  runs,
  assignedIssuesCount,
  activeSessions,
  activeSessionsOpen,
  setActiveSessionsOpen,
  configFooterOpen,
  setConfigFooterOpen,
  runtimeState,
  reportsToAgent,
  directReports,
  canonicalAgentRef,
  onResetSession,
  onConfigure,
  onRetry,
}: {
  agent: Agent;
  runs: HeartbeatRun[];
  assignedIssuesCount: number;
  activeSessions: AgentTaskSession[];
  activeSessionsOpen: boolean;
  setActiveSessionsOpen: (v: boolean) => void;
  configFooterOpen: boolean;
  setConfigFooterOpen: (v: boolean) => void;
  runtimeState?: AgentRuntimeState;
  reportsToAgent: Agent | null;
  directReports: Agent[];
  canonicalAgentRef: string;
  onResetSession: (taskKey: string | null) => void;
  onConfigure: () => void;
  onRetry: (runId: string) => void;
}) {
  return (
    <div className="font-mono">
      <PulseRibbon runs={runs} canonicalAgentRef={canonicalAgentRef} />
      <SkillsRow agent={agent} onConfigure={onConfigure} />
      <CostLine runtimeState={runtimeState} agent={agent} />

      <RecentRunsTable
        runs={runs}
        canonicalAgentRef={canonicalAgentRef}
        onRetry={onRetry}
      />

      <ActiveSessionsAccordion
        sessions={activeSessions}
        runs={runs}
        canonicalAgentRef={canonicalAgentRef}
        open={activeSessionsOpen}
        setOpen={setActiveSessionsOpen}
        onResetSession={onResetSession}
      />

      <ConfigurationFooter
        agent={agent}
        runtimeState={runtimeState}
        reportsToAgent={reportsToAgent}
        directReports={directReports}
        assignedIssuesCount={assignedIssuesCount}
        canonicalAgentRef={canonicalAgentRef}
        open={configFooterOpen}
        setOpen={setConfigFooterOpen}
        onConfigure={onConfigure}
      />
    </div>
  );
}

/* ── Pulse Ribbon ─────────────────────────────────────────────────────────── */

function PulseRibbon({ runs, canonicalAgentRef }: { runs: HeartbeatRun[]; canonicalAgentRef: string }) {
  const navigate = useNavigate();
  const slice = runs.slice(0, 50).slice().reverse();
  const [hover, setHover] = useState<{ x: number; y: number; run: HeartbeatRun } | null>(null);

  const TICK_W = 6;
  const GAP = 2;
  const HEIGHT = 40;
  const PAD_X = 8;
  const widthInner = Math.max(slice.length * (TICK_W + GAP) - GAP, 0);
  const width = widthInner + PAD_X * 2;
  const counts = useMemo(() => {
    const c = { allow: 0, block: 0, pending: 0 };
    for (const r of slice) {
      const v = runVerdict(r);
      if (v === "allow") c.allow++;
      else if (v === "block") c.block++;
      else c.pending++;
    }
    return c;
  }, [slice]);

  return (
    <div className="border-b border-border bg-surface-1">
      <div className="flex items-center justify-between px-4 pt-3">
        <span className="eyebrow">pulse · last 50 runs</span>
        <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">
          <span className="text-[var(--verdict-allow)]">{counts.allow} allow</span>
          {"  ·  "}
          <span className="text-[var(--verdict-block)]">{counts.block} block</span>
          {"  ·  "}
          <span className="text-[var(--verdict-pending)]">{counts.pending} pending</span>
        </span>
      </div>
      <div className="px-2 pb-3 pt-2 overflow-x-auto gitmesh-scrollbar relative" onMouseLeave={() => setHover(null)}>
        {slice.length === 0 ? (
          <div className="px-4 py-3 text-[11px] text-text-tertiary">no runs in window</div>
        ) : (
          <svg width={width} height={HEIGHT} className="block">
            {slice.map((r, idx) => {
              const x = PAD_X + idx * (TICK_W + GAP);
              const verdict = runVerdict(r);
              const fill =
                verdict === "allow" ? "var(--verdict-allow)" :
                  verdict === "block" ? "var(--verdict-block)" :
                    "var(--verdict-pending)";
              const dur = runDurationSec(r) ?? 0;
              const minH = 8;
              const maxH = HEIGHT - 6;
              const scaled = Math.min(maxH, minH + Math.log2(1 + Math.max(0, dur)) * 6);
              const isLive = r.status === "running" || r.status === "queued";
              return (
                <rect
                  key={r.id}
                  x={x}
                  y={HEIGHT - scaled - 2}
                  width={TICK_W}
                  height={scaled}
                  fill={fill}
                  opacity={isLive ? 0.85 : 1}
                  className="cursor-pointer"
                  onMouseEnter={(e) => {
                    const rect = (e.currentTarget.ownerSVGElement?.parentElement?.getBoundingClientRect());
                    setHover({ x: rect ? x : 0, y: 0, run: r });
                  }}
                  onClick={() => navigate(`/agents/${canonicalAgentRef}/runs/${r.id}`)}
                >
                  <title>{`${shortHash(r.id)} · ${r.status} · ${formatDurationCompact(runDurationSec(r))}`}</title>
                </rect>
              );
            })}
          </svg>
        )}
        {hover && (
          <div
            className="pointer-events-none absolute top-0 -translate-x-1/2 mt-[-4px] bg-popover border border-border px-2 py-1 text-[10px] uppercase tracking-[0.10em] text-foreground"
            style={{ left: hover.x + 8 + 3 }}
          >
            {shortHash(hover.run.id)} · {hover.run.status} · {formatDurationCompact(runDurationSec(hover.run))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Skills Row ───────────────────────────────────────────────────────────── */

function SkillsRow({ agent, onConfigure }: { agent: Agent; onConfigure: () => void }) {
  const config = (agent.adapterConfig ?? {}) as Record<string, unknown>;
  const rawSkills = (() => {
    const candidates: unknown[] = [
      config.skills,
      config.skill_names,
      (agent.metadata as Record<string, unknown> | null)?.skills,
    ];
    for (const c of candidates) {
      if (Array.isArray(c)) return c.filter((v): v is string => typeof v === "string");
    }
    return [] as string[];
  })();

  return (
    <div className="border-b border-border px-4 py-2 flex flex-wrap items-center gap-2">
      <span className="eyebrow shrink-0 mr-1">skills</span>
      {rawSkills.length === 0 ? (
        <span className="text-[11px] text-text-tertiary uppercase tracking-[0.10em]">none</span>
      ) : (
        rawSkills.map((s) => (
          <span
            key={s}
            className="px-1.5 py-0.5 border border-border text-[10px] uppercase tracking-[0.10em] text-foreground"
          >
            {s}
          </span>
        ))
      )}
      <button
        className="ml-auto text-[10px] uppercase tracking-[0.18em] text-text-tertiary hover:text-foreground transition-colors"
        onClick={onConfigure}
      >
        manage →
      </button>
    </div>
  );
}

/* ── Cost Line ────────────────────────────────────────────────────────────── */

function CostLine({ runtimeState, agent }: { runtimeState?: AgentRuntimeState; agent: Agent }) {
  const totalCents = runtimeState?.totalCostCents ?? agent.spentMonthlyCents ?? 0;
  const inputTok = runtimeState?.totalInputTokens ?? 0;
  const outputTok = runtimeState?.totalOutputTokens ?? 0;
  const cachedTok = runtimeState?.totalCachedInputTokens ?? 0;

  return (
    <div className="border-b border-border px-4 py-2 flex flex-wrap items-center gap-x-4 gap-y-1">
      <span className="eyebrow">cost</span>
      <span className="text-[11px] tabular-nums text-foreground">
        month: <span className="text-foreground">{formatCents(totalCents)}</span>
        <span className="text-text-tertiary">
          {"  ("}~{formatTokens(inputTok)} in / {formatTokens(outputTok)} out / {formatTokens(cachedTok)} cached{")"}
        </span>
      </span>
    </div>
  );
}

/* ── Recent Runs Table ────────────────────────────────────────────────────── */

function RecentRunsTable({
  runs,
  canonicalAgentRef,
  onRetry,
}: {
  runs: HeartbeatRun[];
  canonicalAgentRef: string;
  onRetry: (runId: string) => void;
}) {
  const slice = runs.slice(0, 25);
  const maxDur = Math.max(1, ...slice.map((r) => runDurationSec(r) ?? 0));

  return (
    <div className="border-b border-border">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <span className="eyebrow">trace history</span>
        {runs.length > slice.length && (
          <span className="text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">
            showing {slice.length}/{runs.length}
          </span>
        )}
      </div>
      {slice.length === 0 ? (
        <div className="px-4 py-3 text-[11px] text-text-tertiary uppercase tracking-[0.10em]">no runs yet</div>
      ) : (
        <div>
          <div className="grid grid-cols-[88px_120px_1fr_88px_100px_72px_64px] gap-3 px-4 py-1 border-b border-border text-[9px] uppercase tracking-[0.18em] text-text-tertiary">
            <span>id</span>
            <span>started</span>
            <span>duration</span>
            <span>verdict</span>
            <span className="text-right">tokens</span>
            <span>attest</span>
            <span className="text-right">retry</span>
          </div>
          {slice.map((run) => {
            const verdict = runVerdict(run);
            const dur = runDurationSec(run);
            const pct = dur !== null ? Math.max(2, Math.round((dur / maxDur) * 100)) : 0;
            const m = runMetrics(run);
            const isRunning = run.status === "running" || run.status === "queued";
            const canRetry = run.status === "failed" || run.status === "timed_out";
            return (
              <div
                key={run.id}
                className="grid grid-cols-[88px_120px_1fr_88px_100px_72px_64px] gap-3 px-4 items-center border-b border-border hover:bg-[color-mix(in_oklab,var(--surface-2)_60%,transparent)] transition-colors text-[11px] tabular-nums"
                style={{ height: 28 }}
              >
                <Link
                  to={`/agents/${canonicalAgentRef}/runs/${run.id}`}
                  className="text-foreground no-underline hover:text-[var(--verdict-attested)]"
                >
                  {shortHash(run.id)}
                </Link>
                <span className="text-text-secondary">{relativeTime(run.createdAt)}</span>
                <span className="flex items-center gap-2">
                  <span
                    className="gm-waterfall-bar flex-1 max-w-[180px]"
                    data-state={isRunning ? "running" : undefined}
                  >
                    <span style={{ width: `${pct}%` }} />
                  </span>
                  <span className="text-text-tertiary w-12 shrink-0">{formatDurationCompact(dur)}</span>
                </span>
                <span>
                  <span className="verdict-chip" data-verdict={verdict}>
                    {run.status}
                  </span>
                </span>
                <span className="text-right text-text-secondary">
                  {m.totalTokens > 0 ? formatTokens(m.totalTokens) : "-"}
                </span>
                <span>
                  <span
                    className="verdict-chip"
                    data-verdict={verdict === "allow" ? "attested" : verdict === "block" ? "block" : "pending"}
                  >
                    {verdict === "allow" ? "ok" : verdict === "block" ? "fail" : "-"}
                  </span>
                </span>
                <span className="text-right">
                  {canRetry ? (
                    <button
                      className="text-text-tertiary hover:text-foreground uppercase tracking-[0.10em] text-[10px]"
                      onClick={() => onRetry(run.id)}
                    >
                      retry
                    </button>
                  ) : (
                    <span className="text-text-tertiary">-</span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Active Sessions Accordion ───────────────────────────────────────────── */

function ActiveSessionsAccordion({
  sessions,
  runs,
  canonicalAgentRef,
  open,
  setOpen,
  onResetSession,
}: {
  sessions: AgentTaskSession[];
  runs: HeartbeatRun[];
  canonicalAgentRef: string;
  open: boolean;
  setOpen: (v: boolean) => void;
  onResetSession: (taskKey: string | null) => void;
}) {
  if (sessions.length === 0) return null;

  return (
    <div className="border-b border-border">
      <button
        className="w-full flex items-center justify-between px-4 py-2 text-left hover:bg-[color-mix(in_oklab,var(--surface-2)_60%,transparent)] transition-colors"
        onClick={() => setOpen(!open)}
      >
        <span className="flex items-center gap-2">
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          <span className="eyebrow">active sessions</span>
          <span className="text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">{sessions.length}</span>
        </span>
      </button>
      {open && (
        <div>
          {sessions.map((s) => {
            const lastRun = runs.find((r) => r.id === s.lastRunId);
            return (
              <div
                key={s.id}
                className="grid grid-cols-[1fr_120px_120px_88px_72px] gap-3 px-4 items-center border-t border-border text-[11px] tabular-nums"
                style={{ height: 28 }}
              >
                <span className="truncate">
                  <span className="text-text-tertiary uppercase tracking-[0.10em] mr-2">task</span>
                  <span className="text-foreground">{s.taskKey}</span>
                </span>
                <span className="text-text-secondary truncate">
                  {s.sessionDisplayId ?? "-"}
                </span>
                <span className="text-text-tertiary">{relativeTime(s.updatedAt)}</span>
                {lastRun ? (
                  <Link
                    to={`/agents/${canonicalAgentRef}/runs/${lastRun.id}`}
                    className="text-foreground no-underline hover:text-[var(--verdict-attested)]"
                  >
                    {shortHash(lastRun.id)}
                  </Link>
                ) : (
                  <span className="text-text-tertiary">-</span>
                )}
                <button
                  className="text-text-tertiary hover:text-[var(--verdict-block)] uppercase tracking-[0.10em] text-[10px] text-right"
                  onClick={() => onResetSession(s.taskKey)}
                >
                  reset
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Configuration Footer (collapsible inline) ───────────────────────────── */

function ConfigurationFooter({
  agent,
  runtimeState,
  reportsToAgent,
  directReports,
  assignedIssuesCount,
  canonicalAgentRef,
  open,
  setOpen,
  onConfigure,
}: {
  agent: Agent;
  runtimeState?: AgentRuntimeState;
  reportsToAgent: Agent | null;
  directReports: Agent[];
  assignedIssuesCount: number;
  canonicalAgentRef: string;
  open: boolean;
  setOpen: (v: boolean) => void;
  onConfigure: () => void;
}) {
  const config = (agent.adapterConfig ?? {}) as Record<string, unknown>;
  const model = typeof config.model === "string" ? config.model : "";
  const heartbeat = (agent.runtimeConfig as Record<string, unknown>)?.heartbeat as Record<string, unknown> | undefined;
  const hbLabel = heartbeat?.enabled
    ? (() => {
      const sec = Number(heartbeat.intervalSec) || 300;
      return sec >= 60 ? `every ${Math.round(sec / 60)}m` : `every ${sec}s`;
    })()
    : "off";

  const rows: Array<{ k: string; v: React.ReactNode }> = [
    { k: "id", v: <span className="font-mono">{shortHash(agent.id)}</span> },
    { k: "url_key", v: <span className="font-mono">{agent.urlKey}</span> },
    { k: "adapter", v: <span>{adapterLabels[agent.adapterType] ?? agent.adapterType}{model ? ` · ${model}` : ""}</span> },
    { k: "heartbeat", v: <span>{hbLabel}</span> },
    { k: "session_id", v: <span className="text-text-secondary">{runtimeState?.sessionDisplayId ?? runtimeState?.sessionId ?? "-"}</span> },
    {
      k: "reports_to",
      v: reportsToAgent
        ? <Link to={`/agents/${agentRouteRef(reportsToAgent)}`} className="text-foreground no-underline hover:text-[var(--verdict-attested)]">{reportsToAgent.name}</Link>
        : <span className="text-text-tertiary">none</span>,
    },
    {
      k: "direct_reports",
      v: directReports.length > 0
        ? <span>{directReports.map((r) => r.name).join(", ")}</span>
        : <span className="text-text-tertiary">none</span>,
    },
    { k: "assigned_tasks", v: <Link to={`/issues?assignee=${agent.id}`} className="text-foreground no-underline hover:text-[var(--verdict-attested)]">{assignedIssuesCount}</Link> },
    { k: "canonical_ref", v: <span className="font-mono text-text-secondary">{canonicalAgentRef}</span> },
  ];

  return (
    <div>
      <button
        className="w-full flex items-center justify-between px-4 py-2 text-left hover:bg-[color-mix(in_oklab,var(--surface-2)_60%,transparent)] transition-colors"
        onClick={() => setOpen(!open)}
      >
        <span className="flex items-center gap-2">
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          <span className="eyebrow">configuration</span>
        </span>
        <span
          className="text-[10px] uppercase tracking-[0.18em] text-text-tertiary hover:text-foreground"
          onClick={(e) => { e.stopPropagation(); onConfigure(); }}
        >
          edit →
        </span>
      </button>
      {open && (
        <div className="border-t border-border">
          {rows.map((r, idx) => (
            <div
              key={r.k}
              className={cn(
                "grid grid-cols-[160px_1fr] gap-3 px-4 text-[11px] items-center",
                idx < rows.length - 1 && "border-b border-border",
              )}
              style={{ height: 26 }}
            >
              <span className="text-text-tertiary uppercase tracking-[0.10em]">{r.k}</span>
              <span className="text-foreground tabular-nums">{r.v}</span>
            </div>
          ))}
          {agent.capabilities && (
            <div className="border-t border-border px-4 py-2 text-[11px]">
              <span className="text-text-tertiary uppercase tracking-[0.10em]">capabilities</span>
              <p className="text-foreground mt-1 whitespace-pre-wrap">{agent.capabilities}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Run Trace Section (with runId) ──────────────────────────────────────── */

function RunTraceSection({
  agent,
  runs,
  selectedRun,
  urlRunId,
  canonicalAgentRef,
  adapterType,
  isMobile,
}: {
  agent: Agent;
  runs: HeartbeatRun[];
  selectedRun: HeartbeatRun | null;
  urlRunId: string;
  canonicalAgentRef: string;
  adapterType: string;
  isMobile: boolean;
}) {
  return (
    <div className="font-mono">
      <RunPillBar
        runs={runs}
        selectedRunId={urlRunId}
        canonicalAgentRef={canonicalAgentRef}
        isMobile={isMobile}
      />
      {selectedRun ? (
        <Tracecard
          key={selectedRun.id}
          run={selectedRun}
          canonicalAgentRef={canonicalAgentRef}
          adapterType={adapterType}
        />
      ) : (
        <div className="px-4 py-6 text-[12px] text-text-tertiary uppercase tracking-[0.10em]">
          run {shortHash(urlRunId)} not found in this worker's history
        </div>
      )}
      <Link
        to={`/agents/${canonicalAgentRef}`}
        className="block px-4 py-2 text-[10px] uppercase tracking-[0.18em] text-text-tertiary hover:text-foreground border-t border-border no-underline"
      >
        ← back to worker · {agent.name}
      </Link>
    </div>
  );
}

/* ── Run Pill Bar ─────────────────────────────────────────────────────────── */

function RunPillBar({
  runs,
  selectedRunId,
  canonicalAgentRef,
  isMobile,
}: {
  runs: HeartbeatRun[];
  selectedRunId: string;
  canonicalAgentRef: string;
  isMobile: boolean;
}) {
  // Most recent on the right => render in reverse-chronological then visually flip
  // Actually render most recent on right by reversing display
  const slice = runs.slice(0, isMobile ? 12 : 24).slice().reverse();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const active = el.querySelector<HTMLElement>('[data-active="true"]');
    if (active) active.scrollIntoView({ inline: "center", block: "nearest" });
  }, [selectedRunId]);

  return (
    <div className="border-b border-border bg-surface-1">
      <div className="flex items-center gap-3 px-4 pt-3 pb-1">
        <span className="eyebrow">trace history</span>
        <span className="text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">
          {runs.length} total
        </span>
      </div>
      <div ref={ref} className="px-4 pb-3 pt-2 overflow-x-auto gitmesh-scrollbar flex items-center gap-1">
        {slice.length === 0 ? (
          <span className="text-[11px] text-text-tertiary">no related runs</span>
        ) : (
          slice.map((r) => {
            const isActive = r.id === selectedRunId;
            const verdict = runVerdict(r);
            return (
              <Link
                key={r.id}
                to={`/agents/${canonicalAgentRef}/runs/${r.id}`}
                data-active={isActive}
                className={cn(
                  "shrink-0 inline-flex items-center gap-1.5 px-2 py-1 border text-[10px] uppercase tracking-[0.10em] no-underline tabular-nums",
                  isActive
                    ? cn(
                      "text-foreground",
                      verdict === "allow" && "border-[var(--verdict-allow)]",
                      verdict === "block" && "border-[var(--verdict-block)]",
                      verdict === "pending" && "border-[var(--verdict-pending)]",
                    )
                    : "border-border text-text-secondary hover:text-foreground hover:border-foreground",
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    verdict === "allow" && "bg-[var(--verdict-allow)]",
                    verdict === "block" && "bg-[var(--verdict-block)]",
                    verdict === "pending" && "bg-[var(--verdict-pending)]",
                  )}
                />
                {shortHash(r.id)}
                <span className="text-text-tertiary">{formatDurationCompact(runDurationSec(r))}</span>
              </Link>
            );
          })
        )}
      </div>
    </div>
  );
}

/* ── Tracecard (replaces RunDetail + LogViewer) ─────────────────────────── */

function Tracecard({
  run,
  canonicalAgentRef,
  adapterType,
}: {
  run: HeartbeatRun;
  canonicalAgentRef: string;
  adapterType: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [claudeLoginResult, setClaudeLoginResult] = useState<ClaudeLoginResult | null>(null);
  const [copiedVerify, setCopiedVerify] = useState(false);
  const m = runMetrics(run);
  const verdict = runVerdict(run);

  useEffect(() => { setClaudeLoginResult(null); }, [run.id]);

  const cancelRun = useMutation({
    mutationFn: () => heartbeatsApi.cancel(run.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.heartbeats(run.projectId, run.agentId) });
    },
  });

  const canResumeLostRun = run.errorCode === "process_lost" && run.status === "failed";
  const resumePayload = useMemo(() => {
    const payload: Record<string, unknown> = { resumeFromRunId: run.id };
    const ctx = asRecord(run.contextSnapshot);
    if (!ctx) return payload;
    const issueId = asNonEmptyString(ctx.issueId);
    const taskId = asNonEmptyString(ctx.taskId);
    const taskKey = asNonEmptyString(ctx.taskKey);
    const commentId = asNonEmptyString(ctx.wakeCommentId) ?? asNonEmptyString(ctx.commentId);
    if (issueId) payload.issueId = issueId;
    if (taskId) payload.taskId = taskId;
    if (taskKey) payload.taskKey = taskKey;
    if (commentId) payload.commentId = commentId;
    return payload;
  }, [run.contextSnapshot, run.id]);

  const resumeRun = useMutation({
    mutationFn: async () => {
      const result = await agentsApi.wakeup(run.agentId, {
        source: "on_demand",
        triggerDetail: "manual",
        reason: "resume_process_lost_run",
        payload: resumePayload,
      }, run.projectId);
      if (!("id" in result)) throw new Error("Resume request was skipped because the worker is not currently invokable.");
      return result;
    },
    onSuccess: (resumedRun) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.heartbeats(run.projectId, run.agentId) });
      navigate(`/agents/${canonicalAgentRef}/runs/${resumedRun.id}`);
    },
  });

  const canRetryRun = run.status === "failed" || run.status === "timed_out";
  const retryPayload = useMemo(() => {
    const payload: Record<string, unknown> = {};
    const ctx = asRecord(run.contextSnapshot);
    if (!ctx) return payload;
    const issueId = asNonEmptyString(ctx.issueId);
    const taskId = asNonEmptyString(ctx.taskId);
    const taskKey = asNonEmptyString(ctx.taskKey);
    if (issueId) payload.issueId = issueId;
    if (taskId) payload.taskId = taskId;
    if (taskKey) payload.taskKey = taskKey;
    return payload;
  }, [run.contextSnapshot]);

  const retryRun = useMutation({
    mutationFn: async () => {
      const result = await agentsApi.wakeup(run.agentId, {
        source: "on_demand",
        triggerDetail: "manual",
        reason: "retry_failed_run",
        payload: retryPayload,
      }, run.projectId);
      if (!("id" in result)) throw new Error("Retry was skipped because the worker is not currently invokable.");
      return result;
    },
    onSuccess: (newRun) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.heartbeats(run.projectId, run.agentId) });
      navigate(`/agents/${canonicalAgentRef}/runs/${newRun.id}`);
    },
  });

  const { data: touchedIssues } = useQuery({
    queryKey: queryKeys.runIssues(run.id),
    queryFn: () => auditLogApi.issuesForRun(run.id),
  });
  const touchedIssueIds = useMemo(
    () => Array.from(new Set((touchedIssues ?? []).map((issue) => issue.issueId))),
    [touchedIssues],
  );

  const clearSessionsForTouchedIssues = useMutation({
    mutationFn: async () => {
      if (touchedIssueIds.length === 0) return 0;
      await Promise.all(touchedIssueIds.map((issueId) => agentsApi.resetSession(run.agentId, issueId, run.projectId)));
      return touchedIssueIds.length;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.runtimeState(run.agentId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.taskSessions(run.agentId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.runIssues(run.id) });
    },
  });

  const runClaudeLogin = useMutation({
    mutationFn: () => agentsApi.loginWithClaude(run.agentId, run.projectId),
    onSuccess: (data) => { setClaudeLoginResult(data); },
  });

  const isRunning = run.status === "running" && !!run.startedAt && !run.finishedAt;
  const [elapsedSec, setElapsedSec] = useState<number>(() => {
    if (!run.startedAt) return 0;
    return Math.max(0, Math.round((Date.now() - new Date(run.startedAt).getTime()) / 1000));
  });
  useEffect(() => {
    if (!isRunning || !run.startedAt) return;
    const startMs = new Date(run.startedAt).getTime();
    setElapsedSec(Math.max(0, Math.round((Date.now() - startMs) / 1000)));
    const id = setInterval(() => {
      setElapsedSec(Math.max(0, Math.round((Date.now() - startMs) / 1000)));
    }, 1000);
    return () => clearInterval(id);
  }, [isRunning, run.startedAt]);

  const startTime = run.startedAt ? timeOfDay(run.startedAt) : null;
  const endTime = run.finishedAt ? timeOfDay(run.finishedAt) : null;
  const durationSec = run.startedAt && run.finishedAt
    ? Math.round((new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime()) / 1000)
    : null;
  const displayDurationSec = durationSec ?? (isRunning ? elapsedSec : null);
  const maxBarSec = Math.max(1, displayDurationSec ?? 0);
  const barPct = displayDurationSec !== null ? Math.max(2, Math.min(100, Math.round((displayDurationSec / Math.max(60, maxBarSec)) * 100))) : 0;
  const hasNonZeroExit = run.exitCode !== null && run.exitCode !== 0;

  const verifyCmd = `gitmesh-agents run inspect ${run.id}`;
  const copyVerify = () => {
    navigator.clipboard.writeText(verifyCmd);
    setCopiedVerify(true);
    setTimeout(() => setCopiedVerify(false), 1500);
  };

  return (
    <div className="border-b border-border">
      {/* Header strip */}
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 px-4 py-3 border-b border-border items-center">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] tabular-nums">
          <span className="font-mono text-foreground">{run.id}</span>
          <span className="verdict-chip" data-verdict={verdict}>{run.status}</span>
          <span className="flex items-center gap-2">
            <span
              className="gm-waterfall-bar w-[160px]"
              data-state={isRunning ? "running" : undefined}
            >
              <span style={{ width: `${barPct}%` }} />
            </span>
            <span className="text-text-tertiary">{formatDurationCompact(displayDurationSec)}</span>
          </span>
          <span
            className="verdict-chip"
            data-verdict={verdict === "allow" ? "attested" : verdict === "block" ? "block" : "pending"}
          >
            {verdict === "allow" ? "attested" : verdict === "block" ? "unverified" : "pending"}
          </span>
        </div>
        <div className="flex items-center gap-2 justify-end text-[10px] uppercase tracking-[0.10em]">
          {(run.status === "running" || run.status === "queued") && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none text-[var(--verdict-block)]"
              onClick={() => cancelRun.mutate()}
              disabled={cancelRun.isPending}
            >
              <X className="h-3 w-3 mr-1" />
              {cancelRun.isPending ? "cancelling…" : "cancel"}
            </Button>
          )}
          {canResumeLostRun && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
              onClick={() => resumeRun.mutate()}
              disabled={resumeRun.isPending}
            >
              <RotateCcw className="h-3 w-3 mr-1" />
              {resumeRun.isPending ? "resuming…" : "resume"}
            </Button>
          )}
          {canRetryRun && !canResumeLostRun && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
              onClick={() => retryRun.mutate()}
              disabled={retryRun.isPending}
            >
              <RotateCcw className="h-3 w-3 mr-1" />
              {retryRun.isPending ? "retrying…" : "retry"}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
            onClick={copyVerify}
            title={verifyCmd}
          >
            <Copy className="h-3 w-3 mr-1" />
            {copiedVerify ? "copied" : "copy verify cmd"}
          </Button>
        </div>
      </div>

      {/* Sub-header: timing + metrics */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-x-4 gap-y-1 px-4 py-2 border-b border-border text-[11px] tabular-nums">
        <span><span className="text-text-tertiary uppercase tracking-[0.10em]">started</span> <span className="text-foreground">{startTime ?? "-"}</span></span>
        <span><span className="text-text-tertiary uppercase tracking-[0.10em]">ended</span> <span className="text-foreground">{endTime ?? "-"}</span></span>
        <span><span className="text-text-tertiary uppercase tracking-[0.10em]">in</span> <span className="text-foreground">{formatTokens(m.input)}</span></span>
        <span><span className="text-text-tertiary uppercase tracking-[0.10em]">out</span> <span className="text-foreground">{formatTokens(m.output)}</span></span>
        <span><span className="text-text-tertiary uppercase tracking-[0.10em]">cached</span> <span className="text-foreground">{formatTokens(m.cached)}</span></span>
        <span><span className="text-text-tertiary uppercase tracking-[0.10em]">cost</span> <span className="text-foreground">{m.cost > 0 ? `$${m.cost.toFixed(4)}` : "-"}</span></span>
      </div>

      {/* Errors / auth recovery */}
      {(run.error || hasNonZeroExit || resumeRun.isError || retryRun.isError) && (
        <div className="border-b border-border px-4 py-2 space-y-1 text-[11px]">
          {run.error && (
            <div className="text-[var(--verdict-block)]">
              <span className="text-text-tertiary uppercase tracking-[0.10em] mr-2">error</span>
              {run.error}{run.errorCode && <span className="text-text-tertiary ml-1">({run.errorCode})</span>}
            </div>
          )}
          {hasNonZeroExit && (
            <div className="text-[var(--verdict-block)]">
              <span className="text-text-tertiary uppercase tracking-[0.10em] mr-2">exit</span>
              {run.exitCode}{run.signal && <span className="text-text-tertiary ml-1">(signal {run.signal})</span>}
            </div>
          )}
          {resumeRun.isError && <div className="text-[var(--verdict-block)]">{resumeRun.error instanceof Error ? resumeRun.error.message : "Failed to resume run"}</div>}
          {retryRun.isError && <div className="text-[var(--verdict-block)]">{retryRun.error instanceof Error ? retryRun.error.message : "Failed to retry run"}</div>}
        </div>
      )}

      {run.errorCode === "claude_auth_required" && adapterType === "claude_local" && (
        <div className="border-b border-border px-4 py-2 space-y-2 text-[11px]">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] border border-border rounded-none"
            onClick={() => runClaudeLogin.mutate()}
            disabled={runClaudeLogin.isPending}
          >
            {runClaudeLogin.isPending ? "running claude login…" : "login to claude"}
          </Button>
          {runClaudeLogin.isError && (
            <p className="text-[var(--verdict-block)]">
              {runClaudeLogin.error instanceof Error ? runClaudeLogin.error.message : "Failed to run Claude login"}
            </p>
          )}
          {claudeLoginResult?.loginUrl && (
            <p>
              <span className="text-text-tertiary uppercase tracking-[0.10em] mr-2">login url</span>
              <a href={claudeLoginResult.loginUrl} className="text-[var(--verdict-attested)] underline underline-offset-2 break-all" target="_blank" rel="noreferrer">
                {claudeLoginResult.loginUrl}
              </a>
            </p>
          )}
          {claudeLoginResult?.stdout && (
            <pre className="bg-surface-2 p-2 text-[11px] whitespace-pre-wrap overflow-x-auto">{claudeLoginResult.stdout}</pre>
          )}
          {claudeLoginResult?.stderr && (
            <pre className="bg-surface-2 p-2 text-[11px] text-[var(--verdict-block)] whitespace-pre-wrap overflow-x-auto">{claudeLoginResult.stderr}</pre>
          )}
        </div>
      )}

      {/* Touched issues */}
      {touchedIssues && touchedIssues.length > 0 && (
        <div className="border-b border-border px-4 py-2 text-[11px]">
          <div className="flex items-center justify-between mb-1">
            <span className="text-text-tertiary uppercase tracking-[0.10em]">issues touched ({touchedIssues.length})</span>
            {touchedIssueIds.length > 0 && (
              <button
                type="button"
                className="text-[10px] uppercase tracking-[0.10em] text-text-tertiary hover:text-foreground disabled:opacity-50"
                disabled={clearSessionsForTouchedIssues.isPending}
                onClick={() => {
                  if (!window.confirm(`Clear session for ${touchedIssueIds.length} issue${touchedIssueIds.length === 1 ? "" : "s"}?`)) return;
                  clearSessionsForTouchedIssues.mutate();
                }}
              >
                {clearSessionsForTouchedIssues.isPending ? "clearing…" : "clear sessions"}
              </button>
            )}
          </div>
          <div className="space-y-0.5">
            {touchedIssues.map((issue) => (
              <Link
                key={issue.issueId}
                to={`/issues/${issue.identifier ?? issue.issueId}`}
                className="flex items-center gap-2 no-underline text-foreground hover:text-[var(--verdict-attested)]"
              >
                <span className="font-mono text-text-tertiary w-20 shrink-0">{issue.identifier ?? shortHash(issue.issueId)}</span>
                <span className="truncate">{issue.title}</span>
                <span className="ml-auto"><StatusBadge status={issue.status} /></span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Session row, inline */}
      {(run.sessionIdBefore || run.sessionIdAfter) && (
        <div className="border-b border-border px-4 py-2 text-[11px] grid grid-cols-1 md:grid-cols-[160px_1fr_1fr] gap-2 items-center">
          <span className="text-text-tertiary uppercase tracking-[0.10em]">session</span>
          {run.sessionIdBefore && (
            <span className="flex items-center gap-2"><span className="text-text-tertiary uppercase tracking-[0.10em] w-12">before</span><CopyText text={run.sessionIdBefore} className="font-mono" /></span>
          )}
          {run.sessionIdAfter && (
            <span className="flex items-center gap-2"><span className="text-text-tertiary uppercase tracking-[0.10em] w-12">after</span><CopyText text={run.sessionIdAfter} className="font-mono" /></span>
          )}
        </div>
      )}

      {/* Inline merged timeline */}
      <InlineTimeline run={run} adapterType={adapterType} />
    </div>
  );
}

/* ── Inline merged timeline (transcript + events as one stream) ─────────── */

type TimelineRow =
  | { kind: "event"; ts: Date; stream: "stdout" | "stderr" | "system" | null; level: "info" | "warn" | "error" | null; text: string; key: string }
  | { kind: "transcript-assistant"; ts: Date; text: string; key: string }
  | { kind: "transcript-thinking"; ts: Date; text: string; key: string }
  | { kind: "transcript-user"; ts: Date; text: string; key: string }
  | { kind: "transcript-tool-call"; ts: Date; name: string; input: unknown; key: string }
  | { kind: "transcript-tool-result"; ts: Date; content: string; isError: boolean; key: string }
  | { kind: "transcript-init"; ts: Date; model: string; sessionId: string | null; key: string }
  | { kind: "transcript-result"; ts: Date; inputTokens: number; outputTokens: number; cachedTokens: number; costUsd: number; subtype: string | null; isError: boolean; errors: string[]; text: string; key: string }
  | { kind: "transcript-raw"; ts: Date; stream: "stdout" | "stderr" | "system"; text: string; key: string };

function InlineTimeline({ run, adapterType }: { run: HeartbeatRun; adapterType: string }) {
  const [events, setEvents] = useState<HeartbeatRunEvent[]>([]);
  const [logLines, setLogLines] = useState<Array<{ ts: string; stream: "stdout" | "stderr" | "system"; chunk: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [logLoading, setLogLoading] = useState(!!run.logRef);
  const [logError, setLogError] = useState<string | null>(null);
  const [logOffset, setLogOffset] = useState(0);
  const [isFollowing, setIsFollowing] = useState(false);
  const [isStreamingConnected, setIsStreamingConnected] = useState(false);
  const [showFailures, setShowFailures] = useState(true);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pendingLogLineRef = useRef("");
  const scrollContainerRef = useRef<ScrollContainer | null>(null);
  const isFollowingRef = useRef(false);
  const lastMetricsRef = useRef<{ scrollHeight: number; distanceFromBottom: number }>({
    scrollHeight: 0,
    distanceFromBottom: Number.POSITIVE_INFINITY,
  });
  const isLive = run.status === "running" || run.status === "queued";

  function isRunLogUnavailable(err: unknown): boolean {
    return err instanceof ApiError && err.status === 404;
  }

  function appendLogContent(content: string, finalize = false) {
    if (!content && !finalize) return;
    const combined = `${pendingLogLineRef.current}${content}`;
    const split = combined.split("\n");
    pendingLogLineRef.current = split.pop() ?? "";
    if (finalize && pendingLogLineRef.current) {
      split.push(pendingLogLineRef.current);
      pendingLogLineRef.current = "";
    }
    const parsed: Array<{ ts: string; stream: "stdout" | "stderr" | "system"; chunk: string }> = [];
    for (const line of split) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const raw = JSON.parse(trimmed) as { ts?: unknown; stream?: unknown; chunk?: unknown };
        const stream = raw.stream === "stderr" || raw.stream === "system" ? raw.stream : "stdout";
        const chunk = typeof raw.chunk === "string" ? raw.chunk : "";
        const ts = typeof raw.ts === "string" ? raw.ts : new Date().toISOString();
        if (!chunk) continue;
        parsed.push({ ts, stream, chunk });
      } catch {
        // ignore malformed lines
      }
    }
    if (parsed.length > 0) setLogLines((prev) => [...prev, ...parsed]);
  }

  const { data: initialEvents } = useQuery({
    queryKey: ["run-events", run.id],
    queryFn: () => heartbeatsApi.events(run.id, 0, 200),
  });

  useEffect(() => {
    if (initialEvents) {
      setEvents(initialEvents);
      setLoading(false);
    }
  }, [initialEvents]);

  const getScrollContainer = useCallback((): ScrollContainer => {
    if (scrollContainerRef.current) return scrollContainerRef.current;
    const container = findScrollContainer(logEndRef.current);
    scrollContainerRef.current = container;
    return container;
  }, []);

  const updateFollowingState = useCallback(() => {
    const container = getScrollContainer();
    const metrics = readScrollMetrics(container);
    lastMetricsRef.current = metrics;
    const nearBottom = metrics.distanceFromBottom <= LIVE_SCROLL_BOTTOM_TOLERANCE_PX;
    isFollowingRef.current = nearBottom;
    setIsFollowing((prev) => (prev === nearBottom ? prev : nearBottom));
  }, [getScrollContainer]);

  useEffect(() => {
    scrollContainerRef.current = null;
    lastMetricsRef.current = { scrollHeight: 0, distanceFromBottom: Number.POSITIVE_INFINITY };
    if (!isLive) {
      isFollowingRef.current = false;
      setIsFollowing(false);
      return;
    }
    updateFollowingState();
  }, [isLive, run.id, updateFollowingState]);

  useEffect(() => {
    if (!isLive) return;
    const container = getScrollContainer();
    updateFollowingState();
    if (container === window) {
      window.addEventListener("scroll", updateFollowingState, { passive: true });
    } else {
      container.addEventListener("scroll", updateFollowingState, { passive: true });
    }
    window.addEventListener("resize", updateFollowingState);
    return () => {
      if (container === window) window.removeEventListener("scroll", updateFollowingState);
      else container.removeEventListener("scroll", updateFollowingState);
      window.removeEventListener("resize", updateFollowingState);
    };
  }, [isLive, run.id, getScrollContainer, updateFollowingState]);

  useEffect(() => {
    if (!isLive || !isFollowingRef.current) return;
    const container = getScrollContainer();
    const previous = lastMetricsRef.current;
    const current = readScrollMetrics(container);
    const growth = Math.max(0, current.scrollHeight - previous.scrollHeight);
    const expectedDistance = previous.distanceFromBottom + growth;
    const movedAwayBy = current.distanceFromBottom - expectedDistance;
    if (movedAwayBy > LIVE_SCROLL_BOTTOM_TOLERANCE_PX) {
      isFollowingRef.current = false;
      setIsFollowing(false);
      lastMetricsRef.current = current;
      return;
    }
    scrollToContainerBottom(container, "auto");
    const after = readScrollMetrics(container);
    lastMetricsRef.current = after;
    if (!isFollowingRef.current) isFollowingRef.current = true;
    setIsFollowing((prev) => (prev ? prev : true));
  }, [events.length, logLines.length, isLive, getScrollContainer]);

  // Persisted shell log
  useEffect(() => {
    let cancelled = false;
    pendingLogLineRef.current = "";
    setLogLines([]);
    setLogOffset(0);
    setLogError(null);

    if (!run.logRef && !isLive) {
      setLogLoading(false);
      return () => { cancelled = true; };
    }
    setLogLoading(true);
    const firstLimit =
      typeof run.logBytes === "number" && run.logBytes > 0
        ? Math.min(Math.max(run.logBytes + 1024, 256_000), 2_000_000)
        : 256_000;

    const load = async () => {
      try {
        let offset = 0;
        let first = true;
        while (!cancelled) {
          const result = await heartbeatsApi.log(run.id, offset, first ? firstLimit : 256_000);
          if (cancelled) break;
          appendLogContent(result.content, result.nextOffset === undefined);
          const next = result.nextOffset ?? offset + result.content.length;
          setLogOffset(next);
          offset = next;
          first = false;
          if (result.nextOffset === undefined || isLive) break;
        }
      } catch (err) {
        if (!cancelled) {
          if (isLive && isRunLogUnavailable(err)) { setLogLoading(false); return; }
          setLogError(err instanceof Error ? err.message : "Failed to load run log");
        }
      } finally {
        if (!cancelled) setLogLoading(false);
      }
    };

    void load();
    return () => { cancelled = true; };
  }, [run.id, run.logRef, run.logBytes, isLive]);

  // Poll events for live runs (when ws not connected)
  useEffect(() => {
    if (!isLive || isStreamingConnected) return;
    const interval = setInterval(async () => {
      const maxSeq = events.length > 0 ? Math.max(...events.map((e) => e.seq)) : 0;
      try {
        const newEvents = await heartbeatsApi.events(run.id, maxSeq, 100);
        if (newEvents.length > 0) setEvents((prev) => [...prev, ...newEvents]);
      } catch { /* ignore */ }
    }, 2000);
    return () => clearInterval(interval);
  }, [run.id, isLive, isStreamingConnected, events]);

  // Poll log for live runs
  useEffect(() => {
    if (!isLive || isStreamingConnected) return;
    const interval = setInterval(async () => {
      try {
        const result = await heartbeatsApi.log(run.id, logOffset, 256_000);
        if (result.content) appendLogContent(result.content, result.nextOffset === undefined);
        if (result.nextOffset !== undefined) setLogOffset(result.nextOffset);
        else if (result.content.length > 0) setLogOffset((prev) => prev + result.content.length);
      } catch (err) {
        if (isRunLogUnavailable(err)) return;
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [run.id, isLive, isStreamingConnected, logOffset]);

  // WebSocket live updates (drives LiveUpdatesProvider's stream too)
  useEffect(() => {
    if (!isLive) return;
    let closed = false;
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;

    const scheduleReconnect = () => {
      if (closed) return;
      reconnectTimer = window.setTimeout(connect, 1500);
    };

    const connect = () => {
      if (closed) return;
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const url = `${protocol}://${window.location.host}/api/projects/${encodeURIComponent(run.projectId)}/events/ws`;
      socket = new WebSocket(url);

      socket.onopen = () => { setIsStreamingConnected(true); };

      socket.onmessage = (message) => {
        const rawMessage = typeof message.data === "string" ? message.data : "";
        if (!rawMessage) return;

        let event: LiveEvent;
        try { event = JSON.parse(rawMessage) as LiveEvent; } catch { return; }

        if (event.projectId !== run.projectId) return;
        const payload = asRecord(event.payload);
        const eventRunId = asNonEmptyString(payload?.runId);
        if (!payload || eventRunId !== run.id) return;

        if (event.type === "heartbeat.run.log") {
          const chunk = typeof payload.chunk === "string" ? payload.chunk : "";
          if (!chunk) return;
          const streamRaw = asNonEmptyString(payload.stream);
          const stream = streamRaw === "stderr" || streamRaw === "system" ? streamRaw : "stdout";
          const ts = asNonEmptyString((payload as Record<string, unknown>).ts) ?? event.createdAt;
          setLogLines((prev) => [...prev, { ts, stream, chunk }]);
          return;
        }

        if (event.type !== "heartbeat.run.event") return;

        const seq = typeof payload.seq === "number" ? payload.seq : null;
        if (seq === null || !Number.isFinite(seq)) return;

        const streamRaw = asNonEmptyString(payload.stream);
        const stream = streamRaw === "stdout" || streamRaw === "stderr" || streamRaw === "system" ? streamRaw : null;
        const levelRaw = asNonEmptyString(payload.level);
        const level = levelRaw === "info" || levelRaw === "warn" || levelRaw === "error" ? levelRaw : null;

        const liveEvent: HeartbeatRunEvent = {
          id: seq,
          projectId: run.projectId,
          runId: run.id,
          agentId: run.agentId,
          seq,
          eventType: asNonEmptyString(payload.eventType) ?? "event",
          stream,
          level,
          color: asNonEmptyString(payload.color),
          message: asNonEmptyString(payload.message),
          payload: asRecord(payload.payload),
          createdAt: new Date(event.createdAt),
        };

        setEvents((prev) => {
          if (prev.some((existing) => existing.seq === seq)) return prev;
          return [...prev, liveEvent];
        });
      };

      socket.onerror = () => { socket?.close(); };
      socket.onclose = () => {
        setIsStreamingConnected(false);
        scheduleReconnect();
      };
    };

    connect();

    return () => {
      closed = true;
      setIsStreamingConnected(false);
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (socket) {
        socket.onopen = null; socket.onmessage = null; socket.onerror = null; socket.onclose = null;
        socket.close(1000, "tracecard_unmount");
      }
    };
  }, [isLive, run.projectId, run.id, run.agentId]);

  const adapterInvokePayload = useMemo(() => {
    const evt = events.find((e) => e.eventType === "adapter.invoke");
    return asRecord(evt?.payload ?? null);
  }, [events]);

  const adapter = useMemo(() => getUIAdapter(adapterType), [adapterType]);
  const transcript = useMemo(() => buildTranscript(logLines, adapter.parseStdoutLine), [logLines, adapter]);

  const merged = useMemo<TimelineRow[]>(() => {
    const rows: TimelineRow[] = [];
    for (const evt of events) {
      // Skip adapter.invoke since rendered as separate header
      if (evt.eventType === "adapter.invoke") continue;
      rows.push({
        kind: "event",
        ts: new Date(evt.createdAt),
        stream: evt.stream,
        level: evt.level,
        text: evt.message ?? (evt.payload ? JSON.stringify(evt.payload) : ""),
        key: `e-${evt.id}-${evt.seq}`,
      });
    }
    transcript.forEach((entry, idx) => {
      const ts = new Date(entry.ts);
      switch (entry.kind) {
        case "assistant": rows.push({ kind: "transcript-assistant", ts, text: entry.text, key: `t-a-${idx}` }); break;
        case "thinking": rows.push({ kind: "transcript-thinking", ts, text: entry.text, key: `t-th-${idx}` }); break;
        case "user": rows.push({ kind: "transcript-user", ts, text: entry.text, key: `t-u-${idx}` }); break;
        case "tool_call": rows.push({ kind: "transcript-tool-call", ts, name: entry.name, input: entry.input, key: `t-tc-${idx}` }); break;
        case "tool_result": rows.push({ kind: "transcript-tool-result", ts, content: entry.content, isError: entry.isError, key: `t-tr-${idx}` }); break;
        case "init": rows.push({ kind: "transcript-init", ts, model: entry.model, sessionId: entry.sessionId, key: `t-i-${idx}` }); break;
        case "result": rows.push({ kind: "transcript-result", ts, inputTokens: entry.inputTokens, outputTokens: entry.outputTokens, cachedTokens: entry.cachedTokens, costUsd: entry.costUsd, subtype: entry.subtype ?? null, isError: entry.isError, errors: entry.errors, text: entry.text, key: `t-r-${idx}` }); break;
        default: {
          const stream = entry.kind === "stderr" ? "stderr" : entry.kind === "system" ? "system" : "stdout";
          rows.push({ kind: "transcript-raw", ts, stream, text: entry.text, key: `t-raw-${idx}` });
        }
      }
    });
    rows.sort((a, b) => a.ts.getTime() - b.ts.getTime());
    return rows;
  }, [events, transcript]);

  if (loading && logLoading) {
    return <div className="px-4 py-3 text-[11px] text-text-tertiary uppercase tracking-[0.10em]">loading trace…</div>;
  }
  if (events.length === 0 && logLines.length === 0 && !logError) {
    return <div className="px-4 py-3 text-[11px] text-text-tertiary uppercase tracking-[0.10em]">no trace events</div>;
  }

  return (
    <div className="text-[11px]">
      {adapterInvokePayload && (
        <details className="border-b border-border">
          <summary className="cursor-pointer px-4 py-2 flex items-center gap-2 hover:bg-[color-mix(in_oklab,var(--surface-2)_60%,transparent)]">
            <span className="eyebrow">invocation</span>
            {typeof adapterInvokePayload.adapterType === "string" && (
              <span className="text-text-secondary uppercase tracking-[0.10em] text-[10px]">{adapterInvokePayload.adapterType}</span>
            )}
          </summary>
          <div className="px-4 py-2 space-y-2">
            {typeof adapterInvokePayload.cwd === "string" && (
              <div className="break-all"><span className="text-text-tertiary uppercase tracking-[0.10em] mr-2">cwd</span><span className="font-mono">{adapterInvokePayload.cwd}</span></div>
            )}
            {typeof adapterInvokePayload.command === "string" && (
              <div className="break-all">
                <span className="text-text-tertiary uppercase tracking-[0.10em] mr-2">cmd</span>
                <span className="font-mono">
                  {[
                    adapterInvokePayload.command,
                    ...(Array.isArray(adapterInvokePayload.commandArgs)
                      ? adapterInvokePayload.commandArgs.filter((v): v is string => typeof v === "string")
                      : []),
                  ].join(" ")}
                </span>
              </div>
            )}
            {Array.isArray(adapterInvokePayload.commandNotes) && adapterInvokePayload.commandNotes.length > 0 && (
              <ul className="list-disc pl-5 space-y-1">
                {adapterInvokePayload.commandNotes
                  .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
                  .map((note, idx) => (<li key={`${idx}-${note}`} className="break-all font-mono">{note}</li>))}
              </ul>
            )}
            {adapterInvokePayload.prompt !== undefined && (
              <div>
                <div className="text-text-tertiary uppercase tracking-[0.10em] mb-1">prompt</div>
                <pre className="bg-surface-2 p-2 overflow-x-auto whitespace-pre-wrap">
                  {typeof adapterInvokePayload.prompt === "string" ? adapterInvokePayload.prompt : JSON.stringify(adapterInvokePayload.prompt, null, 2)}
                </pre>
              </div>
            )}
            {adapterInvokePayload.context !== undefined && (
              <div>
                <div className="text-text-tertiary uppercase tracking-[0.10em] mb-1">context</div>
                <pre className="bg-surface-2 p-2 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(adapterInvokePayload.context, null, 2)}</pre>
              </div>
            )}
            {adapterInvokePayload.env !== undefined && (
              <div>
                <div className="text-text-tertiary uppercase tracking-[0.10em] mb-1">env</div>
                <pre className="bg-surface-2 p-2 overflow-x-auto whitespace-pre-wrap font-mono">{formatEnvForDisplay(adapterInvokePayload.env)}</pre>
              </div>
            )}
          </div>
        </details>
      )}

      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="eyebrow">trace · {merged.length} events</span>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.10em] text-text-tertiary cursor-pointer">
            <input
              type="checkbox"
              checked={showFailures}
              onChange={(e) => setShowFailures(e.target.checked)}
              className="h-3 w-3"
            />
            expand failures
          </label>
          {isLive && !isFollowing && (
            <button
              onClick={() => {
                const container = getScrollContainer();
                isFollowingRef.current = true;
                setIsFollowing(true);
                scrollToContainerBottom(container, "auto");
                lastMetricsRef.current = readScrollMetrics(container);
              }}
              className="text-[10px] uppercase tracking-[0.10em] text-text-tertiary hover:text-foreground"
            >
              jump to live
            </button>
          )}
          {isLive && (
            <span className="flex items-center gap-1 text-[10px] uppercase tracking-[0.10em] text-[var(--verdict-attested)]">
              <span className="gm-pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--verdict-attested)]" />
              live
            </span>
          )}
        </div>
      </div>

      <div className="px-4 py-2">
        {merged.map((row) => (
          <TimelineRowView key={row.key} row={row} expandFailures={showFailures} />
        ))}
        {logError && <div className="text-[var(--verdict-block)] mt-2">{logError}</div>}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}

function TimelineRowView({ row, expandFailures }: { row: TimelineRow; expandFailures: boolean }) {
  const ts = timeOfDay(row.ts);
  const baseGrid = "grid grid-cols-[64px_88px_1fr] gap-2 items-baseline";
  const tsCell = "text-text-tertiary tabular-nums select-none text-[10px]";
  const lblCell = "text-[10px] uppercase tracking-[0.10em]";

  switch (row.kind) {
    case "event": {
      const streamLabel = row.stream ? `[${row.stream}]` : "[event]";
      const color =
        row.level === "error" || row.stream === "stderr" ? "text-[var(--verdict-block)]"
          : row.level === "warn" ? "text-[var(--verdict-pending)]"
            : row.stream === "system" ? "text-text-tertiary"
              : "text-foreground";
      return (
        <div className={baseGrid}>
          <span className={tsCell}>{ts}</span>
          <span className={cn(lblCell, color)}>{streamLabel}</span>
          <span className={cn("whitespace-pre-wrap break-words", color)}>{row.text}</span>
        </div>
      );
    }
    case "transcript-assistant":
      return (
        <div className={baseGrid}>
          <span className={tsCell}>{ts}</span>
          <span className={cn(lblCell, "text-[var(--verdict-allow)]")}>[assistant]</span>
          <span className="whitespace-pre-wrap break-words text-foreground">{row.text}</span>
        </div>
      );
    case "transcript-thinking":
      return (
        <div className={baseGrid}>
          <span className={tsCell}>{ts}</span>
          <span className={cn(lblCell, "text-text-tertiary")}>[thinking]</span>
          <span className="whitespace-pre-wrap break-words text-text-secondary italic">{row.text}</span>
        </div>
      );
    case "transcript-user":
      return (
        <div className={baseGrid}>
          <span className={tsCell}>{ts}</span>
          <span className={cn(lblCell, "text-text-secondary")}>[user]</span>
          <span className="whitespace-pre-wrap break-words text-foreground">{row.text}</span>
        </div>
      );
    case "transcript-tool-call":
      return (
        <details className={baseGrid} open={false}>
          <summary className="contents cursor-pointer">
            <span className={tsCell}>{ts}</span>
            <span className={cn(lblCell, "text-[var(--verdict-pending)]")}>[tool_call]</span>
            <span className="text-foreground truncate">{row.name}</span>
          </summary>
          <span />
          <span />
          <pre className="col-start-3 bg-surface-2 p-2 mt-1 text-[10px] overflow-x-auto whitespace-pre-wrap text-foreground">
            {JSON.stringify(row.input, null, 2)}
          </pre>
        </details>
      );
    case "transcript-tool-result":
      return (
        <details className={baseGrid} open={row.isError && expandFailures}>
          <summary className="contents cursor-pointer">
            <span className={tsCell}>{ts}</span>
            <span className={cn(lblCell, row.isError ? "text-[var(--verdict-block)]" : "text-text-secondary")}>[tool_result]</span>
            <span className={cn(row.isError ? "text-[var(--verdict-block)]" : "text-text-secondary", "truncate")}>
              {row.isError ? "error" : "ok"}
            </span>
          </summary>
          <span />
          <span />
          <pre className={cn(
            "col-start-3 p-2 mt-1 text-[10px] overflow-x-auto whitespace-pre-wrap max-h-60 overflow-y-auto",
            row.isError ? "bg-[color-mix(in_oklab,var(--verdict-block)_8%,var(--surface-2))] text-[var(--verdict-block)]" : "bg-surface-2 text-text-secondary",
          )}>
            {(() => { try { return JSON.stringify(JSON.parse(row.content), null, 2); } catch { return row.content; } })()}
          </pre>
        </details>
      );
    case "transcript-init":
      return (
        <div className={baseGrid}>
          <span className={tsCell}>{ts}</span>
          <span className={cn(lblCell, "text-text-tertiary")}>[init]</span>
          <span className="text-text-secondary">model={row.model}{row.sessionId ? ` session=${row.sessionId}` : ""}</span>
        </div>
      );
    case "transcript-result": {
      const failed = row.isError || row.errors.length > 0;
      return (
        <details className={baseGrid} open={failed && expandFailures}>
          <summary className="contents cursor-pointer">
            <span className={tsCell}>{ts}</span>
            <span className={cn(lblCell, failed ? "text-[var(--verdict-block)]" : "text-[var(--verdict-attested)]")}>[result]</span>
            <span className="text-foreground tabular-nums">
              tokens in={formatTokens(row.inputTokens)} out={formatTokens(row.outputTokens)} cached={formatTokens(row.cachedTokens)} cost=${row.costUsd.toFixed(6)}
            </span>
          </summary>
          {(row.subtype || failed) && (
            <>
              <span /><span />
              <div className="col-start-3 mt-1 text-[var(--verdict-block)] whitespace-pre-wrap break-words">
                subtype={row.subtype || "unknown"} is_error={row.isError ? "true" : "false"}
                {row.errors.length > 0 ? ` errors=${row.errors.join(" | ")}` : ""}
              </div>
            </>
          )}
          {row.text && (
            <>
              <span /><span />
              <div className="col-start-3 mt-1 whitespace-pre-wrap break-words text-foreground">{row.text}</div>
            </>
          )}
        </details>
      );
    }
    case "transcript-raw": {
      const color = row.stream === "stderr" ? "text-[var(--verdict-block)]"
        : row.stream === "system" ? "text-text-tertiary"
          : "text-foreground";
      return (
        <div className={baseGrid}>
          <span className={tsCell}>{ts}</span>
          <span className={cn(lblCell, color)}>[{row.stream}]</span>
          <span className={cn("whitespace-pre-wrap break-words", color)}>{row.text}</span>
        </div>
      );
    }
  }
}

/* ── Configure / Keys / Revisions blocks (within slide-over) ────────────── */

function ConfigureBlock({
  agent,
  projectId,
  onDirtyChange,
  onSaveActionChange,
  onCancelActionChange,
  onSavingChange,
  updatePermissions,
}: {
  agent: Agent;
  projectId?: string;
  onDirtyChange: (dirty: boolean) => void;
  onSaveActionChange: (save: (() => void) | null) => void;
  onCancelActionChange: (cancel: (() => void) | null) => void;
  onSavingChange: (saving: boolean) => void;
  updatePermissions: { mutate: (canCreate: boolean) => void; isPending: boolean };
}) {
  const queryClient = useQueryClient();

  const { data: adapterModels } = useQuery({
    queryKey:
      projectId
        ? queryKeys.agents.adapterModels(projectId, agent.adapterType)
        : ["agents", "none", "adapter-models", agent.adapterType],
    queryFn: () => agentsApi.adapterModels(projectId!, agent.adapterType),
    enabled: Boolean(projectId),
  });

  const updateAgent = useMutation({
    mutationFn: (data: Record<string, unknown>) => agentsApi.update(agent.id, data, projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(agent.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(agent.urlKey) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.configRevisions(agent.id) });
    },
  });

  useEffect(() => { onSavingChange(updateAgent.isPending); }, [onSavingChange, updateAgent.isPending]);

  return (
    <div className="space-y-5">
      <AgentConfigForm
        mode="edit"
        agent={agent}
        onSave={(patch) => updateAgent.mutate(patch)}
        isSaving={updateAgent.isPending}
        adapterModels={adapterModels}
        onDirtyChange={onDirtyChange}
        onSaveActionChange={onSaveActionChange}
        onCancelActionChange={onCancelActionChange}
        hideInlineSave
        sectionLayout="cards"
      />
      <div>
        <span className="eyebrow block mb-2">permissions</span>
        <div className="border border-border px-3 py-2 flex items-center justify-between text-[12px] font-mono">
          <span>can_create_workers</span>
          <Button
            variant={agent.permissions?.canCreateAgents ? "default" : "outline"}
            size="sm"
            className="h-7 px-2 font-mono text-[10px] uppercase tracking-[0.10em] rounded-none"
            onClick={() => updatePermissions.mutate(!Boolean(agent.permissions?.canCreateAgents))}
            disabled={updatePermissions.isPending}
          >
            {agent.permissions?.canCreateAgents ? "on" : "off"}
          </Button>
        </div>
      </div>
    </div>
  );
}

function RevisionsBlock({ agent, projectId }: { agent: Agent; projectId?: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: configRevisions } = useQuery({
    queryKey: queryKeys.agents.configRevisions(agent.id),
    queryFn: () => agentsApi.listConfigRevisions(agent.id, projectId),
  });

  const rollbackConfig = useMutation({
    mutationFn: (revisionId: string) => agentsApi.rollbackConfigRevision(agent.id, revisionId, projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(agent.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.detail(agent.urlKey) });
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.configRevisions(agent.id) });
    },
  });

  return (
    <div>
      <button
        className="flex items-center gap-2 hover:text-foreground transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <span className="eyebrow">revisions</span>
        <span className="text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">
          {configRevisions?.length ?? 0}
        </span>
      </button>
      {open && (
        <div className="mt-2">
          {(configRevisions ?? []).length === 0 ? (
            <p className="text-[11px] text-text-tertiary uppercase tracking-[0.10em]">none</p>
          ) : (
            <div className="border border-border">
              {(configRevisions ?? []).slice(0, 10).map((revision, idx, arr) => (
                <div
                  key={revision.id}
                  className={cn(
                    "px-3 py-2 grid grid-cols-[88px_120px_1fr_72px] gap-2 items-center text-[11px] tabular-nums",
                    idx < arr.length - 1 && "border-b border-border",
                  )}
                >
                  <span className="font-mono text-foreground">{shortHash(revision.id)}</span>
                  <span className="text-text-secondary">{formatDate(revision.createdAt)}</span>
                  <span className="text-text-tertiary truncate">
                    {revision.changedKeys.length > 0 ? revision.changedKeys.join(", ") : "no changes"}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 px-2 font-mono text-[10px] uppercase tracking-[0.10em] rounded-none"
                    onClick={() => rollbackConfig.mutate(revision.id)}
                    disabled={rollbackConfig.isPending}
                  >
                    restore
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function KeysBlock({ agentId, projectId }: { agentId: string; projectId?: string }) {
  const queryClient = useQueryClient();
  const [newKeyName, setNewKeyName] = useState("");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [tokenVisible, setTokenVisible] = useState(false);
  const [copied, setCopied] = useState(false);

  const { data: keys, isLoading } = useQuery({
    queryKey: queryKeys.agents.keys(agentId),
    queryFn: () => agentsApi.listKeys(agentId, projectId),
  });

  const createKey = useMutation({
    mutationFn: () => agentsApi.createKey(agentId, newKeyName.trim() || "Default", projectId),
    onSuccess: (data) => {
      setNewToken(data.token);
      setTokenVisible(true);
      setNewKeyName("");
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.keys(agentId) });
    },
  });

  const revokeKey = useMutation({
    mutationFn: (keyId: string) => agentsApi.revokeKey(agentId, keyId, projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.keys(agentId) });
    },
  });

  function copyToken() {
    if (!newToken) return;
    navigator.clipboard.writeText(newToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const activeKeys = (keys ?? []).filter((k: AgentKey) => !k.revokedAt);
  const revokedKeys = (keys ?? []).filter((k: AgentKey) => k.revokedAt);

  return (
    <div className="space-y-3">
      <span className="eyebrow block">api keys</span>

      {newToken && (
        <div className="border border-[var(--verdict-pending)] p-3 space-y-2 text-[11px]">
          <p className="text-[var(--verdict-pending)] uppercase tracking-[0.10em]">key issued - copy now, will not be shown again</p>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-surface-2 px-2 py-1 font-mono text-[var(--verdict-allow)] truncate">
              {tokenVisible ? newToken : newToken.replace(/./g, "•")}
            </code>
            <Button variant="ghost" size="icon-sm" className="rounded-none" onClick={() => setTokenVisible((v) => !v)}>
              {tokenVisible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </Button>
            <Button variant="ghost" size="icon-sm" className="rounded-none" onClick={copyToken}>
              <Copy className="h-3.5 w-3.5" />
            </Button>
            {copied && <span className="text-[var(--verdict-allow)]">copied</span>}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="font-mono text-[10px] uppercase tracking-[0.10em] rounded-none"
            onClick={() => setNewToken(null)}
          >
            dismiss
          </Button>
        </div>
      )}

      <div className="border border-border p-3 space-y-2">
        <div className="flex items-center gap-1.5 text-text-tertiary uppercase tracking-[0.10em] text-[10px]">
          <Key className="h-3 w-3" /> create key
        </div>
        <div className="flex items-center gap-2">
          <Input
            placeholder="key name (e.g. production)"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            className="h-8 text-[12px] font-mono"
            onKeyDown={(e) => { if (e.key === "Enter") createKey.mutate(); }}
          />
          <Button
            size="sm"
            className="h-8 px-2 font-mono text-[10px] uppercase tracking-[0.10em] rounded-none"
            onClick={() => createKey.mutate()}
            disabled={createKey.isPending}
          >
            <Plus className="h-3 w-3 mr-1" /> create
          </Button>
        </div>
      </div>

      {isLoading && <p className="text-[11px] text-text-tertiary">loading…</p>}
      {!isLoading && activeKeys.length === 0 && !newToken && (
        <p className="text-[11px] text-text-tertiary uppercase tracking-[0.10em]">no active keys</p>
      )}

      {activeKeys.length > 0 && (
        <div className="border border-border">
          {activeKeys.map((key: AgentKey, idx: number) => (
            <div
              key={key.id}
              className={cn(
                "flex items-center justify-between px-3 py-2 text-[11px]",
                idx < activeKeys.length - 1 && "border-b border-border",
              )}
            >
              <span className="font-mono">
                {key.name}
                <span className="text-text-tertiary ml-2">{formatDate(key.createdAt)}</span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive font-mono text-[10px] uppercase tracking-[0.10em] rounded-none"
                onClick={() => revokeKey.mutate(key.id)}
                disabled={revokeKey.isPending}
              >
                revoke
              </Button>
            </div>
          ))}
        </div>
      )}

      {revokedKeys.length > 0 && (
        <div className="border border-border opacity-50">
          {revokedKeys.map((key: AgentKey, idx: number) => (
            <div
              key={key.id}
              className={cn(
                "flex items-center justify-between px-3 py-2 text-[11px]",
                idx < revokedKeys.length - 1 && "border-b border-border",
              )}
            >
              <span className="font-mono line-through">
                {key.name}
                <span className="text-text-tertiary ml-2">
                  revoked {key.revokedAt ? formatDate(key.revokedAt) : ""}
                </span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

