/**
 * Claude stream-event formatter.
 *
 * Implemented as a declarative spec on top of the shared
 * `defineEventFormatter` helper. The output strings emitted here are
 * byte-for-byte identical to the legacy imperative version; only the
 * source structure changed - the wire format is preserved.
 */

import {
  asRecord,
  asString,
  ERROR_TEXT_PRESETS,
  extractErrorText,
} from "@gitmesh/adapter-shared/coerce";
import {
  defineEventFormatter,
  emitToolInput,
  selectKindFromType,
  tokensLine,
  type EventEmitter,
  type FormatterContext,
} from "@gitmesh/adapter-shared/event-format";

// Claude's error envelopes follow the codex/codex-style key precedence:
// `message` > `error` > `code` > JSON-stringified record.
const claudeErrorText = (value: unknown) => extractErrorText(value, ERROR_TEXT_PRESETS.codex);

interface ClaudeContext extends FormatterContext {
  readonly subtype: string;
  readonly isError: boolean;
}

function prepare(base: FormatterContext): ClaudeContext {
  const subtype = asString(base.parsed?.subtype);
  const isError = base.parsed?.is_error === true;
  return Object.freeze({ ...base, subtype, isError });
}

function emitAssistantBlocks(message: Record<string, unknown>, emit: EventEmitter): void {
  const content = Array.isArray(message.content) ? message.content : [];
  for (const blockRaw of content) {
    const block = asRecord(blockRaw);
    if (!block) continue;
    const blockType = asString(block.type);

    if (blockType === "text") {
      const text = asString(block.text);
      if (text) emit.success(`assistant: ${text}`);
      continue;
    }

    if (blockType === "tool_use") {
      const name = asString(block.name, "unknown");
      emit.warn(`tool_call: ${name}`);
      emitToolInput(block.input, emit);
    }
  }
}

/**
 * The "system" event in Claude's stream is split by `subtype`. We treat the
 * `init` variant as its own logical event so the spec stays declarative.
 */
function selectClaudeKind(ctx: ClaudeContext): string | null {
  const type = selectKindFromType(ctx);
  if (type === "system" && ctx.subtype === "init") return "system.init";
  return type;
}

/** Format a Claude `result` event line: tokens, optional `result:` body, optional error summary. */
function handleResult(ctx: ClaudeContext, emit: EventEmitter): void {
  const usage = asRecord(ctx.parsed?.usage) ?? {};
  const input = Number(usage.input_tokens ?? 0);
  const output = Number(usage.output_tokens ?? 0);
  const cached = Number(usage.cache_read_input_tokens ?? 0);
  const cost = Number(ctx.parsed?.total_cost_usd ?? 0);
  const resultText = asString(ctx.parsed?.result);

  if (resultText) {
    emit.success("result:");
    emit.raw(resultText);
  }

  const errors = Array.isArray(ctx.parsed?.errors)
    ? (ctx.parsed!.errors as unknown[]).map(claudeErrorText).filter(Boolean)
    : [];
  if (ctx.subtype.startsWith("error") || ctx.isError || errors.length > 0) {
    emit.error(
      `claude_result: subtype=${ctx.subtype || "unknown"} is_error=${ctx.isError ? "true" : "false"}`,
    );
    if (errors.length > 0) emit.error(`claude_errors: ${errors.join(" | ")}`);
  }

  emit.info(
    tokensLine({
      input: Number.isFinite(input) ? input : 0,
      output: Number.isFinite(output) ? output : 0,
      cached: Number.isFinite(cached) ? cached : 0,
      cost: Number.isFinite(cost) ? cost : 0,
    }),
  );
}

const formatter = defineEventFormatter<ClaudeContext>({
  name: "claude",
  prepare,
  selectKind: selectClaudeKind,

  events: {
    "system.init": {
      label: "session initialised",
      handle(ctx, emit) {
        const model = asString(ctx.parsed?.model, "unknown");
        const sessionId = asString(ctx.parsed?.session_id);
        emit.info(`Claude initialized (model: ${model}${sessionId ? `, session: ${sessionId}` : ""})`);
      },
    },

    assistant: {
      label: "assistant message blocks",
      handle(ctx, emit) {
        const message = asRecord(ctx.parsed?.message) ?? {};
        emitAssistantBlocks(message, emit);
      },
    },

    result: {
      label: "final result + token usage",
      handle: handleResult,
    },
  },

  // Claude uniquely keeps debug-mode passthrough for unrecognised events;
  // every other adapter unconditionally echoes the raw line. The legacy
  // implementation only logged when `debug=true`, so we mirror that.
  fallback(ctx, emit) {
    if (ctx.debug) emit.muted(ctx.line);
  },

  onUnparseable(line, emit) {
    emit.raw(line);
  },
});

export const printClaudeStreamEvent: (raw: string, debug: boolean) => void = formatter;
