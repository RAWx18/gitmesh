import { useState, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "@/lib/router";
import { useProject } from "@/context/ProjectContext";
import { useBreadcrumbs } from "@/context/BreadcrumbContext";
import { agentsApi } from "@/api/agents";
import { queryKeys } from "@/lib/queryKeys";
import { AGENT_ROLES } from "@gitmesh/core";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Shield, User } from "lucide-react";
import { cn, agentUrl } from "@/lib/utils";
import { roleLabels } from "@/components/agent-config-primitives";
import { AgentConfigForm, type CreateConfigValues } from "@/features/AgentConfigForm";
import { defaultCreateValues } from "@/components/agent-config-defaults";
import { getUIAdapter } from "@/adapters";
import { AgentIcon } from "@/features/AgentIconPicker";
import {
  DEFAULT_CODEX_LOCAL_BYPASS_APPROVALS_AND_SANDBOX,
  DEFAULT_CODEX_LOCAL_MODEL,
} from "@gitmesh/adapter-codex-local";
import { DEFAULT_CURSOR_LOCAL_MODEL } from "@gitmesh/adapter-cursor-local";

// Supported adapter types in GitMesh
const GITMESH_ADAPTER_TYPES: CreateConfigValues["adapterType"][] = [
  "claude_local",
  "codex_local",
  "opencode_local",
  "pi_local",
  "cursor",
  "gateway",
  "minimax",
];
const SUPPORTED_ADAPTER_SET = new Set(GITMESH_ADAPTER_TYPES);

// Build initial config for a given adapter type - rewritten logic
function buildInitialConfig(adapterType: CreateConfigValues["adapterType"]): CreateConfigValues {
  const base = { ...defaultCreateValues, adapterType };

  // Adapter-specific defaults using a map instead of if-else chain
  const adapterDefaults: Partial<Record<CreateConfigValues["adapterType"], Partial<CreateConfigValues>>> = {
    codex_local: {
      model: DEFAULT_CODEX_LOCAL_MODEL,
      dangerouslyBypassSandbox: DEFAULT_CODEX_LOCAL_BYPASS_APPROVALS_AND_SANDBOX,
    },
    cursor: {
      model: DEFAULT_CURSOR_LOCAL_MODEL,
    },
    opencode_local: {
      model: "",
    },
  };

  const overrides = adapterDefaults[adapterType] ?? {};
  return { ...base, ...overrides };
}

// Check if adapter needs model validation
function adapterRequiresModelCheck(adapterType: CreateConfigValues["adapterType"]): boolean {
  return adapterType === "opencode_local";
}

// Validate model against discovered adapters
function validateModelForAdapter(
  model: string,
  adapterType: CreateConfigValues["adapterType"],
  discoveredModels: { id: string }[]
): string | null {
  if (!adapterRequiresModelCheck(adapterType)) return null;

  if (!model.trim()) {
    return "OpenCode requires an explicit model in provider/model format.";
  }

  const isAvailable = discoveredModels.some((m) => m.id === model);
  if (!isAvailable) {
    if (discoveredModels.length === 0) {
      return "No OpenCode models discovered. Run `opencode models` and authenticate providers.";
    }
    return `Configured OpenCode model is unavailable: ${model}`;
  }

  return null;
}

// Derive effective role based on whether this is the first agent
function deriveEffectiveRole(isFirstAgent: boolean, selectedRole: string): string {
  return isFirstAgent ? "triage" : selectedRole;
}

