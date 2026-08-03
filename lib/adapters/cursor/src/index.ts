/**
 * @gitmesh/adapter-cursor-local - public entry point.
 *
 * The model catalogue is expressed as a structured family list (not a
 * flat mirror of an external file). The set of model
 * IDs surfaced to the runtime is unchanged; tests in
 * `models.test.ts` validate that.
 */

export const type = "cursor";
export const label = "Cursor CLI (local)";
export const DEFAULT_CURSOR_LOCAL_MODEL = "auto";

interface ModelFamily {
  /** Stable family key used for documentation / future grouping in the UI. */
  family: string;
  /** Optional human-readable description. */
  description?: string;
  /** Ordered list of model IDs Cursor exposes for this family. */
  ids: readonly string[];
}

/**
 * Cursor's available model IDs, grouped by family. Order within each
 * family is preserved when flattening, and family order matches the
 * legacy flat list so existing fallback / preference logic still picks
 * the same first/last entries.
 */
const CURSOR_MODEL_FAMILIES: readonly ModelFamily[] = [
  {
    family: "default",
    description: "Generic / catch-all entries Cursor surfaces in any plan.",
    ids: [DEFAULT_CURSOR_LOCAL_MODEL, "composer-1.5", "composer-1"],
  },
  {
    family: "gpt-5.3-codex",
    description: "OpenAI gpt-5.3 codex tiers (low → xhigh, plus -fast peers).",
    ids: [
      "gpt-5.3-codex-low",
      "gpt-5.3-codex-low-fast",
      "gpt-5.3-codex",
      "gpt-5.3-codex-fast",
      "gpt-5.3-codex-high",
      "gpt-5.3-codex-high-fast",
      "gpt-5.3-codex-xhigh",
      "gpt-5.3-codex-xhigh-fast",
      "gpt-5.3-codex-spark-preview",
    ],
  },
  {
    family: "gpt-5.2-codex",
    ids: [
      "gpt-5.2",
      "gpt-5.2-codex-low",
      "gpt-5.2-codex-low-fast",
      "gpt-5.2-codex",
      "gpt-5.2-codex-fast",
      "gpt-5.2-codex-high",
      "gpt-5.2-codex-high-fast",
      "gpt-5.2-codex-xhigh",
      "gpt-5.2-codex-xhigh-fast",
    ],
  },
  {
    family: "gpt-5.1-codex",
    ids: [
      "gpt-5.1-codex-max",
      "gpt-5.1-codex-max-high",
      "gpt-5.2-high",
      "gpt-5.1-high",
      "gpt-5.1-codex-mini",
    ],
  },
  {
    family: "anthropic",
    description: "Cursor's Anthropic Claude lane.",
    ids: [
      "opus-4.6-thinking",
      "opus-4.6",
      "opus-4.5",
      "opus-4.5-thinking",
      "sonnet-4.6",
      "sonnet-4.6-thinking",
      "sonnet-4.5",
      "sonnet-4.5-thinking",
    ],
  },
  {
    family: "gemini",
    ids: ["gemini-3.1-pro", "gemini-3-pro", "gemini-3-flash"],
  },
  {
    family: "other",
    description: "Third-party providers Cursor occasionally exposes.",
    ids: ["grok", "kimi-k2.5"],
  },
];

const CURSOR_FALLBACK_MODEL_IDS: readonly string[] = CURSOR_MODEL_FAMILIES.flatMap(
  (entry) => entry.ids,
);

export const models = CURSOR_FALLBACK_MODEL_IDS.map((id) => ({ id, label: id }));

/**
 * Programmatic access to the family-grouped catalogue. The runtime uses
 * the flat `models` list above; the UI may eventually consume this.
 */
export function getCursorModelFamilies(): readonly ModelFamily[] {
  return CURSOR_MODEL_FAMILIES;
}

export const agentConfigurationDoc = `# cursor agent configuration

Adapter: cursor

Use when:
- You want Gitmesh to run Cursor Agent CLI locally as the agent runtime
- You want Cursor chat session resume across heartbeats via --resume
- You want structured stream output in run logs via --output-format stream-json

Don't use when:
- You need webhook-style external invocation (use gateway or http)
- You only need one-shot shell commands (use process)
- Cursor Agent CLI is not installed on the machine

Core fields:
- cwd (string, optional): default absolute working directory fallback for the agent process (created if missing when possible)
- instructionsFilePath (string, optional): absolute path to a markdown instructions file prepended to the run prompt
- promptTemplate (string, optional): run prompt template
- model (string, optional): Cursor model id (for example auto or gpt-5.3-codex)
- mode (string, optional): Cursor execution mode passed as --mode (plan|ask). Leave unset for normal autonomous runs.
- command (string, optional): defaults to "agent"
- extraArgs (string[], optional): additional CLI args
- env (object, optional): KEY=VALUE environment variables

Operational fields:
- timeoutSec (number, optional): run timeout in seconds
- graceSec (number, optional): SIGTERM grace period in seconds

Notes:
- Runs are executed with: agent -p --output-format stream-json ...
- Prompts are piped to Cursor via stdin.
- Sessions are resumed with --resume when stored session cwd matches current cwd.
- Gitmesh auto-injects local playbooks into "~/.cursor/skills" when missing, so Cursor can discover "$gitmesh-agents" and related playbooks on local runs.
- Gitmesh auto-adds --yolo unless one of --trust/--yolo/-f is already present in extraArgs.
`;
