---
name: design-guide
description: >
  GitMesh Agents UI design system. Invoke this skill when creating new
  components, modifying existing ones, adding pages or features to the
  frontend, styling UI elements, or when you need to understand the design
  language. Covers component creation, design tokens, typography,
  status/priority systems, composition patterns, and the live
  /design-guide showcase page. Always pair with the frontend-design and
  web-design-guidelines skills.
---

# GitMesh Agents Design Guide

This guide is split into:

- **Section A - Foundations.** What the system is, what it's built on, and the tokens you draw from.
- **Section B - Building blocks.** Components, when to make new ones, how to compose them.
- **Section C - Working in the codebase.** File conventions, the showcase page, common mistakes.

Use this skill alongside `frontend-design` (visual polish) and
`web-design-guidelines` (web best practices).

---

## Section A - Foundations

### A.1 Stance

GitMesh Agents is a professional control plane - dense, keyboard-driven,
dark-themed by default. Every pixel earns its place.

The five non-negotiable principles:

1. **Density beats padding.** Show information without requiring clicks. Whitespace separates; it does not pad.
2. **Keyboard-first.** Global shortcuts (`Cmd+K`, `C`, `[`, `]`). Power users rarely touch the mouse.
3. **Contextual, not modal.** Inline editing over dialogs. Dropdowns over page navigations.
4. **Dark-themed by default.** Neutral grays (OKLCH), not pure black. Accent colour reserved for status / priority. Text is the primary visual element.
5. **Component-driven.** Reusable components capture conventions. Build at the right abstraction - not too granular, not monolithic.

### A.2 Stack

| Concern | Choice |
|---------|--------|
| Framework | React 19 + TypeScript + Vite |
| Styling | Tailwind CSS v4 with CSS variables (OKLCH) |
| UI primitives | shadcn/ui (new-york style, neutral base, CSS variables on) |
| Accessibility | Radix UI primitives |
| Icons | Lucide React (16px nav, 14px inline) |
| Variants | class-variance-authority (CVA) |
| Class merging | `clsx` + `tailwind-merge` via the `cn()` utility |

Path aliases live in `ui/components.json`: `@/components`,
`@/components/ui`, `@/lib`, `@/hooks`.

### A.3 Tokens

All tokens are CSS variables in `ui/src/index.css`. Both light and dark
themes use OKLCH. **Never use raw hex / rgb values - always use a
semantic token.**

#### Colour tokens

| Token pair | Used for |
|------------|----------|
| `--background` / `--foreground` | Page background and primary text |
| `--card` / `--card-foreground` | Card surfaces |
| `--primary` / `--primary-foreground` | Primary actions and emphasis |
| `--secondary` / `--secondary-foreground` | Secondary surfaces |
| `--muted` / `--muted-foreground` | Subdued text and labels |
| `--accent` / `--accent-foreground` | Hover states and active nav |
| `--destructive` | Destructive actions |
| `--border` | All borders |
| `--ring` | Focus rings |
| `--sidebar-*` | Sidebar-specific variants |
| `--chart-1`...`--chart-5` | Data visualisation |

#### Radius

A single base `--radius` (0.625rem) drives a small ladder:

- `rounded-sm`: small inputs, pills
- `rounded-md`: buttons, inputs, small components
- `rounded-lg`: cards, dialogs
- `rounded-xl`: card containers, large components
- `rounded-full`: badges, avatars, status dots

Hard ceiling: `rounded-xl` (except `rounded-full`). No `rounded-2xl`.

#### Shadows

Minimal: `shadow-xs` for outline buttons, `shadow-sm` for cards. Nothing
heavier - no `shadow-md` and up.

### A.4 Typography scale

Use these patterns exactly. Do not invent new ones.

| Pattern | Classes | Where it lives |
|---------|---------|----------------|
| Page title | `text-xl font-bold` | Top of pages |
| Section title | `text-lg font-semibold` | Major sections |
| Section heading | `text-sm font-semibold text-muted-foreground uppercase tracking-wide` | Design guide, sidebar |
| Card title | `text-sm font-medium` or `text-sm font-semibold` | Card headers, list item titles |
| Body | `text-sm` | Default body text |
| Muted body | `text-sm text-muted-foreground` | Descriptions, secondary text |
| Tiny label | `text-xs text-muted-foreground` | Metadata, timestamps, property labels |
| Mono identifier | `text-xs font-mono text-muted-foreground` | Issue keys (`GM-001`), CSS vars |
| Large stat | `text-2xl font-bold` | Dashboard metric values |
| Code / log | `font-mono text-xs` | Log output, snippets |

