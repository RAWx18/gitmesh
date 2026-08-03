/**
 * Test data factories for the GitMesh Agents server suite.
 *
 * The factories return plain object literals that mirror the shape used
 * by domain modules (issues, agents, heartbeat workspaces, etc.). Tests
 * import the factories instead of inlining their own object literals so
 * that:
 *   1. Each test has a single line of intent (`makeIssue({ assigneeUserId: 'u' })`).
 *   2. When a domain shape grows a new required field, only the factory
 *      changes, not every test.
 *   3. Counter-based identifiers prevent accidental cross-test collisions
 *      while still being deterministic per-test (`resetFactoryCounters`).
 */

let _counter = 0;

/** Reset the monotonically-increasing id sequence (call from `beforeEach`). */
export function resetFactoryCounters(): void {
  _counter = 0;
}

function nextId(prefix: string): string {
  _counter += 1;
  return `${prefix}-${_counter}`;
}

// ---------------------------------------------------------------------------
// Issues
// ---------------------------------------------------------------------------

export interface IssueFactoryShape {
  createdByUserId: string | null;
  assigneeUserId: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export function makeIssue(overrides: Partial<IssueFactoryShape> = {}): IssueFactoryShape {
  const createdAt = overrides.createdAt ?? new Date("2026-03-06T10:00:00.000Z");
  return {
    createdByUserId: null,
    assigneeUserId: null,
    createdAt,
    updatedAt: overrides.updatedAt ?? new Date(createdAt.getTime() + 60 * 60 * 1000),
    ...overrides,
  };
}

export interface IssueUserContextInputShape {
  myLastCommentAt: Date | string | null;
  myLastReadAt: Date | string | null;
  lastExternalCommentAt: Date | string | null;
}

export function makeIssueUserContextInput(
  overrides: Partial<IssueUserContextInputShape> = {},
): IssueUserContextInputShape {
  return {
    myLastCommentAt: null,
    myLastReadAt: null,
    lastExternalCommentAt: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export type AgentStatus = "idle" | "active" | "running" | "terminated" | "paused";

export interface AgentRowShape {
  id: string;
  name: string;
  status: AgentStatus;
}

export function makeAgent(overrides: Partial<AgentRowShape> = {}): AgentRowShape {
  return {
    id: overrides.id ?? nextId("agent"),
    name: overrides.name ?? "agent",
    status: overrides.status ?? "idle",
  };
}

/** Build a small fleet of agents with sequential names - useful for collision tests. */
export function makeAgentFleet(
  count: number,
  baseName: string,
  status: AgentStatus = "idle",
): AgentRowShape[] {
  const fleet: AgentRowShape[] = [];
  for (let i = 1; i <= count; i += 1) {
    const suffix = i === 1 ? "" : `-${i}`;
    fleet.push(makeAgent({ name: `${baseName}${suffix}`, status }));
  }
  return fleet;
}

// ---------------------------------------------------------------------------
// Heartbeat / workspace
// ---------------------------------------------------------------------------

export interface ResolvedWorkspaceShape {
  cwd: string;
  source: "project_primary" | "task_session" | "agent_home";
  projectId: string | null;
  workspaceId: string | null;
  repoUrl: string | null;
  repoRef: string | null;
  workspaceHints: Array<{
    workspaceId: string;
    cwd: string | null;
    repoUrl: string | null;
    repoRef: string | null;
  }>;
  warnings: string[];
}

export function makeResolvedWorkspace(
  overrides: Partial<ResolvedWorkspaceShape> = {},
): ResolvedWorkspaceShape {
  return {
    cwd: "/tmp/project",
    source: "project_primary",
    projectId: "project-1",
    workspaceId: "workspace-1",
    repoUrl: null,
    repoRef: null,
    workspaceHints: [],
    warnings: [],
    ...overrides,
  };
}

export interface PreviousSessionShape {
  sessionId: string;
  cwd: string;
  workspaceId: string;
}

export function makePreviousSession(
  overrides: Partial<PreviousSessionShape> = {},
): PreviousSessionShape {
  return {
    sessionId: "session-1",
    cwd: "/tmp/project",
    workspaceId: "workspace-1",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Operators
// ---------------------------------------------------------------------------

export interface OperatorActorShape {
  type: "operator" | "agent" | "anonymous";
  source?: "session" | "local_implicit" | "claim_token";
  userId?: string;
}

export function makeOperator(
  overrides: Partial<OperatorActorShape> = {},
): OperatorActorShape {
  return {
    type: "operator",
    source: "session",
    userId: overrides.userId ?? nextId("user"),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export interface ProjectRowShape {
  id: string;
  name: string;
  shortname: string;
}

export function makeProject(overrides: Partial<ProjectRowShape> = {}): ProjectRowShape {
  const id = overrides.id ?? nextId("project");
  return {
    id,
    name: overrides.name ?? `Project ${id}`,
    shortname: overrides.shortname ?? id,
    ...overrides,
  };
}
