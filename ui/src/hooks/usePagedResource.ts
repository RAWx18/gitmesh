/**
 * `usePagedResource`: generic data-binding hook for list views.
 *
 * GitMesh list views were each repeating the same pattern: a primary
 * `useQuery` for the list, a secondary `useQuery` for stats/aggregates,
 * a pair of `useMutation`s for inline rename + delete, and a pile of
 * imperative state for inline-edit / confirm-delete UI.
 *
 * This hook collapses that into a single descriptor. Views become
 * pure render functions over the returned bag - no boilerplate.
 *
 * (Different surface than upstream's repeated `useQuery + useMutation +
 * useState` boilerplate per page.)
 */

import { useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

export interface PagedResourceConfig<TItem, TStats = unknown> {
  /** TanStack queryKey for the list */
  listKey: QueryKey;
  /** fetch the list */
  listFn: () => Promise<TItem[]>;
  /**
   * If false, the list query is not active - useful when another
   * provider (e.g. a context) already owns the canonical query. The
   * hook still uses `listKey` for cache invalidation after mutations.
   */
  listEnabled?: boolean;
  /** optional secondary query - e.g. per-row stats */
  statsKey?: QueryKey;
  statsFn?: () => Promise<TStats>;
  /** rename mutation - invalidates list on success */
  renameFn?: (input: { id: string; name: string }) => Promise<unknown>;
  /** delete mutation - invalidates list + stats on success */
  removeFn?: (id: string) => Promise<unknown>;
  /** extra keys to invalidate after mutations (e.g. legacy aliases) */
  extraInvalidate?: QueryKey[];
}

export interface PagedResourceState<TItem, TStats = unknown> {
  items: TItem[];
  stats: TStats | undefined;
  loading: boolean;
  error: Error | null;
  // Inline edit state machine
  editingId: string | null;
  editValue: string;
  beginEdit: (id: string, currentValue: string) => void;
  changeEditValue: (value: string) => void;
  commitEdit: () => void;
  cancelEdit: () => void;
  isEditPending: boolean;
  // Inline delete confirmation
  confirmingDeleteId: string | null;
  beginDelete: (id: string) => void;
  confirmDelete: () => void;
  cancelDelete: () => void;
  isDeletePending: boolean;
}

export function usePagedResource<TItem, TStats = unknown>(
  config: PagedResourceConfig<TItem, TStats>,
): PagedResourceState<TItem, TStats> {
  const queryClient = useQueryClient();

  const list = useQuery({
    queryKey: config.listKey,
    queryFn: config.listFn,
    enabled: config.listEnabled !== false,
  });

  const stats = useQuery({
    queryKey: config.statsKey ?? ["__paged_stats_disabled__"],
    queryFn: () => (config.statsFn ? config.statsFn() : Promise.resolve(undefined)),
    enabled: Boolean(config.statsKey && config.statsFn),
  });

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: config.listKey });
    if (config.statsKey) queryClient.invalidateQueries({ queryKey: config.statsKey });
    for (const extra of config.extraInvalidate ?? []) {
      queryClient.invalidateQueries({ queryKey: extra });
    }
  }

  const renameMutation = useMutation({
    mutationFn: (input: { id: string; name: string }) =>
      config.renameFn ? config.renameFn(input) : Promise.resolve(),
    onSuccess: () => {
      invalidateAll();
      setEditingId(null);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) =>
      config.removeFn ? config.removeFn(id) : Promise.resolve(),
    onSuccess: () => {
      invalidateAll();
      setConfirmingDeleteId(null);
    },
  });

  return {
    items: list.data ?? [],
    stats: stats.data as TStats | undefined,
    loading: list.isLoading,
    error: (list.error as Error | null) ?? null,
    editingId,
    editValue,
    beginEdit: (id, currentValue) => {
      setEditingId(id);
      setEditValue(currentValue);
    },
    changeEditValue: setEditValue,
    commitEdit: () => {
      if (!editingId) return;
      const trimmed = editValue.trim();
      if (!trimmed) return;
      renameMutation.mutate({ id: editingId, name: trimmed });
    },
    cancelEdit: () => {
      setEditingId(null);
      setEditValue("");
    },
    isEditPending: renameMutation.isPending,
    confirmingDeleteId,
    beginDelete: setConfirmingDeleteId,
    confirmDelete: () => {
      if (!confirmingDeleteId) return;
      removeMutation.mutate(confirmingDeleteId);
    },
    cancelDelete: () => setConfirmingDeleteId(null),
    isDeletePending: removeMutation.isPending,
  };
}
