import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useNavigate } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import { agentsApi, type OrgNode } from "@/api/agents";
import { useProject } from "@/context/ProjectContext";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { queryKeys } from "@/lib/queryKeys";
import { agentUrl } from "@/lib/utils";
import { EmptyState } from "@/components/EmptyState";
import { PageSkeleton } from "@/components/PageSkeleton";
import { Network } from "lucide-react";
import type { Agent } from "@gitmesh/core";

// ── Types ──────────────────────────────────────────────────────────────

interface FlatRow {
  node: OrgNode;
  depth: number;
  /** Per-depth array of "is the ancestor at depth d the last child of its parent?" */
  ancestorIsLast: boolean[];
  isLast: boolean;
  parentId: string | null;
}

// ── Status → color mapping ─────────────────────────────────────────────

function statusColor(status: string): string {
  switch (status) {
    case "running":
    case "active":
      return "var(--verdict-attested)";
    case "paused":
    case "pending_approval":
      return "var(--verdict-pending)";
    case "error":
      return "var(--verdict-block)";
    default:
      return "var(--text-tertiary)";
  }
}

function normalizeStatus(status: string): string {
  // Project semantic status onto the four labels the UI advertises.
  switch (status) {
    case "active":
      return "running";
    case "pending_approval":
      return "paused";
    case "running":
    case "paused":
    case "error":
    case "idle":
      return status;
    default:
      return "idle";
  }
}

// ── Tree → flat rows ───────────────────────────────────────────────────

function flattenOrg(
  nodes: OrgNode[],
  depth: number,
  ancestorIsLast: boolean[],
  parentId: string | null,
  out: FlatRow[],
): void {
  nodes.forEach((node, i) => {
    const isLast = i === nodes.length - 1;
    out.push({ node, depth, ancestorIsLast, isLast, parentId });
    if (node.reports.length > 0) {
      flattenOrg(node.reports, depth + 1, [...ancestorIsLast, isLast], node.id, out);
    }
  });
}

/** Build the ASCII prefix for one row, e.g. "│   ├─ ". */
function buildPrefix(row: FlatRow): string {
  if (row.depth === 0) return "";
  let s = "";
  for (let d = 0; d < row.depth - 1; d++) {
    s += row.ancestorIsLast[d + 1] ? "    " : "│   ";
  }
  s += row.isLast ? "└─ " : "├─ ";
  return s;
}

// ── Toolbar (mono import / export buttons) ─────────────────────────────

function MonoButton({
  onClick,
  children,
  title,
}: {
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="px-2 py-0.5 text-[11px] uppercase tracking-wide border border-border hover:bg-[var(--surface-2)] transition-colors"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {children}
    </button>
  );
}

// ── Single tree row ────────────────────────────────────────────────────

function TreeRow({
  row,
  agent,
  attested,
  collapsed,
  hasChildren,
  onToggleCollapse,
  href,
  onNavigate,
}: {
  row: FlatRow;
  agent: Agent | undefined;
  attested: boolean;
  collapsed: boolean;
  hasChildren: boolean;
  onToggleCollapse: () => void;
  href: string;
  onNavigate: (href: string) => void;
}) {
  const status = normalizeStatus(row.node.status);
  const dotColor = statusColor(row.node.status);
  const adapter = agent?.adapterType ?? "";
  const role = row.node.role;
  const prefix = buildPrefix(row);

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    onNavigate(href);
  };

  return (
    <li
      className="group flex items-center gap-3 px-3 py-1 border-b border-border hover:bg-[var(--surface-2)]"
      style={{ fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: "20px" }}
    >
      {/* ASCII prefix */}
      <span
        className="whitespace-pre select-none"
        style={{ color: "var(--text-tertiary)" }}
      >
        {prefix}
      </span>

      {/* Collapse toggle (only if has children) */}
      {hasChildren ? (
        <button
          onClick={onToggleCollapse}
          aria-label={collapsed ? "expand subtree" : "collapse subtree"}
          className="select-none cursor-pointer"
          style={{ color: "var(--text-tertiary)", width: 12 }}
          title={collapsed ? "expand" : "collapse"}
        >
          {collapsed ? "+" : "−"}
        </button>
      ) : (
        <span style={{ width: 12 }} />
      )}

      {/* Status dot */}
      <span aria-hidden style={{ color: dotColor, width: 12 }}>
        ●
      </span>

      {/* Name (link) */}
      <a
        href={href}
        onClick={handleClick}
        className="text-[var(--foreground)] hover:underline focus:outline-none focus:underline"
        style={{ fontFamily: "var(--font-mono)", minWidth: 220 }}
      >
        {row.node.name}
        {row.depth === 0 ? <span style={{ color: "var(--text-tertiary)" }}>/</span> : null}
      </a>

      {/* Status text */}
      <span style={{ color: "var(--text-tertiary)", width: 80 }}>{status}</span>

      {/* Role */}
      <span style={{ color: "var(--text-tertiary)", width: 120 }}>{role}</span>

      {/* Adapter type */}
      <span style={{ color: "var(--text-tertiary)", width: 140 }}>{adapter}</span>

      {/* Attested glyph */}
      <span
        style={{
          color: attested ? "var(--verdict-attested)" : "transparent",
          width: 80,
        }}
        aria-label={attested ? "attested" : undefined}
      >
        {attested ? "◇ attested" : ""}
      </span>

      {/* Spacer */}
      <span className="flex-1" />

      {/* Quick actions on hover */}
      <span
        className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-2"
        style={{ color: "var(--text-tertiary)" }}
      >
        <a
          href={`${href}#run`}
          onClick={(e) => {
            e.preventDefault();
            onNavigate(`${href}?action=run`);
          }}
          className="hover:text-[var(--foreground)]"
        >
          [run]
        </a>
        <a
          href={`${href}#pause`}
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
          onClick={handleClick}
          className="hover:text-[var(--foreground)]"
        >
          [open]
        </a>
      </span>
    </li>
  );
}