### A.5 Status & priority systems

Status colour is consistent across every entity that has a status. The
mapping lives in `StatusBadge.tsx` and `StatusIcon.tsx`:

| Status (any of) | Colour | Entity types |
|-----------------|--------|--------------|
| `active`, `achieved`, `completed`, `succeeded`, `approved`, `done` | green shades | Agents, goals, issues, approvals |
| `running` | cyan | Agents |
| `paused` | orange | Agents |
| `idle`, `pending` | yellow | Agents, approvals |
| `failed`, `error`, `rejected`, `blocked` | red shades | Runs, agents, approvals, issues |
| `archived`, `planned`, `backlog`, `cancelled` | neutral gray | Various |
| `todo` | blue | Issues |
| `in_progress` | indigo | Issues |
| `in_review` | violet | Issues |

Priority icons (`PriorityIcon.tsx`):

- Critical &rarr; red `AlertTriangle`
- High &rarr; orange `ArrowUp`
- Medium &rarr; yellow `Minus`
- Low &rarr; blue `ArrowDown`

Inline agent status dots: `running` (cyan, `animate-pulse`), `active`
(green), `paused` (yellow), `error` (red), `offline` (neutral).

### A.6 Layout

Three-zone shell defined in `Layout.tsx`:

- **Sidebar**: `w-60`, collapsible, hosts `ProjectSwitcher` and `SidebarSections`.
- **Main content**: `flex-1`, scrollable.
- **Properties panel**: `w-80`, only shown on detail views, hidden on lists.

---

## Section B - Building blocks

### B.1 Component hierarchy

Three tiers, in order of growing app-specificity:

1. **shadcn/ui primitives**: `ui/src/components/ui/`. Button, Card, Input, Badge, Dialog, Tabs, etc. **Do not modify these directly - extend through composition.**
2. **Custom composites**: `ui/src/components/`. StatusBadge, EntityRow, MetricCard, etc. These encode GitMesh-specific design language.
3. **Pages**: `ui/src/pages/`. Compose primitives + composites into routes.

The complete inventory lives in
[`references/component-index.md`](references/component-index.md). Treat
that file as the canonical list of available components.

### B.2 When (and when not) to make a new component

Make a new component when:

- the same visual pattern appears in **two or more** places;
- the pattern carries interactive behaviour (status changes, inline editing);
- the pattern encodes domain logic (status colours, priority icons).

**Don't** make a component for:

- one-off layouts specific to a single page;
- simple className combinations - use Tailwind directly;
- thin wrappers that add no semantic value.

### B.3 Composition patterns

These patterns may not all be a single component, but they must be
applied consistently wherever they appear.

#### Entity row with status + priority

The standard list-item shape for issues and similar entities:

```tsx
<EntityRow
  leading={<><StatusIcon status="in_progress" /><PriorityIcon priority="high" /></>}
  identifier="GM-001"
  title="Implement authentication flow"
  subtitle="Assigned to Agent Alpha"
  trailing={<StatusBadge status="in_progress" />}
  onClick={() => {}}
/>
```

Leading slot ordering is fixed: `StatusIcon` first, then `PriorityIcon`.
Trailing slot is a `StatusBadge` or a timestamp.

#### Grouped list (status header + rows)

```tsx
<div className="flex items-center gap-2 px-4 py-2 bg-muted/50 rounded-t-md">
  <StatusIcon status="in_progress" />
  <span className="text-sm font-medium">In Progress</span>
  <span className="text-xs text-muted-foreground ml-1">2</span>
</div>
<div className="border border-border rounded-b-md">
  <EntityRow ... />
  <EntityRow ... />
</div>
```

#### Property row (label / value pairs)

```tsx
<div className="flex items-center justify-between py-1.5">
  <span className="text-xs text-muted-foreground">Status</span>
  <StatusBadge status="active" />
</div>
```

The label is always `text-xs text-muted-foreground`; the value sits on
the right; the container uses `space-y-1`.

#### Metric card grid (dashboard)

