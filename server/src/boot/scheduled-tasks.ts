/**
 * Background scheduled tasks owned by the bootstrap path.
 *
 * Each function returns void; they are fire-and-forget. The caller decides
 * when to call them based on config.
 */
import {
  formatDatabaseBackupResult,
  runDatabaseBackup,
} from "@gitmesh/data";
import { heartbeatService } from "../core/index.js";
import { logger } from "../infra/middleware/logger.js";

export interface HeartbeatSchedulerConfig {
  enabled: boolean;
  intervalMs: number;
}

export function startHeartbeatScheduler(
  db: unknown,
  config: HeartbeatSchedulerConfig,
): void {
  if (!config.enabled) return;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const heartbeat = heartbeatService(db as any);

  // Reap orphaned runs at startup (no threshold - runningProcesses is empty).
  void heartbeat.reapOrphanedRuns().catch((err) => {
    logger.error({ err }, "startup reap of orphaned heartbeat runs failed");
  });

  setInterval(() => {
    void heartbeat
      .tickTimers(new Date())
      .then((result) => {
        if (result.enqueued > 0) {
          logger.info({ ...result }, "heartbeat timer tick enqueued runs");
        }
      })
      .catch((err) => {
        logger.error({ err }, "heartbeat timer tick failed");
      });

    // Periodically reap orphaned runs (5-min staleness threshold).
    void heartbeat
      .reapOrphanedRuns({ staleThresholdMs: 5 * 60 * 1000 })
      .catch((err) => {
        logger.error({ err }, "periodic reap of orphaned heartbeat runs failed");
      });
  }, config.intervalMs);
}

export interface DatabaseBackupConfig {
  enabled: boolean;
  intervalMinutes: number;
  retentionDays: number;
  backupDir: string;
  connectionString: string;
}

export function startDatabaseBackupScheduler(config: DatabaseBackupConfig): void {
  if (!config.enabled) return;

  const intervalMs = config.intervalMinutes * 60 * 1000;
  let inFlight = false;

  const runOnce = async () => {
    if (inFlight) {
      logger.warn(
        "Skipping scheduled database backup because a previous backup is still running",
      );
      return;
    }

    inFlight = true;
    try {
      const result = await runDatabaseBackup({
        connectionString: config.connectionString,
        backupDir: config.backupDir,
        retentionDays: config.retentionDays,
        filenamePrefix: "gitmesh-agents",
      });
      logger.info(
        {
          backupFile: result.backupFile,
          sizeBytes: result.sizeBytes,
          prunedCount: result.prunedCount,
          backupDir: config.backupDir,
          retentionDays: config.retentionDays,
        },
        `Automatic database backup complete: ${formatDatabaseBackupResult(result)}`,
      );
    } catch (err) {
      logger.error({ err, backupDir: config.backupDir }, "Automatic database backup failed");
    } finally {
      inFlight = false;
    }
  };

  logger.info(
    {
      intervalMinutes: config.intervalMinutes,
      retentionDays: config.retentionDays,
      backupDir: config.backupDir,
    },
    "Automatic database backups enabled",
  );

  setInterval(() => {
    void runOnce();
  }, intervalMs);
}

export async function startAttestationWorker(db: unknown): Promise<void> {
  try {
    const { attestationService } = await import("../core/attestation.js");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    attestationService(db as any).startWorker({ intervalMs: 1500 });
    logger.info("Attestation worker started");
  } catch (err) {
    logger.warn({ err }, "Failed to start attestation worker (non-fatal)");
  }
}

export async function seedDefaultProjectTemplates(db: unknown): Promise<void> {
  try {
    const { seedDefaultTemplates } = await import("../core/template-seeds.js");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const seedResult = await seedDefaultTemplates(db as any);
    if (seedResult.seeded > 0) {
      logger.info(
        { seeded: seedResult.seeded, skipped: seedResult.skipped },
        "Default project templates seeded",
      );
    }
  } catch (err) {
    logger.warn({ err }, "Failed to seed default project templates (non-fatal)");
  }
}
