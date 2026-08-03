import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from "react";
import { useNavigate, useLocation } from "@/lib/router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Approval, ApprovalComment, Issue, Agent } from "@gitmesh/core";
import { approvalsApi } from "../../api/approvals";
import { agentsApi } from "../../api/agents";
import { useProject } from "../../context/ProjectContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { cn } from "../../lib/utils";
import { PageSkeleton } from "../../components/PageSkeleton";

type FilterPill = "is:pending" | "is:approved" | "is:rejected" | "for:@me";

const FILTER_PILLS: FilterPill[] = ["is:pending", "is:approved", "is:rejected", "for:@me"];

type Verdict = "pending" | "approved" | "rejected" | "revision_requested" | "cancelled";

function verdictTone(status: Verdict): {
  chip: "pending" | "allow" | "block" | "attested";
  rail: string;
  label: string;
} {
  switch (status) {
    case "approved":
      return { chip: "allow", rail: "var(--verdict-allow)", label: "approved" };
    case "rejected":
      return { chip: "block", rail: "var(--verdict-block)", label: "rejected" };
    case "revision_requested":
      return { chip: "pending", rail: "var(--verdict-pending)", label: "revise" };
    case "cancelled":
      return { chip: "attested", rail: "var(--border)", label: "cancelled" };
    case "pending":
    default:
      return { chip: "pending", rail: "var(--verdict-pending)", label: "pending" };
  }
}

