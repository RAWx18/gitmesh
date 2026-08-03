/**
 * Projects view: `usePagedResource` owns list / stats / inline-rename /
 * delete lifecycle; this file renders from that hook’s data bag.
 */

import { useEffect } from "react";
import { useProject } from "../../context/ProjectContext";
import { useDialog } from "../../context/DialogContext";
import { useBreadcrumbs } from "../../context/BreadcrumbContext";
import { projectsApi } from "../../api/projects-api";
import { queryKeys } from "../../lib/queryKeys";
import { usePagedResource } from "../../hooks/usePagedResource";
import { formatCents, relativeTime } from "../../lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Pencil,
  Check,
  X,
  Plus,
  MoreHorizontal,
  Trash2,
  Users,
  CircleDot,
  DollarSign,
  Calendar,
} from "lucide-react";

type ProjectStatsRow = { agentCount: number; issueCount: number };
type ProjectStatsMap = Record<string, ProjectStatsRow>;

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "active"
      ? "bg-green-500/10 text-green-600 dark:text-green-400"
      : status === "paused"
        ? "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400"
        : "bg-muted text-muted-foreground";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>
      {status}
    </span>
  );
}

export function Projects() {
  const {
    projects,
    selectedProjectId,
    setSelectedProjectId,
    loading: projectsLoading,
    error: projectsError,
  } = useProject();
  const { openOnboarding } = useDialog();
  const { setBreadcrumbs } = useBreadcrumbs();

  // The list itself is owned by `useProject()`; we only use the resource
  // hook for stats + inline edit/delete state. The `listKey` here is the
  // canonical projects key - `usePagedResource` will invalidate it after
  // mutations (which prompts `useProject()` to refetch).
  // The list itself is owned by `useProject()`; we only use the resource
  // hook for stats + inline edit/delete state. `listEnabled: false` keeps
  // the query inert here - the canonical key is still used for cache
  // invalidation after rename/delete, which fans out to ProjectContext.
  const resource = usePagedResource<never, ProjectStatsMap>({
    listKey: queryKeys.projects.all,
    listEnabled: false,
    listFn: () => Promise.resolve([]),
    statsKey: queryKeys.projects.stats,
    statsFn: () => projectsApi.stats() as Promise<ProjectStatsMap>,
    renameFn: ({ id, name }) => projectsApi.update(id, { name }),
    removeFn: (id) => projectsApi.remove(id),
    extraInvalidate: [queryKeys.projects.stats],
  });

  useEffect(() => {
    setBreadcrumbs([{ label: "Projects" }]);
  }, [setBreadcrumbs]);

  const stats = resource.stats;

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between gap-6 border-b border-border pb-6">
        <div>
          <p className="eyebrow mb-3">Workspace</p>
          <h1 className="text-4xl font-semibold tracking-tight text-foreground md:text-5xl">Projects</h1>
          <p className="mt-2 max-w-xl text-sm text-text-secondary">
            Each project scopes its own agents, policies, budgets, and forge connection.
          </p>
        </div>
        <Button size="sm" onClick={() => openOnboarding()}>
          <Plus className="h-3.5 w-3.5" />
          New Project
        </Button>
      </header>

      <div className="h-6">
        {projectsLoading && <p className="text-sm text-text-tertiary">Loading projects…</p>}
        {projectsError && <p className="text-sm text-destructive">{projectsError.message}</p>}
      </div>

      <div className="grid gap-3">
        {projects.map((project) => {
          const selected = project.id === selectedProjectId;
          const isEditing = resource.editingId === project.id;
          const isConfirmingDelete = resource.confirmingDeleteId === project.id;
          const row = stats?.[project.id];
          const agentCount = row?.agentCount ?? 0;
          const issueCount = row?.issueCount ?? 0;
          const budgetPct =
            project.budgetMonthlyCents > 0
              ? Math.round((project.spentMonthlyCents / project.budgetMonthlyCents) * 100)
              : 0;

          return (
            <div
              key={project.id}
              role="button"
              tabIndex={0}
              onClick={() => setSelectedProjectId(project.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelectedProjectId(project.id);
                }
              }}
              className={`group relative text-left bg-card border rounded-md p-5 transition-colors cursor-pointer ${
                selected ? "border-border-strong" : "border-border hover:border-border-strong"
              }`}
            >
              {selected && (
                <span aria-hidden className="absolute inset-y-2 left-0 w-[2px] rounded-r-full bg-primary" />
              )}

              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  {isEditing ? (
                    <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                      <Input
                        value={resource.editValue}
                        onChange={(e) => resource.changeEditValue(e.target.value)}
                        className="h-7 text-sm"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === "Enter") resource.commitEdit();
                          if (e.key === "Escape") resource.cancelEdit();
                        }}
                      />
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={resource.commitEdit}
                        disabled={resource.isEditPending}
                        aria-label="Save"
                      >
                        <Check className="h-3.5 w-3.5 text-green-500" />
                      </Button>
                      <Button variant="ghost" size="icon-xs" onClick={resource.cancelEdit} aria-label="Cancel">
                        <X className="h-3.5 w-3.5 text-muted-foreground" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-base">{project.name}</h3>
                      <StatusPill status={project.status} />
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        className="text-muted-foreground opacity-0 group-hover:opacity-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          resource.beginEdit(project.id, project.name);
                        }}
                        aria-label="Rename"
                      >
                        <Pencil className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                  {project.description && !isEditing && (
                    <p className="text-sm text-muted-foreground mt-1 line-clamp-2">{project.description}</p>
                  )}
                </div>

                <div onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        className="text-muted-foreground opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100"
                        aria-label="Project actions"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => resource.beginEdit(project.id, project.name)}>
                        <Pencil className="h-3.5 w-3.5" />
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" onClick={() => resource.beginDelete(project.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                        Delete Project
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>

              <div className="flex items-center gap-3 sm:gap-5 mt-4 text-sm text-muted-foreground flex-wrap">
                <div className="flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5" />
                  <span>
                    {agentCount} {agentCount === 1 ? "agent" : "agents"}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CircleDot className="h-3.5 w-3.5" />
                  <span>
                    {issueCount} {issueCount === 1 ? "issue" : "issues"}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <DollarSign className="h-3.5 w-3.5" />
                  <span>
                    {formatCents(project.spentMonthlyCents)}
                    {project.budgetMonthlyCents > 0 ? (
                      <>
                        {" "}/ {formatCents(project.budgetMonthlyCents)}{" "}
                        <span className="text-xs">({budgetPct}%)</span>
                      </>
                    ) : (
                      <span className="text-xs ml-1">Unlimited budget</span>
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 ml-auto">
                  <Calendar className="h-3.5 w-3.5" />
                  <span>Created {relativeTime(project.createdAt)}</span>
                </div>
              </div>

              {isConfirmingDelete && (
                <div
                  className="mt-4 flex items-center justify-between bg-destructive/5 border border-destructive/20 rounded-md px-4 py-3"
                  onClick={(e) => e.stopPropagation()}
                >
                  <p className="text-sm text-destructive font-medium">
                    Delete this project and all its data? This cannot be undone.
                  </p>
                  <div className="flex items-center gap-2 ml-4 shrink-0">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={resource.cancelDelete}
                      disabled={resource.isDeletePending}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={resource.confirmDelete}
                      disabled={resource.isDeletePending}
                    >
                      {resource.isDeletePending ? "Deleting…" : "Delete"}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
