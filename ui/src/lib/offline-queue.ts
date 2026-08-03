/**
 * Offline Approval Queue Service
 *
 * Uses IndexedDB to queue approval/rejection actions when offline,
 * and syncs them when connectivity is restored.
 */

import type { Approval } from "@gitmesh/core";

const DB_NAME = "gitmesh-offline";
const DB_VERSION = 1;
const STORE_NAME = "pending-actions";

export interface QueuedAction {
  id: string;
  action: "approve" | "reject" | "requestRevision";
  approvalId: string;
  decisionNote?: string;
  queuedAt: number;
  retryCount: number;
}

export interface PendingApprovalCache {
  approvalId: string;
  approval: Approval;
  queuedAt: number;
}

// ─── IndexedDB Helpers ─────────────────────────────────────────────────────────

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("pending-approvals")) {
        db.createObjectStore("pending-approvals", { keyPath: "approvalId" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function getStore(mode: IDBTransactionMode): Promise<{
  actionStore: IDBObjectStore;
  pendingStore: IDBObjectStore;
}> {
  const db = await openDB();
  const transaction = db.transaction([STORE_NAME, "pending-approvals"], mode);
  return {
    actionStore: transaction.objectStore(STORE_NAME),
    pendingStore: transaction.objectStore("pending-approvals"),
  };
}

// ─── Offline Queue ──────────────────────────────────────────────────────────────

/**
 * Add an approval action to the offline queue.
 */
export async function queueApprovalAction(
  action: "approve" | "reject" | "requestRevision",
  approvalId: string,
  decisionNote?: string,
): Promise<QueuedAction> {
  const queuedAction: QueuedAction = {
    id: crypto.randomUUID(),
    action,
    approvalId,
    decisionNote,
    queuedAt: Date.now(),
    retryCount: 0,
  };

  const { actionStore } = await getStore("readwrite");
  await new Promise<void>((resolve, reject) => {
    const req = actionStore.add(queuedAction);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });

  return queuedAction;
}

/**
 * Get all pending actions in the queue.
 */
export async function getPendingActions(): Promise<QueuedAction[]> {
  const { actionStore } = await getStore("readonly");
  return new Promise((resolve, reject) => {
    const req = actionStore.getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/**
 * Remove an action from the queue (after successful sync).
 */
export async function removePendingAction(id: string): Promise<void> {
  const { actionStore } = await getStore("readwrite");
  return new Promise((resolve, reject) => {
    const req = actionStore.delete(id);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

/**
 * Clear all pending actions.
 */
export async function clearPendingActions(): Promise<void> {
  const { actionStore } = await getStore("readwrite");
  return new Promise((resolve, reject) => {
    const req = actionStore.clear();
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

/**
 * Check if there are pending offline actions.
 */
export async function hasPendingActions(): Promise<boolean> {
  const actions = await getPendingActions();
  return actions.length > 0;
}

// ─── Pending Approvals Cache ──────────────────────────────────────────────────

/**
 * Cache an approval locally so it's available offline.
 */
export async function cachePendingApproval(approval: Approval): Promise<void> {
  const { pendingStore } = await getStore("readwrite");
  const cache: PendingApprovalCache = {
    approvalId: approval.id,
    approval,
    queuedAt: Date.now(),
  };
  await new Promise<void>((resolve, reject) => {
    const req = pendingStore.put(cache);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

/**
 * Get a cached approval by ID.
 */
export async function getCachedApproval(approvalId: string): Promise<Approval | null> {
  const { pendingStore } = await getStore("readonly");
  return new Promise((resolve, reject) => {
    const req = pendingStore.get(approvalId);
    req.onsuccess = () => {
      const cache = req.result as PendingApprovalCache | undefined;
      resolve(cache?.approval ?? null);
    };
    req.onerror = () => reject(req.error);
  });
}

/**
 * Get all cached pending approvals.
 */
export async function getCachedPendingApprovals(): Promise<Approval[]> {
  const { pendingStore } = await getStore("readonly");
  return new Promise((resolve, reject) => {
    const req = pendingStore.getAll();
    req.onsuccess = () => {
      const caches = req.result as PendingApprovalCache[];
      resolve(caches.map((c) => c.approval));
    };
    req.onerror = () => reject(req.error);
  });
}

// ─── Sync Logic ────────────────────────────────────────────────────────────────

/**
 * Sync all pending actions to the server.
 * Called when the app comes back online.
 */
export async function syncPendingActions(
  api: {
    post: (url: string, data: Record<string, unknown>) => Promise<{ ok?: boolean; error?: string }>;
  },
  onProgress?: (synced: number, total: number) => void,
): Promise<{ synced: number; failed: number; errors: string[] }> {
  const actions = await getPendingActions();
  let synced = 0;
  let failed = 0;
  const errors: string[] = [];

  for (let i = 0; i < actions.length; i++) {
    const action = actions[i];
    onProgress?.(i, actions.length);

    try {
      let url: string;
      let body: Record<string, unknown> = {};

      switch (action.action) {
        case "approve":
          url = `/approvals/${action.approvalId}/approve`;
          body = { decisionNote: action.decisionNote };
          break;
        case "reject":
          url = `/approvals/${action.approvalId}/reject`;
          body = { decisionNote: action.decisionNote };
          break;
        case "requestRevision":
          url = `/approvals/${action.approvalId}/request-revision`;
          body = { decisionNote: action.decisionNote };
          break;
      }

      const result = await api.post(url, body);

      if (result && "ok" in result && result.ok) {
        await removePendingAction(action.id);
        synced++;
      } else {
        failed++;
        errors.push(`Failed to sync ${action.action} for ${action.approvalId}`);
      }
    } catch (err) {
      failed++;
      errors.push(
        `Error syncing ${action.action} for ${action.approvalId}: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }

  return { synced, failed, errors };
}

/**
 * Check if the browser is currently online.
 */
export function isOnline(): boolean {
  return navigator.onLine;
}

/**
 * Register online/offline listeners for auto-sync.
 */
export function registerAutoSync(
  api: {
    post: (url: string, data: Record<string, unknown>) => Promise<{ ok?: boolean; error?: string }>;
  },
  onSyncComplete?: (result: { synced: number; failed: number; errors: string[] }) => void,
): () => void {
  const handleOnline = async () => {
    const result = await syncPendingActions(api);
    onSyncComplete?.(result);
  };

  window.addEventListener("online", handleOnline);

  // Return cleanup function
  return () => {
    window.removeEventListener("online", handleOnline);
  };
}

// ─── Offline Approval Actions ───────────────────────────────────────────────────

/**
 * Submit an approval action, queuing offline if disconnected.
 * Returns the result of the action or a queued confirmation.
 */
export async function submitApprovalAction(
  action: "approve" | "reject" | "requestRevision",
  approvalId: string,
  decisionNote: string | undefined,
  api: {
    post: (url: string, data: Record<string, unknown>) => Promise<unknown>;
  },
): Promise<{
  success: boolean;
  queued: boolean;
  error?: string;
}> {
  if (!isOnline()) {
    // Queue for later sync
    await queueApprovalAction(action, approvalId, decisionNote);
    return { success: true, queued: true };
  }

  try {
    let url: string;
    switch (action) {
      case "approve":
        url = `/approvals/${approvalId}/approve`;
        break;
      case "reject":
        url = `/approvals/${approvalId}/reject`;
        break;
      case "requestRevision":
        url = `/approvals/${approvalId}/request-revision`;
        break;
    }

    await api.post(url, { decisionNote });
    return { success: true, queued: false };
  } catch (err) {
    // If the request fails (network error), queue for retry
    if (err instanceof TypeError) {
      await queueApprovalAction(action, approvalId, decisionNote);
      return { success: true, queued: true };
    }
    return {
      success: false,
      queued: false,
      error: err instanceof Error ? err.message : "Unknown error",
    };
  }
}
