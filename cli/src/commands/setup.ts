import * as p from "@clack/prompts";
import path from "node:path";
import pc from "picocolors";
import {
  AUTH_BASE_URL_MODES,
  DEPLOYMENT_EXPOSURES,
  DEPLOYMENT_MODES,
  SECRET_PROVIDERS,
  STORAGE_PROVIDERS,
  type AuthBaseUrlMode,
  type DeploymentExposure,
  type DeploymentMode,
  type SecretProvider,
  type StorageProvider,
} from "@gitmesh/core";
import { configExists, readConfig, resolveConfigPath, writeConfig } from "../config/store.js";
import type { GitmeshConfig } from "../config/schema.js";
import { ensureAgentJwtSecret, resolveAgentJwtEnvFile } from "../config/env.js";
import { ensureLocalSecretsKeyFile } from "../config/secrets-key.js";
import { promptDatabase } from "../prompts/database.js";
import { promptLlm } from "../prompts/llm.js";
import { promptLogging } from "../prompts/logging.js";
import { defaultSecretsConfig } from "../prompts/secrets.js";
import { defaultStorageConfig, promptStorage } from "../prompts/storage.js";
import { promptServer } from "../prompts/server.js";
import {
  describeLocalInstancePaths,
  expandHomePrefix,
  resolveDefaultBackupDir,
  resolveDefaultEmbeddedPostgresDir,
  resolveDefaultLogsDir,
  resolveGitmeshInstanceId,
} from "../config/home.js";
import { bootstrapAdminInvite } from "./auth-bootstrap-admin.js";
import { printGitmeshCliBanner } from "../utils/banner.js";
import { runWizard, type WizardStep } from "./_shared/wizard.js";

type SetupMode = "quickstart" | "advanced";

type SetupOptions = {
  config?: string;
  run?: boolean;
  yes?: boolean;
  invokedByRun?: boolean;
};

type SetupDefaults = Pick<
  GitmeshConfig,
  "database" | "logging" | "server" | "auth" | "storage" | "secrets"
>;

interface SetupState extends SetupDefaults {
  llm?: GitmeshConfig["llm"];
  setupMode: SetupMode;
}

// ---------------------------------------------------------------------------
// Env-derived defaults - same surface as before, factored into typed helpers.
// ---------------------------------------------------------------------------

const SETUP_ENV_KEYS = [
  "GITMESH_PUBLIC_URL",
  "DATABASE_URL",
  "GITMESH_DB_BACKUP_ENABLED",
  "GITMESH_DB_BACKUP_INTERVAL_MINUTES",
  "GITMESH_DB_BACKUP_RETENTION_DAYS",
  "GITMESH_DB_BACKUP_DIR",
  "GITMESH_DEPLOYMENT_MODE",
  "GITMESH_DEPLOYMENT_EXPOSURE",
  "HOST",
  "PORT",
  "SERVE_UI",
  "GITMESH_ALLOWED_HOSTNAMES",
  "GITMESH_AUTH_BASE_URL_MODE",
  "GITMESH_AUTH_PUBLIC_BASE_URL",
  "BETTER_AUTH_URL",
  "BETTER_AUTH_BASE_URL",
  "GITMESH_STORAGE_PROVIDER",
  "GITMESH_STORAGE_LOCAL_DIR",
  "GITMESH_STORAGE_S3_BUCKET",
  "GITMESH_STORAGE_S3_REGION",
  "GITMESH_STORAGE_S3_ENDPOINT",
  "GITMESH_STORAGE_S3_PREFIX",
  "GITMESH_STORAGE_S3_FORCE_PATH_STYLE",
  "GITMESH_SECRETS_PROVIDER",
  "GITMESH_SECRETS_STRICT_MODE",
  "GITMESH_SECRETS_MASTER_KEY_FILE",
] as const;

function parseBooleanFromEnv(raw: string | undefined): boolean | null {
  if (raw === undefined) return null;
  const lower = raw.trim().toLowerCase();
  if (lower === "true" || lower === "1" || lower === "yes") return true;
  if (lower === "false" || lower === "0" || lower === "no") return false;
  return null;
}

