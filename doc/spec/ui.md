# GitMesh Agents - UI Reference

> **Status** Draft &middot; **Last revised** 2026-02-17.
>
> This is the canonical UI reference. It is organised as a top-level
> **token catalogue** + **route catalogue**, not as a narrative tour, so
> you can jump straight to the section you need. Use the route catalogue
> (&sect;6&ndash;&sect;13) when wiring up a page; use the token catalogue
> (&sect;1&ndash;&sect;3) when building shared primitives.

---

## Contents

1. Design language - voice, density, theme
2. Visual tokens - colours, typography, icons
3. Application shell
4. Common navigation chrome - sidebar, breadcrumbs, search
5. Page index
6. Issues
7. Projects, Goals, Org Chart
8. Dashboard & Inbox
9. Agents
10. Approvals (contextual, not standalone)
11. Costs
12. Activity log
13. Auxiliary surfaces - Cmd+K, keyboard, responsive, empty/error states
14. Component library map
15. URL routing table
16. Implementation order

---

## 1. Design language

GitMesh Agents is a professional control plane, not a toy dashboard. It
is built to be lived in:

- **Density beats padding.** Whitespace separates; it does not pad.
- **Keyboard-first.** `Cmd+K`, `C` (new issue), and J/K navigation should keep power users off the mouse.
- **Contextual, not modal.** Inline editors > dialogs. Dropdowns > page navigations. Never break the user's mental context unnecessarily.
- **Dark by default.** Neutral charcoals (not pure black). Accent colour reserved for state and priority. Text is the primary visual element.

---

## 2. Visual tokens

### 2.1 Colour

| Token | Value |
|-------|-------|
| Background | `hsl(220, 13%, 10%)` (charcoal) |
| Surface / card | `hsl(220, 13%, 13%)` |
| Border | `hsl(220, 10%, 18%)` |
| Text primary | `hsl(220, 10%, 90%)` |
| Text secondary | `hsl(220, 10%, 55%)` |
| Accent (interactive) | `hsl(220, 80%, 60%)`: muted blue |

Status colours (consistent across every entity that has a status):

| Status | Colour |
|--------|--------|
| Backlog | gray `hsl(220, 10%, 45%)` |
| Todo | gray-blue `hsl(220, 20%, 55%)` |
| In Progress | yellow `hsl(45, 90%, 55%)` |
| In Review | violet `hsl(270, 60%, 60%)` |
| Done | green `hsl(140, 60%, 50%)` |
| Cancelled | gray `hsl(220, 10%, 40%)` |
| Blocked | amber `hsl(25, 90%, 55%)` |

Priority indicators (always icons, never text alone):

| Priority | Glyph |
|----------|-------|
| Critical | red circle, filled |
| High | orange circle, half-filled |
| Medium | yellow circle, outline |
| Low | gray circle, outline, dashed |

### 2.2 Typography

- Font: system stack - Inter when loaded, otherwise `-apple-system, BlinkMacSystemFont, 'Segoe UI'`.
- Body: 13px / 1.5.
- Labels and metadata: 11px / uppercase tracking.
- Headings: 14&ndash;18px / semi-bold. Never all-caps.

### 2.3 Icons

`lucide-react` everywhere. 16px in nav, 14px inline. Every sidebar entry,
status indicator, and action button gets an icon.

---

## 3. Application shell

A three-zone layout: sidebar (240px) on the left, breadcrumb bar across
the top of the main+properties area, main content (flex), and an
optional right-hand properties panel (320px).

- **Sidebar:** fixed, 240px. Collapsible to icon-only (48px) via toggle or shortcut.
- **Breadcrumb bar:** spans full width above main + properties. Carries navigation path, entity actions, and view controls.
- **Main content:** scrollable. Holds the primary view (list, detail, chart).
- **Properties panel:** right-hand, 320px, **contextual to the selected entity**. Visible on detail views (issue, project, agent), hidden on list views and the dashboard. Resizable. Slides in/out as you move into and out of detail views - not a permanent sidebar.

---

