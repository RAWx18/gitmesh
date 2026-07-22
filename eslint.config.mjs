// @ts-check
import tseslint from "typescript-eslint";

/**
 * Pivot import-boundary lint (task T0.4).
 *
 * AGENTS.md hard rule 1 / pivot.md §9.2, §10.8: nothing in the new
 * workspace-compiler packages may depend on the legacy server runtime or any
 * database code path. `doctor` / `apply` / `check` are pure file operations.
 *
 * Scope is intentionally limited to the pivot packages — the legacy codebase
 * (`server/`, `ui/`, `cli/` legacy commands, old `lib/*`) is frozen and not
 * linted. New per-agent adapter packages must be added to this list as they
 * land (E1+).
 */
const PIVOT_PACKAGE_GLOBS = [
  "lib/workspace-core/**/*.{ts,tsx,mts,cts,js,mjs,cjs}",
  "lib/workspace-adapters/**/*.{ts,tsx,mts,cts,js,mjs,cjs}",
];

const RESTRICTED_IMPORT_PATTERNS = [
  {
    group: ["@gitmesh/server", "@gitmesh/server/**", "**/server", "**/server/**"],
    message:
      "Pivot boundary (AGENTS.md hard rule 1): workspace-core/adapters must not import the legacy server. doctor/apply/check are pure file operations.",
  },
  {
    group: ["drizzle*", "drizzle*/**"],
    message:
      "Pivot boundary (AGENTS.md hard rule 1): no Drizzle ORM in workspace-core/adapters — the new product has no database.",
  },
  {
    group: [
      "pg",
      "pg/**",
      "pg-*",
      "pg-*/**",
      "postgres",
      "postgres/**",
      "postgres-*",
      "postgres-*/**",
    ],
    message:
      "Pivot boundary (AGENTS.md hard rule 1): no Postgres client libraries in workspace-core/adapters — the new product has no database.",
  },
  {
    group: ["@gitmesh/data", "@gitmesh/data/**"],
    message:
      "Pivot boundary: @gitmesh/data is the legacy Drizzle/Postgres layer and must not leak into workspace-core/adapters.",
  },
];

export default tseslint.config(
  {
    // `data/` holds local Postgres state (unreadable, legacy-only) — never crawl it.
    ignores: ["**/dist/**", "**/node_modules/**", "data/**"],
  },
  {
    files: PIVOT_PACKAGE_GLOBS,
    languageOptions: {
      parser: tseslint.parser,
      ecmaVersion: "latest",
      sourceType: "module",
    },
    rules: {
      "no-restricted-imports": ["error", { patterns: RESTRICTED_IMPORT_PATTERNS }],
    },
  },
);
