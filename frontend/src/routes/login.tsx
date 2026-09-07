import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Field, inputClass } from "@/components/fan/ui";
import { login } from "@/lib/api";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in — Finance Agentic Network" },
      {
        name: "description",
        content: "Sign in to review discount requests across the company network.",
      },
      { property: "og:title", content: "Sign in — Finance Agentic Network" },
      { property: "og:description", content: "Internal finance-ops sign in." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const loginMutation = useMutation({
    mutationFn: () => login(username, password),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      navigate({ to: "/queue" });
    },
  });

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,480px)]">
      <div className="hidden flex-col justify-between bg-sidebar px-12 py-14 text-sidebar-foreground lg:flex">
        <div>
          <p className="label-mono text-sidebar-muted">Finance</p>
          <p className="mt-1 text-lg font-semibold">Agentic Network</p>
        </div>
        <div className="max-w-md">
          <p className="text-sm leading-relaxed text-sidebar-muted">
            An agent pipeline approves the safe discount requests, declines the clearly bad ones,
            and sends everything genuinely uncertain here for a person to decide.
          </p>
          <p className="mt-4 text-xs text-sidebar-muted">
            Some data in this environment is real and some is seeded demo data. Each screen says
            which is which rather than pretending it's uniform.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-center px-6 py-16">
        <form
          className="w-full max-w-sm"
          onSubmit={(e) => {
            e.preventDefault();
            loginMutation.mutate();
          }}
        >
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            One account works across every company in the network.
          </p>

          <div className="mt-8 space-y-5">
            <Field label="Username">
              <input
                className={inputClass}
                name="username"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="your.name"
              />
            </Field>
            <Field label="Password">
              <input
                className={inputClass}
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </div>

          {loginMutation.isError ? (
            <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              Invalid username or password.
            </p>
          ) : null}

          <Button
            type="submit"
            variant="primary"
            className="mt-6 w-full"
            disabled={loginMutation.isPending || !username || !password}
          >
            {loginMutation.isPending ? "Signing in…" : "Sign in"}
          </Button>

          <p className="mt-6 border-t border-border pt-4 text-xs text-muted-foreground">
            Two demo accounts exist in this environment, one with a manager role and one with a
            CFO role. Credentials are handed out separately, not printed here.
          </p>
        </form>
      </div>
    </div>
  );
}
