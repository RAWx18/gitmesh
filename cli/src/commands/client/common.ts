import pc from "picocolors";
import type { Command } from "commander";
import { readConfig } from "../../config/store.js";
import {
  readContext,
  resolveProfile,
  type ClientContextProfile,
} from "../../client/context.js";
import { ApiRequestError, GitmeshApiClient, gitmeshClient } from "../../client/http.js";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface BaseClientOptions {
  config?: string;
  dataDir?: string;
  context?: string;
  profile?: string;
  apiBase?: string;
  apiKey?: string;
  projectId?: string;
  json?: boolean;
}

export interface ResolvedClientContext {
  api: GitmeshApiClient;
  /** Typed-resource builder for callers that want `.issues.list()` style. */
  resources: ReturnType<typeof gitmeshClient>;
  projectId?: string;
  profileName: string;
  profile: ClientContextProfile;
  json: boolean;
}

interface ResolveOptions {
  requireProject?: boolean;
}

// ---------------------------------------------------------------------------
// Common option registration
// ---------------------------------------------------------------------------

/**
 * Standard set of client-context flags shared by every subcommand below the
 * `gitmesh-agents` root that talks to the API. Kept identical to the previous
 * surface so help output is byte-stable.
 */
export function addCommonClientOptions(
  command: Command,
  opts?: { includeProject?: boolean },
): Command {
  command
    .option("-c, --config <path>", "Path to GitMesh Agents config file")
    .option(
      "-d, --data-dir <path>",
      "GitMesh Agents data directory root (isolates state from ~/.gitmesh-agents)",
    )
    .option("--context <path>", "Path to CLI context file")
    .option("--profile <name>", "CLI context profile name")
    .option("--api-base <url>", "Base URL for the GitMesh Agents API")
    .option("--api-key <token>", "Bearer token for agent-authenticated calls")
    .option("--json", "Output raw JSON");

  if (opts?.includeProject) {
    command.option("-P, --project-id <id>", "Project ID (overrides context default)");
  }

  return command;
}

// ---------------------------------------------------------------------------
// Resolver pipeline
// ---------------------------------------------------------------------------

interface ProfileSlice {
  profileName: string;
  profile: ClientContextProfile;
}

function loadProfileSlice(options: BaseClientOptions): ProfileSlice {
  const context = readContext(options.context);
  const { name, profile } = resolveProfile(context, options.profile);
  return { profileName: name, profile };
}

function readKeyFromProfileEnv(profile: ClientContextProfile): string | undefined {
  if (!profile.apiKeyEnvVarName) return undefined;
  const value = process.env[profile.apiKeyEnvVarName];
  return value?.trim() ? value.trim() : undefined;
}

function inferApiBaseFromConfig(configPath?: string): string {
  const envHost = process.env.GITMESH_SERVER_HOST?.trim() || "localhost";
  let port = Number(process.env.GITMESH_SERVER_PORT || "");

  if (!Number.isFinite(port) || port <= 0) {
    try {
      const config = readConfig(configPath);
      port = Number(config?.server?.port ?? 3100);
    } catch {
      port = 3100;
    }
  }

  if (!Number.isFinite(port) || port <= 0) {
    port = 3100;
  }

  return `http://${envHost}:${port}`;
}

interface MergedTransport {
  apiBase: string;
  apiKey?: string;
  projectId?: string;
}

function mergeFromEnvironment(
  options: BaseClientOptions,
  slice: ProfileSlice,
): MergedTransport {
  const apiBase =
    options.apiBase?.trim() ||
    process.env.GITMESH_API_URL?.trim() ||
    slice.profile.apiBase ||
    inferApiBaseFromConfig(options.config);

  const apiKey =
    options.apiKey?.trim() ||
    process.env.GITMESH_API_KEY?.trim() ||
    readKeyFromProfileEnv(slice.profile);

  const projectId =
    options.projectId?.trim() ||
    process.env.GITMESH_PROJECT_ID?.trim() ||
    slice.profile.projectId;

  return { apiBase, apiKey, projectId };
}

