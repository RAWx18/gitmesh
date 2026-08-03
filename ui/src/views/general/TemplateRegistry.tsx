import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  Terminal,
  Package2,
  Server,
  Cloud,
  User,
  Tags,
  GitPullRequest,
  FileText,
  Shield,
  MessagesSquare,
  UserPlus,
  Rocket,
  Bot,
  CircleSmall,
} from "lucide-react";
import { useProject } from "../../context/ProjectContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { api } from "../../api/client";

interface Template {
  id: string;
  name: string;
  description: string | null;
  archetype: string;
  agents: Array<{
    role: string;
    name: string;
    schedule?: string;
    triggers?: string[];
    budget: number;
  }>;
  policies: Array<{
    name: string;
    actionPattern: string;
    effect: string;
  }>;
  version: string;
  authorId: string | null;
  communityContributed: boolean;
  featured: boolean;
  downloadCount: number;
  createdAt: string;
}

const ARCHETYPE_STYLES: Record<string, { label: string; key: string; Icon: LucideIcon }> = {
  cli_tool: { label: "cli", key: "cli_tool", Icon: Terminal },
  js_library: { label: "lib", key: "js_library", Icon: Package2 },
  infrastructure: { label: "infra", key: "infrastructure", Icon: Server },
  cncf_sandbox: { label: "cncf", key: "cncf_sandbox", Icon: Cloud },
  solo_maintainer: { label: "solo", key: "solo_maintainer", Icon: User },
};

const ROLE_ICONS: Record<string, LucideIcon> = {
  triage: Tags,
  pr_review: GitPullRequest,
  docs: FileText,
  security: Shield,
  community: MessagesSquare,
  onboarding: UserPlus,
  release: Rocket,
  general: Bot,
};

function archetypeGlyph(archetype: string): string {
  switch (archetype) {
    case "cli_tool":
      return "$_";
    case "js_library":
      return "{}";
    case "infrastructure":
      return "[]";
    case "cncf_sandbox":
      return "<>";
    case "solo_maintainer":
      return "@";
    default:
      return "·";
  }
}