## 4. Navigation chrome

### 4.1 Sidebar

Primary navigation, grouped into collapsible sections.

#### Project header (top, always visible)

- Full-width project switcher button: project icon (first-letter avatar with project colour, or uploaded icon) - project name (truncated with ellipsis) - chevron-down.
- Dropdown shows: list of projects with status dots (`green` = active, `yellow` = paused, `gray` = archived), search field at top, divider, `+ Create project` at the bottom.
- Below the project name: icon-button row with **Search** (opens `Cmd+K`) and **New Issue** (opens the new-issue modal in the current project context).

#### Sidebar groups

| Group | Items |
|-------|-------|
| Personal (no header, always at top) | Inbox (with unread badge), My Issues |
| Work | Issues, Projects, Goals, Views |
| Project | Dashboard, Org Chart, Agents, Costs, Activity |

> Approvals are intentionally absent from the sidebar. They surface
> through the Inbox (primary), the Dashboard (count metric), and inline
> on entity pages (&sect;10). The `/approvals` route remains reachable
> via `See all approvals` links in those surfaces.

#### Sidebar behaviour

- Section headers click to collapse / expand. Collapsed state persists in `localStorage`.
- Active nav item: left-border accent + background tint.
- Hover: subtle background highlight.
- Badge counts: small rounded-rect pills on the right.
- Icons: 16px, left-aligned, 8px gap to label.

#### Sidebar icon map (lucide-react)

| Item | Icon |
|------|------|
| Inbox | `Inbox` |
| My Issues | `CircleUser` |
| Issues | `CircleDot` |
| Projects | `Hexagon` |
| Goals | `Target` |
| Views | `LayoutList` |
| Dashboard | `LayoutDashboard` |
| Org Chart | `GitBranch` |
| Agents | `Bot` |
| Costs | `DollarSign` |
| Activity | `History` |

### 4.2 Breadcrumb bar

Sits above the main content + properties panel.

Left side: clickable breadcrumb segments separated by `›`; the current
segment is non-clickable and slightly bolder. Plus a star icon
(favourite the entity) and a three-dot menu (delete / archive /
duplicate / copy link / ...).

Right side: notification bell on detail views (subscribe to changes for
this entity), and the panel toggle (show / hide right properties panel).

Some detail pages render a tab row below the breadcrumb (pill-shaped
buttons; active tab gets a subtle background fill):

| Page | Tabs |
|------|------|
| Project detail | Overview &middot; Updates &middot; Issues &middot; Settings |
| Agent detail | Overview &middot; Heartbeats &middot; Issues &middot; Costs |

### 4.3 Cmd+K search

Global modal at `Cmd+K` (or the sidebar search icon). Type-ahead across
issues, agents, projects, goals; results are grouped by type with icons.
Empty input shows recent items. A pinned **Actions** section at the
bottom lists `Create new issue` (`C`), `Create new agent`,
`Create new project`. Arrow keys navigate, Enter selects, Escape closes.

---

## 5. Page index

| Section | Route | Purpose |
|---------|-------|---------|
| Issues | `/issues`, `/issues/:id` | The workhorse task list and detail |
| Projects | `/projects`, `/projects/:id`, `/projects/:id/issues` | Group of issues + goal link |
| Goals | `/goals`, `/goals/:id` | Hierarchical goal tree |
| Dashboard | `/dashboard` | Project health overview |
| Inbox | `/inbox` | Aggregate of attention items (approvals, alerts, stale work) |
| My Issues | `/my-issues` | Operator-scoped slice of issues |
| Org Chart | `/org` | Interactive agent reporting tree |
| Agents | `/agents`, `/agents/:id` | Agent list + per-agent control panel |
| Approvals | `/approvals`, `/approvals/:id` | Governance gate detail (not in sidebar) |
| Costs | `/costs` | Spend visualisation |
| Activity | `/activity` | Audit trail |
| Settings | `/settings` | Project settings |

---

## 6. Issues

### 6.1 List

Default for the **Issues** sidebar entry.

Top toolbar:

