import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import { milestonesApi } from "../../api/milestones";
import { useProject } from "../../context/ProjectContext";
import { useDialog } from "../../context/DialogContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { Target } from "lucide-react";
import type { Goal } from "@gitmesh/core";

type Verdict = "block" | "pending" | "attested" | "none";

function statusVerdict(status: string): Verdict {
  if (status === "achieved") return "attested";
  if (status === "active") return "pending";
  if (status === "cancelled") return "block";
  return "none";
}

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

const LEVEL_PILLS = ["all", "project", "milestone", "issue", "task"] as const;
type LevelPill = (typeof LEVEL_PILLS)[number];

export function Milestones() {
  const { selectedProjectId } = useProject();
  const { openNewGoal } = useDialog();
  const { setBreadcrumbs } = useBreadcrumbs();
  const navigate = useNavigate();

  const [filterText, setFilterText] = useState("");
  const [levelFilter, setLevelFilter] = useState<LevelPill>("all");
  const [focusedIdx, setFocusedIdx] = useState(0);
  const filterInputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    setBreadcrumbs([{ label: "Milestones" }]);
  }, [setBreadcrumbs]);

  const { data: goals, isLoading, error } = useQuery({
    queryKey: queryKeys.milestones.list(selectedProjectId!),
    queryFn: () => milestonesApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const allGoals: Goal[] = goals ?? [];

  const filtered = useMemo(() => {
    let r = allGoals.slice();
    if (levelFilter !== "all") {
      r = r.filter((g) => g.level === levelFilter);
    }
    const q = filterText.trim().toLowerCase();
    if (q) {
      r = r.filter((g) =>
        [g.title, g.description ?? "", g.status, g.level].join(" ").toLowerCase().includes(q),
      );
    }
    r.sort((a, b) => {
      const ta = new Date(a.updatedAt ?? a.createdAt).getTime();
      const tb = new Date(b.updatedAt ?? b.createdAt).getTime();
      return tb - ta;
    });
    return r;
  }, [allGoals, filterText, levelFilter]);

  // Keyboard
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
      if (filtered.length === 0) return;

      if (e.key === "j") {
        e.preventDefault();
        setFocusedIdx((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setFocusedIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const g = filtered[focusedIdx];
        if (g) navigate(`/milestones/${g.id}`);
      } else if (e.key === "n" && !isTyping) {
        e.preventDefault();
        openNewGoal();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filtered, focusedIdx, navigate, openNewGoal]);

  useEffect(() => {
    if (focusedIdx >= filtered.length) {
      setFocusedIdx(Math.max(0, filtered.length - 1));
    }
  }, [filtered.length, focusedIdx]);

  useEffect(() => {
    rowRefs.current[focusedIdx]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusedIdx]);

  if (!selectedProjectId) {
    return (
      <div
        className="py-12 text-center text-xs text-text-tertiary"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        select a project to view milestones
      </div>
    );
  }

  return (
    <div
      className="flex flex-col gap-3 pb-12"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {/* Header strip */}
      <div className="flex h-8 items-center justify-between border-b border-border">
        <span className="text-sm tracking-tight text-foreground">
          milestones
          <span className="ml-2 tabular-nums text-text-tertiary">· {allGoals.length}</span>
          {filtered.length !== allGoals.length && (
            <span className="ml-1 tabular-nums text-text-tertiary">
              ({filtered.length} shown)
            </span>
          )}
        </span>
        <div className="flex min-w-[220px] flex-1 items-center gap-1.5 border-b border-border px-1 py-0.5 sm:max-w-sm sm:flex-none">
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

      {/* Filter pill bar */}
      <div className="flex flex-wrap items-center gap-2">
        {LEVEL_PILLS.map((lvl) => {
          const active = levelFilter === lvl;
          return (
            <button
              key={lvl}
              type="button"
              onClick={() => setLevelFilter(lvl)}
              className="rounded-sm px-2 py-0.5 text-[11px] tracking-tight transition-colors"
              style={{
                border: active ? "1px solid var(--verdict-attested)" : "1px solid transparent",
                color: active ? "var(--verdict-attested)" : "var(--text-tertiary)",
                background: "transparent",
              }}
            >
              level:{lvl}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => openNewGoal()}
          className="ml-auto rounded-sm px-2 py-0.5 text-[11px] tracking-tight text-text-tertiary transition-colors hover:text-foreground"
          style={{ border: "1px solid transparent" }}
        >
          [+ new]
        </button>
      </div>

      {/* Errors */}
      {error && (
        <div className="text-xs" style={{ color: "var(--verdict-block)" }}>
          {(error as Error).message}
        </div>
      )}

      {/* Body */}
      {isLoading ? (
        <div className="py-12 text-center text-xs text-text-tertiary">
          loading milestones …
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-xs text-text-tertiary">
          {allGoals.length === 0
            ? "no milestones - press n to add"
            : "no milestones match - try a different filter"}
        </div>
      ) : (
        <div className="flex flex-col">
          {/* Column header row */}
          <div
            className="grid h-6 items-center gap-2 border-b border-border pl-0 pr-2 text-[10px] uppercase tracking-[0.18em] text-text-tertiary"
            style={{
              gridTemplateColumns:
                "2px 16px 90px minmax(0, 1fr) 90px 90px 56px",
            }}
          >
            <span />
            <span />
            <span>level</span>
            <span>title</span>
            <span>status</span>
            <span>owner</span>
            <span className="text-right">upd</span>
          </div>

          {filtered.map((g, idx) => {
            const isFocused = idx === focusedIdx;
            const verdict = statusVerdict(g.status);
            const railColor =
              verdict === "block"
                ? "var(--verdict-block)"
                : verdict === "pending"
                  ? "var(--verdict-pending)"
                  : verdict === "attested"
                    ? "var(--verdict-attested)"
                    : "transparent";
            return (
              <div
                key={g.id}
                ref={(el) => {
                  rowRefs.current[idx] = el;
                }}
                onClick={() => {
                  setFocusedIdx(idx);
                  navigate(`/milestones/${g.id}`);
                }}
                onMouseEnter={() => setFocusedIdx(idx)}
                className="group grid h-6 cursor-pointer items-center gap-2 border-b border-border pr-2 text-[12px] transition-colors"
                style={{
                  gridTemplateColumns:
                    "2px 16px 90px minmax(0, 1fr) 90px 90px 56px",
                  background: isFocused ? "var(--surface-2)" : "transparent",
                }}
              >
                {/* Verdict rail */}
                <span
                  aria-hidden
                  className="block h-full"
                  style={{ background: railColor }}
                />
                {/* Glyph */}
                <span className="flex h-full items-center justify-center text-text-tertiary">
                  <Target className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                </span>
                {/* Level */}
                <span className="truncate text-[11px] text-text-tertiary">{g.level}</span>
                {/* Title */}
                <span className="min-w-0 truncate text-foreground">
                  {g.title}
                  {g.description && (
                    <span className="ml-2 text-[10px] text-text-tertiary">
                      {g.description.slice(0, 80)}
                      {g.description.length > 80 ? "…" : ""}
                    </span>
                  )}
                </span>
                {/* Status */}
                <span>
                  <span className="verdict-chip" data-verdict={verdict}>
                    {g.status}
                  </span>
                </span>
                {/* Owner */}
                <span className="truncate text-[11px] text-text-tertiary">
                  {g.ownerAgentId ? `@${g.ownerAgentId.slice(0, 8)}` : "-"}
                </span>
                {/* Updated */}
                <span className="text-right text-[11px] tabular-nums text-text-tertiary">
                  {fmtRelative(g.updatedAt ?? g.createdAt)}
                </span>
              </div>
            );
          })}
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
        <span>n new</span>
        <span>·</span>
        <span>/ filter</span>
        <span className="ml-auto tabular-nums">
          {filtered.length}/{allGoals.length}
        </span>
      </div>
    </div>
  );
}
