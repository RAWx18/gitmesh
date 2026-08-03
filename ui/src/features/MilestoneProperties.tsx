/**
 * Milestone properties as a small declarative table: each row is a
 * descriptor; the renderer walks the table.
 */

import { useState, type ReactNode } from "react";
import { Link } from "@/lib/router";
import { useQuery } from "@tanstack/react-query";
import type { Goal } from "@gitmesh/core";
import { GOAL_STATUSES, GOAL_LEVELS } from "@gitmesh/core";
import { agentsApi } from "../api/agents";
import { milestonesApi } from "../api/milestones";
import { useProject } from "../context/ProjectContext";
import { queryKeys } from "../lib/queryKeys";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate, cn, agentUrl } from "../lib/utils";
import { Separator } from "@/components/ui/separator";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";

interface MilestonePropertiesProps {
  milestone: Goal;
  onUpdate?: (data: Record<string, unknown>) => void;
}

function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

interface PropertyRow {
  label: string;
  /** Render the read-only display node */
  render: () => ReactNode;
  /** Optional editable picker - when both `onUpdate` and this are present, the row is editable */
  picker?: {
    options: readonly string[];
    current: string;
    onChange: (next: string) => void;
    /** override how each option is rendered in the popover */
    renderOption?: (opt: string) => ReactNode;
  };
}

export function MilestoneProperties({ milestone, onUpdate }: MilestonePropertiesProps) {
  const { selectedProjectId } = useProject();

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const { data: allGoals } = useQuery({
    queryKey: queryKeys.milestones.list(selectedProjectId!),
    queryFn: () => milestonesApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  const ownerAgent = milestone.ownerAgentId
    ? agents?.find((a) => a.id === milestone.ownerAgentId)
    : null;

  const parentGoal = milestone.parentId ? allGoals?.find((g) => g.id === milestone.parentId) : null;

  const editableRows: PropertyRow[] = [
    {
      label: "Status",
      render: () => <StatusBadge status={milestone.status} />,
      picker: onUpdate
        ? {
            options: GOAL_STATUSES,
            current: milestone.status,
            onChange: (status) => onUpdate({ status }),
          }
        : undefined,
    },
    {
      label: "Level",
      render: () => <span className="text-sm capitalize">{milestone.level}</span>,
      picker: onUpdate
        ? {
            options: GOAL_LEVELS,
            current: milestone.level,
            onChange: (level) => onUpdate({ level }),
          }
        : undefined,
    },
    {
      label: "Owner",
      render: () =>
        ownerAgent ? (
          <Link to={agentUrl(ownerAgent)} className="text-sm hover:underline">
            {ownerAgent.name}
          </Link>
        ) : (
          <span className="text-sm text-muted-foreground">None</span>
        ),
    },
  ];

  if (milestone.parentId) {
    editableRows.push({
      label: "Parent Goal",
      render: () => (
        <Link to={`/milestones/${milestone.parentId}`} className="text-sm hover:underline">
          {parentGoal?.title ?? milestone.parentId!.slice(0, 8)}
        </Link>
      ),
    });
  }

  const metaRows: PropertyRow[] = [
    {
      label: "Created",
      render: () => <span className="text-sm">{formatDate(milestone.createdAt)}</span>,
    },
    {
      label: "Updated",
      render: () => <span className="text-sm">{formatDate(milestone.updatedAt)}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        {editableRows.map((row) => (
          <PropertyRowView key={row.label} row={row} />
        ))}
      </div>

      <Separator />

      <div className="space-y-1">
        {metaRows.map((row) => (
          <PropertyRowView key={row.label} row={row} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subviews
// ---------------------------------------------------------------------------

function PropertyRowView({ row }: { row: PropertyRow }) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="text-xs text-muted-foreground shrink-0 w-20">{row.label}</span>
      <div className="flex items-center gap-1.5 min-w-0">
        {row.picker ? <PickerWrapper picker={row.picker}>{row.render()}</PickerWrapper> : row.render()}
      </div>
    </div>
  );
}

function PickerWrapper({
  picker,
  children,
}: {
  picker: NonNullable<PropertyRow["picker"]>;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const renderOption = picker.renderOption ?? humanize;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button className="cursor-pointer hover:opacity-80 transition-opacity">{children}</button>
      </PopoverTrigger>
      <PopoverContent className="w-40 p-1" align="end">
        {picker.options.map((opt) => (
          <Button
            key={opt}
            variant="ghost"
            size="sm"
            className={cn("w-full justify-start text-xs", opt === picker.current && "bg-accent")}
            onClick={() => {
              picker.onChange(opt);
              setOpen(false);
            }}
          >
            {renderOption(opt)}
          </Button>
        ))}
      </PopoverContent>
    </Popover>
  );
}
