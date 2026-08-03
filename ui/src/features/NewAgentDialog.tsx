/**
 * New agent dialog: step machine (`"choice" | "advanced"`) plus a
 * declarative adapter catalog. Renders one step at a time from that
 * machine.
 */

import { useEffect, useState, type ComponentType } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@/lib/router";
import { useDialog } from "../context/DialogContext";
import { useProject } from "../context/ProjectContext";
import { agentsApi } from "../api/agents";
import { queryKeys } from "../lib/queryKeys";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Bot, Code, MousePointer2, Sparkles, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import { OpenCodeLogoIcon } from "../components/OpenCodeLogoIcon";

type AdvancedAdapterType =
  | "claude_local"
  | "codex_local"
  | "opencode_local"
  | "pi_local"
  | "cursor"
  | "gateway";

interface AdapterCard {
  value: AdvancedAdapterType;
  label: string;
  desc: string;
  icon: ComponentType<{ className?: string }>;
  recommended?: boolean;
}

const ADAPTER_CATALOG: AdapterCard[] = [
  { value: "claude_local", label: "Claude Code", icon: Sparkles, desc: "Local Claude agent", recommended: true },
  { value: "codex_local", label: "Codex", icon: Code, desc: "Local Codex agent", recommended: true },
  { value: "opencode_local", label: "OpenCode", icon: OpenCodeLogoIcon, desc: "Local multi-provider agent" },
  { value: "pi_local", label: "Pi", icon: Terminal, desc: "Local Pi agent" },
  { value: "cursor", label: "Cursor", icon: MousePointer2, desc: "Local Cursor agent" },
  { value: "gateway", label: "Gateway", icon: Bot, desc: "Invoke agent via gateway protocol" },
];

type Step = "choice" | "advanced";

export function NewAgentDialog() {
  const { newAgentOpen, closeNewAgent, openNewIssue } = useDialog();
  const { selectedProjectId } = useProject();
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("choice");

  // Reset step machine on every open transition.
  useEffect(() => {
    if (newAgentOpen) setStep("choice");
  }, [newAgentOpen]);

  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId && newAgentOpen,
  });

  const leadAgent = (agents ?? []).find((a) => (a.role as string) === "triage");

  function close() {
    setStep("choice");
    closeNewAgent();
  }

  function handleAskLead() {
    close();
    openNewIssue({
      assigneeAgentId: leadAgent?.id,
      title: "Create a new agent",
      description: "(type in what kind of agent you want here)",
    });
  }

  function handleAdvancedAdapterPick(adapterType: AdvancedAdapterType) {
    close();
    navigate(`/agents/enable?adapterType=${encodeURIComponent(adapterType)}`);
  }

  return (
    <Dialog open={newAgentOpen} onOpenChange={(open) => (!open ? close() : null)}>
      <DialogContent showCloseButton={false} className="sm:max-w-md p-0 gap-0 overflow-hidden">
        <DialogHeader onClose={close} />
        <div className="p-6 space-y-6">
          {step === "choice" ? (
            <ChoiceStep onAskLead={handleAskLead} onAdvanced={() => setStep("advanced")} />
          ) : (
            <AdvancedStep onBack={() => setStep("choice")} onPick={handleAdvancedAdapterPick} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

function DialogHeader({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
      <span className="text-sm text-muted-foreground">Add a new agent</span>
      <Button
        variant="ghost"
        size="icon-xs"
        className="text-muted-foreground"
        onClick={onClose}
        aria-label="Close"
      >
        <span className="text-lg leading-none">&times;</span>
      </Button>
    </div>
  );
}

function ChoiceStep({
  onAskLead,
  onAdvanced,
}: {
  onAskLead: () => void;
  onAdvanced: () => void;
}) {
  return (
    <>
      <div className="text-center space-y-3">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent">
          <Sparkles className="h-6 w-6 text-foreground" />
        </div>
        <p className="text-sm text-muted-foreground">
          We recommend letting your lead triage agent handle agent setup - they know the project structure
          and can configure reporting, permissions, and adapters.
        </p>
      </div>

      <Button className="w-full" size="lg" onClick={onAskLead}>
        <Bot className="h-4 w-4 mr-2" />
        Ask the lead agent to create a new agent
      </Button>

      <div className="text-center">
        <button
          className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
          onClick={onAdvanced}
        >
          I want advanced configuration myself
        </button>
      </div>
    </>
  );
}

function AdvancedStep({
  onBack,
  onPick,
}: {
  onBack: () => void;
  onPick: (adapter: AdvancedAdapterType) => void;
}) {
  return (
    <>
      <div className="space-y-2">
        <button
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={onBack}
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <p className="text-sm text-muted-foreground">Choose your adapter type for advanced setup.</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {ADAPTER_CATALOG.map((opt) => (
          <AdapterCardButton key={opt.value} card={opt} onPick={() => onPick(opt.value)} />
        ))}
      </div>
    </>
  );
}

function AdapterCardButton({ card, onPick }: { card: AdapterCard; onPick: () => void }) {
  const Icon = card.icon;
  return (
    <button
      className={cn(
        "flex flex-col items-center gap-1.5 rounded-md border border-border p-3 text-xs transition-colors hover:bg-accent/50 relative",
      )}
      onClick={onPick}
    >
      {card.recommended && (
        <span className="absolute -top-1.5 right-1.5 bg-green-500 text-white text-[9px] font-semibold px-1.5 py-0.5 rounded-full leading-none">
          Recommended
        </span>
      )}
      <Icon className="h-4 w-4" />
      <span className="font-medium">{card.label}</span>
      <span className="text-muted-foreground text-[10px]">{card.desc}</span>
    </button>
  );
}
