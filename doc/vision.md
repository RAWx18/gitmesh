# GitMesh Agents - Product Definition

## What It Is

GitMesh Agents is the control plane for autonomous AI projects. One instance of GitMesh Agents can run multiple projects. A **project** is a first-order object.

## Core Concepts

### Project

A project has:

- A **goal**: the reason it exists ("Create the #1 AI note-taking app that does $1M MRR within 3 months")
- **Agents**: every agent is an AI agent
- **Org structure**: who reports to whom
- **Revenue & expenses**: tracked at the project level
- **Task hierarchy**: all work traces back to the project goal

### Agents & Agents

Every agent is an agent. When you create a project, you start by defining the admin, then build out from there.

Each agent has:

- **Adapter type + config**: how this agent runs and what defines its identity/behavior. This is adapter-specific (e.g., an gateway agent might use SOUL.md and HEARTBEAT.md files; a Claude Code agent might use CLAUDE.md; a bare script might use CLI args). GitMesh Agents doesn't prescribe the format - the adapter does.
- **Role & reporting**: their title, who they report to, who reports to them
- **Capabilities description**: a short paragraph on what this agent does and when they're relevant (helps other agents discover who can help with what)

Example: A admin agent's adapter config tells it to "review what your executives are doing, check project metrics, reprioritize if needed, assign new strategic initiatives" on each heartbeat. An engineer's config tells it to "check assigned tasks, pick the highest priority, and work it."

Then you define who reports to the admin: a pr_review managing programmers, a docs managing the marketing team, and so on. Every agent in the tree gets their own adapter configuration.

### Agent Execution

There are two fundamental modes for running an agent's heartbeat:

1. **Run a command**: GitMesh Agents kicks off a process (shell command, Python script, etc.) and tracks it. The heartbeat is "execute this and monitor it."
2. **Fire and forget a request**: GitMesh Agents sends a webhook/API call to an externally running agent. The heartbeat is "notify this agent to wake up." (gateway hooks work this way.)

We provide sensible defaults - a default agent that shells out to Claude Code or Codex with your configuration, remembers session IDs, runs basic scripts. But you can plug in anything.

### Task Management

Task management is hierarchical. At any moment, every piece of work must trace back to the project's top-level goal through a chain of parent tasks:

```
I am researching the Facebook ads Granola uses (current task)
  because → I need to create Facebook ads for our software (parent)
    because → I need to grow new signups by 100 users (parent)
      because → I need to get revenue to $2,000 this week (parent)
        because → ...
          because → We're building the #1 AI note-taking app to $1M MRR in 3 months
```

Tasks have parentage. Every task exists in service of a parent task, all the way up to the project goal. This is what keeps autonomous agents aligned - they can always answer "why am I doing this?"

More detailed task structure TBD.

## Principles

1. **Unopinionated about how you run your agents.** Your agents could be gateway bots, Python scripts, Node scripts, Claude Code sessions, Codex instances - we don't care. GitMesh Agents defines the control plane for communication and provides utility infrastructure for heartbeats. It does not mandate an agent runtime.

2. **Project is the unit of organization.** Everything lives under a project. One GitMesh Agents instance, many projects.

3. **Adapter config defines the agent.** Every agent has an adapter type and configuration that controls its identity and behavior. The minimum contract is just "be callable."

4. **All work traces to the goal.** Hierarchical task management means nothing exists in isolation. If you can't explain why a task matters to the project goal, it shouldn't exist.

5. **Control plane, not execution plane.** GitMesh Agents orchestrates. Agents run wherever they run and phone home.

## User Flow (Dream Scenario)

1. Open GitMesh Agents, create a new project
2. Define the project's goal: "Create the #1 AI note-taking app, $1M MRR in 3 months"
3. Create the admin
   - Choose an adapter (e.g., process adapter for Claude Code, HTTP adapter for Gateway)
   - Configure the adapter (agent identity, loop behavior, execution settings)
   - admin proposes strategic breakdown → operator approves
4. Define the admin's reports: pr_review, docs, security, etc.
   - Each gets their own adapter config and role definition
5. Define their reports: engineers under pr_review, marketers under docs, etc.
6. Set budgets, define initial strategic tasks
7. Hit go - agents start their heartbeats and the project runs

## Guidelines

There are two runtime modes GitMesh Agents must support:

- `local_trusted` (default): single-user local trusted deployment with no login friction
- `authenticated`: login-required mode that supports both private-network and public deployment exposure policies

Canonical mode design and command expectations live in `doc/DEPLOYMENT-MODES.md`.

## Further Detail

See [architecture.md](./architecture.md) for the full technical specification.
