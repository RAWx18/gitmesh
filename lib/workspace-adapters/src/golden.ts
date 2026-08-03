import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

/**
 * Golden-fixture harness (pivot T0.5, hard rule 4).
 *
 * Every detector and emitter ships fixtures laid out as
 * `fixtures/<adapter>/<case>/{input-repo/, expected/}`. A runner produces
 * output files from `input-repo/` and this harness compares them against
 * `expected/` **byte-exactly**: no newline, encoding, or whitespace
 * normalization of any kind, matching the determinism rule (same inputs →
 * byte-identical outputs).
 *
 * Limitations, by design: expected trees contain regular files only
 * (symlinks throw - git checkouts differ across platforms), and empty
 * directories are ignored (git cannot represent them).
 */

/** One discovered fixture case. */
export interface GoldenCase {
  /** Adapter directory name, e.g. `claude-code`. */
  adapter: string;
  /** Case directory name, e.g. `fresh-emit`. */
  name: string;
  /** Absolute path of the case directory. */
  dir: string;
  /** Absolute path of the case's `input-repo/` tree. */
  inputRepoDir: string;
  /** Absolute path of the case's `expected/` tree. */
  expectedDir: string;
}

/** A file produced by a golden runner, path relative to the output root. */
export interface GoldenOutputFile {
  /** POSIX-style relative path, e.g. `nested/config.json`. */
  path: string;
  /** Exact bytes to compare; strings are encoded as UTF-8 verbatim. */
  content: string | Uint8Array;
}

/** Produces output files for one fixture's `input-repo/`. */
export type GoldenRunner = (
  inputRepoDir: string,
) => GoldenOutputFile[] | Promise<GoldenOutputFile[]>;

/** One byte-exact deviation between produced output and `expected/`. */
export type GoldenDifference =
  | { kind: "missing"; path: string }
  | { kind: "unexpected"; path: string }
  | { kind: "content"; path: string; firstDiffByte: number; detail: string };

export interface GoldenResult {
  ok: boolean;
  /** Sorted by path, then kind - deterministic across runs. */
  differences: GoldenDifference[];
}

/**
 * Discovers every `<adapter>/<case>` fixture under `fixturesRoot`, sorted for
 * deterministic test ordering. A case directory missing `input-repo/` or
 * `expected/` is a structural error and throws.
 */
export function listGoldenCases(fixturesRoot: string): GoldenCase[] {
  const cases: GoldenCase[] = [];
  for (const adapter of listSubdirectories(fixturesRoot)) {
    const adapterDir = join(fixturesRoot, adapter);
    for (const name of listSubdirectories(adapterDir)) {
      const dir = join(adapterDir, name);
      const inputRepoDir = join(dir, "input-repo");
      const expectedDir = join(dir, "expected");
      for (const required of [inputRepoDir, expectedDir]) {
        if (!isDirectory(required)) {
          throw new Error(
            `Malformed golden fixture ${adapter}/${name}: missing ${required}`,
          );
        }
      }
      cases.push({ adapter, name, dir, inputRepoDir, expectedDir });
    }
  }
  return cases;
}

/** Runs `runner` against one case and byte-compares its output to `expected/`. */
export async function runGoldenCase(
  goldenCase: Pick<GoldenCase, "inputRepoDir" | "expectedDir">,
  runner: GoldenRunner,
): Promise<GoldenResult> {
  const expected = readTree(goldenCase.expectedDir);
  const actual = collectOutputs(await runner(goldenCase.inputRepoDir));

  const differences: GoldenDifference[] = [];
  for (const [path, expectedBytes] of expected) {
    const actualBytes = actual.get(path);
    if (actualBytes === undefined) {
      differences.push({ kind: "missing", path });
      continue;
    }
    const firstDiffByte = firstDifference(expectedBytes, actualBytes);
    if (firstDiffByte !== -1) {
      differences.push({
        kind: "content",
        path,
        firstDiffByte,
        detail: describeDifference(expectedBytes, actualBytes, firstDiffByte),
      });
    }
  }
  for (const path of actual.keys()) {
    if (!expected.has(path)) {
      differences.push({ kind: "unexpected", path });
    }
  }
  differences.sort((a, b) =>
    a.path === b.path ? a.kind.localeCompare(b.kind) : a.path < b.path ? -1 : 1,
  );
  return { ok: differences.length === 0, differences };
}

