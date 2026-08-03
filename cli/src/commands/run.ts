/**
 * `run`: bootstrap setup + doctor + start the gitmesh server.
 *
 * Restructured into three phases (`prepareInstanceFs`, `ensureConfigPresent`,
 * `runDoctorOrFail`) and a final server-import. Error formatting helpers were
 * pulled into a small namespace-style object for readability.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import * as p from "@clack/prompts";
import pc from "picocolors";
import { setup } from "./setup.js";
import { doctor } from "./doctor.js";
import { configExists, resolveConfigPath } from "../config/store.js";
import {
  describeLocalInstancePaths,
  resolveGitmeshHomeDir,
  resolveGitmeshInstanceId,
} from "../config/home.js";

interface RunOptions {
  config?: string;
  instance?: string;
  repair?: boolean;
  yes?: boolean;
}

// ---------------------------------------------------------------------------
// Phases
// ---------------------------------------------------------------------------

interface InstancePaths {
  homeDir: string;
  instanceId: string;
  configPath: string;
}

function prepareInstanceFs(opts: RunOptions): InstancePaths {
  const instanceId = resolveGitmeshInstanceId(opts.instance);
  process.env.GITMESH_INSTANCE_ID = instanceId;

  const homeDir = resolveGitmeshHomeDir();
  fs.mkdirSync(homeDir, { recursive: true });

  const paths = describeLocalInstancePaths(instanceId);
  fs.mkdirSync(paths.instanceRoot, { recursive: true });

  const configPath = resolveConfigPath(opts.config);
  process.env.GITMESH_CONFIG = configPath;

  return { homeDir: paths.homeDir, instanceId: paths.instanceId, configPath };
}

async function ensureConfigPresent(configPath: string): Promise<boolean> {
  if (configExists(configPath)) return true;

  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    p.log.error("No config found and terminal is non-interactive.");
    p.log.message(
      `Run ${pc.cyan("gitmesh-agents setup")} once, then retry ${pc.cyan("gitmesh-agents run")}.`,
    );
    process.exit(1);
  }

  p.log.step("No config found. Starting setup...");
  await setup({ config: configPath, invokedByRun: true });
  return true;
}

async function runDoctorOrFail(configPath: string, opts: RunOptions): Promise<void> {
  p.log.step("Running doctor checks...");
  const summary = await doctor({
    config: configPath,
    repair: opts.repair ?? true,
    yes: opts.yes ?? true,
  });
  if (summary.failed > 0) {
    p.log.error("Doctor found blocking issues. Not starting server.");
    process.exit(1);
  }
}

// ---------------------------------------------------------------------------
// Error helpers - collected into one object so they share a clear namespace.
// ---------------------------------------------------------------------------

const ServerImportErrors = {
  format(err: unknown): string {
    if (err instanceof Error) {
      if (err.message && err.message.trim().length > 0) return err.message;
      return err.name;
    }
    if (typeof err === "string") return err;
    try {
      return JSON.stringify(err);
    } catch {
      return String(err);
    }
  },

  isModuleNotFound(err: unknown): boolean {
    if (!(err instanceof Error)) return false;
    const code = (err as { code?: unknown }).code;
    if (code === "ERR_MODULE_NOT_FOUND") return true;
    return err.message.includes("Cannot find module");
  },

  missingSpecifier(err: unknown): string | null {
    if (!(err instanceof Error)) return null;
    const packageMatch = err.message.match(/Cannot find package '([^']+)' imported from/);
    if (packageMatch?.[1]) return packageMatch[1];
    const moduleMatch = err.message.match(/Cannot find module '([^']+)'/);
    if (moduleMatch?.[1]) return moduleMatch[1];
    return null;
  },
} as const;

// ---------------------------------------------------------------------------
// Server import - dev path first, fall through to packaged @gitmesh/server.
// ---------------------------------------------------------------------------

function maybeEnableUiDevMiddleware(entrypoint: string): void {
  if (process.env.GITMESH_UI_DEV_MIDDLEWARE !== undefined) return;
  const normalized = entrypoint.replaceAll("\\", "/");
  if (
    normalized.endsWith("/server/src/index.ts") ||
    normalized.endsWith("@gitmesh/server/src/index.ts")
  ) {
    process.env.GITMESH_UI_DEV_MIDDLEWARE = "true";
  }
}

async function importServerEntry(): Promise<void> {
  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
  const devEntry = path.resolve(projectRoot, "server/src/index.ts");

  if (fs.existsSync(devEntry)) {
    maybeEnableUiDevMiddleware(devEntry);
    await import(pathToFileURL(devEntry).href);
    return;
  }

  try {
    await import("@gitmesh/server");
  } catch (err) {
    const missingSpecifier = ServerImportErrors.missingSpecifier(err);
    const missingServerEntrypoint = !missingSpecifier || missingSpecifier === "@gitmesh/server";
    if (ServerImportErrors.isModuleNotFound(err) && missingServerEntrypoint) {
      throw new Error(
        `Could not locate a Gitmesh server entrypoint.\n` +
          `Tried: ${devEntry}, @gitmesh/server\n` +
          `${ServerImportErrors.format(err)}`,
      );
    }
    throw new Error(`Gitmesh server failed to start.\n${ServerImportErrors.format(err)}`);
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export async function runCommand(opts: RunOptions): Promise<void> {
  const paths = prepareInstanceFs(opts);

  p.intro(pc.bgCyan(pc.black(" gitmesh-agents run ")));
  p.log.message(pc.dim(`Home: ${paths.homeDir}`));
  p.log.message(pc.dim(`Instance: ${paths.instanceId}`));
  p.log.message(pc.dim(`Config: ${paths.configPath}`));

  await ensureConfigPresent(paths.configPath);
  await runDoctorOrFail(paths.configPath, opts);

  p.log.step("Starting Gitmesh server...");
  await importServerEntry();
}
