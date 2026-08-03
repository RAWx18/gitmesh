import { useMemo, useState, useCallback } from "react";
import { Link } from "@/lib/router";
import type { Issue } from "@gitmesh/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentsApi } from "../api/agents";
import { authApi } from "../api/auth";
import { issuesApi } from "../api/issues";
import { subprojectsApi } from "../api/subprojects";
import { useProject } from "../context/ProjectContext";
import { queryKeys } from "../lib/queryKeys";
import { useSubprojectOrder } from "../hooks/useSubprojectOrder";
import { getRecentAssigneeIds, sortAgentsByRecency, trackRecentAssignee } from "../lib/recent-assignees";
import { StatusIcon } from "../components/StatusIcon";
import { PriorityIcon } from "../components/PriorityIcon";
import { Identity } from "../components/Identity";
import { formatDate, cn, subprojectUrl } from "../lib/utils";
import { timeAgo } from "../lib/timeAgo";
import { Separator } from "@/components/ui/separator";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { User, Hexagon, ArrowUpRight, Tag, Plus, Trash2 } from "lucide-react";
import { AgentIcon } from "./AgentIconPicker";

// ── Props ─────────────────────────────────────────────────────────────────

interface Props {
  issue: Issue;
  onUpdate: (data: Record<string, unknown>) => void;
  inline?: boolean;
}

// ── Property row ─────────────────────────────────────────────────────────

function PropertyRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="text-xs text-muted-foreground shrink-0 w-20">{label}</span>
      <div className="flex items-center gap-1.5 min-w-0 flex-1">{children}</div>
    </div>
  );
}

// ── Search input ─────────────────────────────────────────────────────────

function SearchInput({
  value,
  onChange,
  placeholder,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  autoFocus?: boolean;
}) {
  return (
    <input
      className="w-full px-2 py-1.5 text-xs bg-transparent outline-none border-b border-border mb-1 placeholder:text-muted-foreground/50"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoFocus={autoFocus}
    />
  );
}

// ── Color swatch ─────────────────────────────────────────────────────────

function ColorSwatch({ color, size = "sm" }: { color: string; size?: "sm" | "xs" }) {
  const dim = size === "sm" ? "h-3 w-3" : "h-2.5 w-2.5";
  return <span className={`shrink-0 ${dim} rounded-sm`} style={{ backgroundColor: color }} />;
}

// ── Scrollable list ───────────────────────────────────────────────────────

function ScrollArea({ children, maxHeight = "max-h-48" }: { children: React.ReactNode; maxHeight?: string }) {
  return <div className={`overflow-y-auto overscroll-contain ${maxHeight}`}>{children}</div>;
}

// ── Label chip ──────────────────────────────────────────────────────────

function LabelChip({
  label,
  onRemove,
  removable,
}: {
  label: { id: string; name: string; color: string };
  onRemove?: () => void;
  removable?: boolean;
}) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium border"
      style={{ borderColor: label.color, backgroundColor: `${label.color}22`, color: label.color }}
    >
      {label.name}
      {removable && onRemove && (
        <button
          type="button"
          className="ml-0.5 hover:opacity-70"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
        >
          ×
        </button>
      )}
    </span>
  );
}

// ── Label picker ─────────────────────────────────────────────────────────

