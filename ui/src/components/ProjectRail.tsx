import { useCallback, useEffect, useMemo, useState } from "react";
import { Workflow, Plus } from "lucide-react";
import { useQueries } from "@tanstack/react-query";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useProject } from "../context/ProjectContext";
import { useDialog } from "../context/DialogContext";
import { cn } from "../lib/utils";
import { queryKeys } from "../lib/queryKeys";
import { sidebarBadgesApi } from "../api/sidebarBadges";
import { heartbeatsApi } from "../api/heartbeats";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Project } from "@gitmesh/core";
import { ProjectPatternIcon } from "./ProjectPatternIcon";

const ORDER_STORAGE_KEY = "gitmesh-agents.projectOrder";

function getStoredOrder(): string[] {
  try {
    const raw = localStorage.getItem(ORDER_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return [];
}

function saveOrder(ids: string[]) {
  localStorage.setItem(ORDER_STORAGE_KEY, JSON.stringify(ids));
}

/** Sort projects by stored order, appending any new ones at the end. */
function sortByStoredOrder(projects: Project[]): Project[] {
  const order = getStoredOrder();
  if (order.length === 0) return projects;

  const byId = new Map(projects.map((c) => [c.id, c]));
  const sorted: Project[] = [];

  for (const id of order) {
    const c = byId.get(id);
    if (c) {
      sorted.push(c);
      byId.delete(id);
    }
  }
  // Append any projects not in stored order
  for (const c of byId.values()) {
    sorted.push(c);
  }
  return sorted;
}

function SortableProjectItem({
  project,
  isSelected,
  hasLiveAgents,
  hasUnreadInbox,
  onSelect,
}: {
  project: Project;
  isSelected: boolean;
  hasLiveAgents: boolean;
  hasUnreadInbox: boolean;
  onSelect: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: project.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 10 : undefined,
    opacity: isDragging ? 0.8 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners} className="overflow-visible">
      <Tooltip delayDuration={300}>
        <TooltipTrigger asChild>
          <a
            href={`/${project.issuePrefix}/dashboard`}
            onClick={(e) => {
              e.preventDefault();
              onSelect();
            }}
            className="relative flex items-center justify-center group overflow-visible"
          >
            {/* Selection indicator pill */}
            <div
              className={cn(
                "absolute left-[-14px] w-1 rounded-r-full bg-foreground transition-[height] duration-150",
                isSelected
                  ? "h-5"
                  : "h-0 group-hover:h-2"
              )}
            />
            <div
              className={cn("relative overflow-visible transition-transform duration-150", isDragging && "scale-105")}
            >
              <ProjectPatternIcon
                projectName={project.name}
                brandColor={project.brandColor}
                className={cn(
                  isSelected
                    ? "rounded-[14px]"
                    : "rounded-[22px] group-hover:rounded-[14px]",
                  isDragging && "shadow-lg",
                )}
              />
              {hasLiveAgents && (
                <span className="pointer-events-none absolute -right-0.5 -top-0.5 z-10">
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-80" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-500 ring-2 ring-background" />
                  </span>
                </span>
              )}
              {hasUnreadInbox && (
                <span className="pointer-events-none absolute -bottom-0.5 -right-0.5 z-10 h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-background" />
              )}
            </div>
          </a>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          <p>{project.name}</p>
        </TooltipContent>
      </Tooltip>
    </div>
  );
}

export function ProjectRail() {
  const { projects, selectedProjectId, setSelectedProjectId } = useProject();
  const { openOnboarding } = useDialog();
  const sidebarProjects = useMemo(
    () => projects.filter((project) => project.status !== "archived"),
    [projects],
  );
  const projectIds = useMemo(() => sidebarProjects.map((project) => project.id), [sidebarProjects]);

  const liveRunsQueries = useQueries({
    queries: projectIds.map((projectId) => ({
      queryKey: queryKeys.liveRuns(projectId),
      queryFn: () => heartbeatsApi.liveRunsForProject(projectId),
      refetchInterval: 10_000,
    })),
  });
  const sidebarBadgeQueries = useQueries({
    queries: projectIds.map((projectId) => ({
      queryKey: queryKeys.sidebarBadges(projectId),
      queryFn: () => sidebarBadgesApi.get(projectId),
      refetchInterval: 15_000,
    })),
  });
  const hasLiveAgentsByProjectId = useMemo(() => {
    const result = new Map<string, boolean>();
    projectIds.forEach((projectId, index) => {
      result.set(projectId, (liveRunsQueries[index]?.data?.length ?? 0) > 0);
    });
    return result;
  }, [projectIds, liveRunsQueries]);
  const hasUnreadInboxByProjectId = useMemo(() => {
    const result = new Map<string, boolean>();
    projectIds.forEach((projectId, index) => {
      result.set(projectId, (sidebarBadgeQueries[index]?.data?.inbox ?? 0) > 0);
    });
    return result;
  }, [projectIds, sidebarBadgeQueries]);

  // Maintain sorted order in local state, synced from projects + localStorage
  const [orderedIds, setOrderedIds] = useState<string[]>(() =>
    sortByStoredOrder(sidebarProjects).map((c) => c.id)
  );

  // Re-sync orderedIds from localStorage whenever projects changes.
  // Handles initial data load (projects starts as [] before query resolves)
  // and subsequent refetches triggered by live updates.
  useEffect(() => {
    if (sidebarProjects.length === 0) {
      setOrderedIds([]);
      return;
    }
    setOrderedIds(sortByStoredOrder(sidebarProjects).map((c) => c.id));
  }, [sidebarProjects]);

  // Sync order across tabs via the native storage event
  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key !== ORDER_STORAGE_KEY) return;
      try {
        const ids: string[] = e.newValue ? JSON.parse(e.newValue) : [];
        setOrderedIds(ids);
      } catch { /* ignore malformed data */ }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  // Re-derive when projects change (new project added/removed)
  const orderedProjects = useMemo(() => {
    const byId = new Map(sidebarProjects.map((c) => [c.id, c]));
    const result: Project[] = [];
    for (const id of orderedIds) {
      const c = byId.get(id);
      if (c) {
        result.push(c);
        byId.delete(id);
      }
    }
    // Append any new projects not yet in our order
    for (const c of byId.values()) {
      result.push(c);
    }
    return result;
  }, [sidebarProjects, orderedIds]);

  // Require 8px of movement before starting a drag to avoid interfering with clicks
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    })
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const ids = orderedProjects.map((c) => c.id);
      const oldIndex = ids.indexOf(active.id as string);
      const newIndex = ids.indexOf(over.id as string);
      if (oldIndex === -1 || newIndex === -1) return;

      const newIds = arrayMove(ids, oldIndex, newIndex);
      setOrderedIds(newIds);
      saveOrder(newIds);
    },
    [orderedProjects]
  );

  return (
    <div className="flex flex-col items-center w-[72px] shrink-0 h-full bg-sidebar border-r border-sidebar-border">
      {/* GitMesh icon - brand mark */}
      <div className="flex items-center justify-center h-12 w-full shrink-0 border-b border-sidebar-border">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-primary/10">
          <Workflow className="h-5 w-5 text-primary" />
        </div>
      </div>

      {/* Project list */}
      <div className="flex-1 flex flex-col items-center gap-2 py-3 w-full overflow-y-auto overflow-x-hidden scrollbar-none">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={orderedProjects.map((c) => c.id)}
            strategy={verticalListSortingStrategy}
          >
            {orderedProjects.map((project) => (
              <SortableProjectItem
                key={project.id}
                project={project}
                isSelected={project.id === selectedProjectId}
                hasLiveAgents={hasLiveAgentsByProjectId.get(project.id) ?? false}
                hasUnreadInbox={hasUnreadInboxByProjectId.get(project.id) ?? false}
                onSelect={() => setSelectedProjectId(project.id)}
              />
            ))}
          </SortableContext>
        </DndContext>
      </div>

      {/* Separator before add button */}
      <div className="w-8 h-px bg-border mx-auto shrink-0" />

      {/* Add project button */}
      <div className="flex items-center justify-center py-2 shrink-0">
        <Tooltip delayDuration={300}>
          <TooltipTrigger asChild>
            <button
              onClick={() => openOnboarding()}
              className="flex items-center justify-center w-11 h-11 rounded-[22px] hover:rounded-[14px] border-2 border-dashed border-primary/30 text-primary/60 hover:border-primary/60 hover:text-primary transition-[border-color,color,border-radius] duration-150"
              aria-label="Add project"
            >
              <Plus className="h-5 w-5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            <p>Add project</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
