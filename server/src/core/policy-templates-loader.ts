/**
 * Policy Templates Loader
 *
 * Reads versioned YAML templates from `playbooks/policy-templates/` at
 * runtime. Each template carries operator-facing metadata (title, what
 * it does, what it protects, audit example) plus one or more validated
 * policy bodies that are reused as inputs to `policyEngineService.createPolicy`.
 *
 * Two file shapes are supported:
 *   1. `metadata` + `policy`: single-policy template
 *   2. `metadata` + `policies: [...]`: multi-policy template (e.g. dependency-update-policy)
 *
 * The loader caches the parsed result; in-process cache invalidation is
 * exposed for dev/test callers via `clearPolicyTemplateCache`.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "js-yaml";
import { compilePoliciesFromYAML, type CompiledPolicy } from "./policy-compiler.js";

export interface PolicyTemplateMetadata {
  slug: string;
  title: string;
  whatItDoes: string;
  whatItProtects: string;
  whenToUse: string;
  auditExample: string;
  videoUrl: string | null;
  defaultEnabled: boolean;
}

export interface PolicyTemplate {
  metadata: PolicyTemplateMetadata;
  policies: CompiledPolicy[];
  /** Path on disk for diagnostics. */
  sourcePath: string;
}

export interface PolicyTemplateLoadError {
  slug: string | null;
  sourcePath: string;
  error: string;
}

const CACHE_KEY = Symbol.for("gitmesh.policyTemplates");
type CacheEntry = { templates: PolicyTemplate[]; errors: PolicyTemplateLoadError[]; loadedFrom: string | null };

function getGlobalCache(): { value: CacheEntry | null } {
  const g = globalThis as unknown as Record<symbol, unknown>;
  if (!g[CACHE_KEY]) {
    g[CACHE_KEY] = { value: null };
  }
  return g[CACHE_KEY] as { value: CacheEntry | null };
}

export function clearPolicyTemplateCache(): void {
  getGlobalCache().value = null;
}

export function loadPolicyTemplates(): {
  templates: PolicyTemplate[];
  errors: PolicyTemplateLoadError[];
  loadedFrom: string | null;
} {
  const cache = getGlobalCache();
  if (cache.value) return cache.value;

  const templatesDir = resolveTemplatesDir();
  const result: CacheEntry = { templates: [], errors: [], loadedFrom: templatesDir };

  if (!templatesDir) {
    cache.value = result;
    return result;
  }

  let entries: string[];
  try {
    entries = fs.readdirSync(templatesDir).filter((f) => f.endsWith(".yaml") || f.endsWith(".yml"));
  } catch (err) {
    result.errors.push({
      slug: null,
      sourcePath: templatesDir,
      error: `Could not read templates directory: ${err instanceof Error ? err.message : String(err)}`,
    });
    cache.value = result;
    return result;
  }

  for (const fileName of entries.sort()) {
    const filePath = path.join(templatesDir, fileName);
    try {
      const raw = fs.readFileSync(filePath, "utf8");
      const parsed = YAML.load(raw);
      if (!isObject(parsed)) {
        result.errors.push({ slug: null, sourcePath: filePath, error: "Template root must be an object" });
        continue;
      }

      const metadata = parseMetadata(parsed.metadata, fileName);
      const policyDefs = collectPolicyDefs(parsed);
      if (policyDefs.length === 0) {
        result.errors.push({
          slug: metadata.slug,
          sourcePath: filePath,
          error: "Template must define `policy` or `policies` block",
        });
        continue;
      }

      const compiled = compilePoliciesFromYAML(YAML.dump(policyDefs));
      if (compiled.errors.length > 0) {
        for (const e of compiled.errors) {
          result.errors.push({
            slug: metadata.slug,
            sourcePath: filePath,
            error: `Policy "${e.policy}" failed to compile: ${e.error}`,
          });
        }
        continue;
      }

      result.templates.push({ metadata, policies: compiled.policies, sourcePath: filePath });
    } catch (err) {
      result.errors.push({
        slug: null,
        sourcePath: filePath,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  cache.value = result;
  return result;
}

export function findPolicyTemplate(slug: string): PolicyTemplate | null {
  const { templates } = loadPolicyTemplates();
  const normalized = slug.trim().toLowerCase();
  return templates.find((t) => t.metadata.slug.toLowerCase() === normalized) ?? null;
}

export function getDefaultEnabledTemplates(): PolicyTemplate[] {
  return loadPolicyTemplates().templates.filter((t) => t.metadata.defaultEnabled);
}

function parseMetadata(raw: unknown, fileName: string): PolicyTemplateMetadata {
  if (!isObject(raw)) {
    throw new Error(`Template ${fileName} is missing metadata block`);
  }
  const slug = typeof raw.slug === "string" ? raw.slug.trim() : path.basename(fileName).replace(/\.ya?ml$/, "");
  if (!slug) throw new Error(`Template ${fileName} has empty slug`);

  return {
    slug,
    title: stringOr(raw.title, slug),
    whatItDoes: stringOr(raw.whatItDoes, ""),
    whatItProtects: stringOr(raw.whatItProtects, ""),
    whenToUse: stringOr(raw.whenToUse, ""),
    auditExample: stringOr(raw.auditExample, ""),
    videoUrl: typeof raw.videoUrl === "string" ? raw.videoUrl : null,
    defaultEnabled: raw.defaultEnabled === true,
  };
}

function collectPolicyDefs(parsed: Record<string, unknown>): unknown[] {
  if (Array.isArray(parsed.policies)) return parsed.policies;
  if (isObject(parsed.policy)) return [parsed.policy];
  return [];
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringOr(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function resolveTemplatesDir(): string | null {
  const moduleDir = path.dirname(fileURLToPath(import.meta.url));
  const candidates = [
    // dev: server/src/core -> ../../../playbooks/policy-templates
    path.resolve(moduleDir, "../../../playbooks/policy-templates"),
    // built: server/dist/core -> ../../playbooks/policy-templates
    path.resolve(moduleDir, "../../playbooks/policy-templates"),
    // cwd (monorepo root)
    path.resolve(process.cwd(), "playbooks/policy-templates"),
  ];
  for (const candidate of candidates) {
    try {
      const stat = fs.statSync(candidate);
      if (stat.isDirectory()) return candidate;
    } catch {
      // continue
    }
  }
  return null;
}
