import { useState, useRef, useEffect, useCallback, type ChangeEvent } from "react";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { HelpCircle, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { AGENT_ROLE_LABELS } from "@gitmesh/core";

// ── Help text dictionary - GitMesh-specific ──────────────────────────────

export const helpText: Record<string, string> = {
  name: "Display name for this agent.",
  title: "Job title shown in the org chart.",
  role: "Organizational role. Determines position and capabilities.",
  reportsTo: "The agent this one reports to in the org hierarchy.",
  capabilities: "Describes what this agent can do. Shown in the org chart and used for task routing.",
  adapterType: "How this agent runs: local CLI (Claude/Codex/OpenCode), Gateway, spawned process, or generic HTTP webhook.",
  cwd: "Default working directory fallback for local adapters. Use an absolute path on the machine running GitMesh Agents.",
  promptTemplate: "The prompt sent to the agent on each heartbeat. Supports {{ agent.id }}, {{ agent.name }}, {{ agent.role }} variables.",
  model: "Override the default model used by the adapter.",
  thinkingEffort: "Control model reasoning depth. Supported values vary by adapter/model.",
  chrome: "Enable Claude's Chrome integration by passing --chrome.",
  dangerouslySkipPermissions: "Run Claude without permission prompts. Required for unattended operation.",
  dangerouslyBypassSandbox: "Run Codex without sandbox restrictions. Required for filesystem/network access.",
  search: "Enable Codex web search capability during runs.",
  maxTurnsPerRun: "Maximum number of agentic turns (tool calls) per heartbeat run.",
  command: "The command to execute (e.g. node, python).",
  localCommand: "Override the path to the CLI command you want the adapter to call (e.g. /usr/local/bin/claude, codex, opencode).",
  args: "Command-line arguments, comma-separated.",
  extraArgs: "Extra CLI arguments for local adapters, comma-separated.",
  envVars: "Environment variables injected into the adapter process. Use plain values or secret references.",
  webhookUrl: "The URL that receives POST requests when the agent is invoked.",
  heartbeatInterval: "Run this agent automatically on a timer. Useful for periodic tasks like checking for new work.",
  intervalSec: "Seconds between automatic heartbeat invocations.",
  timeoutSec: "Maximum seconds a run can take before being terminated. 0 means no timeout.",
  graceSec: "Seconds to wait after sending interrupt before force-killing the process.",
  wakeOnDemand: "Allow this agent to be woken by assignments, API calls, UI actions, or automated systems.",
  cooldownSec: "Minimum seconds between consecutive heartbeat runs.",
  maxConcurrentRuns: "Maximum number of heartbeat runs that can execute simultaneously for this agent.",
  budgetMonthlyCents: "Monthly spending limit in cents. 0 means no limit.",
};

// Alias for compatibility
export const help = helpText;

// GitMesh-specific adapter labels
export const adapterLabels: Record<string, string> = {
  claude_local: "Claude (local)",
  codex_local: "Codex (local)",
  opencode_local: "OpenCode (local)",
  gateway: "Gateway",
  cursor: "Cursor (local)",
  process: "Process",
  http: "HTTP",
  minimax: "MiniMax",
};

export const roleLabels = AGENT_ROLE_LABELS as Record<string, string>;

// ── Hint icon component - rewritten ────────────────────────────────────

export function HintIcon({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          aria-label={`Help: ${text.slice(0, 30)}`}
        >
          <HelpCircle className="h-3 w-3" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

// ── Field component - rewritten ─────────────────────────────────────────

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <label className="text-xs text-muted-foreground font-medium">{label}</label>
        {hint && <HintIcon text={hint} />}
      </div>
      {children}
    </div>
  );
}

// ── Toggle component - rewritten with different internal structure ───────

function ToggleSwitch({
  checked,
  onToggle,
}: {
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={cn(
        "relative inline-flex h-[22px] w-9 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        checked ? "bg-green-600" : "bg-muted"
      )}
      onClick={onToggle}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-0.5"
        )}
      />
    </button>
  );
}

export function ToggleField({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-muted-foreground">{label}</span>
        {hint && <HintIcon text={hint} />}
      </div>
      <ToggleSwitch checked={checked} onToggle={() => onChange(!checked)} />
    </div>
  );
}

