/**
 * Cursor stream-event formatter.
 *
 * Cursor's wire stream is a superset of the other adapters: it carries
 * the same `assistant` / `user` / `result` / `error` events plus a
 * second-generation legacy stream (`step_start`, `text`, `tool_use`,
 * `step_finish`) and Cursor-specific `tool_call` payloads with nested
 * `started` / `completed` subtypes.
 *
 * The implementation is a declarative spec on top of the shared
 * `defineEventFormatter` helper. Each event has a small handler; the
 * `prepare` step normalises the cursor "stdout: …"/"stderr: …" wrapper
 * lines so the per-event handlers see a clean parsed object.
 */

import {
  asNumber,
  asRecord,
  asString,
  safeJsonParse,
  stringifyUnknown,
} from "@gitmesh/adapter-shared/coerce";
import {
  defineEventFormatter,
  emitToolInput,
  selectKindFromType,
  tokensLine,
  type EventEmitter,
  type FormatterContext,
  type FormatterSpec,
} from "@gitmesh/adapter-shared/event-format";

import { normalizeCursorStreamLine } from "../shared/stream.js";

interface CursorContext extends FormatterContext {
  /** subtype, lowercased, trimmed. */
  readonly subtype: string;
}

function prepare(base: FormatterContext): CursorContext {
  const subtype = asString(base.parsed?.subtype).trim().toLowerCase();
  return Object.freeze({ ...base, subtype });
}

/* ----------------------------------------------------------------------- */
/* Helpers shared between user / assistant / legacy tool events            */
/* ----------------------------------------------------------------------- */

function emitText(prefix: string, text: string, color: "user" | "assistant" | "thinking", emit: EventEmitter): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  const line = `${prefix}: ${trimmed}`;
  if (color === "user") emit.muted(line);
  else if (color === "thinking") emit.muted(line);
  else emit.success(line);
}

function emitMessage(
  messageRaw: unknown,
  prefix: "user" | "assistant",
  emit: EventEmitter,
): void {
  if (typeof messageRaw === "string") {
    emitText(prefix, messageRaw, prefix === "user" ? "user" : "assistant", emit);
    return;
  }

  const message = asRecord(messageRaw);
  if (!message) return;

  emitText(prefix, asString(message.text), prefix === "user" ? "user" : "assistant", emit);

  const content = Array.isArray(message.content) ? message.content : [];
  for (const partRaw of content) {
    const part = asRecord(partRaw);
    if (!part) continue;
    const partType = asString(part.type).trim();

    if (partType === "output_text" || partType === "text") {
      emitText(prefix, asString(part.text), prefix === "user" ? "user" : "assistant", emit);
      continue;
    }

    if (prefix !== "assistant") continue;

    if (partType === "thinking") {
      emitText("thinking", asString(part.text), "thinking", emit);
      continue;
    }

    if (partType === "tool_call") {
      const name = asString(part.name, asString(part.tool, "tool"));
      emit.warn(`tool_call: ${name}`);
      emitToolInput(part.input ?? part.arguments ?? part.args, emit);
      continue;
    }

    if (partType === "tool_result") {
      const isError = part.is_error === true || asString(part.status).toLowerCase() === "error";
      const contentText =
        asString(part.output) ||
        asString(part.text) ||
        asString(part.result) ||
        stringifyUnknown(part.output ?? part.result ?? part.text ?? part);
      const header = `tool_result${isError ? " (error)" : ""}`;
      if (isError) {
        emit.error(header);
        if (contentText) emit.error(contentText);
      } else {
        emit.note(header);
        if (contentText) emit.muted(contentText);
      }
    }
  }
}

