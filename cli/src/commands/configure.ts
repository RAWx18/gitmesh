/**
 * `configure`: section-by-section reconfiguration of an existing config file.
 *
 * Restructured around a small map of section handlers; the body of the loop
 * is now flat (look up handler, run it, persist) instead of a long
 * switch/case. Behaviour is preserved exactly.
 */
import * as p from "@clack/prompts";
import pc from "picocolors";
import { readConfig, writeConfig, configExists, resolveConfigPath } from "../config/store.js";
import type { GitmeshConfig } from "../config/schema.js";
import { ensureLocalSecretsKeyFile } from "../config/secrets-key.js";
import { promptDatabase } from "../prompts/database.js";
import { promptLlm } from "../prompts/llm.js";
import { promptLogging } from "../prompts/logging.js";
import { defaultSecretsConfig, promptSecrets } from "../prompts/secrets.js";
import { defaultStorageConfig, promptStorage } from "../prompts/storage.js";
import { promptServer } from "../prompts/server.js";
import {
  resolveDefaultBackupDir,
  resolveDefaultEmbeddedPostgresDir,
  resolveDefaultLogsDir,
  resolveGitmeshInstanceId,
} from "../config/home.js";
import { printGitmeshCliBanner } from "../utils/banner.js";

type Section = "llm" | "database" | "logging" | "server" | "storage" | "secrets";

interface SectionHandler {
  label: string;
  apply: (config: GitmeshConfig, configPath: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Defaults builder
// ---------------------------------------------------------------------------

function defaultConfig(): GitmeshConfig {
  const instanceId = resolveGitmeshInstanceId();
  return {
    $meta: {
      version: 1,
      updatedAt: new Date().toISOString(),
      source: "configure",
    },
    database: {
      mode: "embedded-postgres",
      embeddedPostgresDataDir: resolveDefaultEmbeddedPostgresDir(instanceId),
      embeddedPostgresPort: 54329,
      backup: {
        enabled: true,
        intervalMinutes: 60,
        retentionDays: 30,
        dir: resolveDefaultBackupDir(instanceId),
      },
    },
    logging: {
      mode: "file",
      logDir: resolveDefaultLogsDir(instanceId),
    },
    server: {
      deploymentMode: "local_trusted",
      exposure: "private",
      host: "127.0.0.1",
      port: 3100,
      allowedHostnames: [],
      serveUi: true,
    },
    auth: {
      baseUrlMode: "auto",
      disableSignUp: false,
    },
    storage: defaultStorageConfig(),
    secrets: defaultSecretsConfig(),
  };
}

// ---------------------------------------------------------------------------
// Section handlers - one per configurable area.
// ---------------------------------------------------------------------------

const SECTION_HANDLERS: Record<Section, SectionHandler> = {
  database: {
    label: "Database",
    async apply(config) {
      config.database = await promptDatabase(config.database);
    },
  },
  llm: {
    label: "LLM Provider",
    async apply(config) {
      const llm = await promptLlm();
      if (llm) config.llm = llm;
      else delete config.llm;
    },
  },
  logging: {
    label: "Logging",
    async apply(config) {
      config.logging = await promptLogging();
    },
  },
  server: {
    label: "Server",
    async apply(config) {
      const { server, auth } = await promptServer({
        currentServer: config.server,
        currentAuth: config.auth,
      });
      config.server = server;
      config.auth = auth;
    },
  },
  storage: {
    label: "Storage",
    async apply(config) {
      config.storage = await promptStorage(config.storage);
    },
  },
  secrets: {
    label: "Secrets",
    async apply(config, configPath) {
      config.secrets = await promptSecrets(config.secrets);
      const keyResult = ensureLocalSecretsKeyFile(config, configPath);
      switch (keyResult.status) {
        case "created":
          p.log.success(`Created local secrets key file at ${pc.dim(keyResult.path)}`);
          break;
        case "existing":
          p.log.message(pc.dim(`Using existing local secrets key file at ${keyResult.path}`));
          break;
        case "skipped_provider":
          p.log.message(pc.dim("Skipping local key file management for non-local provider"));
          break;
        default:
          p.log.message(
            pc.dim("Skipping local key file management because GITMESH_SECRETS_MASTER_KEY is set"),
          );
      }
    },
  },
};

// ---------------------------------------------------------------------------
// Section selection
// ---------------------------------------------------------------------------

async function pickSection(): Promise<Section | null> {
  const choice = await p.select({
    message: "Which section do you want to configure?",
    options: (Object.entries(SECTION_HANDLERS) as Array<[Section, SectionHandler]>).map(
      ([value, handler]) => ({ value, label: handler.label }),
    ),
  });
  if (p.isCancel(choice)) {
    p.cancel("Configuration cancelled.");
    return null;
  }
  return choice;
}

function loadOrFallbackConfig(configPath: string | undefined): GitmeshConfig {
  try {
    return readConfig(configPath) ?? defaultConfig();
  } catch (err) {
    p.log.message(
      pc.yellow(
        `Existing config is invalid. Loading defaults so you can repair it now.\n${err instanceof Error ? err.message : String(err)}`,
      ),
    );
    return defaultConfig();
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export async function configure(opts: {
  config?: string;
  section?: string;
}): Promise<void> {
  printGitmeshCliBanner();
  p.intro(pc.bgCyan(pc.black(" gitmesh-agents configure ")));
  const configPath = resolveConfigPath(opts.config);

  if (!configExists(opts.config)) {
    p.log.error("No config file found. Run `gitmesh-agents setup` first.");
    p.outro("");
    return;
  }

  const config = loadOrFallbackConfig(opts.config);

  // Validate the explicitly-requested section name early.
  let section: Section | undefined = opts.section as Section | undefined;
  if (section && !(section in SECTION_HANDLERS)) {
    p.log.error(
      `Unknown section: ${section}. Choose from: ${Object.keys(SECTION_HANDLERS).join(", ")}`,
    );
    p.outro("");
    return;
  }

  const singleShot = Boolean(opts.section);

  while (true) {
    if (!section) {
      const picked = await pickSection();
      if (picked === null) return;
      section = picked;
    }

    const handler = SECTION_HANDLERS[section];
    p.log.step(pc.bold(handler.label));
    await handler.apply(config, configPath);

    config.$meta.updatedAt = new Date().toISOString();
    config.$meta.source = "configure";
    writeConfig(config, opts.config);
    p.log.success(`${handler.label} configuration updated.`);

    if (singleShot) break;

    const another = await p.confirm({
      message: "Configure another section?",
      initialValue: false,
    });
    if (p.isCancel(another) || !another) break;
    section = undefined; // reset to show picker
  }

  p.outro("Configuration saved.");
}
