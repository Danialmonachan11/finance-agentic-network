import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/fan/shell";
import {
  ApprovalLevelBadge,
  Badge,
  Button,
  EmptyState,
  PageHeader,
  Panel,
  SkeletonRows,
  Stat,
  Table,
  Td,
  Th,
} from "@/components/fan/ui";
import { dateTime, pct } from "@/lib/fan-data";
import { getExecuted } from "@/lib/api";

export const Route = createFileRoute("/executed")({
  head: () => ({
    meta: [
      { title: "Executed decisions — Finance Agentic Network" },
      {
        name: "description",
        content:
          "History of settled discount requests: what was asked, what was approved, and who signed off.",
      },
      { property: "og:title", content: "Executed decisions — Finance Agentic Network" },
      {
        property: "og:description",
        content: "Settled discount decisions.",
      },
    ],
  }),
  component: ExecutedPage,
});

function ExecutedPage() {
  const executedQuery = useQuery({ queryKey: ["executed"], queryFn: getExecuted });

  if (executedQuery.isLoading) {
    return (
      <AppShell>
        <PageHeader eyebrow="History" title="Executed" description="Loading…" />
        <Panel>
          <SkeletonRows rows={6} />
        </Panel>
      </AppShell>
    );
  }
  if (executedQuery.isError || !executedQuery.data) {
    return (
      <AppShell>
        <PageHeader eyebrow="History" title="Executed" description="" />
        <Panel>
          <EmptyState
            title="Couldn't load this"
            body="Something went wrong fetching executed decisions. Try again."
            action={
              <Button size="sm" onClick={() => executedQuery.refetch()}>
                Try again
              </Button>
            }
          />
        </Panel>
      </AppShell>
    );
  }

  const executed = executedQuery.data;

  return (
    <AppShell>
      <PageHeader
        eyebrow="History"
        title="Executed"
        description="Requests that have been settled. The approved rate is often lower than the rate that was asked for — both are kept."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <Stat label="Decisions on record" value={executed.length} />
        {/* Every real executed row today is a human decision — no auto-execution
            path exists server-side yet (see "Known gaps", Phase 1). */}
        <Stat label="Decided by a person" value={executed.length} tone="accent" />
      </div>

      <Panel title="Decision history">
        <Table>
          <thead>
            <tr>
              <Th>Invoice</Th>
              <Th>Seller</Th>
              <Th>Buyer</Th>
              <Th align="right">Asked</Th>
              <Th align="right">Approved</Th>
              <Th>Sign-off level</Th>
              <Th>Approved by</Th>
              <Th>Decided</Th>
              <Th>Decided by</Th>
            </tr>
          </thead>
          <tbody>
            {executed.map((row) => (
              <tr key={row.invoice_number} className="transition-colors hover:bg-secondary/60">
                <Td mono className="font-semibold">
                  {row.invoice_number}
                </Td>
                <Td>{row.seller_name}</Td>
                <Td>{row.buyer_name}</Td>
                <Td mono align="right">
                  {pct(row.claimed_rate)}
                </Td>
                <Td mono align="right" className="font-semibold">
                  {row.approved_rate === 0 ? "0% — declined" : pct(row.approved_rate)}
                </Td>
                <Td>
                  <ApprovalLevelBadge level={row.approval_level} />
                </Td>
                <Td mono>{row.approved_by}</Td>
                <Td>{dateTime(row.decided_at)}</Td>
                <Td>
                  <Badge tone="accent">a person</Badge>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </AppShell>
  );
}
