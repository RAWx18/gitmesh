/**
 * Declarative schema → renderer for adapter `ConfigFields` panels.
 *
 * Each adapter describes its config form as a `FieldSchema[]`. The renderer
 * walks the schema and binds every field to the unified `AdapterConfigFieldsProps`
 * (`isCreate`, `values`, `set`, `config`, `eff`, `mark`) - so adapter modules
 * stop hand-rolling read/commit boilerplate per-field.
 *
 * Adding a new field is a one-liner in a schema array.
 */

import { useState, type ReactNode } from "react";
import { Eye, EyeOff } from "lucide-react";
import {
  Field,
  ToggleField,
  DraftInput,
  DraftNumberInput,
  help as helpDict,
} from "../../components/agent-config-primitives";
import type { AdapterConfigFieldsProps } from "../types";

export const inputClass =
  "w-full rounded-md border border-border px-2.5 py-1.5 bg-transparent outline-none text-sm font-mono placeholder:text-muted-foreground/40";

// ---------------------------------------------------------------------------
// Schema types
// ---------------------------------------------------------------------------

interface FieldBase {
  /** key inside `adapterConfig` and on the create-mode `values` bag */
  key: string;
  label: string;
  /** look up in `helpText` dict; if not found, used as literal */
  hint?: string;
  /** show only in edit mode (default true) */
  edit?: boolean;
  /** show only in create mode (default true) */
  create?: boolean;
  placeholder?: string;
}

export interface TextFieldSchema extends FieldBase {
  type: "text";
  defaultValue?: string;
}

export interface SecretFieldSchema extends FieldBase {
  type: "secret";
  /** read effective value; defaults to reading `config[key]` */
  read?: (props: AdapterConfigFieldsProps) => string;
  /** write effective value; defaults to mark("adapterConfig", key, value) */
  write?: (props: AdapterConfigFieldsProps, value: string) => void;
}

export interface ToggleFieldSchema extends FieldBase {
  type: "toggle";
  defaultValue?: boolean;
}

export interface NumberFieldSchema extends FieldBase {
  type: "number";
  defaultValue?: number;
}

export interface SelectFieldSchema extends FieldBase {
  type: "select";
  options: Array<{ value: string; label: string }>;
  defaultValue?: string;
}

export interface CommaListFieldSchema extends FieldBase {
  type: "commaList";
  /** default joined string for create mode; default joined for edit when missing */
  defaultValue?: string;
  /** raw default for the array stored on `adapterConfig` */
  defaultArray?: string[];
}

export interface CustomFieldSchema {
  type: "custom";
  /** if create or edit only, set these */
  edit?: boolean;
  create?: boolean;
  render: (props: AdapterConfigFieldsProps) => ReactNode;
  /** for stable keying */
  key: string;
}

export type FieldSchema =
  | TextFieldSchema
  | SecretFieldSchema
  | ToggleFieldSchema
  | NumberFieldSchema
  | SelectFieldSchema
  | CommaListFieldSchema
  | CustomFieldSchema;

// ---------------------------------------------------------------------------
// Renderer
// ---------------------------------------------------------------------------

function shouldRender(schema: { create?: boolean; edit?: boolean }, isCreate: boolean): boolean {
  if (isCreate) return schema.create !== false;
  return schema.edit !== false;
}

function resolveHint(hint: string | undefined): string | undefined {
  if (!hint) return undefined;
  return helpDict[hint] ?? hint;
}

