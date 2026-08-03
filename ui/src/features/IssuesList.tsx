import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { Link } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import { useDialog } from "../context/DialogContext";
import { useProject } from "../context/ProjectContext";
import { issuesApi } from "../api/issues";
import { queryKeys } from "../lib/queryKeys";
import { groupBy } from "../lib/groupBy";
import { formatDate, cn } from "../lib/utils";
import { StatusIcon } from "../components/StatusIcon";
import { PriorityIcon } from "../components/PriorityIcon";
import { EmptyState } from "../components/EmptyState";
import { Identity } from "../components/Identity";
import { PageSkeleton } from "../components/PageSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { CircleDot, Plus, Filter, ArrowUpDown, Layers, Check, X, ChevronRight, List, Columns3, User, Search, ArrowDown } from "lucide-react";
import { KanbanBoard } from "./KanbanBoard";
import type { Issue } from "@gitmesh/core";

// ── Constants ─────────────────────────────────────────────────────────────

const STATUS_SEQ = ["in_progress", "todo", "backlog", "in_review", "blocked", "done", "cancelled"];
const PRIORITY_SEQ = ["critical", "high", "medium", "low"];

const QUICK_PRESETS = [
  { label: "All", statuses: [] as string[] },
  { label: "Active", statuses: ["todo", "in_progress", "in_review", "blocked"] },
  { label: "Backlog", statuses: ["backlog"] },
  { label: "Done", statuses: ["done", "cancelled"] },
] as const;

// ── Helpers ───────────────────────────────────────────────────────────────

