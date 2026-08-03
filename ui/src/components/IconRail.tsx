import { NavLink } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard,
  CircleDot,
  Bot,
  Inbox,
  Settings,
  Plus,
  Milestone,
  Layers,
  DollarSign,
  Shield,
  Package,
  Lock,
  ImageIcon,
  ScrollText,
  Users,
  GitPullRequest,
} from "lucide-react";
import { useDialog } from "../context/DialogContext";
import { useProject } from "../context/ProjectContext";
import { sidebarBadgesApi } from "../api/sidebarBadges";
import { heartbeatsApi } from "../api/heartbeats";
import { agentsApi } from "../api/agents";
import { queryKeys } from "../lib/queryKeys";
import { cn } from "../lib/utils";
import { ProjectSwitcher } from "./ProjectSwitcher";

interface NavItemProps {
  to: string;
  icon?: typeof LayoutDashboard;
  label: string;
  badge?: number;
  badgeTone?: "default" | "danger";
  liveCount?: number;
  isSubItem?: boolean;
}

function NavItem({ to, icon: Icon, label, badge, badgeTone = "default", liveCount, isSubItem = false }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors",
          isSubItem ? "pl-8 text-[12px]" : "",
          isActive
            ? "bg-surface-3 text-foreground"
            : "text-text-secondary hover:bg-surface-2 hover:text-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Left rule for active state */}
          {isActive && (
            <span className="absolute inset-y-1 left-0 w-[2px] rounded-r-full bg-primary" />
          )}
          {Icon && (
            <Icon
              className={cn("h-4 w-4 shrink-0", isActive && "text-primary")}
              strokeWidth={1.6}
            />
          )}
          <span className="flex-1 truncate">{label}</span>

          {liveCount != null && liveCount > 0 && (
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-success gm-pulse-dot" />
              <span className="font-mono text-[10px] text-success">{liveCount}</span>
            </span>
          )}

          {badge != null && badge > 0 && (
            <span
              className={cn(
                "flex h-4 min-w-[18px] items-center justify-center rounded-full px-1 font-mono text-[9px] font-semibold leading-none",
                badgeTone === "danger"
                  ? "bg-destructive/15 text-destructive"
                  : "bg-primary/15 text-primary",
              )}
            >
              {badge > 99 ? "99+" : badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

function NavDivider() {
  return <div className="mx-3 my-2 h-px shrink-0 bg-border" role="presentation" />;
}

export function IconRail() {
  const { openNewIssue } = useDialog();
  const { selectedProjectId } = useProject();

  const { data: sidebarBadges } = useQuery({
    queryKey: queryKeys.sidebarBadges(selectedProjectId!),
    queryFn: () => sidebarBadgesApi.get(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: liveRuns } = useQuery({
    queryKey: queryKeys.liveRuns(selectedProjectId!),
    queryFn: () => heartbeatsApi.liveRunsForProject(selectedProjectId!),
    enabled: !!selectedProjectId,
    refetchInterval: 10_000,
  });

  const { data: agents = [] } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const liveRunCount = liveRuns?.length ?? 0;
  const inboxCount = sidebarBadges?.inbox ?? 0;
  const approvalCount = sidebarBadges?.approvals ?? 0;

  const agentCounts = {
    all: agents.length,
    active: liveRunCount,
    paused: 0,
    error: sidebarBadges?.failedRuns ?? 0,
  };

  return (
    <aside className="flex h-full w-[224px] shrink-0 flex-col overflow-hidden border-r border-border bg-sidebar">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 py-3.5 border-b border-border">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <span className="font-mono text-[11px] font-bold tracking-tight">GM</span>
        </div>
        <div className="flex min-w-0 flex-col leading-tight">
          <span className="text-sm font-semibold text-foreground">GitMesh</span>
          <span className="font-mono text-[9px] uppercase tracking-[0.20em] text-text-tertiary">
            Control Plane
          </span>
        </div>
      </div>

      {/* Project switcher */}
      <div className="px-3 py-3 border-b border-border">
        <ProjectSwitcher />
      </div>

      {/* Primary CTA */}
      <div className="px-3 pt-3">
        <button
          type="button"
          onClick={(e) => { e.preventDefault(); openNewIssue(); }}
          className="flex w-full items-center justify-between rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-[13px] font-medium text-foreground transition-colors hover:border-border-strong hover:bg-surface-3"
        >
          <span className="flex items-center gap-2">
            <Plus className="h-3.5 w-3.5" strokeWidth={2} />
            New Issue
          </span>
          <kbd className="rounded border border-border bg-surface-3 px-1 font-mono text-[9px] text-text-tertiary">
            C
          </kbd>
        </button>
      </div>

      {/* Nav - flat list; dividers only (no section labels) */}
      <nav className="gitmesh-scrollbar flex flex-col gap-px px-2 py-2 flex-1 overflow-y-auto">
          <NavItem to="/dashboard" icon={LayoutDashboard} label="Dashboard" liveCount={liveRunCount} />
          <NavItem
            to="/inbox"
            icon={Inbox}
            label="Inbox"
            badge={inboxCount}
            badgeTone={inboxCount > 0 ? "danger" : "default"}
          />
          <NavItem
            to="/approvals"
            icon={Shield}
            label="Approvals"
            badge={approvalCount}
            badgeTone={approvalCount > 0 ? "danger" : "default"}
          />

          <NavDivider />

          <NavItem to="/issues" icon={CircleDot} label="Issues" />
          <NavItem to="/prs" icon={GitPullRequest} label="Pull requests" />
          <NavItem to="/milestones" icon={Milestone} label="Milestones" />
          <NavItem to="/subprojects" icon={Layers} label="Subprojects" />

          <NavDivider />

          <NavItem to="/agents/all" icon={Bot} label="Agents" badge={agentCounts.all} />
          <NavItem to="/agents/active" label="Active" isSubItem badge={agentCounts.active} />
          <NavItem to="/agents/paused" label="Paused" isSubItem badge={agentCounts.paused} />
          <NavItem to="/agents/error" label="Error" isSubItem badge={agentCounts.error} badgeTone={agentCounts.error > 0 ? "danger" : "default"} />

          <NavDivider />

          <NavItem to="/policies" icon={Shield} label="Policies" />
          <NavItem to="/templates" icon={Package} label="Templates" />
          <NavItem to="/secrets" icon={Lock} label="Secrets" />
          <NavItem to="/assets" icon={ImageIcon} label="Assets" />
          <NavItem to="/audit" icon={ScrollText} label="Audit log" />
          <NavItem to="/costs" icon={DollarSign} label="Costs" />

          <NavDivider />

          <NavItem to="/org" icon={Users} label="Org chart" />
          <NavItem to="/project/settings" icon={Settings} label="Project settings" />
          <NavItem to="/instance-settings" icon={Settings} label="Instance" />
      </nav>
    </aside>
  );
}
