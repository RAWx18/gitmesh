/**
 * `useFormDialog`: generic dialog/form state hook.
 *
 * Every dialog feature (NewMilestone, NewAgent, NewIssue, …) was repeating
 * the same shape: open/close from `useDialog()`, a draft state record,
 * a reset routine, an onSubmit that fires a mutation and closes on
 * success, and a Ctrl/⌘+Enter handler.
 *
 * This hook centralizes that. Callers describe an `initial` draft, an
 * `onSubmit` that performs the mutation, and (optional) `validate`. They
 * receive a draft + setters + open/close binding.
 *
 * GitMesh's variant differs from upstream's hand-rolled per-dialog state
 * (which used inline `useState`s and ad-hoc reset functions).
 */

import { useCallback, useEffect, useState, type KeyboardEvent } from "react";

export interface UseFormDialogConfig<TDraft extends object> {
  /** is the dialog open? */
  open: boolean;
  /** close handler - called by hook on submit success or external close */
  onClose: () => void;
  /** initial draft when dialog opens */
  initial: TDraft;
  /** validation - return falsy to block submit */
  validate?: (draft: TDraft) => boolean;
  /** submit - return a promise; on resolve the dialog closes + draft resets */
  onSubmit: (draft: TDraft) => Promise<unknown>;
  /** auto-reset draft when dialog re-opens */
  resetOnOpen?: boolean;
}

export interface UseFormDialogResult<TDraft extends object> {
  draft: TDraft;
  set: <K extends keyof TDraft>(key: K, value: TDraft[K]) => void;
  patch: (partial: Partial<TDraft>) => void;
  replace: (next: TDraft) => void;
  reset: () => void;
  submit: () => Promise<void>;
  /** true while `onSubmit` is in flight */
  submitting: boolean;
  /** true when validate(draft) returns truthy */
  canSubmit: boolean;
  /** wrap to bind to dialog `onOpenChange` */
  handleOpenChange: (next: boolean) => void;
  /** keyboard handler - submits on Cmd/Ctrl+Enter */
  handleKeyDown: (e: KeyboardEvent) => void;
}

export function useFormDialog<TDraft extends object>(
  config: UseFormDialogConfig<TDraft>,
): UseFormDialogResult<TDraft> {
  const { open, onClose, initial, validate, onSubmit, resetOnOpen = true } = config;

  const [draft, setDraft] = useState<TDraft>(initial);
  const [submitting, setSubmitting] = useState(false);

  // Re-prime the draft on every open transition (so the dialog always
  // starts fresh). We deliberately don't depend on `initial` directly to
  // avoid re-priming when callers pass a fresh literal each render.
  useEffect(() => {
    if (open && resetOnOpen) setDraft(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = useCallback(<K extends keyof TDraft>(key: K, value: TDraft[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }, []);

  const patch = useCallback((partial: Partial<TDraft>) => {
    setDraft((prev) => ({ ...prev, ...partial }));
  }, []);

  const replace = useCallback((next: TDraft) => setDraft(next), []);

  const reset = useCallback(() => setDraft(initial), [initial]);

  const canSubmit = validate ? validate(draft) : true;

  const submit = useCallback(async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(draft);
      setDraft(initial);
      onClose();
    } finally {
      setSubmitting(false);
    }
  }, [canSubmit, draft, initial, onClose, onSubmit, submitting]);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) {
        setDraft(initial);
        onClose();
      }
    },
    [initial, onClose],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        void submit();
      }
    },
    [submit],
  );

  return { draft, set, patch, replace, reset, submit, submitting, canSubmit, handleOpenChange, handleKeyDown };
}