function labelize(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function toggle(arr: string[], val: string): string[] {
  return arr.includes(val) ? arr.filter((v) => v !== val) : [...arr, val];
}

function sameArray(a: string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  return [...a].sort().every((v, i) => v === [...b].sort()[i]);
}

// ── Types ─────────────────────────────────────────────────────────────────

export type SortField = "status" | "priority" | "title" | "created" | "updated";
export type GroupField = "status" | "priority" | "assignee" | "none";
export type ViewMode = "list" | "board";

export interface ViewState {
  statuses: string[];
  priorities: string[];
  assignees: string[];
  labels: string[];
  sortField: SortField;
  sortDir: "asc" | "desc";
  groupBy: GroupField;
  viewMode: ViewMode;
  collapsedGroups: string[];
}

const DEFAULT: ViewState = {
  statuses: [],
  priorities: [],
  assignees: [],
  labels: [],
  sortField: "updated",
  sortDir: "desc",
  groupBy: "none",
  viewMode: "list",
  collapsedGroups: [],
};

function loadState(key: string): ViewState {
  try {
    const raw = localStorage.getItem(key);
    if (raw) return { ...DEFAULT, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return { ...DEFAULT };
}

function saveState(key: string, state: ViewState) {
  localStorage.setItem(key, JSON.stringify(state));
}

// ── Filter/sort ────────────────────────────────────────────────────────────

function filterIssues(issues: Issue[], s: ViewState): Issue[] {
  let r = issues;
  if (s.statuses.length > 0) r = r.filter((i) => s.statuses.includes(i.status));
  if (s.priorities.length > 0) r = r.filter((i) => s.priorities.includes(i.priority));
  if (s.assignees.length > 0) r = r.filter((i) => i.assigneeAgentId != null && s.assignees.includes(i.assigneeAgentId));
  if (s.labels.length > 0) r = r.filter((i) => (i.labelIds ?? []).some((id) => s.labels.includes(id)));
  return r;
}

function sortIssues(issues: Issue[], s: ViewState): Issue[] {
  const dir = s.sortDir === "asc" ? 1 : -1;
  return [...issues].sort((a, b) => {
    switch (s.sortField) {
      case "status": return dir * (STATUS_SEQ.indexOf(a.status) - STATUS_SEQ.indexOf(b.status));
      case "priority": return dir * (PRIORITY_SEQ.indexOf(a.priority) - PRIORITY_SEQ.indexOf(b.priority));
      case "title": return dir * a.title.localeCompare(b.title);
      case "created": return dir * (new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
      case "updated": return dir * (new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime());
      default: return 0;
    }
  });
}

function activeFilterCount(s: ViewState): number {
  return [s.statuses.length > 0, s.priorities.length > 0, s.assignees.length > 0, s.labels.length > 0].filter(Boolean).length;
}

// ── Sub-components ─────────────────────────────────────────────────────────

function ViewModeToggle({ viewMode, onChange }: { viewMode: ViewMode; onChange: (v: ViewMode) => void }) {
  return (
    <div className="flex items-center border border-border rounded-md overflow-hidden mr-1">
      <button
        className={cn("p-1.5 transition-colors", viewMode === "list" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}
        onClick={() => onChange("list")}
        title="List view"
      >
        <List className="h-3.5 w-3.5" />
      </button>
      <button
        className={cn("p-1.5 transition-colors", viewMode === "board" ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground")}
        onClick={() => onChange("board")}
        title="Board view"
      >
        <Columns3 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function QuickFilters({ statuses, onToggle }: { statuses: string[]; onToggle: (s: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {QUICK_PRESETS.map((p) => {
        const active = sameArray(statuses, p.statuses);
        return (
          <button
            key={p.label}
            className={cn(
              "px-2.5 py-1 text-xs rounded-full border transition-colors",
              active ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground hover:border-foreground/30",
            )}
            onClick={() => onToggle(active ? [] : [...p.statuses])}
          >
            {p.label}
          </button>
        );
      })}
    </div>
  );
}

function StatusFilters({ selected, onToggle }: { selected: string[]; onToggle: (s: string) => void }) {
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">Status</span>
      <div className="space-y-0.5">
        {STATUS_SEQ.map((s) => (
          <label key={s} className="flex items-center gap-2 px-2 py-1 rounded-sm hover:bg-accent/50 cursor-pointer">
            <Checkbox checked={selected.includes(s)} onCheckedChange={() => onToggle(s)} />
            <StatusIcon status={s} />
            <span className="text-sm">{labelize(s)}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function PriorityFilters({ selected, onToggle }: { selected: string[]; onToggle: (p: string) => void }) {
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">Priority</span>
      <div className="space-y-0.5">
        {PRIORITY_SEQ.map((p) => (
          <label key={p} className="flex items-center gap-2 px-2 py-1 rounded-sm hover:bg-accent/50 cursor-pointer">
            <Checkbox checked={selected.includes(p)} onCheckedChange={() => onToggle(p)} />
            <PriorityIcon priority={p} />
            <span className="text-sm">{labelize(p)}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function AssigneeFilters({ agents }: { agents?: { id: string; name: string }[] }) {
  if (!agents?.length) return null;
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">Assignee</span>
      <div className="space-y-0.5 max-h-32 overflow-y-auto">
        {agents.map((a) => (
          <label key={a.id} className="flex items-center gap-2 px-2 py-1 rounded-sm hover:bg-accent/50 cursor-pointer">
            <Checkbox />
            <Identity name={a.name} size="xs" />
            <span className="text-sm truncate">{a.name}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function LabelFilters({ labels }: { labels?: { id: string; name: string; color: string }[] }) {
  if (!labels?.length) return null;
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">Labels</span>
      <div className="space-y-0.5 max-h-32 overflow-y-auto">
        {labels.map((l) => (
          <label key={l.id} className="flex items-center gap-2 px-2 py-1 rounded-sm hover:bg-accent/50 cursor-pointer">
            <Checkbox />
            <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: l.color }} />
            <span className="text-sm truncate">{l.name}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function FilterPanel({
  viewState,
  agents,
  labels,
  onUpdate,
  onClear,
}: {
  viewState: ViewState;
  agents?: { id: string; name: string }[];
  labels?: { id: string; name: string; color: string }[];
  onUpdate: (patch: Partial<ViewState>) => void;
  onClear: () => void;
}) {
  const count = activeFilterCount(viewState);
  return (
    <div className="p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Filters</span>
        {count > 0 && <button className="text-xs text-muted-foreground hover:text-foreground" onClick={onClear}>Clear</button>}
      </div>
      <div className="space-y-1.5">
        <span className="text-xs text-muted-foreground">Quick filters</span>
        <QuickFilters statuses={viewState.statuses} onToggle={(statuses) => onUpdate({ statuses })} />
      </div>
      <div className="border-t border-border" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
        <StatusFilters selected={viewState.statuses} onToggle={(s) => onUpdate({ statuses: toggle(viewState.statuses, s) })} />
        <div className="space-y-3">
          <PriorityFilters selected={viewState.priorities} onToggle={(p) => onUpdate({ priorities: toggle(viewState.priorities, p) })} />
          <AssigneeFilters agents={agents} />
          <LabelFilters labels={labels} />
        </div>
      </div>
    </div>
  );
}

function FilterPopover({
  viewState,
  agents,
  labels,
  onUpdate,
  children,
}: {
  viewState: ViewState;
  agents?: { id: string; name: string }[];
  labels?: { id: string; name: string; color: string }[];
  onUpdate: (patch: Partial<ViewState>) => void;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent align="end" className="w-[min(480px,calc(100vw-2rem))] p-0">
        <FilterPanel
          viewState={viewState}
          agents={agents}
          labels={labels}
          onUpdate={onUpdate}
          onClear={() => onUpdate({ statuses: [], priorities: [], assignees: [], labels: [] })}
        />
      </PopoverContent>
    </Popover>
  );
}

function SortPopover({ viewState, onUpdate }: { viewState: ViewState; onUpdate: (p: Partial<ViewState>) => void }) {
  const [open, setOpen] = useState(false);
  const fields: [SortField, string][] = [["status", "Status"], ["priority", "Priority"], ["title", "Title"], ["created", "Created"], ["updated", "Updated"]];
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="text-xs">
          <ArrowUpDown className="h-3.5 w-3.5 sm:h-3 sm:w-3 sm:mr-1" />
          <span className="hidden sm:inline">Sort</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-48 p-0">
        <div className="p-2 space-y-0.5">
          {fields.map(([field, label]) => (
            <button
              key={field}
              className={cn(
                "flex items-center justify-between w-full px-2 py-1.5 text-sm rounded-sm",
                viewState.sortField === field ? "bg-accent/50 text-foreground" : "hover:bg-accent/50 text-muted-foreground",
              )}
              onClick={() => {
                if (viewState.sortField === field) {
                  onUpdate({ sortDir: viewState.sortDir === "asc" ? "desc" : "asc" });
                } else {
                  onUpdate({ sortField: field, sortDir: "asc" });
                }
                setOpen(false);
              }}
            >
              <span>{label}</span>
              {viewState.sortField === field && <span className="text-xs text-muted-foreground">{viewState.sortDir === "asc" ? "\u2191" : "\u2193"}</span>}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function GroupPopover({ viewState, onUpdate }: { viewState: ViewState; onUpdate: (p: Partial<ViewState>) => void }) {
  const [open, setOpen] = useState(false);
  const fields: [GroupField, string][] = [["status", "Status"], ["priority", "Priority"], ["assignee", "Assignee"], ["none", "None"]];
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="text-xs">
          <Layers className="h-3.5 w-3.5 sm:h-3 sm:w-3 sm:mr-1" />
          <span className="hidden sm:inline">Group</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-44 p-0">
        <div className="p-2 space-y-0.5">
          {fields.map(([value, label]) => (
            <button
              key={value}
              className={cn(
                "flex items-center justify-between w-full px-2 py-1.5 text-sm rounded-sm",
                viewState.groupBy === value ? "bg-accent/50 text-foreground" : "hover:bg-accent/50 text-muted-foreground",
              )}
              onClick={() => { onUpdate({ groupBy: value }); setOpen(false); }}
            >
              <span>{label}</span>
              {viewState.groupBy === value && <Check className="h-3.5 w-3.5" />}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function AssigneePickerPopover({
  agents,
  assigneeAgentId,
  onAssign,
}: {
  agents?: { id: string; name: string; icon?: string | null }[];
  assigneeAgentId: string | null;
  onAssign: (id: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className="flex w-[180px] shrink-0 items-center rounded-md px-2 py-1 hover:bg-accent/50 transition-colors"
          onClick={(e) => e.preventDefault()}
        >
          {assigneeAgentId && agents?.find((a) => a.id === assigneeAgentId) ? (
            <Identity name={agents.find((a) => a.id === assigneeAgentId)!.name} size="sm" />
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-dashed border-muted-foreground/35 bg-muted/30">
                <User className="h-3 w-3" />
              </span>
              Assignee
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-1" align="end" onClick={(e) => e.stopPropagation()} onPointerDownOutside={() => setSearch("")}>
        <input
          className="w-full px-2 py-1.5 text-xs bg-transparent outline-none border-b border-border mb-1 placeholder:text-muted-foreground/50"
          placeholder="Search agents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
        <div className="max-h-48 overflow-y-auto overscroll-contain">
          <button
            className={cn("flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50", !assigneeAgentId && "bg-accent")}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); onAssign(null); }}
          >
            No assignee
          </button>
          {(agents ?? [])
            .filter((a) => !search.trim() || a.name.toLowerCase().includes(search.toLowerCase()))
            .map((a) => (
              <button
                key={a.id}
                className={cn(
                  "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50 text-left",
                  assigneeAgentId === a.id && "bg-accent",
                )}
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); onAssign(a.id); }}
              >
                <Identity name={a.name} size="sm" className="min-w-0" />
              </button>
            ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function IssueCard({
  issue,
  agents,
  liveIssueIds,
  onUpdate,
}: {
  issue: Issue;
  agents?: { id: string; name: string; icon?: string | null }[];
  liveIssueIds?: Set<string>;
  onUpdate: (id: string, data: Record<string, unknown>) => void;
}) {
  const isLive = liveIssueIds?.has(issue.id);
  return (
    <Link
      to={`/issues/${issue.identifier ?? issue.id}`}
      className="flex items-center gap-2 py-2 pl-2 pr-3 text-sm border-b border-border last:border-b-0 cursor-pointer hover:bg-surface-2/60 transition-colors no-underline text-inherit"
    >
      <div className="w-3.5 shrink-0 hidden sm:block" />
      <div className="shrink-0" onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}>
        <StatusIcon status={issue.status} onChange={(s) => onUpdate(issue.id, { status: s })} />
      </div>
      <span className="font-mono text-[11px] tabular-nums text-text-tertiary shrink-0">{issue.identifier ?? issue.id.slice(0, 8)}</span>
      <span className="truncate flex-1 min-w-0 text-foreground">{issue.title}</span>
      {(issue.labels ?? []).length > 0 && (
        <div className="hidden md:flex items-center gap-1 max-w-[240px] overflow-hidden">
          {(issue.labels ?? []).slice(0, 3).map((label) => (
            <span
              key={label.id}
              className="inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-medium"
              style={{ borderColor: label.color, color: label.color, backgroundColor: `${label.color}1f` }}
            >
              {label.name}
            </span>
          ))}
          {(issue.labels ?? []).length > 3 && <span className="text-[10px] text-muted-foreground">+{(issue.labels ?? []).length - 3}</span>}
        </div>
      )}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0 ml-auto">
        {isLive && (
          <span className="inline-flex items-center gap-1 sm:gap-1.5 px-1.5 sm:px-2 py-0.5 rounded-full bg-blue-500/10">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
            </span>
            <span className="text-[11px] font-medium text-blue-600 dark:text-blue-400 hidden sm:inline">Live</span>
          </span>
        )}
        <div className="hidden sm:block">
          <AssigneePickerPopover
            agents={agents}
            assigneeAgentId={issue.assigneeAgentId ?? null}
            onAssign={(id) => onUpdate(issue.id, { assigneeAgentId: id, assigneeUserId: null })}
          />
        </div>
        <span className="text-xs text-muted-foreground hidden sm:inline">{formatDate(issue.createdAt)}</span>
      </div>
    </Link>
  );
}

function GroupHeading({
  label,
  groupKey,
  isOpen,
  collapsed,
  onToggle,
  onNewIssue,
}: {
  label: string | null;
  groupKey: string;
  isOpen: boolean;
  collapsed: boolean;
  onToggle: () => void;
  onNewIssue: () => void;
}) {
  if (!label) return null;
  return (
    <div className="flex items-center gap-2 border-b border-border bg-surface-2/40 px-2 py-1.5">
      <CollapsibleTrigger className="flex items-center gap-1.5">
        <ChevronRight className="h-3 w-3 shrink-0 text-text-tertiary transition-transform [[data-state=open]>&]:rotate-90" />
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-text-secondary">{label}</span>
      </CollapsibleTrigger>
      <Button variant="ghost" size="icon-xs" className="ml-auto text-text-tertiary hover:text-foreground" onClick={onNewIssue}>
        <Plus className="h-3 w-3" />
      </Button>
    </div>
  );
}

function GroupedList({
  groups,
  agents,
  liveIssueIds,
  viewState,
  onToggleGroup,
  onUpdate,
  onNewIssue,
}: {
  groups: { key: string; label: string | null; items: Issue[] }[];
  agents?: { id: string; name: string; icon?: string | null }[];
  liveIssueIds?: Set<string>;
  viewState: ViewState;
  onToggleGroup: (k: string) => void;
  onUpdate: (id: string, data: Record<string, unknown>) => void;
  onNewIssue: (k?: string) => void;
}) {
  return (
    <>
      {groups.map((g) => (
        <Collapsible
          key={g.key}
          open={!viewState.collapsedGroups.includes(g.key)}
          onOpenChange={() => onToggleGroup(g.key)}
        >
          {g.label && (
            <GroupHeading
              label={g.label}
              groupKey={g.key}
              isOpen={!viewState.collapsedGroups.includes(g.key)}
              collapsed={viewState.collapsedGroups.includes(g.key)}
              onToggle={() => onToggleGroup(g.key)}
              onNewIssue={() => onNewIssue(g.key)}
            />
          )}
          <CollapsibleContent>
            {g.items.map((issue) => (
              <IssueCard key={issue.id} issue={issue} agents={agents} liveIssueIds={liveIssueIds} onUpdate={onUpdate} />
            ))}
          </CollapsibleContent>
        </Collapsible>
      ))}
    </>
  );
}

function FilterBadge({ count }: { count: number }) {
  return (
    <Button variant="ghost" size="sm" className={cn("text-xs", count > 0 ? "text-blue-600 dark:text-blue-400" : "")}>
      <Filter className="h-3.5 w-3.5 sm:h-3 sm:w-3 sm:mr-1" />
      <span className="hidden sm:inline">{count > 0 ? `Filters: ${count}` : "Filter"}</span>
      {count > 0 && <span className="sm:hidden text-[10px] font-medium ml-0.5">{count}</span>}
    </Button>
  );
}

// ── Main component ────────────────────────────────────────────────────────

interface IssuesListProps {
  issues: Issue[];
  isLoading?: boolean;
  error?: Error | null;
  agents?: { id: string; name: string; icon?: string | null }[];
  liveIssueIds?: Set<string>;
  projectId?: string;
  viewStateKey: string;
  initialAssignees?: string[];
  initialSearch?: string;
  onSearchChange?: (s: string) => void;
  onUpdateIssue: (id: string, data: Record<string, unknown>) => void;
}

export function IssuesList({
  issues,
  isLoading,
  error,
  agents,
  liveIssueIds,
  projectId,
  viewStateKey,
  initialAssignees,
  initialSearch,
  onSearchChange,
  onUpdateIssue,
}: IssuesListProps) {
  const { selectedProjectId } = useProject();
  const { openNewIssue } = useDialog();

  /** Prefer explicit page scope subproject/GitMesh project id over context until route sync settles. */
  const effectiveProjectId = projectId ?? selectedProjectId ?? null;

  const scopedKey = effectiveProjectId ? `${viewStateKey}:${effectiveProjectId}` : viewStateKey;

  const [viewState, setViewState] = useState<ViewState>(() => {
    if (initialAssignees) return { ...DEFAULT, assignees: initialAssignees, statuses: [] };
    return loadState(scopedKey);
  });

  const [search, setSearch] = useState(initialSearch ?? "");
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  const prevKey = useRef(scopedKey);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(id);
  }, [search]);

  useEffect(() => { setSearch(initialSearch ?? ""); }, [initialSearch]);

  useEffect(() => {
    if (prevKey.current !== scopedKey) {
      prevKey.current = scopedKey;
      setViewState(
        initialAssignees ? { ...DEFAULT, assignees: initialAssignees, statuses: [] } : loadState(scopedKey),
      );
    }
  }, [scopedKey, initialAssignees]);

  const updateView = useCallback((patch: Partial<ViewState>) => {
    setViewState((prev) => {
      const next = { ...prev, ...patch };
      saveState(scopedKey, next);
      return next;
    });
  }, [scopedKey]);

  // Search query
  const { data: searchedIssues = [] } = useQuery({
    queryKey: queryKeys.issues.search(effectiveProjectId!, debouncedSearch.trim(), projectId),
    queryFn: () => issuesApi.list(effectiveProjectId!, { q: debouncedSearch.trim(), projectId }),
    enabled: !!effectiveProjectId && debouncedSearch.trim().length > 0,
  });

  // Labels
  const { data: labels } = useQuery({
    queryKey: queryKeys.issues.labels(effectiveProjectId!),
    queryFn: () => issuesApi.listLabels(effectiveProjectId!),
    enabled: !!effectiveProjectId,
  });

  // Filter + sort
  const filtered = useMemo(() => {
    const src = debouncedSearch.trim().length > 0 ? searchedIssues : issues;
    return sortIssues(filterIssues(src, viewState), viewState);
  }, [issues, searchedIssues, viewState, debouncedSearch]);

  // Grouped
  const groupedContent = useMemo(() => {
    if (viewState.groupBy === "none") return [{ key: "__all", label: null as string | null, items: filtered }];
    if (viewState.groupBy === "status") {
      const groups = groupBy(filtered, (i) => i.status);
      return STATUS_SEQ.filter((s) => groups[s]?.length).map((s) => ({ key: s, label: labelize(s), items: groups[s]! }));
    }
    if (viewState.groupBy === "priority") {
      const groups = groupBy(filtered, (i) => i.priority);
      return PRIORITY_SEQ.filter((p) => groups[p]?.length).map((p) => ({ key: p, label: labelize(p), items: groups[p]! }));
    }
    const groups = groupBy(filtered, (i) => i.assigneeAgentId ?? "__unassigned");
    return Object.keys(groups).map((k) => ({
      key: k,
      label: k === "__unassigned" ? "Unassigned" : (agents?.find((a) => a.id === k)?.name ?? k.slice(0, 8)),
      items: groups[k]!,
    }));
  }, [filtered, viewState.groupBy, agents]);

  const getDefaults = useCallback((groupKey?: string) => {
    const d: Record<string, string> = {};
    if (projectId) d.projectId = projectId;
    if (groupKey) {
      if (viewState.groupBy === "status") d.status = groupKey;
      else if (viewState.groupBy === "priority") d.priority = groupKey;
      else if (viewState.groupBy === "assignee" && groupKey !== "__unassigned") d.assigneeAgentId = groupKey;
    }
    return d;
  }, [projectId, viewState.groupBy]);

  const [showScrollBottom, setShowScrollBottom] = useState(false);
  useEffect(() => {
    const el = document.getElementById("main-content");
    if (!el) return;
    const check = () => setShowScrollBottom(el.scrollHeight - el.scrollTop - el.clientHeight > 300);
    check();
    el.addEventListener("scroll", check, { passive: true });
    return () => el.removeEventListener("scroll", check);
  }, [filtered.length]);

  const scrollBottom = useCallback(() => {
    const el = document.getElementById("main-content");
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  const toggleGroup = useCallback((k: string) => {
    setViewState((prev) => ({
      ...prev,
      collapsedGroups: prev.collapsedGroups.includes(k) ? prev.collapsedGroups.filter((g) => g !== k) : [...prev.collapsedGroups, k],
    }));
  }, []);

  const filterCount = activeFilterCount(viewState);

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 sm:gap-3">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <Button size="sm" variant="outline" onClick={() => openNewIssue(getDefaults())}>
            <Plus className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">New Issue</span>
          </Button>
          <div className="relative w-48 sm:w-64 md:w-80">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => { setSearch(e.target.value); onSearchChange?.(e.target.value); }}
              placeholder="Search issues..."
              className="pl-7 text-xs sm:text-sm"
              aria-label="Search issues"
            />
          </div>
        </div>
        <div className="flex items-center gap-0.5 sm:gap-1 shrink-0">
          <ViewModeToggle viewMode={viewState.viewMode} onChange={(v) => updateView({ viewMode: v })} />
          <FilterPopover viewState={viewState} agents={agents} labels={labels} onUpdate={updateView}>
            <FilterBadge count={filterCount} />
          </FilterPopover>
          {viewState.viewMode === "list" && (
            <>
              <SortPopover viewState={viewState} onUpdate={updateView} />
              <GroupPopover viewState={viewState} onUpdate={updateView} />
            </>
          )}
        </div>
      </div>

      {isLoading && <PageSkeleton variant="issues-list" />}
      {error && <p className="text-sm text-destructive">{error.message}</p>}

      {!isLoading && filtered.length === 0 && viewState.viewMode === "list" && (
        <EmptyState
          icon={CircleDot}
          message="No issues match the current filters or search."
          action="Create Issue"
          onAction={() => openNewIssue(getDefaults())}
        />
      )}

      {viewState.viewMode === "board" ? (
        <KanbanBoard issues={filtered} agents={agents} liveIssueIds={liveIssueIds} onUpdateIssue={onUpdateIssue} />
      ) : filtered.length > 0 ? (
        <div className="overflow-hidden rounded-md border border-border bg-card">
          <GroupedList
            groups={groupedContent}
            agents={agents}
            liveIssueIds={liveIssueIds}
            viewState={viewState}
            onToggleGroup={toggleGroup}
            onUpdate={onUpdateIssue}
            onNewIssue={getDefaults}
          />
        </div>
      ) : null}

      {showScrollBottom && (
        <button
          onClick={scrollBottom}
          className="fixed bottom-6 right-6 z-40 flex h-9 w-9 items-center justify-center rounded-full border border-border bg-background shadow-md hover:bg-accent transition-colors"
          aria-label="Scroll to bottom"
        >
          <ArrowDown className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