export function EnableAgent() {
  const { selectedProjectId } = useProject();
  const { setBreadcrumbs } = useBreadcrumbs();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Form state - consolidated
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [role, setRole] = useState("general");
  const [reportsTo, setReportsTo] = useState("");
  const [configValues, setConfigValues] = useState<CreateConfigValues>(() => {
    const preset = searchParams.get("adapterType");
    if (preset && SUPPORTED_ADAPTER_SET.has(preset as CreateConfigValues["adapterType"])) {
      return buildInitialConfig(preset as CreateConfigValues["adapterType"]);
    }
    return defaultCreateValues;
  });

  // UI state
  const [roleOpen, setRoleOpen] = useState(false);
  const [reportsToOpen, setReportsToOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Query for existing agents
  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(selectedProjectId!),
    queryFn: () => agentsApi.list(selectedProjectId!),
    enabled: !!selectedProjectId,
  });

  // Query for adapter models (when relevant)
  const {
    data: adapterModels,
    error: adapterModelsError,
    isLoading: adapterModelsLoading,
    isFetching: adapterModelsFetching,
  } = useQuery({
    queryKey: selectedProjectId
      ? queryKeys.agents.adapterModels(selectedProjectId, configValues.adapterType)
      : ["agents", "none", "adapter-models", configValues.adapterType],
    queryFn: () => agentsApi.adapterModels(selectedProjectId!, configValues.adapterType),
    enabled: Boolean(selectedProjectId),
  });

  // Derived state
  const isFirstAgent = !agents || agents.length === 0;
  const effectiveRole = deriveEffectiveRole(isFirstAgent, role);
  const currentReportsTo = agents?.find((a) => a.id === reportsTo);

  // Set default name/title for first agent
  useEffect(() => {
    if (isFirstAgent) {
      if (!name) setName("Triage Bot");
      if (!title) setTitle("Triage Agent");
    }
  }, [isFirstAgent]);

  // Update config when adapter type is preset via URL
  useEffect(() => {
    const preset = searchParams.get("adapterType");
    if (!preset) return;
    if (!SUPPORTED_ADAPTER_SET.has(preset as CreateConfigValues["adapterType"])) return;

    setConfigValues((prev) => {
      if (prev.adapterType === preset) return prev;
      return buildInitialConfig(preset as CreateConfigValues["adapterType"]);
    });
  }, [searchParams]);

  // Mutation to create agent
  const createAgent = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      agentsApi.enable(selectedProjectId!, data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.agents.list(selectedProjectId!) });
      queryClient.invalidateQueries({ queryKey: queryKeys.approvals.list(selectedProjectId!) });
      navigate(agentUrl(result.agent));
    },
    onError: (error) => {
      setFormError(error instanceof Error ? error.message : "Failed to create agent");
    },
  });

  // Build adapter config using the adapter pattern
  const buildAdapterConfig = useCallback(() => {
    const adapter = getUIAdapter(configValues.adapterType);
    return adapter.buildAdapterConfig(configValues);
  }, [configValues]);

  // Submit handler with validation
  const handleSubmit = useCallback(() => {
    if (!selectedProjectId || !name.trim()) return;
    setFormError(null);

    // Validate model if required
    const modelError = validateModelForAdapter(
      configValues.model,
      configValues.adapterType,
      adapterModels ?? []
    );

    if (modelError) {
      setFormError(modelError);
      return;
    }

    // Check for loading state
    if (adapterModelsLoading || adapterModelsFetching) {
      setFormError("OpenCode models are still loading. Please wait and try again.");
      return;
    }

    // Build runtime config
    const runtimeConfig = {
      heartbeat: {
        enabled: configValues.heartbeatEnabled,
        intervalSec: configValues.intervalSec,
        wakeOnDemand: true,
        cooldownSec: 10,
        maxConcurrentRuns: 1,
      },
    };

    // Submit
    createAgent.mutate({
      name: name.trim(),
      role: effectiveRole,
      ...(title.trim() ? { title: title.trim() } : {}),
      ...(reportsTo ? { reportsTo } : {}),
      adapterType: configValues.adapterType,
      adapterConfig: buildAdapterConfig(),
      runtimeConfig,
      budgetMonthlyCents: 0,
    });
  }, [
    selectedProjectId,
    name,
    configValues,
    effectiveRole,
    title,
    reportsTo,
    buildAdapterConfig,
    adapterModels,
    adapterModelsLoading,
    adapterModelsFetching,
    createAgent,
  ]);

  // Handle config changes
  const handleConfigChange = useCallback((patch: Partial<CreateConfigValues>) => {
    setConfigValues((prev) => ({ ...prev, ...patch }));
  }, []);

  // Render role selector
  const renderRoleSelector = () => (
    <Popover open={roleOpen} onOpenChange={setRoleOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs hover:bg-accent/50 transition-colors",
            isFirstAgent && "opacity-60 cursor-not-allowed"
          )}
          disabled={isFirstAgent}
        >
          <Shield className="h-3 w-3 text-muted-foreground" />
          {roleLabels[effectiveRole] ?? effectiveRole}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-36 p-1" align="start">
        {AGENT_ROLES.map((r) => (
          <button
            key={r}
            className={cn(
              "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50",
              r === role && "bg-accent"
            )}
            onClick={() => { setRole(r); setRoleOpen(false); }}
          >
            {roleLabels[r] ?? r}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );

  // Render reports-to selector
  const renderReportsToSelector = () => (
    <Popover open={reportsToOpen} onOpenChange={setReportsToOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs hover:bg-accent/50 transition-colors",
            isFirstAgent && "opacity-60 cursor-not-allowed"
          )}
          disabled={isFirstAgent}
        >
          {currentReportsTo ? (
            <>
              <AgentIcon icon={currentReportsTo.icon} className="h-3 w-3 text-muted-foreground" />
              {`Reports to ${currentReportsTo.name}`}
            </>
          ) : (
            <>
              <User className="h-3 w-3 text-muted-foreground" />
              {isFirstAgent ? "Reports to: N/A (Lead)" : "Reports to..."}
            </>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-48 p-1" align="start">
        <button
          className={cn(
            "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50",
            !reportsTo && "bg-accent"
          )}
          onClick={() => { setReportsTo(""); setReportsToOpen(false); }}
        >
          No manager
        </button>
        {(agents ?? []).map((a) => (
          <button
            key={a.id}
            className={cn(
              "flex items-center gap-2 w-full px-2 py-1.5 text-xs rounded hover:bg-accent/50 truncate",
              a.id === reportsTo && "bg-accent"
            )}
            onClick={() => { setReportsTo(a.id); setReportsToOpen(false); }}
          >
            <AgentIcon icon={a.icon} className="shrink-0 h-3 w-3 text-muted-foreground" />
            {a.name}
            <span className="text-muted-foreground ml-auto">{roleLabels[a.role] ?? a.role}</span>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );

  // Render form footer
  const renderFooter = () => (
    <div className="border-t border-border px-4 py-3">
      {isFirstAgent && (
        <p className="text-xs text-muted-foreground mb-2">This will be the lead triage agent</p>
      )}
      {formError && (
        <p className="text-xs text-destructive mb-2">{formError}</p>
      )}
      <div className="flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => navigate("/agents")}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={!name.trim() || createAgent.isPending}
          onClick={handleSubmit}
        >
          {createAgent.isPending ? "Creating…" : "Create agent"}
        </Button>
      </div>
    </div>
  );

  // Render property chips row
  const renderPropertyChips = () => (
    <div className="flex items-center gap-1.5 px-4 py-2 border-t border-border flex-wrap">
      {renderRoleSelector()}
      {renderReportsToSelector()}
    </div>
  );

  // Render name input
  const renderNameInput = () => (
    <div className="px-4 pt-4 pb-2">
      <input
        className="w-full text-lg font-semibold bg-transparent outline-none placeholder:text-muted-foreground/50"
        placeholder="Agent name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
      />
    </div>
  );

  // Render title input
  const renderTitleInput = () => (
    <div className="px-4 pb-2">
      <input
        className="w-full bg-transparent outline-none text-sm text-muted-foreground placeholder:text-muted-foreground/40"
        placeholder="Title (e.g. Triage Agent, PR Reviewer)"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
    </div>
  );

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold">Enable Agent</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Advanced agent configuration
        </p>
      </div>

      {/* Form card */}
      <div className="border border-border">
        {renderNameInput()}
        {renderTitleInput()}
        {renderPropertyChips()}

        {/* Shared config form */}
        <AgentConfigForm
          mode="create"
          values={configValues}
          onChange={handleConfigChange}
          adapterModels={adapterModels}
        />

        {renderFooter()}
      </div>
    </div>
  );
}
