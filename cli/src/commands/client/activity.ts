/**
 * `activity list`: read project activity-log entries via the spec helper.
 */
import { Command } from "commander";
import type { ActivityEvent } from "@gitmesh/core";
import {
  defineClientCommand,
  formatInlineRecord,
  printOutput,
} from "../_shared/define.js";
import { buildQueryString } from "../_shared/parse.js";
import type { BaseClientOptions } from "./common.js";

interface ActivityListOpts extends BaseClientOptions {
  agentId?: string;
  entityType?: string;
  entityId?: string;
}

function renderActivityRow(row: ActivityEvent): string {
  return formatInlineRecord({
    id: row.id,
    action: row.action,
    actorType: row.actorType,
    actorId: row.actorId,
    entityType: row.entityType,
    entityId: row.entityId,
    createdAt: String(row.createdAt),
  });
}

export function registerActivityCommands(program: Command): void {
  const activity = program.command("activity").description("Activity log operations");

  defineClientCommand<ActivityListOpts>(activity, {
    name: "list",
    describe: "List project activity log entries",
    options: [
      { flag: "-P, --project-id <id>", desc: "Project ID", required: true },
      { flag: "--agent-id <id>", desc: "Filter by agent ID" },
      { flag: "--entity-type <type>", desc: "Filter by entity type" },
      { flag: "--entity-id <id>", desc: "Filter by entity ID" },
    ],
    requireProject: true,
    async run(ctx, { options }) {
      const path = `/api/projects/${ctx.projectId}/activity${buildQueryString({
        agentId: options.agentId,
        entityType: options.entityType,
        entityId: options.entityId,
      })}`;
      const rows = (await ctx.api.get<ActivityEvent[]>(path)) ?? [];

      if (ctx.json) {
        printOutput(rows, { json: true });
        return;
      }
      if (rows.length === 0) {
        printOutput([], { json: false });
        return;
      }
      for (const row of rows) console.log(renderActivityRow(row));
    },
  });
}
