import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/fan/shell";
import { Button, EmptyState, Panel, SkeletonRows, StatusBadge, Table, Td, Th } from "@/components/fan/ui";
import { dateTime } from "@/lib/fan-data";
import { getAudit } from "@/lib/api";

export const Route = createFileRoute("/audit")({
  head: () => ({
    meta: [
      { title: "Raw audit log — Finance Agentic Network" },
      {
        name: "description",
        content:
          "Technical view: one row per pipeline step, plus network-wide model spend, for anyone checking how the agents actually decided.",
      },
      { property: "og:title", content: "Raw audit log — Finance Agentic Network" },
      {
        property: "og:description",
        content: "Per-step pipeline trace and model spend. Secondary to the approval queue.",
      },
    ],
  }),
  component: AuditPage,
});

function AuditPage() {
  const auditQuery = useQuery({ queryKey: ["audit"], queryFn: getAudit });

  const header = (
    <header className="mb-8 border-b border-border pb-5">
      <p className="label-mono mb-2">Technical view · secondary</p>
      <h1 className="text-lg font-semibold">Raw audit log</h1>
      <p className="mt-2 max-w-2xl text-xs text-muted-foreground">
        One row per pipeline step, unedited. This page exists so anyone can check the agents'
        work; it is not where reviewing happens.{" "}
        <Link to="/queue" className="text-primary underline underline-offset-4">
          The approval queue is the working screen.
        </Link>
      </p>
    </header>
  );

  if (auditQuery.isLoading) {
    return (
      <AppShell>
        {header}
        <Panel>
          <SkeletonRows rows={6} />
        </Panel>
      </AppShell>
    );
  }
  if (auditQuery.isError || !auditQuery.data) {
    return (
      <AppShell>
        {header}
        <Panel>
          <EmptyState
            title="Couldn't load this"
            body="Something went wrong fetching the audit log. Try again."
            action={
              <Button size="sm" onClick={() => auditQuery.refetch()}>
                Try again
              </Button>
            }
          />
        </Panel>
      </AppShell>
    );
  }

  const audit = auditQuery.data;

  return (
    <AppShell>
      {header}

      <section className="surface mb-6 grid gap-px overflow-hidden bg-border sm:grid-cols-3">
        {[
          { label: "Workflows run", value: audit.network_cost.workflows.toLocaleString() },
          { label: "Model calls", value: audit.network_cost.calls.toLocaleString() },
          { label: "Spend", value: `$${audit.network_cost.total_cost_usd.toFixed(4)}` },
        ].map((s) => (
          <div key={s.label} className="bg-card px-5 py-4">
            <p className="label-mono">{s.label}</p>
            <p className="num mt-1 text-base font-semibold">{s.value}</p>
          </div>
        ))}
      </section>
      <p className="mb-6 text-xs text-muted-foreground">
        Network-wide model spend. This is the real OpenRouter-reported cost, not an estimate.
      </p>

      <Panel title="Pipeline steps">
        <Table>
          <thead>
            <tr>
              <Th>Workflow</Th>
              <Th>Step</Th>
              <Th>Agent</Th>
              <Th>Outcome</Th>
              <Th>Reason</Th>
              <Th>Timestamp</Th>
            </tr>
          </thead>
          <tbody>
            {audit.workflows.map((row, i) => (
              <tr
                key={`${row.workflow_id}-${i}`}
                className="text-xs transition-colors hover:bg-secondary/60"
              >
                <Td mono>{row.workflow_id}</Td>
                <Td mono>{row.step}</Td>
                <Td mono>{row.agent}</Td>
                <Td>
                  <StatusBadge status={row.status} />
                </Td>
                <Td className="max-w-md">{row.reason}</Td>
                <Td mono>{dateTime(row.timestamp)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </AppShell>
  );
}
