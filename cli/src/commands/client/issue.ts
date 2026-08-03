/**
 * `issue` subcommands.
 *
 * Each subcommand is declared as a `defineClientCommand` spec; the wrapper
 * resolves the operator/project context and feeds it to the spec's `run`.
 * That keeps each subcommand body focused on payload assembly + API call.
 */
import { Command } from "commander";
import {
  addIssueCommentSchema,
  checkoutIssueSchema,
  createIssueSchema,
  updateIssueSchema,
  type Issue,
  type IssueComment,
} from "@gitmesh/core";
import {
  defineClientCommand,
  formatInlineRecord,
  printOutput,
} from "../_shared/define.js";
import {
  buildQueryString,
  parseCsv,
  parseHiddenAt,
  parseOptionalInt,
} from "../_shared/parse.js";
import type { BaseClientOptions } from "./common.js";

// ---------------------------------------------------------------------------
// Option shapes - kept narrow so the type-system catches typos in spec bodies
// ---------------------------------------------------------------------------

interface IssueListOpts extends BaseClientOptions {
  status?: string;
  assigneeAgentId?: string;
  match?: string;
}

interface IssueCreateOpts extends BaseClientOptions {
  title: string;
  description?: string;
  status?: string;
  priority?: string;
  assigneeAgentId?: string;
  goalId?: string;
  parentId?: string;
  requestDepth?: string;
  billingCode?: string;
}

interface IssueUpdateOpts extends BaseClientOptions {
  title?: string;
  description?: string;
  status?: string;
  priority?: string;
  assigneeAgentId?: string;
  goalId?: string;
  parentId?: string;
  requestDepth?: string;
  billingCode?: string;
  comment?: string;
  hiddenAt?: string;
}

interface IssueCommentOpts extends BaseClientOptions {
  body: string;
  reopen?: boolean;
}

