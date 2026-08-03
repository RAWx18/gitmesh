/**
 * GlyphRail - 48px thin navigation rail.
 *
 * Replaces the wide 224px sidebar pattern common in generic admin UIs.
 * The rail is glyph-only, with hover tooltips. Vocabulary is intentionally
 * GitMesh-specific:
 *
 *   Mesh    - the live forge graph (formerly "Dashboard")
 *   Signal  - items that need attention (formerly "Inbox")
 *   Gate    - approvals (formerly "Approvals")
 *   Issues / PRs / Milestones - work surfaces
 *   Workers - agent fleet (formerly "Agents")
 *   Rules   - policies
 *   Registry- policy + project templates
 *   Ledger  - audit log + attestations
 *   Costs   - cost & budget
 *   Org     - org chart
 *   Settings
 *
 * Sub-navigation lives in a command palette (⌘K) or in-page tabs, not in
 * a vertical encyclopedia rail.
 */
import { NavLink } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import {
  Network,
  Radio,
  ShieldCheck,
  CircleDot,
  GitPullRequest,
  Milestone,
  Bot,
  Scale,
  PackageOpen,
  ScrollText,
  DollarSign,
  GitFork,
  Settings,
  Lock,
} from "lucide-react";
import { useProject } from "../context/ProjectContext";
import { sidebarBadgesApi } from "../api/sidebarBadges";
import { heartbeatsApi } from "../api/heartbeats";
import { queryKeys } from "../lib/queryKeys";
import { cn } from "../lib/utils";

interface GlyphProps {
  to: string;
  label: string;
  Icon: typeof Network;
  badge?: number;
  badgeTone?: "default" | "danger" | "live";
}

function Glyph({ to, label, Icon, badge, badgeTone = "default" }: GlyphProps) {
  return (
    <NavLink to={to} className="block">
      {({ isActive }) => (
        <span
          className="glyph-rail-item"
          data-active={isActive ? "true" : "false"}
          aria-label={label}
          tabIndex={-1}
        >
          <span className="relative flex h-9 w-9 items-center justify-center">
            <Icon className="h-4 w-4" strokeWidth={1.6} />
            {typeof badge === "number" && badge > 0 && (
              <span
                className={cn(
                  "absolute -right-0.5 -top-0.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full px-1 font-mono text-[8px] font-bold leading-none",
                  badgeTone === "danger"
                    ? "bg-[var(--verdict-block)] text-background"
                    : badgeTone === "live"
                    ? "bg-[var(--verdict-attested)] text-background"
                    : "bg-foreground/10 text-foreground",
                )}
              >
                {badge > 99 ? "99+" : badge}
              </span>
            )}
          </span>
          <span className="tooltip">{label}</span>
        </span>
      )}
    </NavLink>
  );
}

function Divider() {
  return <div className="my-2 h-px w-full bg-border/60" role="presentation" />;
}

export function GlyphRail() {
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

  const liveRunCount = liveRuns?.length ?? 0;
  const inboxCount = sidebarBadges?.inbox ?? 0;
  const approvalCount = sidebarBadges?.approvals ?? 0;
  const failedRunCount = sidebarBadges?.failedRuns ?? 0;

  return (
    <aside className="glyph-rail flex h-full w-12 shrink-0 flex-col">
      {/* Brand glyph */}
      <NavLink to="/dashboard" className="block">
        <span className="flex h-12 items-center justify-center border-b border-border">
          <span
            className="font-mono text-[11px] font-bold tracking-tighter"
            style={{ color: "var(--verdict-attested)" }}
            title="GitMesh - Forge Instrumentation"
          >
            GM
          </span>
        </span>
      </NavLink>

      <nav className="flex flex-1 flex-col items-stretch py-1">
        {/* Live: Mesh / Signal / Gate */}
        <Glyph
          to="/dashboard"
          label="Mesh"
          Icon={Network}
          badge={liveRunCount}
          badgeTone={liveRunCount > 0 ? "live" : "default"}
        />
        <Glyph
          to="/inbox"
          label="Signal"
          Icon={Radio}
          badge={inboxCount}
          badgeTone={inboxCount > 0 ? "danger" : "default"}
        />
        <Glyph
          to="/approvals"
          label="Gate"
          Icon={ShieldCheck}
          badge={approvalCount}
          badgeTone={approvalCount > 0 ? "danger" : "default"}
        />

        <Divider />

        {/* Work surfaces */}
        <Glyph to="/issues" label="Issues" Icon={CircleDot} />
        <Glyph to="/prs" label="Pull requests" Icon={GitPullRequest} />
        <Glyph to="/milestones" label="Milestones" Icon={Milestone} />

        <Divider />

        {/* Workers (agents) */}
        <Glyph
          to="/agents/all"
          label="Workers"
          Icon={Bot}
          badge={failedRunCount}
          badgeTone={failedRunCount > 0 ? "danger" : "default"}
        />

        <Divider />

        {/* Governance + audit */}
        <Glyph to="/policies" label="Rules" Icon={Scale} />
        <Glyph to="/templates" label="Registry" Icon={PackageOpen} />
        <Glyph to="/audit" label="Ledger" Icon={ScrollText} />

        <Divider />

        {/* Ops */}
        <Glyph to="/costs" label="Costs" Icon={DollarSign} />
        <Glyph to="/org" label="Org" Icon={GitFork} />
        <Glyph to="/secrets" label="Secrets" Icon={Lock} />
      </nav>

      <NavLink to="/project/settings" className="block">
        <span className="glyph-rail-item border-t border-border">
          <span className="flex h-9 w-9 items-center justify-center">
            <Settings className="h-4 w-4" strokeWidth={1.6} />
          </span>
          <span className="tooltip">Settings</span>
        </span>
      </NavLink>
    </aside>
  );
}
