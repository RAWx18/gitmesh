/**
 * `heartbeat run`: invoke a single agent heartbeat and stream its events
 * back to the operator.
 *
 * The previous shape interleaved option parsing, run-state mutation, and
 * stream rendering inside a single very large function. This rewrite splits
 * the concerns into:
 *
 *   - Option/transport parsing  → `parseHeartbeatOpts()`
 *   - Stream rendering          → `HeartbeatRenderer`
 *   - Run-state polling         → `pollUntilTerminal()`
 *   - Final-status reporting    → `reportFinalStatus()`
 *
 * The CLI surface (flags, output text, exit codes) is byte-stable.
 */
import { setTimeout as delay } from "node:timers/promises";
import pc from "picocolors";
import type {
  Agent,
  HeartbeatRun,
  HeartbeatRunEvent,
  HeartbeatRunStatus,
} from "@gitmesh/core";
import { getCLIAdapter } from "../adapters/index.js";
import { resolveCommandContext } from "./client/common.js";
import type { GitmeshApiClient } from "../client/http.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const HEARTBEAT_SOURCES = ["timer", "assignment", "on_demand", "automation"] as const;
const HEARTBEAT_TRIGGERS = ["manual", "ping", "callback", "system"] as const;
const TERMINAL_STATUSES = new Set<HeartbeatRunStatus>([
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
]);
const POLL_INTERVAL_MS = 200;
const LOG_FETCH_LIMIT_BYTES = 16384;
const EVENT_FETCH_LIMIT = 100;

type HeartbeatSource = (typeof HEARTBEAT_SOURCES)[number];
type HeartbeatTrigger = (typeof HEARTBEAT_TRIGGERS)[number];
type InvokedHeartbeat = HeartbeatRun | { status: "skipped" };
type LogStream = "stdout" | "stderr" | "system";

interface HeartbeatRunEventRecord extends HeartbeatRunEvent {
  type?: string | null;
}

export interface HeartbeatRunOptions {
  config?: string;
  context?: string;
  profile?: string;
  agentId: string;
  apiBase?: string;
  apiKey?: string;
  source: string;
  trigger: string;
  timeoutMs: string;
  debug?: boolean;
  json?: boolean;
}

// ---------------------------------------------------------------------------
// Tiny generic helpers
// ---------------------------------------------------------------------------

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asErrorText(value: unknown): string {
  if (typeof value === "string") return value;
  const obj = asRecord(value);
  if (!obj) return "";
  const message =
    (typeof obj.message === "string" && obj.message) ||
    (typeof obj.error === "string" && obj.error) ||
    (typeof obj.code === "string" && obj.code) ||
    "";
  if (message) return message;
  try {
    return JSON.stringify(obj);
  } catch {
    return "";
  }
}

function pickEnum<T extends string>(
  candidate: string,
  allowed: readonly T[],
  fallback: T,
): T {
  return (allowed as readonly string[]).includes(candidate) ? (candidate as T) : fallback;
}

interface ParsedOptions {
  source: HeartbeatSource;
  triggerDetail: HeartbeatTrigger;
  timeoutMs: number;
  debug: boolean;
}

function parseHeartbeatOpts(opts: HeartbeatRunOptions): ParsedOptions {
  const parsedTimeout = Number.parseInt(opts.timeoutMs, 10);
  return {
    source: pickEnum(opts.source, HEARTBEAT_SOURCES, "on_demand"),
    triggerDetail: pickEnum(opts.trigger, HEARTBEAT_TRIGGERS, "manual"),
    timeoutMs: Number.isFinite(parsedTimeout) ? parsedTimeout : 0,
    debug: Boolean(opts.debug),
  };
}

// ---------------------------------------------------------------------------
// Stream renderer
// ---------------------------------------------------------------------------

class HeartbeatRenderer {
  private stdoutJsonBuffer = "";
  private readonly cliAdapter: ReturnType<typeof getCLIAdapter>;
  private readonly debug: boolean;

  constructor(adapterType: string, debug: boolean) {
    this.cliAdapter = getCLIAdapter(adapterType);
    this.debug = debug;
  }

  private rawChunk(stream: LogStream, chunk: string): void {
    if (stream === "stdout") process.stdout.write(pc.green("[stdout] ") + chunk);
    else if (stream === "stderr") process.stdout.write(pc.red("[stderr] ") + chunk);
    else process.stdout.write(pc.yellow("[system] ") + chunk);
  }

  handleStreamChunk(stream: LogStream, chunk: string): void {
    if (this.debug) {
      this.rawChunk(stream, chunk);
      return;
    }
    if (stream !== "stdout") {
      this.rawChunk(stream, chunk);
      return;
    }

    const combined = this.stdoutJsonBuffer + chunk;
    const lines = combined.split(/\r?\n/);
    this.stdoutJsonBuffer = lines.pop() ?? "";
    for (const line of lines) {
      this.cliAdapter.formatStdoutEvent(line, this.debug);
    }
  }

  flushBuffered(): void {
    if (!this.debug && this.stdoutJsonBuffer.trim()) {
      this.cliAdapter.formatStdoutEvent(this.stdoutJsonBuffer, this.debug);
      this.stdoutJsonBuffer = "";
    }
  }