function parseNumberFromEnv(raw: string | undefined): number | null {
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseEnumFromEnv<T extends string>(
  raw: string | undefined,
  allowed: readonly T[],
): T | null {
  if (!raw) return null;
  return allowed.includes(raw as T) ? (raw as T) : null;
}

function resolvePathFromEnv(raw: string | undefined): string | null {
  if (!raw || raw.trim().length === 0) return null;
  return path.resolve(expandHomePrefix(raw.trim()));
}

function pickPublicUrl(): string | undefined {
  return (
    process.env.GITMESH_PUBLIC_URL?.trim() ||
    process.env.GITMESH_AUTH_PUBLIC_BASE_URL?.trim() ||
    process.env.BETTER_AUTH_URL?.trim() ||
    process.env.BETTER_AUTH_BASE_URL?.trim() ||
    undefined
  );
}

function hostnameFromUrl(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.trim().toLowerCase();
  } catch {
    return null;
  }
}

function quickstartDefaultsFromEnv(): {
  defaults: SetupDefaults;
  usedEnvKeys: string[];
  ignoredEnvKeys: Array<{ key: string; reason: string }>;
} {
  const instanceId = resolveGitmeshInstanceId();
  const defaultStorage = defaultStorageConfig();
  const defaultSecrets = defaultSecretsConfig();
  const databaseUrl = process.env.DATABASE_URL?.trim() || undefined;
  const publicUrl = pickPublicUrl();
  const deploymentMode =
    parseEnumFromEnv<DeploymentMode>(process.env.GITMESH_DEPLOYMENT_MODE, DEPLOYMENT_MODES) ??
    "local_trusted";
  const deploymentExposureFromEnv = parseEnumFromEnv<DeploymentExposure>(
    process.env.GITMESH_DEPLOYMENT_EXPOSURE,
    DEPLOYMENT_EXPOSURES,
  );
  const deploymentExposure =
    deploymentMode === "local_trusted" ? "private" : (deploymentExposureFromEnv ?? "private");
  const authPublicBaseUrl = publicUrl;
  const authBaseUrlModeFromEnv = parseEnumFromEnv<AuthBaseUrlMode>(
    process.env.GITMESH_AUTH_BASE_URL_MODE,
    AUTH_BASE_URL_MODES,
  );
  const authBaseUrlMode = authBaseUrlModeFromEnv ?? (authPublicBaseUrl ? "explicit" : "auto");
  const allowedHostnamesFromEnv = process.env.GITMESH_ALLOWED_HOSTNAMES
    ? process.env.GITMESH_ALLOWED_HOSTNAMES
        .split(",")
        .map((value) => value.trim().toLowerCase())
        .filter((value) => value.length > 0)
    : [];
  const hostnameFromPublicUrl = hostnameFromUrl(publicUrl);
  const storageProvider =
    parseEnumFromEnv<StorageProvider>(process.env.GITMESH_STORAGE_PROVIDER, STORAGE_PROVIDERS) ??
    defaultStorage.provider;
  const secretsProvider =
    parseEnumFromEnv<SecretProvider>(process.env.GITMESH_SECRETS_PROVIDER, SECRET_PROVIDERS) ??
    defaultSecrets.provider;
  const databaseBackupEnabled = parseBooleanFromEnv(process.env.GITMESH_DB_BACKUP_ENABLED) ?? true;
  const databaseBackupIntervalMinutes = Math.max(
    1,
    parseNumberFromEnv(process.env.GITMESH_DB_BACKUP_INTERVAL_MINUTES) ?? 60,
  );
  const databaseBackupRetentionDays = Math.max(
    1,
    parseNumberFromEnv(process.env.GITMESH_DB_BACKUP_RETENTION_DAYS) ?? 30,
  );

  const defaults: SetupDefaults = {
    database: {
      mode: databaseUrl ? "postgres" : "embedded-postgres",
      ...(databaseUrl ? { connectionString: databaseUrl } : {}),
      embeddedPostgresDataDir: resolveDefaultEmbeddedPostgresDir(instanceId),
      embeddedPostgresPort: 54329,
      backup: {
        enabled: databaseBackupEnabled,
        intervalMinutes: databaseBackupIntervalMinutes,
        retentionDays: databaseBackupRetentionDays,
        dir:
          resolvePathFromEnv(process.env.GITMESH_DB_BACKUP_DIR) ??
          resolveDefaultBackupDir(instanceId),
      },
    },
    logging: {
      mode: "file",
      logDir: resolveDefaultLogsDir(instanceId),
    },
    server: {
      deploymentMode,
      exposure: deploymentExposure,
      host: process.env.HOST ?? "127.0.0.1",
      port: Number(process.env.PORT) || 3100,
      allowedHostnames: Array.from(
        new Set([
          ...allowedHostnamesFromEnv,
          ...(hostnameFromPublicUrl ? [hostnameFromPublicUrl] : []),
        ]),
      ),
      serveUi: parseBooleanFromEnv(process.env.SERVE_UI) ?? true,
    },
    auth: {
      baseUrlMode: authBaseUrlMode,
      disableSignUp: false,
      ...(authPublicBaseUrl ? { publicBaseUrl: authPublicBaseUrl } : {}),
    },
    storage: {
      provider: storageProvider,
      localDisk: {
        baseDir:
          resolvePathFromEnv(process.env.GITMESH_STORAGE_LOCAL_DIR) ??
          defaultStorage.localDisk.baseDir,
      },
      s3: {
        bucket: process.env.GITMESH_STORAGE_S3_BUCKET ?? defaultStorage.s3.bucket,
        region: process.env.GITMESH_STORAGE_S3_REGION ?? defaultStorage.s3.region,
        endpoint: process.env.GITMESH_STORAGE_S3_ENDPOINT ?? defaultStorage.s3.endpoint,
        prefix: process.env.GITMESH_STORAGE_S3_PREFIX ?? defaultStorage.s3.prefix,
        forcePathStyle:
          parseBooleanFromEnv(process.env.GITMESH_STORAGE_S3_FORCE_PATH_STYLE) ??
          defaultStorage.s3.forcePathStyle,
      },
    },
    secrets: {
      provider: secretsProvider,
      strictMode:
        parseBooleanFromEnv(process.env.GITMESH_SECRETS_STRICT_MODE) ?? defaultSecrets.strictMode,
      localEncrypted: {
        keyFilePath:
          resolvePathFromEnv(process.env.GITMESH_SECRETS_MASTER_KEY_FILE) ??
          defaultSecrets.localEncrypted.keyFilePath,
      },
    },
  };

  const ignoredEnvKeys: Array<{ key: string; reason: string }> = [];
  if (deploymentMode === "local_trusted" && process.env.GITMESH_DEPLOYMENT_EXPOSURE !== undefined) {
    ignoredEnvKeys.push({
      key: "GITMESH_DEPLOYMENT_EXPOSURE",
      reason: "Ignored because deployment mode local_trusted always forces private exposure",
    });
  }

  const ignoredKeySet = new Set(ignoredEnvKeys.map((entry) => entry.key));
  const usedEnvKeys = SETUP_ENV_KEYS.filter(
    (key) => process.env[key] !== undefined && !ignoredKeySet.has(key),
  );
  return { defaults, usedEnvKeys, ignoredEnvKeys };
}

