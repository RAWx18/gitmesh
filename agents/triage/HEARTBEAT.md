# Triage agent - heartbeat checklist

GitMesh runs you in **heartbeats**: short execution windows. Each heartbeat: wake, sync with the control plane, triage one slice of work, exit cleanly. You do not run continuously.

## Environment

When injected by the control plane, you may have: `GITMESH_AGENT_ID`, `GITMESH_PROJECT_ID`, `GITMESH_API_URL`, `GITMESH_RUN_ID`, optional `GITMESH_API_KEY`, `GITMESH_TASK_ID`, `GITMESH_WAKE_REASON`, `GITMESH_WAKE_COMMENT_ID`, and related vars.

**Mutations:** include `X-Gitmesh-Run-Id: $GITMESH_RUN_ID` on all issue mutations (checkout, patch, comment) that support it.

## High-level loop

1. **Identity**: If needed, `GET /api/agents/me` for your id, project, role, budget.

2. **Approval follow-up**: If `GITMESH_APPROVAL_ID` is set, handle per `playbooks/core/playbook.md`.

3. **Assignments**: `GET /api/projects/{projectId}/issues?assigneeAgentId={you}&status=todo,in_progress,blocked` (exact query shapes in the core playbook).

4. **Pick work**: Prefer `in_progress`, then `todo`. Respect mention-based wakes (`GITMESH_WAKE_COMMENT_ID`): read that thread first.

5. **Checkout**: `POST /api/issues/{issueId}/checkout` before changing work you do not already own. On `409 Conflict`, stop and pick different work.

6. **Triage**: Apply rules in **`AGENTS.md`**; post summary from **`TOOLS.md`** templates.

7. **Finish**: `PATCH` status and comment as appropriate (`done`, `blocked`, `in_review`, etc.). If blocked, explain who unblocks.

8. **Delegate**: Create subtasks with `POST /api/projects/{projectId}/issues` when routing to another lane (set `parentId` / `goalId` per project rules).

## Blocked-task dedup

Before re-commenting on a `blocked` task, read the thread: if your last comment was the blocker and nothing new appeared, skip duplicate noise.

## Deeper reference

Full request shapes, headers, and edge cases: **`playbooks/core/playbook.md`** (GitMesh Agents skill).
