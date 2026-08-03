import { UserPlus, Lightbulb, ShieldCheck, CircleDot, ShieldAlert, GitMerge } from "lucide-react";

export const typeLabel: Record<string, string> = {
  enable_agent: "Enable Agent",
  approve_admin_strategy: "Admin Strategy",
  merge_pr: "Merge PR",
  close_issue: "Close Issue",
  publish_advisory: "Publish Advisory",
};

export const typeIcon: Record<string, typeof UserPlus> = {
  enable_agent: UserPlus,
  approve_admin_strategy: Lightbulb,
  merge_pr: GitMerge,
  close_issue: CircleDot,
  publish_advisory: ShieldAlert,
};

export const defaultTypeIcon = ShieldCheck;

function PayloadField({ label, value }: { label: string; value: unknown }) {
  if (!value) return null;
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">{label}</span>
      <span>{String(value)}</span>
    </div>
  );
}

export function EnableAgentPayload({ payload }: { payload: Record<string, unknown> }) {
  return (
    <div className="mt-3 space-y-1.5 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Name</span>
        <span className="font-medium">{String(payload.name ?? "-")}</span>
      </div>
      <PayloadField label="Role" value={payload.role} />
      <PayloadField label="Title" value={payload.title} />
      <PayloadField label="Icon" value={payload.icon} />
      {!!payload.capabilities && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs pt-0.5">Capabilities</span>
          <span className="text-muted-foreground">{String(payload.capabilities)}</span>
        </div>
      )}
      {!!payload.adapterType && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Adapter</span>
          <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
            {String(payload.adapterType)}
          </span>
        </div>
      )}
    </div>
  );
}

export function CeoStrategyPayload({ payload }: { payload: Record<string, unknown> }) {
  const plan = payload.plan ?? payload.description ?? payload.strategy ?? payload.text;
  return (
    <div className="mt-3 space-y-1.5 text-sm">
      <PayloadField label="Title" value={payload.title} />
      {!!plan && (
        <div className="mt-2 rounded-md bg-muted/40 px-3 py-2 text-sm text-muted-foreground whitespace-pre-wrap font-mono text-xs max-h-48 overflow-y-auto">
          {String(plan)}
        </div>
      )}
      {!plan && (
        <pre className="mt-2 rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground overflow-x-auto max-h-48">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function ApprovalPayloadRenderer({ type, payload }: { type: string; payload: Record<string, unknown> }) {
  if (type === "enable_agent") return <EnableAgentPayload payload={payload} />;
  if (type === "merge_pr") return <MergePrPayload payload={payload} />;
  if (type === "close_issue") return <CloseIssuePayload payload={payload} />;
  if (type === "publish_advisory") return <PublishAdvisoryPayload payload={payload} />;
  if (type === "approve_admin_strategy") return <ApproveAdminStrategyPayload payload={payload} />;
  return <CeoStrategyPayload payload={payload} />;
}

export function MergePrPayload({ payload }: { payload: Record<string, unknown> }) {
  const prNumber = payload.prNumber;
  const prTitle = payload.prTitle;
  const repo = payload.repo;
  const url = payload.url;

  return (
    <div className="mt-3 space-y-1.5 text-sm">
      {prNumber != null && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">PR</span>
          <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">#{String(prNumber)}</span>
        </div>
      )}
      {!!prTitle && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Title</span>
          <span className="font-medium">{String(prTitle)}</span>
        </div>
      )}
      {!!repo && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Repo</span>
          <span className="font-mono text-xs">{String(repo)}</span>
        </div>
      )}
      {!!url && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Link</span>
          <a
            href={String(url)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline break-all"
          >
            {String(url)}
          </a>
        </div>
      )}
    </div>
  );
}

export function CloseIssuePayload({ payload }: { payload: Record<string, unknown> }) {
  const issueIdentifier = payload.issueIdentifier;
  const issueTitle = payload.issueTitle;
  const reason = payload.reason;

  return (
    <div className="mt-3 space-y-1.5 text-sm">
      {!!issueIdentifier && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Issue</span>
          <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">{String(issueIdentifier)}</span>
        </div>
      )}
      {!!issueTitle && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Title</span>
          <span className="font-medium">{String(issueTitle)}</span>
        </div>
      )}
      {!!reason && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Reason</span>
          <span className="italic text-muted-foreground">{String(reason)}</span>
        </div>
      )}
    </div>
  );
}

export function PublishAdvisoryPayload({ payload }: { payload: Record<string, unknown> }) {
  const advisoryId = payload.advisoryId;
  const title = payload.title;
  const severity = payload.severity;
  const pkg = payload.package;

  const severityColor: Record<string, string> = {
    Critical: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    High: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
    Medium: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    Low: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  };
  const badgeClass = severity ? (severityColor[String(severity)] ?? "bg-muted text-muted-foreground") : "";

  return (
    <div className="mt-3 space-y-1.5 text-sm">
      {!!advisoryId && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">ID</span>
          <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">{String(advisoryId)}</span>
        </div>
      )}
      {!!title && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Title</span>
          <span className="font-medium">{String(title)}</span>
        </div>
      )}
      {!!severity && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Severity</span>
          <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${badgeClass}`}>{String(severity)}</span>
        </div>
      )}
      {!!pkg && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Package</span>
          <span className="font-mono text-xs">{String(pkg)}</span>
        </div>
      )}
    </div>
  );
}

export function ApproveAdminStrategyPayload({ payload }: { payload: Record<string, unknown> }) {
  const strategyName = payload.strategyName ?? payload.name ?? payload.strategy;
  const description = payload.description ?? payload.plan ?? payload.text;

  return (
    <div className="mt-3 space-y-1.5 text-sm">
      {!!strategyName && (
        <div className="flex items-start gap-2">
          <span className="text-muted-foreground w-20 sm:w-24 shrink-0 text-xs">Strategy</span>
          <span className="font-medium">{String(strategyName)}</span>
        </div>
      )}
      {!!description && (
        <div className="mt-2 rounded-md bg-muted/40 px-3 py-2 text-sm text-muted-foreground whitespace-pre-wrap font-mono text-xs max-h-48 overflow-y-auto">
          {String(description)}
        </div>
      )}
      {!strategyName && !description && (
        <pre className="mt-2 rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground overflow-x-auto max-h-48">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}
