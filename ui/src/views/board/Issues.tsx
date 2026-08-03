import { useEffect, useMemo, useCallback, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "@/lib/router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Issue, Subproject } from "@gitmesh/core";
import { issuesApi } from "../../api/issues";
import { agentsApi } from "../../api/agents";
import { heartbeatsApi } from "../../api/heartbeats";
import { subprojectsApi } from "../../api/subprojects";
import { useProject } from "../../context/ProjectContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { EmptyState } from "../../components/EmptyState";
import { StatusIcon } from "../../components/StatusIcon";
import { PriorityIcon } from "../../components/PriorityIcon";
import { IssuesList } from "../../features/IssuesList";
import { CircleDot } from "lucide-react";

// ── Types & helpers ─────────────────────────────────────────────────────

type AgentLite = { id: string; name: string; icon?: string | null };

type PillKey =
  | "is:open"
  | "is:blocked"
  | "is:in_review"
  | "is:done"
  | "agent:@me"
  | "priority:critical+high";

type GroupKey = "none" | "status" | "assignee" | "subproject";

type Verdict = "block" | "pending" | "attested" | "none";

const PILLS: PillKey[] = [
  "is:open",
  "is:blocked",
  "is:in_review",
  "is:done",
  "agent:@me",
  "priority:critical+high",
];

function fmtRelative(d: Date | string | null | undefined): string {
  if (!d) return "-";
  const t = typeof d === "string" ? new Date(d).getTime() : d.getTime();
  const diff = Date.now() - t;
  if (Number.isNaN(diff)) return "-";
  const s = Math.max(0, Math.floor(diff / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days}d`;
  const mo = Math.floor(days / 30);
  if (mo < 12) return `${mo}mo`;
  return `${Math.floor(mo / 12)}y`;
}

function statusVerdict(status: string): Verdict {
  if (status === "blocked") return "block";
  if (status === "in_review") return "pending";
  return "none";
}

// ── Component ───────────────────────────────────────────────────────────

export function Issues() {
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  // Filter / search URL state
  const initialSearch = searchParams.get("q") ?? "";
  const [filterText, setFilterText] = useState<string>(initialSearch);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const writeSearchParam = useCallback((search: string) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const trimmedSearch = search.trim();
      const currentSearch = new URLSearchParams(window.location.search).get("q") ?? "";
      if (currentSearch === trimmedSearch) return;
      const url = new URL(window.location.href);
      if (trimmedSearch) url.searchParams.set("q", trimmedSearch);
      else url.searchParams.delete("q");
      const nextUrl = `${url.pathname}${url.search}${url.hash}`;
      window.history.replaceState(window.history.state, "", nextUrl);
    }, 300);
  }, []);

  useEffect(() => {
    writeSearchParam(filterText);
  }, [filterText, writeSearchParam]);

  useEffect(() => {
    return () => clearTimeout(debounceRef.current);
  }, []);

  // ── Data ──────────────────────────────────────────────────────────────

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: subprojects } = useQuery<Subproject[]>({
    queryKey: queryKeys.subprojects.list(selectedProjectId!),
    queryFn: () => subprojectsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: liveRuns } = useQuery({
    queryKey: queryKeys.liveRuns(selectedProjectId!),
    queryFn: () => heartbeatsApi.liveRunsForProject(selectedProjectId!),
    enabled: !!selectedProjectId,
    refetchInterval: 5000,
  });

  const liveIssueIds = useMemo(() => {
    const ids = new Set<string>();
    for (const run of liveRuns ?? []) {
      if (run.issueId) ids.add(run.issueId);
    }
    return ids;
  }, [liveRuns]);

  useEffect(() => {
    setBreadcrumbs([{ label: "Issues" }]);
  }, [setBreadcrumbs]);

  const { data: issues, isLoading, error } = useQuery({
    queryKey: queryKeys.issues.list(selectedProjectId!),
    queryFn: () => issuesApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const updateIssue = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      issuesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.list(selectedProjectId!) });
    },
  });

  const handleUpdate = useCallback(
    (id: string, data: Record<string, unknown>) => updateIssue.mutate({ id, data }),
    [updateIssue],
  );

  // ── View toggles ──────────────────────────────────────────────────────

  const [view, setView] = useState<"table" | "board">("table");
  const [pills, setPills] = useState<Set<PillKey>>(() => {
    const s = new Set<PillKey>();
    if (searchParams.get("assignee")) s.add("agent:@me");
    return s;
  });
  const [groupBy, setGroupBy] = useState<GroupKey>("none");
  const [focusedIdx, setFocusedIdx] = useState(0);

  const initialAssigneeFromUrl = searchParams.get("assignee") ?? null;

  // Subproject lookup
  const subprojectName = useCallback(
    (id: string | null): string => {
      if (!id) return "-";
      const sp = subprojects?.find((s) => s.id === id);
      return sp?.name ?? id.slice(0, 6);
    },
    [subprojects],
  );

  // Agent lookup
  const agentLookup = useMemo(() => {
    const m = new Map<string, AgentLite>();
    for (const a of agents ?? []) m.set(a.id, a);
    return m;
  }, [agents]);

  // ── Filter pipeline ───────────────────────────────────────────────────

  const allIssues = issues ?? [];

  const filtered = useMemo(() => {
    let r = allIssues.slice();

    // Pill filters
    if (pills.has("is:open")) {
      r = r.filter((i) => i.status !== "done" && i.status !== "cancelled");
    }
    if (pills.has("is:blocked")) {
      r = r.filter((i) => i.status === "blocked");
    }
    if (pills.has("is:in_review")) {
      r = r.filter((i) => i.status === "in_review");
    }
    if (pills.has("is:done")) {
      r = r.filter((i) => i.status === "done");
    }
    if (pills.has("priority:critical+high")) {
      r = r.filter((i) => i.priority === "critical" || i.priority === "high");
    }
    if (pills.has("agent:@me") && initialAssigneeFromUrl) {
      r = r.filter((i) => i.assigneeAgentId === initialAssigneeFromUrl);
    }

    // Free-text filter (mono input)
    const q = filterText.trim().toLowerCase();
    if (q) {
      r = r.filter((i) => {
        const blob = [
          i.title,
          i.identifier ?? "",
          i.status,
          i.priority,
          subprojectName(i.subprojectId),
          i.assigneeAgentId ? agentLookup.get(i.assigneeAgentId)?.name ?? "" : "",
        ]
          .join(" ")
          .toLowerCase();
        return blob.includes(q);
      });
    }

    // Sort updated desc by default
    r.sort((a, b) => {
      const ta = new Date(a.updatedAt).getTime();
      const tb = new Date(b.updatedAt).getTime();
      return tb - ta;
    });

    return r;
  }, [allIssues, pills, filterText, initialAssigneeFromUrl, subprojectName, agentLookup]);

  // ── Grouping ──────────────────────────────────────────────────────────

  const groups = useMemo(() => {
    if (groupBy === "none") {
      return [{ key: "", label: "", rows: filtered }];
    }
    const map = new Map<string, Issue[]>();
    for (const issue of filtered) {
      let k: string;
      if (groupBy === "status") k = issue.status;
      else if (groupBy === "assignee") {
        k = issue.assigneeAgentId
          ? agentLookup.get(issue.assigneeAgentId)?.name ?? issue.assigneeAgentId
          : "unassigned";
      } else {
        k = subprojectName(issue.subprojectId);
      }
      const arr = map.get(k);
      if (arr) arr.push(issue);
      else map.set(k, [issue]);
    }
    return Array.from(map.entries()).map(([key, rows]) => ({
      key,
      label: key.toUpperCase().replace(/_/g, " "),
      rows,
    }));
  }, [filtered, groupBy, agentLookup, subprojectName]);

  // Flat list for keyboard nav
  const flatIssues = useMemo(() => groups.flatMap((g) => g.rows), [groups]);

  // ── Keyboard ──────────────────────────────────────────────────────────

  const filterInputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      const isTyping =
        tag === "input" || tag === "textarea" || (e.target as HTMLElement | null)?.isContentEditable;

      if (e.key === "/" && !isTyping) {
        e.preventDefault();
        filterInputRef.current?.focus();
        return;
      }
      if (e.key === "Escape" && document.activeElement === filterInputRef.current) {
        filterInputRef.current?.blur();
        return;
      }
      if (isTyping) return;
      if (view !== "table") return;
      if (flatIssues.length === 0) return;

      if (e.key === "j") {
        e.preventDefault();
        setFocusedIdx((i) => Math.min(flatIssues.length - 1, i + 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setFocusedIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const issue = flatIssues[focusedIdx];
        if (issue) navigate(`/issues/${issue.identifier ?? issue.id}`);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [flatIssues, focusedIdx, navigate, view]);

  useEffect(() => {
    if (focusedIdx >= flatIssues.length) {
      setFocusedIdx(Math.max(0, flatIssues.length - 1));
    }
  }, [flatIssues.length, focusedIdx]);

  useEffect(() => {
    rowRefs.current[focusedIdx]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusedIdx]);

  // ── Toggle helpers ────────────────────────────────────────────────────

  const togglePill = (k: PillKey) => {
    setPills((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

  const cycleGroup = () => {
    setGroupBy((g) =>
      g === "none" ? "status" : g === "status" ? "assignee" : g === "assignee" ? "subproject" : "none",
    );
  };

  // ── Empty / loading guards ────────────────────────────────────────────

  if (!selectedProjectId) {
    return <EmptyState icon={CircleDot} message="Select a project to view issues." />;
  }

  // ── Render ────────────────────────────────────────────────────────────

  // Board view falls back to original feature component (kept behind toggle)
  if (view === "board") {
    return (
      <div
        className="flex flex-col gap-3 pb-12"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <HeaderStrip
          count={filtered.length}
          total={allIssues.length}
          view={view}
          onView={setView}
        />
        <IssuesList
          issues={issues ?? []}
          isLoading={isLoading}
          error={error as Error | null}
          agents={agents}
          liveIssueIds={liveIssueIds}
          viewStateKey="gitmesh-agents:issues-view"
          initialAssignees={initialAssigneeFromUrl ? [initialAssigneeFromUrl] : undefined}
          initialSearch={initialSearch}
          onSearchChange={(s) => setFilterText(s)}
          onUpdateIssue={handleUpdate}
        />
      </div>
    );
  }

  let runningIdx = -1;

  return (
    <div
      className="flex flex-col gap-3 pb-12"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {/* Header strip */}
      <HeaderStrip
        count={filtered.length}
        total={allIssues.length}
        view={view}
        onView={setView}
      />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        {PILLS.map((k) => {
          const active = pills.has(k);
          const disabled = k === "agent:@me" && !initialAssigneeFromUrl;
          return (
            <button
              key={k}
              type="button"
              onClick={() => !disabled && togglePill(k)}
              disabled={disabled}
              className="rounded-sm px-2 py-0.5 text-[11px] tracking-tight transition-colors disabled:opacity-40"
              style={{
                border: active ? "1px solid var(--verdict-attested)" : "1px solid transparent",
                color: active ? "var(--verdict-attested)" : "var(--text-tertiary)",
                background: "transparent",
              }}
            >
              {k}
            </button>
          );
        })}

        <button
          type="button"
          onClick={cycleGroup}
          className="rounded-sm px-2 py-0.5 text-[11px] tracking-tight transition-colors"
          style={{
            border:
              groupBy !== "none"
                ? "1px solid var(--verdict-attested)"
                : "1px solid transparent",
            color: groupBy !== "none" ? "var(--verdict-attested)" : "var(--text-tertiary)",
            background: "transparent",
          }}
          title="cycle grouping"
        >
          group:{groupBy}
        </button>

        <div className="ml-auto flex min-w-[220px] flex-1 items-center gap-1.5 border-b border-border px-1 py-0.5 sm:max-w-sm sm:flex-none">
          <span className="text-text-tertiary">{">"}</span>
          <input
            ref={filterInputRef}
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="filter ..."
            className="w-full bg-transparent text-[12px] outline-none placeholder:text-text-tertiary"
            style={{ fontFamily: "var(--font-mono)" }}
          />
          {filterText && (
            <button
              type="button"
              onClick={() => setFilterText("")}
              className="text-[10px] text-text-tertiary hover:text-foreground"
              aria-label="clear filter"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Errors */}
      {error && (
        <div className="text-xs" style={{ color: "var(--verdict-block)" }}>
          {(error as Error).message}
        </div>
      )}

      {/* Body */}
      {isLoading ? (
        <div
          className="py-12 text-center text-xs text-text-tertiary"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          loading issues …
        </div>
      ) : flatIssues.length === 0 ? (
        <div
          className="py-12 text-center text-xs text-text-tertiary"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          no issues match - try a different filter
        </div>
      ) : (
        <div className="flex flex-col">
          {/* Column header row */}
          <div
            className="grid h-6 items-center gap-2 border-b border-border pl-0 pr-2 text-[10px] uppercase tracking-[0.18em] text-text-tertiary"
            style={{
              gridTemplateColumns:
                "2px 16px 96px 16px minmax(0, 1fr) 140px 100px 56px 60px",
            }}
          >
            <span />
            <span />
            <span>id</span>
            <span />
            <span>title</span>
            <span>assignee</span>
            <span>subproject</span>
            <span className="text-right">upd</span>
            <span className="text-right">act</span>
          </div>

          {groups.map((g, gi) => (
            <div key={`g-${gi}-${g.key}`} className="flex flex-col">
              {groupBy !== "none" && (
                <div
                  className="flex h-5 items-center gap-2 border-b border-border pl-2 text-[10px] tracking-[0.18em] text-text-tertiary"
                  style={{ textTransform: "uppercase" }}
                >
                  <span>{g.label || "-"}</span>
                  <span>·</span>
                  <span className="tabular-nums">{g.rows.length}</span>
                </div>
              )}
              {g.rows.map((issue) => {
                runningIdx += 1;
                const idx = runningIdx;
                const isFocused = idx === focusedIdx;
                const isLive = liveIssueIds.has(issue.id);
                const verdict: Verdict = isLive
                  ? "attested"
                  : statusVerdict(issue.status);
                const railColor =
                  verdict === "block"
                    ? "var(--verdict-block)"
                    : verdict === "pending"
                      ? "var(--verdict-pending)"
                      : verdict === "attested"
                        ? "var(--verdict-attested)"
                        : "transparent";
                const assignee = issue.assigneeAgentId
                  ? agentLookup.get(issue.assigneeAgentId)
                  : null;
                return (
                  <div
                    key={issue.id}
                    ref={(el) => {
                      rowRefs.current[idx] = el;
                    }}
                    onClick={() => {
                      setFocusedIdx(idx);
                      navigate(`/issues/${issue.identifier ?? issue.id}`);
                    }}
                    onMouseEnter={() => setFocusedIdx(idx)}
                    className="group grid h-6 cursor-pointer items-center gap-2 border-b border-border pr-2 text-[12px] transition-colors"
                    style={{
                      gridTemplateColumns:
                        "2px 16px 96px 16px minmax(0, 1fr) 140px 100px 56px 60px",
                      background: isFocused ? "var(--surface-2)" : "transparent",
                    }}
                  >
                    {/* Verdict rail */}
                    <span
                      aria-hidden
                      className="block h-full"
                      style={{ background: railColor }}
                    />
                    {/* Priority glyph */}
                    <span className="flex h-full items-center justify-center">
                      <PriorityIcon priority={issue.priority} />
                    </span>
                    {/* ID */}
                    <span className="truncate text-[11px] tabular-nums text-text-tertiary">
                      {issue.identifier ?? issue.id.slice(0, 8)}
                    </span>
                    {/* Status glyph */}
                    <span
                      className="inline-flex h-full items-center justify-center text-text-tertiary"
                      title={issue.status}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <StatusIcon
                        status={issue.status}
                        onChange={(s) => handleUpdate(issue.id, { status: s })}
                      />
                    </span>
                    {/* Title */}
                    <span className="min-w-0 truncate text-foreground">
                      {issue.title}
                      {issue.labels && issue.labels.length > 0 && (
                        <span className="ml-2 text-[10px] text-text-tertiary">
                          {issue.labels
                            .slice(0, 2)
                            .map((l) => `#${l.name}`)
                            .join(" ")}
                          {issue.labels.length > 2 ? ` +${issue.labels.length - 2}` : ""}
                        </span>
                      )}
                    </span>
                    {/* Assignee */}
                    <span className="truncate text-[11px] text-text-tertiary">
                      {assignee ? `@${assignee.name}` : "-"}
                    </span>
                    {/* Subproject */}
                    <span className="truncate text-[11px] text-text-tertiary">
                      {subprojectName(issue.subprojectId)}
                    </span>
                    {/* Updated */}
                    <span className="text-right text-[11px] tabular-nums text-text-tertiary">
                      {fmtRelative(issue.updatedAt)}
                    </span>
                    {/* Inline actions */}
                    <span
                      className="flex items-center justify-end gap-1 text-[10px] text-text-tertiary opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {isLive && (
                        <span
                          className="verdict-chip"
                          data-verdict="attested"
                          title="live run"
                        >
                          live
                        </span>
                      )}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}

      {/* Footer hint */}
      <div
        className="mt-2 flex items-center gap-3 border-t border-border pt-2 text-[10px] tracking-[0.18em] text-text-tertiary"
        style={{ textTransform: "uppercase" }}
      >
        <span>j/k</span>
        <span>·</span>
        <span>↵ open</span>
        <span>·</span>
        <span>/ filter</span>
        <span className="ml-auto tabular-nums">
          {flatIssues.length}/{allIssues.length}
        </span>
      </div>
    </div>
  );
}

