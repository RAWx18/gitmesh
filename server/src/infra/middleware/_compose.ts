/**
 * Predicate-style guard composition helpers.
 *
 * Guards are declared as small specs: a name, an optional `when` filter
 * (skip the guard entirely), a `check` predicate (return true to allow), and
 * a `deny` describer that produces the rejection response.
 *
 * The composed Express handler reads the spec, runs the predicate, and either
 * calls `next()` or sends the deny response. Multiple guard specs can be
 * combined with `composeGuards` so a route mounts a single middleware while
 * keeping each rule isolated and individually testable.
 */
import type { Request, Response, RequestHandler } from "express";

/**
 * A formal description of a guard rule. The shape intentionally separates
 * "should this guard run?" from "does the request pass?" from "what does
 * a failure look like?" so callers can unit-test each axis on its own.
 */
export interface GuardSpec {
  /** Human-readable identifier for logs / debugging. */
  name: string;
  /**
   * Optional pre-check. When it returns false the guard is treated as a
   * no-op and `next()` is called. Used for opt-in rules (e.g. only running
   * on mutating verbs, or only when a feature flag is set).
   */
  when?: (req: Request) => boolean;
  /** True => request passes the guard, false => deny. */
  check: (req: Request) => boolean;
  /** Build the rejection payload. Receives the same request for context. */
  deny: (req: Request) => GuardDenial;
}

/** Description of a rejection: the HTTP status, error text, and content negotiation hint. */
export interface GuardDenial {
  status: number;
  error: string;
  /** When set, force a content-type. Otherwise responds with JSON. */
  contentType?: "json" | "text";
}

function sendDenial(res: Response, denial: GuardDenial): void {
  if (denial.contentType === "text") {
    res.status(denial.status).type("text/plain").send(denial.error);
    return;
  }
  res.status(denial.status).json({ error: denial.error });
}

/**
 * Convert a single guard spec into an Express middleware. The runtime
 * is small on purpose: each spec is responsible for its own logic and the
 * compose layer is just plumbing.
 */
export function defineGuard(spec: GuardSpec): RequestHandler {
  return (req, res, next) => {
    if (spec.when && !spec.when(req)) {
      next();
      return;
    }
    if (spec.check(req)) {
      next();
      return;
    }
    sendDenial(res, spec.deny(req));
  };
}

/**
 * Compose multiple guard specs into a single middleware. Each guard is
 * evaluated in order; the first denial wins. This avoids stacking many
 * tiny middlewares on a route mount.
 */
export function composeGuards(...specs: GuardSpec[]): RequestHandler {
  return (req, res, next) => {
    for (const spec of specs) {
      if (spec.when && !spec.when(req)) continue;
      if (spec.check(req)) continue;
      sendDenial(res, spec.deny(req));
      return;
    }
    next();
  };
}

/** Convenience - a guard that wants to run on mutating verbs only. */
export const mutatingMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);
export function isMutating(req: Request): boolean {
  return mutatingMethods.has(req.method.toUpperCase());
}

/** Hint helper used by hostname / API paths - JSON for /api or json-accept, text otherwise. */
export function negotiateContentType(req: Request): "json" | "text" {
  if (req.path.startsWith("/api")) return "json";
  if (req.accepts(["json", "html", "text"]) === "json") return "json";
  return "text";
}
