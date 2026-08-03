/**
 * Command palette: navigation entries come from `./command-catalog.ts`,
 * and markup maps over `NAV_GROUPS`. Recent-page tracking uses a small
 * dedicated helper.
 */

import { useState, useEffect, useMemo, type ComponentType } from "react";
import { useNavigate, useLocation } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import { useProject } from "../context/ProjectContext";
import { useDialog } from "../context/DialogContext";
import { useSidebar } from "../context/SidebarContext";
import { issuesApi } from "../api/issues";
import { agentsApi } from "../api/agents";
import { subprojectsApi } from "../api/subprojects";
import { queryKeys } from "../lib/queryKeys";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  CircleDot,
  Bot,
  Hexagon,
  Milestone,
  Layers,
  SquarePen,
  Plus,
  ArrowRight,
  Play,
  Eye,
} from "lucide-react";
import { Identity } from "../components/Identity";
import { agentUrl, subprojectUrl } from "../lib/utils";
import { NAV_GROUPS, labelForPath, type CatalogEntry } from "./command-catalog";

// ---------------------------------------------------------------------------
// Recent-pages helper - encapsulates the localStorage interaction.
// ---------------------------------------------------------------------------

const RECENT_STORAGE_KEY = "gitmesh.recentPages";
const MAX_RECENT = 6;

interface RecentPage {
  path: string;
  label: string;
  timestamp: number;
}

