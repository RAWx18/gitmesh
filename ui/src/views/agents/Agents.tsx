import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useNavigate, useLocation } from "@/lib/router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentsApi } from "@/api/agents";
import { heartbeatsApi } from "@/api/heartbeats";
import { useProject } from "@/context/ProjectContext";
import { useDialog } from "@/context/DialogContext";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { queryKeys } from "@/lib/queryKeys";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { relativeTime, agentRouteRef, agentUrl } from "@/lib/utils";
import { Bot } from "lucide-react";
import { AGENT_ROLE_LABELS, type Agent } from "@gitmesh/core";
import type { HeartbeatRun } from "@gitmesh/core";

// ── Labels ─────────────────────────────────────────────────────────────

const ADAPTER_LABELS: Record<string, string> = {
  claude_local: "claude",
  codex_local: "codex",
  opencode_local: "opencode",
  cursor: "cursor",
  gateway: "gateway",
  process: "process",
  http: "http",
};

const ROLE_LABELS = AGENT_ROLE_LABELS as Record<string, string>;

// ── Pill / filter routing ──────────────────────────────────────────────

type RoutePathSegment = "all" | "active" | "paused" | "error";
type PillKey = "all" | "running" | "idle" | "paused" | "error";

const PILL_ORDER: PillKey[] = ["all", "running", "idle", "paused", "error"];

function pillToRoute(pill: PillKey): { segment: RoutePathSegment; status?: "running" | "idle" } {
  switch (pill) {
    case "all":
      return { segment: "all" };
    case "running":
      return { segment: "active", status: "running" };
    case "idle":
      return { segment: "active", status: "idle" };
    case "paused":
      return { segment: "paused" };
    case "error":
      return { segment: "error" };
  }
}

function pillFromUrl(segment: RoutePathSegment, statusParam: string | null): PillKey {
  if (segment === "all") return "all";
  if (segment === "active") {
    if (statusParam === "running") return "running";
    if (statusParam === "idle") return "idle";
    return "running";
  }
  return segment;
}

function statusMatchesPill(status: Agent["status"], pill: PillKey): boolean {
  switch (pill) {
    case "all":
      return true;
    case "running":
      return status === "running" || status === "active";
    case "idle":
      return status === "idle";
    case "paused":
      return status === "paused";
    case "error":
      return status === "error";
  }
}

// ── Status → verdict color ─────────────────────────────────────────────

function statusVerdict(status: string): "allow" | "block" | "pending" | "attested" | "neutral" {
  switch (status) {
    case "running":
    case "active":
      return "attested";
    case "idle":
      return "allow";
    case "paused":
    case "pending_approval":
      return "pending";
    case "error":
      return "block";
    default:
      return "neutral";
  }
}

function verdictVar(v: ReturnType<typeof statusVerdict>): string {
  switch (v) {
    case "allow":
      return "var(--verdict-allow)";
    case "block":
      return "var(--verdict-block)";
    case "pending":
      return "var(--verdict-pending)";
    case "attested":
      return "var(--verdict-attested)";
    case "neutral":
    default:
      return "var(--text-tertiary)";
  }
}

function normalizeStatusLabel(status: string): string {
  switch (status) {
    case "active":
      return "running";
    case "pending_approval":
      return "paused";
    default:
      return status;
  }
}

// ── Live runs (queued/running grouped by agent) ────────────────────────

function useLiveRuns(runs?: HeartbeatRun[]) {
  return useMemo(() => {
    const byAgent = new Map<string, { runId: string; liveCount: number }>();
    for (const run of runs ?? []) {
      if (run.status !== "running" && run.status !== "queued") continue;
      const existing = byAgent.get(run.agentId);
      if (existing) {
        existing.liveCount += 1;
      } else {
        byAgent.set(run.agentId, { runId: run.id, liveCount: 1 });
      }
    }
    return byAgent;
  }, [runs]);
}

// Build per-agent recent run history (latest first), capped to 14.
function useRecentRunsByAgent(runs?: HeartbeatRun[]) {
  return useMemo(() => {
    const m = new Map<string, HeartbeatRun[]>();
    for (const r of runs ?? []) {
      const arr = m.get(r.agentId) ?? [];
      arr.push(r);
      m.set(r.agentId, arr);
    }
    for (const [k, arr] of m) {
      arr.sort((a, b) => {
        const at = new Date(a.createdAt).getTime();
        const bt = new Date(b.createdAt).getTime();
        return bt - at;
      });
      m.set(k, arr.slice(0, 14));
    }
    return m;
  }, [runs]);
}

