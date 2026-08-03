import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
  type ChangeEvent,
  type ReactNode,
} from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Link } from "@/lib/router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { issuesApi } from "../../api/issues";
import { auditLogApi, type RunForIssue } from "../../api/audit-log";
import { heartbeatsApi } from "../../api/heartbeats";
import { agentsApi } from "../../api/agents";
import { authApi } from "../../api/auth";
import { subprojectsApi } from "../../api/subprojects";
import { useProject } from "../../context/ProjectContext";
import { usePanel } from "../../context/PanelContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { useSubprojectOrder } from "../../hooks/useSubprojectOrder";
import { relativeTime, cn, formatTokens } from "../../lib/utils";
import { MarkdownBody } from "../../components/MarkdownBody";
import { MarkdownEditor, type MarkdownEditorRef, type MentionOption } from "../../components/MarkdownEditor";
import { LiveRunWidget } from "../../features/LiveRunWidget";
import { Identity } from "../../components/Identity";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ImagePlus, Trash2, EyeOff, ChevronRight } from "lucide-react";
import type { ActivityEvent, Agent, Issue, IssueAttachment, IssueComment, IssueLabel } from "@gitmesh/core";

// ── Types ────────────────────────────────────────────────────────────────

type Verdict = "allow" | "block" | "pending" | "attested";

type StreamItem =
  | { kind: "description"; createdAt: Date | string; key: string }
  | { kind: "comment"; createdAt: Date | string; key: string; comment: IssueComment }
  | { kind: "activity"; createdAt: Date | string; key: string; event: ActivityEvent }
  | { kind: "run"; createdAt: Date | string; key: string; run: RunForIssue }
  | { kind: "attachment"; createdAt: Date | string; key: string; attachment: IssueAttachment };

// ── Constants ────────────────────────────────────────────────────────────

const ACTION_LABELS: Record<string, string> = {
  "issue.created": "created",
  "issue.updated": "updated",
  "issue.checked_out": "checked out",
  "issue.released": "released",
  "issue.comment_added": "commented",
  "issue.attachment_added": "attached",
  "issue.attachment_removed": "removed attachment",
  "issue.deleted": "deleted",
  "agent.created": "created agent",
  "agent.updated": "updated agent",
  "agent.paused": "paused agent",
  "agent.resumed": "resumed agent",
  "agent.terminated": "terminated agent",
  "heartbeat.invoked": "invoked heartbeat",
  "heartbeat.cancelled": "cancelled heartbeat",
  "approval.created": "requested approval",
  "approval.approved": "approved",
  "approval.rejected": "rejected",
};

const STATUS_OPTIONS = ["backlog", "todo", "in_progress", "in_review", "blocked", "done", "cancelled"] as const;
const PRIORITY_OPTIONS = ["urgent", "high", "medium", "low", "none"] as const;

// ── Helpers ──────────────────────────────────────────────────────────────

function statusVerdict(status: string): Verdict {
  switch (status) {
    case "done":
      return "attested";
    case "in_progress":
    case "in_review":
      return "allow";
    case "blocked":
    case "cancelled":
      return "block";
    case "todo":
    case "backlog":
    default:
      return "pending";
  }
}

function runVerdict(status: string): Verdict {
  switch (status) {
    case "succeeded":
      return "allow";
    case "failed":
    case "timed_out":
      return "block";
    case "running":
    case "queued":
    case "cancelled":
    default:
      return "pending";
  }
}