// ---------------------------------------------------------------------------
// Side effects pulled out of the linear flow
// ---------------------------------------------------------------------------

async function maybeTestDatabaseConnection(database: GitmeshConfig["database"]): Promise<void> {
  if (database.mode !== "postgres" || !database.connectionString) return;
  const spinner = p.spinner();
  spinner.start("Testing database connection...");
  try {
    const { createDb } = await import("@gitmesh/data");
    const db = createDb(database.connectionString);
    await db.execute("SELECT 1");
    spinner.stop("Database connection successful");
  } catch {
    spinner.stop(
      pc.yellow(
        "Could not connect to database - you can fix this later with `gitmesh-agents doctor`",
      ),
    );
  }
}

async function maybeValidateLlmKey(llm: GitmeshConfig["llm"] | undefined): Promise<void> {
  if (!llm?.apiKey) return;
  const spinner = p.spinner();
  spinner.start("Validating API key...");
  try {
    if (llm.provider === "claude") {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "x-api-key": llm.apiKey,
          "anthropic-version": "2023-06-01",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          model: "claude-sonnet-4-5-20250929",
          max_tokens: 1,
          messages: [{ role: "user", content: "hi" }],
        }),
      });
      if (res.ok || res.status === 400) spinner.stop("API key is valid");
      else if (res.status === 401)
        spinner.stop(pc.yellow("API key appears invalid - you can update it later"));
      else spinner.stop(pc.yellow("Could not validate API key - continuing anyway"));
    } else {
      const res = await fetch("https://api.openai.com/v1/models", {
        headers: { Authorization: `Bearer ${llm.apiKey}` },
      });
      if (res.ok) spinner.stop("API key is valid");
      else if (res.status === 401)
        spinner.stop(pc.yellow("API key appears invalid - you can update it later"));
      else spinner.stop(pc.yellow("Could not validate API key - continuing anyway"));
    }
  } catch {
    spinner.stop(pc.yellow("Could not reach API - continuing anyway"));
  }
}

function applySecretsDefaults(secrets: GitmeshConfig["secrets"]): GitmeshConfig["secrets"] {
  const fallback = defaultSecretsConfig();
  return {
    provider: secrets.provider ?? fallback.provider,
    strictMode: secrets.strictMode ?? fallback.strictMode,
    localEncrypted: {
      keyFilePath:
        secrets.localEncrypted?.keyFilePath ?? fallback.localEncrypted.keyFilePath,
    },
  };
}