/** Like {@link runGoldenCase}, but throws a readable report on any deviation. */
export async function assertGoldenCase(
  goldenCase: Pick<GoldenCase, "inputRepoDir" | "expectedDir">,
  runner: GoldenRunner,
): Promise<void> {
  const result = await runGoldenCase(goldenCase, runner);
  if (!result.ok) {
    const lines = result.differences.map((d) => {
      switch (d.kind) {
        case "missing":
          return `  missing:    ${d.path} (expected but not produced)`;
        case "unexpected":
          return `  unexpected: ${d.path} (produced but not expected)`;
        case "content":
          return `  differs:    ${d.path} at byte ${d.firstDiffByte} - ${d.detail}`;
      }
    });
    throw new Error(
      `Golden fixture mismatch against ${goldenCase.expectedDir}:\n${lines.join("\n")}`,
    );
  }
}

/**
 * Reads a directory tree as runner outputs - for runners that write into a
 * scratch directory (or identity checks over `input-repo/` itself).
 */
export function readTreeAsGoldenOutputs(rootDir: string): GoldenOutputFile[] {
  return [...readTree(rootDir)].map(([path, content]) => ({ path, content }));
}

/** Reads a directory tree into `posix-relative-path → bytes`, files only. */
function readTree(root: string, prefix = ""): Map<string, Uint8Array> {
  const files = new Map<string, Uint8Array>();
  const entries = readdirSync(root, { withFileTypes: true }).sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  );
  for (const entry of entries) {
    const absolute = join(root, entry.name);
    const relative = prefix === "" ? entry.name : `${prefix}/${entry.name}`;
    if (entry.isSymbolicLink()) {
      throw new Error(`Golden fixtures must contain regular files only: ${absolute}`);
    }
    if (entry.isDirectory()) {
      for (const [path, bytes] of readTree(absolute, relative)) {
        files.set(path, bytes);
      }
    } else if (entry.isFile()) {
      files.set(relative, readFileSync(absolute));
    } else {
      throw new Error(`Golden fixtures must contain regular files only: ${absolute}`);
    }
  }
  return files;
}

/** Validates runner output paths and materializes contents as bytes. */
function collectOutputs(outputs: readonly GoldenOutputFile[]): Map<string, Uint8Array> {
  const files = new Map<string, Uint8Array>();
  for (const output of outputs) {
    const path = output.path;
    const segments = path.split("/");
    if (
      path === "" ||
      path.startsWith("/") ||
      path.includes("\\") ||
      segments.includes("..") ||
      segments.includes(".") ||
      segments.includes("")
    ) {
      throw new Error(
        `Golden runner produced an invalid output path: ${JSON.stringify(path)} ` +
          "(paths must be normalized, POSIX-style, and relative)",
      );
    }
    if (files.has(path)) {
      throw new Error(`Golden runner produced duplicate output path: ${path}`);
    }
    files.set(
      path,
      typeof output.content === "string"
        ? new TextEncoder().encode(output.content)
        : output.content,
    );
  }
  return files;
}

/** Index of the first differing byte, or -1 when identical. */
function firstDifference(a: Uint8Array, b: Uint8Array): number {
  const shorter = Math.min(a.length, b.length);
  for (let i = 0; i < shorter; i++) {
    if (a[i] !== b[i]) {
      return i;
    }
  }
  return a.length === b.length ? -1 : shorter;
}

/** Renders the bytes around `index` on both sides for the mismatch report. */
function describeDifference(
  expected: Uint8Array,
  actual: Uint8Array,
  index: number,
): string {
  return `expected ${previewAt(expected, index)}, got ${previewAt(actual, index)}`;
}

function previewAt(bytes: Uint8Array, index: number): string {
  if (index >= bytes.length) {
    return `end of file (${bytes.length} bytes)`;
  }
  const window = bytes.slice(index, index + 16);
  const printable = new TextDecoder("utf-8", { fatal: false }).decode(window);
  return JSON.stringify(printable);
}

function listSubdirectories(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}