// ── Pulse strip (per row) ──────────────────────────────────────────────

function PulseStrip({ runs }: { runs: HeartbeatRun[] }) {
  const W = 80;
  const H = 14;
  const slots = 14;
  const slotW = W / slots;
  // Render newest on the right.
  const cells = [...runs].reverse();
  const padding = Math.max(0, slots - cells.length);

  function runColor(run: HeartbeatRun): string {
    switch (run.status) {
      case "succeeded":
        return "var(--verdict-allow)";
      case "failed":
      case "timed_out":
      case "cancelled":
        return "var(--verdict-block)";
      case "queued":
      case "running":
      default:
        return "var(--verdict-pending)";
    }
  }

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      aria-hidden
      style={{ display: "block" }}
    >
      {/* baseline ticks for empty slots */}
      {Array.from({ length: padding }).map((_, i) => (
        <rect
          key={`pad-${i}`}
          x={i * slotW + 1}
          y={H / 2 - 0.5}
          width={Math.max(1, slotW - 2)}
          height={1}
          fill="var(--border)"
        />
      ))}
      {cells.map((r, i) => (
        <rect
          key={r.id}
          x={(padding + i) * slotW + 1}
          y={2}
          width={Math.max(1, slotW - 2)}
          height={H - 4}
          fill={runColor(r)}
          opacity={0.95}
        />
      ))}
    </svg>
  );
}

// ── Budget bar ─────────────────────────────────────────────────────────

function BudgetBar({ spentCents, capCents }: { spentCents: number; capCents: number }) {
  const W = 60;
  const H = 6;
  if (!capCents || capCents <= 0) {
    // No cap - single tick mark
    return (
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden style={{ display: "block" }}>
        <rect x={0} y={H / 2 - 0.5} width={W} height={1} fill="var(--border)" />
        <rect x={W / 2 - 0.5} y={1} width={1} height={H - 2} fill="var(--text-tertiary)" />
      </svg>
    );
  }
  const ratio = Math.max(0, Math.min(1.5, spentCents / capCents));
  const fillRatio = Math.min(1, ratio);
  const color =
    ratio > 0.85
      ? "var(--verdict-block)"
      : ratio > 0.6
        ? "var(--verdict-pending)"
        : "var(--verdict-attested)";
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden style={{ display: "block" }}>
      <rect x={0} y={0} width={W} height={H} fill="var(--surface-2)" />
      <rect x={0} y={0} width={W * fillRatio} height={H} fill={color} />
      <rect x={0} y={0} width={W} height={H} fill="none" stroke="var(--border)" strokeWidth={1} />
    </svg>
  );
}

// ── Header pills ───────────────────────────────────────────────────────

function PillBar({
  active,
  onSelect,
  counts,
}: {
  active: PillKey;
  onSelect: (p: PillKey) => void;
  counts: Record<PillKey, number>;
}) {
  return (
    <div
      className="flex items-center gap-2"
      style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}
    >
      {PILL_ORDER.map((p, i) => {
        const isActive = p === active;
        return (
          <span key={p} className="flex items-center gap-2">
            {i > 0 && <span style={{ color: "var(--text-tertiary)" }}>·</span>}
            <button
              type="button"
              onClick={() => onSelect(p)}
              className="px-1.5 py-0 transition-colors"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                lineHeight: "18px",
                color: isActive ? "var(--foreground)" : "var(--text-tertiary)",
                outline: isActive ? "1px solid var(--verdict-attested)" : "1px solid transparent",
                background: "transparent",
                cursor: "pointer",
              }}
            >
              {p}
              <span
                className="ml-1 tabular-nums"
                style={{ color: isActive ? "var(--text-secondary)" : "var(--text-tertiary)" }}
              >
                {counts[p]}
              </span>
            </button>
          </span>
        );
      })}
    </div>
  );
}

// ── Roster row ─────────────────────────────────────────────────────────

const GRID_TEMPLATE =
  "16px 18px minmax(160px,1.4fr) minmax(120px,1fr) 90px 80px 90px 88px 70px minmax(80px,1fr)";