- Status tabs: `All Issues`, `Active` (todo + in_progress + in_review + blocked), `Backlog`. Each carries a status icon and a count. Active tab is filled.
- Settings gear - configure issue display defaults and custom fields.
- Filter button - reveals the filter bar (&sect;6.2).
- Display dropdown - toggles grouping (status / priority / assignee / project / none) and layout (list / kanban).

Grouping:

- Default group is by status (matches the reference screenshots).
- Each group header carries: collapse chevron, status icon, status name, count, and a `+` to create an issue in that status.
- Groups are collapsible; collapsed groups show only the header and count.

Issue row layout (left to right):

1. **Checkbox**: bulk-selection. Hidden until hover; appears left of the priority indicator.
2. **Priority indicator**: always visible.
3. **Issue key**: e.g. `CLIP-5`. Monospace, muted.
4. **Status circle**: clickable; opens the inline status dropdown.
5. **Title**: primary text, ellipsis on overflow.
6. **Assignee**: agent avatar + name, right-aligned. Dashed circle placeholder when unassigned.
7. **Date**: creation or target date, muted, far right.

Row interactions:

- Click row &rarr; issue detail.
- Click status circle &rarr; inline status dropdown (Backlog / Todo / In Progress / In Review / Done / Cancelled). Numbers `1`&ndash;`6` are shortcuts.
- Checkbox &rarr; bulk selection. When any are selected, a floating bulk-action bar appears: count selected, plus `Status`, `Priority`, `Assignee`, `Project` dropdowns and `Delete` / `Cancel`.
- Hover &rarr; checkbox surfaces, row highlights subtly.
- Right-click &rarr; same context menu as the three-dot.

### 6.2 Filter bar

Toggling Filter reveals a chip-based bar above the list. Each filter is a
chip showing `field operator value`. Click a chip to edit, `&times;`
to remove. `+ Add filter` opens a field menu: Status, Priority, Assignee,
Project, Goal, Created date, Labels, Creator. Filters are AND-composed
and persisted in the URL query string for sharing.

### 6.3 Detail view (three-pane)

Sidebar on the left, main content in the middle, properties panel on the
right. The main content holds the title, an inline properties chip-bar,
description, subtasks, and comments, in that order.

Header area:

- Title: 18px semi-bold, click-to-edit inline.
- Subtitle: issue key in muted text.
- Inline properties chip-bar under the title: status circle, priority, assignee, target date, project, etc. Each chip opens its own small editor.

Description: markdown-rendered; click to enter the inline markdown
editor. Headings, lists, code blocks, links, images all supported.

Subtasks (if any): collapsible section; each subtask is a mini issue row
(status circle + title + assignee). `+ Add subtask` at the bottom.

Comments: chronological list. Each entry shows author avatar / icon,
author name, timestamp, markdown body. Bot icon for agent comments,
human icon for the operator. The composer is a markdown text-area at the
bottom with a primary `Comment` button.

Right pane (Properties panel): label + editable value rows.

| Property | Editor |
|----------|--------|
| Status | Dropdown + colour dot |
| Priority | Dropdown + icon |
| Assignee | Agent picker (searchable) |
| Project | Project picker |
| Goal | Goal picker |
| Labels | Multi-select tag input |
| Lead | Agent picker |
| Members | Multi-select agent picker |
| Start date | Date picker |
| Target date | Date picker |
| Created by | Read-only text |
| Created | Read-only timestamp |
| Billing code | Text input |

Below properties: divider, then **Activity**: compact timeline of
status / assignment changes and comments, with relative timestamps and
a `See all` link.

### 6.4 New issue modal

Triggered by the sidebar pencil, the `C` shortcut, or any `+` in the
issue list.

Top bar: breadcrumb showing project context - `New issue`; `Save as
draft`; expand-to-page; close.

Body: large title input (auto-focused) above an expandable markdown
description (placeholder `Add a description...`).

Bottom property chips: Status (defaults to Todo), Priority, Assignee,
Project, Labels by default; the `&middot;&middot;&middot;` button reveals Goal, Start
date, Target date, Billing code, Parent issue.

