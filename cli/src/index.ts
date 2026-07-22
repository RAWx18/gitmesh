import { runCli } from "./program.js";
import { registerLegacyCommands } from "./legacy.js";

runCli("gitmesh-agents", registerLegacyCommands);
