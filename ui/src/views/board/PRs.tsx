import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import { pullRequestsApi } from "../../api/pull-requests";
import { useProject } from "../../context/ProjectContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { queryKeys } from "../../lib/queryKeys";
import { GitPullRequest } from "lucide-react";
import type { PullRequestStatus } from "../../api/pull-requests";

type Tab = "open" | "merged" | "closed" | "all";

const TABS: { value: Tab; label: string }[] = [
  { value: "open", label: "is:open" },
  { value: "merged", label: "is:merged" },
  { value: "closed", label: "is:closed" },
  { value: "all", label: "is:all" },
];

type Verdict = "block" | "pending" | "attested" | "none";

function statusVerdict(status: PullRequestStatus): Verdict {
  if (status === "merged") return "attested";
  if (status === "open") return "pending";
  if (status === "closed") return "block";
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

export function PRs() {
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const statusParam = (searchParams.get("status") ?? "open") as Tab;
  const statusFilter: Tab = TABS.find((t) => t.value === statusParam)?.value ?? "open";

  const [filterText, setFilterText] = useState("");
  const [focusedIdx, setFocusedIdx] = useState(0);
  const filterInputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    setBreadcrumbs([{ label: "Pull Requests" }]);
  }, [setBreadcrumbs]);

  const { data: prs, isLoading, error } = useQuery({
    queryKey: queryKeys.pullRequests.list(selectedProjectId!, statusFilter),
    queryFn: () => pullRequestsApi.list(selectedProjectId!, { status: statusFilter }),
    enabled: !!selectedProjectId,
  });

  const allPrs = prs ?? [];

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    let r = allPrs.slice();
    if (q) {
      r = r.filter((p) => {
        const blob = [
          p.title,
          p.identifier ?? "",
          p.forgePrNumber ? `!${p.forgePrNumber}` : "",
          p.status,
          p.authorAgentId ?? "",
          p.authorUserId ?? "",
          ...(p.labels ?? []).map((l) => l.name),
        ]
          .join(" ")
          .toLowerCase();
        return blob.includes(q);
      });
    }
    r.sort((a, b) => {
      const ta = new Date(a.updatedAt ?? a.createdAt).getTime();
      const tb = new Date(b.updatedAt ?? b.createdAt).getTime();
      return tb - ta;
    });
    return r;
  }, [allPrs, filterText]);

  const setStatus = useCallback(
    (next: Tab) => {
      const params = new URLSearchParams(searchParams);
      if (next === "open") params.delete("status");
      else params.set("status", next);
      setSearchParams(params, { replace: true });
      setFocusedIdx(0);
    },
    [searchParams, setSearchParams],
  );

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
        const pr = filtered[focusedIdx];
        if (pr) navigate(`/prs/${pr.id}`);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filtered, focusedIdx, navigate]);

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
        select a project to view pull requests
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
          prs
          <span className="ml-2 tabular-nums text-text-tertiary">· {allPrs.length}</span>
          {filtered.length !== allPrs.length && (
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
        {TABS.map((tab) => {
          const active = statusFilter === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              onClick={() => setStatus(tab.value)}
              className="rounded-sm px-2 py-0.5 text-[11px] tracking-tight transition-colors"
              style={{
                border: active ? "1px solid var(--verdict-attested)" : "1px solid transparent",
                color: active ? "var(--verdict-attested)" : "var(--text-tertiary)",
                background: "transparent",
              }}
            >
              {tab.label}
            </button>
          );
        })}
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
          loading pull requests …
        </div>
      ) : filtered.length === 0 ? (
        <div
          className="py-12 text-center text-xs text-text-tertiary"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {filterText
            ? "no prs match - try a different filter"
            : statusFilter === "open"
              ? "no open pull requests"
              : `no ${statusFilter} pull requests`}
        </div>
      ) : (
        <div className="flex flex-col">
          {/* Column header row */}
          <div
            className="grid h-6 items-center gap-2 border-b border-border pl-0 pr-2 text-[10px] uppercase tracking-[0.18em] text-text-tertiary"
            style={{
              gridTemplateColumns:
                "2px 16px 80px minmax(0, 1fr) 90px 100px 56px",
            }}
          >
            <span />
            <span />
            <span>id</span>
            <span>title</span>
            <span>status</span>
            <span>author</span>
            <span className="text-right">upd</span>
          </div>

          {filtered.map((pr, idx) => {
            const isFocused = idx === focusedIdx;
            const verdict = statusVerdict(pr.status);
            const railColor =
              verdict === "block"
                ? "var(--verdict-block)"
                : verdict === "pending"
                  ? "var(--verdict-pending)"
                  : verdict === "attested"
                    ? "var(--verdict-attested)"
                    : "transparent";
            const idStr = pr.forgePrNumber
              ? `!${pr.forgePrNumber}`
              : pr.identifier
                ? `#${pr.identifier.replace(/^[^#]+-?/, "")}`
                : pr.id.slice(0, 6);
            const author =
              pr.authorAgentId
                ? `@${pr.authorAgentId.slice(0, 8)}`
                : pr.authorUserId
                  ? pr.authorUserId === "local-board"
                    ? "@maintainer"
                    : `@${pr.authorUserId.slice(0, 10)}`
                  : "-";
            return (
              <div
                key={pr.id}
                ref={(el) => {
                  rowRefs.current[idx] = el;
                }}
                onClick={() => {
                  setFocusedIdx(idx);
                  navigate(`/prs/${pr.id}`);
                }}
                onMouseEnter={() => setFocusedIdx(idx)}
                className="group grid h-6 cursor-pointer items-center gap-2 border-b border-border pr-2 text-[12px] transition-colors"
                style={{
                  gridTemplateColumns:
                    "2px 16px 80px minmax(0, 1fr) 90px 100px 56px",
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
                  <GitPullRequest className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                </span>
                {/* ID */}
                <span className="truncate text-[11px] tabular-nums text-text-tertiary">
                  {idStr}
                </span>
                {/* Title */}
                <span className="min-w-0 truncate text-foreground">
                  {pr.title}
                  {(pr.labels ?? []).length > 0 && (
                    <span className="ml-2 text-[10px] text-text-tertiary">
                      {(pr.labels ?? [])
                        .slice(0, 2)
                        .map((l) => `#${l.name}`)
                        .join(" ")}
                      {(pr.labels ?? []).length > 2
                        ? ` +${(pr.labels ?? []).length - 2}`
                        : ""}
                    </span>
                  )}
                </span>
                {/* Status */}
                <span>
                  <span className="verdict-chip" data-verdict={verdict}>
                    {pr.status}
                  </span>
                </span>
                {/* Author */}
                <span className="truncate text-[11px] text-text-tertiary">{author}</span>
                {/* Updated */}
                <span className="text-right text-[11px] tabular-nums text-text-tertiary">
                  {fmtRelative(pr.updatedAt ?? pr.createdAt)}
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
        <span>/ filter</span>
        <span className="ml-auto tabular-nums">
          {filtered.length}/{allPrs.length}
        </span>
      </div>
    </div>
  );
}