Footer: attachment icon; `Create more` toggle (keep modal open for rapid
entry); primary `Create issue` button.

Behaviour:

- `Cmd+Enter` submits.
- Project context pre-fills when invoked from inside one.
- The status group's `+` button pre-fills that status.
- Slug / key auto-generates from the project prefix + incrementing number; visible in the breadcrumb.

### 6.5 Kanban view

`Display` &rarr; **Operator (kanban)**. Columns map 1:1 to status:
Backlog / Todo / In Progress / In Review / Done. Each card carries the
issue key (muted), the title (primary), priority icon (bottom-left),
assignee avatar (bottom-right). Cards are draggable across columns;
invalid status transitions surface as an error toast. Each column header
has a `+` to create a new issue in that status.

---

## 7. Projects, Goals, Org Chart

### 7.1 Project list

Each row: project icon (coloured hexagon), name, status badge, lead
agent, target date. New project via the `+ New project` action.

### 7.2 Project detail

Three-pane. Tab row: Overview / Updates / Issues / Settings.

- **Overview (middle pane).** Project icon + editable name. Markdown description. Inline properties chip-bar (`status`, `priority`, `lead`, `target`, `team`, ...). Resources section (linked documents + URLs). `Write first project update` CTA. Description body. Collapsible Milestones list with date + status.
- **Issues tab.** Filtered issue list (same controls as &sect;6) scoped to this project.
- **Right pane.** Status, Priority, Lead, Members, Start date, Target date, Teams, Labels, Goal link. Activity at the bottom.

### 7.3 Goals

Goals form a hierarchical tree (parent / child relationships). The list
view renders an indented tree. Each row: expand chevron (when there are
children), target icon, title, level badge (Project / Team / Agent /
Task), status badge.

Detail view: three-pane. Middle pane shows title, description, child
goals, linked projects. Right pane shows level, status, owner agent,
parent goal, plus activity.

### 7.4 Org Chart

Interactive tree of agents. Each node displays agent name, role/title,
status dot (coloured by agent status), and avatar (bot icon, unique
colour per agent).

Interactions: zoom / pan with wheel + drag; click selects (tooltip with
last heartbeat, current task, spend); double-click opens agent detail;
right-click context menu = `View / Pause / Resume / Invoke heartbeat /
Edit`.

---

## 8. Dashboard & Inbox

### 8.1 Dashboard

Project health overview. Top row of four metric cards, then two detail
panels.

| Card | Content |
|------|---------|
| Agents | Total / active / running / paused / error counts (each with a coloured dot) |
| Tasks | Open / in progress / blocked / done counts |
| Costs | MTD spend in dollars + budget utilisation % with a mini progress bar |
| Approvals | Pending count; clicks navigate to Inbox (the primary approval interaction point) |

| Panel | Content |
|-------|---------|
| Recent Activity | Last ~10 activity log entries, compact timeline format |
| Stale Tasks | Tasks in progress beyond a threshold without updates - key, title, assignee, time-since-update |

Every card / panel is clickable to navigate to its full page.

### 8.2 Inbox

The Inbox is the operator's action centre. Items are grouped, with the
most actionable first.

- **Approvals pending** (top priority). Each row: shield icon + approval type + title; requester + relative timestamp; one-line payload summary (agent name/role for `enable_agent`, plan title for `approve_admin_strategy`); inline `[Approve]` / `[Reject]` for simple approvals (with optional decision-note confirmation); `[View details &rarr;]` for complex approvals that need full review. The category header has a `See all approvals &rarr;` link to `/approvals`.
- **Alerts.** Failed heartbeats, agents in error status, budget alerts at 80% / 100% on agent or project. Each links to the relevant agent or cost page.
- **Stale work.** Tasks `in_progress` or `todo` with no activity beyond a configurable threshold (default 24h). Each shows issue key, title, time since last activity. Click to navigate.

Behaviour notes:

