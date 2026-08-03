/**
 * `doctor`: diagnostic suite for an existing config.
 *
 * Restructured around a declarative `Probe[]` pipeline. Each probe is a small
 * (name, run, repair?) descriptor; the runner executes them in order, calls
 * `maybeRepair` on each, and bails early when the bootstrap config check
 * fails. Output text and exit semantics are preserved.
 */
import * as p from "@clack/prompts";
import pc from "picocolors";
import type { GitmeshConfig } from "../config/schema.js";
import { readConfig, resolveConfigPath } from "../config/store.js";
import {
  agentJwtSecretCheck,
  configCheck,
  databaseCheck,
  deploymentAuthCheck,
  llmCheck,
  logCheck,
  portCheck,
  secretsCheck,
  storageCheck,
  type CheckResult,
} from "../checks/index.js";
import { printGitmeshCliBanner } from "../utils/banner.js";

const STATUS_ICON = {
  pass: pc.green("✓"),
  warn: pc.yellow("!"),
  fail: pc.red("✗"),
} as const;

interface DoctorOpts {
  config?: string;
  repair?: boolean;
  yes?: boolean;
}

interface ProbeContext {
  config: GitmeshConfig;
  configPath: string;
  rawConfigOption: string | undefined;
}

interface Probe {
  /**
   * Run the check. May be sync or async. Probes that can't apply (e.g. they
   * skip on a particular config shape) can return null to drop themselves.
   */
  run: (ctx: ProbeContext) => Promise<CheckResult> | CheckResult;
}

// ---------------------------------------------------------------------------
// Probe pipeline - order matches the previous numbered steps.
// ---------------------------------------------------------------------------

const PROBES: Probe[] = [
  { run: ({ config }) => deploymentAuthCheck(config) },
  { run: ({ rawConfigOption }) => agentJwtSecretCheck(rawConfigOption) },
  { run: ({ config, configPath }) => secretsCheck(config, configPath) },
  { run: ({ config, configPath }) => storageCheck(config, configPath) },
  { run: ({ config, configPath }) => databaseCheck(config, configPath) },
  { run: ({ config }) => llmCheck(config) },
  { run: ({ config, configPath }) => logCheck(config, configPath) },
  { run: ({ config }) => portCheck(config) },
];

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

function printResult(result: CheckResult): void {
  const icon = STATUS_ICON[result.status];
  p.log.message(`${icon} ${pc.bold(result.name)}: ${result.message}`);
  if (result.status !== "pass" && result.repairHint) {
    p.log.message(`  ${pc.dim(result.repairHint)}`);
  }
}

async function maybeRepair(result: CheckResult, opts: DoctorOpts): Promise<void> {
  if (result.status === "pass" || !result.canRepair || !result.repair) return;
  if (!opts.repair) return;

  let shouldRepair = opts.yes;
  if (!shouldRepair) {
    const answer = await p.confirm({
      message: `Repair "${result.name}"?`,
      initialValue: true,
    });
    if (p.isCancel(answer)) return;
    shouldRepair = answer;
  }

  if (!shouldRepair) return;

  try {
    await result.repair();
    p.log.success(`Repaired: ${result.name}`);
  } catch (err) {
    p.log.error(`Repair failed: ${err instanceof Error ? err.message : String(err)}`);
  }
}

function printSummary(
  results: CheckResult[],
): { passed: number; warned: number; failed: number } {
  const passed = results.filter((r) => r.status === "pass").length;
  const warned = results.filter((r) => r.status === "warn").length;
  const failed = results.filter((r) => r.status === "fail").length;

  const parts: string[] = [pc.green(`${passed} passed`)];
  if (warned) parts.push(pc.yellow(`${warned} warnings`));
  if (failed) parts.push(pc.red(`${failed} failed`));

  p.note(parts.join(", "), "Summary");

  if (failed > 0) {
    p.outro(pc.red("Some checks failed. Fix the issues above and re-run doctor."));
  } else if (warned > 0) {
    p.outro(pc.yellow("All critical checks passed with some warnings."));
  } else {
    p.outro(pc.green("All checks passed!"));
  }

  return { passed, warned, failed };
}

// ---------------------------------------------------------------------------
// Bootstrap: load config + early-bail when unreadable
// ---------------------------------------------------------------------------

interface BootstrapOk {
  ok: true;
  config: GitmeshConfig;
}
interface BootstrapFail {
  ok: false;
  result: CheckResult;
}

/**
 * Read the config file. Returns the parsed config on success, or a `fail`
 * `CheckResult` representing the read-error so the caller can surface it
 * uniformly with the rest of the probe results.
 *
 * Pre-condition: the caller has already run `configCheck()` and seen it pass.
 */
function loadConfigOrFail(opts: DoctorOpts): BootstrapOk | BootstrapFail {
  try {
    const config = readConfig(opts.config);
    if (!config) {
      return {
        ok: false,
        result: {
          name: "Config file",
          status: "fail",
          message: "Config file is empty",
          canRepair: false,
        },
      };
    }
    return { ok: true, config };
  } catch (err) {
    return {
      ok: false,
      result: {
        name: "Config file",
        status: "fail",
        message: `Could not read config: ${err instanceof Error ? err.message : String(err)}`,
        canRepair: false,
        repairHint: "Run `gitmesh-agents configure --section database` or `gitmesh-agents setup`",
      },
    };
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export async function doctor(
  opts: DoctorOpts,
): Promise<{ passed: number; warned: number; failed: number }> {
  printGitmeshCliBanner();
  p.intro(pc.bgCyan(pc.black(" gitmesh-agents doctor ")));

  const configPath = resolveConfigPath(opts.config);
  const results: CheckResult[] = [];

  // Bootstrap: config-shape check is special - it must pass before we can run
  // any of the deeper probes. `bootstrapConfig` runs that check internally and
  // returns the parsed config or a `fail` CheckResult.
  const initialCheck = configCheck(opts.config);
  results.push(initialCheck);
  printResult(initialCheck);
  if (initialCheck.status === "fail") {
    return printSummary(results);
  }

  const bootstrap = loadConfigOrFail(opts);
  if (!bootstrap.ok) {
    results.push(bootstrap.result);
    printResult(bootstrap.result);
    return printSummary(results);
  }

  const ctx: ProbeContext = {
    config: bootstrap.config,
    configPath,
    rawConfigOption: opts.config,
  };

  for (const probe of PROBES) {
    const result = await probe.run(ctx);
    results.push(result);
    printResult(result);
    await maybeRepair(result, opts);
  }

  return printSummary(results);
}