// ---------------------------------------------------------------------------
// Step list
// ---------------------------------------------------------------------------

interface AdvancedStepDeps {
  // Allow tests / future callers to swap implementations if needed.
  promptDatabase: typeof promptDatabase;
  promptLlm: typeof promptLlm;
  promptLogging: typeof promptLogging;
  promptServer: typeof promptServer;
  promptStorage: typeof promptStorage;
}

function buildAdvancedSteps(deps: AdvancedStepDeps): ReadonlyArray<WizardStep<SetupState>> {
  return [
    {
      title: "Database",
      when: (s) => s.setupMode === "advanced",
      async run(state) {
        const database = await deps.promptDatabase(state.database);
        await maybeTestDatabaseConnection(database);
        return { database };
      },
    },
    {
      title: "LLM Provider",
      when: (s) => s.setupMode === "advanced",
      async run() {
        const llm = await deps.promptLlm();
        await maybeValidateLlmKey(llm);
        return { llm };
      },
    },
    {
      title: "Logging",
      when: (s) => s.setupMode === "advanced",
      async run() {
        const logging = await deps.promptLogging();
        return { logging };
      },
    },
    {
      title: "Server",
      when: (s) => s.setupMode === "advanced",
      async run(state) {
        const { server, auth } = await deps.promptServer({
          currentServer: state.server,
          currentAuth: state.auth,
        });
        return { server, auth };
      },
    },
    {
      title: "Storage",
      when: (s) => s.setupMode === "advanced",
      async run(state) {
        const storage = await deps.promptStorage(state.storage);
        return { storage };
      },
    },
    {
      title: "Secrets",
      when: (s) => s.setupMode === "advanced",
      run(state) {
        const secrets = applySecretsDefaults(state.secrets);
        p.log.message(
          pc.dim(
            `Using defaults: provider=${secrets.provider}, strictMode=${secrets.strictMode}, keyFile=${secrets.localEncrypted.keyFilePath}`,
          ),
        );
        return { secrets };
      },
    },
  ];
}

// ---------------------------------------------------------------------------
// Top-level entry
// ---------------------------------------------------------------------------

async function chooseSetupMode(yes: boolean): Promise<SetupMode | null> {
  if (yes) {
    p.log.message(pc.dim("`--yes` enabled: using Quickstart defaults."));
    return "quickstart";
  }
  const choice = await p.select({
    message: "Choose setup path",
    options: [
      {
        value: "quickstart" as const,
        label: "Quickstart",
        hint: "Recommended: local defaults + ready to run",
      },
      {
        value: "advanced" as const,
        label: "Advanced setup",
        hint: "Customize database, server, storage, and more",
      },
    ],
    initialValue: "quickstart",
  });
  if (p.isCancel(choice)) {
    p.cancel("Setup cancelled.");
    return null;
  }
  return choice as SetupMode;
}

function logQuickstartHeader(
  state: SetupState,
  usedEnvKeys: string[],
  ignoredEnvKeys: Array<{ key: string; reason: string }>,
): void {
  if (state.setupMode !== "quickstart") return;
  p.log.step(pc.bold("Quickstart"));
  p.log.message(pc.dim("Using quickstart defaults."));
  if (usedEnvKeys.length > 0) {
    p.log.message(
      pc.dim(`Environment-aware defaults active (${usedEnvKeys.length} env var(s) detected).`),
    );
  } else {
    p.log.message(
      pc.dim(
        "No environment overrides detected: embedded database, file storage, local encrypted secrets.",
      ),
    );
  }
  for (const ignored of ignoredEnvKeys) {
    p.log.message(pc.dim(`Ignored ${ignored.key}: ${ignored.reason}`));
  }
}

function logSummary(config: GitmeshConfig): void {
  const { database, logging, server, auth, storage, secrets, llm } = config;
  p.note(
    [
      `Database: ${database.mode}`,
      llm ? `LLM: ${llm.provider}` : "LLM: not configured",
      `Logging: ${logging.mode} -> ${logging.logDir}`,
      `Server: ${server.deploymentMode}/${server.exposure} @ ${server.host}:${server.port}`,
      `Allowed hosts: ${server.allowedHostnames.length > 0 ? server.allowedHostnames.join(", ") : "(loopback only)"}`,
      `Auth URL mode: ${auth.baseUrlMode}${auth.publicBaseUrl ? ` (${auth.publicBaseUrl})` : ""}`,
      `Storage: ${storage.provider}`,
      `Secrets: ${secrets.provider} (strict mode ${secrets.strictMode ? "on" : "off"})`,
      "Agent auth: GITMESH_AGENT_JWT_SECRET configured",
    ].join("\n"),
    "Configuration saved",
  );

  p.note(
    [
      `Run: ${pc.cyan("gitmesh-agents run")}`,
      `Reconfigure later: ${pc.cyan("gitmesh-agents configure")}`,
      `Diagnose setup: ${pc.cyan("gitmesh-agents doctor")}`,
    ].join("\n"),
    "Next commands",
  );
}