- Unread items have a filled blue dot indicator on the left.
- Clicking an item marks it read.
- Approvals leave the inbox once decided (move to resolved state).
- Alerts leave when the underlying condition resolves (agent resumed, budget raised).
- The sidebar badge count reflects total unresolved inbox items.
- For V1, the inbox is computed from live data (pending-approvals query + alert conditions). No separate notification table.

---

## 9. Agents

### 9.1 List

Columns: avatar / icon, name, role, status (with coloured dot), cost
(spent / budget for the month), last heartbeat (relative time). Click a
row to open detail.

### 9.2 Detail (three-pane)

Tab row: Overview / Heartbeats / Issues / Costs.

- **Overview (middle pane).** Agent name + role, capabilities description, adapter type + config summary, current task (when present), reports-to (clickable), direct reports list.
- **Heartbeats tab.** Table of heartbeat runs - time, source (manual / scheduler), status, duration, error if any. `Invoke` button at the top.
- **Issues tab.** Issues assigned to this agent.
- **Costs tab.** Cost breakdown by model and by time range, with a budget progress bar.
- **Right pane (properties).** Status, Role, Title, Reports To, Adapter Type, Context Mode, Budget (monthly), Spent (monthly), Last Heartbeat.
- **Quick actions in the breadcrumb bar.** `Pause` &middot; `Resume` &middot; `Invoke Heartbeat` &middot; `&middot;&middot;&middot;`.

---

## 10. Approvals (contextual, not standalone)

Approvals are governance gates, not work items. They keep their own data
model (different status machine, side-effect triggers, unstructured
payload) but they do **not** get a top-level nav entry.

Where they appear:

| Surface | Role |
|---------|------|
| Inbox | **Primary.** Pending approvals at the top with inline approve/reject |
| Dashboard | "Pending Approvals" metric card with count, links to inbox |
| Entity detail pages | Contextual banners (e.g. agent detail: `Enabled via approval - requested by admin on Feb 15` with a link to the approval record). An agent in `pending` status can show `Pending approval - requested by admin` with inline approve/reject. |
| Activity log | Approval events (created / approved / rejected) appear in the timeline like any other event. |

### 10.1 Approvals list page (`/approvals`)

Still exists as the `See all` destination from Inbox and Dashboard, but
not in the sidebar. Status tabs filter by approval status (`Pending`,
`Approved`, `Rejected`, `All`). Each row: status dot, type, payload
title / summary, requester, relative time.

### 10.2 Approval detail

Three-pane layout. The middle pane renders the payload by type:

- **`enable_agent`**: preview of the agent that will be created: name, role, title, reports-to, capabilities, adapter config, budget.
- **`approve_admin_strategy`**: the strategy text, proposed goal breakdown, initial task structure.

For pending approvals, the action region sits at the very top of the
middle pane: an optional decision-note field plus prominent `[&times; Reject]`
and `[&check; Approve]` buttons.

Right pane: Type, Status, Requested by, Requested at, Decided by,
Decided at, Decision note. Activity timeline below.

---

## 11. Costs

Cost dashboard, scoped to the current month by default.

- Top: project-wide budget progress bar - large, prominent, MTD spend / budget cap with a horizontal progress meter.
- Two side-by-side breakdown tables: **By Agent** and **By Project**. Each row is entity name + spend.
- Bottom: recent cost events table - agent, provider/model, token counts (in / out), cost, relative timestamp.

---

## 12. Activity log

A chronological, filterable audit trail.

Each entry: actor icon (bot for agent, human for operator, gear for
system), actor name, action description with entity links, relative
timestamp.

Filters: actor type (agent / user / system), entity type (issue / agent
/ project / etc.), action type, time range. Infinite scroll with a
`Load more` fallback.

---

## 13. Auxiliary surfaces

### 13.1 Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+K` | Open search |
| `C` | Create new issue |
| `Cmd+Enter` | Submit form (in modals) |
| `Escape` | Close modal / deselect |
| `[` | Toggle sidebar collapsed |
| `]` | Toggle properties panel |
| `J` / `K` | Navigate up / down in lists |
| `Enter` | Open selected item |
| `Backspace` | Go back |
| `S` | Toggle status on selected issue |
| `X` | Toggle checkbox selection |
| `Cmd+A` | Select all (in list context) |