function RosterHeader({
  bulkSelecting,
  visibleHeaderCheckboxState,
  onToggleSelectAll,
}: {
  bulkSelecting: boolean;
  visibleHeaderCheckboxState: boolean | "indeterminate";
  onToggleSelectAll: () => void;
}) {
  return (
    <div
      className="grid items-center gap-3 px-3 border-b border-border"
      style={{
        gridTemplateColumns: GRID_TEMPLATE,
        height: 24,
        fontFamily: "var(--font-mono)",
        fontSize: 10,
        textTransform: "uppercase",
        letterSpacing: "0.12em",
        color: "var(--text-tertiary)",
      }}
    >
      <span>
        {bulkSelecting ? (
          <input
            type="checkbox"
            checked={visibleHeaderCheckboxState === true}
            ref={(el) => {
              if (el) el.indeterminate = visibleHeaderCheckboxState === "indeterminate";
            }}
            onChange={onToggleSelectAll}
            style={{ width: 12, height: 12, accentColor: "var(--verdict-attested)" }}
          />
        ) : null}
      </span>
      <span aria-hidden />
      <span>name</span>
      <span>role</span>
      <span>adapter</span>
      <span>status</span>
      <span>last run</span>
      <span>pulse</span>
      <span>budget</span>
      <span className="text-right pr-2">actions</span>
    </div>
  );
}

function RosterRow({
  agent,
  recentRuns,
  liveCount,
  selected,
  bulkSelecting,
  isCursor,
  onToggleSelected,
  onNavigate,
  rowRef,
}: {
  agent: Agent;
  recentRuns: HeartbeatRun[];
  liveCount: number;
  selected: boolean;
  bulkSelecting: boolean;
  isCursor: boolean;
  onToggleSelected: () => void;
  onNavigate: (href: string) => void;
  rowRef?: (el: HTMLDivElement | null) => void;
}) {
  const verdict = statusVerdict(agent.status);
  const verdictAttr =
    verdict === "allow"
      ? "allow"
      : verdict === "block"
        ? "block"
        : verdict === "pending"
          ? "pending"
          : verdict === "attested"
            ? "allow"
            : undefined;
  const statusLabel = normalizeStatusLabel(agent.status);
  const adapter = ADAPTER_LABELS[agent.adapterType] ?? agent.adapterType;
  const role = ROLE_LABELS[agent.role] ?? agent.role;
  const href = agentUrl(agent);
  const ref = agentRouteRef(agent);
  const lastRun = agent.lastHeartbeatAt ? relativeTime(agent.lastHeartbeatAt) : "-";

  const handleRowClick = (e: React.MouseEvent) => {
    if (bulkSelecting) {
      e.preventDefault();
      onToggleSelected();
      return;
    }
    onNavigate(href);
  };

  return (
    <div
      ref={rowRef}
      role="row"
      tabIndex={-1}
      onClick={handleRowClick}
      className="group grid items-center gap-3 px-3 border-b border-border cursor-pointer"
      style={{
        gridTemplateColumns: GRID_TEMPLATE,
        height: 28,
        fontFamily: "var(--font-mono)",
        fontSize: 12,
        lineHeight: "20px",
        background: isCursor ? "var(--surface-2)" : "transparent",
        outline: isCursor ? "1px solid var(--border-strong)" : "none",
        outlineOffset: "-1px",
      }}
      onMouseEnter={(e) => {
        if (!isCursor) e.currentTarget.style.background = "var(--surface-2)";
      }}
      onMouseLeave={(e) => {
        if (!isCursor) e.currentTarget.style.background = "transparent";
      }}
    >
      {/* checkbox */}
      <span onClick={(e) => e.stopPropagation()}>
        {bulkSelecting && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelected}
            style={{ width: 12, height: 12, accentColor: "var(--verdict-attested)" }}
          />
        )}
      </span>

      {/* glyph */}
      <span className="flex items-center justify-center">
        <span
          className="mesh-node"
          {...(verdictAttr ? { "data-verdict": verdictAttr } : {})}
          {...(agent.status === "running" || agent.status === "active"
            ? { "data-running": "true" }
            : {})}
          style={{ width: 8, height: 8, borderWidth: 1 }}
          aria-label={statusLabel}
        />
      </span>

      {/* name */}
      <span
        className="truncate"
        style={{ color: "var(--foreground)" }}
        title={agent.name}
      >
        {agent.name}
        {liveCount > 0 && (
          <span
            className="ml-1.5 tabular-nums"
            style={{ color: "var(--verdict-attested)", fontSize: 10 }}
            title={`${liveCount} live run${liveCount > 1 ? "s" : ""}`}
          >
            ·live{liveCount > 1 ? `(${liveCount})` : ""}
          </span>
        )}
      </span>

      {/* role */}
      <span
        className="truncate lowercase"
        style={{ color: "var(--text-secondary)" }}
        title={role}
      >
        {role.toLowerCase()}
      </span>

      {/* adapter */}
      <span
        className="truncate lowercase"
        style={{ color: "var(--text-secondary)" }}
      >
        {adapter}
      </span>

      {/* status */}
      <span className="lowercase" style={{ color: verdictVar(verdict) }}>
        {statusLabel}
      </span>

      {/* last run */}
      <span
        className="tabular-nums truncate"
        style={{ color: "var(--text-tertiary)", fontSize: 11 }}
      >
        {lastRun}
      </span>

      {/* pulse */}
      <span className="flex items-center">
        <PulseStrip runs={recentRuns} />
      </span>

      {/* budget */}
      <span className="flex items-center tabular-nums">
        <BudgetBar
          spentCents={agent.spentMonthlyCents ?? 0}
          capCents={agent.budgetMonthlyCents ?? 0}
        />
      </span>

      {/* actions (hover-reveal) */}
      <span
        className="opacity-0 group-hover:opacity-100 transition-opacity flex justify-end gap-2 pr-1"
        style={{ color: "var(--text-tertiary)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <a
          href={`${href}?action=run`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(`${href}?action=run`);
          }}
          className="hover:text-[var(--foreground)]"
        >
          [run]
        </a>
        <a
          href={`${href}?action=pause`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(`${href}?action=pause`);
          }}
          className="hover:text-[var(--foreground)]"
        >
          [pause]
        </a>
        <a
          href={href}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(href);
          }}
          className="hover:text-[var(--foreground)]"
          data-agent-ref={ref}
        >
          [open]
        </a>
      </span>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────

