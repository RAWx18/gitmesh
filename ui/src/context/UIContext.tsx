/**
 * Unified UI shell context.
 *
 * Cross-cutting UI concerns (toasts, theme, etc.) are available through a
 * single `useUI()` hook. Call-sites may still use `useToast()` /
 * `useTheme()`: thin wrappers that read the same store.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

// ---------------------------------------------------------------------------
// Toast types (kept identical for backward compat with existing imports)
// ---------------------------------------------------------------------------

export type ToastTone = "info" | "success" | "warn" | "error";

export interface ToastAction {
  label: string;
  href: string;
}

export interface ToastInput {
  id?: string;
  dedupeKey?: string;
  title: string;
  body?: string;
  tone?: ToastTone;
  ttlMs?: number;
  action?: ToastAction;
}

export interface ToastItem {
  id: string;
  title: string;
  body?: string;
  tone: ToastTone;
  ttlMs: number;
  action?: ToastAction;
  createdAt: number;
}

// ---------------------------------------------------------------------------
// Theme types
// ---------------------------------------------------------------------------

export type Theme = "light" | "dark";

// ---------------------------------------------------------------------------
// Combined context value
// ---------------------------------------------------------------------------

interface UIContextValue {
  // Toasts
  toasts: ToastItem[];
  pushToast: (input: ToastInput) => string | null;
  dismissToast: (id: string) => void;
  clearToasts: () => void;
  // Theme
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const UIContext = createContext<UIContextValue | null>(null);

// ---------------------------------------------------------------------------
// Tunables
// ---------------------------------------------------------------------------

const DEFAULT_TTL_BY_TONE: Record<ToastTone, number> = {
  info: 4000,
  success: 3500,
  warn: 8000,
  error: 10000,
};
const MIN_TTL_MS = 1500;
const MAX_TTL_MS = 15000;
const MAX_TOASTS = 5;
const DEDUPE_WINDOW_MS = 3500;
const DEDUPE_MAX_AGE_MS = 20000;

const THEME_STORAGE_KEY = "gitmesh-agents.theme";
const DARK_THEME_COLOR = "#18181b";
const LIGHT_THEME_COLOR = "#ffffff";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clampTtl(value: number | undefined, tone: ToastTone) {
  const fallback = DEFAULT_TTL_BY_TONE[tone];
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(MIN_TTL_MS, Math.min(MAX_TTL_MS, Math.floor(value)));
}

function generateToastId() {
  return `toast_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function resolveThemeFromDocument(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  const isDark = theme === "dark";
  const root = document.documentElement;
  root.classList.toggle("dark", isDark);
  root.style.colorScheme = isDark ? "dark" : "light";
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  if (themeColorMeta instanceof HTMLMetaElement) {
    themeColorMeta.setAttribute("content", isDark ? DARK_THEME_COLOR : LIGHT_THEME_COLOR);
  }
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function UIProvider({ children }: { children: ReactNode }) {
  // ---- toast state -------------------------------------------------------
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timersRef = useRef(new Map<string, number>());
  const dedupeRef = useRef(new Map<string, number>());

  const clearTimer = useCallback((id: string) => {
    const handle = timersRef.current.get(id);
    if (handle !== undefined) {
      window.clearTimeout(handle);
      timersRef.current.delete(id);
    }
  }, []);

  const dismissToast = useCallback(
    (id: string) => {
      clearTimer(id);
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    },
    [clearTimer],
  );

  const clearToasts = useCallback(() => {
    for (const handle of timersRef.current.values()) {
      window.clearTimeout(handle);
    }
    timersRef.current.clear();
    setToasts([]);
  }, []);

  const pushToast = useCallback(
    (input: ToastInput) => {
      const now = Date.now();
      const tone = input.tone ?? "info";
      const ttlMs = clampTtl(input.ttlMs, tone);
      const dedupeKey =
        input.dedupeKey ??
        input.id ??
        `${tone}|${input.title}|${input.body ?? ""}|${input.action?.href ?? ""}`;

      // Sweep stale dedupe entries.
      for (const [key, ts] of dedupeRef.current.entries()) {
        if (now - ts > DEDUPE_MAX_AGE_MS) dedupeRef.current.delete(key);
      }

      const lastSeen = dedupeRef.current.get(dedupeKey);
      if (lastSeen && now - lastSeen < DEDUPE_WINDOW_MS) return null;
      dedupeRef.current.set(dedupeKey, now);

      const id = input.id ?? generateToastId();
      clearTimer(id);

      setToasts((prev) => {
        const next: ToastItem = {
          id,
          title: input.title,
          body: input.body,
          tone,
          ttlMs,
          action: input.action,
          createdAt: now,
        };
        const without = prev.filter((t) => t.id !== id);
        return [next, ...without].slice(0, MAX_TOASTS);
      });

      timersRef.current.set(
        id,
        window.setTimeout(() => dismissToast(id), ttlMs),
      );
      return id;
    },
    [clearTimer, dismissToast],
  );

  useEffect(
    () => () => {
      for (const handle of timersRef.current.values()) {
        window.clearTimeout(handle);
      }
      timersRef.current.clear();
    },
    [],
  );

  // ---- theme state -------------------------------------------------------
  const [theme, setThemeState] = useState<Theme>(() => resolveThemeFromDocument());

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);
  const toggleTheme = useCallback(
    () => setThemeState((cur) => (cur === "dark" ? "light" : "dark")),
    [],
  );

  useEffect(() => {
    applyTheme(theme);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Ignore restricted-environment write failures.
    }
  }, [theme]);

  const value = useMemo<UIContextValue>(
    () => ({
      toasts,
      pushToast,
      dismissToast,
      clearToasts,
      theme,
      setTheme,
      toggleTheme,
    }),
    [toasts, pushToast, dismissToast, clearToasts, theme, setTheme, toggleTheme],
  );

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useUI(): UIContextValue {
  const ctx = useContext(UIContext);
  if (!ctx) throw new Error("useUI must be used within UIProvider");
  return ctx;
}