function policyVerdict(outcome: ActivityEvent["policyOutcome"]): Verdict | null {
  if (outcome === "allowed") return "allow";
  if (outcome === "blocked") return "block";
  if (outcome === "require_approval") return "pending";
  return null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function usageNumber(usage: Record<string, unknown> | null, ...keys: string[]) {
  if (!usage) return 0;
  for (const key of keys) {
    const v = usage[key];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return 0;
}

function shortHash(id: string | null | undefined): string {
  if (!id) return "-";
  return id.slice(0, 8);
}

function timeOfDay(date: Date | string): string {
  return new Date(date).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function dayStamp(date: Date | string): string {
  return new Date(date).toLocaleDateString("en-US", {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
  });
}

function humanizeValue(value: unknown): string {
  if (typeof value !== "string") return String(value ?? "none");
  return value.replace(/_/g, " ");
}

function formatAction(action: string, details: Record<string, unknown> | null | undefined): string {
  if (action === "issue.updated" && details) {
    const previous = (details._previous ?? {}) as Record<string, unknown>;
    const parts: string[] = [];
    if (details.status !== undefined) {
      const from = previous.status;
      parts.push(from ? `status ${humanizeValue(from)} → ${humanizeValue(details.status)}` : `status → ${humanizeValue(details.status)}`);
    }
    if (details.priority !== undefined) {
      const from = previous.priority;
      parts.push(from ? `priority ${humanizeValue(from)} → ${humanizeValue(details.priority)}` : `priority → ${humanizeValue(details.priority)}`);
    }
    if (details.assigneeAgentId !== undefined || details.assigneeUserId !== undefined) {
      parts.push(details.assigneeAgentId || details.assigneeUserId ? "assigned" : "unassigned");
    }
    if (details.title !== undefined) parts.push("retitled");
    if (details.description !== undefined) parts.push("edited description");
    if (parts.length > 0) return parts.join(" · ");
  }
  return ACTION_LABELS[action] ?? action.replace(/[._]/g, " ");
}

function actorLabel(evt: ActivityEvent, agentMap: Map<string, Agent>): string {
  if (evt.actorType === "agent") {
    const agent = agentMap.get(evt.actorId);
    return agent ? `@${agent.name}` : `@${shortHash(evt.actorId)}`;
  }
  if (evt.actorType === "system") return "@system";
  if (evt.actorType === "user") return "@maintainer";
  return `@${shortHash(evt.actorId)}`;
}

function commentAuthor(comment: IssueComment, agentMap: Map<string, Agent>): string {
  if (comment.authorAgentId) {
    const agent = agentMap.get(comment.authorAgentId);
    return agent ? `@${agent.name}` : `@${shortHash(comment.authorAgentId)}`;
  }
  if (comment.authorUserId) return "@maintainer";
  return "@unknown";
}

// ── Mono primitives ──────────────────────────────────────────────────────

function MeshDot({ verdict, running }: { verdict?: Verdict; running?: boolean }) {
  return (
    <span
      className="mesh-node"
      data-verdict={verdict ?? "default"}
      data-running={running ? "true" : undefined}
    />
  );
}

function VerdictChip({ verdict, label }: { verdict: Verdict; label: string }) {
  return (
    <span className="verdict-chip" data-verdict={verdict}>
      {label}
    </span>
  );
}

function ActionKey({
  letter,
  label,
  onClick,
  disabled,
  emphasis,
}: {
  letter?: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  emphasis?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "h-7 px-2 inline-flex items-center gap-1.5 border border-border rounded-none font-mono text-[10px] uppercase tracking-[0.10em]",
        "hover:bg-accent/40 disabled:opacity-40 disabled:pointer-events-none",
        emphasis && "border-[var(--verdict-attested)] text-[var(--verdict-attested)]",
      )}
    >
      {letter && (
        <span className="opacity-60">[{letter}]</span>
      )}
      <span>{label}</span>
    </button>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow !text-[10px] !tracking-[0.18em] mb-1">{children}</div>;
}

function EnumPopover({
  triggerLabel,
  options,
  current,
  onSelect,
  triggerData,
  width = "w-44",
}: {
  triggerLabel: ReactNode;
  options: readonly string[];
  current: string;
  onSelect: (v: string) => void;
  triggerData?: string;
  width?: string;
}) {
  const dataAttr = triggerData ? { [`data-${triggerData}`]: "" } : {};
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          {...dataAttr}
          className="w-full flex items-center justify-between hover:text-foreground text-left h-7 px-2 border border-border rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40"
        >
          {triggerLabel}
          <span className="opacity-50">▸</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className={cn("p-1 font-mono text-[11px] rounded-none", width)} align="end">
        {options.map((v) => (
          <button
            key={v}
            className={cn(
              "w-full text-left px-2 py-1.5 hover:bg-accent/40 uppercase tracking-[0.10em]",
              v === current && "bg-accent/60",
            )}
            onClick={() => onSelect(v)}
          >
            {v.replace(/_/g, " ")}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

// ── Right column: inline assign popover ──────────────────────────────────

function InlinePicker({
  value,
  options,
  emptyLabel,
  onChange,
  trigger,
  width = "w-56",
}: {
  value: string | null;
  options: { id: string; label: string }[];
  emptyLabel: string;
  onChange: (id: string | null) => void;
  trigger: ReactNode;
  width?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((o) => o.label.toLowerCase().includes(needle));
  }, [q, options]);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent
        className={cn("p-1 font-mono text-[11px] rounded-none", width)}
        align="start"
      >
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filter…"
          className="w-full px-2 py-1.5 bg-transparent outline-none border-b border-border text-[11px] mb-1"
        />
        <button
          type="button"
          className={cn(
            "w-full text-left px-2 py-1.5 hover:bg-accent/40 uppercase tracking-[0.10em] text-[10px]",
            !value && "text-foreground",
            value && "text-text-tertiary",
          )}
          onClick={() => {
            onChange(null);
            setOpen(false);
            setQ("");
          }}
        >
          {emptyLabel}
        </button>
        <div className="max-h-56 overflow-y-auto gitmesh-scrollbar">
          {filtered.map((opt) => (
            <button
              key={opt.id}
              type="button"
              className={cn(
                "w-full text-left px-2 py-1.5 hover:bg-accent/40",
                opt.id === value && "bg-accent/60 text-foreground",
              )}
              onClick={() => {
                onChange(opt.id);
                setOpen(false);
                setQ("");
              }}
            >
              {opt.label}
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="px-2 py-2 text-text-tertiary text-[10px] uppercase tracking-[0.10em]">no match</div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Component ────────────────────────────────────────────────────────────

export function IssueDetail() {
  const { issueId } = useParams<{ issueId: string }>();
  const { selectedProjectId } = useProject();
  const { closePanel } = usePanel();
  const { setBreadcrumbs } = useBreadcrumbs();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [mobilePropsOpen, setMobilePropsOpen] = useState(false);
  const [composerValue, setComposerValue] = useState("");
  const [composerFocused, setComposerFocused] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const composerRef = useRef<MarkdownEditorRef>(null);
  const lastMarkedReadIssueIdRef = useRef<string | null>(null);
  const composerBandRef = useRef<HTMLDivElement | null>(null);

  // ── Queries ────────────────────────────────────────────────────────────

  const { data: issue, isLoading, error } = useQuery({
    queryKey: queryKeys.issues.detail(issueId!),
    queryFn: () => issuesApi.get(issueId!),
    enabled: !!issueId,
  });

  const { data: comments } = useQuery({
    queryKey: queryKeys.issues.comments(issueId!),
    queryFn: () => issuesApi.listComments(issueId!),
    enabled: !!issueId,
  });

  const { data: activity } = useQuery({
    queryKey: queryKeys.issues.activity(issueId!),
    queryFn: () => auditLogApi.forIssue(issueId!),
    enabled: !!issueId,
  });

  const { data: linkedRuns } = useQuery({
    queryKey: queryKeys.issues.runs(issueId!),
    queryFn: () => auditLogApi.runsForIssue(issueId!),
    enabled: !!issueId,
    refetchInterval: 5000,
  });

  const { data: linkedApprovals } = useQuery({
    queryKey: queryKeys.issues.approvals(issueId!),
    queryFn: () => issuesApi.listApprovals(issueId!),
    enabled: !!issueId,
  });

  const { data: attachments } = useQuery({
    queryKey: queryKeys.issues.attachments(issueId!),
    queryFn: () => issuesApi.listAttachments(issueId!),
    enabled: !!issueId,
  });

  const { data: liveRuns } = useQuery({
    queryKey: queryKeys.issues.liveRuns(issueId!),
    queryFn: () => heartbeatsApi.liveRunsForIssue(issueId!),
    enabled: !!issueId,
    refetchInterval: 3000,
  });

  const { data: activeRun } = useQuery({
    queryKey: queryKeys.issues.activeRun(issueId!),
    queryFn: () => heartbeatsApi.activeRunForIssue(issueId!),
    enabled: !!issueId,
    refetchInterval: 3000,
  });

  const { data: allIssues } = useQuery({
    queryKey: queryKeys.issues.list(selectedProjectId!),
    queryFn: () => issuesApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: session } = useQuery({
    queryKey: queryKeys.auth.session,
    queryFn: () => authApi.getSession(),
  });

  const { data: projects } = useQuery({
    queryKey: queryKeys.subprojects.list(selectedProjectId!),
    queryFn: () => subprojectsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: labelsCatalog } = useQuery({
    queryKey: queryKeys.issues.labels(selectedProjectId!),
    queryFn: () => issuesApi.listLabels(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const currentUserId = session?.user?.id ?? session?.session?.userId ?? null;
  const { orderedProjects } = useSubprojectOrder({
    projects: projects ?? [],
    projectId: selectedProjectId,
    userId: currentUserId,
  });

  // ── Derived state ──────────────────────────────────────────────────────

  const agentMap = useMemo(() => {
    const m = new Map<string, Agent>();
    for (const a of agents ?? []) m.set(a.id, a);
    return m;
  }, [agents]);

  const mentionOptions = useMemo<MentionOption[]>(() => {
    const opts: MentionOption[] = [];
    const active = [...(agents ?? [])]
      .filter((a) => a.status !== "terminated")
      .sort((a, b) => a.name.localeCompare(b.name));
    for (const agent of active) opts.push({ id: `agent:${agent.id}`, name: agent.name, kind: "agent" });
    for (const p of orderedProjects)
      opts.push({
        id: `project:${p.id}`,
        name: p.name,
        kind: "project",
        projectId: p.id,
        projectColor: p.color,
      });
    return opts;
  }, [agents, orderedProjects]);

  const childIssues = useMemo(() => {
    if (!allIssues || !issue) return [];
    return allIssues
      .filter((i) => i.parentId === issue.id)
      .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  }, [allIssues, issue]);

  const hasLiveRuns = (liveRuns ?? []).length > 0 || !!activeRun;

  const timelineRuns = useMemo<RunForIssue[]>(() => {
    const liveIds = new Set<string>();
    for (const r of liveRuns ?? []) liveIds.add(r.id);
    if (activeRun) liveIds.add(activeRun.id);
    if (liveIds.size === 0) return linkedRuns ?? [];
    return (linkedRuns ?? []).filter((r) => !liveIds.has(r.runId));
  }, [linkedRuns, liveRuns, activeRun]);

  const issueCostSummary = useMemo(() => {
    let input = 0;
    let output = 0;
    let cost = 0;
    let hasCost = false;
    let hasTokens = false;
    for (const run of linkedRuns ?? []) {
      const usage = asRecord(run.usageJson);
      const result = asRecord(run.resultJson);
      const ri = usageNumber(usage, "inputTokens", "input_tokens");
      const ro = usageNumber(usage, "outputTokens", "output_tokens");
      const rc =
        usageNumber(usage, "costUsd", "cost_usd", "total_cost_usd") ||
        usageNumber(result, "total_cost_usd", "cost_usd", "costUsd");
      if (rc > 0) hasCost = true;
      if (ri + ro > 0) hasTokens = true;
      input += ri;
      output += ro;
      cost += rc;
    }
    return { input, output, cost, totalTokens: input + output, hasCost, hasTokens };
  }, [linkedRuns]);

  const attestationsCount = useMemo(() => {
    return (activity ?? []).filter((e) => e.policyOutcome === "allowed").length;
  }, [activity]);

  // ── Stream (timeline) ──────────────────────────────────────────────────

  const stream = useMemo<StreamItem[]>(() => {
    if (!issue) return [];
    const items: StreamItem[] = [];
    items.push({ kind: "description", createdAt: issue.createdAt, key: `desc:${issue.id}` });
    for (const c of comments ?? []) {
      items.push({ kind: "comment", createdAt: c.createdAt, key: `comment:${c.id}`, comment: c });
    }
    for (const evt of activity ?? []) {
      // Skip noisy comment_added duplicates already represented by a comment row
      if (evt.action === "issue.comment_added") continue;
      items.push({ kind: "activity", createdAt: evt.createdAt, key: `act:${evt.id}`, event: evt });
    }
    for (const run of timelineRuns) {
      items.push({ kind: "run", createdAt: run.createdAt, key: `run:${run.runId}`, run });
    }
    for (const a of attachments ?? []) {
      items.push({ kind: "attachment", createdAt: a.createdAt, key: `att:${a.id}`, attachment: a });
    }
    items.sort(
      (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    );
    return items;
  }, [issue, comments, activity, timelineRuns, attachments]);

  // ── Mutations ──────────────────────────────────────────────────────────

  const invalidateIssue = useCallback(() => {
    if (!issueId) return;
    queryClient.invalidateQueries({ queryKey: queryKeys.issues.detail(issueId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.issues.activity(issueId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.issues.runs(issueId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.issues.approvals(issueId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.issues.attachments(issueId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.issues.liveRuns(issueId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.issues.activeRun(issueId) });
    if (selectedProjectId) {
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.list(selectedProjectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.listTouchedByMe(selectedProjectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.listUnreadTouchedByMe(selectedProjectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.sidebarBadges(selectedProjectId) });
    }
  }, [issueId, queryClient, selectedProjectId]);

  const markIssueRead = useMutation({
    mutationFn: (id: string) => issuesApi.markRead(id),
    onSuccess: () => {
      if (selectedProjectId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.issues.listTouchedByMe(selectedProjectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.issues.listUnreadTouchedByMe(selectedProjectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.sidebarBadges(selectedProjectId) });
      }
    },
  });

  const updateIssue = useMutation({
    mutationFn: (data: Record<string, unknown>) => issuesApi.update(issueId!, data),
    onSuccess: () => invalidateIssue(),
  });

  const checkoutIssue = useMutation({
    mutationFn: (agentId: string) => issuesApi.checkout(issueId!, agentId),
    onSuccess: () => invalidateIssue(),
  });

  const releaseIssue = useMutation({
    mutationFn: () => issuesApi.release(issueId!),
    onSuccess: () => invalidateIssue(),
  });

  const addComment = useMutation({
    mutationFn: ({ body, reopen }: { body: string; reopen?: boolean }) =>
      issuesApi.addComment(issueId!, body, reopen),
    onSuccess: () => {
      invalidateIssue();
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.comments(issueId!) });
    },
  });

  const uploadAttachment = useMutation({
    mutationFn: async (file: File) => {
      if (!selectedProjectId) throw new Error("No project selected");
      return issuesApi.uploadAttachment(selectedProjectId, issueId!, file);
    },
    onSuccess: () => {
      setAttachmentError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.attachments(issueId!) });
      invalidateIssue();
    },
    onError: (err) => {
      setAttachmentError(err instanceof Error ? err.message : "upload failed");
    },
  });

  const deleteAttachment = useMutation({
    mutationFn: (attachmentId: string) => issuesApi.deleteAttachment(attachmentId),
    onSuccess: () => {
      setAttachmentError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.attachments(issueId!) });
      invalidateIssue();
    },
    onError: (err) => {
      setAttachmentError(err instanceof Error ? err.message : "delete failed");
    },
  });

  // ── Effects ────────────────────────────────────────────────────────────

  useEffect(() => {
    const titleLabel = issue?.title ?? issueId ?? "Issue";
    setBreadcrumbs([
      { label: "Issues", href: "/issues" },
      { label: hasLiveRuns ? `🔵 ${titleLabel}` : titleLabel },
    ]);
  }, [setBreadcrumbs, issue, issueId, hasLiveRuns]);

  // Redirect UUID → identifier
  useEffect(() => {
    if (issue?.identifier && issueId !== issue.identifier) {
      navigate(`/issues/${issue.identifier}`, { replace: true });
    }
  }, [issue, issueId, navigate]);

  useEffect(() => {
    if (!issue?.id) return;
    if (lastMarkedReadIssueIdRef.current === issue.id) return;
    lastMarkedReadIssueIdRef.current = issue.id;
    markIssueRead.mutate(issue.id);
  }, [issue?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // The redesigned page renders its own inline sidekick - close any legacy panel.
  useEffect(() => {
    closePanel();
    return () => closePanel();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Composer actions ───────────────────────────────────────────────────

  const focusComposer = useCallback(() => {
    composerBandRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    composerRef.current?.focus();
  }, []);

  const submitComposer = useCallback(async () => {
    const body = composerValue.trim();
    if (!body) return;
    await addComment.mutateAsync({ body });
    setComposerValue("");
  }, [composerValue, addComment]);

  // ── Keyboard ───────────────────────────────────────────────────────────

  const assignableAgents = useMemo(
    () =>
      [...(agents ?? [])]
        .filter((a) => a.status !== "terminated")
        .sort((a, b) => a.name.localeCompare(b.name)),
    [agents],
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const isTyping =
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.isContentEditable ||
          t.closest("[contenteditable='true']"));
      if (e.key === "Escape") {
        if (composerFocused) (document.activeElement as HTMLElement | null)?.blur();
        return;
      }
      if (isTyping) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (!issue) return;
      switch (e.key) {
        case "/":
          e.preventDefault();
          focusComposer();
          break;
        case "c":
          if (assignableAgents[0]) checkoutIssue.mutate(assignableAgents[0].id);
          break;
        case "r":
          releaseIssue.mutate();
          break;
        case "e":
          setEditingDescription(true);
          break;
        case "a": {
          // Trigger the assignee popover by focusing it (open programmatic via aria? simplest: focus)
          const trigger = document.querySelector<HTMLButtonElement>("[data-issue-assign-trigger]");
          trigger?.click();
          break;
        }
        case "s": {
          const trigger = document.querySelector<HTMLButtonElement>("[data-issue-status-trigger]");
          trigger?.click();
          break;
        }
        case "p": {
          const trigger = document.querySelector<HTMLButtonElement>("[data-issue-priority-trigger]");
          trigger?.click();
          break;
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [issue, composerFocused, focusComposer, assignableAgents, checkoutIssue, releaseIssue]);

  // ── Loading / error ────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <p className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.10em] text-text-tertiary">
        loading dossier…
      </p>
    );
  }
  if (error) {
    return (
      <p className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.10em] text-[var(--verdict-block)]">
        {error.message}
      </p>
    );
  }
  if (!issue) return null;

  const ancestors = issue.ancestors ?? [];
  const verdict = statusVerdict(issue.status);
  const subproject = (projects ?? []).find((p) => p.id === issue.projectId) ?? null;
  const parent = ancestors[0] ?? null;
  const assigneeAgent = issue.assigneeAgentId ? agentMap.get(issue.assigneeAgentId) : null;
  const isCheckedOut = !!issue.checkoutRunId;

  const handleFilePicked = async (evt: ChangeEvent<HTMLInputElement>) => {
    const file = evt.target.files?.[0];
    if (!file) return;
    await uploadAttachment.mutateAsync(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ── Render ─────────────────────────────────────────────────────────────

  const sidekickProps = {
    issue,
    verdict,
    subproject,
    parent,
    assigneeAgent: assigneeAgent ?? null,
    assignableAgents,
    childIssues,
    attachments: attachments ?? [],
    attachmentError,
    attestations: attestationsCount,
    linkedApprovalsCount: linkedApprovals?.length ?? 0,
    costSummary: issueCostSummary,
    labelsCatalog: labelsCatalog ?? [],
    projects: projects ?? [],
    onUpdate: (data: Record<string, unknown>) => updateIssue.mutate(data),
    onPickFile: () => fileInputRef.current?.click(),
    onDeleteAttachment: (id: string) => deleteAttachment.mutate(id),
    uploadDisabled: uploadAttachment.isPending,
    issueId: issueId!,
  };

  return (
    <div className="font-mono">
      {/* ── Top strip ─────────────────────────────────────────────────── */}
      <TopStrip
        issue={issue}
        verdict={verdict}
        ancestors={ancestors}
        subproject={subproject}
        parent={parent}
        attestations={attestationsCount}
        hasLiveRuns={hasLiveRuns}
        onCheckout={(agentId) => checkoutIssue.mutate(agentId)}
        onRelease={() => releaseIssue.mutate()}
        onUpdate={(data) => updateIssue.mutate(data)}
        onHide={() => {
          updateIssue.mutate(
            { hiddenAt: new Date().toISOString() },
            { onSuccess: () => navigate("/issues/all") },
          );
        }}
        onOpenMobileProps={() => setMobilePropsOpen(true)}
        assignableAgents={assignableAgents}
        isCheckedOut={isCheckedOut}
      />

      {/* ── Body: timeline + sidekick ────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-12">
        {/* Left: timeline */}
        <div className="md:col-span-8 border-b md:border-b-0 md:border-r border-border">
          <Timeline
            issue={issue}
            stream={stream}
            agentMap={agentMap}
            editingDescription={editingDescription}
            onStartEditDescription={() => setEditingDescription(true)}
            onCancelEditDescription={() => setEditingDescription(false)}
            onSaveDescription={(description) => {
              updateIssue.mutate({ description });
              setEditingDescription(false);
            }}
            onDeleteAttachment={(id) => deleteAttachment.mutate(id)}
            onUploadImage={async (file) => {
              const att = await uploadAttachment.mutateAsync(file);
              return att.contentPath;
            }}
            mentions={mentionOptions}
            issueId={issueId!}
            issueProjectId={issue.projectId}
          />

          {/* Composer */}
          <div ref={composerBandRef} className="border-t border-border bg-surface-1">
            <div className="px-4 pt-2">
              <Eyebrow>compose · comment</Eyebrow>
            </div>
            <div className="px-4 pb-3">
              <MarkdownEditor
                ref={composerRef}
                value={composerValue}
                onChange={setComposerValue}
                placeholder="reply to issue…"
                bordered={false}
                mentions={mentionOptions}
                imageUploadHandler={async (file) => {
                  const att = await uploadAttachment.mutateAsync(file);
                  return att.contentPath;
                }}
                onSubmit={submitComposer}
                onBlur={() => setComposerFocused(false)}
              />
              <div
                className="mt-2 flex items-center justify-between"
                onFocus={() => setComposerFocused(true)}
              >
                <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary">
                  markdown · @mentions · ⌘↩ post · esc cancel
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setComposerValue("")}
                    disabled={!composerValue.trim()}
                    className="h-7 px-2 inline-flex items-center gap-1 border border-border rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40 disabled:opacity-40"
                  >
                    discard
                  </button>
                  <button
                    type="button"
                    onClick={submitComposer}
                    disabled={!composerValue.trim() || addComment.isPending}
                    className="h-7 px-2 inline-flex items-center gap-1.5 border border-[var(--verdict-attested)] text-[var(--verdict-attested)] rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40 disabled:opacity-40"
                  >
                    <span className="opacity-60">[⌘↩]</span>
                    {addComment.isPending ? "posting…" : "post"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: sidekick */}
        <aside className="md:col-span-4 hidden md:block">
          <Sidekick {...sidekickProps} />
        </aside>
      </div>

      {/* Footer hint */}
      <div className="border-t border-border bg-surface-1 px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary">
        <span className="opacity-60">[c]</span> checkout · <span className="opacity-60">[r]</span> release ·{" "}
        <span className="opacity-60">[a]</span> assign · <span className="opacity-60">[s]</span> status ·{" "}
        <span className="opacity-60">[p]</span> priority · <span className="opacity-60">[e]</span> edit ·{" "}
        <span className="opacity-60">[/]</span> comment · <span className="opacity-60">[⌘↩]</span> post
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="hidden"
        onChange={handleFilePicked}
      />

      {/* Mobile sidekick */}
      <Sheet open={mobilePropsOpen} onOpenChange={setMobilePropsOpen}>
        <SheetContent side="bottom" className="max-h-[85dvh] pb-[env(safe-area-inset-bottom)]">
          <SheetHeader>
            <SheetTitle className="font-mono text-[11px] uppercase tracking-[0.18em] text-text-tertiary">
              dossier · metadata
            </SheetTitle>
          </SheetHeader>
          <ScrollArea className="flex-1 overflow-y-auto">
            <Sidekick {...sidekickProps} />
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </div>
  );
}

// ── Top strip ────────────────────────────────────────────────────────────

function TopStrip({
  issue,
  verdict,
  ancestors,
  subproject,
  parent,
  attestations,
  hasLiveRuns,
  onCheckout,
  onRelease,
  onUpdate,
  onHide,
  onOpenMobileProps,
  assignableAgents,
  isCheckedOut,
}: {
  issue: Issue;
  verdict: Verdict;
  ancestors: Issue["ancestors"];
  subproject: { id: string; name: string } | null;
  parent: { id: string; identifier: string | null; title: string } | null;
  attestations: number;
  hasLiveRuns: boolean;
  onCheckout: (agentId: string) => void;
  onRelease: () => void;
  onUpdate: (data: Record<string, unknown>) => void;
  onHide: () => void;
  onOpenMobileProps: () => void;
  assignableAgents: Agent[];
  isCheckedOut: boolean;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const ident = issue.identifier ?? `GIT-${shortHash(issue.id)}`;
  const created = timeOfDay(issue.createdAt);
  const createdDay = dayStamp(issue.createdAt);

  return (
    <div className="border-b border-border bg-[color-mix(in_oklab,var(--surface-2)_60%,transparent)]">
      {/* Ancestor breadcrumb (if any) */}
      {ancestors && ancestors.length > 0 && (
        <div className="px-4 pt-2 flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary flex-wrap">
          {[...ancestors].reverse().map((a, i) => (
            <span key={a.id} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="h-3 w-3 shrink-0 opacity-50" />}
              <Link
                to={`/issues/${a.identifier ?? a.id}`}
                className="hover:text-foreground transition-colors truncate max-w-[200px]"
              >
                {a.identifier ?? shortHash(a.id)} {a.title}
              </Link>
            </span>
          ))}
        </div>
      )}

      {/* Hidden warning */}
      {issue.hiddenAt && (
        <div className="border-b border-border px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.10em] text-[var(--verdict-block)] flex items-center gap-1.5">
          <EyeOff className="h-3 w-3" /> issue hidden
        </div>
      )}

      {/* Identity row */}
      <div className="flex items-center gap-3 px-4 py-2 flex-wrap">
        <span className="font-mono text-[12px] tracking-tight text-foreground">{ident}</span>
        <VerdictChip verdict={verdict} label={issue.status.replace(/_/g, " ")} />
        <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary">
          <span className="text-text-secondary">prio</span>{" "}
          <span className="text-foreground">{issue.priority}</span>
        </span>
        <span className="text-foreground text-[13px] tracking-tight font-normal flex-1 min-w-0 truncate">
          {issue.title}
        </span>

        {hasLiveRuns && (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 border border-[var(--verdict-attested)] text-[var(--verdict-attested)] font-mono text-[10px] uppercase tracking-[0.12em]">
            <span className="gm-pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--verdict-attested)]" />
            live
          </span>
        )}

        <div className="flex items-center gap-1 shrink-0">
          {!isCheckedOut ? (
            <ActionKey
              letter="c"
              label="checkout"
              disabled={!assignableAgents[0]}
              onClick={() => assignableAgents[0] && onCheckout(assignableAgents[0].id)}
            />
          ) : (
            <ActionKey letter="r" label="release" onClick={onRelease} />
          )}
          <EnumPopover
            triggerLabel={<span><span className="opacity-60">[s]</span> status</span>}
            triggerData="issue-status-trigger"
            options={STATUS_OPTIONS}
            current={issue.status}
            onSelect={(v) => onUpdate({ status: v })}
          />
          <EnumPopover
            triggerLabel={<span><span className="opacity-60">[p]</span> prio</span>}
            triggerData="issue-priority-trigger"
            options={PRIORITY_OPTIONS}
            current={issue.priority}
            onSelect={(v) => onUpdate({ priority: v })}
          />
          <Popover open={moreOpen} onOpenChange={setMoreOpen}>
            <PopoverTrigger asChild>
              <button className="h-7 px-2 inline-flex items-center gap-1.5 border border-border rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40">
                <span className="opacity-60">[⌘k]</span> more
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-44 p-1 font-mono text-[11px] rounded-none" align="end">
              <button
                className="flex items-center gap-2 w-full px-2 py-1.5 hover:bg-accent/40 uppercase tracking-[0.10em] text-[var(--verdict-block)]"
                onClick={() => {
                  onHide();
                  setMoreOpen(false);
                }}
              >
                <EyeOff className="h-3 w-3" /> hide issue
              </button>
            </PopoverContent>
          </Popover>
          <button
            type="button"
            onClick={onOpenMobileProps}
            className="md:hidden h-7 px-2 border border-border rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40"
          >
            meta
          </button>
        </div>
      </div>

      {/* Meta line */}
      <div className="px-4 pb-2 font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary flex items-center gap-3 flex-wrap">
        <span>
          <span className="text-text-secondary">created</span>{" "}
          <span className="text-foreground tabular-nums">
            {createdDay} {created}
          </span>
        </span>
        <span className="opacity-50">·</span>
        <span>
          <span className="text-text-secondary">by</span>{" "}
          <span className="text-foreground">
            {issue.createdByAgentId
              ? `@${shortHash(issue.createdByAgentId)}`
              : issue.createdByUserId
                ? "@maintainer"
                : "@system"}
          </span>
        </span>
        {subproject && (
          <>
            <span className="opacity-50">·</span>
            <span>
              <span className="text-text-secondary">in</span>{" "}
              <Link
                to={`/projects/${subproject.id}`}
                className="text-foreground hover:underline"
              >
                subproject/{subproject.name}
              </Link>
            </span>
          </>
        )}
        {parent && (
          <>
            <span className="opacity-50">·</span>
            <span>
              <span className="text-text-secondary">parent</span>{" "}
              <Link
                to={`/issues/${parent.identifier ?? parent.id}`}
                className="text-foreground hover:underline"
              >
                #{parent.identifier ?? shortHash(parent.id)}
              </Link>
            </span>
          </>
        )}
        <span className="opacity-50">·</span>
        <span>
          <span className="text-text-secondary">attestations</span>{" "}
          <span className="text-foreground tabular-nums">{attestations}</span>
        </span>
      </div>
    </div>
  );
}

// ── Timeline ─────────────────────────────────────────────────────────────

function Timeline({
  issue,
  stream,
  agentMap,
  editingDescription,
  onStartEditDescription,
  onCancelEditDescription,
  onSaveDescription,
  onDeleteAttachment,
  onUploadImage,
  mentions,
  issueId,
  issueProjectId,
}: {
  issue: Issue;
  stream: StreamItem[];
  agentMap: Map<string, Agent>;
  editingDescription: boolean;
  onStartEditDescription: () => void;
  onCancelEditDescription: () => void;
  onSaveDescription: (value: string) => void;
  onDeleteAttachment: (id: string) => void;
  onUploadImage: (file: File) => Promise<string>;
  mentions: MentionOption[];
  issueId: string;
  issueProjectId: string;
}) {
  return (
    <div className="mesh-spine relative pl-12 pr-4 py-3 space-y-3 min-h-[200px]">
      {stream.map((item) => {
        if (item.kind === "description") {
          return (
            <DescriptionRow
              key={item.key}
              issue={issue}
              editing={editingDescription}
              onStartEdit={onStartEditDescription}
              onCancel={onCancelEditDescription}
              onSave={onSaveDescription}
              onUploadImage={onUploadImage}
              mentions={mentions}
            />
          );
        }
        if (item.kind === "comment") {
          return (
            <CommentRow
              key={item.key}
              comment={item.comment}
              author={commentAuthor(item.comment, agentMap)}
            />
          );
        }
        if (item.kind === "activity") {
          return <ActivityRow key={item.key} event={item.event} agentMap={agentMap} />;
        }
        if (item.kind === "run") {
          return <RunRow key={item.key} run={item.run} agentMap={agentMap} />;
        }
        if (item.kind === "attachment") {
          return (
            <AttachmentRow
              key={item.key}
              attachment={item.attachment}
              onDelete={() => onDeleteAttachment(item.attachment.id)}
            />
          );
        }
        return null;
      })}

      {/* Live run insertion at end (anchored, distinct verdict) */}
      <div className="relative">
        <span className="absolute -left-[34px] top-1.5">
          <MeshDot verdict="pending" running />
        </span>
        <LiveRunWidget issueId={issueId} projectId={issueProjectId} />
      </div>
    </div>
  );
}

function NodeRow({
  verdict,
  running,
  children,
}: {
  verdict?: Verdict;
  running?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="relative">
      <span className="absolute -left-[34px] top-1.5">
        <MeshDot verdict={verdict} running={running} />
      </span>
      {children}
    </div>
  );
}

function DescriptionRow({
  issue,
  editing,
  onCancel,
  onSave,
  onUploadImage,
  mentions,
  onStartEdit,
}: {
  issue: Issue;
  editing: boolean;
  onCancel: () => void;
  onSave: (value: string) => void;
  onUploadImage: (file: File) => Promise<string>;
  mentions: MentionOption[];
  onStartEdit: () => void;
}) {
  const [val, setVal] = useState(issue.description ?? "");
  useEffect(() => {
    if (editing) setVal(issue.description ?? "");
  }, [editing, issue.description]);
  return (
    <NodeRow verdict="attested">
      <div className="border border-border rounded-none bg-surface-1">
        <div className="flex items-center justify-between px-3 py-1 border-b border-border">
          <span className="eyebrow !text-[10px] !tracking-[0.18em]">
            description · {timeOfDay(issue.createdAt)} · {dayStamp(issue.createdAt)}
          </span>
          {!editing && (
            <button
              type="button"
              className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary hover:text-foreground"
              onClick={onStartEdit}
            >
              [e] edit
            </button>
          )}
        </div>
        <div className="px-3 py-2">
          {editing ? (
            <div className="space-y-2">
              <MarkdownEditor
                value={val}
                onChange={setVal}
                placeholder="describe the issue…"
                bordered
                mentions={mentions}
                imageUploadHandler={onUploadImage}
                onSubmit={() => onSave(val)}
              />
              <div className="flex items-center justify-end gap-1">
                <button
                  type="button"
                  onClick={onCancel}
                  className="h-7 px-2 border border-border rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40"
                >
                  cancel
                </button>
                <button
                  type="button"
                  onClick={() => onSave(val)}
                  className="h-7 px-2 border border-[var(--verdict-attested)] text-[var(--verdict-attested)] rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40"
                >
                  save
                </button>
              </div>
            </div>
          ) : issue.description ? (
            <MarkdownBody className="text-sm">{issue.description}</MarkdownBody>
          ) : (
            <p className="font-mono text-[11px] uppercase tracking-[0.10em] text-text-tertiary">
              empty body - press [e] to edit
            </p>
          )}
        </div>
      </div>
    </NodeRow>
  );
}

function CommentRow({ comment, author }: { comment: IssueComment; author: string }) {
  return (
    <NodeRow verdict="allow">
      <div className="border border-border rounded-none bg-surface-1">
        <div className="flex items-center gap-2 px-3 py-1 border-b border-border">
          <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">
            {timeOfDay(comment.createdAt)}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-foreground">
            {author}
          </span>
          <span className="opacity-50">-</span>
          <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary">
            comment
          </span>
        </div>
        <div className="px-3 py-2">
          <MarkdownBody className="text-sm">{comment.body}</MarkdownBody>
        </div>
      </div>
    </NodeRow>
  );
}

function ActivityRow({ event, agentMap }: { event: ActivityEvent; agentMap: Map<string, Agent> }) {
  const verdict = policyVerdict(event.policyOutcome) ?? "pending";
  const isAttested = event.policyOutcome === "allowed";
  return (
    <NodeRow verdict={isAttested ? "attested" : verdict}>
      <div className="flex items-center gap-2 py-1 font-mono text-[11px]">
        <span className="text-text-tertiary uppercase tracking-[0.10em] tabular-nums">
          {timeOfDay(event.createdAt)}
        </span>
        <span className="text-foreground">{actorLabel(event, agentMap)}</span>
        <span className="opacity-50">-</span>
        <span className="text-text-secondary">{formatAction(event.action, event.details)}</span>
        {event.policyOutcome && (
          <VerdictChip
            verdict={verdict}
            label={event.policyOutcome === "allowed" ? "attested" : event.policyOutcome.replace(/_/g, " ")}
          />
        )}
        {event.runId && (
          <Link
            to={`/agents/${event.agentId ?? "unknown"}/runs/${event.runId}`}
            className="ml-auto text-text-tertiary uppercase tracking-[0.10em] hover:text-foreground"
          >
            run·{shortHash(event.runId)}
          </Link>
        )}
      </div>
    </NodeRow>
  );
}

function RunRow({ run, agentMap }: { run: RunForIssue; agentMap: Map<string, Agent> }) {
  const verdict = runVerdict(run.status);
  const agent = agentMap.get(run.agentId);
  const dur =
    run.startedAt && run.finishedAt
      ? Math.max(0, Math.round((new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime()) / 1000))
      : null;
  const durLabel = dur === null ? "-" : dur < 60 ? `${dur}s` : `${Math.floor(dur / 60)}m${dur % 60 ? ` ${dur % 60}s` : ""}`;
  const barWidth = Math.min(80, Math.max(4, dur ? Math.log2(1 + dur) * 8 : 4));
  const usage = asRecord(run.usageJson);
  const result = asRecord(run.resultJson);
  const cost =
    usageNumber(usage, "costUsd", "cost_usd", "total_cost_usd") ||
    usageNumber(result, "total_cost_usd", "cost_usd", "costUsd");
  return (
    <NodeRow verdict={verdict} running={run.status === "running"}>
      <div className="flex items-center gap-2 py-1 font-mono text-[11px]">
        <span className="text-text-tertiary uppercase tracking-[0.10em] tabular-nums">
          {timeOfDay(run.createdAt)}
        </span>
        <span className="text-foreground">@{agent?.name ?? shortHash(run.agentId)}</span>
        <span className="opacity-50">-</span>
        <span className="text-text-secondary">run·{shortHash(run.runId)}</span>
        <VerdictChip verdict={verdict} label={run.status} />
        <span
          className="inline-block h-[6px] rounded-[1px]"
          style={{
            width: `${barWidth}px`,
            background:
              verdict === "allow"
                ? "var(--verdict-allow)"
                : verdict === "block"
                  ? "var(--verdict-block)"
                  : "var(--verdict-pending)",
            opacity: 0.85,
          }}
          title={`${durLabel}${cost ? ` · $${cost.toFixed(4)}` : ""}`}
        />
        <span className="text-text-tertiary tabular-nums">{durLabel}</span>
        {cost > 0 && (
          <span className="text-text-tertiary tabular-nums">${cost.toFixed(4)}</span>
        )}
      </div>
    </NodeRow>
  );
}

function AttachmentRow({
  attachment,
  onDelete,
}: {
  attachment: IssueAttachment;
  onDelete: () => void;
}) {
  const isImage = attachment.contentType.startsWith("image/");
  const sizeKb = (attachment.byteSize / 1024).toFixed(1);
  return (
    <NodeRow verdict="attested">
      <div className="border border-border rounded-none bg-surface-1">
        <div className="flex items-center gap-2 px-3 py-1 border-b border-border">
          <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">
            {timeOfDay(attachment.createdAt)}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-secondary">attachment</span>
          <a
            href={attachment.contentPath}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-[11px] text-foreground hover:underline truncate"
          >
            {attachment.originalFilename ?? attachment.id}
          </a>
          <span className="font-mono text-[10px] uppercase tracking-[0.10em] text-text-tertiary tabular-nums">
            {sizeKb}kb · {attachment.contentType}
          </span>
          <button
            type="button"
            onClick={onDelete}
            className="ml-auto text-text-tertiary hover:text-[var(--verdict-block)]"
            title="delete"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
        {isImage && (
          <a href={attachment.contentPath} target="_blank" rel="noreferrer" className="block">
            <img
              src={attachment.contentPath}
              alt={attachment.originalFilename ?? "attachment"}
              className="max-h-56 w-full object-contain bg-accent/10"
              loading="lazy"
            />
          </a>
        )}
      </div>
    </NodeRow>
  );
}

// ── Sidekick (right column) ──────────────────────────────────────────────

function Sidekick({
  issue,
  verdict,
  subproject,
  parent,
  assigneeAgent,
  assignableAgents,
  childIssues,
  attachments,
  attachmentError,
  attestations,
  linkedApprovalsCount,
  costSummary,
  labelsCatalog,
  projects,
  onUpdate,
  onPickFile,
  onDeleteAttachment,
  uploadDisabled,
  issueId,
}: {
  issue: Issue;
  verdict: Verdict;
  subproject: { id: string; name: string } | null;
  parent: { id: string; identifier: string | null; title: string } | null;
  assigneeAgent: Agent | null;
  assignableAgents: Agent[];
  childIssues: Issue[];
  attachments: IssueAttachment[];
  attachmentError: string | null;
  attestations: number;
  linkedApprovalsCount: number;
  costSummary: { input: number; output: number; cost: number; totalTokens: number; hasCost: boolean; hasTokens: boolean };
  labelsCatalog: IssueLabel[];
  projects: { id: string; name: string }[];
  onUpdate: (data: Record<string, unknown>) => void;
  onPickFile: () => void;
  onDeleteAttachment: (id: string) => void;
  uploadDisabled: boolean;
  issueId: string;
}) {
  const issueLabelIds = new Set((issue.labels ?? []).map((l) => l.id));

  const toggleLabel = (id: string) => {
    const next = new Set(issueLabelIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onUpdate({ labelIds: Array.from(next) });
  };

  return (
    <div className="font-mono text-[11px]">
      {/* STATUS */}
      <SidekickSection label="status">
        <EnumPopover
          triggerLabel={<VerdictChip verdict={verdict} label={issue.status.replace(/_/g, " ")} />}
          options={STATUS_OPTIONS}
          current={issue.status}
          onSelect={(v) => onUpdate({ status: v })}
        />
      </SidekickSection>

      {/* ASSIGNEE */}
      <SidekickSection label="assignee">
        <InlinePicker
          value={issue.assigneeAgentId ?? null}
          options={assignableAgents.map((a) => ({ id: a.id, label: a.name }))}
          emptyLabel="- unassigned"
          onChange={(id) =>
            onUpdate({
              assigneeAgentId: id,
              assigneeUserId: id ? null : issue.assigneeUserId,
            })
          }
          trigger={
            <button
              data-issue-assign-trigger
              className="w-full flex items-center justify-between hover:text-foreground text-left"
            >
              <span>
                {assigneeAgent ? (
                  <Identity name={`@${assigneeAgent.name}`} size="xs" />
                ) : issue.assigneeUserId ? (
                  <span className="text-foreground">@maintainer</span>
                ) : (
                  <span className="text-text-tertiary">- unassigned</span>
                )}
              </span>
              <span className="opacity-50">▸</span>
            </button>
          }
        />
      </SidekickSection>

      {/* PRIORITY */}
      <SidekickSection label="priority">
        <EnumPopover
          triggerLabel={<span className="text-foreground uppercase tracking-[0.10em]">{issue.priority}</span>}
          options={PRIORITY_OPTIONS}
          current={issue.priority}
          onSelect={(v) => onUpdate({ priority: v })}
        />
      </SidekickSection>

      {/* LABELS */}
      <SidekickSection label="labels">
        {issueLabelIds.size === 0 && labelsCatalog.length === 0 ? (
          <span className="text-text-tertiary">-</span>
        ) : (
          <Popover>
            <PopoverTrigger asChild>
              <button className="w-full flex items-center justify-between hover:text-foreground text-left">
                <span className="flex items-center gap-1 flex-wrap">
                  {(issue.labels ?? []).slice(0, 4).map((l) => (
                    <span
                      key={l.id}
                      className="inline-flex items-center px-1.5 py-0 border text-[10px] uppercase tracking-[0.08em]"
                      style={{
                        borderColor: l.color,
                        color: l.color,
                      }}
                    >
                      {l.name}
                    </span>
                  ))}
                  {issueLabelIds.size === 0 && (
                    <span className="text-text-tertiary">- none</span>
                  )}
                  {(issue.labels ?? []).length > 4 && (
                    <span className="text-text-tertiary">+{(issue.labels ?? []).length - 4}</span>
                  )}
                </span>
                <span className="opacity-50">▸</span>
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-56 p-1 font-mono text-[11px] rounded-none" align="end">
              <div className="max-h-56 overflow-y-auto gitmesh-scrollbar">
                {labelsCatalog.map((l) => {
                  const active = issueLabelIds.has(l.id);
                  return (
                    <button
                      key={l.id}
                      onClick={() => toggleLabel(l.id)}
                      className={cn(
                        "w-full flex items-center gap-2 px-2 py-1.5 hover:bg-accent/40",
                        active && "bg-accent/60",
                      )}
                    >
                      <span
                        className="inline-block h-2 w-2"
                        style={{ background: l.color }}
                      />
                      <span className="uppercase tracking-[0.08em]">{l.name}</span>
                      {active && <span className="ml-auto opacity-70">✓</span>}
                    </button>
                  );
                })}
                {labelsCatalog.length === 0 && (
                  <div className="px-2 py-2 text-text-tertiary text-[10px] uppercase tracking-[0.10em]">
                    no labels defined
                  </div>
                )}
              </div>
            </PopoverContent>
          </Popover>
        )}
      </SidekickSection>

      {/* PARENT */}
      <SidekickSection label="parent">
        {parent ? (
          <Link
            to={`/issues/${parent.identifier ?? parent.id}`}
            className="flex items-center justify-between hover:text-foreground"
          >
            <span className="truncate">
              <span className="text-text-secondary">#{parent.identifier ?? shortHash(parent.id)}</span>{" "}
              <span className="text-foreground">{parent.title}</span>
            </span>
            <span className="opacity-50">▸</span>
          </Link>
        ) : (
          <span className="text-text-tertiary">- none</span>
        )}
        {childIssues.length > 0 && (
          <div className="mt-1.5 pt-1.5 border-t border-border space-y-0.5">
            <span className="eyebrow !text-[9px] !tracking-[0.18em]">children · {childIssues.length}</span>
            {childIssues.slice(0, 6).map((c) => (
              <Link
                key={c.id}
                to={`/issues/${c.identifier ?? c.id}`}
                className="flex items-center justify-between hover:text-foreground"
              >
                <span className="truncate">
                  <span className="text-text-secondary">#{c.identifier ?? shortHash(c.id)}</span>{" "}
                  <span className="text-foreground">{c.title}</span>
                </span>
                <span className="opacity-50">▸</span>
              </Link>
            ))}
          </div>
        )}
      </SidekickSection>

      {/* SUBPROJECT */}
      <SidekickSection label="subproject">
        <InlinePicker
          value={issue.projectId ?? null}
          options={projects.map((p) => ({ id: p.id, label: p.name }))}
          emptyLabel="- none"
          onChange={(id) => onUpdate({ projectId: id })}
          trigger={
            <button className="w-full flex items-center justify-between hover:text-foreground text-left">
              <span className="truncate">
                {subproject ? (
                  <span className="text-foreground">subproject/{subproject.name}</span>
                ) : (
                  <span className="text-text-tertiary">- none</span>
                )}
              </span>
              <span className="opacity-50">▸</span>
            </button>
          }
        />
      </SidekickSection>

      {/* EXECUTION */}
      <SidekickSection label="execution">
        <div className="space-y-0.5">
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">checkout</span>
            <span className="text-foreground">
              {issue.checkoutRunId ? `run·${shortHash(issue.checkoutRunId)}` : "-"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary">locked</span>
            <span className="text-foreground tabular-nums">
              {issue.executionLockedAt ? relativeTime(issue.executionLockedAt) : "-"}
            </span>
          </div>
          {costSummary.hasCost && (
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">cost</span>
              <span className="text-foreground tabular-nums">${costSummary.cost.toFixed(4)}</span>
            </div>
          )}
          {costSummary.hasTokens && (
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">tokens</span>
              <span className="text-foreground tabular-nums">
                {formatTokens(costSummary.totalTokens)}
              </span>
            </div>
          )}
          {linkedApprovalsCount > 0 && (
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">approvals</span>
              <span className="text-foreground tabular-nums">{linkedApprovalsCount}</span>
            </div>
          )}
        </div>
      </SidekickSection>

      {/* ATTACHMENTS */}
      <SidekickSection label="attachments">
        <div className="space-y-1">
          {attachmentError && (
            <p className="text-[10px] uppercase tracking-[0.10em] text-[var(--verdict-block)]">
              {attachmentError}
            </p>
          )}
          {attachments.length === 0 && (
            <span className="text-text-tertiary">- none</span>
          )}
          {attachments.map((a) => (
            <div key={a.id} className="flex items-center gap-2">
              <a
                href={a.contentPath}
                target="_blank"
                rel="noreferrer"
                className="truncate text-foreground hover:underline flex-1"
              >
                {a.originalFilename ?? a.id}
              </a>
              <span className="text-text-tertiary tabular-nums text-[10px]">
                {(a.byteSize / 1024).toFixed(1)}kb
              </span>
              <button
                type="button"
                onClick={() => onDeleteAttachment(a.id)}
                className="text-text-tertiary hover:text-[var(--verdict-block)]"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={onPickFile}
            disabled={uploadDisabled}
            className="mt-1 h-7 px-2 inline-flex items-center gap-1.5 border border-border rounded-none font-mono text-[10px] uppercase tracking-[0.10em] hover:bg-accent/40 disabled:opacity-40"
          >
            <ImagePlus className="h-3 w-3" />
            {uploadDisabled ? "uploading…" : "upload image"}
          </button>
        </div>
      </SidekickSection>

      {/* ATTESTATIONS link */}
      <div className="px-4 py-2 border-t border-border">
        <Link
          to={`/audit-log?issueId=${issueId}`}
          className="flex items-center justify-between hover:text-foreground"
        >
          <span>
            <span className="text-text-secondary">attestations</span>{" "}
            <span className="text-foreground tabular-nums">{attestations}</span>
          </span>
          <span className="opacity-50">▸</span>
        </Link>
      </div>
    </div>
  );
}

function SidekickSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="px-4 py-2 border-b border-border">
      <Eyebrow>{label}</Eyebrow>
      <div>{children}</div>
    </div>
  );
}