interface IssueCheckoutOpts extends BaseClientOptions {
  agentId: string;
  expectedStatuses?: string;
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function filterIssueRows(rows: Issue[], match: string | undefined): Issue[] {
  if (!match?.trim()) return rows;
  const needle = match.trim().toLowerCase();
  return rows.filter((row) => {
    const haystack = [row.identifier, row.title, row.description]
      .filter((part): part is string => Boolean(part))
      .join("\n")
      .toLowerCase();
    return haystack.includes(needle);
  });
}

function renderIssueRow(row: Issue): string {
  return formatInlineRecord({
    identifier: row.identifier,
    id: row.id,
    status: row.status,
    priority: row.priority,
    assigneeAgentId: row.assigneeAgentId,
    title: row.title,
    projectId: row.projectId,
  });
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

export function registerIssueCommands(program: Command): void {
  const issue = program.command("issue").description("Issue operations");

  defineClientCommand<IssueListOpts>(issue, {
    name: "list",
    describe: "List issues for a project",
    options: [
      { flag: "-P, --project-id <id>", desc: "Project ID" },
      { flag: "--status <csv>", desc: "Comma-separated statuses" },
      { flag: "--assignee-agent-id <id>", desc: "Filter by assignee agent ID" },
      { flag: "--match <text>", desc: "Local text match on identifier/title/description" },
    ],
    requireProject: true,
    async run(ctx, { options }) {
      const path = `/api/projects/${ctx.projectId}/issues${buildQueryString({
        status: options.status,
        assigneeAgentId: options.assigneeAgentId,
        projectId: options.projectId,
      })}`;

      const rows = (await ctx.api.get<Issue[]>(path)) ?? [];
      const filtered = filterIssueRows(rows, options.match);

      if (ctx.json) {
        printOutput(filtered, { json: true });
        return;
      }
      if (filtered.length === 0) {
        printOutput([], { json: false });
        return;
      }
      for (const row of filtered) {
        console.log(renderIssueRow(row));
      }
    },
  });

  defineClientCommand<BaseClientOptions>(issue, {
    name: "get",
    describe: "Get an issue by UUID or identifier (e.g. PC-12)",
    positional: [{ name: "idOrIdentifier", desc: "Issue ID or identifier" }],
    async run(ctx, { positional }) {
      const [idOrIdentifier] = positional;
      const row = await ctx.resources.issues.get<Issue>(idOrIdentifier);
      printOutput(row, { json: ctx.json });
    },
  });

  defineClientCommand<IssueCreateOpts>(issue, {
    name: "create",
    describe: "Create an issue",
    options: [
      { flag: "-P, --project-id <id>", desc: "Project ID", required: true },
      { flag: "--title <title>", desc: "Issue title", required: true },
      { flag: "--description <text>", desc: "Issue description" },
      { flag: "--status <status>", desc: "Issue status" },
      { flag: "--priority <priority>", desc: "Issue priority" },
      { flag: "--assignee-agent-id <id>", desc: "Assignee agent ID" },
      { flag: "--goal-id <id>", desc: "Goal ID" },
      { flag: "--parent-id <id>", desc: "Parent issue ID" },
      { flag: "--request-depth <n>", desc: "Request depth integer" },
      { flag: "--billing-code <code>", desc: "Billing code" },
    ],
    requireProject: true,
    async run(ctx, { options }) {
      const payload = createIssueSchema.parse({
        title: options.title,
        description: options.description,
        status: options.status,
        priority: options.priority,
        assigneeAgentId: options.assigneeAgentId,
        projectId: options.projectId,
        goalId: options.goalId,
        parentId: options.parentId,
        requestDepth: parseOptionalInt(options.requestDepth),
        billingCode: options.billingCode,
      });

      const created = await ctx.resources.issues.create<Issue>(ctx.projectId!, payload);
      printOutput(created, { json: ctx.json });
    },
  });

  defineClientCommand<IssueUpdateOpts>(issue, {
    name: "update",
    describe: "Update an issue",
    positional: [{ name: "issueId", desc: "Issue ID" }],
    options: [
      { flag: "--title <title>", desc: "Issue title" },
      { flag: "--description <text>", desc: "Issue description" },
      { flag: "--status <status>", desc: "Issue status" },
      { flag: "--priority <priority>", desc: "Issue priority" },
      { flag: "--assignee-agent-id <id>", desc: "Assignee agent ID" },
      { flag: "--goal-id <id>", desc: "Goal ID" },
      { flag: "--parent-id <id>", desc: "Parent issue ID" },
      { flag: "--request-depth <n>", desc: "Request depth integer" },
      { flag: "--billing-code <code>", desc: "Billing code" },
      { flag: "--comment <text>", desc: "Optional comment to add with update" },
      { flag: "--hidden-at <iso8601|null>", desc: "Set hiddenAt timestamp or literal 'null'" },
    ],
    async run(ctx, { positional, options }) {
      const [issueId] = positional;
      const payload = updateIssueSchema.parse({
        title: options.title,
        description: options.description,
        status: options.status,
        priority: options.priority,
        assigneeAgentId: options.assigneeAgentId,
        projectId: options.projectId,
        goalId: options.goalId,
        parentId: options.parentId,
        requestDepth: parseOptionalInt(options.requestDepth),
        billingCode: options.billingCode,
        comment: options.comment,
        hiddenAt: parseHiddenAt(options.hiddenAt),
      });
      const updated = await ctx.api.patch<Issue & { comment?: IssueComment | null }>(
        `/api/issues/${issueId}`,
        payload,
      );
      printOutput(updated, { json: ctx.json });
    },
  });

  defineClientCommand<IssueCommentOpts>(issue, {
    name: "comment",
    describe: "Add comment to issue",
    positional: [{ name: "issueId", desc: "Issue ID" }],
    options: [
      { flag: "--body <text>", desc: "Comment body", required: true },
      { flag: "--reopen", desc: "Reopen if issue is done/cancelled" },
    ],
    async run(ctx, { positional, options }) {
      const [issueId] = positional;
      const payload = addIssueCommentSchema.parse({
        body: options.body,
        reopen: options.reopen,
      });
      const comment = await ctx.api.post<IssueComment>(
        `/api/issues/${issueId}/comments`,
        payload,
      );
      printOutput(comment, { json: ctx.json });
    },
  });

  defineClientCommand<IssueCheckoutOpts>(issue, {
    name: "checkout",
    describe: "Checkout issue for an agent",
    positional: [{ name: "issueId", desc: "Issue ID" }],
    options: [
      { flag: "--agent-id <id>", desc: "Agent ID", required: true },
      {
        flag: "--expected-statuses <csv>",
        desc: "Expected current statuses",
        defaultValue: "todo,backlog,blocked",
      },
    ],
    async run(ctx, { positional, options }) {
      const [issueId] = positional;
      const payload = checkoutIssueSchema.parse({
        agentId: options.agentId,
        expectedStatuses: parseCsv(options.expectedStatuses),
      });
      const updated = await ctx.api.post<Issue>(`/api/issues/${issueId}/checkout`, payload);
      printOutput(updated, { json: ctx.json });
    },
  });

  defineClientCommand<BaseClientOptions>(issue, {
    name: "release",
    describe: "Release issue back to todo and clear assignee",
    positional: [{ name: "issueId", desc: "Issue ID" }],
    async run(ctx, { positional }) {
      const [issueId] = positional;
      const updated = await ctx.api.post<Issue>(`/api/issues/${issueId}/release`, {});
      printOutput(updated, { json: ctx.json });
    },
  });
}