function formatTime(d: Date | string): string {
  const date = typeof d === "string" ? new Date(d) : d;
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function actionVerb(type: Approval["type"]): string {
  switch (type) {
    case "enable_agent":
      return "enable";
    case "approve_admin_strategy":
      return "approve-strategy";
    case "merge_pr":
      return "merge";
    case "close_issue":
      return "close";
    case "publish_advisory":
      return "publish";
    default:
      return String(type);
  }
}

function entityFromPayload(approval: Approval): string {
  const p = approval.payload ?? {};
  const candidates = [
    (p as Record<string, unknown>).issueRef,
    (p as Record<string, unknown>).issueNumber,
    (p as Record<string, unknown>).prRef,
    (p as Record<string, unknown>).prNumber,
    (p as Record<string, unknown>).agentName,
    (p as Record<string, unknown>).target,
    (p as Record<string, unknown>).name,
    (p as Record<string, unknown>).title,
  ];
  for (const c of candidates) {
    if (typeof c === "string" && c.length > 0) return c;
    if (typeof c === "number") return `#${c}`;
  }
  return approval.type;
}

function contextFromPayload(approval: Approval): string {
  const p = approval.payload ?? {};
  const ctx = (p as Record<string, unknown>).reason ?? (p as Record<string, unknown>).summary ?? (p as Record<string, unknown>).note;
  if (typeof ctx === "string" && ctx.length > 0) return ctx;
  return approval.id.slice(0, 8);
}

export function Approvals() {
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();

  const [actionError, setActionError] = useState<string | null>(null);
  const [activePill, setActivePill] = useState<FilterPill>("is:pending");
  const [filterText, setFilterText] = useState("");
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [decisionNotes, setDecisionNotes] = useState<Record<string, string>>({});
  const [commentDraft, setCommentDraft] = useState<Record<string, string>>({});

  const filterInputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const containerRef = useRef<HTMLDivElement | null>(null);

  const pathSegment = location.pathname.split("/").pop() ?? "pending";

  useEffect(() => {
    setBreadcrumbs([{ label: "Gate" }]);
  }, [setBreadcrumbs]);

  useEffect(() => {
    if (pathSegment === "all") setActivePill("is:pending");
  }, [pathSegment]);

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.approvals.list(selectedProjectId!),
    queryFn: () => approvalsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => approvalsApi.approve(id, note),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals.list(selectedProjectId!) });
    },
    onError: (err) => setActionError(err instanceof Error ? err.message : "Failed to approve"),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => approvalsApi.reject(id, note),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals.list(selectedProjectId!) });
    },
    onError: (err) => setActionError(err instanceof Error ? err.message : "Failed to reject"),
  });

  const reviseMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      approvalsApi.requestRevision(id, note),
    onSuccess: () => {
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals.list(selectedProjectId!) });
    },
    onError: (err) => setActionError(err instanceof Error ? err.message : "Failed to request revision"),
  });

  const addCommentMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => approvalsApi.addComment(id, body),
    onSuccess: (_data, vars) => {
      setActionError(null);
      setCommentDraft((prev) => ({ ...prev, [vars.id]: "" }));
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals.comments(vars.id) });
    },
    onError: (err) => setActionError(err instanceof Error ? err.message : "Failed to add comment"),
  });

  const all = data ?? [];
  const total = all.length;
  const pendingCount = all.filter(
    (a) => a.status === "pending" || a.status === "revision_requested",
  ).length;

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    return all
      .filter((a) => {
        switch (activePill) {
          case "is:pending":
            return a.status === "pending" || a.status === "revision_requested";
          case "is:approved":
            return a.status === "approved";
          case "is:rejected":
            return a.status === "rejected";
          case "for:@me":
            return true;
          default:
            return true;
        }
      })
      .filter((a) => {
        if (!q) return true;
        const hay = [a.type, a.id, a.status, JSON.stringify(a.payload ?? {})]
          .join(" ")
          .toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [all, activePill, filterText]);

  // Clamp focused index when list changes
  useEffect(() => {
    if (filtered.length === 0) {
      setFocusedIndex(0);
      return;
    }
    setFocusedIndex((i) => Math.min(i, filtered.length - 1));
  }, [filtered.length]);

  const focusedApproval = filtered[focusedIndex];

  // Comments for currently expanded row
  const { data: expandedComments } = useQuery({
    queryKey: queryKeys.approvals.comments(expandedId ?? ""),
    queryFn: () => approvalsApi.listComments(expandedId!),
    enabled: !!expandedId,
  });

  const { data: expandedIssues } = useQuery({
    queryKey: queryKeys.approvals.issues(expandedId ?? ""),
    queryFn: () => approvalsApi.listIssues(expandedId!),
    enabled: !!expandedId,
  });

  const handleApprove = (id: string) => {
    approveMutation.mutate({ id, note: decisionNotes[id]?.trim() || undefined });
  };
  const handleReject = (id: string) => {
    rejectMutation.mutate({ id, note: decisionNotes[id]?.trim() || undefined });
  };
  const handleRevise = (id: string) => {
    if (expandedId !== id) {
      setExpandedId(id);
      // require note before mutating; user fills then re-presses v
      return;
    }
    const note = decisionNotes[id]?.trim();
    if (!note) {
      // focus the textarea
      const ta = document.getElementById(`gate-note-${id}`);
      if (ta) (ta as HTMLTextAreaElement).focus();
      return;
    }
    reviseMutation.mutate({ id, note });
  };

  const focusFilter = () => {
    filterInputRef.current?.focus();
    filterInputRef.current?.select();
  };

  const onContainerKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const tag = target.tagName;
    const isEditable =
      tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
    if (e.key === "/" && !isEditable) {
      e.preventDefault();
      focusFilter();
      return;
    }
    if (isEditable) return;
    if (filtered.length === 0) return;

    const current = filtered[focusedIndex];

    switch (e.key) {
      case "j":
      case "ArrowDown": {
        e.preventDefault();
        const next = Math.min(focusedIndex + 1, filtered.length - 1);
        setFocusedIndex(next);
        rowRefs.current[filtered[next]?.id]?.focus();
        break;
      }
      case "k":
      case "ArrowUp": {
        e.preventDefault();
        const next = Math.max(focusedIndex - 1, 0);
        setFocusedIndex(next);
        rowRefs.current[filtered[next]?.id]?.focus();
        break;
      }
      case "Enter": {
        if (!current) return;
        e.preventDefault();
        setExpandedId((prev) => (prev === current.id ? null : current.id));
        break;
      }
      case "a": {
        if (!current) return;
        e.preventDefault();
        handleApprove(current.id);
        break;
      }
      case "r": {
        if (!current) return;
        e.preventDefault();
        handleReject(current.id);
        break;
      }
      case "v": {
        if (!current) return;
        e.preventDefault();
        handleRevise(current.id);
        break;
      }
      default:
        break;
    }
  };

  if (!selectedProjectId) {
    return (
      <p className="font-mono text-sm text-muted-foreground">
        gate · select a project first
      </p>
    );
  }

  if (isLoading) {
    return <PageSkeleton variant="approvals" />;
  }

  return (
    <div
      ref={containerRef}
      onKeyDown={onContainerKey}
      tabIndex={-1}
      className="relative flex h-full flex-col font-mono text-[12.5px] text-foreground outline-none"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {/* Header strip */}
      <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
        <span className="text-foreground">
          gate · <span style={{ color: "var(--verdict-pending)" }}>{pendingCount}</span>
          <span className="text-muted-foreground">/{total}</span>
        </span>

        <div className="ml-4 flex items-center gap-1 text-[11px]">
          {FILTER_PILLS.map((pill, idx) => {
            const active = activePill === pill;
            return (
              <span key={pill} className="flex items-center">
                {idx > 0 && <span className="mx-1 text-muted-foreground/60">·</span>}
                <button
                  type="button"
                  onClick={() => setActivePill(pill)}
                  className={cn(
                    "px-1.5 py-0.5 transition-colors",
                    active
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                  style={
                    active
                      ? {
                          borderBottom: "1px solid var(--verdict-attested)",
                          color: "var(--verdict-attested)",
                        }
                      : undefined
                  }
                >
                  {pill}
                </button>
              </span>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-1.5 text-[11px]">
          <span className="text-muted-foreground">&gt;</span>
          <input
            ref={filterInputRef}
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                setFilterText("");
                (e.target as HTMLInputElement).blur();
              }
            }}
            placeholder="filter ..."
            spellCheck={false}
            className="w-48 bg-transparent px-1 py-0.5 text-foreground placeholder:text-muted-foreground/60 outline-none focus:ring-0"
            style={{ fontFamily: "var(--font-mono)" }}
          />
        </div>
      </div>

      {(error || actionError) && (
        <div
          className="border-b border-border px-4 py-1.5 text-[11px]"
          style={{ color: "var(--verdict-block)" }}
        >
          ! {error?.message ?? actionError}
        </div>
      )}

      {/* Queue */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="px-4 py-8 text-[12px] text-muted-foreground">
            <span style={{ color: "var(--verdict-allow)" }}>gate is clear</span>
            <span className="text-muted-foreground"> · nothing pending</span>
          </div>
        ) : (
          filtered.map((approval, idx) => {
            const tone = verdictTone(approval.status as Verdict);
            const isExpanded = expandedId === approval.id;
            const isFocused = focusedIndex === idx;
            const requesterAgent: Agent | null = approval.requestedByAgentId
              ? (agents ?? []).find((a) => a.id === approval.requestedByAgentId) ?? null
              : null;
            const agentLabel = requesterAgent?.name ?? "system";
            const time = formatTime(approval.createdAt);
            const verb = actionVerb(approval.type);
            const entity = entityFromPayload(approval);
            const ctx = contextFromPayload(approval);

            const rowStyle: CSSProperties = {
              borderLeft: `2px solid ${tone.rail}`,
              fontFamily: "var(--font-mono)",
            };

            return (
              <div key={approval.id} className="border-b border-border">
                {/* Single-line row */}
                <div
                  ref={(el) => {
                    rowRefs.current[approval.id] = el;
                  }}
                  role="button"
                  tabIndex={0}
                  onFocus={() => setFocusedIndex(idx)}
                  onClick={(e) => {
                    // Don't toggle when clicking action buttons
                    const target = e.target as HTMLElement;
                    if (target.closest("[data-row-action]")) return;
                    setFocusedIndex(idx);
                    setExpandedId((prev) => (prev === approval.id ? null : approval.id));
                  }}
                  className={cn(
                    "group flex h-7 cursor-pointer select-none items-center gap-2 px-3 text-[12px] outline-none",
                    "hover:bg-[var(--surface-2)] focus:bg-[var(--surface-2)]",
                    isFocused && "bg-[var(--surface-2)]",
                  )}
                  style={rowStyle}
                >
                  {/* Collapse toggle + id */}
                  <span className="w-3 text-center text-muted-foreground">
                    {isExpanded ? "▾" : "▸"}
                  </span>
                  <span className="w-[60px] truncate text-muted-foreground">
                    {approval.id.slice(0, 8)}
                  </span>

                  {/* Verdict chip */}
                  <span className="verdict-chip" data-verdict={tone.chip}>
                    {tone.label}
                  </span>

                  {/* Time */}
                  <span className="w-[42px] text-muted-foreground">{time}</span>

                  {/* agent → action on entity */}
                  <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate">
                    <span className="truncate text-foreground">{agentLabel}</span>
                    <span className="text-muted-foreground">→</span>
                    <span style={{ color: "var(--verdict-attested)" }}>{verb}</span>
                    <span className="text-muted-foreground">on</span>
                    <span className="truncate text-foreground">{entity}</span>
                    <span className="text-muted-foreground/60">·</span>
                    <span className="truncate text-muted-foreground">{ctx}</span>
                  </span>

                  {/* Inline actions */}
                  <div
                    className={cn(
                      "ml-auto flex shrink-0 items-center gap-2 text-[11px]",
                      "opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100",
                      isFocused && "opacity-100",
                    )}
                  >
                    <button
                      type="button"
                      data-row-action
                      onClick={(e) => {
                        e.stopPropagation();
                        handleApprove(approval.id);
                      }}
                      disabled={approveMutation.isPending}
                      className="hover:underline"
                      style={{ color: "var(--verdict-allow)" }}
                    >
                      [a]pprove
                    </button>
                    <button
                      type="button"
                      data-row-action
                      onClick={(e) => {
                        e.stopPropagation();
                        handleReject(approval.id);
                      }}
                      disabled={rejectMutation.isPending}
                      className="hover:underline"
                      style={{ color: "var(--verdict-block)" }}
                    >
                      [r]eject
                    </button>
                    <button
                      type="button"
                      data-row-action
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRevise(approval.id);
                      }}
                      disabled={reviseMutation.isPending}
                      className="hover:underline"
                      style={{ color: "var(--verdict-pending)" }}
                    >
                      [v]revise
                    </button>
                  </div>
                </div>

                {/* Expanded payload */}
                {isExpanded && (
                  <ExpandedPayload
                    approval={approval}
                    issues={expandedIssues ?? null}
                    comments={expandedComments ?? null}
                    requesterAgent={requesterAgent}
                    decisionNote={decisionNotes[approval.id] ?? ""}
                    onDecisionNoteChange={(v) =>
                      setDecisionNotes((prev) => ({ ...prev, [approval.id]: v }))
                    }
                    commentDraft={commentDraft[approval.id] ?? ""}
                    onCommentDraftChange={(v) =>
                      setCommentDraft((prev) => ({ ...prev, [approval.id]: v }))
                    }
                    onAddComment={() => {
                      const body = (commentDraft[approval.id] ?? "").trim();
                      if (!body) return;
                      addCommentMutation.mutate({ id: approval.id, body });
                    }}
                    onApprove={() => handleApprove(approval.id)}
                    onReject={() => handleReject(approval.id)}
                    onRevise={() => handleRevise(approval.id)}
                    onOpenDetail={() => navigate(`/approvals/${approval.id}`)}
                    pending={
                      approveMutation.isPending ||
                      rejectMutation.isPending ||
                      reviseMutation.isPending
                    }
                  />
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer hint */}
      <div className="pointer-events-none absolute bottom-2 right-3 select-none text-[10.5px] text-muted-foreground">
        j/k · ↵ expand · a approve · r reject · v revise · / filter
      </div>

      {/* Hidden focus reference */}
      <div className="sr-only" aria-live="polite">
        {focusedApproval ? `focused ${focusedApproval.id}` : ""}
      </div>
    </div>
  );
}

interface ExpandedPayloadProps {
  approval: Approval;
  issues: Issue[] | null;
  comments: ApprovalComment[] | null;
  requesterAgent: Agent | null;
  decisionNote: string;
  onDecisionNoteChange: (v: string) => void;
  commentDraft: string;
  onCommentDraftChange: (v: string) => void;
  onAddComment: () => void;
  onApprove: () => void;
  onReject: () => void;
  onRevise: () => void;
  onOpenDetail: () => void;
  pending: boolean;
}

function ExpandedPayload({
  approval,
  issues,
  comments,
  requesterAgent,
  decisionNote,
  onDecisionNoteChange,
  commentDraft,
  onCommentDraftChange,
  onAddComment,
  onApprove,
  onReject,
  onRevise,
  onOpenDetail,
  pending,
}: ExpandedPayloadProps) {
  const tone = verdictTone(approval.status as Verdict);

  const payloadEntries = useMemo(() => {
    const p = approval.payload ?? {};
    const base: [string, string][] = [
      ["id", approval.id],
      ["type", approval.type],
      ["status", approval.status],
      ["created", new Date(approval.createdAt).toISOString()],
    ];
    if (approval.decidedAt) {
      base.push(["decided", new Date(approval.decidedAt).toISOString()]);
    }
    if (approval.decisionNote) {
      base.push(["note", approval.decisionNote]);
    }
    if (requesterAgent) {
      base.push(["agent", requesterAgent.name]);
    }
    for (const [k, v] of Object.entries(p as Record<string, unknown>)) {
      let rendered: string;
      if (v === null || v === undefined) rendered = "-";
      else if (typeof v === "object") rendered = JSON.stringify(v);
      else rendered = String(v);
      base.push([`payload.${k}`, rendered]);
    }
    return base;
  }, [approval, requesterAgent]);

  return (
    <div
      className="grid gap-0 border-t border-border bg-[var(--surface-1)] text-[12px] md:grid-cols-2"
      style={{ borderLeft: `2px solid ${tone.rail}`, fontFamily: "var(--font-mono)" }}
    >
      {/* Left: payload key/value */}
      <div className="border-b border-border p-3 md:border-b-0 md:border-r">
        <div className="mb-2 flex items-center justify-between text-[11px] text-muted-foreground">
          <span>payload</span>
          <button
            type="button"
            onClick={onOpenDetail}
            className="hover:underline"
            style={{ color: "var(--verdict-attested)" }}
          >
            open detail →
          </button>
        </div>
        <dl className="space-y-0.5">
          {payloadEntries.map(([k, v]) => (
            <div key={k} className="flex gap-3 leading-5">
              <dt className="w-32 shrink-0 truncate text-muted-foreground">{k}</dt>
              <dd className="min-w-0 flex-1 break-all text-foreground">{v}</dd>
            </div>
          ))}
        </dl>
        {issues && issues.length > 0 && (
          <div className="mt-3 border-t border-border pt-2">
            <div className="mb-1 text-[11px] text-muted-foreground">linked-issues</div>
            <ul className="space-y-0.5">
              {issues.map((issue) => (
                <li key={issue.id} className="flex gap-2 leading-5">
                  <span className="text-muted-foreground">#{String(issue.id).slice(0, 6)}</span>
                  <span className="truncate text-foreground">{issue.title}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Right: comments + decision note */}
      <div className="flex flex-col p-3">
        <div className="mb-2 text-[11px] text-muted-foreground">comments</div>
        <div className="mb-2 max-h-40 flex-1 space-y-1 overflow-y-auto">
          {comments && comments.length > 0 ? (
            comments.map((c) => (
              <div key={c.id} className="leading-5">
                <span className="text-muted-foreground">
                  {formatTime(c.createdAt)} ·{" "}
                  {c.authorAgentId ? `agent:${c.authorAgentId.slice(0, 6)}` : "user"} ›
                </span>{" "}
                <span className="text-foreground">{c.body}</span>
              </div>
            ))
          ) : (
            <div className="text-muted-foreground">- no comments -</div>
          )}
        </div>

        <div className="mb-2 flex items-stretch gap-2">
          <span className="pt-1 text-muted-foreground">›</span>
          <input
            value={commentDraft}
            onChange={(e) => onCommentDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onAddComment();
              }
            }}
            placeholder="reply ..."
            spellCheck={false}
            className="flex-1 border-b border-border bg-transparent py-0.5 text-[12px] outline-none placeholder:text-muted-foreground/60 focus:border-[var(--verdict-attested)]"
            style={{ fontFamily: "var(--font-mono)" }}
          />
        </div>

        <div className="mb-2 text-[11px] text-muted-foreground">decision-note</div>
        <textarea
          id={`gate-note-${approval.id}`}
          value={decisionNote}
          onChange={(e) => onDecisionNoteChange(e.target.value)}
          rows={2}
          placeholder="optional note for approve/reject; required for revise ..."
          spellCheck={false}
          className="mb-2 resize-none border border-border bg-transparent p-1.5 text-[12px] outline-none placeholder:text-muted-foreground/60 focus:border-[var(--verdict-attested)]"
          style={{ fontFamily: "var(--font-mono)" }}
        />

        <div className="flex items-center gap-3 text-[11px]">
          <button
            type="button"
            onClick={onApprove}
            disabled={pending}
            className="hover:underline disabled:opacity-50"
            style={{ color: "var(--verdict-allow)" }}
          >
            [approve]
          </button>
          <button
            type="button"
            onClick={onReject}
            disabled={pending}
            className="hover:underline disabled:opacity-50"
            style={{ color: "var(--verdict-block)" }}
          >
            [reject]
          </button>
          <button
            type="button"
            onClick={onRevise}
            disabled={pending}
            className="hover:underline disabled:opacity-50"
            style={{ color: "var(--verdict-pending)" }}
          >
            [request revision]
          </button>
        </div>
      </div>
    </div>
  );
}

export default Approvals;
