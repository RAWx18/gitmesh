import { useMemo } from "react";
import { NavLink, useLocation } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import {
  House,
  CircleDot,
  Users,
  Inbox,
} from "lucide-react";
import { sidebarBadgesApi } from "../api/sidebarBadges";
import { useProject } from "../context/ProjectContext";
import { useDialog } from "../context/DialogContext";
import { queryKeys } from "../lib/queryKeys";
import { cn } from "../lib/utils";

interface MobileBottomNavProps {
  visible: boolean;
}

interface MobileNavLinkItem {
  type: "link";
  to: string;
  label: string;
  icon: typeof House;
  badge?: number;
}

type MobileNavItem = MobileNavLinkItem;

export function MobileBottomNav({ visible }: MobileBottomNavProps) {
  const location = useLocation();
  const { selectedProjectId } = useProject();
  const { openNewIssue } = useDialog();

  const { data: sidebarBadges } = useQuery({
    queryKey: queryKeys.sidebarBadges(selectedProjectId!),
    queryFn: () => sidebarBadgesApi.get(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const items = useMemo<MobileNavItem[]>(
    () => [
      { type: "link", to: "/dashboard", label: "Home", icon: House },
      { type: "link", to: "/issues", label: "Issues", icon: CircleDot },
      { type: "link", to: "/agents/all", label: "Agents", icon: Users },
      {
        type: "link",
        to: "/inbox",
        label: "Inbox",
        icon: Inbox,
        badge: sidebarBadges?.inbox,
      },
    ],
    [sidebarBadges?.inbox],
  );

  const isNewIssueActive = /\/issues\/new(?:\/|$)/.test(location.pathname);

  return (
    <>
      {/* Floating Action Button */}
      <button
        type="button"
        onClick={() => openNewIssue()}
        className={cn(
          "fixed right-4 z-30 flex items-center justify-center w-14 h-14 rounded-full bg-primary text-primary-foreground shadow-3 transition-all duration-200 md:hidden active:scale-95",
          visible ? "bottom-[calc(4.5rem+env(safe-area-inset-bottom))]" : "bottom-6",
          isNewIssueActive && "ring-2 ring-primary/50 ring-offset-2 ring-offset-background",
        )}
        aria-label="New Issue"
      >
        <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>

      {/* Bottom tab bar - 4 columns */}
      <nav
        className={cn(
          "fixed bottom-0 left-0 right-0 z-30 border-t border-border bg-card/90 backdrop-blur-lg supports-[backdrop-filter]:bg-card/80 transition-transform duration-200 ease-out md:hidden pb-[env(safe-area-inset-bottom)]",
          visible ? "translate-y-0" : "translate-y-full",
        )}
        aria-label="Mobile navigation"
      >
        <div className="grid h-14 grid-cols-4 px-2">
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.label}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "relative flex min-w-0 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors",
                    isActive
                      ? "text-primary"
                      : "text-muted-foreground",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {/* Active indicator dot */}
                    {isActive && (
                      <span className="absolute top-1 w-1 h-1 rounded-full bg-primary" />
                    )}
                    <span className="relative mt-1">
                      <Icon className={cn("h-[18px] w-[18px]", isActive && "stroke-[2.5]")} />
                      {item.badge != null && item.badge > 0 && (
                        <span className="absolute -right-2.5 -top-1.5 min-w-[14px] text-center rounded-full bg-red-500 px-1 py-0.5 text-[8px] font-bold leading-none text-white">
                          {item.badge > 99 ? "99+" : item.badge}
                        </span>
                      )}
                    </span>
                    <span className="truncate">{item.label}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </div>
      </nav>
    </>
  );
}