```tsx
<div className="grid md:grid-cols-2 xl:grid-cols-4 gap-4">
  <MetricCard icon={Bot} value={12} label="Active Agents" description="+3 this week" />
  ...
</div>
```

#### Budget progress bar (threshold-coloured)

Colour by threshold: green at `<60%`, yellow at `60&ndash;85%`, red at `>85%`.

```tsx
<div className="w-full h-2 bg-muted rounded-full overflow-hidden">
  <div className="h-full rounded-full bg-green-400" style={{ width: `${pct}%` }} />
</div>
```

#### Comment thread

Author header (name + timestamp), then body, in bordered cards with
`space-y-3`. Composer textarea + primary button below.

#### Cost table

Plain `<table>` with `text-xs`, header row `bg-accent/20`, `font-mono`
on numeric values.

#### Log viewer

`bg-neutral-950 rounded-lg p-3 font-mono text-xs` container. Colour
lines by level: default (`foreground`), `WARN` (`yellow-400`), `ERROR`
(`red-400`), `SYS` (`blue-300`). Include a live indicator dot when
streaming.

### B.4 Interactive patterns

| Concern | Tailwind |
|---------|----------|
| Entity row hover | `hover:bg-accent/50` |
| Nav item hover | `hover:bg-accent/50 hover:text-accent-foreground` |
| Active nav item | `bg-accent text-accent-foreground` |
| Focus | `focus-visible:ring-ring focus-visible:ring-[3px]` |
| Disabled | `disabled:opacity-50 disabled:pointer-events-none` |
| Inline editing | Use the `InlineEditor` component - click to edit, `Enter` saves, `Escape` cancels |
| Popover selectors | `StatusIcon` and `PriorityIcon` use Radix Popover for inline selection. Match this pattern for any clickable property that opens a picker. |

---

## Section C - Working in the codebase

### C.1 File conventions

| Kind | Path / casing |
|------|---------------|
| shadcn primitives | `ui/src/components/ui/{component}.tsx` (lowercase, kebab-case) |
| Custom components | `ui/src/components/{ComponentName}.tsx` (PascalCase) |
| Pages | `ui/src/pages/{PageName}.tsx` (PascalCase) |
| Utilities | `ui/src/lib/{name}.ts` |
| Hooks | `ui/src/hooks/{useName}.ts` |
| API modules | `ui/src/api/{entity}.ts` |
| Context providers | `ui/src/context/{Name}Context.tsx` |

All components merge classes with `cn()` from `@/lib/utils`. All
components with multiple visual variants use CVA.

### C.2 The `/design-guide` page

- **Location.** `ui/src/pages/DesignGuide.tsx`
- **Route.** `/design-guide`

This is the **living showcase** for every component and pattern. It is
the source of truth for how things look. Three rules:

1. When you add a new reusable component, you **must** add it to the design guide. Show all variants, sizes, and states.
2. When you change an existing component's API, update its design guide section in the same change.
3. When you add a new composition pattern, add a section demonstrating it.

Section structure to follow:

```tsx
<Section title="My New Component">
  <SubSection title="Variants">
    {/* show all variants */}
  </SubSection>
  <SubSection title="Sizes">
    {/* show all sizes */}
  </SubSection>
  <SubSection title="States">
    {/* show interactive / disabled states */}
  </SubSection>
</Section>
```

Section ordering is logical: foundations (colours, typography) first,
then primitives, then composites, then patterns.

### C.3 Workflow when you add a new reusable component

1. Add it under `ui/src/components/` (PascalCase).
2. Register it in [`references/component-index.md`](references/component-index.md).
3. Show every variant / size / state on `/design-guide`.
4. Follow the naming and file conventions in &sect;C.1.

### C.4 Mistakes to avoid

- Raw hex / rgb values instead of CSS variable tokens.
- Inventing typography styles instead of using the established scale.
- Hardcoding status colours instead of using `StatusBadge` / `StatusIcon`.
- Building one-off styled elements when a reusable component already exists.
- Shipping a new component without updating the `/design-guide` page.
- Using `shadow-md` or heavier - keep shadows at `xs` / `sm` only.
- Using `rounded-2xl` or larger - the cap is `rounded-xl` (except `rounded-full` for pills and dots).
- Forgetting dark mode - always use semantic tokens; never hardcode light or dark values.
