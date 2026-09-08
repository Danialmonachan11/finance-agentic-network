import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { getMe, getProposals, logout } from "@/lib/api";

const primaryNav = [
  { to: "/pairs", label: "Pairs", badge: false },
  { to: "/queue", label: "Approval queue", badge: true },
  { to: "/invoices", label: "Invoices" },
  { to: "/executed", label: "Executed" },
  { to: "/agents", label: "Agent performance" },
] as const;


const secondaryNav = [{ to: "/audit", label: "Raw audit log" }] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: proposals } = useQuery({ queryKey: ["proposals"], queryFn: getProposals });
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: getMe });
  const pendingCount = proposals?.length ?? 0;

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear();
      navigate({ to: "/login" });
    },
  });

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="bg-sidebar text-sidebar-foreground lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto">
        <div className="flex h-full flex-col px-4 py-6">
          <Link to="/queue" className="block px-2">
            <span className="label-mono block text-sidebar-muted">Finance</span>
            <span className="mt-0.5 block text-sm font-semibold tracking-tight">
              Agentic Network
            </span>
          </Link>

          <nav className="mt-8 flex-1" aria-label="Primary">
            <p className="label-mono px-2 pb-2 text-sidebar-muted">Review</p>
            <ul className="space-y-0.5">
              {primaryNav.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className="flex items-center justify-between rounded-md px-2 py-2 text-sm text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
                    activeProps={{
                      className: "bg-sidebar-accent !text-sidebar-foreground font-medium",
                    }}
                  >
                    <span>{item.label}</span>
                    {"badge" in item && item.badge && pendingCount > 0 ? (
                      <span className="num rounded-sm bg-primary px-1.5 py-0.5 text-2xs font-semibold text-primary-foreground">
                        {pendingCount}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>

            <p className="label-mono mt-8 px-2 pb-2 text-sidebar-muted">Technical</p>
            <ul className="space-y-0.5 border-t border-sidebar-border pt-2">
              {secondaryNav.map((item) => (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    className="block rounded-md px-2 py-1.5 text-xs text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
                    activeProps={{ className: "!text-sidebar-foreground" }}
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div className="mt-8 border-t border-sidebar-border pt-4">
            {me ? (
              <>
                <p className="text-xs font-medium">{me.display_name}</p>
                <p className="label-mono mt-0.5 text-sidebar-muted">{me.role} role</p>
                <button
                  type="button"
                  onClick={() => logoutMutation.mutate()}
                  disabled={logoutMutation.isPending}
                  className="mt-3 inline-block text-xs text-sidebar-muted underline underline-offset-4 hover:text-sidebar-foreground"
                >
                  {logoutMutation.isPending ? "Signing out…" : "Sign out"}
                </button>
              </>
            ) : (
              <Link
                to="/login"
                className="inline-block text-xs text-sidebar-muted underline underline-offset-4 hover:text-sidebar-foreground"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </aside>

      <main className="min-w-0 px-6 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}

export function DataNote({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn("text-xs text-muted-foreground", className)}>{children}</p>
  );
}
