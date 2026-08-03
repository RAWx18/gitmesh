import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import { subprojectsApi } from "../../api/subprojects";
import { useProject } from "../../context/ProjectContext";
import { useDialog } from "../../context/DialogContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { subprojectUrl } from "../../lib/utils";
import { Hexagon } from "lucide-react";
import type { Subproject } from "@gitmesh/core";

type Verdict = "block" | "pending" | "attested" | "none";

function statusVerdict(status: string): Verdict {
  const s = status.toLowerCase();
  if (s === "completed" || s === "shipped" || s === "done") return "attested";
  if (s === "active" || s === "in_progress" || s === "started") return "pending";
  if (s === "archived" || s === "cancelled" || s === "blocked") return "block";
  return "none";
}

function fmtTargetDate(d: string | null | undefined): string {
  if (!d) return "-";
  const t = new Date(d).getTime();
  if (Number.isNaN(t)) return "-";
  const diff = t - Date.now();
  const days = Math.round(diff / 86400000);
  if (days === 0) return "today";
  if (days > 0) return days < 30 ? `+${days}d` : days < 365 ? `+${Math.round(days / 30)}mo` : `+${Math.round(days / 365)}y`;
  const ago = -days;
  return ago < 30 ? `-${ago}d` : ago < 365 ? `-${Math.round(ago / 30)}mo` : `-${Math.round(ago / 365)}y`;
}

export function Subprojects() {
  const { selectedProjectId } = useProject();
  const { openNewSubproject } = useDialog();
  const { setBreadcrumbs } = useBreadcrumbs();
  const navigate = useNavigate();

  const [filterText, setFilterText] = useState("");
  const [focusedIdx, setFocusedIdx] = useState(0);
  const filterInputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    setBreadcrumbs([{ label: "Subprojects" }]);
  }, [setBreadcrumbs]);

  const { data: projects, isLoading, error } = useQuery({
    queryKey: queryKeys.subprojects.list(selectedProjectId!),
    queryFn: () => subprojectsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const allProjects: Subproject[] = projects ?? [];

  const filtered = useMemo(() => {
    let r = allProjects.slice();
    const q = filterText.trim().toLowerCase();
    if (q) {
      r = r.filter((p) =>
        [p.name, p.description ?? "", p.status, p.urlKey ?? ""]
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    r.sort((a, b) => {
      const ta = new Date(a.updatedAt ?? a.createdAt).getTime();
      const tb = new Date(b.updatedAt ?? b.createdAt).getTime();
      return tb - ta;
    });
    return r;
  }, [allProjects, filterText]);

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

      if (e.key === "n") {
        e.preventDefault();
        openNewSubproject();
        return;
      }
      if (filtered.length === 0) return;

      if (e.key === "j") {
        e.preventDefault();
        setFocusedIdx((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === "k") {
        e.preventDefault();
        setFocusedIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const p = filtered[focusedIdx];
        if (p) navigate(subprojectUrl(p));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filtered, focusedIdx, navigate, openNewSubproject]);

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
        select a project to view subprojects
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
          subprojects
          <span className="ml-2 tabular-nums text-text-tertiary">· {allProjects.length}</span>
          {filtered.length !== allProjects.length && (
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

      {/* Action row */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={openNewSubproject}
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
          loading subprojects …
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-xs text-text-tertiary">
          {allProjects.length === 0
            ? "no subprojects - press n to add"
            : "no subprojects match - try a different filter"}
        </div>
      ) : (
        <div className="flex flex-col">
          {/* Column header row */}
          <div
            className="grid h-6 items-center gap-2 border-b border-border pl-0 pr-2 text-[10px] uppercase tracking-[0.18em] text-text-tertiary"
            style={{
              gridTemplateColumns:
                "2px 16px minmax(0, 1fr) 90px 90px 70px",
            }}
          >
            <span />
            <span />
            <span>name</span>
            <span>status</span>
            <span>lead</span>
            <span className="text-right">target</span>
          </div>

          {filtered.map((p, idx) => {
            const isFocused = idx === focusedIdx;
            const verdict = statusVerdict(p.status);
            const railColor =
              verdict === "block"
                ? "var(--verdict-block)"
                : verdict === "pending"
                  ? "var(--verdict-pending)"
                  : verdict === "attested"
                    ? "var(--verdict-attested)"
                    : p.color
                      ? p.color
                      : "transparent";
            return (
              <div
                key={p.id}
                ref={(el) => {
                  rowRefs.current[idx] = el;
                }}
                onClick={() => {
                  setFocusedIdx(idx);
                  navigate(subprojectUrl(p));
                }}
                onMouseEnter={() => setFocusedIdx(idx)}
                className="group grid h-6 cursor-pointer items-center gap-2 border-b border-border pr-2 text-[12px] transition-colors"
                style={{
                  gridTemplateColumns:
                    "2px 16px minmax(0, 1fr) 90px 90px 70px",
                  background: isFocused ? "var(--surface-2)" : "transparent",
                }}
              >
                {/* Verdict / color rail */}
                <span
                  aria-hidden
                  className="block h-full"
                  style={{ background: railColor }}
                />
                {/* Glyph */}
                <span className="flex h-full items-center justify-center text-text-tertiary">
                  <Hexagon className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                </span>
                {/* Name + description */}
                <span className="min-w-0 truncate text-foreground">
                  {p.name}
                  {p.description && (
                    <span className="ml-2 text-[10px] text-text-tertiary">
                      {p.description.slice(0, 80)}
                      {p.description.length > 80 ? "…" : ""}
                    </span>
                  )}
                </span>
                {/* Status */}
                <span>
                  <span className="verdict-chip" data-verdict={verdict}>
                    {p.status}
                  </span>
                </span>
                {/* Lead */}
                <span className="truncate text-[11px] text-text-tertiary">
                  {p.leadAgentId ? `@${p.leadAgentId.slice(0, 8)}` : "-"}
                </span>
                {/* Target */}
                <span className="text-right text-[11px] tabular-nums text-text-tertiary">
                  {fmtTargetDate(p.targetDate)}
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
          {filtered.length}/{allProjects.length}
        </span>
      </div>
    </div>
  );
}