  private adapterInvoke(payload: Record<string, unknown>): void {
    const adapterType = typeof payload.adapterType === "string" ? payload.adapterType : "unknown";
    const command = typeof payload.command === "string" ? payload.command : "";
    const cwd = typeof payload.cwd === "string" ? payload.cwd : "";
    const args =
      Array.isArray(payload.commandArgs) &&
      (payload.commandArgs as unknown[]).every((v) => typeof v === "string")
        ? (payload.commandArgs as string[])
        : [];
    const env = asRecord(payload.env);
    const prompt = typeof payload.prompt === "string" ? payload.prompt : "";
    const context = asRecord(payload.context);

    console.log(pc.cyan(`Adapter: ${adapterType}`));
    if (cwd) console.log(pc.cyan(`Working dir: ${cwd}`));
    if (command) {
      const rendered = args.length > 0 ? `${command} ${args.join(" ")}` : command;
      console.log(pc.cyan(`Command: ${rendered}`));
    }
    if (env) {
      console.log(pc.cyan("Env:"));
      console.log(pc.gray(JSON.stringify(env, null, 2)));
    }
    if (context) {
      console.log(pc.cyan("Context:"));
      console.log(pc.gray(JSON.stringify(context, null, 2)));
    }
    if (prompt) {
      console.log(pc.cyan("Prompt:"));
      console.log(prompt);
    }
  }

  handleEvent(event: HeartbeatRunEventRecord, runId: string): number {
    const payload = asRecord(event.payload) ?? {};
    if (event.runId !== runId) return event.seq ?? 0;

    const eventType =
      typeof event.eventType === "string"
        ? event.eventType
        : typeof event.type === "string"
        ? event.type
        : "";

    if (eventType === "heartbeat.run.status") {
      const status = typeof payload.status === "string" ? payload.status : null;
      if (status) console.log(pc.blue(`[status] ${status}`));
    } else if (eventType === "adapter.invoke") {
      this.adapterInvoke(payload);
    } else if (eventType === "heartbeat.run.log") {
      const stream = typeof payload.stream === "string" ? (payload.stream as LogStream) : "system";
      const chunk = typeof payload.chunk === "string" ? payload.chunk : "";
      if (chunk && (stream === "stdout" || stream === "stderr" || stream === "system")) {
        this.handleStreamChunk(stream, chunk);
      }
    } else if (typeof event.message === "string") {
      console.log(pc.gray(`[event] ${eventType || "heartbeat.run.event"}: ${event.message}`));
    }

    return event.seq ?? 0;
  }
}

