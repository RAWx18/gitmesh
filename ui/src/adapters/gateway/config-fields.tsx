import type { AdapterConfigFieldsProps } from "../types";
import { renderAdapterSchema, type FieldSchema } from "../_shared/adapter-form";
import { Field } from "../../components/agent-config-primitives";

/**
 * Gateway adapter config - declarative schema with two custom slots
 * (gateway-token secret routing through `headers`, and the static
 * "Device auth" copy block).
 *
 * Visibility branching (e.g. session-key only when strategy === "fixed")
 * is handled by reading effective state inside the schema-build callback.
 */
function buildGatewaySchema(props: AdapterConfigFieldsProps): FieldSchema[] {
  const { config, eff } = props;

  const sessionStrategy = String(
    eff("adapterConfig", "sessionKeyStrategy", String(config.sessionKeyStrategy ?? "fixed")),
  );

  const fields: FieldSchema[] = [
    {
      type: "text",
      key: "url",
      label: "Gateway URL",
      hint: "webhookUrl",
      placeholder: "ws://127.0.0.1:18789",
    },
    {
      type: "text",
      key: "gitmesh-agentsApiUrl",
      label: "GitMesh Agents API URL override",
      placeholder: "https://gitmesh-agents.example",
      create: false,
    },
    {
      type: "select",
      key: "sessionKeyStrategy",
      label: "Session strategy",
      defaultValue: "fixed",
      options: [
        { value: "fixed", label: "Fixed" },
        { value: "issue", label: "Per issue" },
        { value: "run", label: "Per run" },
      ],
      create: false,
    },
  ];

  if (sessionStrategy === "fixed") {
    fields.push({
      type: "text",
      key: "sessionKey",
      label: "Session key",
      defaultValue: "gitmesh-agents",
      placeholder: "gitmesh-agents",
      create: false,
    });
  }

  fields.push(
    {
      type: "secret",
      key: "x-gateway-token",
      label: "Gateway auth token (x-gateway-token)",
      placeholder: "Gateway token",
      create: false,
      read: ({ config, eff }) => {
        const configured =
          config.headers && typeof config.headers === "object" && !Array.isArray(config.headers)
            ? (config.headers as Record<string, unknown>)
            : {};
        const effective =
          (eff("adapterConfig", "headers", configured) as Record<string, unknown>) ?? {};
        if (typeof effective["x-gateway-token"] === "string") return String(effective["x-gateway-token"]);
        if (typeof effective["x-gateway-auth"] === "string") return String(effective["x-gateway-auth"]);
        return "";
      },
      write: ({ config, eff, mark }, raw) => {
        const configured =
          config.headers && typeof config.headers === "object" && !Array.isArray(config.headers)
            ? (config.headers as Record<string, unknown>)
            : {};
        const effective =
          (eff("adapterConfig", "headers", configured) as Record<string, unknown>) ?? {};
        const next: Record<string, unknown> = { ...effective };
        const trimmed = raw.trim();
        if (trimmed) {
          next["x-gateway-token"] = trimmed;
          delete next["x-gateway-auth"];
        } else {
          delete next["x-gateway-token"];
          delete next["x-gateway-auth"];
        }
        mark("adapterConfig", "headers", Object.keys(next).length > 0 ? next : undefined);
      },
    },
    {
      type: "text",
      key: "role",
      label: "Role",
      defaultValue: "operator",
      placeholder: "operator",
      create: false,
    },
    {
      type: "commaList",
      key: "scopes",
      label: "Scopes (comma-separated)",
      defaultArray: ["operator.admin"],
      placeholder: "operator.admin",
      create: false,
    },
    {
      type: "custom",
      key: "waitTimeoutMs",
      create: false,
      render: ({ config, eff, mark }) => (
        <Field label="Wait timeout (ms)">
          <input
            type="text"
            className="w-full rounded-md border border-border px-2.5 py-1.5 bg-transparent outline-none text-sm font-mono placeholder:text-muted-foreground/40"
            defaultValue={String(eff("adapterConfig", "waitTimeoutMs", String(config.waitTimeoutMs ?? "120000")))}
            placeholder="120000"
            onBlur={(e) => {
              const parsed = Number.parseInt(e.target.value.trim(), 10);
              mark(
                "adapterConfig",
                "waitTimeoutMs",
                Number.isFinite(parsed) && parsed > 0 ? parsed : undefined,
              );
            }}
          />
        </Field>
      ),
    },
    {
      type: "custom",
      key: "device-auth-info",
      create: false,
      render: () => (
        <Field label="Device auth">
          <div className="text-xs text-muted-foreground leading-relaxed">
            Always enabled for gateway agents. GitMesh Agents persists a device key during onboarding so pairing approvals
            remain stable across runs.
          </div>
        </Field>
      ),
    },
  );

  return fields;
}

export function GatewayConfigFields(props: AdapterConfigFieldsProps) {
  const schema = buildGatewaySchema(props);
  return <>{renderAdapterSchema(schema, props)}</>;
}
