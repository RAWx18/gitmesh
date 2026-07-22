/**
 * Builds the publishable `gitmesh` binary (pivot T0.6).
 *
 * Bundles cli/src/gitmesh.ts — the same entry the monorepo runs in dev — into
 * a single self-contained dist/gitmesh.js, reusing the externals list from
 * cli/esbuild.config.mjs so both CLIs bundle workspace code identically.
 *
 * After bundling, the esbuild metafile is checked against this package's
 * manifest: every external package the bundle imports must be a declared
 * dependency (or a documented runtime-optional), and every declared
 * dependency must be imported. A drifting manifest fails the build instead
 * of failing `npx gitmesh-cli` on a user's machine.
 */

import { chmodSync, readFileSync, rmSync } from "node:fs";
import { builtinModules } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import esbuild from "esbuild";
import cliConfig from "../../cli/esbuild.config.mjs";

const packageDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(packageDir, "../..");

// Packages the bundle may reference at runtime without declaring as
// dependencies (loaded via dynamic import behind graceful error paths).
// Empty today: the gitmesh.ts entry ships a legacy stub, so no server or
// database code path is reachable (ADR-002).
const RUNTIME_OPTIONAL = new Set([]);

// Stale artifacts in dist/ would be published via files:["dist"].
rmSync(resolve(packageDir, "dist"), { recursive: true, force: true });

const result = await esbuild.build({
  ...cliConfig,
  absWorkingDir: packageDir,
  entryPoints: [resolve(repoRoot, "cli/src/gitmesh.ts")],
  outdir: undefined,
  outfile: "dist/gitmesh.js",
  splitting: false,
  metafile: true,
  // The published artifact ships no sourcemap — with sourcesContent it
  // triples the tarball for no end-user benefit.
  sourcemap: false,
});

chmodSync(resolve(packageDir, "dist/gitmesh.js"), 0o755);

// ── Manifest drift check ─────────────────────────────────────────────────────

/** Top-level package name of an import specifier, or null for builtins. */
function packageName(specifier) {
  if (specifier.startsWith("node:")) return null;
  const segments = specifier.split("/");
  const name = specifier.startsWith("@")
    ? segments.slice(0, 2).join("/")
    : segments[0];
  return builtinModules.includes(name) ? null : name;
}

const imported = new Set();
for (const output of Object.values(result.metafile.outputs)) {
  for (const entry of output.imports) {
    if (!entry.external) continue;
    const name = packageName(entry.path);
    if (name !== null) imported.add(name);
  }
}

const manifest = JSON.parse(
  readFileSync(resolve(packageDir, "package.json"), "utf8"),
);
const declared = new Set(Object.keys(manifest.dependencies ?? {}));

const missing = [...imported].filter(
  (name) => !declared.has(name) && !RUNTIME_OPTIONAL.has(name),
).sort();
const unused = [...declared].filter((name) => !imported.has(name)).sort();

if (missing.length > 0 || unused.length > 0) {
  if (missing.length > 0) {
    console.error(
      `gitmesh-cli build: bundle imports packages missing from dependencies: ${missing.join(", ")}`,
    );
  }
  if (unused.length > 0) {
    console.error(
      `gitmesh-cli build: declared dependencies never imported by the bundle: ${unused.join(", ")}`,
    );
  }
  process.exit(1);
}

console.log(
  `gitmesh-cli build: dist/gitmesh.js ok (${imported.size} external packages, all declared)`,
);