export function Agents() {
  const { selectedProjectId } = useProject();
  const { openNewAgent } = useDialog();
  const { setBreadcrumbs } = useBreadcrumbs();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  // Derive route segment + status param.
  const pathSegment = (location.pathname.split("/").pop() ?? "all") as RoutePathSegment;
  const validSegments: RoutePathSegment[] = ["all", "active", "paused", "error"];
  const currentSegment: RoutePathSegment = validSegments.includes(pathSegment)
    ? pathSegment
    : "all";

  const statusParam = useMemo(() => {
    const sp = new URLSearchParams(location.search);
    return sp.get("status");
  }, [location.search]);

  const currentPill: PillKey = pillFromUrl(currentSegment, statusParam);

  const [filterText, setFilterText] = useState("");
  const [bulkSelecting, setBulkSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [cursorIndex, setCursorIndex] = useState(0);

  const filterInputRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // ── Queries (preserved) ────────────────────────────────────────────
  const { data: agents, isLoading, error } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: runs } = useQuery({
    queryKey: queryKeys.heartbeats(selectedProjectId!),
    queryFn: () => heartbeatsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
    refetchInterval: 15_000,
  });

  // ── Derived ────────────────────────────────────────────────────────
  const liveRuns = useLiveRuns(runs);
  const recentByAgent = useRecentRunsByAgent(runs);

  // Counts per pill (computed from full agent list, ignoring text filter).
  const pillCounts = useMemo(() => {
    const counts: Record<PillKey, number> = {
      all: 0,
      running: 0,
      idle: 0,
      paused: 0,
      error: 0,
    };
    for (const a of agents ?? []) {
      if (a.status === "terminated") continue;
      counts.all += 1;
      for (const p of PILL_ORDER) {
        if (p === "all") continue;
        if (statusMatchesPill(a.status, p)) counts[p] += 1;
      }
    }
    return counts;
  }, [agents]);

  // Visible roster.
  const visibleAgents = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    return (agents ?? []).filter((a) => {
      if (a.status === "terminated") return false;
      if (!statusMatchesPill(a.status, currentPill)) return false;
      if (!q) return true;
      const role = (ROLE_LABELS[a.role] ?? a.role).toLowerCase();
      const adapter = (ADAPTER_LABELS[a.adapterType] ?? a.adapterType).toLowerCase();
      return (
        a.name.toLowerCase().includes(q) ||
        role.includes(q) ||
        adapter.includes(q)
      );
    });
  }, [agents, currentPill, filterText]);

  // ── Mutations (preserved) ──────────────────────────────────────────
  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => agentsApi.bulkDelete(selectedProjectId!, ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list(selectedProjectId!) });
      queryClient.invalidateQueries({ queryKey: queryKeys.org(selectedProjectId!) });
      queryClient.invalidateQueries({ queryKey: queryKeys.heartbeats(selectedProjectId!) });
      setBulkSelecting(false);
      setSelectedIds(new Set());
    },
  });

  // ── Effects ────────────────────────────────────────────────────────
  useEffect(() => {
    setBreadcrumbs([{ label: "Workers" }]);
  }, [setBreadcrumbs]);

  useEffect(() => {
    if (!bulkSelecting) setSelectedIds(new Set());
  }, [bulkSelecting]);

  // Keep cursor in range.
  useEffect(() => {
    if (cursorIndex >= visibleAgents.length) {
      setCursorIndex(Math.max(0, visibleAgents.length - 1));
    }
  }, [visibleAgents.length, cursorIndex]);

  // j/k/↵// keybindings
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      const isFormField =
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        (target && target.isContentEditable);

      if (e.key === "/") {
        if (isFormField) return;
        e.preventDefault();
        filterInputRef.current?.focus();
        filterInputRef.current?.select();
        return;
      }

      if (isFormField) return;

      if (e.key === "j") {
        e.preventDefault();
        setCursorIndex((i) => Math.min(visibleAgents.length - 1, i + 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setCursorIndex((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        const a = visibleAgents[cursorIndex];
        if (a) {
          e.preventDefault();
          navigate(agentUrl(a));
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visibleAgents, cursorIndex, navigate]);

  // Scroll cursor row into view.
  useEffect(() => {
    const a = visibleAgents[cursorIndex];
    if (!a) return;
    const el = rowRefs.current.get(a.id);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursorIndex, visibleAgents]);

  // ── Selection helpers ──────────────────────────────────────────────
  const toggleAgentSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectedOnVisible = useMemo(
    () => visibleAgents.filter((a) => selectedIds.has(a.id)).length,
    [visibleAgents, selectedIds],
  );
  const visibleHeaderCheckboxState: boolean | "indeterminate" =
    visibleAgents.length > 0 && selectedOnVisible === visibleAgents.length
      ? true
      : selectedOnVisible > 0
        ? "indeterminate"
        : false;

  function toggleSelectAllVisible() {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const curAll =
        visibleAgents.length > 0 && visibleAgents.every((a) => next.has(a.id));
      if (curAll) {
        visibleAgents.forEach((a) => next.delete(a.id));
      } else {
        visibleAgents.forEach((a) => next.add(a.id));
      }
      return next;
    });
  }

  function confirmBulkDelete() {
    const n = selectedIds.size;
    if (n === 0) return;
    if (!window.confirm(`terminate ${n} worker(s)? this cannot be undone.`)) return;
    bulkDeleteMutation.mutate([...selectedIds]);
  }

  // ── Pill click → URL nav ───────────────────────────────────────────
  function handleSelectPill(pill: PillKey) {
    const { segment, status } = pillToRoute(pill);
    const qs = status ? `?status=${status}` : "";
    navigate(`/agents/${segment}${qs}`);
  }

  // ── Early returns ──────────────────────────────────────────────────
  if (!selectedProjectId) {
    return <EmptyState icon={Bot} message="Select a project to view workers." />;
  }
  if (isLoading) {
    return <PageSkeleton variant="list" />;
  }

  const totalNonTerminated = (agents ?? []).filter((a) => a.status !== "terminated").length;
  const isCompletelyEmpty = (agents?.length ?? 0) === 0;

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <div
      className="flex flex-col h-[calc(100vh-4rem)] w-full"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {/* Header strip */}
      <div
        className="flex items-center gap-4 px-4 py-2 border-b border-border"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <span
          className="lowercase"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            color: "var(--foreground)",
          }}
        >
          workers
          <span className="ml-1.5 tabular-nums" style={{ color: "var(--text-tertiary)" }}>
            · {totalNonTerminated}
          </span>
        </span>

        <span style={{ color: "var(--text-tertiary)" }}>│</span>

        {/* free-text filter */}
        <label
          className="flex items-center gap-2 text-[11px]"
          style={{ color: "var(--text-tertiary)" }}
        >
          <span aria-hidden>{">"}</span>
          <input
            ref={filterInputRef}
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="filter ... (press /)"
            className="px-2 py-0.5 bg-transparent border border-border focus:outline-none focus:border-[var(--foreground)]"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              minWidth: 220,
              color: "var(--foreground)",
            }}
          />
        </label>

        <span className="flex-1" />

        {/* Pill bar */}
        <PillBar active={currentPill} onSelect={handleSelectPill} counts={pillCounts} />

        <span style={{ color: "var(--text-tertiary)" }}>│</span>

        {/* Onboard one */}
        <button
          type="button"
          onClick={openNewAgent}
          className="px-2 py-0.5 border border-border hover:bg-[var(--surface-2)] transition-colors"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--foreground)",
            textTransform: "lowercase",
          }}
        >
          + onboard
        </button>

        <button
          type="button"
          onClick={() => setBulkSelecting((v) => !v)}
          disabled={isCompletelyEmpty || bulkDeleteMutation.isPending}
          className="px-2 py-0.5 border border-border hover:bg-[var(--surface-2)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: bulkSelecting ? "var(--foreground)" : "var(--text-secondary)",
            textTransform: "lowercase",
            outline: bulkSelecting ? "1px solid var(--verdict-attested)" : "none",
            outlineOffset: "-1px",
          }}
        >
          select
        </button>
      </div>

      {/* Bulk action bar */}
      {bulkSelecting && (
        <div
          className="flex items-center gap-3 px-4 py-1 border-b border-border"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-secondary)",
            background: "var(--surface-1)",
          }}
        >
          <span className="tabular-nums" style={{ color: "var(--foreground)" }}>
            {selectedIds.size}
          </span>
          <span style={{ color: "var(--text-tertiary)" }}>selected</span>
          <span style={{ color: "var(--text-tertiary)" }}>·</span>
          <button
            type="button"
            disabled={selectedIds.size === 0 || bulkDeleteMutation.isPending}
            onClick={confirmBulkDelete}
            className="hover:text-[var(--foreground)] disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ color: "var(--verdict-block)" }}
          >
            {bulkDeleteMutation.isPending ? "terminating..." : "terminate"}
          </button>
          <span style={{ color: "var(--text-tertiary)" }}>·</span>
          <button
            type="button"
            onClick={() => {
              setBulkSelecting(false);
              setSelectedIds(new Set());
            }}
            className="hover:text-[var(--foreground)]"
          >
            cancel
          </button>
          {bulkDeleteMutation.isError && (
            <span className="ml-2" style={{ color: "var(--verdict-block)" }}>
              {bulkDeleteMutation.error instanceof Error
                ? bulkDeleteMutation.error.message
                : "bulk terminate failed"}
            </span>
          )}
        </div>
      )}

      {/* Error surface */}
      {error && (
        <div
          className="px-4 py-1 border-b border-border"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--verdict-block)",
          }}
        >
          {error.message}
        </div>
      )}

      {/* Roster */}
      <div className="flex-1 overflow-auto">
        {isCompletelyEmpty ? (
          <div
            className="px-4 py-8 text-center"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              color: "var(--text-tertiary)",
            }}
          >
            no workers - onboard one to get started
          </div>
        ) : (
          <>
            <RosterHeader
              bulkSelecting={bulkSelecting}
              visibleHeaderCheckboxState={visibleHeaderCheckboxState}
              onToggleSelectAll={toggleSelectAllVisible}
            />
            {visibleAgents.length === 0 ? (
              <div
                className="px-4 py-8 text-center"
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: "var(--text-tertiary)",
                }}
              >
                no workers in this slice - try the all filter or onboard one
              </div>
            ) : (
              visibleAgents.map((agent, idx) => (
                <RosterRow
                  key={agent.id}
                  agent={agent}
                  recentRuns={recentByAgent.get(agent.id) ?? []}
                  liveCount={liveRuns.get(agent.id)?.liveCount ?? 0}
                  selected={selectedIds.has(agent.id)}
                  bulkSelecting={bulkSelecting}
                  isCursor={idx === cursorIndex}
                  onToggleSelected={() => toggleAgentSelection(agent.id)}
                  onNavigate={(href) => navigate(href)}
                  rowRef={(el) => {
                    if (el) rowRefs.current.set(agent.id, el);
                    else rowRefs.current.delete(agent.id);
                  }}
                />
              ))
            )}
          </>
        )}
      </div>

      {/* Footer hint */}
      <div
        className="flex items-center justify-end px-4 py-1 border-t border-border"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          color: "var(--text-tertiary)",
        }}
      >
        j/k navigate · ↵ open · / filter
      </div>
    </div>
  );
}

export default Agents;
