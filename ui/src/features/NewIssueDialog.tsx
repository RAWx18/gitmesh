/*
 * NewIssueDialog - Top-docked CLI command bar.
 *
 * This is NOT a centered modal. It is a thin mono command bar
 * that slides down from the top of the viewport, parsing inline flag tokens
 * (`--priority`, `--for`, `--in`, `--label`) out of the title as the user
 * types. Tab expands a draft sheet for description and remaining metadata.
 * No backdrop overlay, no card shadow, no labelled form fields.
 */
import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDialog } from "../context/DialogContext";
import { useProject } from "../context/ProjectContext";
import { issuesApi } from "../api/issues";
import { subprojectsApi } from "../api/subprojects";
import { agentsApi } from "../api/agents";
import { authApi } from "../api/auth";
import { assetsApi } from "../api/assets";
import { queryKeys } from "../lib/queryKeys";
import { useSubprojectOrder } from "../hooks/useSubprojectOrder";
import { trackRecentAssignee } from "../lib/recent-assignees";
import { cn } from "../lib/utils";
import { MarkdownEditor, type MarkdownEditorRef, type MentionOption } from "../components/MarkdownEditor";

const DRAFT_KEY = "gitmesh-agents:issue-draft";
const DEBOUNCE_MS = 800;

interface IssueDraft {
  title: string;
  description: string;
  status: string;
  priority: string;
  assigneeId: string;
  projectId: string;
  labels: string[];
}

const PRIORITY_VALUES = ["critical", "high", "medium", "low"] as const;
type PriorityValue = (typeof PRIORITY_VALUES)[number];

const STATUS_VALUES = ["backlog", "todo", "in_progress", "in_review", "done"] as const;

function loadDraft(): IssueDraft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<IssueDraft>;
    return {
      title: parsed.title ?? "",
      description: parsed.description ?? "",
      status: parsed.status ?? "todo",
      priority: parsed.priority ?? "",
      assigneeId: parsed.assigneeId ?? "",
      projectId: parsed.projectId ?? "",
      labels: Array.isArray(parsed.labels) ? parsed.labels : [],
    };
  } catch {
    return null;
  }
}

function saveDraft(draft: IssueDraft) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  } catch {
    /* ignore quota */
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore */
  }
}

// ── Token parser ───────────────────────────────────────────────────────────

interface ParsedToken {
  start: number;
  end: number;
  flag: "priority" | "for" | "in" | "label";
  raw: string;
  value: string;
}

interface ParsedCommand {
  title: string;
  tokens: ParsedToken[];
  priority: string;
  forName: string;
  inName: string;
  labels: string[];
}

const FLAG_RE = /--(priority|for|in|label)\s+(@?[^\s][^\s]*)/g;

function parseCommand(input: string): ParsedCommand {
  const tokens: ParsedToken[] = [];
  let priority = "";
  let forName = "";
  let inName = "";
  const labels: string[] = [];

  let m: RegExpExecArray | null;
  FLAG_RE.lastIndex = 0;
  while ((m = FLAG_RE.exec(input)) !== null) {
    const flag = m[1] as ParsedToken["flag"];
    const value = (m[2] ?? "").replace(/^@/, "");
    tokens.push({
      start: m.index,
      end: m.index + m[0].length,
      flag,
      raw: m[0],
      value,
    });
    if (flag === "priority") priority = value;
    else if (flag === "for") forName = value;
    else if (flag === "in") inName = value;
    else if (flag === "label") labels.push(value);
  }

  // Title = input with all token spans removed, whitespace normalised.
  let title = input;
  for (let i = tokens.length - 1; i >= 0; i--) {
    const tok = tokens[i]!;
    title = title.slice(0, tok.start) + title.slice(tok.end);
  }
  title = title.replace(/\s+/g, " ").trim();

  return { title, tokens, priority, forName, inName, labels };
}

// Render the input value with token-spans highlighted, mirroring caret layout.
function renderTokenizedOverlay(input: string, tokens: ParsedToken[]) {
  if (tokens.length === 0) return null;
  const parts: Array<{ text: string; chip: boolean }> = [];
  let cursor = 0;
  for (const tok of tokens) {
    if (tok.start > cursor) {
      parts.push({ text: input.slice(cursor, tok.start), chip: false });
    }
    parts.push({ text: input.slice(tok.start, tok.end), chip: true });
    cursor = tok.end;
  }
  if (cursor < input.length) {
    parts.push({ text: input.slice(cursor), chip: false });
  }
  return parts;
}

