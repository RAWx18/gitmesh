/**
 * `allowed-hostname`: append a hostname to the auth allowlist.
 *
 * Restructured around a small `applyAllowedHostname` pure helper so the
 * top-level command body is just a sequence of load → mutate → save → report
 * steps.
 */
import * as p from "@clack/prompts";
import pc from "picocolors";
import { normalizeHostnameInput } from "../config/hostnames.js";
import type { GitmeshConfig } from "../config/schema.js";
import { readConfig, resolveConfigPath, writeConfig } from "../config/store.js";

interface AllowedHostnameOpts {
  config?: string;
}

interface MutationResult {
  hostname: string;
  alreadyPresent: boolean;
}

/** Add `host` (after normalisation) to `config.server.allowedHostnames`. */
function applyAllowedHostname(config: GitmeshConfig, host: string): MutationResult {
  const hostname = normalizeHostnameInput(host);
  const current = new Set(
    (config.server.allowedHostnames ?? [])
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );
  const alreadyPresent = current.has(hostname);
  current.add(hostname);

  config.server.allowedHostnames = Array.from(current).sort();
  config.$meta.updatedAt = new Date().toISOString();
  config.$meta.source = "configure";

  return { hostname, alreadyPresent };
}

function isAllowlistEnforced(config: GitmeshConfig): boolean {
  return config.server.deploymentMode === "authenticated" && config.server.exposure === "private";
}

export async function addAllowedHostname(host: string, opts: AllowedHostnameOpts): Promise<void> {
  const configPath = resolveConfigPath(opts.config);
  const config = readConfig(opts.config);

  if (!config) {
    p.log.error(`No config found at ${configPath}. Run ${pc.cyan("gitmesh-agents setup")} first.`);
    return;
  }

  const { hostname, alreadyPresent } = applyAllowedHostname(config, host);
  writeConfig(config, opts.config);

  if (alreadyPresent) {
    p.log.info(`Hostname ${pc.cyan(hostname)} is already allowed.`);
  } else {
    p.log.success(`Added allowed hostname: ${pc.cyan(hostname)}`);
  }

  if (!isAllowlistEnforced(config)) {
    p.log.message(
      pc.dim("Note: allowed hostnames are enforced only in authenticated/private mode."),
    );
  }
}