function buildLabelPicker({
  labels,
  selected,
  inline,
  onToggle,
  onCreate,
  onDelete,
}: {
  labels: { id: string; name: string; color: string }[];
  selected: string[];
  inline?: boolean;
  onToggle: (id: string) => void;
  onCreate: (name: string, color: string) => void;
  onDelete: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("#6366f1");

  const filtered = useMemo(
    () => labels.filter((l) => !search.trim() || l.name.toLowerCase().includes(search.toLowerCase())),
    [labels, search],
  );

  const trigger = selected.length > 0 ? (
    <div className="flex items-center gap-1 flex-wrap">
      {labels.filter((l) => selected.includes(l.id)).slice(0, 3).map((l) => (
        <LabelChip key={l.id} label={l} />
      ))}
      {selected.length > 3 && <span className="text-xs text-muted-foreground">+{selected.length - 3}</span>}
    </div>
  ) : (
    <>
      <Tag className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-sm text-muted-foreground">No labels</span>
    </>
  );

  const content = (
    <>
      <SearchInput value={search} onChange={setSearch} placeholder="Search labels..." autoFocus={!inline} />
      <ScrollArea>
        {filtered.map((label) => (
          <div key={label.id} className="flex items-center gap-1">
            <button
              className={cn(
                "flex items-center gap-2 flex-1 px-2 py-1.5 text-xs rounded hover:bg-accent/50 text-left",
                selected.includes(label.id) && "bg-accent",
              )}
              onClick={() => onToggle(label.id)}
            >
              <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: label.color }} />
              <span className="truncate">{label.name}</span>
            </button>
            <button
              type="button"
              className="p-1 text-muted-foreground hover:text-destructive rounded"
              onClick={() => onDelete(label.id)}
              title={`Delete ${label.name}`}
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
      </ScrollArea>
      <div className="mt-2 border-t border-border pt-2 space-y-1">
        <div className="flex items-center gap-1">
          <input
            className="h-7 w-7 p-0 rounded bg-transparent"
            type="color"
            value={newColor}
            onChange={(e) => setNewColor(e.target.value)}
          />
          <input
            className="flex-1 px-2 py-1.5 text-xs bg-transparent outline-none rounded placeholder:text-muted-foreground/50"
            placeholder="New label"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
        </div>
        <button
          className="flex items-center justify-center gap-1.5 w-full px-2 py-1.5 text-xs rounded border border-border hover:bg-accent/50 disabled:opacity-50"
          disabled={!newName.trim()}
          onClick={() => { onCreate(newName.trim(), newColor); setNewName(""); }}
        >
          <Plus className="h-3 w-3" />
          Create label
        </button>
      </div>
    </>
  );

  return { trigger, content };
}

// ── Assignee picker ───────────────────────────────────────────────────────

function buildAssigneePicker({
  agents,
  assigneeAgentId,
  assigneeUserId,
  createdByUserId,
  currentUserId,
  inline,
  onUpdate,
}: {
  agents: { id: string; name: string; status: string; icon?: string | null }[];
  assigneeAgentId: string | null;
  assigneeUserId: string | null;
  createdByUserId?: string | null;
  currentUserId?: string;
  inline?: boolean;
  onUpdate: (data: { assigneeAgentId: string | null; assigneeUserId: string | null }) => void;
}) {
  const [search, setSearch] = useState("");
  const recentIds = useMemo(() => getRecentAssigneeIds(), []);
  const sorted = useMemo(
    () => sortAgentsByRecency(agents.filter((a) => a.status !== "terminated"), recentIds),
    [agents, recentIds],
  );
  const filtered = useMemo(
    () => sorted.filter((a) => !search.trim() || a.name.toLowerCase().includes(search.toLowerCase())),
    [sorted, search],
  );

  const userLabel = (userId: string | null | undefined) => {
    if (!userId) return null;
    if (userId === "local-board") return "Maintainer";
    if (currentUserId && userId === currentUserId) return "Me";
    return userId.slice(0, 5);
  };

  const assignee = assigneeAgentId ? agents.find((a) => a.id === assigneeAgentId) : null;
  const trigger = assignee ? (
    <Identity name={assignee.name} size="sm" />
  ) : assigneeUserId ? (
    <>
      <User className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-sm">{userLabel(assigneeUserId)}</span>
    </>
  ) : (
    <>
      <User className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-sm text-muted-foreground">Unassigned</span>
    </>
  );

  const content = (
    <>
      <SearchInput value={search} onChange={setSearch} placeholder="Search assignees..." autoFocus={!inline} />
      <ScrollArea>
        <button
          className={cn(
            "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50",
            !assigneeAgentId && !assigneeUserId && "bg-accent",
          )}
          onClick={() => onUpdate({ assigneeAgentId: null, assigneeUserId: null })}
        >
          No assignee
        </button>
        {createdByUserId && (
          <button
            className={cn(
              "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50",
              assigneeUserId === createdByUserId && "bg-accent",
            )}
            onClick={() => onUpdate({ assigneeAgentId: null, assigneeUserId: createdByUserId })}
          >
            <User className="h-3 w-3 shrink-0 text-muted-foreground" />
            {userLabel(createdByUserId) ? `Assign to ${userLabel(createdByUserId) === "Me" ? "me" : userLabel(createdByUserId)}` : "Assign to requester"}
          </button>
        )}
        {filtered.map((a) => (
          <button
            key={a.id}
            className={cn(
              "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50",
              a.id === assigneeAgentId && "bg-accent",
            )}
            onClick={() => { trackRecentAssignee(a.id); onUpdate({ assigneeAgentId: a.id, assigneeUserId: null }); }}
          >
            <AgentIcon icon={a.icon} className="shrink-0 h-3 w-3 text-muted-foreground" />
            {a.name}
          </button>
        ))}
      </ScrollArea>
    </>
  );

  return { trigger, content };
}

// ── Project picker ───────────────────────────────────────────────────────

function buildProjectPicker({
  projects,
  selectedId,
  inline,
  onUpdate,
}: {
  projects: { id: string; name: string; color: string | null }[];
  selectedId: string | null;
  inline?: boolean;
  onUpdate: (projectId: string | null) => void;
}) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(
    () => projects.filter((p) => !search.trim() || p.name.toLowerCase().includes(search.toLowerCase())),
    [projects, search],
  );

  const selected = projects.find((p) => p.id === selectedId);
  const trigger = selectedId && selected ? (
    <>
      <ColorSwatch color={selected.color ?? "#6366f1"} />
      <span className="text-sm truncate">{selected.name}</span>
    </>
  ) : (
    <>
      <Hexagon className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-sm text-muted-foreground">No project</span>
    </>
  );

  const content = (
    <>
      <SearchInput value={search} onChange={setSearch} placeholder="Search projects..." autoFocus={!inline} />
      <ScrollArea>
        <button
          className={cn(
            "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50 whitespace-nowrap",
            !selectedId && "bg-accent",
          )}
          onClick={() => onUpdate(null)}
        >
          No project
        </button>
        {filtered.map((p) => (
          <button
            key={p.id}
            className={cn(
              "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50 whitespace-nowrap",
              p.id === selectedId && "bg-accent",
            )}
            onClick={() => onUpdate(p.id)}
          >
            <ColorSwatch color={p.color ?? "#6366f1"} />
            {p.name}
          </button>
        ))}
      </ScrollArea>
    </>
  );

  return { trigger, content };
}

// ── Property picker (inline/popover wrapper) ────────────────────────────

function PropertyPicker({
  inline,
  label,
  open,
  onOpenChange,
  triggerContent,
  triggerClassName,
  popoverClassName,
  extra,
  children,
}: {
  inline?: boolean;
  label: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  triggerContent: React.ReactNode;
  triggerClassName?: string;
  popoverClassName?: string;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  const btnClass = cn(
    "inline-flex items-center gap-1.5 cursor-pointer hover:bg-accent/50 rounded px-1 -mx-1 py-0.5 transition-colors",
    triggerClassName,
  );

  if (inline) {
    return (
      <div>
        <PropertyRow label={label}>
          <button className={btnClass} onClick={() => onOpenChange(!open)}>
            {triggerContent}
          </button>
          {extra}
        </PropertyRow>
        {open && (
          <div className={cn("rounded-md border border-border bg-popover p-1 mb-2", popoverClassName)}>
            {children}
          </div>
        )}
      </div>
    );
  }

  return (
    <PropertyRow label={label}>
      <Popover open={open} onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>
          <button className={btnClass}>{triggerContent}</button>
        </PopoverTrigger>
        <PopoverContent className={cn("p-1", popoverClassName)} align="end" collisionPadding={16}>
          {children}
        </PopoverContent>
      </Popover>
      {extra}
    </PropertyRow>
  );
}

// ── Main component ────────────────────────────────────────────────────────

export function IssueProperties({ issue, onUpdate, inline }: Props) {
  const { selectedProjectId } = useProject();
  const queryClient = useQueryClient();
  const projectId = issue.projectId ?? selectedProjectId;

  // Picker open/close state - keyed by picker name
  const [pickerState, setPickerState] = useState({
    labels: false,
    assignee: false,
    project: false,
  });

  const openPicker = useCallback((name: "labels" | "assignee" | "project") => {
    setPickerState((s) => ({ ...s, [name]: true }));
  }, []);

  const closePicker = useCallback((name: "labels" | "assignee" | "project") => {
    setPickerState((s) => ({ ...s, [name]: false }));
  }, []);

  // Session (for current user)
  const { data: session } = useQuery({
    queryKey: queryKeys.auth.session,
    queryFn: () => authApi.getSession(),
  });
  const currentUserId = session?.user?.id ?? session?.session?.userId;

  // Agents list
  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(projectId!),
    queryFn: () => agentsApi.list(projectId!),
    enabled: !!projectId,
  });

  // Projects (subprojects)
  const { data: projects } = useQuery({
    queryKey: queryKeys.subprojects.list(projectId!),
    queryFn: () => subprojectsApi.list(projectId!),
    enabled: !!projectId,
  });
  const { orderedProjects } = useSubprojectOrder({
    projects: projects ?? [],
    projectId,
    userId: currentUserId,
  });

  // Labels
  const { data: labels } = useQuery({
    queryKey: queryKeys.issues.labels(projectId!),
    queryFn: () => issuesApi.listLabels(projectId!),
    enabled: !!projectId,
  });

  // Label mutations
  const createLabel = useMutation({
    mutationFn: (data: { name: string; color: string }) => issuesApi.createLabel(projectId!, data),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.issues.labels(projectId!) });
      onUpdate({ labelIds: [...(issue.labelIds ?? []), created.id] });
    },
  });

  const deleteLabel = useMutation({
    mutationFn: (labelId: string) => issuesApi.deleteLabel(labelId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.labels(projectId!) });
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.list(projectId!) });
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.detail(issue.id) });
    },
  });

  // Label toggle
  const handleLabelToggle = useCallback((labelId: string) => {
    const ids = issue.labelIds ?? [];
    const next = ids.includes(labelId) ? ids.filter((id) => id !== labelId) : [...ids, labelId];
    onUpdate({ labelIds: next });
  }, [issue.labelIds, onUpdate]);

  // Build picker data
  const labelPicker = buildLabelPicker({
    labels: labels ?? [],
    selected: issue.labelIds ?? [],
    inline,
    onToggle: handleLabelToggle,
    onCreate: (name, color) => createLabel.mutate({ name, color }),
    onDelete: (id) => {
      deleteLabel.mutate(id);
      onUpdate({ labelIds: (issue.labelIds ?? []).filter((lid) => lid !== id) });
    },
  });

  const assigneePicker = buildAssigneePicker({
    agents: agents ?? [],
    assigneeAgentId: issue.assigneeAgentId ?? null,
    assigneeUserId: issue.assigneeUserId ?? null,
    createdByUserId: issue.createdByUserId,
    currentUserId,
    inline,
    onUpdate: (data) => { onUpdate(data); closePicker("assignee"); },
  });

  const projectPicker = buildProjectPicker({
    projects: orderedProjects,
    selectedId: issue.projectId ?? null,
    inline,
    onUpdate: (id) => { onUpdate({ projectId: id }); closePicker("project"); },
  });

  // Project URL helper
  const projectLink = (id: string | null) => {
    if (!id) return null;
    const project = projects?.find((p) => p.id === id) ?? null;
    return project ? subprojectUrl(project) : `/projects/${id}`;
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <PropertyRow label="Status">
          <StatusIcon status={issue.status} onChange={(status) => onUpdate({ status })} showLabel />
        </PropertyRow>

        <PropertyRow label="Priority">
          <PriorityIcon priority={issue.priority} onChange={(priority) => onUpdate({ priority })} showLabel />
        </PropertyRow>

        <PropertyPicker
          inline={inline}
          label="Labels"
          open={pickerState.labels}
          onOpenChange={(open) => (open ? openPicker("labels") : closePicker("labels"))}
          triggerContent={labelPicker.trigger}
          triggerClassName="min-w-0 max-w-full"
          popoverClassName="w-64"
        >
          {labelPicker.content}
        </PropertyPicker>

        <PropertyPicker
          inline={inline}
          label="Assignee"
          open={pickerState.assignee}
          onOpenChange={(open) => (open ? openPicker("assignee") : closePicker("assignee"))}
          triggerContent={assigneePicker.trigger}
          popoverClassName="w-52"
          extra={issue.assigneeAgentId ? (
            <Link
              to={`/agents/${issue.assigneeAgentId}`}
              className="inline-flex items-center justify-center h-5 w-5 rounded hover:bg-accent/50 transition-colors text-muted-foreground hover:text-foreground"
              onClick={(e) => e.stopPropagation()}
            >
              <ArrowUpRight className="h-3 w-3" />
            </Link>
          ) : undefined}
        >
          {assigneePicker.content}
        </PropertyPicker>

        <PropertyPicker
          inline={inline}
          label="Project"
          open={pickerState.project}
          onOpenChange={(open) => (open ? openPicker("project") : closePicker("project"))}
          triggerContent={projectPicker.trigger}
          triggerClassName="min-w-0 max-w-full"
          popoverClassName="w-fit min-w-[11rem]"
          extra={issue.projectId ? (
            <Link
              to={projectLink(issue.projectId)!}
              className="inline-flex items-center justify-center h-5 w-5 rounded hover:bg-accent/50 transition-colors text-muted-foreground hover:text-foreground"
              onClick={(e) => e.stopPropagation()}
            >
              <ArrowUpRight className="h-3 w-3" />
            </Link>
          ) : undefined}
        >
          {projectPicker.content}
        </PropertyPicker>

        {issue.parentId && (
          <PropertyRow label="Parent">
            <Link
              to={`/issues/${issue.ancestors?.[0]?.identifier ?? issue.parentId}`}
              className="text-sm hover:underline"
            >
              {issue.ancestors?.[0]?.title ?? issue.parentId.slice(0, 8)}
            </Link>
          </PropertyRow>
        )}

        {issue.requestDepth > 0 && (
          <PropertyRow label="Depth">
            <span className="text-sm font-mono">{issue.requestDepth}</span>
          </PropertyRow>
        )}
      </div>

      <Separator />

      <div className="space-y-1">
        {issue.startedAt && (
          <PropertyRow label="Started">
            <span className="text-sm">{formatDate(issue.startedAt)}</span>
          </PropertyRow>
        )}
        {issue.completedAt && (
          <PropertyRow label="Completed">
            <span className="text-sm">{formatDate(issue.completedAt)}</span>
          </PropertyRow>
        )}
        <PropertyRow label="Created">
          <span className="text-sm">{formatDate(issue.createdAt)}</span>
        </PropertyRow>
        <PropertyRow label="Updated">
          <span className="text-sm">{timeAgo(issue.updatedAt)}</span>
        </PropertyRow>
      </div>
    </div>
  );
}