// Reused inline styles - keep mono everywhere, avoid Tailwind for var() refs.
const FONT_MONO = { fontFamily: "var(--font-mono)" } as const;
const TINY_LABEL = { color: "var(--text-tertiary)", ...FONT_MONO } as const;
const DASH_INPUT = {
  ...FONT_MONO,
  color: "var(--foreground)",
  borderBottom: "1px dashed var(--border)",
} as const;

// ── Component ─────────────────────────────────────────────────────────────

export function NewIssueDialog() {
  const { newIssueOpen, newIssueDefaults, closeNewIssue } = useDialog();
  const { projects, selectedProjectId, selectedProject } = useProject();
  const queryClient = useQueryClient();

  // Single-line command source of truth.
  const [command, setCommand] = useState("");
  const [description, setDescription] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState<string>("todo");
  // Manual overrides set from the draft sheet selectors. Empty = inferred.
  const [overridePriority, setOverridePriority] = useState<string>("");
  const [overrideAssigneeId, setOverrideAssigneeId] = useState<string>("");
  const [overrideSubprojectId, setOverrideSubprojectId] = useState<string>("");
  const [manualLabels, setManualLabels] = useState<string[]>([]);
  const [labelInput, setLabelInput] = useState("");

  const draftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const descriptionEditorRef = useRef<MarkdownEditorRef>(null);
  const attachInputRef = useRef<HTMLInputElement | null>(null);

  const effectiveProjectId = selectedProjectId;
  const dialogProject = selectedProject ?? projects.find((p) => p.id === effectiveProjectId);

  // ── Data ────────────────────────────────────────────────────────────────
  const { data: agents } = useQuery({
    queryKey: queryKeys.agents.list(effectiveProjectId!),
    queryFn: () => agentsApi.list(effectiveProjectId!),
    enabled: !!effectiveProjectId && newIssueOpen,
  });

  const { data: subprojects } = useQuery({
    queryKey: queryKeys.subprojects.list(effectiveProjectId!),
    queryFn: () => subprojectsApi.list(effectiveProjectId!),
    enabled: !!effectiveProjectId && newIssueOpen,
  });

  const { data: session } = useQuery({
    queryKey: queryKeys.auth.session,
    queryFn: () => authApi.getSession(),
  });
  const currentUserId = session?.user?.id ?? session?.session?.userId ?? null;

  const { orderedProjects: orderedSubprojects } = useSubprojectOrder({
    projects: subprojects ?? [],
    projectId: effectiveProjectId,
    userId: currentUserId,
  });

  const mentionOptions = useMemo<MentionOption[]>(() => {
    const options: MentionOption[] = [];
    const activeAgents = [...(agents ?? [])]
      .filter((agent) => agent.status !== "terminated")
      .sort((a, b) => a.name.localeCompare(b.name));
    for (const agent of activeAgents) {
      options.push({ id: `agent:${agent.id}`, name: agent.name, kind: "agent" });
    }
    for (const sp of orderedSubprojects) {
      options.push({
        id: `project:${sp.id}`,
        name: sp.name,
        kind: "project",
        projectId: sp.id,
        projectColor: sp.color,
      });
    }
    return options;
  }, [agents, orderedSubprojects]);

  // ── Parse current command ──────────────────────────────────────────────
  const parsed = useMemo(() => parseCommand(command), [command]);

  const inferredPriority = useMemo<string>(() => {
    if (overridePriority) return overridePriority;
    const p = parsed.priority.toLowerCase();
    return (PRIORITY_VALUES as readonly string[]).includes(p) ? p : "";
  }, [parsed.priority, overridePriority]);

  const inferredAssigneeId = useMemo<string>(() => {
    if (overrideAssigneeId) return overrideAssigneeId;
    if (!parsed.forName || !agents) return "";
    const needle = parsed.forName.toLowerCase();
    const exact = agents.find((a) => a.name.toLowerCase() === needle && a.status !== "terminated");
    if (exact) return exact.id;
    const partial = agents.find(
      (a) => a.status !== "terminated" && a.name.toLowerCase().includes(needle),
    );
    return partial?.id ?? "";
  }, [parsed.forName, agents, overrideAssigneeId]);

  const inferredSubprojectId = useMemo<string>(() => {
    if (overrideSubprojectId) return overrideSubprojectId;
    if (!parsed.inName) return "";
    const needle = parsed.inName.toLowerCase();
    const exact = orderedSubprojects.find((sp) => sp.name.toLowerCase() === needle);
    if (exact) return exact.id;
    const partial = orderedSubprojects.find((sp) => sp.name.toLowerCase().includes(needle));
    return partial?.id ?? "";
  }, [parsed.inName, orderedSubprojects, overrideSubprojectId]);

  const effectiveLabels = useMemo<string[]>(() => {
    const set = new Set<string>([...parsed.labels, ...manualLabels]);
    return Array.from(set);
  }, [parsed.labels, manualLabels]);

  // ── Mutations ───────────────────────────────────────────────────────────
  const createIssue = useMutation({
    mutationFn: ({ projectId, ...data }: { projectId: string } & Record<string, unknown>) =>
      issuesApi.create(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.list(effectiveProjectId!) });
      if (draftTimer.current) clearTimeout(draftTimer.current);
      clearDraft();
      reset();
      closeNewIssue();
    },
  });

  const uploadDescriptionImage = useMutation({
    mutationFn: async (file: File) => {
      if (!effectiveProjectId) throw new Error("No project selected");
      return assetsApi.uploadImage(effectiveProjectId, file, "issues/drafts");
    },
  });

  // ── Draft persistence ──────────────────────────────────────────────────
  const scheduleSave = useCallback((draft: IssueDraft) => {
    if (draftTimer.current) clearTimeout(draftTimer.current);
    draftTimer.current = setTimeout(() => {
      if (draft.title.trim()) saveDraft(draft);
    }, DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    if (!newIssueOpen) return;
    scheduleSave({
      title: command,
      description,
      status,
      priority: inferredPriority,
      assigneeId: inferredAssigneeId,
      projectId: inferredSubprojectId,
      labels: effectiveLabels,
    });
  }, [
    command,
    description,
    status,
    inferredPriority,
    inferredAssigneeId,
    inferredSubprojectId,
    effectiveLabels,
    newIssueOpen,
    scheduleSave,
  ]);

  // ── Open/close lifecycle ──────────────────────────────────────────────
  useEffect(() => {
    if (!newIssueOpen) {
      setExpanded(false);
      return;
    }

    const draft = loadDraft();
    if (newIssueDefaults.title) {
      // Build a fresh command line from defaults.
      const tokens: string[] = [];
      if (newIssueDefaults.priority) tokens.push(`--priority ${newIssueDefaults.priority}`);
      const baseTitle = newIssueDefaults.title;
      setCommand([baseTitle, ...tokens].join(" ").trim());
      setDescription(newIssueDefaults.description ?? "");
      setStatus(newIssueDefaults.status ?? "todo");
      setOverridePriority(newIssueDefaults.priority ?? "");
      setOverrideAssigneeId(newIssueDefaults.assigneeAgentId ?? "");
      setOverrideSubprojectId(newIssueDefaults.projectId ?? "");
      setManualLabels([]);
    } else if (draft && draft.title.trim()) {
      setCommand(draft.title);
      setDescription(draft.description);
      setStatus(draft.status || "todo");
      setOverridePriority(draft.priority);
      setOverrideAssigneeId(newIssueDefaults.assigneeAgentId ?? draft.assigneeId);
      setOverrideSubprojectId(newIssueDefaults.projectId ?? draft.projectId);
      setManualLabels(draft.labels ?? []);
    } else {
      setCommand("");
      setDescription("");
      setStatus(newIssueDefaults.status ?? "todo");
      setOverridePriority(newIssueDefaults.priority ?? "");
      setOverrideAssigneeId(newIssueDefaults.assigneeAgentId ?? "");
      setOverrideSubprojectId(newIssueDefaults.projectId ?? "");
      setManualLabels([]);
    }

    // Focus the bar on the next frame (after slide-in begins).
    const handle = requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
    return () => cancelAnimationFrame(handle);
  }, [newIssueOpen, newIssueDefaults]);

  useEffect(
    () => () => {
      if (draftTimer.current) clearTimeout(draftTimer.current);
    },
    [],
  );

  // Sync overlay scroll with input scroll for token highlighting.
  function handleInputScroll() {
    if (overlayRef.current && inputRef.current) {
      overlayRef.current.scrollLeft = inputRef.current.scrollLeft;
    }
  }

  function reset() {
    setCommand("");
    setDescription("");
    setStatus("todo");
    setOverridePriority("");
    setOverrideAssigneeId("");
    setOverrideSubprojectId("");
    setManualLabels([]);
    setLabelInput("");
    setExpanded(false);
  }

  function discardAndClose() {
    clearDraft();
    reset();
    closeNewIssue();
  }

  function handleSubmit() {
    if (!effectiveProjectId) return;
    const titleText = parsed.title.trim();
    if (!titleText) return;
    const priority = inferredPriority || "medium";
    const body: Record<string, unknown> = {
      title: titleText,
      description: description.trim() || undefined,
      status,
      priority,
    };
    if (inferredAssigneeId) {
      body.assigneeAgentId = inferredAssigneeId;
      trackRecentAssignee(inferredAssigneeId);
    }
    if (inferredSubprojectId) {
      body.subprojectId = inferredSubprojectId;
    }
    // Labels are kept on the draft for now - server expects UUIDs (labelIds),
    // not free-text labels, so we surface them visually but do not submit them.
    createIssue.mutate({
      projectId: effectiveProjectId,
      ...body,
    });
  }

  // ── Keyboard handling ──────────────────────────────────────────────────
  function handleBarKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      closeNewIssue();
      return;
    }
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
      return;
    }
    if (e.key === "Enter" && !expanded) {
      // Plain Enter on the bar: submit if title present, else expand.
      if (parsed.title.trim()) {
        e.preventDefault();
        handleSubmit();
      }
      return;
    }
    if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault();
      setExpanded(true);
      // Focus the description editor on the next frame.
      requestAnimationFrame(() => descriptionEditorRef.current?.focus());
    }
  }

  function handleSheetKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      closeNewIssue();
      return;
    }
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  }

  async function handleAttachImage(evt: ChangeEvent<HTMLInputElement>) {
    const file = evt.target.files?.[0];
    if (!file) return;
    try {
      const asset = await uploadDescriptionImage.mutateAsync(file);
      const name = file.name || "image";
      setDescription((prev) => {
        const suffix = `![${name}](${asset.contentPath})`;
        return prev ? `${prev}\n\n${suffix}` : suffix;
      });
    } finally {
      if (attachInputRef.current) attachInputRef.current.value = "";
    }
  }

  async function handleDescriptionDrop(file: File) {
    const asset = await uploadDescriptionImage.mutateAsync(file);
    return asset.contentPath;
  }

  function addManualLabel() {
    const t = labelInput.trim();
    if (!t) return;
    if (effectiveLabels.includes(t)) {
      setLabelInput("");
      return;
    }
    setManualLabels((prev) => [...prev, t]);
    setLabelInput("");
  }

  function removeLabel(label: string) {
    if (parsed.labels.includes(label)) {
      // Strip the inline --label token from the command.
      const next = command.replace(new RegExp(`--label\\s+${escapeRegExp(label)}\\b`, "g"), "").replace(/\s+/g, " ").trim();
      setCommand(next);
    }
    setManualLabels((prev) => prev.filter((l) => l !== label));
  }

  // ── Derived ────────────────────────────────────────────────────────────
  const canSubmit = parsed.title.trim().length > 0 && !!effectiveProjectId && !createIssue.isPending;
  const projectShort = (dialogProject?.name ?? "-").slice(0, 3).toUpperCase();
  const overlayParts = renderTokenizedOverlay(command, parsed.tokens);

  // Resolve display strings for the chip selectors.
  const inferredAssigneeName = useMemo(() => {
    if (!inferredAssigneeId) return "";
    return agents?.find((a) => a.id === inferredAssigneeId)?.name ?? "";
  }, [inferredAssigneeId, agents]);

  const inferredSubprojectName = useMemo(() => {
    if (!inferredSubprojectId) return "";
    return orderedSubprojects.find((sp) => sp.id === inferredSubprojectId)?.name ?? "";
  }, [inferredSubprojectId, orderedSubprojects]);

  if (!newIssueOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 pointer-events-none"
      aria-modal="true"
      role="dialog"
      onKeyDown={handleSheetKeyDown}
    >
      {/* Subtle dim - far below modal-overlay strength. */}
      <div
        className="absolute inset-0 pointer-events-auto"
        style={{ background: "rgba(0,0,0,0.12)" }}
        onClick={() => closeNewIssue()}
      />

      {/* Top-docked CLI bar + draft sheet. */}
      <div
        className="relative pointer-events-auto mx-auto w-full max-w-[720px] px-3 pt-2"
        style={{ animation: "gm-newissue-slide 160ms ease-out" }}
      >
        <style>{`
          @keyframes gm-newissue-slide {
            from { transform: translateY(-12px); opacity: 0; }
            to   { transform: translateY(0);     opacity: 1; }
          }
        `}</style>

        {/* Command bar row */}
        <div
          className="relative flex items-center gap-2 h-[52px] px-3"
          style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border-strong)", ...FONT_MONO }}
        >
          <span className="shrink-0 select-none text-[11px] tracking-widest uppercase" style={TINY_LABEL} aria-hidden>
            [{projectShort}]
          </span>
          <span className="shrink-0 select-none" style={{ color: "var(--verdict-attested)" }} aria-hidden>&gt;</span>
          <div className="relative flex-1 min-w-0 h-full">
            <div
              ref={overlayRef}
              className="absolute inset-0 flex items-center overflow-hidden whitespace-pre pointer-events-none text-[13px]"
              style={{ ...FONT_MONO, color: "transparent" }}
              aria-hidden
            >
              {overlayParts ? (
                <span>
                  {overlayParts.map((part, i) =>
                    part.chip ? (
                      <span key={i} style={{ color: "var(--verdict-attested)", background: "color-mix(in oklab, var(--verdict-attested) 12%, transparent)", padding: "0 2px", borderRadius: 2 }}>
                        {part.text}
                      </span>
                    ) : (
                      <span key={i}>{part.text}</span>
                    ),
                  )}
                </span>
              ) : null}
            </div>
            <input
              ref={inputRef}
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              onScroll={handleInputScroll}
              onKeyDown={handleBarKeyDown}
              spellCheck={false}
              autoCapitalize="off"
              autoComplete="off"
              autoCorrect="off"
              placeholder="new issue: type a title, then `Tab` for details, `⌘↩` to create"
              className="absolute inset-0 w-full bg-transparent outline-none border-0 text-[13px] caret-current"
              style={{ ...FONT_MONO, color: "var(--foreground)" }}
            />
          </div>
          <span className="shrink-0 select-none text-[10px] uppercase tracking-widest" style={TINY_LABEL}>
            {expanded ? "tab=fields" : "tab=expand"}
          </span>
        </div>

        {/* Inline parsed-flag summary (always visible when tokens or overrides exist). */}
        <ParsedSummary
          priority={inferredPriority}
          assigneeName={inferredAssigneeName || (parsed.forName && !inferredAssigneeId ? `?${parsed.forName}` : "")}
          subprojectName={inferredSubprojectName || (parsed.inName && !inferredSubprojectId ? `?${parsed.inName}` : "")}
          labels={effectiveLabels}
          createPending={createIssue.isPending}
          createError={createIssue.error}
        />

        {/* Draft sheet */}
        {expanded && (
          <div style={{ background: "var(--surface-2)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border-strong)", ...FONT_MONO }}>
            <div className="px-3 pt-3 pb-2 max-h-[40vh] overflow-y-auto" style={{ borderBottom: "1px solid var(--border)" }}>
              <div className="text-[10px] uppercase tracking-widest mb-1" style={TINY_LABEL}>description</div>
              <MarkdownEditor
                ref={descriptionEditorRef}
                value={description}
                onChange={setDescription}
                placeholder="// describe what needs to happen…"
                bordered={false}
                mentions={mentionOptions}
                contentClassName="text-sm min-h-[120px]"
                imageUploadHandler={handleDescriptionDrop}
              />
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2 text-[12px]">
              <ChipSelect label="status" value={status} options={STATUS_VALUES.map((v) => ({ value: v, label: v.replace("_", " ") }))} onChange={setStatus} />
              <ChipSelect label="priority" value={inferredPriority} options={[{ value: "", label: "-" }, ...PRIORITY_VALUES.map((v) => ({ value: v, label: v }))]} onChange={setOverridePriority} />
              <ChipSelect label="for" value={inferredAssigneeId} options={[{ value: "", label: "-" }, ...((agents ?? []).filter((a) => a.status !== "terminated").map((a) => ({ value: a.id, label: a.name })))]} onChange={setOverrideAssigneeId} />
              <ChipSelect label="in" value={inferredSubprojectId} options={[{ value: "", label: "-" }, ...orderedSubprojects.map((sp) => ({ value: sp.id, label: sp.name }))]} onChange={setOverrideSubprojectId} />

              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-[10px] uppercase tracking-widest" style={TINY_LABEL}>labels</span>
                {effectiveLabels.map((l) => (
                  <span key={l} className="verdict-chip" data-verdict="attested" style={{ cursor: "pointer" }} onClick={() => removeLabel(l)} title="click to remove">
                    {l} ×
                  </span>
                ))}
                <input
                  value={labelInput}
                  onChange={(e) => setLabelInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addManualLabel(); } }}
                  placeholder="+label"
                  spellCheck={false}
                  className="bg-transparent outline-none border-0 w-[80px] text-[12px]"
                  style={DASH_INPUT}
                />
              </div>

              <div className="ml-auto flex items-center gap-2">
                <input ref={attachInputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={handleAttachImage} />
                <button
                  type="button"
                  onClick={() => attachInputRef.current?.click()}
                  disabled={uploadDescriptionImage.isPending}
                  className="text-[11px] uppercase tracking-widest hover:opacity-100 disabled:opacity-50"
                  style={TINY_LABEL}
                >
                  {uploadDescriptionImage.isPending ? "uploading…" : "+attach"}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between px-3 py-2" style={{ borderTop: "1px solid var(--border)", ...FONT_MONO }}>
              <button type="button" onClick={discardAndClose} className="text-[11px] uppercase tracking-widest hover:opacity-100" style={TINY_LABEL}>
                [discard]
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSubmit}
                className={cn("text-[11px] uppercase tracking-widest disabled:opacity-40")}
                style={{ color: canSubmit ? "var(--verdict-attested)" : "var(--text-tertiary)", ...FONT_MONO }}
              >
                [{createIssue.isPending ? "creating…" : "⌘↩ create"}]
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Subcomponents ──────────────────────────────────────────────────────────

