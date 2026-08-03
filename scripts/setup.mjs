#!/usr/bin/env node
/**
 * Cross-platform one-command setup for GitMesh.
 *
 * Works on Windows, macOS, and Linux. From a fresh checkout, this script:
 *   1. Verifies Node 20+ is installed
 *   2. Enables corepack and pins pnpm if missing
 *   3. Copies .env.example → .env if .env does not yet exist
 *   4. Runs `pnpm install`
 *   5. Builds the workspace (`pnpm build`) so dist/* is populated
 *   6. Optionally starts the dev server when invoked with --start
 *
 * Usage:
 *   node scripts/setup.mjs           # install + build, do not start
 *   node scripts/setup.mjs --start   # install + build + run pnpm dev
 *   node scripts/setup.mjs --skip-build
 *   node scripts/setup.mjs --with-docker-db  # start docker-compose db too
 */

import { spawn } from "node:child_process";
import { existsSync, copyFileSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";
import os from "node:os";

const __filename = fileURLToPath(import.meta.url);
const repoRoot = resolve(dirname(__filename), "..");
const isWindows = process.platform === "win32";

const args = new Set(process.argv.slice(2));
const SHOULD_START = args.has("--start");
const SKIP_BUILD = args.has("--skip-build");
const WITH_DOCKER_DB = args.has("--with-docker-db");

const reset = "\x1b[0m";
const dim = "\x1b[2m";
const green = "\x1b[32m";
const yellow = "\x1b[33m";
const red = "\x1b[31m";
const bold = "\x1b[1m";
const cyan = "\x1b[36m";

function step(msg) {
  console.log(`\n${bold}${cyan}▶ ${msg}${reset}`);
}
function ok(msg) {
  console.log(`  ${green}✓${reset} ${msg}`);
}
function warn(msg) {
  console.log(`  ${yellow}⚠${reset} ${msg}`);
}
function fail(msg) {
  console.error(`  ${red}✗ ${msg}${reset}`);
}

function run(cmd, cmdArgs, opts = {}) {
  return new Promise((resolveProm, rejectProm) => {
    const child = spawn(cmd, cmdArgs, {
      stdio: opts.stdio ?? "inherit",
      cwd: opts.cwd ?? repoRoot,
      env: { ...process.env, ...(opts.env ?? {}) },
      shell: isWindows && opts.shell !== false,
    });
    child.on("error", rejectProm);
    child.on("close", (code) => {
      if (code === 0) resolveProm();
      else rejectProm(new Error(`${cmd} exited with code ${code}`));
    });
  });
}

function runCapture(cmd, cmdArgs) {
  return new Promise((resolveProm) => {
    const child = spawn(cmd, cmdArgs, {
      cwd: repoRoot,
      shell: isWindows,
    });
    let stdout = "";
    child.stdout?.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.on("error", () => resolveProm({ ok: false, stdout: "" }));
    child.on("close", (code) => {
      resolveProm({ ok: code === 0, stdout: stdout.trim() });
    });
  });
}

async function checkNodeVersion() {
  step("Checking Node.js version");
  const major = Number.parseInt(process.versions.node.split(".")[0], 10);
  if (Number.isNaN(major) || major < 20) {
    fail(
      `Node ${process.versions.node} detected. GitMesh requires Node 20 or newer. Install from https://nodejs.org/ and re-run.`,
    );
    process.exit(1);
  }
  ok(`Node ${process.versions.node}`);
}

async function ensurePnpm() {
  step("Ensuring pnpm is available");
  const { ok: hasPnpm, stdout } = await runCapture("pnpm", ["--version"]);
  if (hasPnpm && stdout) {
    ok(`pnpm ${stdout}`);
    return;
  }
  warn("pnpm not found; enabling via corepack");
  try {
    await run("corepack", ["enable"]);
    await run("corepack", ["prepare", "pnpm@9.15.4", "--activate"]);
    ok("pnpm installed via corepack");
  } catch (err) {
    fail(`Could not install pnpm automatically: ${err.message}`);
    fail("Install manually: npm install -g pnpm@9.15.4");
    process.exit(1);
  }
}

async function ensureEnvFile() {
  step("Checking .env file");
  const envPath = resolve(repoRoot, ".env");
  const examplePath = resolve(repoRoot, ".env.example");

  if (existsSync(envPath)) {
    ok(".env exists - leaving untouched");
    return;
  }
  if (!existsSync(examplePath)) {
    warn("No .env.example found; skipping .env creation");
    return;
  }
  copyFileSync(examplePath, envPath);
  ok("Created .env from .env.example");
  console.log(
    `${dim}    Edit .env if you want to set GITHUB_LOCAL_DEV_PAT or switch to authenticated mode.${reset}`,
  );
}

async function pnpmInstall() {
  step("Installing workspace dependencies");
  // Use --no-frozen-lockfile so first-time setup works even if the committed
  // lockfile drifted from the user's pnpm version.
  await run("pnpm", ["install", "--no-frozen-lockfile"]);
  ok("Dependencies installed");
}

async function pnpmBuild() {
  if (SKIP_BUILD) {
    warn("--skip-build set; not running pnpm build");
    return;
  }
  step("Building workspace packages");
  await run("pnpm", ["build"]);
  ok("Workspace built");
}

async function maybeStartDockerDb() {
  if (!WITH_DOCKER_DB) return;
  step("Starting Postgres via docker-compose");
  const composeFile = resolve(repoRoot, "docker-compose.dev.yml");
  if (!existsSync(composeFile)) {
    warn("docker-compose.dev.yml not found; skipping Docker DB step");
    return;
  }
  // Try `docker compose` (v2) first, fall back to `docker-compose` (v1)
  const { ok: hasCompose } = await runCapture("docker", ["compose", "version"]);
  const composeCmd = hasCompose ? ["compose"] : [];
  const cmd = hasCompose ? "docker" : "docker-compose";
  const subArgs = hasCompose ? [...composeCmd, "-f", composeFile, "up", "-d"] : ["-f", composeFile, "up", "-d"];
  await run(cmd, subArgs);
  ok("Postgres container is up on localhost:5433");
}

function printNextSteps() {
  console.log(`
${bold}${green}✓ Setup complete${reset}

${bold}Next steps:${reset}
  ${cyan}pnpm dev${reset}              # Start API + UI on http://localhost:3100
  ${cyan}pnpm test:run${reset}         # Run the test suite
  ${cyan}pnpm gitmesh-agents --help${reset}  # Operator CLI

${bold}Optional:${reset}
  • To use GitHub in local dev without an OAuth App, set ${cyan}GITHUB_LOCAL_DEV_PAT${reset} in .env
    (create a token at https://github.com/settings/tokens with scopes: repo, admin:repo_hook,
    read:user, user:email).
  • To use Docker Postgres instead of embedded: ${cyan}pnpm db:up${reset} then set
    ${cyan}DATABASE_URL=postgres://gitmesh:gitmesh@localhost:5433/gitmesh${reset} in .env.

${dim}Docs: doc/DEVELOPING.md • doc/v1-spec.md • CLAUDE.md${reset}
`);
}

async function main() {
  console.log(`${bold}GitMesh setup${reset} ${dim}(${os.platform()} ${os.release()})${reset}`);
  try {
    await checkNodeVersion();
    await ensurePnpm();
    await ensureEnvFile();
    await maybeStartDockerDb();
    await pnpmInstall();
    await pnpmBuild();
    printNextSteps();

    if (SHOULD_START) {
      step("Starting dev server (Ctrl+C to stop)");
      await run("pnpm", ["dev"]);
    }
  } catch (err) {
    console.error(`\n${red}${bold}Setup failed:${reset} ${err.message}`);
    process.exit(1);
  }
}

main();
