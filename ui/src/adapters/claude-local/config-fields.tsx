import type { AdapterConfigFieldsProps } from "../types";
import { renderAdapterSchema, inputClass, type FieldSchema } from "../_shared/adapter-form";
import { Field, DraftInput } from "../../components/agent-config-primitives";
import { ChoosePathButton } from "../../features/PathInstructionsModal";

const instructionsFileHint =
  "Absolute path to a markdown file (e.g. AGENTS.md) that defines this agent's behavior. Injected into the system prompt at runtime.";

/**
 * Claude (local) - schema-driven, with one custom slot for the path-picker
 * button that doesn't fit the standard text input shape.
 */
const CLAUDE_LOCAL_BASIC: FieldSchema[] = [
  {
    type: "custom",
    key: "instructionsFilePath",
    render: ({ isCreate, values, set, config, eff, mark }: AdapterConfigFieldsProps) => {
      const value = isCreate
        ? String(values?.instructionsFilePath ?? "")
        : eff("adapterConfig", "instructionsFilePath", String(config.instructionsFilePath ?? ""));
      return (
        <Field label="Agent instructions file" hint={instructionsFileHint}>
          <div className="flex items-center gap-2">
            <DraftInput
              value={value}
              onCommit={(v) =>
                isCreate
                  ? set?.({ instructionsFilePath: v })
                  : mark("adapterConfig", "instructionsFilePath", v || undefined)
              }
              immediate
              className={inputClass}
              placeholder="/absolute/path/to/AGENTS.md"
            />
            <ChoosePathButton />
          </div>
        </Field>
      );
    },
  },
];

const CLAUDE_LOCAL_ADVANCED: FieldSchema[] = [
  {
    type: "toggle",
    key: "chrome",
    label: "Enable Chrome",
    hint: "chrome",
    defaultValue: false,
  },
  {
    type: "toggle",
    key: "dangerouslySkipPermissions",
    label: "Skip permissions",
    hint: "dangerouslySkipPermissions",
    defaultValue: true,
  },
  {
    type: "number",
    key: "maxTurnsPerRun",
    label: "Max turns per run",
    hint: "maxTurnsPerRun",
    defaultValue: 80,
  },
];

export function ClaudeLocalConfigFields(props: AdapterConfigFieldsProps) {
  return <>{renderAdapterSchema(CLAUDE_LOCAL_BASIC, props)}</>;
}

export function ClaudeLocalAdvancedFields(props: AdapterConfigFieldsProps) {
  return <>{renderAdapterSchema(CLAUDE_LOCAL_ADVANCED, props)}</>;
}
