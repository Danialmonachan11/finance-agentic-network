import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/fan/shell";
import {
  Badge,
  Button,
  EmptyState,
  InfoTip,
  PageHeader,
  Panel,
  ShareBar,
  SkeletonRows,
  Stat,
  StatusBadge,
  Table,
  Td,
  Th,
} from "@/components/fan/ui";
import { getAutomation } from "@/lib/api";
import { dateTime, pct } from "@/lib/fan-data";

const WINDOW_LABEL = "last 30 days";
/** Fully loaded hourly cost used for the savings figure below — an assumption, not measured. */
const REVIEWER_HOURLY_COST_USD = 52;
/** Minutes a reviewer historically spent on one request before the pipeline existed — an assumption, not measured. */
const MINUTES_PER_MANUAL_REVIEW = 11;

export const Route = createFileRoute("/agents")({
  head: () => ({
    meta: [
      { title: "Agent performance — Finance Agentic Network" },
      {
        name: "description",
        content:
          "How much of the discount review the pipeline auto-declined without a human, and what the models cost.",
      },
      { property: "og:title", content: "Agent performance — Finance Agentic Network" },
      {
        property: "og:description",
        content: "Auto-decline share and model spend against reviewer time saved.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AgentsPage,
});

function usd(n: number, digits = 2) {
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

function AgentsPage() {
  const automationQuery = useQuery({ queryKey: ["automation"], queryFn: getAutomation });

  if (automationQuery.isLoading) {
    return (
      <AppShell>
        <PageHeader eyebrow="Oversight" title="Agent performance and cost" description="Loading…" />
        <Panel>
          <SkeletonRows rows={6} />
        </Panel>
      </AppShell>
    );
  }
  if (automationQuery.isError || !automationQuery.data) {
    return (
      <AppShell>
        <PageHeader eyebrow="Oversight" title="Agent performance and cost" description="" />
        <Panel>
          <EmptyState
            title="Couldn't load this"
            body="Something went wrong fetching agent performance data. Try again."
            action={
              <Button size="sm" onClick={() => automationQuery.refetch()}>
                Try again
              </Button>
            }
          />
        </Panel>
      </AppShell>
    );
  }

  const data = automationQuery.data;
  const { total, auto_declined, auto_executed, human_decided, still_pending } = data.decided_or_pending;
  const decided = auto_declined + auto_executed + human_decided;
  const autoShare = decided ? (auto_declined + auto_executed) / decided : 0;
  const hoursSaved = ((auto_declined + auto_executed) * MINUTES_PER_MANUAL_REVIEW) / 60;
  const labourSaved = hoursSaved * REVIEWER_HOURLY_COST_USD;
  const models = data.models;
  const totalCost = models.reduce((a, m) => a + m.cost_usd, 0);
  const totalCalls = models.reduce((a, m) => a + m.calls, 0);
  const netSaved = labourSaved - totalCost;
  const costPerDecision = decided ? totalCost / decided : 0;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Oversight"
        title="Agent performance and cost"
        description={`What the pipeline auto-declined on its own over the ${WINDOW_LABEL}, and what the models cost against the reviewer time that saved.`}
        actions={<Badge tone="neutral">{WINDOW_LABEL}</Badge>}
      />

      {/* ------------------------------------------------ automation share */}
      <section className="mb-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
        <Panel title="Auto-declined without a human">
          <div className="px-5 py-5">
            <div className="flex items-end justify-between gap-4">
              <div className="flex items-baseline gap-2">
                <span className="num text-4xl font-semibold text-primary tabular-nums">
                  {(autoShare * 100).toFixed(1)}%
                </span>
                <span className="text-xs text-muted-foreground">
                  of decided requests, on a 0–100% scale
                </span>
              </div>
              <InfoTip label="How this share is worked out">
                {auto_declined} requests were auto-declined and {auto_executed} were auto-executed
                by the pipeline alone, with no human — an execution only happens when the discount
                is within contract terms and the risk score is low; anything else, including every
                approval above that risk bar, goes to a person ({human_decided} did). Requests still
                sitting in the queue ({still_pending}) are left out — they have not been decided by
                anyone yet.
              </InfoTip>
            </div>

            <div className="mt-4">
              <ShareBar value={autoShare} />
              <div className="mt-2 flex justify-between text-2xs text-muted-foreground">
                <span className="num">
                  {auto_declined + auto_executed} decided by the pipeline alone ({auto_declined}{" "}
                  declined, {auto_executed} executed)
                </span>
                <span className="num">{human_decided} decided by a person</span>
              </div>
            </div>

            <div className="mt-6 grid gap-px border-t border-border bg-border sm:grid-cols-3">
              <Fact label="Requests in window" value={total.toString()} />
              <Fact label="Decided" value={decided.toString()} />
              <Fact
                label="Still awaiting review"
                value={still_pending.toString()}
                hint="sitting in the approval queue"
              />
            </div>

            <div className="mt-6">
              <p className="label-mono mb-3">Week by week</p>
              <ul className="space-y-2.5">
                {data.weekly.map((w) => {
                  const weekDecided = w.auto_declined + w.auto_executed + w.human_decided;
                  const share = weekDecided ? (w.auto_declined + w.auto_executed) / weekDecided : 0;
                  return (
                    <li key={w.week} className="flex items-center gap-3">
                      <span className="num w-24 text-2xs text-muted-foreground">
                        {new Date(w.week).toLocaleDateString("en-GB", {
                          day: "2-digit",
                          month: "short",
                        })}
                      </span>
                      <div className="flex-1">
                        <ShareBar value={share} />
                      </div>
                      <span className="num w-28 text-right text-2xs text-muted-foreground">
                        {(share * 100).toFixed(0)}% of {weekDecided}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </Panel>

        {/* ------------------------------------------------------- cost meter */}
        <Panel title="Cost meter">
          <div className="space-y-4 px-5 py-5">
            <div>
              <p className="label-mono">Model spend, {WINDOW_LABEL}</p>
              <p className="num mt-1 text-2xl font-semibold">{usd(totalCost, 4)}</p>
              <p className="mt-1 text-2xs text-muted-foreground">
                Real provider-reported cost, not an estimate.
              </p>
            </div>

            <div className="border-t border-border pt-4">
              <p className="label-mono flex items-center gap-1.5">
                Reviewer time avoided
                <InfoTip label="How the saving is estimated">
                  {auto_declined + auto_executed} auto-decided requests × {MINUTES_PER_MANUAL_REVIEW}{" "}
                  minutes, an assumed median a reviewer spends per request, at{" "}
                  {usd(REVIEWER_HOURLY_COST_USD, 0)}/hour fully loaded. The minutes and the hourly
                  rate are assumptions, not measured figures; the model cost above is measured.
                </InfoTip>
              </p>
              <p className="num mt-1 text-2xl font-semibold">{hoursSaved.toFixed(1)} h</p>
              <p className="mt-1 text-2xs text-muted-foreground">
                worth about {usd(labourSaved)} of reviewer time
              </p>
            </div>

            <div className="border-t border-border pt-4">
              <p className="label-mono">Net against spend</p>
              <p
                className="num mt-1 text-2xl font-semibold"
                style={{ color: "var(--color-status-success-ink)" }}
              >
                {usd(netSaved)}
              </p>
              <p className="mt-1 text-2xs text-muted-foreground">
                estimated saving minus the measured model spend
              </p>
            </div>

            <div className="border-t border-border pt-4">
              <p className="label-mono">Cost per decision</p>
              <p className="num mt-1 text-base font-semibold">{usd(costPerDecision, 4)}</p>
            </div>
          </div>
        </Panel>
      </section>

      {/* -------------------------------------------------------- model table */}
      <div className="mb-8 grid gap-4 sm:grid-cols-3">
        <Stat label="Models in use" value={new Set(models.map((m) => m.model)).size} />
        <Stat label="Model calls" value={totalCalls.toLocaleString()} />
        <Stat label="Spend across models" value={usd(totalCost, 4)} tone="accent" />
      </div>

      <Panel
        title="Models in the pipeline"
        description="One row per model used in the window, with its real call, token, and cost totals."
      >
        <Table>
          <thead>
            <tr>
              <Th>Model</Th>
              <Th align="right">Calls</Th>
              <Th align="right">Tokens in / out</Th>
              <Th align="right">Cost</Th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.model} className="transition-colors hover:bg-secondary/60">
                <Td mono className="text-xs font-semibold">
                  {m.model}
                </Td>
                <Td mono align="right">
                  {m.calls.toLocaleString()}
                </Td>
                <Td mono align="right" className="text-xs">
                  {m.tokens_in.toLocaleString()} / {m.tokens_out.toLocaleString()}
                </Td>
                <Td mono align="right">
                  {usd(m.cost_usd, 4)}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>

      {/* -------------------------------------------------- what was decided */}
      <Panel
        title="What was decided"
        description={`Every request in the ${WINDOW_LABEL} that got a real outcome — the rows behind the numbers above.`}
      >
        {data.decisions.length === 0 ? (
          <div className="px-5 py-5">
            <EmptyState title="Nothing decided yet" body="No requests in this window have an outcome." />
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Invoice</Th>
                <Th>Seller</Th>
                <Th>Buyer</Th>
                <Th align="right">Rate</Th>
                <Th>Outcome</Th>
                <Th>Decided by</Th>
                <Th>Decided</Th>
              </tr>
            </thead>
            <tbody>
              {data.decisions.map((d) => (
                <tr key={`${d.invoice_number}-${d.decided_at}`} className="transition-colors hover:bg-secondary/60">
                  <Td mono className="font-semibold">
                    {d.invoice_number}
                  </Td>
                  <Td>{d.seller_name}</Td>
                  <Td>{d.buyer_name}</Td>
                  <Td mono align="right">
                    {pct(d.approved_rate ?? d.claimed_rate)}
                  </Td>
                  <Td>
                    <StatusBadge status={d.outcome} />
                  </Td>
                  <Td className="text-xs">{d.approved_by ?? "—"}</Td>
                  <Td className="text-xs text-muted-foreground">{dateTime(d.decided_at)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <p className="mt-6 text-xs text-muted-foreground">
        Spend and call counts come from the provider's own reporting. Time saved and the money
        attached to it are estimates built on an assumed review time, and are labelled as such.
        Step-by-step traces for individual workflows live in the{" "}
        <Link to="/audit" className="underline underline-offset-4 hover:text-foreground">
          raw audit log
        </Link>
        .
      </p>
    </AppShell>
  );
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-card px-4 py-3">
      <p className="label-mono">{label}</p>
      <p className="num mt-1 text-base font-semibold">{value}</p>
      {hint ? <p className="mt-0.5 text-2xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
