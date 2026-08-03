/**
 * Typed-fetch wrapper for the GitMesh Agents control-plane API.
 *
 * The wrapper is built around a tiny request builder: each call goes through
 * `prepareRequest -> sendRequest -> decodeResponse`, so cross-cutting concerns
 * (auth header, run-id propagation, JSON encoding, 404 swallowing, error
 * decoding) live in one place each.
 *
 * `GitmeshApiClient` and `ApiRequestError` are kept as the public exported
 * names so existing call sites (`commands/client/common.ts`, `project.ts`,
 * `playbook-install.ts`, the http test) keep working without churn.
 */
import { URL } from "node:url";

// ---------------------------------------------------------------------------
// Public error type
// ---------------------------------------------------------------------------

export class ApiRequestError extends Error {
  status: number;
  details?: unknown;
  body?: unknown;

  constructor(status: number, message: string, details?: unknown, body?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.details = details;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RequestOptions {
  ignoreNotFound?: boolean;
}

export interface ApiClientOptions {
  apiBase: string;
  apiKey?: string;
  runId?: string;
}

type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE" | "PUT";

interface PreparedRequest {
  url: string;
  init: RequestInit;
  ignoreNotFound: boolean;
}

// ---------------------------------------------------------------------------
// Request builder - pure, no I/O
// ---------------------------------------------------------------------------

interface BuilderContext {
  apiBase: string;
  apiKey?: string;
  runId?: string;
}

function joinUrl(apiBase: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const [pathname, query] = normalizedPath.split("?");
  const url = new URL(apiBase);
  url.pathname = `${url.pathname.replace(/\/+$/, "")}${pathname}`;
  if (query) url.search = query;
  return url.toString();
}

function buildHeaders(
  ctx: BuilderContext,
  method: HttpMethod,
  hasBody: boolean,
  extra?: HeadersInit,
): Record<string, string> {
  const merged: Record<string, string> = {
    accept: "application/json",
    ...flattenHeaders(extra),
  };

  if (hasBody && !merged["content-type"]) {
    merged["content-type"] = "application/json";
  }

  if (ctx.apiKey) {
    merged.authorization = `Bearer ${ctx.apiKey}`;
  }

  if (ctx.runId) {
    merged["x-gitmesh-agents-run-id"] = ctx.runId;
  }

  // Keep verb-specific cleanup contained - GET/DELETE never carry a content-type.
  if (!hasBody && (method === "GET" || method === "DELETE")) {
    delete merged["content-type"];
  }

  return merged;
}

function prepareRequest(
  ctx: BuilderContext,
  method: HttpMethod,
  path: string,
  body: unknown,
  options?: RequestOptions,
): PreparedRequest {
  const hasBody = body !== undefined;
  const init: RequestInit = {
    method,
    headers: buildHeaders(ctx, method, hasBody),
  };

  if (hasBody) {
    init.body = typeof body === "string" ? body : JSON.stringify(body);
  }

  return {
    url: joinUrl(ctx.apiBase, path),
    init,
    ignoreNotFound: Boolean(options?.ignoreNotFound),
  };
}

// ---------------------------------------------------------------------------
// Response decode
// ---------------------------------------------------------------------------

async function decodeResponse<T>(
  response: Response,
  prepared: PreparedRequest,
): Promise<T | null> {
  if (prepared.ignoreNotFound && response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw await decodeApiError(response);
  }

  if (response.status === 204) return null;

  const text = await response.text();
  if (!text.trim()) return null;

  return safeParseJson(text) as T;
}

async function decodeApiError(response: Response): Promise<ApiRequestError> {
  const text = await response.text();
  const parsed = safeParseJson(text);

  if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
    const body = parsed as Record<string, unknown>;
    const message =
      stringFromField(body.error) ??
      stringFromField(body.message) ??
      `Request failed with status ${response.status}`;
    return new ApiRequestError(response.status, message, body.details, parsed);
  }

  return new ApiRequestError(
    response.status,
    `Request failed with status ${response.status}`,
    undefined,
    parsed,
  );
}

function stringFromField(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function safeParseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function flattenHeaders(headers: HeadersInit | undefined): Record<string, string> {
  if (!headers) return {};
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers.map(([k, v]) => [k, String(v)]));
  }
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  return Object.fromEntries(Object.entries(headers).map(([k, v]) => [k, String(v)]));
}