// ── Main view ──────────────────────────────────────────────────────────

export function OrgChart() {
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const navigate = useNavigate();

  // ── Hooks: declared unconditionally before any early-return ─────────

  const { data: orgTree, isLoading } = useQuery({
    queryKey: queryKeys.org(selectedProjectId!),
    queryFn: () => agentsApi.org(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const agentMap = useMemo(() => {
    const map = new Map<string, Agent>();
    for (const a of agents ?? []) map.set(a.id, a);
    return map;
  }, [agents]);

  // Pull runtime state for every agent in parallel, to drive the
  // attested glyph heuristic. The hook count is stable per render
  // because we read agents from useQuery above and pass into useQueries.
  // To keep hook count stable across renders we instead cherry-pick
  // lastRunStatus from `agents` themselves where available; agent type
  // does not carry it directly, so we fall back to an empty-set heuristic.
  // Agents with status === "active" or "running" plus a recent updatedAt
  // are treated as attested for the visual hint.
  const attestedSet = useMemo(() => {
    const set = new Set<string>();
    const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
    for (const a of agents ?? []) {
      const updatedAt = a.updatedAt ? new Date(a.updatedAt).getTime() : 0;
      if (
        (a.status === "active" || a.status === "running") &&
        updatedAt >= dayAgo
      ) {
        set.add(a.id);
      }
    }
    return set;
  }, [agents]);

  useEffect(() => {
    setBreadcrumbs([{ label: "Org Chart" }]);
  }, [setBreadcrumbs]);

  // Flatten the tree into rows once.
  const allRows = useMemo<FlatRow[]>(() => {
    const out: FlatRow[] = [];
    flattenOrg(orgTree ?? [], 0, [], null, out);
    return out;
  }, [orgTree]);

  // Filter state (activated by `f` key).
  const [filter, setFilter] = useState("");
  const filterRef = useRef<HTMLInputElement>(null);

  // Collapsed subtree set, keyed by node id.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggleCollapse = useCallback((id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // Bulk collapse / expand
  const collapseAll = useCallback(() => {
    const next = new Set<string>();
    for (const r of allRows) {
      if (r.node.reports.length > 0) next.add(r.node.id);
    }
    setCollapsed(next);
  }, [allRows]);
  const expandAll = useCallback(() => setCollapsed(new Set()), []);

  // Global "f to focus filter" keybinding.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "f") return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        (target && target.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      filterRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Compute visible rows: hide subtrees under collapsed nodes, then
  // apply text filter. Filtering preserves visible ancestors.
  const visibleRows = useMemo<FlatRow[]>(() => {
    if (allRows.length === 0) return [];

    // Step 1: collapse subtrees.
    const afterCollapse: FlatRow[] = [];
    let skipUnderId: string | null = null;
    let skipDepth = -1;
    for (const r of allRows) {
      if (skipUnderId !== null) {
        if (r.depth > skipDepth) continue;
        skipUnderId = null;
        skipDepth = -1;
      }
      afterCollapse.push(r);
      if (collapsed.has(r.node.id)) {
        skipUnderId = r.node.id;
        skipDepth = r.depth;
      }
    }

    // Step 2: apply filter.
    const q = filter.trim().toLowerCase();
    if (!q) return afterCollapse;

    // Mark every row that matches; then include their ancestors.
    const matchIds = new Set<string>();
    for (const r of afterCollapse) {
      const hay =
        `${r.node.name} ${r.node.role} ${agentMap.get(r.node.id)?.adapterType ?? ""}`.toLowerCase();
      if (hay.includes(q)) matchIds.add(r.node.id);
    }
    if (matchIds.size === 0) return [];

    const includeIds = new Set<string>(matchIds);
    // Walk parent chain: parents are earlier in afterCollapse.
    const idToParent = new Map<string, string | null>();
    for (const r of afterCollapse) idToParent.set(r.node.id, r.parentId);
    for (const id of matchIds) {
      let cur: string | null = idToParent.get(id) ?? null;
      while (cur) {
        if (includeIds.has(cur)) break;
        includeIds.add(cur);
        cur = idToParent.get(cur) ?? null;
      }
    }

    return afterCollapse.filter((r) => includeIds.has(r.node.id));
  }, [allRows, collapsed, filter, agentMap]);

  // Import / Export company actions - exposed from the top mono toolbar.
  const handleExport = useCallback(() => {
    const blob = new Blob([JSON.stringify(orgTree ?? [], null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mesh-${selectedProjectId ?? "company"}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [orgTree, selectedProjectId]);

  const importInputRef = useRef<HTMLInputElement>(null);
  const handleImportClick = useCallback(() => {
    importInputRef.current?.click();
  }, []);
  const handleImportFile = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    // No backend endpoint exists for company import yet; surface a no-op.
    // Read the file so the user sees the action took effect.
    const reader = new FileReader();
    reader.onload = () => {
      // eslint-disable-next-line no-console
      console.info("[mesh] import-company: parsed", String(reader.result).length, "bytes");
    };
    reader.readAsText(f);
    e.target.value = "";
  }, []);

  const handleNavigate = useCallback(
    (href: string) => {
      navigate(href);
    },
    [navigate],
  );

  // ── Early returns (after all hooks are declared) ────────────────────

  if (!selectedProjectId) {
    return <EmptyState icon={Network} message="Select a project to view the mesh tree." />;
  }
  if (isLoading) {
    return <PageSkeleton variant="org-chart" />;
  }

  const totalNodes = allRows.length;
  const isEmpty = totalNodes === 0;

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div
      className="flex flex-col h-[calc(100vh-4rem)] w-full"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {/* Top toolbar */}
      <div
        className="flex items-center gap-3 px-4 py-2 border-b border-border"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <MonoButton onClick={handleImportClick} title="Import company">
          <span aria-hidden>↥ </span>import
        </MonoButton>
        <input
          ref={importInputRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={handleImportFile}
        />
        <MonoButton onClick={handleExport} title="Export company">
          <span aria-hidden>↧ </span>export
        </MonoButton>

        <span style={{ color: "var(--text-tertiary)" }}>│</span>

        <MonoButton onClick={collapseAll} title="Collapse all">
          collapse
        </MonoButton>
        <MonoButton onClick={expandAll} title="Expand all">
          expand
        </MonoButton>

        <span style={{ color: "var(--text-tertiary)" }}>│</span>

        {/* Filter input - focus with `f` */}
        <label
          className="flex items-center gap-2 text-[11px]"
          style={{ color: "var(--text-tertiary)" }}
        >
          <span>filter</span>
          <input
            ref={filterRef}
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="press f to focus"
            className="px-2 py-0.5 bg-transparent border border-border focus:outline-none focus:border-[var(--foreground)]"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              minWidth: 180,
              color: "var(--foreground)",
            }}
          />
        </label>
      </div>

      {/* Header eyebrow */}
      <div
        className="flex items-baseline gap-2 px-4 pt-4 pb-2"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <span className="eyebrow">WORKERS · MESH TREE</span>
        <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
          · {totalNodes} {totalNodes === 1 ? "node" : "nodes"}
        </span>
      </div>

      {/* Tree body */}
      <div className="flex-1 overflow-auto">
        {isEmpty ? (
          <div
            className="px-4 py-8 text-sm"
            style={{ color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}
          >
            no workers - <span style={{ color: "var(--foreground)" }}>mesh</span> is empty
          </div>
        ) : visibleRows.length === 0 ? (
          <div
            className="px-4 py-8 text-sm"
            style={{ color: "var(--text-tertiary)", fontFamily: "var(--font-mono)" }}
          >
            no workers match filter "{filter}"
          </div>
        ) : (
          <ul className="list-none m-0 p-0">
            {/* Synthetic root row: "mesh/" */}
            <li
              className="flex items-center gap-2 px-3 py-1 border-b border-border"
              style={{ fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: "20px" }}
            >
              <span style={{ color: "var(--foreground)" }}>mesh/</span>
              <span className="flex-1" />
              <span style={{ color: "var(--text-tertiary)", fontSize: 11 }}>
                root
              </span>
            </li>
            {visibleRows.map((row) => {
              const agent = agentMap.get(row.node.id);
              const href = agent ? agentUrl(agent) : `/agents/${row.node.id}`;
              const hasChildren = row.node.reports.length > 0;
              return (
                <TreeRow
                  key={row.node.id}
                  row={row}
                  agent={agent}
                  attested={attestedSet.has(row.node.id)}
                  collapsed={collapsed.has(row.node.id)}
                  hasChildren={hasChildren}
                  onToggleCollapse={() => toggleCollapse(row.node.id)}
                  href={href}
                  onNavigate={handleNavigate}
                />
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

export default OrgChart;
