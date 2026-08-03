import type { AdapterConfigFieldsProps } from "../types";
import { renderAdapterSchema, type FieldSchema } from "../_shared/adapter-form";

/**
 * Process adapter - schema-driven. Compare with upstream's hand-rolled JSX:
 * adding a field here is a single object literal.
 */
const PROCESS_SCHEMA: FieldSchema[] = [
  {
    type: "text",
    key: "command",
    label: "Command",
    hint: "command",
    placeholder: "e.g. node, python",
  },
  {
    type: "commaList",
    key: "args",
    label: "Args (comma-separated)",
    hint: "args",
    placeholder: "e.g. script.js, --flag",
  },
];

export function ProcessConfigFields(props: AdapterConfigFieldsProps) {
  return <>{renderAdapterSchema(PROCESS_SCHEMA, props)}</>;
}
