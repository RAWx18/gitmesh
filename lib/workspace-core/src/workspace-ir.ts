import { z } from "zod";

/**
 * Workspace intermediate representation (IR).
 *
 * Intentionally empty at this stage (pivot T0.1); the full shape
 * (instructions, mcpServers, skills, commands, subagents,
 * permissionModel, agentOverrides) lands with T3.1.
 */
export const workspaceIRSchema = z.object({}).strict();

export type WorkspaceIR = z.infer<typeof workspaceIRSchema>;