function handleToolCallTopLevel(ctx: CursorContext, emit: EventEmitter): void {
  const subtype = ctx.subtype;
  const callId = asString(ctx.parsed?.call_id, asString(ctx.parsed?.callId, asString(ctx.parsed?.id, "")));
  const toolCall = asRecord(ctx.parsed?.tool_call ?? ctx.parsed?.toolCall);

  if (!toolCall) {
    emit.warn(`tool_call${subtype ? `: ${subtype}` : ""}`);
    return;
  }

  const [toolName] = Object.keys(toolCall);
  if (!toolName) {
    emit.warn(`tool_call${subtype ? `: ${subtype}` : ""}`);
    return;
  }

  const payload = asRecord(toolCall[toolName]) ?? {};
  const args = payload.args ?? asRecord(payload.function)?.arguments;
  const result =
    payload.result ??
    payload.output ??
    payload.error ??
    asRecord(payload.function)?.result ??
    asRecord(payload.function)?.output;
  const isError =
    ctx.parsed?.is_error === true ||
    payload.is_error === true ||
    subtype === "failed" ||
    subtype === "error" ||
    subtype === "cancelled" ||
    payload.error !== undefined;

  if (subtype === "started" || subtype === "start") {
    emit.warn(`tool_call: ${toolName}${callId ? ` (${callId})` : ""}`);
    if (args !== undefined) emit.muted(stringifyUnknown(args));
    return;
  }

  if (subtype === "completed" || subtype === "complete" || subtype === "finished") {
    const header = `tool_result${isError ? " (error)" : ""}${callId ? ` (${callId})` : ""}`;
    if (isError) {
      emit.error(header);
      if (result !== undefined) emit.error(stringifyUnknown(result));
    } else {
      emit.note(header);
      if (result !== undefined) emit.muted(stringifyUnknown(result));
    }
    return;
  }

  emit.warn(`tool_call: ${toolName}${subtype ? ` (${subtype})` : ""}`);
}

function handleLegacyToolUse(ctx: CursorContext, emit: EventEmitter): void {
  const part = asRecord(ctx.parsed?.part);
  if (!part) {
    emit.warn("tool_use");
    return;
  }
  const tool = asString(part.tool, "tool");
  const callId = asString(part.callID, asString(part.id, ""));
  const state = asRecord(part.state);
  const status = asString(state?.status);
  const input = state?.input;
  const output = asString(state?.output).replace(/\s+$/, "");
  const metadata = asRecord(state?.metadata);
  const exit = asNumber(metadata?.exit, NaN);
  const isError =
    status === "failed" ||
    status === "error" ||
    status === "cancelled" ||
    (Number.isFinite(exit) && exit !== 0);

  emit.warn(`tool_call: ${tool}${callId ? ` (${callId})` : ""}`);
  if (input !== undefined) emitToolInput(input, emit);

  if (status || output) {
    const summaryLine = ["tool_result", status ? `status=${status}` : "", Number.isFinite(exit) ? `exit=${exit}` : ""]
      .filter(Boolean)
      .join(" ");
    if (isError) emit.error(summaryLine);
    else emit.note(summaryLine);
    if (output) {
      if (isError) emit.error(output);
      else emit.muted(output);
    }
  }
}

function handleSystem(ctx: CursorContext, emit: EventEmitter): void {
  const subtype = asString(ctx.parsed?.subtype);
  if (subtype === "init") {
    const sessionId =
      asString(ctx.parsed?.session_id) || asString(ctx.parsed?.sessionId) || asString(ctx.parsed?.sessionID);
    const model = asString(ctx.parsed?.model);
    const details = [sessionId ? `session: ${sessionId}` : "", model ? `model: ${model}` : ""]
      .filter(Boolean)
      .join(", ");
    emit.info(`Cursor init${details ? ` (${details})` : ""}`);
    return;
  }
  emit.info(`system: ${subtype || "event"}`);
}