function ParsedSummary(props: { priority: string; assigneeName: string; subprojectName: string; labels: string[]; createPending: boolean; createError: unknown; }) {
  const { priority, assigneeName, subprojectName, labels, createPending, createError } = props;
  if (!(priority || assigneeName || subprojectName || labels.length > 0 || createPending || createError)) return null;
  return (
    <div
      className="flex items-center gap-2 flex-wrap px-3 py-1.5 text-[10px]"
      style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)", ...TINY_LABEL }}
    >
      {priority && <span className="verdict-chip" data-verdict="attested">priority {priority}</span>}
      {assigneeName && <span className="verdict-chip" data-verdict="attested">@{assigneeName}</span>}
      {subprojectName && <span className="verdict-chip" data-verdict="attested">in {subprojectName}</span>}
      {labels.map((l) => <span key={l} className="verdict-chip" data-verdict="attested">#{l}</span>)}
      {createError ? (
        <span className="verdict-chip" data-verdict="block">
          err: {(createError as Error).message?.slice(0, 60) ?? "create failed"}
        </span>
      ) : null}
    </div>
  );
}

function ChipSelect(props: { label: string; value: string; options: Array<{ value: string; label: string }>; onChange: (next: string) => void; }) {
  const { label, value, options, onChange } = props;
  return (
    <label className="inline-flex items-center gap-1.5">
      <span className="text-[10px] uppercase tracking-widest" style={TINY_LABEL}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent outline-none border-0 text-[12px] cursor-pointer"
        style={{ ...FONT_MONO, color: value ? "var(--foreground)" : "var(--text-tertiary)", borderBottom: "1px dashed var(--border)", padding: "0 2px" }}
      >
        {options.map((o) => <option key={o.value || "__none"} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
