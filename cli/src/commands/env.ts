/**
 * `env`: print deployment environment variables.
 *
 * Restructured around a declarative `EnvDescriptor` table: every variable is
 * described once (key, required-ness, where the value comes from, note), and
 * the renderer is a small loop over that table. The previous shape inlined
 * the same logic as a long imperative scope.
 */
import * as p from "@clack/prompts";
import pc from "picocolors";
import type { GitmeshConfig } from "../config/schema.js";
import { configExists, readConfig, resolveConfigPath } from "../config/store.js";
import {
  readAgentJwtSecretFromEnv,
  readAgentJwtSecretFromEnvFile,
  resolveAgentJwtEnvFile,
} from "../config/env.js";
import {
  resolveDefaultSecretsKeyFilePath,
  resolveDefaultStorageDir,
  resolveGitmeshInstanceId,
} from "../config/home.js";

type EnvSource = "env" | "config" | "file" | "default" | "missing";

interface EnvVarRow {
  key: string;
  value: string;
  source: EnvSource;
  required: boolean;
  note: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULTS = {
  agentJwtTtlSeconds: "172800",
  agentJwtIssuer: "gitmesh-agents",
  agentJwtAudience: "gitmesh-agents-api",
  heartbeatSchedulerIntervalMs: "30000",
  heartbeatSchedulerEnabled: "true",
  secretsProvider: "local_encrypted",
  storageProvider: "local_disk",
  s3Bucket: "gitmesh-agents",
  s3Region: "us-east-1",
} as const;

function instanceDefaultSecretsKeyFile(): string {
  return resolveDefaultSecretsKeyFilePath(resolveGitmeshInstanceId());
}
function instanceDefaultStorageBaseDir(): string {
  return resolveDefaultStorageDir(resolveGitmeshInstanceId());
}

// ---------------------------------------------------------------------------
// Source resolution helpers
// ---------------------------------------------------------------------------

/** Pick the first defined value, tagging it with where it came from. */
function pickWithSource<T extends string | undefined>(
  envValue: string | undefined,
  configValue: T,
  defaultValue?: string,
): { value: string; source: EnvSource } {
  if (envValue !== undefined && envValue !== null && envValue !== "") {
    return { value: envValue, source: "env" };
  }
  if (configValue !== undefined && configValue !== null && configValue !== "") {
    return { value: String(configValue), source: "config" };
  }
  if (defaultValue !== undefined) {
    return { value: defaultValue, source: "default" };
  }
  return { value: "", source: "missing" };
}

function pickPublicUrl(
  config: GitmeshConfig | null,
): { value: string; source: EnvSource } {
  const envCandidate =
    process.env.GITMESH_PUBLIC_URL ??
    process.env.GITMESH_AUTH_PUBLIC_BASE_URL ??
    process.env.BETTER_AUTH_URL ??
    process.env.BETTER_AUTH_BASE_URL;
  if (envCandidate) return { value: envCandidate, source: "env" };
  if (config?.auth?.publicBaseUrl) {
    return { value: config.auth.publicBaseUrl, source: "config" };
  }
  return { value: "", source: "missing" };
}

function deriveTrustedOrigins(publicUrl: string): string {
  if (!publicUrl) return "";
  try {
    return new URL(publicUrl).origin;
  } catch {
    return "";
  }
}

function resolveAgentJwt(configPath: string): { value: string; source: EnvSource; note: string } {
  const agentJwtEnvFile = resolveAgentJwtEnvFile(configPath);
  const fromEnv = readAgentJwtSecretFromEnv(configPath);
  if (fromEnv) {
    return { value: fromEnv, source: "env", note: "Set in process environment" };
  }
  const fromFile = readAgentJwtSecretFromEnvFile(agentJwtEnvFile);
  if (fromFile) {
    return { value: fromFile, source: "file", note: `Set in ${agentJwtEnvFile}` };
  }
  return {
    value: "",
    source: "missing",
    note: "Generate during setup or set manually (required for local adapter authentication)",
  };
}

// ---------------------------------------------------------------------------
// Row table - declarative description of every env variable we surface.
// ---------------------------------------------------------------------------

function collectDeploymentEnvRows(
  config: GitmeshConfig | null,
  configPath: string,
): EnvVarRow[] {
  const databaseMode = config?.database?.mode ?? "embedded-postgres";
  const databaseUrl = pickWithSource(process.env.DATABASE_URL, config?.database?.connectionString);
  const publicUrl = pickPublicUrl(config);
  const trustedOriginsDefault = deriveTrustedOrigins(publicUrl.value);
  const jwt = resolveAgentJwt(configPath);

  const port = pickWithSource(
    process.env.PORT,
    config?.server?.port !== undefined ? String(config.server.port) : undefined,
    "3100",
  );
  const heartbeatInterval = pickWithSource(
    process.env.HEARTBEAT_SCHEDULER_INTERVAL_MS,
    undefined,
    DEFAULTS.heartbeatSchedulerIntervalMs,
  );
  const heartbeatEnabled = pickWithSource(
    process.env.HEARTBEAT_SCHEDULER_ENABLED,
    undefined,
    DEFAULTS.heartbeatSchedulerEnabled,
  );
  const secretsProvider = pickWithSource(
    process.env.GITMESH_SECRETS_PROVIDER,
    config?.secrets?.provider,
    DEFAULTS.secretsProvider,
  );
  const secretsStrictMode = pickWithSource(
    process.env.GITMESH_SECRETS_STRICT_MODE,
    config?.secrets?.strictMode !== undefined ? String(config.secrets.strictMode) : undefined,
    "false",
  );
  const secretsKeyFilePath = pickWithSource(
    process.env.GITMESH_SECRETS_MASTER_KEY_FILE,
    config?.secrets?.localEncrypted?.keyFilePath,
    instanceDefaultSecretsKeyFile(),
  );
  const storageProvider = pickWithSource(
    process.env.GITMESH_STORAGE_PROVIDER,
    config?.storage?.provider,
    DEFAULTS.storageProvider,
  );
  const storageLocalDir = pickWithSource(
    process.env.GITMESH_STORAGE_LOCAL_DIR,
    config?.storage?.localDisk?.baseDir,
    instanceDefaultStorageBaseDir(),
  );
  const s3Bucket = pickWithSource(
    process.env.GITMESH_STORAGE_S3_BUCKET,
    config?.storage?.s3?.bucket,
    DEFAULTS.s3Bucket,
  );
  const s3Region = pickWithSource(
    process.env.GITMESH_STORAGE_S3_REGION,
    config?.storage?.s3?.region,
    DEFAULTS.s3Region,
  );
  const s3Endpoint = pickWithSource(
    process.env.GITMESH_STORAGE_S3_ENDPOINT,
    config?.storage?.s3?.endpoint,
    "",
  );
  const s3Prefix = pickWithSource(
    process.env.GITMESH_STORAGE_S3_PREFIX,
    config?.storage?.s3?.prefix,
    "",
  );
  const s3ForcePathStyle = pickWithSource(
    process.env.GITMESH_STORAGE_S3_FORCE_PATH_STYLE,
    config?.storage?.s3?.forcePathStyle !== undefined
      ? String(config.storage.s3.forcePathStyle)
      : undefined,
    "false",
  );
  const trustedOrigins = pickWithSource(
    process.env.BETTER_AUTH_TRUSTED_ORIGINS,
    undefined,
    trustedOriginsDefault || undefined,
  );

  const rows: EnvVarRow[] = [
    {
      key: "GITMESH_AGENT_JWT_SECRET",
      value: jwt.value,
      source: jwt.source,
      required: true,
      note: jwt.note,
    },
    {
      key: "DATABASE_URL",
      value: databaseUrl.value,
      source: databaseUrl.source === "default" ? "missing" : databaseUrl.source,
      required: true,
      note:
        databaseMode === "postgres"
          ? "Configured for postgres mode (required)"
          : "Required for live deployment with managed PostgreSQL",
    },
    { key: "PORT", value: port.value, source: port.source, required: false, note: "HTTP listen port" },
    {
      key: "GITMESH_PUBLIC_URL",
      value: publicUrl.value,
      source: publicUrl.source,
      required: false,
      note: "Canonical public URL for auth/callback/invite origin wiring",
    },
    {
      key: "BETTER_AUTH_TRUSTED_ORIGINS",
      value: trustedOrigins.value,
      source:
        trustedOrigins.source === "default" && !trustedOriginsDefault
          ? "missing"
          : trustedOrigins.source,
      required: false,
      note:
        "Comma-separated auth origin allowlist (auto-derived from GITMESH_PUBLIC_URL when possible)",
    },
    {
      key: "GITMESH_AGENT_JWT_TTL_SECONDS",
      value: process.env.GITMESH_AGENT_JWT_TTL_SECONDS ?? DEFAULTS.agentJwtTtlSeconds,
      source: process.env.GITMESH_AGENT_JWT_TTL_SECONDS ? "env" : "default",
      required: false,
      note: "JWT lifetime in seconds",
    },
    {
      key: "GITMESH_AGENT_JWT_ISSUER",
      value: process.env.GITMESH_AGENT_JWT_ISSUER ?? DEFAULTS.agentJwtIssuer,
      source: process.env.GITMESH_AGENT_JWT_ISSUER ? "env" : "default",
      required: false,
      note: "JWT issuer",
    },
    {
      key: "GITMESH_AGENT_JWT_AUDIENCE",
      value: process.env.GITMESH_AGENT_JWT_AUDIENCE ?? DEFAULTS.agentJwtAudience,
      source: process.env.GITMESH_AGENT_JWT_AUDIENCE ? "env" : "default",
      required: false,
      note: "JWT audience",
    },
    {
      key: "HEARTBEAT_SCHEDULER_INTERVAL_MS",
      value: heartbeatInterval.value,
      source: heartbeatInterval.source,
      required: false,
      note: "Heartbeat worker interval in ms",
    },
    {
      key: "HEARTBEAT_SCHEDULER_ENABLED",
      value: heartbeatEnabled.value,
      source: heartbeatEnabled.source,
      required: false,
      note: "Set to `false` to disable timer scheduling",
    },
    {
      key: "GITMESH_SECRETS_PROVIDER",
      value: secretsProvider.value,
      source: secretsProvider.source,
      required: false,
      note: "Default provider for new secrets",
    },
    {
      key: "GITMESH_SECRETS_STRICT_MODE",
      value: secretsStrictMode.value,
      source: secretsStrictMode.source,
      required: false,
      note: "Require secret refs for sensitive env keys",
    },
    {
      key: "GITMESH_SECRETS_MASTER_KEY_FILE",
      value: secretsKeyFilePath.value,
      source: secretsKeyFilePath.source,
      required: false,
      note: "Path to local encrypted secrets key file",
    },
    {
      key: "GITMESH_STORAGE_PROVIDER",
      value: storageProvider.value,
      source: storageProvider.source,
      required: false,
      note: "Storage provider (local_disk or s3)",
    },
    {
      key: "GITMESH_STORAGE_LOCAL_DIR",
      value: storageLocalDir.value,
      source: storageLocalDir.source,
      required: false,
      note: "Local storage base directory for local_disk provider",
    },
    {
      key: "GITMESH_STORAGE_S3_BUCKET",
      value: s3Bucket.value,
      source: s3Bucket.source,
      required: false,
      note: "S3 bucket name for s3 provider",
    },
    {
      key: "GITMESH_STORAGE_S3_REGION",
      value: s3Region.value,
      source: s3Region.source,
      required: false,
      note: "S3 region for s3 provider",
    },
    {
      key: "GITMESH_STORAGE_S3_ENDPOINT",
      value: s3Endpoint.value,
      source: s3Endpoint.source,
      required: false,
      note: "Optional custom endpoint for S3-compatible providers",
    },
    {
      key: "GITMESH_STORAGE_S3_PREFIX",
      value: s3Prefix.value,
      source: s3Prefix.source,
      required: false,
      note: "Optional object key prefix",
    },
    {
      key: "GITMESH_STORAGE_S3_FORCE_PATH_STYLE",
      value: s3ForcePathStyle.value,
      source: s3ForcePathStyle.source,
      required: false,
      note: "Set true for path-style access on compatible providers",
    },
  ];

  const defaultConfigPath = resolveConfigPath();
  if (process.env.GITMESH_CONFIG || configPath !== defaultConfigPath) {
    rows.push({
      key: "GITMESH_CONFIG",
      value: process.env.GITMESH_CONFIG ?? configPath,
      source: process.env.GITMESH_CONFIG ? "env" : "default",
      required: false,
      note: "Optional path override for config file",
    });
  }

  return rows;
}

// ---------------------------------------------------------------------------
// Renderer
// ---------------------------------------------------------------------------

const SOURCE_LABEL: Record<EnvSource, string> = {
  env: "environment",
  config: "config",
  file: "file",
  default: "default",
  missing: "missing",
};

function statusBadge(source: EnvSource): string {
  if (source === "missing") return pc.red("missing");
  if (source === "default") return pc.yellow("default");
  return pc.green("set");
}

function quoteShellValue(value: string): string {
  if (value === "") return "\"\"";
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function uniqueByKey(rows: EnvVarRow[]): EnvVarRow[] {
  const seen = new Set<string>();
  const result: EnvVarRow[] = [];
  for (const row of rows) {
    if (seen.has(row.key)) continue;
    seen.add(row.key);
    result.push(row);
  }
  return result;
}

function renderRow(row: EnvVarRow): string {
  const status = statusBadge(row.source);
  const valueSuffix =
    row.source === "missing" ? "" : ` ${pc.dim("=>")} ${pc.white(quoteShellValue(row.value))}`;
  return `${pc.cyan(row.key)} ${status.padEnd(7)} ${pc.dim(`[${SOURCE_LABEL[row.source]}] ${row.note}`)}${valueSuffix}`;
}

function logSection(title: string, rows: EnvVarRow[]): void {
  if (rows.length === 0) return;
  p.log.message(pc.bold(title));
  for (const row of rows) p.log.message(renderRow(row));
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export async function envCommand(opts: { config?: string }): Promise<void> {
  p.intro(pc.bgCyan(pc.black(" gitmesh-agents env ")));

  const configPath = resolveConfigPath(opts.config);
  let config: GitmeshConfig | null = null;
  let configReadError: string | null = null;

  if (configExists(opts.config)) {
    p.log.message(pc.dim(`Config file: ${configPath}`));
    try {
      config = readConfig(opts.config);
    } catch (err) {
      configReadError = err instanceof Error ? err.message : String(err);
      p.log.message(pc.yellow(`Could not parse config: ${configReadError}`));
    }
  } else {
    p.log.message(pc.dim(`Config file missing: ${configPath}`));
  }

  const rows = collectDeploymentEnvRows(config, configPath);
  const sortedRows = [...rows].sort(
    (a, b) => Number(b.required) - Number(a.required) || a.key.localeCompare(b.key),
  );

  logSection("Required environment variables", sortedRows.filter((row) => row.required));
  logSection("Optional environment variables", sortedRows.filter((row) => !row.required));

  const exportRows = rows.map((row) =>
    row.source === "missing" ? { ...row, value: "<set-this-value>" } : row,
  );
  const exportBlock = uniqueByKey(exportRows)
    .map((row) => `export ${row.key}=${quoteShellValue(row.value)}`)
    .join("\n");

  if (configReadError) {
    p.log.error(`Could not load config cleanly: ${configReadError}`);
  }

  p.note(
    exportBlock || "No values detected. Set required variables manually.",
    "Deployment export block",
  );

  const missingRequired = rows.filter((row) => row.required && row.source === "missing");
  if (missingRequired.length > 0) {
    p.log.message(
      pc.yellow(
        `Missing required values: ${missingRequired.map((row) => row.key).join(", ")}. Set these before deployment.`,
      ),
    );
  } else {
    p.log.message(pc.green("All required deployment variables are present."));
  }
  p.outro("Done");
}
