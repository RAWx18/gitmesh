// Monorepo dev entry for the new CLI: the full tree including working
// `gitmesh legacy` commands (T0.3 AC). The published gitmesh-cli package
// bundles src/gitmesh.ts instead, which ships a legacy stub so the wedge
// package carries no server/database code (pivot §10.8, ADR-002).
import { runCli } from "./program.js";
import { registerLegacyCommands } from "./legacy.js";

runCli("gitmesh", registerLegacyCommands);
