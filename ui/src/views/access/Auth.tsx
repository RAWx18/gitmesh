import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "@/lib/router";
import { authApi } from "../../api/auth";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "@/components/ui/button";
import { AsciiArtAnimation } from "@/components/AsciiArtAnimation";
import { Github, ArrowRight, Terminal, CircleDot } from "lucide-react";

type AuthMode = "sign_in" | "sign_up";

export function AuthPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<AuthMode>("sign_in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const nextPath = useMemo(() => searchParams.get("next") || "/", [searchParams]);
  const { data: session, isLoading: isSessionLoading } = useQuery({
    queryKey: queryKeys.auth.session,
    queryFn: () => authApi.getSession(),
    retry: false,
  });

  useEffect(() => {
    if (session) {
      navigate(nextPath, { replace: true });
    }
  }, [session, navigate, nextPath]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (mode === "sign_in") {
        await authApi.signInEmail({ email: email.trim(), password });
        return;
      }
      await authApi.signUpEmail({
        name: name.trim(),
        email: email.trim(),
        password,
      });
    },
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.session });
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      navigate(nextPath, { replace: true });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Authentication failed");
    },
  });

  const canSubmit =
    email.trim().length > 0 &&
    password.trim().length >= 8 &&
    (mode === "sign_in" || name.trim().length > 0);

  const githubConfigured = session === null
    // Not authed yet - we still need this flag, so query unauthenticated session
    ? true
    : (session?.githubOAuthConfigured ?? false);

  // We always re-query this; even when we don't have a session it returns the flag.
  // The endpoint returns null body for 401 but we use a separate fetch:
  const { data: oauthFlag } = useQuery({
    queryKey: ["auth", "github-config"],
    queryFn: async () => {
      const res = await fetch("/api/auth/get-session", {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const body = await res.json().catch(() => null);
      if (body && typeof body === "object") {
        const flag = (body as { githubOAuthConfigured?: unknown }).githubOAuthConfigured;
        if (typeof flag === "boolean") return flag;
        const data = (body as { data?: { githubOAuthConfigured?: unknown } }).data;
        if (data && typeof data.githubOAuthConfigured === "boolean") return data.githubOAuthConfigured;
      }
      return false;
    },
    retry: false,
  });

  const showGithubButton = (oauthFlag ?? githubConfigured) === true;

  if (isSessionLoading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="flex items-center gap-3">
          <span className="h-2 w-2 rounded-full bg-primary gm-pulse-dot" />
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-text-tertiary">
            Establishing session
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 flex bg-background text-foreground">
      {/* Left - atmospheric column */}
      <aside className="relative hidden md:flex md:w-[46%] flex-col justify-between overflow-hidden border-r border-border bg-surface-2">
        <div className="absolute inset-0 opacity-50">
          <AsciiArtAnimation />
        </div>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(180deg, color-mix(in oklab, var(--surface-2) 88%, transparent) 0%, color-mix(in oklab, var(--surface-2) 60%, transparent) 35%, color-mix(in oklab, var(--surface-2) 92%, transparent) 100%)",
          }}
        />

        <div className="relative px-12 pt-12">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border-strong bg-surface-1 text-primary">
              <span className="font-mono text-sm font-semibold">GM</span>
            </div>
            <div className="font-mono text-[11px] uppercase tracking-[0.32em] text-text-tertiary">
              GitMesh / Control Plane
            </div>
          </div>
        </div>

        <div className="relative px-12 pb-16">
          <p className="eyebrow mb-5">Operator console</p>
          <h2 className="font-display text-5xl leading-[0.95] tracking-tight md:text-6xl text-foreground">
            Coordinate
            <br />
            autonomous
            <br />
            <em className="text-primary not-italic" style={{ fontFamily: "var(--font-serif)", fontStyle: "italic" }}>delivery.</em>
          </h2>
          <p className="mt-6 max-w-md text-sm leading-relaxed text-text-secondary">
            Webhooks, policies, approvals, and budget - every agent action audited,
            every dollar accounted for. One control plane for the entire mesh.
          </p>

          <dl className="mt-10 grid grid-cols-3 gap-6 border-t border-border pt-6 max-w-md">
            <div>
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">Audit</dt>
              <dd className="mt-1 font-display text-2xl text-foreground">100<span className="text-text-tertiary">%</span></dd>
            </div>
            <div>
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">Adapters</dt>
              <dd className="mt-1 font-display text-2xl text-foreground">7</dd>
            </div>
            <div>
              <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-text-tertiary">Policy</dt>
              <dd className="mt-1 font-display text-2xl text-foreground">YAML</dd>
            </div>
          </dl>
        </div>
      </aside>

      {/* Right - form */}
      <main className="relative flex w-full flex-col md:w-[54%]">
        {/* Top status bar */}
        <header className="flex items-center justify-between border-b border-border px-6 py-4 md:px-10">
          <div className="flex items-center gap-2 md:hidden">
            <div className="flex h-7 w-7 items-center justify-center rounded-md border border-border-strong bg-surface-2 text-primary">
              <span className="font-mono text-xs font-semibold">GM</span>
            </div>
            <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-text-tertiary">
              GitMesh
            </span>
          </div>
          <div className="ml-auto flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-text-tertiary">
            <span className="h-1.5 w-1.5 rounded-full bg-success gm-pulse-dot" />
            <span>API operational</span>
          </div>
        </header>

        <div className="flex flex-1 items-center justify-center overflow-y-auto px-6 py-10 md:px-10">
          <div className="w-full max-w-[420px]">
            <div className="mb-8">
              <p className="eyebrow mb-3">{mode === "sign_in" ? "Sign in" : "Create account"}</p>
              <h1 className="font-display text-4xl leading-[1.05] tracking-tight text-foreground md:text-[2.75rem]">
                {mode === "sign_in" ? "Welcome back to the mesh." : "Spin up your workspace."}
              </h1>
              <p className="mt-3 text-sm leading-relaxed text-text-secondary">
                {mode === "sign_in"
                  ? "Use your email and password to access this instance."
                  : "Create an account on this instance. Email confirmation is not required."}
              </p>
            </div>

            {showGithubButton ? (
              <a
                href="/api/auth/sign-in/github"
                className="group flex w-full items-center justify-between gap-3 rounded-md border border-border-strong bg-surface-2 px-4 py-3 text-sm font-medium text-foreground transition-colors hover:bg-surface-3"
              >
                <span className="flex items-center gap-3">
                  <Github className="h-4 w-4" />
                  Continue with GitHub
                </span>
                <ArrowRight className="h-4 w-4 text-text-tertiary transition-transform group-hover:translate-x-0.5" />
              </a>
            ) : (
              <div className="rounded-md border border-border bg-surface-2/60 px-4 py-3">
                <div className="flex items-start gap-3">
                  <Terminal className="mt-0.5 h-4 w-4 text-text-tertiary" />
                  <div className="space-y-1.5">
                    <p className="text-sm font-medium text-foreground">GitHub OAuth not configured</p>
                    <p className="text-xs leading-relaxed text-text-secondary">
                      Set <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">GITHUB_CLIENT_ID</code>
                      {" "}and{" "}
                      <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">GITHUB_CLIENT_SECRET</code>
                      {" "}in <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">.env</code>, or use{" "}
                      <code className="rounded bg-surface-3 px-1 py-0.5 font-mono text-[11px] text-foreground">GITHUB_LOCAL_DEV_PAT</code>
                      {" "}for local development.
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="my-6 flex items-center gap-3">
              <div className="h-px flex-1 bg-border" />
              <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-text-tertiary">
                {showGithubButton ? "or with email" : "with email"}
              </span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                mutation.mutate();
              }}
            >
              {mode === "sign_up" && (
                <Field label="Name">
                  <input
                    className={inputClass}
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    autoComplete="name"
                    autoFocus
                    placeholder="Ada Lovelace"
                  />
                </Field>
              )}
              <Field label="Email">
                <input
                  className={inputClass}
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  autoFocus={mode === "sign_in"}
                  placeholder="ada@example.org"
                />
              </Field>
              <Field
                label="Password"
                hint={mode === "sign_up" ? "8+ characters" : undefined}
              >
                <input
                  className={inputClass}
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete={mode === "sign_in" ? "current-password" : "new-password"}
                  placeholder="••••••••"
                />
              </Field>

              {error && (
                <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2">
                  <CircleDot className="mt-0.5 h-3.5 w-3.5 text-destructive" />
                  <p className="text-xs leading-relaxed text-destructive">{error}</p>
                </div>
              )}

              <Button
                type="submit"
                disabled={!canSubmit || mutation.isPending}
                className="w-full h-11 rounded-md text-[13px] font-medium tracking-wide"
              >
                {mutation.isPending
                  ? "Working…"
                  : mode === "sign_in"
                    ? "Sign in"
                    : "Create account"}
                {!mutation.isPending && <ArrowRight className="h-4 w-4" />}
              </Button>
            </form>

            <p className="mt-6 text-sm text-text-secondary">
              {mode === "sign_in" ? "No account yet?" : "Already have an account?"}{" "}
              <button
                type="button"
                className="font-medium text-foreground underline decoration-text-tertiary underline-offset-4 transition-colors hover:decoration-primary"
                onClick={() => {
                  setError(null);
                  setMode(mode === "sign_in" ? "sign_up" : "sign_in");
                }}
              >
                {mode === "sign_in" ? "Create one" : "Sign in"}
              </button>
            </p>
          </div>
        </div>

        <footer className="border-t border-border px-6 py-4 md:px-10">
          <div className="flex flex-wrap items-center justify-between gap-3 font-mono text-[11px] uppercase tracking-[0.18em] text-text-tertiary">
            <span>v1 · Self-managed</span>
            <a href="/docs" className="transition-colors hover:text-foreground">
              Documentation →
            </a>
          </div>
        </footer>
      </main>
    </div>
  );
}

const inputClass =
  "w-full rounded-md border border-border bg-surface-2/60 px-3 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-text-tertiary focus:border-border-strong focus:bg-surface-2 focus:ring-2 focus:ring-ring/30";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-text-tertiary">
          {label}
        </span>
        {hint && (
          <span className="font-mono text-[10px] tracking-wide text-text-tertiary">{hint}</span>
        )}
      </div>
      {children}
    </label>
  );
}
