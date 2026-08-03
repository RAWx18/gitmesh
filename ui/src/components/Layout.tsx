/**
 * Layout - main application shell.
 *
 * Structure (left → right):
 *   [GlyphRail 48px]
 *   [MeshSpine 340px - persistent live ledger]
 *   [Main: top context bar + outlet + status footer]
 *
 * The "wide sidebar" pattern is intentionally absent. Sub-navigation lives
 * in the command palette (⌘K) or in-page tabs. The signature is the
 * always-visible event spine - runs, policy verdicts, and attestations
 * stream as a single dense thread.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Moon, Search, Sun, Plus } from "lucide-react";
import { Outlet, useLocation, useNavigate, useParams } from "@/lib/router";
import { GlyphRail } from "./GlyphRail";
import { MeshSpine } from "../features/MeshSpine";
import { Sidebar } from "./Sidebar";
import { ProjectSwitcher } from "./ProjectSwitcher";
import { PropertiesPanel } from "../features/PropertiesPanel";
import { CommandPalette } from "../features/CommandPalette";
import { NewIssueDialog } from "../features/NewIssueDialog";
import { NewSubprojectDialog } from "../features/NewSubprojectDialog";
import { NewMilestoneDialog } from "../features/NewMilestoneDialog";
import { NewAgentDialog } from "../features/NewAgentDialog";
import { ToastViewport } from "./ToastViewport";
import { MobileBottomNav } from "./MobileBottomNav";
import { useDialog } from "../context/DialogContext";
import { usePanel } from "../context/PanelContext";
import { useProject } from "../context/ProjectContext";
import { useSidebar } from "../context/SidebarContext";
import { useTheme } from "../context/ThemeContext";
import { useKeyboardShortcuts } from "../hooks/useKeyboardShortcuts";
import { useProjectPageMemory } from "../hooks/useProjectPageMemory";
import { healthApi } from "../api/health";
import { queryKeys } from "../lib/queryKeys";
import { cn } from "../lib/utils";

const SPINE_VISIBLE_KEY = "gitmesh.spine.visible";

export function Layout() {
  const { sidebarOpen, setSidebarOpen, toggleSidebar, isMobile } = useSidebar();
  const { openNewIssue, openOnboarding } = useDialog();
  const { togglePanelVisible } = usePanel();
  const {
    projects,
    loading: projectsLoading,
    selectedProject,
    selectedProjectId,
    setSelectedProjectId,
  } = useProject();
  const { theme, toggleTheme } = useTheme();
  const { projectPrefix } = useParams<{ projectPrefix: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const onboardingTriggered = useRef(false);
  const lastMainScrollTop = useRef(0);
  const [mobileNavVisible, setMobileNavVisible] = useState(true);
  const [spineVisible, setSpineVisible] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    const stored = window.localStorage.getItem(SPINE_VISIBLE_KEY);
    return stored !== "false";
  });
  const nextTheme = theme === "dark" ? "light" : "dark";
  const { data: health } = useQuery({
    queryKey: queryKeys.health,
    queryFn: () => healthApi.get(),
    retry: false,
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SPINE_VISIBLE_KEY, String(spineVisible));
  }, [spineVisible]);

  useEffect(() => {
    if (projectsLoading || onboardingTriggered.current) return;
    if (projects.length === 0) {
      onboardingTriggered.current = true;
      openOnboarding();
    }
  }, [projects, projectsLoading, openOnboarding]);

  useEffect(() => {
    if (!projectPrefix || projectsLoading || projects.length === 0) return;
    const requestedPrefix = projectPrefix.toUpperCase();
    const matched = projects.find((project) => project.issuePrefix.toUpperCase() === requestedPrefix);
    if (!matched) {
      const fallback =
        (selectedProjectId ? projects.find((project) => project.id === selectedProjectId) : null)
        ?? projects[0]!;
      navigate(`/${fallback.issuePrefix}/dashboard`, { replace: true });
      return;
    }
    if (projectPrefix !== matched.issuePrefix) {
      const suffix = location.pathname.replace(/^\/[^/]+/, "");
      navigate(`/${matched.issuePrefix}${suffix}${location.search}`, { replace: true });
      return;
    }
    if (selectedProjectId !== matched.id) {
      setSelectedProjectId(matched.id, { source: "route_sync" });
    }
  }, [projectPrefix, projects, projectsLoading, location.pathname, location.search, navigate, selectedProjectId, setSelectedProjectId]);

  const togglePanel = togglePanelVisible;

  const switchProject = useCallback(
    (index: number) => {
      if (index < projects.length) {
        setSelectedProjectId(projects[index]!.id);
      }
    },
    [projects, setSelectedProjectId],
  );

  useProjectPageMemory();

  useKeyboardShortcuts({
    onNewIssue: () => openNewIssue(),
    onToggleSidebar: toggleSidebar,
    onTogglePanel: togglePanel,
    onSwitchProject: switchProject,
    onNavigate: (path) => navigate(path),
  });

  useEffect(() => {
    if (!isMobile) {
      setMobileNavVisible(true);
      return;
    }
    lastMainScrollTop.current = 0;
    setMobileNavVisible(true);
  }, [isMobile]);

  const handleMainScroll = useCallback(
    (event: React.UIEvent<HTMLElement>) => {
      if (!isMobile) return;
      const currentTop = event.currentTarget.scrollTop;
      const delta = currentTop - lastMainScrollTop.current;
      if (currentTop <= 24) setMobileNavVisible(true);
      else if (delta > 8) setMobileNavVisible(false);
      else if (delta < -8) setMobileNavVisible(true);
      lastMainScrollTop.current = currentTop;
    },
    [isMobile],
  );

  function openSearch() {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
  }

  const deploymentLabel =
    health?.deploymentMode === "authenticated" ? "authenticated" : "self-managed";
  const repoLabel = selectedProject?.forgeOwner && selectedProject?.forgeRepo
    ? `${selectedProject.forgeOwner}/${selectedProject.forgeRepo}`
    : selectedProject?.repoUrl ?? "no forge linked";
  const apiHealthy = !!health;

  return (
    <div className="gitmesh-shell relative h-dvh overflow-hidden bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[200] focus:rounded-md focus:bg-card focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Skip to Main Content
      </a>

      <div className="relative z-10 flex h-full min-h-0">
        {!isMobile && <GlyphRail />}

        {!isMobile && spineVisible && <MeshSpine />}

        {/* Mobile drawer keeps the legacy Sidebar - phones are too narrow for
            the three-column desktop shell. */}
        {isMobile && sidebarOpen && (
          <button
            type="button"
            className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          />
        )}
        {isMobile && (
          <div
            className={cn(
              "fixed inset-y-0 left-0 z-50 w-full max-w-[340px] transition-transform duration-200 ease-out",
              sidebarOpen ? "translate-x-0" : "-translate-x-full",
            )}
          >
            <Sidebar />
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          {/* Top bar - minimal, mono context */}
          <header className="gitmesh-topnav relative shrink-0 border-b border-border bg-background/85 backdrop-blur-sm">
            <div className="flex items-center gap-3 px-4 py-2.5 md:px-5">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                {!isMobile && <ProjectSwitcher />}
                <span className="hidden h-4 w-px bg-border md:block" />
                {selectedProject && (
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-[0.20em] text-text-tertiary">
                      {selectedProject.issuePrefix}
                    </span>
                    <span className="text-text-tertiary/40">·</span>
                    <span className="truncate font-mono text-[12px] text-foreground">
                      {selectedProject.name}
                    </span>
                  </div>
                )}
              </div>

              <div className="ml-auto flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => openNewIssue()}
                  className="hidden md:inline-flex items-center gap-1.5 border border-border bg-background px-2 py-1 font-mono text-[11px] uppercase tracking-[0.10em] text-text-secondary transition-colors hover:border-[var(--verdict-attested)] hover:text-foreground"
                >
                  <Plus className="h-3 w-3" strokeWidth={1.6} />
                  new
                  <kbd className="ml-1 border border-border px-1 text-[9px] text-text-tertiary">C</kbd>
                </button>

                {!isMobile && (
                  <button
                    type="button"
                    onClick={openSearch}
                    className="hidden md:inline-flex items-center gap-1.5 border border-border bg-background px-2 py-1 font-mono text-[11px] uppercase tracking-[0.10em] text-text-secondary transition-colors hover:border-[var(--verdict-attested)] hover:text-foreground"
                    aria-label="Search"
                  >
                    <Search className="h-3 w-3" strokeWidth={1.6} />
                    find
                    <kbd className="ml-1 border border-border px-1 text-[9px] text-text-tertiary">⌘K</kbd>
                  </button>
                )}

                {!isMobile && (
                  <button
                    type="button"
                    onClick={() => setSpineVisible((v) => !v)}
                    className="hidden md:inline-flex items-center gap-1.5 border border-border bg-background px-2 py-1 font-mono text-[11px] uppercase tracking-[0.10em] text-text-secondary transition-colors hover:border-[var(--verdict-attested)] hover:text-foreground"
                    aria-label={spineVisible ? "Hide spine" : "Show spine"}
                    title={spineVisible ? "Hide event spine" : "Show event spine"}
                  >
                    spine {spineVisible ? "·" : "+"}
                  </button>
                )}

                <button
                  type="button"
                  onClick={toggleTheme}
                  className="inline-flex h-7 w-7 items-center justify-center text-text-secondary transition-colors hover:text-foreground"
                  aria-label={`Switch to ${nextTheme} mode`}
                  title={`Switch to ${nextTheme} mode`}
                >
                  {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          </header>

          <main
            id="main-content"
            tabIndex={-1}
            className={cn(
              "gitmesh-scrollbar relative flex-1 overflow-auto",
              isMobile && "pb-[calc(5rem+env(safe-area-inset-bottom))]",
            )}
            onScroll={handleMainScroll}
          >
            <div className="mx-auto w-full max-w-[1200px] px-4 py-5 md:px-6 md:py-6 lg:px-8">
              <Outlet />
            </div>
          </main>

          {/* Status footer - terminal-style, mono */}
          {!isMobile && (
            <footer className="shrink-0 border-t border-border bg-background/80 px-4 py-1.5 md:px-5">
              <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        apiHealthy ? "bg-[var(--verdict-attested)] gm-pulse-dot" : "bg-[var(--verdict-block)]",
                      )}
                    />
                    {apiHealthy ? "ctrl-plane: live" : "ctrl-plane: offline"}
                  </span>
                  <span className="text-text-tertiary/40">·</span>
                  <span>{deploymentLabel}</span>
                </div>
                <div className="flex items-center gap-3 truncate">
                  <span className="truncate max-w-[24rem] normal-case tracking-normal">{repoLabel}</span>
                </div>
              </div>
            </footer>
          )}
        </div>
      </div>

      {isMobile && <MobileBottomNav visible={mobileNavVisible} />}
      <CommandPalette />
      <PropertiesPanel />
      <NewIssueDialog />
      <NewSubprojectDialog />
      <NewMilestoneDialog />
      <NewAgentDialog />
      <ToastViewport />
    </div>
  );
}