### 13.2 Responsive behaviour

| Viewport | Behaviour |
|----------|-----------|
| `>1400px` | Full three-pane (sidebar + main + properties) |
| `1024&ndash;1400px` | Sidebar collapses to icons; properties panel via toggle |
| `<1024px` | Sidebar hidden (hamburger menu); properties panel via toggle / tab |

The properties panel is always dismissible - it must never block the
main content.

### 13.3 Empty states

Every list view must have a thoughtful empty state. Examples:

- No issues - `No issues yet. Create your first issue to start tracking work.` &middot; `[Create issue]`.
- No agents - `No agents in this project. Create an agent to start building your team.` &middot; `[Create agent]`.
- No project selected - `Select a project to get started.` &middot; project switcher or `[Create project]`.

Empty states use a muted line-art illustration (no cartoons) and exactly
one CTA.

### 13.4 Loading and error states

- Loading: skeleton blocks matching the expected layout, with subtle shimmer. **Not** spinners.
- Error: inline error message + retry button. Full-page errors only when the app itself is broken.
- Conflict (`409`): toast `This issue was updated by another user. Refresh to see changes.` with a `Refresh` action.
- Optimistic updates: status changes and property edits update immediately, rolled back on failure.

---

## 14. Component library map

Built on shadcn/ui plus these customisations:

| Component | Base | Customisation |
|-----------|------|---------------|
| StatusBadge | Badge | Coloured dot + label, entity-specific palettes |
| PriorityIcon | custom | SVG circles with priority-matched fills |
| EntityRow | custom | Standardised list row with hover / select states |
| PropertyEditor | custom | Label + inline-editable value with dropdown |
| CommentThread | custom | Avatar + author + timestamp + markdown body |
| BreadcrumbBar | Breadcrumb | Integrated with router, tabs, entity actions |
| CommandPalette | Dialog | `Cmd+K` search with type-ahead and actions |
| FilterBar | custom | Composable filter chips with add / remove |
| SidebarNav | custom | Grouped, collapsible, badge-supporting nav |

---

## 15. URL routing table

Project context is held in React context (not the URL); every route
below is implicitly project-scoped.

| Route | Destination |
|-------|-------------|
| `/` | redirects to `/dashboard` |
| `/dashboard` | project dashboard |
| `/inbox` | inbox / attention items |
| `/my-issues` | operator's issues |
| `/issues` | issue list |
| `/issues/:issueId` | issue detail |
| `/projects` | project list |
| `/projects/:projectId` | project detail (Overview tab) |
| `/projects/:projectId/issues` | project issues |
| `/goals` | goal hierarchy |
| `/goals/:goalId` | goal detail |
| `/org` | org chart |
| `/agents` | agent list |
| `/agents/:agentId` | agent detail |
| `/approvals` | approval list |
| `/approvals/:approvalId` | approval detail |
| `/costs` | cost dashboard |
| `/activity` | activity log |
| `/settings` | project settings |

---

## 16. Implementation order

| Phase | Deliverables |
|-------|--------------|
| 1 - Shell & navigation | Sidebar redesign (groups, icons, project switcher, badges); breadcrumb bar component; three-pane layout system; `Cmd+K` search modal; install `lucide-react` |
| 2 - Issue management (core) | Issue list view with grouping, filtering, status circles; issue detail (three-pane with properties); new issue modal; comments; bulk selection + actions; kanban operator view |
| 3 - Entity detail views | Project list + detail; goal hierarchy; agent list + detail |
| 4 - Project-level views | Inbox with inline approval actions (primary approval UX); dashboard with metric cards; org chart; cost dashboard; activity log with filtering; approvals list page (accessed via Inbox `See all`, not the sidebar) |
| 5 - Polish | Keyboard shortcuts; responsive behaviour; empty states + loading skeletons; error handling and toasts |
