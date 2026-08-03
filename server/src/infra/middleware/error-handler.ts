import type { Request, Response, NextFunction } from "express";
import { ZodError } from "zod";
import { HttpError } from "../../errors.js";

/**
 * Captures request context at the time of an error for structured logging
 * and debugging. Stored on the response object so log writers can access it.
 */
interface ErrorDetails {
  message: string;
  stack?: string;
  name?: string;
  details?: unknown;
  raw?: unknown;
}

interface ErrorSnapshot {
  error: ErrorDetails;
  method: string;
  url: string;
  reqBody?: unknown;
  reqParams?: unknown;
  reqQuery?: unknown;
}

function captureRequestSnapshot(req: Request, error: ErrorDetails, rawError?: Error): ErrorSnapshot {
  const finalError = rawError ? { ...error, stack: rawError.stack } : error;
  return {
    error: finalError,
    method: req.method,
    url: req.originalUrl,
    reqBody: req.body,
    reqParams: req.params,
    reqQuery: req.query,
  };
}

function attachErrorContext(res: Response, err: unknown, snapshot: ErrorSnapshot): void {
  // pino-http augments Response with `err?: Error`; widen via any to allow non-Error throws.
  // The logger middleware reads (res as any).err and __errorContext to populate pino fields.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const target = res as any;
  target.err = err;
  target.__errorContext = snapshot;
}

/**
 * Global Express error handler for the GitMesh Agents API server.
 *
 * Handles three error categories:
 * 1. HttpError - application-level errors (4xx/5xx), returned as JSON
 * 2. ZodError - request validation failures, returned as JSON with issue details
 * 3. Unknown errors - treated as internal server errors (500), details are captured
 *    for logging but sanitized in the client response
 */
export function errorHandler(
  err: unknown,
  req: Request,
  res: Response,
  _next: NextFunction,
): void {
  // Application errors with explicit HTTP status
  if (err instanceof HttpError) {
    if (err.status >= 500) {
      // Only attach full context for 5xx - 4xx are client-visible and should not leak internals.
      // The logger middleware reads __errorContext + err to enrich pino HTTP logs.
      attachErrorContext(
        res,
        err,
        captureRequestSnapshot(
          req,
          { message: err.message, stack: err.stack, name: err.name, details: err.details },
          err instanceof Error ? err : undefined,
        ),
      );
    }
    res.status(err.status).json({
      error: err.message,
      ...(err.details ? { details: err.details } : {}),
    });
    return;
  }

  // Zod validation errors from request body/params/query validation
  if (err instanceof ZodError) {
    res.status(400).json({
      error: "Request validation failed",
      details: err.errors,
    });
    return;
  }

  // Unknown error - treat as internal server error
  const rootCause = err instanceof Error ? err : new Error(String(err));
  const errorDetails: ErrorDetails = {
    message: rootCause.message,
    stack: rootCause.stack,
    name: rootCause.name,
    ...(!(err instanceof Error) ? { raw: err } : {}),
  };

  attachErrorContext(res, err, captureRequestSnapshot(req, errorDetails, rootCause));

  res.status(500).json({ error: "Internal server error" });
}
