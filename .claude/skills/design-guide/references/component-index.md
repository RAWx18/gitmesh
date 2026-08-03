# GitMesh Agents UI Components

Working reference for everything under `ui/src/components/`, `ui/src/features/`, and a few helper utilities. Update this file whenever you add a reusable component.

## How the directories are organized

```
ui/src/
├── components/
│   ├── ui/              shadcn primitives (don't edit; extend via composition)
│   └── *.tsx            custom components used in 2+ places
├── features/            larger composed surfaces - dialogs, panels, palettes
├── hooks/               cross-cutting hooks
└── lib/                 utilities, query-key factories, formatters
```

The `ui/` subdirectory mirrors the shadcn registry layout. **Treat shadcn primitives as immutable**: if you need a variant they don't have, build a custom component in `components/` that composes them.

---

## Pick the right component first

| Goal | Use this | Don't use |
| --- | --- | --- |
| Show a status (todo / in_progress / done / …) | `StatusBadge` for pills, `StatusIcon` for circles | hand-rolled colored spans |
| Show a priority (critical / high / medium / low) | `PriorityIcon` | text labels |
| Render a row in any list of issues / agents / projects | `EntityRow` | bespoke `<div>` rows |
| Render a "name + avatar" reference to a person/agent | `Identity` | `<Avatar>` + `<span>` pair |
| Click-to-edit a string | `InlineEditor` | dual `<input>`/`<span>` toggle |
| Empty list placeholder | `EmptyState` | hand-written prose |
| Stat card on a dashboard | `MetricCard` | `<Card>` + manual layout |
| Loading shell for a route | `PageSkeleton` (variant `list` / `detail`) | scattered `<Skeleton>` |
| Display active filter chips with × | `FilterBar` | per-page chip components |
| Modal | `Dialog` (form: `NewIssueDialog`, `NewProjectDialog`, `NewAgentDialog`) | `Sheet` (use Sheet for side-attached panels) |
| Cmd+K palette | `CommandPalette` | new global modals |
| Properties panel on a detail view | `PropertiesPanel` + entity-specific `*Properties.tsx` | inline `aside` blocks |

---

## Custom components (alphabetical)

Each entry is `Component - file - what it does - key prop notes`.

- **AgentConfigForm**: `AgentConfigForm.tsx`: Full agent create/edit form including adapter-type selection. Composes the primitives in `agent-config-primitives.tsx`.
- **agent-config-primitives**: `agent-config-primitives.tsx`: Form-field primitives reused across agent config: `Field`, `ToggleField`, `ToggleWithNumber`, `CollapsibleSection`, `AutoExpandTextarea`, `DraftInput`.
- **BreadcrumbBar**: `BreadcrumbBar.tsx`: Top breadcrumb spanning main content + properties panel.
- **CommandPalette**: `features/CommandPalette.tsx`: Cmd+K global search across issues, projects, agents.
- **CommentThread**: `CommentThread.tsx`: Comment list + add-comment form on issue/entity detail views.
- **EmptyState**: `EmptyState.tsx`: `icon`, `message`, optional `action` + `onAction`. Use for empty lists.
- **EntityRow**: `EntityRow.tsx`: Standard list row. Slots: `leading`, `identifier`, `title`, `subtitle?`, `trailing?`. Supports `selected` and `onClick`. Wrap rows in a `border border-border rounded-md` container.
- **FilterBar**: `FilterBar.tsx`: Filter chip strip. `filters: { key, label, value }[]`, `onRemove(key)`, `onClear()`.
- **GoalTree**: `GoalTree.tsx`: Hierarchical goal tree with expand/collapse, used on the goals page.
- **Identity**: `Identity.tsx`: Avatar + name pair. Sizes `sm` / `default` / `lg`. Initials are derived from the name when no `avatarUrl` is given.
- **InlineEditor**: `InlineEditor.tsx`: Click-to-edit text. Renders as the underlying `as` element until clicked. Enter saves, Escape cancels.
- **Layout**: `Layout.tsx`: Three-zone app shell: sidebar (`w-60`) + main + properties panel (`w-80`). Wraps every route.
- **MetricCard**: `MetricCard.tsx`: Dashboard stat card. Always render in `grid md:grid-cols-2 xl:grid-cols-4 gap-4`.
- **NewAgentDialog**: `features/NewAgentDialog.tsx`: Create-agent dialog.
- **NewIssueDialog**: `features/NewIssueDialog.tsx`: Create-issue dialog with project/assignee/priority and draft saving.
- **NewProjectDialog**: `features/NewProjectDialog.tsx`: Create-project dialog.
- **OnboardingWizard**: `features/OnboardingWizard.tsx`: Multi-step onboarding flow for new users/projects.
- **PageSkeleton**: `PageSkeleton.tsx`: Full-page loading skeleton. `variant: "list" | "detail"`.
- **PriorityIcon**: `PriorityIcon.tsx`: `priority: "critical" | "high" | "medium" | "low"`. Pass `onChange` to make it interactive.
- **PropertiesPanel**: `PropertiesPanel.tsx`: Right-side panel (`w-80`), closeable, shown on detail views.
- **ProjectSwitcher**: `ProjectSwitcher.tsx`: Project selector dropdown in the sidebar header.
- **Sidebar / SidebarSection / SidebarNavItem**: `Sidebar.tsx`, `SidebarSection.tsx`, `SidebarNavItem.tsx`: Left-nav primitives. Sidebar contains ProjectSwitcher, search, new-issue, and SidebarSections (collapsible groups). Each SidebarNavItem takes an icon, label, and optional badge count.
- **StatusBadge**: `StatusBadge.tsx`: Colored status pill. Supports 20+ statuses; never hardcode status colors elsewhere.
- **StatusIcon**: `StatusIcon.tsx`: Status circle. Pass `onChange` to open a popover picker. Supports `backlog`, `todo`, `in_progress`, `in_review`, `done`, `cancelled`, `blocked`.