function SecretInput({
  label,
  hint,
  value,
  onCommit,
  placeholder,
}: {
  label: string;
  hint?: string;
  value: string;
  onCommit: (v: string) => void;
  placeholder?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <Field label={label} hint={hint}>
      <div className="relative">
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          aria-label={visible ? "Hide secret" : "Show secret"}
        >
          {visible ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
        </button>
        <DraftInput
          value={value}
          onCommit={onCommit}
          immediate
          type={visible ? "text" : "password"}
          className={inputClass + " pl-8"}
          placeholder={placeholder}
        />
      </div>
    </Field>
  );
}

function joinList(value: unknown): string {
  if (Array.isArray(value)) {
    return value.filter((v): v is string => typeof v === "string").join(", ");
  }
  return typeof value === "string" ? value : "";
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function renderOne(schema: FieldSchema, props: AdapterConfigFieldsProps): ReactNode {
  const { isCreate, values, set, config, eff, mark } = props;
  const hint = "type" in schema && schema.type !== "custom" ? resolveHint(schema.hint) : undefined;

  if (schema.type === "custom") {
    return schema.render(props);
  }

  switch (schema.type) {
    case "text": {
      const initial = isCreate
        ? String((values as unknown as Record<string, unknown>)?.[schema.key] ?? schema.defaultValue ?? "")
        : eff("adapterConfig", schema.key, String(config[schema.key] ?? schema.defaultValue ?? ""));
      return (
        <Field label={schema.label} hint={hint}>
          <DraftInput
            value={initial}
            onCommit={(v) =>
              isCreate
                ? set?.({ [schema.key]: v } as never)
                : mark("adapterConfig", schema.key, v || undefined)
            }
            immediate
            className={inputClass}
            placeholder={schema.placeholder}
          />
        </Field>
      );
    }
    case "secret": {
      const value = schema.read ? schema.read(props) : String(eff("adapterConfig", schema.key, String(config[schema.key] ?? "")));
      const onCommit = schema.write
        ? (v: string) => schema.write!(props, v)
        : (v: string) => mark("adapterConfig", schema.key, v ? v : undefined);
      return (
        <SecretInput
          label={schema.label}
          hint={hint}
          value={value}
          onCommit={onCommit}
          placeholder={schema.placeholder}
        />
      );
    }
    case "toggle": {
      const checked = isCreate
        ? Boolean((values as unknown as Record<string, unknown>)?.[schema.key] ?? schema.defaultValue ?? false)
        : Boolean(eff("adapterConfig", schema.key, (config[schema.key] ?? schema.defaultValue ?? false) as boolean));
      return (
        <ToggleField
          label={schema.label}
          hint={hint}
          checked={checked}
          onChange={(v) =>
            isCreate
              ? set?.({ [schema.key]: v } as never)
              : mark("adapterConfig", schema.key, v)
          }
        />
      );
    }
    case "number": {
      const fallback = schema.defaultValue ?? 0;
      if (isCreate) {
        const value = Number((values as unknown as Record<string, unknown>)?.[schema.key] ?? fallback);
        return (
          <Field label={schema.label} hint={hint}>
            <input
              type="number"
              className={inputClass}
              value={value}
              onChange={(e) => set?.({ [schema.key]: Number(e.target.value) } as never)}
              placeholder={schema.placeholder}
            />
          </Field>
        );
      }
      const value = Number(eff("adapterConfig", schema.key, Number(config[schema.key] ?? fallback)));
      return (
        <Field label={schema.label} hint={hint}>
          <DraftNumberInput
            value={value}
            onCommit={(v) => mark("adapterConfig", schema.key, v || fallback)}
            immediate
            className={inputClass}
          />
        </Field>
      );
    }
    case "select": {
      const fallback = schema.defaultValue ?? schema.options[0]?.value ?? "";
      const value = isCreate
        ? String((values as unknown as Record<string, unknown>)?.[schema.key] ?? fallback)
        : String(eff("adapterConfig", schema.key, String(config[schema.key] ?? fallback)));
      return (
        <Field label={schema.label} hint={hint}>
          <select
            value={value}
            onChange={(e) =>
              isCreate
                ? set?.({ [schema.key]: e.target.value } as never)
                : mark("adapterConfig", schema.key, e.target.value)
            }
            className={inputClass}
          >
            {schema.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </Field>
      );
    }
    case "commaList": {
      const value = isCreate
        ? String((values as unknown as Record<string, unknown>)?.[schema.key] ?? schema.defaultValue ?? "")
        : eff(
            "adapterConfig",
            schema.key,
            joinList(config[schema.key] ?? schema.defaultArray ?? schema.defaultValue ?? ""),
          );
      return (
        <Field label={schema.label} hint={hint}>
          <DraftInput
            value={String(value)}
            onCommit={(v) => {
              if (isCreate) {
                set?.({ [schema.key]: v } as never);
              } else {
                const parsed = splitList(v);
                mark("adapterConfig", schema.key, parsed.length > 0 ? parsed : undefined);
              }
            }}
            immediate
            className={inputClass}
            placeholder={schema.placeholder}
          />
        </Field>
      );
    }
  }
}

/** Render an entire schema array against an adapter's props bundle. */
export function renderAdapterSchema(
  schema: FieldSchema[],
  props: AdapterConfigFieldsProps,
): ReactNode {
  return (
    <>
      {schema.map((entry) => {
        if (!shouldRender(entry as { create?: boolean; edit?: boolean }, props.isCreate)) {
          return null;
        }
        return <FragmentItem key={entry.key} schema={entry} props={props} />;
      })}
    </>
  );
}

function FragmentItem({
  schema,
  props,
}: {
  schema: FieldSchema;
  props: AdapterConfigFieldsProps;
}) {
  return <>{renderOne(schema, props)}</>;
}
