/**
 * `context` subcommands - manage CLI context profiles.
 *
 * These commands intentionally don't use `defineClientCommand` (they don't
 * talk to the API), but they share the same option-spec idiom via
 * `defineCommand` so the shape stays uniform across the CLI.
 */
import { Command } from "commander";
import pc from "picocolors";
import {
  readContext,
  resolveContextPath,
  resolveProfile,
  setCurrentProfile,
  upsertProfile,
} from "../../client/context.js";
import { defineCommand, printOutput } from "../_shared/define.js";

interface ContextBaseOpts {
  dataDir?: string;
  context?: string;
  profile?: string;
  json?: boolean;
}

interface ContextSetOpts extends ContextBaseOpts {
  apiBase?: string;
  projectId?: string;
  apiKeyEnvVarName?: string;
  use?: boolean;
}

const SHARED_LOCATION_OPTIONS = [
  {
    flag: "-d, --data-dir <path>",
    desc: "GitMesh Agents data directory root (isolates state from ~/.gitmesh-agents)",
  },
  { flag: "--context <path>", desc: "Path to CLI context file" },
] as const;

export function registerContextCommands(program: Command): void {
  const context = program.command("context").description("Manage CLI client context profiles");

  defineCommand<ContextBaseOpts>(context, {
    name: "show",
    describe: "Show current context and active profile",
    options: [
      ...SHARED_LOCATION_OPTIONS,
      { flag: "--profile <name>", desc: "Profile to inspect" },
      { flag: "--json", desc: "Output raw JSON" },
    ],
    run({ options }) {
      const contextPath = resolveContextPath(options.context);
      const store = readContext(options.context);
      const resolved = resolveProfile(store, options.profile);
      printOutput(
        {
          contextPath,
          currentProfile: store.currentProfile,
          profileName: resolved.name,
          profile: resolved.profile,
          profiles: store.profiles,
        },
        { json: options.json },
      );
    },
  });

  defineCommand<ContextBaseOpts>(context, {
    name: "list",
    describe: "List available context profiles",
    options: [
      ...SHARED_LOCATION_OPTIONS,
      { flag: "--json", desc: "Output raw JSON" },
    ],
    run({ options }) {
      const store = readContext(options.context);
      const rows = Object.entries(store.profiles).map(([name, profile]) => ({
        name,
        current: name === store.currentProfile,
        apiBase: profile.apiBase ?? null,
        projectId: profile.projectId ?? null,
        apiKeyEnvVarName: profile.apiKeyEnvVarName ?? null,
      }));
      printOutput(rows, { json: options.json });
    },
  });

  defineCommand<ContextBaseOpts>(context, {
    name: "use",
    describe: "Set active context profile",
    positional: [{ name: "profile", desc: "Profile name" }],
    options: [...SHARED_LOCATION_OPTIONS],
    run({ positional, options }) {
      const [profile] = positional;
      setCurrentProfile(profile, options.context);
      console.log(pc.green(`Active profile set to '${profile}'.`));
    },
  });

  defineCommand<ContextSetOpts>(context, {
    name: "set",
    describe: "Set values on a profile",
    options: [
      ...SHARED_LOCATION_OPTIONS,
      { flag: "--profile <name>", desc: "Profile name (default: current profile)" },
      { flag: "--api-base <url>", desc: "Default API base URL" },
      { flag: "--project-id <id>", desc: "Default project ID" },
      { flag: "--api-key-env-var-name <name>", desc: "Env var containing API key (recommended)" },
      { flag: "--use", desc: "Set this profile as active" },
      { flag: "--json", desc: "Output raw JSON" },
    ],
    run({ options }) {
      const existing = readContext(options.context);
      const targetProfile = options.profile?.trim() || existing.currentProfile || "default";

      upsertProfile(
        targetProfile,
        {
          apiBase: options.apiBase,
          projectId: options.projectId,
          apiKeyEnvVarName: options.apiKeyEnvVarName,
        },
        options.context,
      );

      if (options.use) {
        setCurrentProfile(targetProfile, options.context);
      }

      const updated = readContext(options.context);
      const resolved = resolveProfile(updated, targetProfile);
      const payload = {
        contextPath: resolveContextPath(options.context),
        currentProfile: updated.currentProfile,
        profileName: resolved.name,
        profile: resolved.profile,
      };

      if (!options.json) {
        console.log(pc.green(`Updated profile '${targetProfile}'.`));
        if (options.use) {
          console.log(pc.green(`Set '${targetProfile}' as active profile.`));
        }
      }
      printOutput(payload, { json: options.json });
    },
  });
}