function handleResult(ctx: CursorContext, emit: EventEmitter): void {
  const usage = asRecord(ctx.parsed?.usage);
  const input = asNumber(usage?.input_tokens, asNumber(usage?.inputTokens));
  const output = asNumber(usage?.output_tokens, asNumber(usage?.outputTokens));
  const cached = asNumber(
    usage?.cached_input_tokens,
    asNumber(usage?.cachedInputTokens, asNumber(usage?.cache_read_input_tokens)),
  );
  const cost = asNumber(ctx.parsed?.total_cost_usd, asNumber(ctx.parsed?.cost_usd, asNumber(ctx.parsed?.cost)));
  const subtype = asString(ctx.parsed?.subtype, "result");
  const isError = ctx.parsed?.is_error === true || subtype === "error" || subtype === "failed";

  emit.info(`result: subtype=${subtype}`);
  emit.info(tokensLine({ input, output, cached, cost }));

  const resultText = asString(ctx.parsed?.result).trim();
  if (resultText) {
    const line = `assistant: ${resultText}`;
    if (isError) emit.error(line);
    else emit.success(line);
  }

  const errors = Array.isArray(ctx.parsed?.errors)
    ? (ctx.parsed!.errors as unknown[]).map((value) => stringifyUnknown(value)).filter(Boolean)
    : [];
  if (errors.length > 0) emit.error(`errors: ${errors.join(" | ")}`);
}

function handleStepFinish(ctx: CursorContext, emit: EventEmitter): void {
  const part = asRecord(ctx.parsed?.part);
  const tokens = asRecord(part?.tokens);
  const cache = asRecord(tokens?.cache);
  const reason = asString(part?.reason, "step_finish");
  const input = asNumber(tokens?.input);
  const output = asNumber(tokens?.output);
  const cached = asNumber(cache?.read);
  const cost = asNumber(part?.cost);
  emit.info(`step finished: reason=${reason}`);
  emit.info(tokensLine({ input, output, cached, cost }));
}

const spec: FormatterSpec<CursorContext> = {
  name: "cursor",
  prepare,
  selectKind: selectKindFromType,

  events: {
    system: { handle: handleSystem },
    assistant: {
      handle(ctx, emit) {
        emitMessage(ctx.parsed?.message, "assistant", emit);
      },
    },
    user: {
      handle(ctx, emit) {
        emitMessage(ctx.parsed?.message, "user", emit);
      },
    },
    thinking: {
      handle(ctx, emit) {
        const text =
          asString(ctx.parsed?.text).trim() || asString(asRecord(ctx.parsed?.delta)?.text).trim();
        if (text) emit.muted(`thinking: ${text}`);
      },
    },
    tool_call: { handle: handleToolCallTopLevel },
    result: { handle: handleResult },
    error: {
      handle(ctx, emit) {
        const message =
          asString(ctx.parsed?.message) ||
          stringifyUnknown(ctx.parsed?.error ?? ctx.parsed?.detail) ||
          ctx.line;
        emit.error(`error: ${message}`);
      },
    },

    // Legacy stream-json shapes - kept as separate events so the spec stays flat.
    step_start: {
      handle(ctx, emit) {
        const sessionId = asString(ctx.parsed?.sessionID);
        emit.info(`step started${sessionId ? ` (session: ${sessionId})` : ""}`);
      },
    },
    text: {
      handle(ctx, emit) {
        const part = asRecord(ctx.parsed?.part);
        const text = asString(part?.text);
        if (text) emit.success(`assistant: ${text}`);
      },
    },
    tool_use: { handle: handleLegacyToolUse },
    step_finish: { handle: handleStepFinish },
  },

  fallback(ctx, emit) {
    emit.raw(ctx.line);
  },
};

const baseFormatter = defineEventFormatter<CursorContext>(spec);

/**
 * Strip Cursor's optional `stdout: …` / `stderr: …` wrapper before delegating
 * to the shared formatter. The legacy implementation called
 * `normalizeCursorStreamLine` on the raw line and dropped the result on empty
 * input; we preserve that behaviour here.
 */
export function printCursorStreamEvent(raw: string, debug: boolean): void {
  const normalised = normalizeCursorStreamLine(raw).line;
  if (!normalised) return;

  // The shared helper expects to JSON-parse the line itself, but we still
  // need to fall back to printing the raw normalised line when it isn't
  // JSON (the legacy formatter did `console.log(line)` in that case).
  if (asRecord(safeJsonParse(normalised)) === null) {
    console.log(normalised);
    return;
  }
  baseFormatter(normalised, debug);
}
