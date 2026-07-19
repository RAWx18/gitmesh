import { describe, expect, it } from "vitest";
import { workspaceIRSchema, type WorkspaceIR } from "./index.js";

describe("workspaceIRSchema", () => {
  it("parses an empty object", () => {
    const ir: WorkspaceIR = workspaceIRSchema.parse({});
    expect(ir).toEqual({});
  });

  it("rejects unknown keys", () => {
    const result = workspaceIRSchema.safeParse({ unexpected: true });
    expect(result.success).toBe(false);
  });

  it("rejects non-object input", () => {
    expect(workspaceIRSchema.safeParse(null).success).toBe(false);
    expect(workspaceIRSchema.safeParse("ir").success).toBe(false);
  });
});