const recentPagesStore = {
  read(): RecentPage[] {
    try {
      const raw = localStorage.getItem(RECENT_STORAGE_KEY);
      return raw ? (JSON.parse(raw) as RecentPage[]) : [];
    } catch {
      return [];
    }
  },
  remember(path: string, label: string) {
    try {
      const recent = this.read().filter((p) => p.path !== path);
      recent.unshift({ path, label, timestamp: Date.now() });
      localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
    } catch {
      // ignore
    }
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const { selectedProjectId } = useProject();
  const { openNewIssue, openNewAgent } = useDialog();
  const { isMobile, setSidebarOpen } = useSidebar();
  const searchQuery = query.trim();
  const [recentPages, setRecentPages] = useState<RecentPage[]>([]);
  const currentPath = location.pathname;

  // ⌘K / Ctrl+K toggles palette
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(true);
        if (isMobile) setSidebarOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isMobile, setSidebarOpen]);

  useEffect(() => {
    if (open) setRecentPages(recentPagesStore.read());
    else setQuery("");
  }, [open]);

  const { data: issues = [] } = useQuery({
    queryKey: queryKeys.issues.list(selectedProjectId!),
    queryFn: () => issuesApi.list(selectedProjectId!),
    enabled: !!selectedProjectId && open,
  });

  const { data: searchedIssues = [] } = useQuery({
    queryKey: queryKeys.issues.search(selectedProjectId!, searchQuery),
    queryFn: () => issuesApi.list(selectedProjectId!, { q: searchQuery }),
    enabled: !!selectedProjectId && open && searchQuery.length > 0,
  });

  const { data: agents = [] } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId && open,
  });

  const { data: projects = [] } = useQuery({
    queryKey: queryKeys.subprojects.list(selectedProjectId!),
    queryFn: () => subprojectsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId && open,
  });

  function go(path: string, label?: string) {
    setOpen(false);
    if (label) recentPagesStore.remember(path, label);
    else recentPagesStore.remember(path, labelForPath(path));
    navigate(path);
  }

  const visibleIssues = useMemo(
    () => (searchQuery.length > 0 ? searchedIssues : issues),
    [issues, searchedIssues, searchQuery],
  );

  const contextualCommands = useMemo<CatalogEntry[]>(() => {
    const out: CatalogEntry[] = [];
    if (currentPath.includes("/issues/") && !currentPath.endsWith("/issues")) {
      out.push(
        { path: "/issues", label: "All Issues", icon: CircleDot },
        { path: currentPath, label: "Open in list", icon: Eye },
      );
    }
    if (currentPath.includes("/agents/") && !currentPath.endsWith("/agents")) {
      out.push(
        { path: "/agents/all", label: "All Agents", icon: Bot },
        { path: currentPath, label: "Run agent", icon: Play },
      );
    }
    if (currentPath.includes("/milestones/")) {
      out.push({ path: "/milestones", label: "All Milestones", icon: Milestone });
    }
    if (currentPath.includes("/subprojects/")) {
      out.push({ path: "/subprojects", label: "All Subprojects", icon: Layers });
    }
    return out;
  }, [currentPath]);

  const agentName = (id: string | null) => {
    if (!id) return null;
    return agents.find((a) => a.id === id)?.name ?? null;
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v && isMobile) setSidebarOpen(false);
      }}
    >
      <CommandInput
        placeholder="Search issues, agents, projects..."
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        <CommandGroup heading="Actions">
          <CommandItem
            onSelect={() => {
              setOpen(false);
              openNewIssue();
            }}
          >
            <SquarePen className="mr-2 h-4 w-4" />
            Create new issue
            <span className="ml-auto text-xs text-muted-foreground">C</span>
          </CommandItem>
          <CommandItem
            onSelect={() => {
              setOpen(false);
              openNewAgent();
            }}
          >
            <Plus className="mr-2 h-4 w-4" />
            Create enable agent
          </CommandItem>
        </CommandGroup>

        {recentPages.length > 0 && searchQuery.length === 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Recent">
              {recentPages.map((page) => (
                <CommandItem key={page.path} onSelect={() => go(page.path, page.label)}>
                  <ArrowRight className="mr-2 h-4 w-4 text-muted-foreground" />
                  {page.label}
                  <span className="ml-auto font-mono text-xs text-muted-foreground truncate max-w-[12rem]">
                    {page.path}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        {NAV_GROUPS.map((group) => (
          <CatalogGroupView
            key={group.heading}
            heading={group.heading}
            entries={group.entries}
            withSeparator
            onSelect={go}
          />
        ))}

        {contextualCommands.length > 0 && (
          <CatalogGroupView
            heading="On this page"
            entries={contextualCommands}
            withSeparator
            onSelect={go}
          />
        )}

        {visibleIssues.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Issues">
              {visibleIssues.slice(0, 10).map((issue) => (
                <CommandItem
                  key={issue.id}
                  value={
                    searchQuery.length > 0
                      ? `${searchQuery} ${issue.identifier ?? ""} ${issue.title}`
                      : undefined
                  }
                  onSelect={() => go(`/issues/${issue.identifier ?? issue.id}`)}
                >
                  <CircleDot className="mr-2 h-4 w-4" />
                  <span className="text-muted-foreground mr-2 font-mono text-xs">
                    {issue.identifier ?? issue.id.slice(0, 8)}
                  </span>
                  <span className="flex-1 truncate">{issue.title}</span>
                  {issue.assigneeAgentId &&
                    (() => {
                      const name = agentName(issue.assigneeAgentId);
                      return name ? (
                        <Identity name={name} size="sm" className="ml-2 hidden sm:inline-flex" />
                      ) : null;
                    })()}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        {agents.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Agents">
              {agents.slice(0, 10).map((agent) => (
                <CommandItem key={agent.id} onSelect={() => go(agentUrl(agent))}>
                  <Bot className="mr-2 h-4 w-4" />
                  {agent.name}
                  <span className="text-xs text-muted-foreground ml-2">{agent.role}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}

        {projects.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Projects">
              {projects.slice(0, 10).map((project) => (
                <CommandItem key={project.id} onSelect={() => go(subprojectUrl(project))}>
                  <Hexagon className="mr-2 h-4 w-4" />
                  {project.name}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}

// ---------------------------------------------------------------------------
// Subviews
// ---------------------------------------------------------------------------

function CatalogGroupView({
  heading,
  entries,
  withSeparator,
  onSelect,
}: {
  heading: string;
  entries: CatalogEntry[];
  withSeparator: boolean;
  onSelect: (path: string, label: string) => void;
}) {
  return (
    <>
      {withSeparator && <CommandSeparator />}
      <CommandGroup heading={heading}>
        {entries.map((entry) => {
          const Icon: ComponentType<{ className?: string }> = entry.icon;
          return (
            <CommandItem key={entry.path + ":" + entry.label} onSelect={() => onSelect(entry.path, entry.label)}>
              <Icon className="mr-2 h-4 w-4" />
              {entry.label}
            </CommandItem>
          );
        })}
      </CommandGroup>
    </>
  );
}
