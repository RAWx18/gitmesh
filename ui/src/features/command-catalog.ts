/**
 * Static command palette catalog.
 *
 * Navigation entries live in a declarative table - each palette item is a
 * single object, and grouping is data, not template branches.
 */

import type { ComponentType } from "react";
import {
  CircleDot,
  Bot,
  LayoutDashboard,
  Inbox,
  DollarSign,
  Milestone,
  Layers,
  ScrollText,
  Shield,
  Package,
  Lock,
  ImageIcon,
  Users,
  Settings,
} from "lucide-react";

export interface CatalogEntry {
  path: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

export interface CatalogGroup {
  heading: string;
  entries: CatalogEntry[];
}

export const NAV_GROUPS: CatalogGroup[] = [
  {
    heading: "Navigation",
    entries: [
      { path: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { path: "/issues", label: "Issues", icon: CircleDot },
      { path: "/agents/all", label: "Agents", icon: Bot },
      { path: "/inbox", label: "Inbox", icon: Inbox },
      { path: "/org", label: "Org Chart", icon: Users },
    ],
  },
  {
    heading: "Project",
    entries: [
      { path: "/milestones", label: "Milestones", icon: Milestone },
      { path: "/subprojects", label: "Subprojects", icon: Layers },
      { path: "/approvals", label: "Approvals", icon: Shield },
      { path: "/costs", label: "Costs", icon: DollarSign },
    ],
  },
  {
    heading: "Configure",
    entries: [
      { path: "/project/settings", label: "Project Settings", icon: Settings },
      { path: "/policies", label: "Policies", icon: Shield },
      { path: "/templates", label: "Templates", icon: Package },
      { path: "/secrets", label: "Secrets", icon: Lock },
      { path: "/assets", label: "Assets", icon: ImageIcon },
      { path: "/audit", label: "Audit Log", icon: ScrollText },
      { path: "/instance-settings", label: "Instance Settings", icon: Settings },
    ],
  },
];

/**
 * Derive a label for an arbitrary path - used for "recent pages" tracking.
 * Uses the catalog as the source of truth for static routes; dynamic
 * detail pages get a generic label.
 */
const STATIC_PATH_LABELS: Record<string, string> = (() => {
  const out: Record<string, string> = {};
  for (const group of NAV_GROUPS) {
    for (const entry of group.entries) {
      out[entry.path] = entry.label;
    }
  }
  return out;
})();

const DYNAMIC_LABELS: Array<[RegExp, string]> = [
  [/\/issues\//, "Issue detail"],
  [/\/agents\//, "Agent detail"],
  [/\/milestones\//, "Milestone detail"],
  [/\/subprojects\//, "Subproject detail"],
  [/\/approvals\//, "Approval detail"],
];

export function labelForPath(path: string): string {
  if (STATIC_PATH_LABELS[path]) return STATIC_PATH_LABELS[path];
  for (const [re, label] of DYNAMIC_LABELS) {
    if (re.test(path)) return label;
  }
  return path.split("/").filter(Boolean).pop() ?? path;
}