export function TemplateRegistry() {
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const queryClient = useQueryClient();

  const [filterText, setFilterText] = useState("");
  const [archetypeFilter, setArchetypeFilter] = useState<string | null>(null);
  const [focusedIdx, setFocusedIdx] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const filterInputRef = useRef<HTMLInputElement | null>(null);
  const rowRefs = useRef<Array<HTMLDivElement | null>>([]);

  useEffect(() => {
    setBreadcrumbs([{ label: "Template Registry" }]);
  }, [setBreadcrumbs]);

  const { data: templates, isLoading, error } = useQuery<Template[]>({
    queryKey: ["templates"],
    queryFn: async () => {
      const res = await api.get<Template[]>("/templates");
      return res;
    },
  });

  const applyMutation = useMutation({
    mutationFn: async (templateId: string) => {
      const res = await api.post<{ agentsCreated: number; policiesCreated: number }>(
        `/projects/${selectedProjectId}/apply-template/${templateId}`,
        {},
      );
      return res;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      alert(`Template applied! Created ${data.agentsCreated} agents and ${data.policiesCreated} policies.`);
    },
  });

  const allTemplates = templates ?? [];

  const filtered = useMemo(() => {
    let r = allTemplates.slice();
    if (archetypeFilter) {
      r = r.filter((t) => t.archetype === archetypeFilter);
    }
    const q = filterText.trim().toLowerCase();
    if (q) {
      r = r.filter((t) =>
        [
          t.name,
          t.description ?? "",
          t.archetype,
          t.version,
          ...(t.agents ?? []).map((a) => a.role),
        ]
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    // Featured first, then download count desc
    r.sort((a, b) => {
      if (a.featured !== b.featured) return a.featured ? -1 : 1;
      return (b.downloadCount ?? 0) - (a.downloadCount ?? 0);
    });
    return r;
  }, [allTemplates, archetypeFilter, filterText]);

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
        const t = filtered[focusedIdx];
        if (t && selectedProjectId && !applyMutation.isPending) {
          applyMutation.mutate(t.id);
        }
      } else if (e.key === " " || e.key === "x") {
        e.preventDefault();
        const t = filtered[focusedIdx];
        if (t) setExpandedId((cur) => (cur === t.id ? null : t.id));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filtered, focusedIdx, applyMutation, selectedProjectId]);

  useEffect(() => {
    if (focusedIdx >= filtered.length) {
      setFocusedIdx(Math.max(0, filtered.length - 1));
    }
  }, [filtered.length, focusedIdx]);

  useEffect(() => {
    rowRefs.current[focusedIdx]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focusedIdx]);

  const ARCHETYPE_KEYS = Object.keys(ARCHETYPE_STYLES);

  return (
    <div
      className="flex flex-col gap-3 pb-12"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {/* Header strip */}
      <div className="flex h-8 items-center justify-between border-b border-border">
        <span className="text-sm tracking-tight text-foreground">
          registry
          <span className="ml-2 tabular-nums text-text-tertiary">
            · {allTemplates.length} templates
          </span>
          {filtered.length !== allTemplates.length && (
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

      {/* Category pill bar */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setArchetypeFilter(null)}
          className="rounded-sm px-2 py-0.5 text-[11px] tracking-tight transition-colors"
          style={{
            border: !archetypeFilter ? "1px solid var(--verdict-attested)" : "1px solid transparent",
            color: !archetypeFilter ? "var(--verdict-attested)" : "var(--text-tertiary)",
            background: "transparent",
          }}
        >
          all
        </button>
        {ARCHETYPE_KEYS.map((key) => {
          const arch = ARCHETYPE_STYLES[key];
          const active = archetypeFilter === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setArchetypeFilter(active ? null : key)}
              className="rounded-sm px-2 py-0.5 text-[11px] tracking-tight transition-colors"
              style={{
                border: active ? "1px solid var(--verdict-attested)" : "1px solid transparent",
                color: active ? "var(--verdict-attested)" : "var(--text-tertiary)",
                background: "transparent",
              }}
            >
              {arch.label}
            </button>
          );
        })}
      </div>

      {/* Errors */}
      {error && (
        <div className="text-xs" style={{ color: "var(--verdict-block)" }}>
          failed to load templates: {(error as Error).message}
        </div>
      )}

      {/* Body */}
      {isLoading ? (
        <div className="py-12 text-center text-xs text-text-tertiary">
          loading templates …
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-xs text-text-tertiary">
          {allTemplates.length === 0
            ? "no templates available yet"
            : "no templates match - try a different filter"}
        </div>
      ) : (
        <div className="flex flex-col">
          {filtered.map((template, idx) => {
            const isFocused = idx === focusedIdx;
            const isExpanded = expandedId === template.id;
            const arch = ARCHETYPE_STYLES[template.archetype];
            const archLabel = arch?.label ?? template.archetype;
            const glyph = archetypeGlyph(template.archetype);
            const author =
              template.authorId
                ? `@${template.authorId.slice(0, 10)}`
                : template.communityContributed
                  ? "@community"
                  : "@core";
            const canDeploy = !!selectedProjectId && !applyMutation.isPending;

            return (
              <div
                key={template.id}
                ref={(el) => {
                  rowRefs.current[idx] = el;
                }}
                onMouseEnter={() => setFocusedIdx(idx)}
                className="flex flex-col border-b border-border transition-colors"
                style={{ background: isFocused ? "var(--surface-2)" : "transparent" }}
              >
                {/* Primary row: 24px, two-column */}
                <div
                  className="grid h-6 cursor-pointer items-center gap-2 pr-2 text-[12px]"
                  style={{
                    gridTemplateColumns: "2px 24px minmax(0, 1fr) auto",
                  }}
                  onClick={() =>
                    setExpandedId((cur) => (cur === template.id ? null : template.id))
                  }
                >
                  {/* Featured rail */}
                  <span
                    aria-hidden
                    className="block h-full"
                    style={{
                      background: template.featured
                        ? "var(--verdict-attested)"
                        : "transparent",
                    }}
                  />
                  {/* Glyph */}
                  <span className="flex h-full items-center justify-center text-[11px] tabular-nums text-text-tertiary">
                    {glyph}
                  </span>
                  {/* One-liner */}
                  <span className="min-w-0 truncate text-foreground">
                    <span>{template.name}</span>
                    <span className="ml-2 text-[11px] text-text-tertiary">
                      · v{template.version}
                    </span>
                    <span className="ml-1 text-[11px] text-text-tertiary">· {archLabel}</span>
                    <span className="ml-1 text-[11px] text-text-tertiary">· {author}</span>
                    <span className="ml-1 text-[11px] tabular-nums text-text-tertiary">
                      · {template.agents.length} agents
                    </span>
                    <span className="ml-1 text-[11px] tabular-nums text-text-tertiary">
                      · {template.policies.length} policies
                    </span>
                    {template.featured && (
                      <span
                        className="ml-2 text-[10px]"
                        style={{ color: "var(--verdict-attested)" }}
                      >
                        ★
                      </span>
                    )}
                  </span>
                  {/* Action */}
                  <button
                    type="button"
                    disabled={!canDeploy}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (canDeploy) applyMutation.mutate(template.id);
                    }}
                    className="rounded-sm px-2 py-0.5 text-[11px] tracking-tight transition-colors disabled:opacity-40"
                    style={{
                      border: "1px solid transparent",
                      color: "var(--verdict-attested)",
                      background: "transparent",
                    }}
                  >
                    [install →]
                  </button>
                </div>

                {/* Description line */}
                {template.description && (
                  <div
                    className="grid h-5 items-center gap-2 pr-2 text-[11px]"
                    style={{
                      gridTemplateColumns: "2px 24px minmax(0, 1fr)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <span />
                    <span />
                    <span className="min-w-0 truncate">
                      {template.description.slice(0, 120)}
                      {template.description.length > 120 ? "…" : ""}
                    </span>
                  </div>
                )}

                {/* Hover/expanded micro-summary */}
                {isExpanded && (
                  <div
                    className="grid items-start gap-2 border-t border-dashed border-border py-1 pr-2 text-[11px]"
                    style={{
                      gridTemplateColumns: "2px 24px minmax(0, 1fr)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <span />
                    <span />
                    <div className="flex min-w-0 flex-col gap-1">
                      {template.agents.length > 0 && (
                        <div className="flex min-w-0 flex-wrap items-center gap-1">
                          <span className="text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
                            agents
                          </span>
                          {template.agents.map((a, i) => {
                            const RoleIcon = ROLE_ICONS[a.role] ?? CircleSmall;
                            return (
                              <span
                                key={i}
                                className="inline-flex items-center gap-1 rounded-sm px-1 text-text-tertiary"
                                title={a.name}
                              >
                                <RoleIcon
                                  className="h-3 w-3"
                                  strokeWidth={1.75}
                                  aria-hidden
                                />
                                <span>{a.role.replace(/_/g, "-")}</span>
                              </span>
                            );
                          })}
                        </div>
                      )}
                      {template.policies.length > 0 && (
                        <div className="flex min-w-0 flex-wrap items-center gap-1">
                          <span className="text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
                            policies
                          </span>
                          {template.policies.map((p, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1 rounded-sm px-1 text-text-tertiary"
                              title={`${p.actionPattern} → ${p.effect}`}
                            >
                              <span>{p.name}</span>
                              <span style={{ color: "var(--text-tertiary)" }}>
                                ({p.effect})
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex items-center gap-3 text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
                        <span>downloads · {template.downloadCount}</span>
                        {template.communityContributed && <span>community</span>}
                      </div>
                    </div>
                  </div>
                )}
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
        <span>↵ install</span>
        <span>·</span>
        <span>x expand</span>
        <span>·</span>
        <span>/ filter</span>
        <span className="ml-auto tabular-nums">
          {filtered.length}/{allTemplates.length}
        </span>
      </div>
    </div>
  );
}
