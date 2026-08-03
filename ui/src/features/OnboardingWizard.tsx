import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { AdapterEnvironmentTestResult, Project } from "@gitmesh/core";
import { useDialog } from "../context/DialogContext";
import { useProject } from "../context/ProjectContext";
import { projectsApi } from '../api/projects-api';
import { milestonesApi } from "../api/milestones";
import { agentsApi } from "../api/agents";
import { issuesApi } from "../api/issues";
import { githubApi, type GitHubRepo } from "../api/github";
import { queryKeys } from "../lib/queryKeys";
import { Dialog, DialogPortal } from "@/components/ui/dialog";
import {
  Popover,
  PopoverContent,
  PopoverTrigger
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { cn } from "../lib/utils";
import { extractModelName, extractProviderIdWithFallback } from "../lib/model-utils";
import { getUIAdapter } from "../adapters";
import { defaultCreateValues } from "../components/agent-config-defaults";
import {
  DEFAULT_CODEX_LOCAL_BYPASS_APPROVALS_AND_SANDBOX,
  DEFAULT_CODEX_LOCAL_MODEL
} from "@gitmesh/adapter-codex-local";
import { DEFAULT_CURSOR_LOCAL_MODEL } from "@gitmesh/adapter-cursor-local";
import { ChoosePathButton } from "./PathInstructionsModal";
import { HintIcon } from "../components/agent-config-primitives";
import { OpenCodeLogoIcon } from "../components/OpenCodeLogoIcon";
import {
  Building2,
  Bot,
  Code,
  ListTodo,
  Rocket,
  ArrowLeft,
  ArrowRight,
  Terminal,
  Sparkles,
  MousePointer2,
  Check,
  Loader2,
  FolderOpen,
  ChevronDown,
  X,
  Github,
  Search,
  Lock,
} from "lucide-react";

type Step = 1 | 1.5 | 2 | 3 | 4;
type AdapterType =
  | "claude_local"
  | "codex_local"
  | "opencode_local"
  | "pi_local"
  | "cursor"
  | "process"
  | "http"
  | "gateway";

const DEFAULT_TASK_DESCRIPTION = `Setup yourself as the Triage agent. The triage pack ships in this repository (no external download):

- agents/triage/AGENTS.md - main operating instructions
- agents/triage/HEARTBEAT.md - per-heartbeat checklist
- agents/triage/SOUL.md - persona and boundaries
- agents/triage/TOOLS.md - comment templates and API notes

In Enable Agent, set the agent instructions file to the absolute path of agents/triage/AGENTS.md on your machine (e.g. <repo-root>/agents/triage/AGENTS.md). Set working directory to your checkout or repo root as your adapter requires.

Reference: playbooks/triage/playbook.md for the shared triage skill; playbooks/core/playbook.md for GitMesh API flows.

Then create your first agent from Enable Agent.`;

/** Shared field styles - flat, minimal focus ring */
const onboardLabelClass = "mb-2 block text-xs font-medium text-muted-foreground";
const onboardControlClass =
  "w-full rounded-xl border border-border/50 bg-muted/20 px-4 py-3 text-[15px] leading-snug text-foreground placeholder:text-muted-foreground/50 transition-colors focus-visible:border-border focus-visible:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25";

export function OnboardingWizard() {
  const { onboardingOpen, onboardingOptions, closeOnboarding } = useDialog();
  const { selectedProjectId, selectedProject, projects, setSelectedProjectId } = useProject();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const initialStep = onboardingOptions.initialStep ?? 1;
  const existingProjectId = onboardingOptions.projectId;

  const [step, setStep] = useState<Step>(initialStep);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");

  // Step 1
  const [projectName, setProjectName] = useState("");
  const [projectMission, setProjectMission] = useState("");

  // Step 2
  const [agentName, setAgentName] = useState("Triage Bot");
  const [adapterType, setAdapterType] = useState<AdapterType>("claude_local");
  const [cwd, setCwd] = useState("");
  const [model, setModel] = useState("");
  const [command, setCommand] = useState("");
  const [args, setArgs] = useState("");
  const [url, setUrl] = useState("");
  const [adapterEnvResult, setAdapterEnvResult] =
    useState<AdapterEnvironmentTestResult | null>(null);
  const [adapterEnvError, setAdapterEnvError] = useState<string | null>(null);
  const [adapterEnvLoading, setAdapterEnvLoading] = useState(false);
  const [forceUnsetAnthropicApiKey, setForceUnsetAnthropicApiKey] =
    useState(false);
  const [unsetAnthropicLoading, setUnsetAnthropicLoading] = useState(false);

  // Step 3
  const [taskTitle, setTaskTitle] = useState("Create your Triage HEARTBEAT.md");
  const [taskDescription, setTaskDescription] = useState(
    DEFAULT_TASK_DESCRIPTION
  );

  // Step 1.5 - GitHub repo picker
  const [repos, setRepos] = useState<GitHubRepo[]>([]);
  const [reposLoading, setReposLoading] = useState(false);
  const [reposError, setReposError] = useState<string | null>(null);
  const [repoSearch, setRepoSearch] = useState("");
  const [selectedRepo, setSelectedRepo] = useState<GitHubRepo | null>(null);
  const [skipGithub, setSkipGithub] = useState(false);

  // Auto-grow textarea for task description
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const autoResizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }, []);

  // Created entity IDs - pre-populate from existing project when skipping step 1
  const [createdProjectId, setCreatedProjectId] = useState<string | null>(
    existingProjectId ?? null
  );
  const [createdProjectPrefix, setCreatedProjectPrefix] = useState<
    string | null
  >(null);
  const [createdAgentId, setCreatedAgentId] = useState<string | null>(null);
  const [createdIssueRef, setCreatedIssueRef] = useState<string | null>(null);

  // Sync step and project when onboarding opens or explicit options change.
  // Do NOT depend on `projects`: after step 1 creates a project, the list refresh
  // would re-run this effect and reset step/createdProjectId - causing duplicate projects.
  useEffect(() => {
    if (!onboardingOpen) return;
    const cId = onboardingOptions.projectId ?? null;
    setStep(onboardingOptions.initialStep ?? 1);
    setCreatedProjectId(cId);
    setCreatedProjectPrefix(null);
  }, [onboardingOpen, onboardingOptions.projectId, onboardingOptions.initialStep]);

  // When resuming at step 1.5 with a known project id, pre-fill the name once the list loads.
  useEffect(() => {
    if (!onboardingOpen) return;
    if (onboardingOptions.initialStep !== 1.5) return;
    const cId = onboardingOptions.projectId;
    if (!cId) return;
    const existing = projects.find((p) => p.id === cId);
    if (existing) setProjectName(existing.name);
  }, [
    onboardingOpen,
    onboardingOptions.initialStep,
    onboardingOptions.projectId,
    projects,
  ]);

  // Backfill issue prefix for an existing project once projects are loaded.
  useEffect(() => {
    if (!onboardingOpen || !createdProjectId || createdProjectPrefix) return;
    const project = projects.find((c) => c.id === createdProjectId);
    if (project) setCreatedProjectPrefix(project.issuePrefix);
  }, [onboardingOpen, createdProjectId, createdProjectPrefix, projects]);

  // Resize textarea when step 3 is shown or description changes
  useEffect(() => {
    if (step === 3) autoResizeTextarea();
  }, [step, taskDescription, autoResizeTextarea]);

  const loadGithubRepos = useCallback(() => {
    setReposLoading(true);
    setReposError(null);
    githubApi
      .listRepos()
      .then((data) => {
        setRepos(data ?? []);
        setReposLoading(false);
      })
      .catch((err) => {
        setReposError(
          err instanceof Error ? err.message : "Failed to load repositories",
        );
        setReposLoading(false);
      });
  }, []);

  // Load GitHub repos when entering step 1.5 and list is empty
  useEffect(() => {
    if (step !== 1.5) return;
    if (repos.length > 0 || reposLoading) return;
    loadGithubRepos();
  }, [step, repos.length, reposLoading, loadGithubRepos]);

  const {
    data: adapterModels,
    error: adapterModelsError,
    isLoading: adapterModelsLoading,
    isFetching: adapterModelsFetching,
  } = useQuery({
    queryKey:
      createdProjectId
        ? queryKeys.agents.adapterModels(createdProjectId, adapterType)
        : ["agents", "none", "adapter-models", adapterType],
    queryFn: () => agentsApi.adapterModels(createdProjectId!, adapterType),
    enabled: Boolean(createdProjectId) && onboardingOpen && step === 2
  });
  const isLocalAdapter =
    adapterType === "claude_local" || adapterType === "codex_local" || adapterType === "opencode_local" || adapterType === "cursor";
  const effectiveAdapterCommand =
    command.trim() ||
    (adapterType === "codex_local"
      ? "codex"
      : adapterType === "cursor"
        ? "agent"
        : adapterType === "opencode_local"
          ? "opencode"
          : "claude");

  useEffect(() => {
    if (step !== 2) return;
    setAdapterEnvResult(null);
    setAdapterEnvError(null);
  }, [step, adapterType, cwd, model, command, args, url]);

  const selectedModel = (adapterModels ?? []).find((m) => m.id === model);
  const hasAnthropicApiKeyOverrideCheck =
    adapterEnvResult?.checks.some(
      (check) =>
        check.code === "claude_anthropic_api_key_overrides_subscription"
    ) ?? false;
  const shouldSuggestUnsetAnthropicApiKey =
    adapterType === "claude_local" &&
    adapterEnvResult?.status === "fail" &&
    hasAnthropicApiKeyOverrideCheck;
  const filteredModels = useMemo(() => {
    const query = modelSearch.trim().toLowerCase();
    return (adapterModels ?? []).filter((entry) => {
      if (!query) return true;
      const provider = extractProviderIdWithFallback(entry.id, "");
      return (
        entry.id.toLowerCase().includes(query) ||
        entry.label.toLowerCase().includes(query) ||
        provider.toLowerCase().includes(query)
      );
    });
  }, [adapterModels, modelSearch]);
  const groupedModels = useMemo(() => {
    if (adapterType !== "opencode_local") {
      return [
        {
          provider: "models",
          entries: [...filteredModels].sort((a, b) => a.id.localeCompare(b.id)),
        },
      ];
    }
    const groups = new Map<string, Array<{ id: string; label: string }>>();
    for (const entry of filteredModels) {
      const provider = extractProviderIdWithFallback(entry.id);
      const bucket = groups.get(provider) ?? [];
      bucket.push(entry);
      groups.set(provider, bucket);
    }
    return Array.from(groups.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([provider, entries]) => ({
        provider,
        entries: [...entries].sort((a, b) => a.id.localeCompare(b.id)),
      }));
  }, [filteredModels, adapterType]);

  function reset() {
    setStep(1);
    setError(null);
    setProjectName("");
    setProjectMission("");
    setAgentName("Triage Bot");
    setAdapterType("claude_local");
    setCwd("");
    setModel("");
    setCommand("");
    setArgs("");
    setUrl("");
    setAdapterEnvResult(null);
    setAdapterEnvError(null);
    setAdapterEnvLoading(false);
    setForceUnsetAnthropicApiKey(false);
    setUnsetAnthropicLoading(false);
    setTaskTitle("Create your Triage HEARTBEAT.md");
    setTaskDescription(DEFAULT_TASK_DESCRIPTION);
    setCreatedProjectId(null);
    setCreatedProjectPrefix(null);
    setCreatedAgentId(null);
    setCreatedIssueRef(null);
    setRepos([]);
    setReposLoading(false);
    setReposError(null);
    setRepoSearch("");
    setSelectedRepo(null);
    setSkipGithub(false);
  }

  function handleClose() {
    setLoading(false);
    reset();
    closeOnboarding();
  }

  function buildAdapterConfig(): Record<string, unknown> {
    const adapter = getUIAdapter(adapterType);
    const config = adapter.buildAdapterConfig({
      ...defaultCreateValues,
      adapterType,
      cwd,
      model:
        adapterType === "codex_local"
          ? model || DEFAULT_CODEX_LOCAL_MODEL
          : adapterType === "cursor"
            ? model || DEFAULT_CURSOR_LOCAL_MODEL
            : model,
      command,
      args,
      url,
      dangerouslySkipPermissions: adapterType === "claude_local",
      dangerouslyBypassSandbox:
        adapterType === "codex_local"
          ? DEFAULT_CODEX_LOCAL_BYPASS_APPROVALS_AND_SANDBOX
          : defaultCreateValues.dangerouslyBypassSandbox
    });
    if (adapterType === "claude_local" && forceUnsetAnthropicApiKey) {
      const env =
        typeof config.env === "object" &&
          config.env !== null &&
          !Array.isArray(config.env)
          ? { ...(config.env as Record<string, unknown>) }
          : {};
      env.ANTHROPIC_API_KEY = { type: "plain", value: "" };
      config.env = env;
    }
    return config;
  }

  async function runAdapterEnvironmentTest(
    adapterConfigOverride?: Record<string, unknown>
  ): Promise<AdapterEnvironmentTestResult | null> {
    if (!createdProjectId) {
      setAdapterEnvError(
        "Create or select a project before testing adapter environment."
      );
      return null;
    }
    setAdapterEnvLoading(true);
    setAdapterEnvError(null);
    try {
      const result = await agentsApi.testEnvironment(
        createdProjectId,
        adapterType,
        {
          adapterConfig: adapterConfigOverride ?? buildAdapterConfig()
        }
      );
      setAdapterEnvResult(result);
      return result;
    } catch (err) {
      setAdapterEnvError(
        err instanceof Error ? err.message : "Adapter environment test failed"
      );
      return null;
    } finally {
      setAdapterEnvLoading(false);
    }
  }

  async function handleStep1Next() {
    setLoading(true);
    setError(null);
    try {
      let project;
      if (createdProjectId) {
        // Re-use existing project - fetch it to check forgeOwner
        project = (await projectsApi.get(createdProjectId)) ?? null;
        if (project) setCreatedProjectPrefix(project.issuePrefix);
      } else {
        project = await projectsApi.create({ name: projectName.trim() });
        setCreatedProjectId(project.id);
        setCreatedProjectPrefix(project.issuePrefix);
        setSelectedProjectId(project.id);
        queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });

        if (projectMission.trim()) {
          await milestonesApi.create(project.id, {
            title: projectMission.trim(),
            level: "project",
            status: "active"
          });
          queryClient.invalidateQueries({
            queryKey: queryKeys.milestones.list(project.id)
          });
        }
      }

      // If a forge is already linked, skip the GitHub repo picker
      if (project?.forgeOwner) {
        setStep(2);
      } else {
        setStep(1.5);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setLoading(false);
    }
  }

  async function handleStep1_5Next() {
    if (!createdProjectId) return;
    setLoading(true);
    setError(null);
    try {
      if (selectedRepo) {
        const forgeOwner = selectedRepo.owner.login;
        const forgeRepo = selectedRepo.name;
        // Use the dedicated endpoint so the OAuth token is saved as a project secret
        await githubApi.connectProject({ projectId: createdProjectId, forgeOwner, forgeRepo });
        // Optimistically update the project in the list cache so selectedProject reflects forgeOwner immediately
        queryClient.setQueryData<Project[]>(queryKeys.projects.all, (old) =>
          old?.map((p) => p.id === createdProjectId
            ? { ...p, forgeOwner, forgeRepo, forgeProvider: "github" as const }
            : p) ?? old,
        );
        queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      }
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect repo");
    } finally {
      setLoading(false);
    }
  }

  async function handleStep2Next() {
    if (!createdProjectId) return;
    setLoading(true);
    setError(null);
    try {
      if (adapterType === "opencode_local") {
        const selectedModelId = model.trim();
        if (!selectedModelId) {
          setError("OpenCode requires an explicit model in provider/model format.");
          return;
        }
        if (adapterModelsError) {
          setError(
            adapterModelsError instanceof Error
              ? adapterModelsError.message
              : "Failed to load OpenCode models.",
          );
          return;
        }
        if (adapterModelsLoading || adapterModelsFetching) {
          setError("OpenCode models are still loading. Please wait and try again.");
          return;
        }
        const discoveredModels = adapterModels ?? [];
        if (!discoveredModels.some((entry) => entry.id === selectedModelId)) {
          setError(
            discoveredModels.length === 0
              ? "No OpenCode models discovered. Run `opencode models` and authenticate providers."
              : `Configured OpenCode model is unavailable: ${selectedModelId}`,
          );
          return;
        }
      }

      if (isLocalAdapter) {
        const result = adapterEnvResult ?? (await runAdapterEnvironmentTest());
        if (!result) return;
      }

      const agent = await agentsApi.create(createdProjectId, {
        name: agentName.trim(),
        role: "triage",
        adapterType,
        adapterConfig: buildAdapterConfig(),
        runtimeConfig: {
          heartbeat: {
            enabled: true,
            intervalSec: 3600,
            wakeOnDemand: true,
            cooldownSec: 10,
            maxConcurrentRuns: 1
          }
        }
      });
      setCreatedAgentId(agent.id);
      queryClient.invalidateQueries({
        queryKey: queryKeys.agents.list(createdProjectId)
      });
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setLoading(false);
    }
  }

  async function handleUnsetAnthropicApiKey() {
    if (!createdProjectId || unsetAnthropicLoading) return;
    setUnsetAnthropicLoading(true);
    setError(null);
    setAdapterEnvError(null);
    setForceUnsetAnthropicApiKey(true);

    const configWithUnset = (() => {
      const config = buildAdapterConfig();
      const env =
        typeof config.env === "object" &&
          config.env !== null &&
          !Array.isArray(config.env)
          ? { ...(config.env as Record<string, unknown>) }
          : {};
      env.ANTHROPIC_API_KEY = { type: "plain", value: "" };
      config.env = env;
      return config;
    })();

    try {
      if (createdAgentId) {
        await agentsApi.update(
          createdAgentId,
          { adapterConfig: configWithUnset },
          createdProjectId
        );
        queryClient.invalidateQueries({
          queryKey: queryKeys.agents.list(createdProjectId)
        });
      }

      const result = await runAdapterEnvironmentTest(configWithUnset);
      if (result?.status === "fail") {
        setError(
          "Retried with ANTHROPIC_API_KEY unset in adapter config, but the environment test is still failing."
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to unset ANTHROPIC_API_KEY and retry."
      );
    } finally {
      setUnsetAnthropicLoading(false);
    }
  }

  async function handleStep3Next() {
    if (!createdProjectId || !createdAgentId) return;
    setLoading(true);
    setError(null);
    try {
      const issue = await issuesApi.create(createdProjectId, {
        title: taskTitle.trim(),
        ...(taskDescription.trim()
          ? { description: taskDescription.trim() }
          : {}),
        assigneeAgentId: createdAgentId,
        status: "todo"
      });
      setCreatedIssueRef(issue.identifier ?? issue.id);
      queryClient.invalidateQueries({
        queryKey: queryKeys.issues.list(createdProjectId)
      });
      setStep(4);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setLoading(false);
    }
  }

  async function handleLaunch() {
    if (!createdAgentId) return;
    setLoading(true);
    setError(null);
    // Capture navigation targets BEFORE reset() clears the state
    const prefix = createdProjectPrefix ?? selectedProject?.issuePrefix ?? undefined;
    const issueRef = createdIssueRef;
    const agentId = createdAgentId;
    reset();
    closeOnboarding();
    if (prefix && issueRef) {
      navigate(`/${prefix}/issues/${issueRef}`);
      return;
    }
    if (prefix) {
      navigate(`/${prefix}/dashboard`);
      return;
    }
    navigate("/");
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (step === 1 && projectName.trim()) handleStep1Next();
      else if (step === 2 && agentName.trim()) handleStep2Next();
      else if (step === 3 && taskTitle.trim()) handleStep3Next();
      else if (step === 4) handleLaunch();
    }
  }

  if (!onboardingOpen) return null;

  const stepLinearIndex =
    step === 1 ? 0 : step === 1.5 ? 1 : step === 2 ? 2 : step === 3 ? 3 : 4;
  const progressWidthPct = ((stepLinearIndex + 1) / 5) * 100;

  return (
    <Dialog
      open={onboardingOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogPortal>
        {/* Plain div instead of DialogOverlay - Radix's overlay wraps in
            RemoveScroll which blocks wheel events on our custom (non-DialogContent)
            scroll container. A plain div preserves the background without scroll-locking. */}
        <div className="fixed inset-0 z-50 bg-background" />
        <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto bg-background" onKeyDown={handleKeyDown}>
          {/* Close button */}
          <button
            type="button"
            onClick={handleClose}
            className="absolute top-5 right-5 z-10 flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Close onboarding"
          >
            <X className="h-4 w-4 stroke-[2]" />
            <span className="sr-only">Close</span>
          </button>

          {/* Single-column onboarding - centered, minimal chrome */}
          <div className="flex w-full max-w-md flex-col px-6 pt-20 pb-28 md:px-8 shrink-0">
            <div className="w-full shrink-0">
              {/* Progress - single bar, no icon cluster */}
              <div className="mb-12 space-y-3">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-medium text-foreground/80">GitMesh</span>
                  <span>{stepLinearIndex + 1} / 5</span>
                </div>
                <div
                  className="h-0.5 w-full overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  aria-valuenow={stepLinearIndex + 1}
                  aria-valuemin={1}
                  aria-valuemax={5}
                >
                  <div
                    className="h-full rounded-full bg-foreground transition-[width] duration-300 ease-out"
                    style={{ width: `${progressWidthPct}%` }}
                  />
                </div>
              </div>

              {/* Step content */}
              {step === 1 && (
                <div className="space-y-8">
                  <header className="space-y-2">
                    <h2 className="text-2xl font-semibold tracking-tight text-foreground md:text-[1.75rem]">
                      Create a workspace
                    </h2>
                    <p className="text-[15px] leading-relaxed text-muted-foreground">
                      A project bundles issues, agents, policies, budgets, and forge linkage. Pick a name that reads well
                      in the sidebar.
                    </p>
                  </header>
                  <div className="space-y-6">
                  <div>
                    <label className={onboardLabelClass}>Display name</label>
                    <input
                      className={onboardControlClass}
                      placeholder="Platform API"
                      value={projectName}
                      onChange={(e) => setProjectName(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className={onboardLabelClass}>North-star goal (optional)</label>
                    <textarea
                      className={cn(onboardControlClass, "min-h-[100px] resize-none")}
                      placeholder="Adds an active milestone for context."
                      value={projectMission}
                      onChange={(e) => setProjectMission(e.target.value)}
                    />
                  </div>
                  </div>
                </div>
              )}

              {step === 1.5 && (
                <div className="space-y-8">
                  <header className="space-y-2">
                    <h2 className="text-2xl font-semibold tracking-tight text-foreground md:text-[1.75rem]">
                      Link GitHub
                    </h2>
                    <p className="text-[15px] leading-relaxed text-muted-foreground">
                      Optional: connect a repo for forge sync and webhooks. Skip if you prefer to attach one later from
                      project settings.
                    </p>
                  </header>

                  <div className="space-y-6">
                  {reposLoading && (
                    <div className="flex items-center gap-2 py-6 text-sm text-text-secondary">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading repositories…
                    </div>
                  )}

                  {reposError && !reposLoading && (
                    <div className="space-y-3">
                      <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-foreground">
                        {reposError}
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          setRepos([]);
                          setReposError(null);
                          loadGithubRepos();
                        }}
                      >
                        Retry loading repositories
                      </Button>
                      <div className="rounded-xl border border-border/50 bg-muted/15 px-4 py-3 text-xs text-muted-foreground">
                        <p className="mb-2 text-[11px] font-medium text-foreground">Local development</p>
                        <p>
                          Set <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">GITHUB_LOCAL_DEV_PAT</code> in <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">.env</code> with a personal access token,
                          or configure <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">GITHUB_CLIENT_ID</code> /
                          <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">GITHUB_CLIENT_SECRET</code> for OAuth.
                        </p>
                      </div>
                    </div>
                  )}

                  {!reposLoading && !reposError && (
                    <>
                      {/* Search */}
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-tertiary" />
                        <input
                          className={cn(onboardControlClass, "pl-10")}
                          placeholder="Search repositories…"
                          value={repoSearch}
                          onChange={(e) => setRepoSearch(e.target.value)}
                          autoFocus
                        />
                      </div>

                      {/* Repo list */}
                      <div className="max-h-64 overflow-y-auto overflow-hidden rounded-xl border border-border/60 bg-muted/10">
                        {repos
                          .filter((r) =>
                            repoSearch
                              ? r.full_name.toLowerCase().includes(repoSearch.toLowerCase()) ||
                                (r.description ?? "").toLowerCase().includes(repoSearch.toLowerCase())
                              : true
                          )
                          .slice(0, 30)
                          .map((repo) => (
                            <button
                              key={repo.id}
                              type="button"
                              onClick={() => setSelectedRepo(repo)}
                              className={`group w-full flex items-center gap-3 border-b border-border last:border-b-0 px-3 py-2.5 text-left transition-colors ${
                                selectedRepo?.id === repo.id ? "bg-surface-2" : "hover:bg-surface-2/60"
                              }`}
                            >
                              <Github className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono text-[12px] font-medium text-foreground truncate">
                                    {repo.owner.login}<span className="text-text-tertiary">/</span>{repo.name}
                                  </span>
                                  {repo.private && (
                                    <Lock className="h-3 w-3 text-text-tertiary shrink-0" />
                                  )}
                                </div>
                                {repo.description && (
                                  <span className="text-xs text-text-tertiary truncate block">
                                    {repo.description}
                                  </span>
                                )}
                              </div>
                              {selectedRepo?.id === repo.id && (
                                <Check className="h-4 w-4 text-primary shrink-0" />
                              )}
                            </button>
                          ))}
                        {repos.filter((r) =>
                          repoSearch ? r.full_name.toLowerCase().includes(repoSearch.toLowerCase()) : true
                        ).length === 0 && (
                          <div className="py-8 text-center text-xs text-text-tertiary">
                            No repositories match.
                          </div>
                        )}
                      </div>

                      {selectedRepo && (
                        <div className="rounded-xl border border-border/50 bg-muted/15 px-4 py-3 text-xs text-muted-foreground">
                          <span className="font-medium text-foreground">Selected · </span>
                          <span className="font-mono text-foreground">{selectedRepo.full_name}</span>
                        </div>
                      )}
                    </>
                  )}
                  </div>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-8">
                  <header className="space-y-2">
                    <h2 className="text-2xl font-semibold tracking-tight text-foreground md:text-[1.75rem]">
                      Triage agent
                    </h2>
                    <p className="text-[15px] leading-relaxed text-muted-foreground">
                      Choose how the agent runs locally. Heartbeats honor budgets and policy; you can add more agents
                      after setup.
                    </p>
                  </header>

                  <div className="space-y-6">
                  <div>
                    <label className={onboardLabelClass}>Name</label>
                    <input
                      className={onboardControlClass}
                      placeholder="Triage Bot"
                      value={agentName}
                      onChange={(e) => setAgentName(e.target.value)}
                      autoFocus
                    />
                  </div>

                  {/* Adapter type radio cards */}
                  <div>
                    <label className={onboardLabelClass}>Adapter</label>
                    <div className="grid grid-cols-2 gap-2.5">
                      {[
                        {
                          value: "claude_local" as const,
                          label: "Claude Code",
                          icon: Sparkles,
                          desc: "Local Claude agent",
                          recommended: true
                        },
                        {
                          value: "codex_local" as const,
                          label: "Codex",
                          icon: Code,
                          desc: "Local Codex agent",
                          recommended: true
                        },
                        {
                          value: "opencode_local" as const,
                          label: "OpenCode",
                          icon: OpenCodeLogoIcon,
                          desc: "Local multi-provider agent"
                        },
                        {
                          value: "pi_local" as const,
                          label: "Pi",
                          icon: Terminal,
                          desc: "Local Pi agent"
                        },
                        {
                          value: "gateway" as const,
                          label: "Gateway",
                          icon: Bot,
                          desc: "Invoke agent via gateway protocol",
                          comingSoon: true,
                          disabledLabel: "Configure Gateway within the App"
                        },
                        {
                          value: "cursor" as const,
                          label: "Cursor",
                          icon: MousePointer2,
                          desc: "Local Cursor agent"
                        }
                      ].map((opt) => (
                        <button
                          key={opt.value}
                          disabled={!!opt.comingSoon}
                          className={cn(
                            "relative flex flex-col items-center gap-1.5 rounded-xl border border-border/60 p-3.5 text-xs transition-colors",
                            opt.comingSoon
                              ? "cursor-not-allowed opacity-35"
                              : adapterType === opt.value
                                ? "border-foreground/25 bg-muted/40 shadow-sm"
                                : "border-transparent bg-muted/10 hover:bg-muted/25",
                          )}
                          onClick={() => {
                            if (opt.comingSoon) return;
                            const nextType = opt.value as AdapterType;
                            setAdapterType(nextType);
                            if (nextType === "codex_local" && !model) {
                              setModel(DEFAULT_CODEX_LOCAL_MODEL);
                            } else if (nextType === "cursor" && !model) {
                              setModel(DEFAULT_CURSOR_LOCAL_MODEL);
                            }
                            if (nextType === "opencode_local") {
                              if (!model.includes("/")) {
                                setModel("");
                              }
                              return;
                            }
                            setModel("");
                          }}
                        >
                          {opt.recommended && (
                            <span className="absolute -top-1.5 right-1.5 rounded-full bg-muted px-2 py-0.5 text-[9px] font-medium text-muted-foreground leading-none ring-1 ring-border/60">
                              Pick
                            </span>
                          )}
                          <opt.icon className="h-4 w-4" />
                          <span className="font-medium">{opt.label}</span>
                          <span className="text-muted-foreground text-[10px]">
                            {opt.comingSoon
                              ? (opt as { disabledLabel?: string }).disabledLabel ??
                              "Coming soon"
                              : opt.desc}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Conditional adapter fields */}
                  {(adapterType === "claude_local" ||
                    adapterType === "codex_local" ||
                    adapterType === "opencode_local" ||
                    adapterType === "pi_local" ||
                    adapterType === "cursor") && (
                      <div className="space-y-3">
                        <div>
                          <div className="flex items-center gap-1.5 mb-1">
                            <label className="text-xs text-muted-foreground">
                              Working directory
                            </label>
                            <HintIcon text="GitMesh Agents works best if you create a new folder for your agents to keep their memories and stay organized. Create a new folder and put the path here." />
                          </div>
                          <div className="flex items-center gap-2 rounded-xl border border-border/50 px-3 py-2">
                            <FolderOpen className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                            <input
                              className="w-full bg-transparent outline-none text-sm font-mono placeholder:text-muted-foreground/50"
                              placeholder="/path/to/project"
                              value={cwd}
                              onChange={(e) => setCwd(e.target.value)}
                            />
                            <ChoosePathButton />
                          </div>
                        </div>
                        <div>
                          <label className="text-xs text-muted-foreground mb-1 block">
                            Model
                          </label>
                          <Popover
                            open={modelOpen}
                            onOpenChange={(next) => {
                              setModelOpen(next);
                              if (!next) setModelSearch("");
                            }}
                          >
                            <PopoverTrigger asChild>
                              <button className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm hover:bg-accent/50 transition-colors w-full justify-between">
                                <span
                                  className={cn(
                                    !model && "text-muted-foreground"
                                  )}
                                >
                                  {selectedModel
                                    ? selectedModel.label
                                    : model ||
                                    (adapterType === "opencode_local"
                                      ? "Select model (required)"
                                      : "Default")}
                                </span>
                                <ChevronDown className="h-3 w-3 text-muted-foreground" />
                              </button>
                            </PopoverTrigger>
                            <PopoverContent
                              className="w-[var(--radix-popover-trigger-width)] p-1"
                              align="start"
                            >
                              <input
                                className="w-full px-2 py-1.5 text-xs bg-transparent outline-none border-b border-border mb-1 placeholder:text-muted-foreground/50"
                                placeholder="Search models..."
                                value={modelSearch}
                                onChange={(e) => setModelSearch(e.target.value)}
                                autoFocus
                              />
                              {adapterType !== "opencode_local" && (
                                <button
                                  className={cn(
                                    "flex items-center gap-2 w-full px-2 py-1.5 text-sm rounded hover:bg-accent/50",
                                    !model && "bg-accent"
                                  )}
                                  onClick={() => {
                                    setModel("");
                                    setModelOpen(false);
                                  }}
                                >
                                  Default
                                </button>
                              )}
                              <div className="max-h-[240px] overflow-y-auto">
                                {groupedModels.map((group) => (
                                  <div key={group.provider} className="mb-1 last:mb-0">
                                    {adapterType === "opencode_local" && (
                                      <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                                        {group.provider} ({group.entries.length})
                                      </div>
                                    )}
                                    {group.entries.map((m) => (
                                      <button
                                        key={m.id}
                                        className={cn(
                                          "flex items-center w-full px-2 py-1.5 text-sm rounded hover:bg-accent/50",
                                          m.id === model && "bg-accent"
                                        )}
                                        onClick={() => {
                                          setModel(m.id);
                                          setModelOpen(false);
                                        }}
                                      >
                                        <span className="block w-full text-left truncate" title={m.id}>
                                          {adapterType === "opencode_local" ? extractModelName(m.id) : m.label}
                                        </span>
                                      </button>
                                    ))}
                                  </div>
                                ))}
                              </div>
                              {filteredModels.length === 0 && (
                                <p className="px-2 py-1.5 text-xs text-muted-foreground">
                                  No models discovered.
                                </p>
                              )}
                            </PopoverContent>
                          </Popover>
                        </div>
                      </div>
                    )}

                  {isLocalAdapter && (
                    <div className="space-y-2 rounded-md border border-border p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div>
                          <p className="text-xs font-medium">
                            Adapter environment check
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            Runs a live probe that asks the adapter CLI to
                            respond with hello.
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 px-2.5 text-xs"
                          disabled={adapterEnvLoading}
                          onClick={() => void runAdapterEnvironmentTest()}
                        >
                          {adapterEnvLoading ? "Testing..." : "Test now"}
                        </Button>
                      </div>

                      {adapterEnvError && (
                        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2.5 py-2 text-[11px] text-destructive">
                          {adapterEnvError}
                        </div>
                      )}

                      {adapterEnvResult && (
                        <AdapterEnvironmentResult result={adapterEnvResult} />
                      )}

                      {shouldSuggestUnsetAnthropicApiKey && (
                        <div className="rounded-md border border-amber-300/60 bg-amber-50/40 px-2.5 py-2 space-y-2">
                          <p className="text-[11px] text-amber-900/90 leading-relaxed">
                            Claude failed while <span className="font-mono">ANTHROPIC_API_KEY</span> is set.
                            You can clear it in this CEO adapter config and retry the probe.
                          </p>
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-2.5 text-xs"
                            disabled={adapterEnvLoading || unsetAnthropicLoading}
                            onClick={() => void handleUnsetAnthropicApiKey()}
                          >
                            {unsetAnthropicLoading ? "Retrying..." : "Unset ANTHROPIC_API_KEY"}
                          </Button>
                        </div>
                      )}

                      <div className="rounded-md border border-border/70 bg-muted/20 px-2.5 py-2 text-[11px] space-y-1.5">
                        <p className="font-medium">Manual debug</p>
                        <p className="text-muted-foreground font-mono break-all">
                          {adapterType === "cursor"
                            ? `${effectiveAdapterCommand} -p --mode ask --output-format json \"Respond with hello.\"`
                            : adapterType === "codex_local"
                              ? `${effectiveAdapterCommand} exec --json -`
                              : adapterType === "opencode_local"
                                ? `${effectiveAdapterCommand} run --format json "Respond with hello."`
                                : `${effectiveAdapterCommand} --print - --output-format stream-json --verbose`}
                        </p>
                        <p className="text-muted-foreground">
                          Prompt:{" "}
                          <span className="font-mono">Respond with hello.</span>
                        </p>
                        {adapterType === "cursor" || adapterType === "codex_local" || adapterType === "opencode_local" ? (
                          <p className="text-muted-foreground">
                            If auth fails, set{" "}
                            <span className="font-mono">
                              {adapterType === "cursor" ? "CURSOR_API_KEY" : "OPENAI_API_KEY"}
                            </span>{" "}
                            in
                            env or run{" "}
                            <span className="font-mono">
                              {adapterType === "cursor"
                                ? "agent login"
                                : adapterType === "codex_local"
                                  ? "codex login"
                                  : "opencode auth login"}
                            </span>.
                          </p>
                        ) : (
                          <p className="text-muted-foreground">
                            If login is required, run{" "}
                            <span className="font-mono">claude login</span> and
                            retry.
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {adapterType === "process" && (
                    <div className="space-y-3">
                      <div>
                        <label className="text-xs text-muted-foreground mb-1 block">
                          Command
                        </label>
                        <input
                          className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50"
                          placeholder="e.g. node, python"
                          value={command}
                          onChange={(e) => setCommand(e.target.value)}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground mb-1 block">
                          Args (comma-separated)
                        </label>
                        <input
                          className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50"
                          placeholder="e.g. script.js, --flag"
                          value={args}
                          onChange={(e) => setArgs(e.target.value)}
                        />
                      </div>
                    </div>
                  )}

                  {(adapterType === "http" || adapterType === "gateway") && (
                    <div>
                      <label className="text-xs text-muted-foreground mb-1 block">
                        {adapterType === "gateway" ? "Gateway URL" : "Webhook URL"}
                      </label>
                      <input
                        className="w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50"
                        placeholder={adapterType === "gateway" ? "ws://127.0.0.1:18789" : "https://..."}
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                      />
                    </div>
                  )}
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-8">
                  <header className="space-y-2">
                    <h2 className="text-2xl font-semibold tracking-tight text-foreground md:text-[1.75rem]">
                      First issue
                    </h2>
                    <p className="text-[15px] leading-relaxed text-muted-foreground">
                      Creates one assigned issue so you can run a heartbeat and see the agent surface in your board.
                    </p>
                  </header>
                  <div className="space-y-6">
                  <div>
                    <label className={onboardLabelClass}>Title</label>
                    <input
                      className={onboardControlClass}
                      placeholder="e.g. Research competitor pricing"
                      value={taskTitle}
                      onChange={(e) => setTaskTitle(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <div>
                    <label className={onboardLabelClass}>Description (optional)</label>
                    <textarea
                      ref={textareaRef}
                      className={cn(onboardControlClass, "max-h-[300px] min-h-[120px] resize-none overflow-y-auto")}
                      placeholder="Add more detail about what the agent should do…"
                      value={taskDescription}
                      onChange={(e) => setTaskDescription(e.target.value)}
                    />
                  </div>
                  </div>
                </div>
              )}

              {step === 4 && (
                <div className="space-y-8">
                  <header className="space-y-2">
                    <h2 className="text-2xl font-semibold tracking-tight text-foreground md:text-[1.75rem]">
                      You&apos;re set
                    </h2>
                    <p className="text-[15px] leading-relaxed text-muted-foreground">
                      Open your first issue from the board, or head to Agents to extend the roster.
                    </p>
                  </header>
                  <div className="overflow-hidden divide-y divide-border/60 rounded-2xl border border-border/50 bg-muted/10">
                    <SummaryRow icon={Building2} label="Project" value={selectedProject?.name ?? (projectName || "Untitled Project")} />
                    <SummaryRow icon={Bot} label={getUIAdapter(adapterType).label} value={agentName} />
                    <SummaryRow icon={ListTodo} label="Issue" value={taskTitle} />
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div className="mt-6 rounded-xl border border-destructive/25 bg-destructive/5 px-4 py-3">
                  <p className="text-sm text-destructive">{error}</p>
                </div>
              )}

              {/* Footer navigation */}
              <div className="mt-14 flex items-center justify-between gap-4 border-t border-border/40 pt-8">
                <div>
                  {step > 1 && step > (onboardingOptions.initialStep ?? 1) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (step === 1.5) {
                          setRepos([]);
                          setReposError(null);
                          setReposLoading(false);
                          setSelectedRepo(null);
                          setRepoSearch("");
                        }
                        setStep((step === 1.5 ? 1 : step - 1) as Step);
                      }}
                      disabled={loading}
                    >
                      <ArrowLeft className="h-3.5 w-3.5 mr-1" />
                      Back
                    </Button>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {step === 1 && (
                    <Button
                      size="sm"
                      className="rounded-xl px-5"
                      disabled={!projectName.trim() || loading}
                      onClick={handleStep1Next}
                    >
                      {loading ? (
                        <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                      ) : (
                        <ArrowRight className="h-3.5 w-3.5 mr-1" />
                      )}
                      {loading ? "Creating..." : "Next"}
                    </Button>
                  )}
                  {step === 1.5 && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => { setSkipGithub(true); setStep(2); }}
                        disabled={loading}
                      >
                        Skip for now
                      </Button>
                      <Button
                        size="sm"
                        className="rounded-xl px-5"
                        disabled={!selectedRepo || loading}
                        onClick={handleStep1_5Next}
                      >
                        {loading ? (
                          <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                        ) : (
                          <ArrowRight className="h-3.5 w-3.5 mr-1" />
                        )}
                        {loading ? "Connecting..." : "Connect & Next"}
                      </Button>
                    </div>
                  )}
                  {step === 2 && (
                    <Button
                      size="sm"
                      className="rounded-xl px-5"
                      disabled={
                        !agentName.trim() || loading || adapterEnvLoading
                      }
                      onClick={handleStep2Next}
                    >
                      {loading ? (
                        <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                      ) : (
                        <ArrowRight className="h-3.5 w-3.5 mr-1" />
                      )}
                      {loading ? "Creating..." : "Next"}
                    </Button>
                  )}
                  {step === 3 && (
                    <Button
                      size="sm"
                      className="rounded-xl px-5"
                      disabled={!taskTitle.trim() || loading}
                      onClick={handleStep3Next}
                    >
                      {loading ? (
                        <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                      ) : (
                        <ArrowRight className="h-3.5 w-3.5 mr-1" />
                      )}
                      {loading ? "Creating..." : "Next"}
                    </Button>
                  )}
                  {step === 4 && (
                    <Button size="sm" className="rounded-xl px-5" disabled={loading} onClick={handleLaunch}>
                      {loading ? (
                        <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                      ) : (
                        <ArrowRight className="h-3.5 w-3.5 mr-1" />
                      )}
                      {loading ? "Opening..." : "Open Issue"}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>

        </div>
      </DialogPortal>
    </Dialog>
  );
}

function AdapterEnvironmentResult({
  result
}: {
  result: AdapterEnvironmentTestResult;
}) {
  const statusLabel =
    result.status === "pass"
      ? "Passed"
      : result.status === "warn"
        ? "Warnings"
        : "Failed";
  const statusClass =
    result.status === "pass"
      ? "text-green-700 dark:text-green-300 border-green-300 dark:border-green-500/40 bg-green-50 dark:bg-green-500/10"
      : result.status === "warn"
        ? "text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-500/10"
        : "text-red-700 dark:text-red-300 border-red-300 dark:border-red-500/40 bg-red-50 dark:bg-red-500/10";

  return (
    <div className={`rounded-md border px-2.5 py-2 text-[11px] ${statusClass}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{statusLabel}</span>
        <span className="opacity-80">
          {new Date(result.testedAt).toLocaleTimeString()}
        </span>
      </div>
      <div className="mt-1.5 space-y-1">
        {result.checks.map((check, idx) => (
          <div
            key={`${check.code}-${idx}`}
            className="leading-relaxed break-words"
          >
            <span className="font-medium uppercase tracking-wide opacity-80">
              {check.level}
            </span>
            <span className="mx-1 opacity-60">·</span>
            <span>{check.message}</span>
            {check.detail && (
              <span className="block opacity-75 break-all">
                ({check.detail})
              </span>
            )}
            {check.hint && (
              <span className="block opacity-90 break-words">
                Hint: {check.hint}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function SummaryRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <Icon className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        <p className="mt-0.5 text-sm font-medium text-foreground truncate">{value}</p>
      </div>
      <Check className="h-4 w-4 shrink-0 text-success" />
    </div>
  );
}
