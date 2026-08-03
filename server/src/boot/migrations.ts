/**
 * Database migration orchestration for the bootstrap path.
 *
 * Extracted from `index.ts` so the main entrypoint reads as a sequence of
 * boot-step calls, while the migration prompt + apply behaviour lives in
 * one isolated module that can be tested independently.
 */
import { stdin, stdout } from "node:process";
import { createInterface } from "node:readline/promises";
import {
  applyPendingMigrations,
  inspectMigrations,
  reconcilePendingMigrationHistory,
} from "@gitmesh/data";
import { logger } from "../infra/middleware/logger.js";

export type MigrationSummary =
  | "skipped"
  | "already applied"
  | "applied (empty database)"
  | "applied (pending migrations)"
  | "pending migrations skipped";

export interface EnsureMigrationsOptions {
  autoApply?: boolean;
}

function formatPendingMigrationSummary(migrations: string[]): string {
  if (migrations.length === 0) return "none";
  return migrations.length > 3
    ? `${migrations.slice(0, 3).join(", ")} (+${migrations.length - 3} more)`
    : migrations.join(", ");
}

async function promptApplyMigrations(migrations: string[]): Promise<boolean> {
  if (process.env.GITMESH_MIGRATION_AUTO_APPLY === "true") return true;
  // "never" means do not interactively prompt - still apply pending migrations
  // so startup does not leave the DB behind schema (TTY dev with .env was
  // skipping before this fix).
  if (process.env.GITMESH_MIGRATION_PROMPT === "never") return true;
  if (!stdin.isTTY || !stdout.isTTY) return true;

  const prompt = createInterface({ input: stdin, output: stdout });
  try {
    const answer = (
      await prompt.question(
        `Apply pending migrations (${formatPendingMigrationSummary(migrations)}) now? (y/N): `,
      )
    )
      .trim()
      .toLowerCase();
    return answer === "y" || answer === "yes";
  } finally {
    prompt.close();
  }
}

export async function ensureMigrations(
  connectionString: string,
  label: string,
  opts?: EnsureMigrationsOptions,
): Promise<MigrationSummary> {
  const autoApply = opts?.autoApply === true;
  let state = await inspectMigrations(connectionString);

  if (state.status === "needsMigrations" && state.reason === "pending-migrations") {
    const repair = await reconcilePendingMigrationHistory(connectionString);
    if (repair.repairedMigrations.length > 0) {
      logger.warn(
        { repairedMigrations: repair.repairedMigrations },
        `${label} had drifted migration history; repaired migration journal entries from existing schema state.`,
      );
      state = await inspectMigrations(connectionString);
      if (state.status === "upToDate") return "already applied";
    }
  }
  if (state.status === "upToDate") return "already applied";

  if (state.status === "needsMigrations" && state.reason === "no-migration-journal-non-empty-db") {
    logger.warn(
      { tableCount: state.tableCount },
      `${label} has existing tables but no migration journal. Run migrations manually to sync schema.`,
    );
    const apply = autoApply ? true : await promptApplyMigrations(state.pendingMigrations);
    if (!apply) {
      logger.warn(
        { pendingMigrations: state.pendingMigrations },
        `${label} has pending migrations; continuing without applying. Run pnpm db:migrate to apply before startup.`,
      );
      return "pending migrations skipped";
    }

    logger.info(
      { pendingMigrations: state.pendingMigrations },
      `Applying ${state.pendingMigrations.length} pending migrations for ${label}`,
    );
    await applyPendingMigrations(connectionString);
    return "applied (pending migrations)";
  }

  const apply = autoApply ? true : await promptApplyMigrations(state.pendingMigrations);
  if (!apply) {
    logger.warn(
      { pendingMigrations: state.pendingMigrations },
      `${label} has pending migrations; continuing without applying. Run pnpm db:migrate to apply before startup.`,
    );
    return "pending migrations skipped";
  }

  logger.info(
    { pendingMigrations: state.pendingMigrations },
    `Applying ${state.pendingMigrations.length} pending migrations for ${label}`,
  );
  await applyPendingMigrations(connectionString);
  return "applied (pending migrations)";
}