export async function setup(opts: SetupOptions): Promise<void> {
  printGitmeshCliBanner();
  p.intro(pc.bgCyan(pc.black(" gitmesh-agents setup ")));
  const configPath = resolveConfigPath(opts.config);
  const instance = describeLocalInstancePaths(resolveGitmeshInstanceId());
  p.log.message(
    pc.dim(
      `Local home: ${instance.homeDir} | instance: ${instance.instanceId} | config: ${configPath}`,
    ),
  );

  if (configExists(opts.config)) {
    p.log.message(pc.dim(`${configPath} exists, updating config`));
    try {
      readConfig(opts.config);
    } catch (err) {
      p.log.message(
        pc.yellow(
          `Existing config appears invalid and will be updated.\n${err instanceof Error ? err.message : String(err)}`,
        ),
      );
    }
  }

  const setupMode = await chooseSetupMode(Boolean(opts.yes));
  if (setupMode === null) return;

  const { defaults, usedEnvKeys, ignoredEnvKeys } = quickstartDefaultsFromEnv();
  const initialState: SetupState = { ...defaults, setupMode };

  // Quickstart logging is conditional and emitted before the (potentially
  // empty) advanced steps run.
  logQuickstartHeader(initialState, usedEnvKeys, ignoredEnvKeys);

  const finalState = await runWizard({
    initial: initialState,
    steps: buildAdvancedSteps({
      promptDatabase,
      promptLlm,
      promptLogging,
      promptServer,
      promptStorage,
    }),
  });

  // Agent JWT bootstrap (always applies regardless of mode).
  const jwtSecret = ensureAgentJwtSecret(configPath);
  const envFilePath = resolveAgentJwtEnvFile(configPath);
  if (jwtSecret.created) {
    p.log.success(`Created ${pc.cyan("GITMESH_AGENT_JWT_SECRET")} in ${pc.dim(envFilePath)}`);
  } else if (process.env.GITMESH_AGENT_JWT_SECRET?.trim()) {
    p.log.info(`Using existing ${pc.cyan("GITMESH_AGENT_JWT_SECRET")} from environment`);
  } else {
    p.log.info(`Using existing ${pc.cyan("GITMESH_AGENT_JWT_SECRET")} in ${pc.dim(envFilePath)}`);
  }

  const config: GitmeshConfig = {
    $meta: {
      version: 1,
      updatedAt: new Date().toISOString(),
      source: "setup",
    },
    ...(finalState.llm && { llm: finalState.llm }),
    database: finalState.database,
    logging: finalState.logging,
    server: finalState.server,
    auth: finalState.auth,
    storage: finalState.storage,
    secrets: finalState.secrets,
  };

  const keyResult = ensureLocalSecretsKeyFile(config, configPath);
  if (keyResult.status === "created") {
    p.log.success(`Created local secrets key file at ${pc.dim(keyResult.path)}`);
  } else if (keyResult.status === "existing") {
    p.log.message(pc.dim(`Using existing local secrets key file at ${keyResult.path}`));
  }

  writeConfig(config, opts.config);
  logSummary(config);

  if (config.server.deploymentMode === "authenticated") {
    p.log.step("Generating bootstrap admin invite");
    await bootstrapAdminInvite({ config: configPath });
  }

  let shouldRunNow = opts.run === true || opts.yes === true;
  if (!shouldRunNow && !opts.invokedByRun && process.stdin.isTTY && process.stdout.isTTY) {
    const answer = await p.confirm({
      message: "Start Gitmesh now?",
      initialValue: true,
    });
    if (!p.isCancel(answer)) {
      shouldRunNow = answer;
    }
  }

  if (shouldRunNow && !opts.invokedByRun) {
    process.env.GITMESH_OPEN_ON_LISTEN = "true";
    const { runCommand } = await import("./run.js");
    await runCommand({ config: configPath, repair: true, yes: true });
    return;
  }

  p.outro("You're all set!");
}