// ---------------------------------------------------------------------------
// Public client
// ---------------------------------------------------------------------------

export class GitmeshApiClient {
  readonly apiBase: string;
  readonly apiKey?: string;
  readonly runId?: string;

  constructor(opts: ApiClientOptions) {
    this.apiBase = opts.apiBase.replace(/\/+$/, "");
    this.apiKey = opts.apiKey?.trim() || undefined;
    this.runId = opts.runId?.trim() || undefined;
  }

  /** GET - body is never sent. */
  get<T>(path: string, opts?: RequestOptions): Promise<T | null> {
    return this.send<T>(prepareRequest(this.context(), "GET", path, undefined, opts));
  }

  /** POST - JSON-encodes object bodies, leaves strings alone. */
  post<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T | null> {
    return this.send<T>(prepareRequest(this.context(), "POST", path, body, opts));
  }

  /** PATCH - same JSON convention as POST. */
  patch<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<T | null> {
    return this.send<T>(prepareRequest(this.context(), "PATCH", path, body, opts));
  }

  /** DELETE - body is never sent. */
  delete<T>(path: string, opts?: RequestOptions): Promise<T | null> {
    return this.send<T>(prepareRequest(this.context(), "DELETE", path, undefined, opts));
  }

  /** Escape hatch for tests / advanced callers. */
  protected context(): BuilderContext {
    return { apiBase: this.apiBase, apiKey: this.apiKey, runId: this.runId };
  }

  protected async send<T>(prepared: PreparedRequest): Promise<T | null> {
    const response = await fetch(prepared.url, prepared.init);
    return decodeResponse<T>(response, prepared);
  }
}

// ---------------------------------------------------------------------------
// Future-friendly typed-resource builder
// ---------------------------------------------------------------------------
//
// The factory below is the new structural surface. Callers that want to opt
// in to the typed style can do `gitmeshClient(base).issues.list({ projectId })`
// instead of hand-crafting URL strings. Today only a handful of resources
// exist; we deliberately keep the surface small until call sites migrate.

export interface IssueListParams {
  projectId: string;
  status?: string;
  priority?: string;
  assigneeUserId?: string;
}

function toQueryString(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    search.append(key, String(value));
  }
  const text = search.toString();
  return text.length > 0 ? `?${text}` : "";
}

export function gitmeshClient(opts: ApiClientOptions) {
  const client = new GitmeshApiClient(opts);
  return {
    raw: client,
    issues: {
      list<T>(params: IssueListParams) {
        const { projectId, ...rest } = params;
        return client.get<T>(`/api/projects/${projectId}/issues${toQueryString(rest)}`);
      },
      get<T>(idOrIdentifier: string) {
        return client.get<T>(`/api/issues/${idOrIdentifier}`);
      },
      create<T>(projectId: string, payload: unknown) {
        return client.post<T>(`/api/projects/${projectId}/issues`, payload);
      },
      patch<T>(issueId: string, payload: unknown) {
        return client.patch<T>(`/api/issues/${issueId}`, payload);
      },
    },
    agents: {
      list<T>(projectId: string) {
        return client.get<T>(`/api/projects/${projectId}/agents`);
      },
      get<T>(agentId: string) {
        return client.get<T>(`/api/agents/${agentId}`);
      },
    },
    dashboard: {
      summary<T>(projectId: string) {
        return client.get<T>(`/api/projects/${projectId}/dashboard`);
      },
    },
  };
}
