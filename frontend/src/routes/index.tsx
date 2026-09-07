import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/fan/shell";
import { Badge, Button, EmptyState, PageHeader, Panel, SkeletonRows } from "@/components/fan/ui";
import { money } from "@/lib/fan-data";
import { getCompanies, getProposals } from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Companies — Finance Agentic Network" },
      {
        name: "description",
        content:
          "Every company in the network, what it is owed, what it owes, and how many discount requests are waiting on its review.",
      },
      { property: "og:title", content: "Companies — Finance Agentic Network" },
      {
        property: "og:description",
        content: "Network overview of receivables, payables and pending discount reviews.",
      },
    ],
  }),
  component: CompaniesPage,
});

function CompaniesPage() {
  const companiesQuery = useQuery({ queryKey: ["companies"], queryFn: getCompanies });
  const proposalsQuery = useQuery({ queryKey: ["proposals"], queryFn: getProposals });
  const totalPending = proposalsQuery.data?.length ?? 0;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Network overview"
        title="Companies"
        description="Every company here both sells and buys. Receivable is what a company is owed on open invoices; payable is what it owes on open invoices. Neither figure includes anything already settled."
        actions={
          <Link to="/queue">
            <Button variant="primary" size="sm">
              Go to approval queue ({totalPending})
            </Button>
          </Link>
        }
      />

      {companiesQuery.isLoading ? (
        <Panel>
          <SkeletonRows rows={4} />
        </Panel>
      ) : companiesQuery.isError || !companiesQuery.data ? (
        <Panel>
          <EmptyState
            title="Couldn't load this"
            body="Something went wrong fetching companies. Try again."
            action={
              <Button size="sm" onClick={() => companiesQuery.refetch()}>
                Try again
              </Button>
            }
          />
        </Panel>
      ) : companiesQuery.data.length === 0 ? (
        <Panel>
          <EmptyState
            title="No companies yet"
            body="Once invoices exist between two parties, both appear here automatically."
          />
        </Panel>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {companiesQuery.data.map((c) => (
            <Link
              key={c.id}
              to="/company/$id"
              params={{ id: c.id }}
              className="surface group flex flex-col p-5 transition-shadow hover:shadow-raised"
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-sm font-semibold group-hover:text-primary">{c.name}</h2>
                {c.pending_as_seller > 0 ? (
                  <Badge tone="pending">{c.pending_as_seller} awaiting review</Badge>
                ) : null}
              </div>

              <dl className="mt-5 grid grid-cols-2 gap-4">
                <div>
                  <dt className="label-mono">Receivable</dt>
                  <dd className="num mt-1 text-base font-semibold">{money(c.receivable)}</dd>
                  <dd className="mt-0.5 text-2xs text-muted-foreground">
                    owed to them, unpaid
                  </dd>
                </div>
                <div>
                  <dt className="label-mono">Payable</dt>
                  <dd className="num mt-1 text-base font-semibold">{money(c.payable)}</dd>
                  <dd className="mt-0.5 text-2xs text-muted-foreground">
                    they owe, unpaid
                  </dd>
                </div>
              </dl>

              <div className="mt-5 flex items-center gap-4 border-t border-border pt-3 text-2xs text-muted-foreground">
                <span>
                  <span className="num font-semibold text-foreground">
                    {c.invoices_as_seller}
                  </span>{" "}
                  issued
                </span>
                <span>
                  <span className="num font-semibold text-foreground">
                    {c.invoices_as_buyer}
                  </span>{" "}
                  received
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
