#!/usr/bin/env node
/**
 * generate-npm-package-json.mjs
 *
 * Reads the dev package.json (which has workspace:* refs) and produces
 * a publishable package.json in cli/ with:
 *   - workspace:* dependencies of bundled packages removed
 *   - all external npm dependencies from those packages inlined
 *   - workspace packages esbuild leaves external kept as versioned deps
 *   - proper metadata for npm
 *
 * The bundled/external package lists come from cli/esbuild.config.mjs so the
 * manifest always describes the bundle that was actually built.
 *
 * Reads from cli/package.dev.json if it exists (build already ran),
 * otherwise from cli/package.json.
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { externalWorkspacePackages, workspacePaths } from "../cli/esbuild.config.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..");

function readPkg(relativePath) {
  return JSON.parse(readFileSync(resolve(repoRoot, relativePath, "package.json"), "utf8"));
}

// Collect all external dependencies from all workspace packages
const allDeps = {};
const allOptionalDeps = {};

for (const pkgPath of workspacePaths) {
  const pkg = readPkg(pkgPath);
  const deps = pkg.dependencies || {};
  const optDeps = pkg.optionalDependencies || {};

  for (const [name, version] of Object.entries(deps)) {
    // Workspace packages are bundled by esbuild, so they need no dependency
    // entry — except the ones esbuild leaves external, which are published
    // separately and must resolve at runtime.
    const externalDir = externalWorkspacePackages.get(name);
    if (externalDir) {
      allDeps[name] = `^${readPkg(externalDir).version}`;
      continue;
    }
    if (name.startsWith("@gitmesh/")) continue;
    // Keep the more specific (pinned) version if conflict
    if (!allDeps[name] || !version.startsWith("^")) {
      allDeps[name] = version;
    }
  }

  for (const [name, version] of Object.entries(optDeps)) {
    allOptionalDeps[name] = version;
  }
}

// Sort alphabetically
const sortedDeps = Object.fromEntries(Object.entries(allDeps).sort(([a], [b]) => a.localeCompare(b)));
const sortedOptDeps = Object.fromEntries(
  Object.entries(allOptionalDeps).sort(([a], [b]) => a.localeCompare(b)),
);

// Read the CLI package metadata — prefer the dev backup if it exists
const devPkgPath = resolve(repoRoot, "cli/package.dev.json");
const cliPkg = existsSync(devPkgPath)
  ? JSON.parse(readFileSync(devPkgPath, "utf8"))
  : readPkg("cli");

// Build the publishable package.json
const publishPkg = {
  name: cliPkg.name,
  version: cliPkg.version,
  description: cliPkg.description,
  type: cliPkg.type,
  bin: cliPkg.bin,
  keywords: cliPkg.keywords,
  license: cliPkg.license,
  repository: cliPkg.repository,
  homepage: cliPkg.homepage,
  files: cliPkg.files,
  engines: { node: ">=20" },
  dependencies: sortedDeps,
};

if (Object.keys(sortedOptDeps).length > 0) {
  publishPkg.optionalDependencies = sortedOptDeps;
}

const output = JSON.stringify(publishPkg, null, 2) + "\n";
const outPath = resolve(repoRoot, "cli/package.json");
writeFileSync(outPath, output);

console.log(`  ✓  Generated publishable package.json (${Object.keys(sortedDeps).length} deps)`);
console.log(`     Version: ${cliPkg.version}`);
