// Split secret key regex into prefix and suffix parts for different matching strategy
const SECRET_KEY_PREFIX_RE = /(?:api|access|auth|token|credential|jwt|private|cookie|connection|bearer|secret|passwd|password|pass)/i;
const SECRET_KEY_SUFFIX_RE = /(?:key|token|auth|authorization|ref|bearer|secret|password|credential|jwt|connectionstring)/i;
const JWT_VALUE_RE = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?$/;
export const REDACTED_EVENT_VALUE = "***REDACTED***";

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

// Classifier-based approach instead of inline type checks
type ValueKind = "null" | "undefined" | "array" | "secret_ref_binding" | "plain_binding" | "plain_object" | "primitive";

function classifyValueKind(value: unknown): ValueKind {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (Array.isArray(value)) return "array";
  if (!isPlainObject(value)) return "primitive";

  const obj = value as Record<string, unknown>;
  const type = obj.type;

  switch (type) {
    case "secret_ref":
      return typeof obj.secretId === "string" ? "secret_ref_binding" : "primitive";
    case "plain":
      return "value" in obj ? "plain_binding" : "primitive";
    default:
      return "plain_object";
  }
}

function isSecretRefBinding(value: unknown): value is { type: "secret_ref"; secretId: string; version?: unknown } {
  if (!isPlainObject(value)) return false;
  return value.type === "secret_ref" && typeof value.secretId === "string";
}

function isPlainBinding(value: unknown): value is { type: "plain"; value: unknown } {
  if (!isPlainObject(value)) return false;
  return value.type === "plain" && "value" in value;
}

// Helper: check if key looks like a secret based on prefix+suffix strategy
function detectSecretKey(key: string): boolean {
  return SECRET_KEY_PREFIX_RE.test(key) && SECRET_KEY_SUFFIX_RE.test(key);
}

function scanValue(value: unknown): unknown {
  const kind = classifyValueKind(value);

  switch (kind) {
    case "null":
    case "undefined":
    case "primitive":
      return value;
    case "array":
      return (value as unknown[]).map(scanValue);
    case "secret_ref_binding":
      return value;
    case "plain_binding":
      return { type: "plain", value: scanValue((value as { type: "plain"; value: unknown }).value) };
    case "plain_object":
      return scanRecord(value as Record<string, unknown>);
  }
}

function scanRecord(record: Record<string, unknown>): Record<string, unknown> {
  // Apply key-based secret detection at every nesting level, not just at the
  // top of sanitizeRecord. Otherwise a payload like { meta: { password: "..." } }
  // would leak the inner value because the outer recursion only walks values.
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(record)) {
    const value = record[key];
    const isSecret = detectSecretKey(key);
    const isJwt = typeof value === "string" && JWT_VALUE_RE.test(value);

    if (isSecret) {
      result[key] = redactValue(value);
    } else if (isJwt) {
      result[key] = REDACTED_EVENT_VALUE;
    } else {
      result[key] = scanValue(value);
    }
  }
  return result;
}

function redactValue(value: unknown): unknown {
  const kind = classifyValueKind(value);

  switch (kind) {
    case "secret_ref_binding":
      // secret_ref bindings only carry a secretId pointer, no actual secret value,
      // so they are safe to keep verbatim even at sensitive keys.
      return value;
    case "plain_binding":
      // plain bindings wrap a literal value - keep the wrapper, redact the inner value.
      return { type: "plain", value: REDACTED_EVENT_VALUE };
    default:
      return REDACTED_EVENT_VALUE;
  }
}

export function sanitizeRecord(record: Record<string, unknown>): Record<string, unknown> {
  return scanRecord(record);
}

export function redactEventPayload(payload: Record<string, unknown> | null): Record<string, unknown> | null {
  if (!payload) return null;
  if (!isPlainObject(payload)) return payload;
  return sanitizeRecord(payload);
}