// ── Toggle with number - rewritten ─────────────────────────────────────

export function ToggleWithNumber({
  label,
  hint,
  checked,
  onCheckedChange,
  number,
  onNumberChange,
  numberLabel,
  numberHint,
  numberPrefix,
  showNumber,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  number: number;
  onNumberChange: (v: number) => void;
  numberLabel: string;
  numberHint?: string;
  numberPrefix?: string;
  showNumber: boolean;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">{label}</span>
          {hint && <HintIcon text={hint} />}
        </div>
        <ToggleSwitch checked={checked} onToggle={() => onCheckedChange(!checked)} />
      </div>

      {showNumber && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground pl-1">
          {numberPrefix && <span className="font-muted">{numberPrefix}</span>}
          <input
            type="number"
            className="w-16 rounded-md border border-border bg-transparent px-2 py-1 text-xs font-mono text-center outline-none focus:border-foreground/30 transition-colors"
            value={number}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              onNumberChange(Number(e.target.value) || 0)
            }
            aria-label={numberLabel}
          />
          <span>{numberLabel}</span>
          {numberHint && <HintIcon text={numberHint} />}
        </div>
      )}
    </div>
  );
}

// ── Collapsible section - rewritten ──────────────────────────────────────

export function CollapsibleSection({
  title,
  icon,
  open,
  onToggle,
  bordered,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  bordered?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={cn(bordered && "border-t border-border")}>
      <button
        type="button"
        className="flex items-center gap-2 w-full px-4 py-2.5 text-xs font-medium text-muted-foreground hover:bg-accent/30 transition-colors"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className={cn("transition-transform", open ? "rotate-90" : "rotate-0")}>
          <ChevronRight className="h-3 w-3" />
        </span>
        {icon}
        <span>{title}</span>
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

// ── Auto-expanding textarea - rewritten ─────────────────────────────────

export function AutoExpandTextarea({
  value,
  onChange,
  onBlur,
  placeholder,
  minRows = 3,
}: {
  value: string;
  onChange: (v: string) => void;
  onBlur?: () => void;
  placeholder?: string;
  minRows?: number;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineHeight = 20;

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(minRows * lineHeight, el.scrollHeight)}px`;
  }, [minRows, lineHeight]);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  return (
    <textarea
      ref={textareaRef}
      className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-mono placeholder:text-muted-foreground/40 outline-none resize-none overflow-hidden transition-colors focus:border-foreground/30"
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
      rows={minRows}
      style={{ minHeight: minRows * lineHeight }}
    />
  );
}

// ── Draft input components - rewritten with different state management ───

function useDraftState<T>(value: T, onCommit: (v: T) => void) {
  const [draft, setDraft] = useState(value);

  // Sync with external value
  useEffect(() => {
    setDraft(value);
  }, [value]);

  // Return current draft and a setter that optionally auto-commits
  const setAndCommit = useCallback(
    (newValue: T, autoCommit: boolean) => {
      setDraft(newValue);
      if (autoCommit) {
        onCommit(newValue);
      }
    },
    [onCommit]
  );

  const commitIfChanged = useCallback(
    (currentValue: T) => {
      if (currentValue !== value) {
        onCommit(currentValue);
      }
    },
    [value, onCommit]
  );

  return { draft, setDraft: setAndCommit, commitIfChanged };
}

export function DraftInput({
  value,
  onCommit,
  immediate = false,
  className,
  ...props
}: {
  value: string;
  onCommit: (v: string) => void;
  immediate?: boolean;
  className?: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "className">) {
  const { draft, setDraft, commitIfChanged } = useDraftState(value, onCommit);

  return (
    <input
      {...props}
      className={cn(
        "w-full rounded-md border border-border bg-transparent px-3 py-1.5 text-sm outline-none transition-colors focus:border-foreground/30 placeholder:text-muted-foreground/40",
        className
      )}
      value={draft}
      onChange={(e) => setDraft(e.target.value, immediate)}
      onBlur={() => commitIfChanged(draft)}
    />
  );
}

export function DraftTextarea({
  value,
  onCommit,
  immediate = false,
  placeholder,
  minRows = 3,
}: {
  value: string;
  onCommit: (v: string) => void;
  immediate?: boolean;
  placeholder?: string;
  minRows?: number;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineHeight = 20;
  const { draft, setDraft, commitIfChanged } = useDraftState(value, onCommit);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(minRows * lineHeight, el.scrollHeight)}px`;
  }, [minRows, lineHeight]);

  useEffect(() => {
    adjustHeight();
  }, [draft, adjustHeight]);

  return (
    <textarea
      ref={textareaRef}
      className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-mono placeholder:text-muted-foreground/40 outline-none resize-none overflow-hidden transition-colors focus:border-foreground/30"
      placeholder={placeholder}
      value={draft}
      onChange={(e) => setDraft(e.target.value, immediate)}
      onBlur={() => commitIfChanged(draft)}
      rows={minRows}
      style={{ minHeight: minRows * lineHeight }}
    />
  );
}