### Per-entity property panels

These render *inside* `PropertiesPanel` and all follow the same row pattern: `text-xs text-muted-foreground` label on the left, value on the right, `py-1.5` row spacing.

| Component | File | Entity |
| --- | --- | --- |
| IssueProperties | `IssueProperties.tsx` | issues |
| AgentProperties | `AgentProperties.tsx` | agents |
| ProjectProperties | `ProjectProperties.tsx` | projects |
| GoalProperties | `GoalProperties.tsx` | goals |

---

## shadcn primitives

These live in `ui/src/components/ui/`. **Out of scope for restyling**: extend via composition, never edit in place.

`button`, `card` (CardHeader / CardTitle / CardDescription / CardAction / CardContent / CardFooter), `input`, `badge`, `label`, `select`, `separator`, `checkbox`, `textarea`, `avatar` (+ AvatarGroup, AvatarGroupCount), `breadcrumb`, `command` (cmdk), `dialog`, `dropdown-menu`, `popover`, `tabs` (`variant: "pill" | "line"`), `tooltip` (app is wrapped in TooltipProvider - don't add another), `scroll-area`, `collapsible`, `skeleton`, `sheet`.

Notable variants worth knowing without opening the file:

- **Button** sizes: `xs`, `sm`, `default`, `lg`, `icon`, `icon-xs`, `icon-sm`, `icon-lg`. Variants: `default`, `secondary`, `outline`, `ghost`, `destructive`, `link`. Implemented via CVA - extend by composing on top, not by editing variants.
- **Avatar** sizes: `sm`, `default`, `lg`: these match the three sizes `Identity` accepts.
- **Tabs** has two visual variants: `pill` (default) and `line` (underline).
- **Badge** vs **StatusBadge**: use `Badge` for generic labels, `StatusBadge` for any entity status. They are not interchangeable.

---

## Utilities and hooks

- **`cn(...)`**: `lib/utils.ts`: clsx + tailwind-merge. Required in every component that conditionally composes classes:
  ```tsx
  import { cn } from "@/lib/utils";
  <div className={cn("base", isActive && "bg-accent", className)} />
  ```

- **Formatting**: `lib/utils.ts`:

  | Function | Returns |
  | --- | --- |
  | `formatCents(cents)` | `"$12.34"` |
  | `formatDate(date)` | `"Jan 15, 2025"` |
  | `relativeTime(date)` | `"2m ago"` for recent, falls back to `"Jan 15"` |
  | `formatTokens(count)` | `"1.2M"`, `"500k"`, etc. |

- **`useKeyboardShortcuts`**: `hooks/useKeyboardShortcuts.ts`: Registers Cmd+K, `C`, `[`, `]`, Cmd+Enter at app scope. Don't register these per-page.

- **`queryKeys`**: `lib/queryKeys.ts`: Structured React Query key factories. Always import from here rather than inlining string arrays.

- **`groupBy`**: `lib/groupBy.ts`: Generic array grouping helper.

---

## Composition recipes

### A list of issues

```tsx
<div className="rounded-md border border-border">
  {issues.map(issue => (
    <EntityRow
      key={issue.id}
      leading={<>
        <StatusIcon status={issue.status} />
        <PriorityIcon priority={issue.priority} />
      </>}
      identifier={issue.identifier}
      title={issue.title}
      trailing={<StatusBadge status={issue.status} />}
      onClick={() => navigate(`/issues/${issue.id}`)}
    />
  ))}
</div>
```

### A dashboard stat strip

```tsx
<div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
  <MetricCard icon={Bot} value={agents.length} label="Active Agents" description="+3 this week" />
  {/* … */}
</div>
```

### A user/agent reference inline

```tsx
<Identity name="Backend Agent" size="sm" avatarUrl={agent.avatarUrl} />
```

### An empty list

```tsx
<EmptyState icon={Inbox} message="No items yet." action="Create Item" onAction={openCreate} />
```

---

## When to add a new component here

A new entry belongs in this index if **at least two unrelated views import it**. One-off components stay co-located with their consumer. When promoting a one-off to shared, also add a row above and a recipe if its composition isn't obvious from props alone.