// ── Header strip ────────────────────────────────────────────────────────

function HeaderStrip({
  count,
  total,
  view,
  onView,
}: {
  count: number;
  total: number;
  view: "table" | "board";
  onView: (v: "table" | "board") => void;
}) {
  return (
    <div className="flex h-8 items-center justify-between border-b border-border">
      <span className="text-sm tracking-tight text-foreground">
        issues
        <span className="ml-2 tabular-nums text-text-tertiary">· {total}</span>
        {count !== total && (
          <span className="ml-1 tabular-nums text-text-tertiary">({count} shown)</span>
        )}
      </span>
      <div className="flex items-center gap-1 text-[11px] tracking-tight">
        <button
          type="button"
          onClick={() => onView("table")}
          className="rounded-sm px-1.5 py-0.5 transition-colors"
          style={{
            color: view === "table" ? "var(--verdict-attested)" : "var(--text-tertiary)",
            border:
              view === "table" ? "1px solid var(--verdict-attested)" : "1px solid transparent",
          }}
        >
          table
        </button>
        <span className="text-text-tertiary">·</span>
        <button
          type="button"
          onClick={() => onView("board")}
          className="rounded-sm px-1.5 py-0.5 transition-colors"
          style={{
            color: view === "board" ? "var(--verdict-attested)" : "var(--text-tertiary)",
            border:
              view === "board" ? "1px solid var(--verdict-attested)" : "1px solid transparent",
          }}
        >
          board
        </button>
      </div>
    </div>
  );
}