export function DraftNumberInput({
  value,
  onCommit,
  immediate = false,
  className,
  ...props
}: {
  value: number;
  onCommit: (v: number) => void;
  immediate?: boolean;
  className?: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "className" | "type">) {
  const { draft, setDraft, commitIfChanged } = useDraftState(String(value), (s) => onCommit(Number(s) || 0));

  return (
    <input
      {...props}
      type="number"
      className={cn(
        "w-20 rounded-md border border-border bg-transparent px-2 py-1 text-xs font-mono text-center outline-none transition-colors focus:border-foreground/30",
        className
      )}
      value={draft}
      onChange={(e) => setDraft(e.target.value, immediate)}
      onBlur={() => commitIfChanged(draft)}
    />
  );
}

// ── Path chooser dialog - rewritten ────────────────────────────────────

export function ChoosePathButton() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className="inline-flex items-center rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent/50 transition-colors shrink-0"
        onClick={() => setOpen(true)}
      >
        Choose
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Specify path manually</DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              Browser security blocks apps from reading full local paths via a file picker.
              Copy the absolute path and paste it into the input.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 text-sm">
            <section className="space-y-2">
              <p className="font-medium text-foreground">macOS (Finder)</p>
              <ol className="list-decimal space-y-1.5 pl-5 text-muted-foreground">
                <li>Find the folder in Finder.</li>
                <li>Hold <kbd className="px-1.5 py-0.5 rounded bg-muted text-xs font-mono">Option</kbd> and right-click the folder.</li>
                <li>Click "Copy as Pathname".</li>
                <li>Paste into the path input.</li>
              </ol>
              <code className="block rounded bg-muted px-3 py-1.5 text-xs font-mono text-muted-foreground">
                /Users/yourname/Documents/project
              </code>
            </section>

            <section className="space-y-2">
              <p className="font-medium text-foreground">Windows (File Explorer)</p>
              <ol className="list-decimal space-y-1.5 pl-5 text-muted-foreground">
                <li>Find the folder in File Explorer.</li>
                <li>Hold <kbd className="px-1.5 py-0.5 rounded bg-muted text-xs font-mono">Shift</kbd> and right-click the folder.</li>
                <li>Click "Copy as path".</li>
                <li>Paste into the path input.</li>
              </ol>
              <code className="block rounded bg-muted px-3 py-1.5 text-xs font-mono text-muted-foreground">
                C:\Users\yourname\Documents\project
              </code>
            </section>

            <section className="space-y-2">
              <p className="font-medium text-foreground">Terminal (macOS/Linux)</p>
              <ol className="list-decimal space-y-1.5 pl-5 text-muted-foreground">
                <li>Run <code className="text-xs">cd /path/to/folder</code></li>
                <li>Run <code className="text-xs">pwd</code></li>
                <li>Copy output and paste into the path input.</li>
              </ol>
            </section>
          </div>

          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Got it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ── Inline field - rewritten ───────────────────────────────────────────

export function InlineField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-1.5 shrink-0">
        <label className="text-xs text-muted-foreground font-medium">{label}</label>
        {hint && <HintIcon text={hint} />}
      </div>
      <div className="w-28 ml-auto">{children}</div>
    </div>
  );
}
