/**
 * Path instructions modal: typed platform registry and <PlatformTabs>.
 * The registry is the single source of truth for icon, label, and how-to
 * copy; consumers use registry helpers instead of parallel structures.
 */

import { useState, type ComponentType, type ReactNode } from "react";
import { Apple, Monitor, Terminal } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Platform registry
// ---------------------------------------------------------------------------

type PlatformId = "mac" | "windows" | "linux";

interface PlatformEntry {
  id: PlatformId;
  label: string;
  icon: ComponentType<{ className?: string }>;
  matches: (ua: string) => boolean;
  steps: string[];
  tip?: string;
}

const PLATFORM_REGISTRY: Record<PlatformId, PlatformEntry> = {
  mac: {
    id: "mac",
    label: "macOS",
    icon: Apple,
    matches: (ua) => ua.includes("mac"),
    steps: [
      "Open Finder and navigate to the folder.",
      "Right-click (or Control-click) the folder.",
      'Hold the Option (⌥) key - "Copy" changes to "Copy as Pathname".',
      'Click "Copy as Pathname", then paste here.',
    ],
    tip: "You can also open Terminal, type cd, drag the folder into the terminal window, and press Enter. Then type pwd to see the full path.",
  },
  windows: {
    id: "windows",
    label: "Windows",
    icon: Monitor,
    matches: (ua) => ua.includes("win"),
    steps: [
      "Open File Explorer and navigate to the folder.",
      "Click in the address bar at the top - the full path will appear.",
      "Copy the path, then paste here.",
    ],
    tip: 'Alternatively, hold Shift and right-click the folder, then select "Copy as path".',
  },
  linux: {
    id: "linux",
    label: "Linux",
    icon: Terminal,
    matches: () => true, // fallback
    steps: [
      "Open a terminal and navigate to the directory with cd.",
      "Run pwd to print the full path.",
      "Copy the output and paste here.",
    ],
    tip: "In most file managers, Ctrl+L reveals the full path in the address bar.",
  },
};

const PLATFORM_ORDER: PlatformId[] = ["mac", "windows", "linux"];

function detectPlatform(): PlatformId {
  if (typeof navigator === "undefined") return "linux";
  const ua = navigator.userAgent.toLowerCase();
  for (const id of PLATFORM_ORDER) {
    if (PLATFORM_REGISTRY[id].matches(ua)) return id;
  }
  return "linux";
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

interface PathInstructionsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PathInstructionsModal({ open, onOpenChange }: PathInstructionsModalProps) {
  const [platform, setPlatform] = useState<PlatformId>(detectPlatform);
  const entry = PLATFORM_REGISTRY[platform];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">How to get a full path</DialogTitle>
          <DialogDescription>
            Paste the absolute path (e.g.{" "}
            <code className="text-xs bg-muted px-1 py-0.5 rounded">/Users/you/project</code>) into the
            input field.
          </DialogDescription>
        </DialogHeader>

        <PlatformTabs current={platform} onChange={setPlatform} />

        <PlatformSteps steps={entry.steps} />

        {entry.tip && (
          <p className="text-xs text-muted-foreground border-l-2 border-border pl-3">{entry.tip}</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PlatformTabs({
  current,
  onChange,
}: {
  current: PlatformId;
  onChange: (id: PlatformId) => void;
}) {
  return (
    <div className="flex gap-1 rounded-md border border-border p-0.5">
      {PLATFORM_ORDER.map((id) => {
        const entry = PLATFORM_REGISTRY[id];
        const Icon = entry.icon;
        const active = current === id;
        return (
          <button
            key={id}
            type="button"
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1 text-xs transition-colors",
              active ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-accent/50",
            )}
            onClick={() => onChange(id)}
            aria-pressed={active}
          >
            <Icon className="h-3.5 w-3.5" />
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}

function PlatformSteps({ steps }: { steps: string[] }): ReactNode {
  return (
    <ol className="space-y-2 text-sm">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-2">
          <span className="text-muted-foreground font-mono text-xs mt-0.5 shrink-0">{i + 1}.</span>
          <span>{step}</span>
        </li>
      ))}
    </ol>
  );
}

/**
 * Small "Choose" button - opens the modal. Public API kept stable.
 */
export function ChoosePathButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={cn(
          "inline-flex items-center rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent/50 transition-colors shrink-0",
          className,
        )}
        onClick={() => setOpen(true)}
      >
        Choose
      </button>
      <PathInstructionsModal open={open} onOpenChange={setOpen} />
    </>
  );
}
