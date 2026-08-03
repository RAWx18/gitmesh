/**
 * Spec-driven Commander wrapper.
 *
 * Commands are described as plain spec objects; this module turns them into
 * the imperative `commander` shape. Centralizes error handling, JSON output,
 * and project/operator context resolution so each command file is data + a
 * `run()` body instead of a hand-rolled `.option().argument().action()` chain.
 */
import { Command } from "commander";
import {
  addCommonClientOptions,
  formatInlineRecord,
  handleCommandError,
  printOutput,
  resolveCommandContext,
  type BaseClientOptions,
  type ResolvedClientContext,
} from "../client/common.js";

// ---------------------------------------------------------------------------
// Spec types
// ---------------------------------------------------------------------------

export interface OptionSpec {
  flag: string;
  desc: string;
  /** Optional default value passed straight through to commander. */
  defaultValue?: string | boolean;
  /** When true, the option is registered with `requiredOption`. */
  required?: boolean;
  /** Optional commander coercion fn (e.g. `Number`). */
  coerce?: (value: string) => unknown;
}

export interface PositionalSpec {
  /** Argument name surrounded by `<>` (required) or `[]` (optional). */
  name: string;
  desc: string;
  required?: boolean;
}

export interface CommandSpec<O> {
  /** Subcommand name (single token, may include alias via "|" suffix). */
  name: string;
  describe: string;
  positional?: PositionalSpec[];
  options?: OptionSpec[];
  /** Hidden alias names. */
  aliases?: string[];
  /** Final action body. Receives parsed positional args + options. */
  run: (args: { positional: string[]; options: O }) => Promise<void> | void;
}

export interface ClientCommandSpec<O extends BaseClientOptions>
  extends Omit<CommandSpec<O>, "run"> {
  /**
   * When true, the resolver enforces a project context (--project-id / env /
   * profile default). The auto-injected `--project-id` option is added at
   * registration time when this flag is set, unless the spec already declares
   * one.
   */
  requireProject?: boolean;
  /** Run handler - receives a typed gitmesh client context. */
  run: (
    ctx: ResolvedClientContext,
    args: { positional: string[]; options: O },
  ) => Promise<void> | void;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function applyPositionals(command: Command, positional: PositionalSpec[] | undefined): void {
  for (const arg of positional ?? []) {
    const wrapped = arg.required === false ? `[${arg.name}]` : `<${arg.name}>`;
    command.argument(wrapped, arg.desc);
  }
}

function applyOptions(command: Command, options: OptionSpec[] | undefined): void {
  for (const opt of options ?? []) {
    const args: unknown[] = [opt.flag, opt.desc];
    if (opt.coerce) args.push(opt.coerce);
    if (opt.defaultValue !== undefined) args.push(opt.defaultValue);

    if (opt.required) {
      // commander's typings disagree about variadic call; cast to keep helper compact.
      (command.requiredOption as (...a: unknown[]) => Command)(...args);
    } else {
      (command.option as (...a: unknown[]) => Command)(...args);
    }
  }
}

function flagDeclares(option: OptionSpec, attribute: string): boolean {
  // commander derives camelCase attribute names from flags; e.g. "-P, --project-id" => projectId.
  // We just match the long-flag tail.
  const longFlagMatch = option.flag.match(/--([\w-]+)/);
  if (!longFlagMatch) return false;
  const camel = longFlagMatch[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
  return camel === attribute;
}

// ---------------------------------------------------------------------------
// Public registrars
// ---------------------------------------------------------------------------

/**
 * Build and attach a non-client subcommand from a spec. The spec's `run`
 * receives parsed args and is wrapped in a try/catch that pretty-prints the
 * error and exits 1, matching the previous hand-rolled pattern.
 */
export function defineCommand<O>(parent: Command, spec: CommandSpec<O>): Command {
  const child = parent.command(spec.name).description(spec.describe);
  applyPositionals(child, spec.positional);
  applyOptions(child, spec.options);
  for (const alias of spec.aliases ?? []) child.alias(alias);

  child.action(async (...invocation: unknown[]) => {
    // Commander invokes with: ...positional, options, command
    const opts = invocation[invocation.length - 2] as O;
    const positional = invocation.slice(0, invocation.length - 2).map(String);
    try {
      await spec.run({ positional, options: opts });
    } catch (err) {
      handleCommandError(err);
    }
  });

  return child;
}

/**
 * Build and attach a *client-facing* subcommand. This wires in the standard
 * suite of context options (--api-base / --api-key / --profile / --json / etc.)
 * and resolves them into a typed `ResolvedClientContext` before invoking the
 * spec's `run` handler.
 */
export function defineClientCommand<O extends BaseClientOptions>(
  parent: Command,
  spec: ClientCommandSpec<O>,
): Command {
  const child = parent.command(spec.name).description(spec.describe);
  applyPositionals(child, spec.positional);
  applyOptions(child, spec.options);
  for (const alias of spec.aliases ?? []) child.alias(alias);

  // Inject --project-id automatically if `requireProject` is set and the spec
  // hasn't already declared its own project flag.
  const declaresProjectId = (spec.options ?? []).some((opt) => flagDeclares(opt, "projectId"));
  addCommonClientOptions(child, {
    includeProject: spec.requireProject === true && !declaresProjectId,
  });

  child.action(async (...invocation: unknown[]) => {
    const options = invocation[invocation.length - 2] as O;
    const positional = invocation.slice(0, invocation.length - 2).map(String);
    try {
      const ctx = resolveCommandContext(options, { requireProject: spec.requireProject === true });
      await spec.run(ctx, { positional, options });
    } catch (err) {
      handleCommandError(err);
    }
  });

  return child;
}

// Re-export common output helpers so command files can import everything from
// a single place.
export { formatInlineRecord, printOutput };
export type { ResolvedClientContext };