function safeParseLogLine(
  line: string,
): { stream: LogStream; chunk: string } | null {
  try {
    const parsed = JSON.parse(line) as { stream?: unknown; chunk?: unknown };
    const stream =
      parsed.stream === "stdout" || parsed.stream === "stderr" || parsed.stream === "system"
        ? (parsed.stream as LogStream)
        : "system";
    const chunk = typeof parsed.chunk === "string" ? parsed.chunk : "";
    return chunk ? { stream, chunk } : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Polling loop
// ---------------------------------------------------------------------------

interface PollResult {
  finalStatus: string | null;
  finalError: string | null;
  finalRun: HeartbeatRun | null;
}

async function pollUntilTerminal(
  api: GitmeshApiClient,
  agent: Agent,
  runId: string,
  renderer: HeartbeatRenderer,
  timeoutMs: number,
): Promise<PollResult> {
  let lastEventSeq = 0;
  let logOffset = 0;
  let finalStatus: string | null = null;
  let finalError: string | null = null;
  let finalRun: HeartbeatRun | null = null;

  const deadline = timeoutMs > 0 ? Date.now() + timeoutMs : null;

  while (true) {
    const events = await api.get<HeartbeatRunEvent[]>(
      `/api/heartbeat-runs/${runId}/events?afterSeq=${lastEventSeq}&limit=${EVENT_FETCH_LIMIT}`,
    );
    for (const event of Array.isArray(events) ? (events as HeartbeatRunEventRecord[]) : []) {
      lastEventSeq = Math.max(lastEventSeq, renderer.handleEvent(event, runId));
    }

    const runList =
      (await api.get<(HeartbeatRun | null)[]>(
        `/api/projects/${agent.projectId}/heartbeat-runs?agentId=${agent.id}`,
      )) || [];
    const currentRun = runList.find((row) => row && row.id === runId) ?? null;
    if (!currentRun) {
      console.error(pc.red("Heartbeat run disappeared"));
      break;
    }

    const currentStatus = currentRun.status as HeartbeatRunStatus | undefined;
    if (currentStatus && currentStatus !== finalStatus) {
      finalStatus = currentStatus;
      console.log(pc.blue(`Status: ${currentStatus}`));
    }
    if (currentStatus && TERMINAL_STATUSES.has(currentStatus)) {
      finalStatus = currentRun.status;
      finalError = currentRun.error;
      finalRun = currentRun;
      break;
    }

    if (deadline && Date.now() >= deadline) {
      finalError = `CLI timed out after ${timeoutMs}ms`;
      finalStatus = "timed_out";
      console.error(pc.yellow(finalError));
      break;
    }

    const logResult = await api.get<{ content: string; nextOffset?: number }>(
      `/api/heartbeat-runs/${runId}/log?offset=${logOffset}&limitBytes=${LOG_FETCH_LIMIT_BYTES}`,
      { ignoreNotFound: true },
    );
    if (logResult && logResult.content) {
      for (const line of logResult.content.split(/\r?\n/)) {
        if (!line) continue;
        const parsed = safeParseLogLine(line);
        if (!parsed) continue;
        renderer.handleStreamChunk(parsed.stream, parsed.chunk);
      }
      if (typeof logResult.nextOffset === "number") {
        logOffset = logResult.nextOffset;
      } else if (logResult.content) {
        logOffset += Buffer.byteLength(logResult.content, "utf8");
      }
    }

    await delay(POLL_INTERVAL_MS);
  }

  return { finalStatus, finalError, finalRun };
}

// ---------------------------------------------------------------------------
// Final reporting
// ---------------------------------------------------------------------------

function reportFinalStatus(
  result: PollResult,
  runId: string,
  debug: boolean,
): void {
  const { finalStatus, finalError, finalRun } = result;

  if (!finalStatus) {
    process.exitCode = 1;
    console.log(pc.gray("Heartbeat stream ended without terminal status"));
    return;
  }

  const label = `Run ${runId} completed with status ${finalStatus}`;
  if (finalStatus === "succeeded") {
    console.log(pc.green(label));
    return;
  }

  console.log(pc.red(label));
  if (finalError) console.log(pc.red(`Error: ${finalError}`));

  if (finalRun) {
    reportClaudeResultDetails(finalRun);
    reportRunExcerpts(finalRun, debug);
  }
  process.exitCode = 1;
}

function reportClaudeResultDetails(run: HeartbeatRun): void {
  const resultObj = asRecord(run.resultJson);
  if (!resultObj) return;

  const subtype = typeof resultObj.subtype === "string" ? resultObj.subtype : "";
  const isError = resultObj.is_error === true;
  const errors = Array.isArray(resultObj.errors)
    ? resultObj.errors.map(asErrorText).filter(Boolean)
    : [];
  const resultText = typeof resultObj.result === "string" ? resultObj.result.trim() : "";

  if (!subtype && !isError && errors.length === 0 && !resultText) return;

  console.log(pc.red("Claude result details:"));
  if (subtype) console.log(pc.red(`  subtype: ${subtype}`));
  if (isError) console.log(pc.red("  is_error: true"));
  if (errors.length > 0) console.log(pc.red(`  errors: ${errors.join(" | ")}`));
  if (resultText) console.log(pc.red(`  result: ${resultText}`));
}

function reportRunExcerpts(run: HeartbeatRun, debug: boolean): void {
  const stderrExcerpt = typeof run.stderrExcerpt === "string" ? run.stderrExcerpt.trim() : "";
  const stdoutExcerpt = typeof run.stdoutExcerpt === "string" ? run.stdoutExcerpt.trim() : "";
  if (stderrExcerpt) {
    console.log(pc.red("stderr excerpt:"));
    console.log(stderrExcerpt);
  }
  if (stdoutExcerpt && (debug || !stderrExcerpt)) {
    console.log(pc.gray("stdout excerpt:"));
    console.log(stdoutExcerpt);
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export async function heartbeatRun(opts: HeartbeatRunOptions): Promise<void> {
  const parsed = parseHeartbeatOpts(opts);

  const ctx = resolveCommandContext({
    config: opts.config,
    context: opts.context,
    profile: opts.profile,
    apiBase: opts.apiBase,
    apiKey: opts.apiKey,
    json: opts.json,
  });
  const api = ctx.api;

  const agent = await api.get<Agent>(`/api/agents/${opts.agentId}`);
  if (!agent || typeof agent !== "object" || !agent.id) {
    console.error(pc.red(`Agent not found: ${opts.agentId}`));
    return;
  }

  const invokeRes = await api.post<InvokedHeartbeat>(
    `/api/agents/${opts.agentId}/wakeup`,
    { source: parsed.source, triggerDetail: parsed.triggerDetail },
  );
  if (!invokeRes) {
    console.error(pc.red("Failed to invoke heartbeat"));
    return;
  }
  if ((invokeRes as { status?: string }).status === "skipped") {
    console.log(pc.yellow("Heartbeat invocation was skipped"));
    return;
  }

  const run = invokeRes as HeartbeatRun;
  console.log(
    pc.cyan(`Invoked heartbeat run ${run.id} for agent ${agent.name} (${agent.id})`),
  );

  const adapterType = agent.adapterType ?? "claude_local";
  const renderer = new HeartbeatRenderer(adapterType, parsed.debug);
  const result = await pollUntilTerminal(api, agent, run.id, renderer, parsed.timeoutMs);

  if (result.finalStatus) {
    renderer.flushBuffered();
  }
  reportFinalStatus(result, run.id, parsed.debug);
}
