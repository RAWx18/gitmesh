import { describe, expect, it } from "vitest";
import { ESLint } from "eslint";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Guards the T0.4 import-boundary lint config against rot: if
 * eslint.config.mjs stops flagging server/Drizzle/Postgres imports inside the
 * pivot packages (or stops covering those packages at all), these tests fail
 * even though `pnpm lint` would happily pass.
 */

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const eslint = new ESLint({ cwd: repoRoot });

/** Lints a snippet as if it lived at `file`, returning boundary violations. */
async function boundaryErrors(file: string, code: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath: join(repoRoot, file) });
  return result.messages
    .filter((m) => m.ruleId === "no-restricted-imports")
    .map((m) => m.message);
}

const FORBIDDEN_IMPORTS = [
  '@gitmesh/server',
  '@gitmesh/server/src/index.js',
  '../../../server/src/index.js',
  'drizzle-orm',
  'drizzle-orm/pg-core',
  'drizzle-kit',
  'pg',
  'pg-pool',
  'postgres',
  '@gitmesh/data',
  '@gitmesh/data/schema.js',
];

const ALLOWED_IMPORTS = [
  'zod',
  'node:fs',
  '@gitmesh/workspace-core',
  './registry.js',
];

describe.each([
  "lib/workspace-core/src/__boundary_probe__.ts",
  "lib/workspace-adapters/src/__boundary_probe__.ts",
])("import boundary in %s", (probeFile) => {
  it.each(FORBIDDEN_IMPORTS)("rejects import of %s", async (specifier) => {
    const errors = await boundaryErrors(probeFile, `import "${specifier}";\n`);
    expect(errors.length).toBeGreaterThan(0);
  });

  it.each(FORBIDDEN_IMPORTS)("rejects re-export from %s", async (specifier) => {
    const errors = await boundaryErrors(probeFile, `export * from "${specifier}";\n`);
    expect(errors.length).toBeGreaterThan(0);
  });

  it.each(ALLOWED_IMPORTS)("allows import of %s", async (specifier) => {
    const errors = await boundaryErrors(probeFile, `import "${specifier}";\n`);
    expect(errors).toEqual([]);
  });

  it("parses TypeScript syntax (rule applies to real sources, not just JS)", async () => {
    const code = 'import type { Sql } from "postgres";\nexport interface X { db: Sql }\n';
    const errors = await boundaryErrors(probeFile, code);
    expect(errors.length).toBeGreaterThan(0);
  });
});