/**
 * Newer-style resolver. Returns the same `ResolvedClientContext` shape that
 * `resolveCommandContext` returns; `resolveCommandContext` is kept as an alias
 * so the existing test in `__tests__/common.test.ts` continues to exercise
 * the same surface.
 */
export function clientContext(
  options: BaseClientOptions,
  resolve?: ResolveOptions,
): ResolvedClientContext {
  const slice = loadProfileSlice(options);
  const transport = mergeFromEnvironment(options, slice);

  if (resolve?.requireProject && !transport.projectId) {
    throw new Error(
      "Project ID is required. Pass --project-id, set GITMESH_PROJECT_ID, or set context profile projectId via `gitmesh-agents context set`.",
    );
  }

  const api = new GitmeshApiClient({
    apiBase: transport.apiBase,
    apiKey: transport.apiKey,
  });
  const resources = gitmeshClient({
    apiBase: transport.apiBase,
    apiKey: transport.apiKey,
  });

  return {
    api,
    resources,
    projectId: transport.projectId,
    profileName: slice.profileName,
    profile: slice.profile,
    json: Boolean(options.json),
  };
}

/** Backwards-compatible alias for `clientContext`: kept for callers/tests. */
export function resolveCommandContext(
  options: BaseClientOptions,
  opts?: ResolveOptions,
): ResolvedClientContext {
  return clientContext(options, opts);
}

// ---------------------------------------------------------------------------
// Output helpers
// ---------------------------------------------------------------------------

const RECORD_KEY_PRIORITY = ["identifier", "id", "name", "status", "priority", "title", "action"] as const;
const VALUE_TRUNCATION = 90;

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") {
    const compact = value.replace(/\s+/g, " ").trim();
    return compact.length > VALUE_TRUNCATION
      ? `${compact.slice(0, VALUE_TRUNCATION - 3)}...`
      : compact;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "[object]";
}

export function formatInlineRecord(record: Record<string, unknown>): string {
  const seen = new Set<string>();
  const parts: string[] = [];

  for (const key of RECORD_KEY_PRIORITY) {
    if (!(key in record)) continue;
    parts.push(`${key}=${renderValue(record[key])}`);
    seen.add(key);
  }

  for (const [key, value] of Object.entries(record)) {
    if (seen.has(key)) continue;
    if (typeof value === "object") continue;
    parts.push(`${key}=${renderValue(value)}`);
  }

  return parts.join(" ");
}

function printArray(items: unknown[]): void {
  if (items.length === 0) {
    console.log(pc.dim("(empty)"));
    return;
  }
  for (const item of items) {
    if (typeof item === "object" && item !== null) {
      console.log(formatInlineRecord(item as Record<string, unknown>));
    } else {
      console.log(String(item));
    }
  }
}

/**
 * Render a CLI result. Behaviour matches the previous flat helper exactly,
 * just split into smaller branches that read top-down.
 */
export function printOutput(
  data: unknown,
  opts: { json?: boolean; label?: string } = {},
): void {
  if (opts.json) {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  if (opts.label) {
    console.log(pc.bold(opts.label));
  }

  if (Array.isArray(data)) {
    printArray(data);
    return;
  }

  if (data === undefined || data === null) {
    console.log(pc.dim("(null)"));
    return;
  }

  if (typeof data === "object") {
    console.log(JSON.stringify(data, null, 2));
    return;
  }

  console.log(String(data));
}

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

export function handleCommandError(error: unknown): never {
  if (error instanceof ApiRequestError) {
    const detailSuffix =
      error.details !== undefined ? ` details=${JSON.stringify(error.details)}` : "";
    console.error(pc.red(`API error ${error.status}: ${error.message}${detailSuffix}`));
    process.exit(1);
  }

  const message = error instanceof Error ? error.message : String(error);
  console.error(pc.red(message));
  process.exit(1);
}
