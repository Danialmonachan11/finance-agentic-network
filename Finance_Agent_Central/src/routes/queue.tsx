import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell } from "@/components/fan/shell";
import {
  ApprovalLevelBadge,
  Badge,
  Button,
  EmptyState,
  FilterSelect,
  InfoTip,
  PageHeader,
  Panel,
  RiskMeter,
  SearchInput,
  SkeletonRows,
  StatusBadge,
} from "@/components/fan/ui";
import {
  companyIdByName,
  dateTime,
  humanStatus,
  money,
  pct,
  shortDate,
  type Company,
  type PendingRequest,
} from "@/lib/fan-data";
import { ApiError, approveProposal, declineProposal, getCompanies, getProposals } from "@/lib/api";
import { useLiveEvents } from "@/hooks/use-live-events";
import { cn } from "@/lib/utils";
import { Link } from "@tanstack/react-router";

export const Route = createFileRoute("/queue")({
  head: () => ({
    meta: [
      { title: "Approval queue — Finance Agentic Network" },
      {
        name: "description",
        content:
          "Review discount requests the agent pipeline could not decide on its own, and approve or decline each one.",
      },
      { property: "og:title", content: "Approval queue — Finance Agentic Network" },
      {
        property: "og:description",
        content: "Pending discount requests routed to a human reviewer.",
      },
    ],
  }),
  component: QueuePage,
});

function QueuePage() {
  const queryClient = useQueryClient();
  const proposalsQuery = useQuery({ queryKey: ["proposals"], queryFn: getProposals });
  const companiesQuery = useQuery({ queryKey: ["companies"], queryFn: getCompanies });

  useLiveEvents(
    ["workflow.executed", "workflow.declined", "workflow.escalated", "workflow.proposed", "workflow.auto_rejected", "workflow.auto_executed"],
    [["proposals"]],
  );

  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("all");
  const [contract, setContract] = useState("all");
  const [sort, setSort] = useState("risk_desc");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const decideMutation = useMutation({
    mutationFn: ({ id, outcome }: { id: string; outcome: "approved" | "declined" }) =>
      outcome === "approved" ? approveProposal(id) : declineProposal(id),
    onSuccess: (_data, { id }) => {
      setDecisionError(null);
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      setSelectedId((current) => (current === id ? null : current));
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 401) {
        setDecisionError("You're signed out. Sign in again to make a decision.");
      } else {
        // error.message is the real backend detail (e.g. the 409 conflict
        // text already says "already resolved by someone else"), show it
        // directly instead of a generic string.
        setDecisionError(error.message || "Couldn't save that decision. Try again.");
      }
    },
  });

  if (proposalsQuery.isLoading || companiesQuery.isLoading) {
    return (
      <AppShell>
        <PageHeader eyebrow="Primary task" title="Approval queue" description="Loading…" />
        <Panel>
          <SkeletonRows rows={6} />
        </Panel>
      </AppShell>
    );
  }
  if (proposalsQuery.isError || companiesQuery.isError || !proposalsQuery.data || !companiesQuery.data) {
    return (
      <AppShell>
        <PageHeader eyebrow="Primary task" title="Approval queue" description="" />
        <Panel>
          <EmptyState
            title="Couldn't load this"
            body="Something went wrong fetching the approval queue. Try again."
            action={
              <Button
                size="sm"
                onClick={() => {
                  proposalsQuery.refetch();
                  companiesQuery.refetch();
                }}
              >
                Try again
              </Button>
            }
          />
        </Panel>
      </AppShell>
    );
  }

  const pendingRequests = proposalsQuery.data;
  const companies = companiesQuery.data;
  const undecided = pendingRequests;

  const q = query.trim().toLowerCase();
  const open = undecided
    .filter((r) => {
      if (
        q &&
        ![r.invoice_number, r.seller_name, r.buyer_name].some((f) => f.toLowerCase().includes(q))
      )
        return false;
      if (level !== "all" && r.approval_level !== level) return false;
      if (contract !== "all" && r.contract_status !== contract) return false;
      return true;
    })
    .sort((a, b) => {
      // Unscored (null) requests sort after scored ones regardless of direction —
      // there's nothing to rank them by, so they shouldn't land at either extreme.
      switch (sort) {
        case "risk_asc":
          if (a.risk_score === null) return b.risk_score === null ? 0 : 1;
          if (b.risk_score === null) return -1;
          return a.risk_score - b.risk_score;
        case "amount_desc":
          return b.amount - a.amount;
        case "due_asc":
          return a.due_date.localeCompare(b.due_date);
        case "requested_desc":
          return b.requested_at.localeCompare(a.requested_at);
        default:
          if (a.risk_score === null) return b.risk_score === null ? 0 : 1;
          if (b.risk_score === null) return -1;
          return b.risk_score - a.risk_score;
      }
    });

  const selected = open.find((r) => r.proposal_id === selectedId) ?? open[0] ?? null;

  const filtersOn = q !== "" || level !== "all" || contract !== "all";
  function clearFilters() {
    setQuery("");
    setLevel("all");
    setContract("all");
  }

  function decide(id: string, outcome: "approved" | "declined") {
    decideMutation.mutate({ id, outcome });
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="Primary task"
        title="Approval queue"
        description="Discount requests the pipeline judged genuinely uncertain. Everything safe was already approved and everything clearly bad was already declined — these are the ones left for a person."
        actions={
          <Badge tone={undecided.length ? "pending" : "success"}>
            {undecided.length} awaiting review
          </Badge>
        }
      />

      {undecided.length === 0 ? (
        <Panel>
          <EmptyState
            title="Queue is clear"
            body="No discount request currently needs a human decision. New ones appear here the moment the pipeline escalates them."
            action={
              <Link to="/executed">
                <Button size="sm">See what was decided</Button>
              </Link>
            }
          />
        </Panel>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)] lg:items-start">
          <Panel
            title="Pending"
            description={`${open.length} of ${undecided.length} request(s) shown`}
          >
            <div className="space-y-3 border-b border-border bg-secondary/40 px-4 py-3">
              <SearchInput
                value={query}
                onChange={setQuery}
                placeholder="Invoice, buyer or seller"
              />
              <div className="grid grid-cols-2 gap-2">
                <FilterSelect
                  label="Sign-off"
                  value={level}
                  onChange={setLevel}
                  options={[
                    { value: "all", label: "Any sign-off" },
                    { value: "manager", label: "Manager sign-off" },
                    { value: "cfo", label: "CFO sign-off" },
                  ]}
                />
                <FilterSelect
                  label="Contract"
                  value={contract}
                  onChange={setContract}
                  options={[
                    { value: "all", label: "Any contract state" },
                    { value: "active", label: "Contract active" },
                    { value: "expired", label: "Contract expired" },
                    { value: "none", label: "No contract on file" },
                  ]}
                />
              </div>
              <FilterSelect
                label="Sort by"
                value={sort}
                onChange={setSort}
                options={[
                  { value: "risk_desc", label: "Riskiest first (1.00 → 0.00)" },
                  { value: "risk_asc", label: "Safest first (0.00 → 1.00)" },
                  { value: "amount_desc", label: "Largest invoice first" },
                  { value: "due_asc", label: "Soonest due date first" },
                  { value: "requested_desc", label: "Most recently requested" },
                ]}
              />
              {filtersOn ? (
                <Button size="sm" variant="ghost" onClick={clearFilters} className="w-full">
                  Clear filters
                </Button>
              ) : null}
            </div>

            {open.length === 0 ? (
              <EmptyState
                title="No request matches those filters"
                body="There are still requests waiting — they are just filtered out of this view."
                action={
                  <Button size="sm" onClick={clearFilters}>
                    Clear filters
                  </Button>
                }
              />
            ) : (
            <ul className="max-h-[70vh] overflow-y-auto">
              {open.map((r) => {

                const active = selected?.proposal_id === r.proposal_id;
                return (
                  <li key={r.proposal_id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(r.proposal_id)}
                      aria-current={active}
                      className={cn(
                        "w-full border-b border-border px-4 py-3 text-left transition-colors hover:bg-secondary",
                        active && "bg-accent/50 shadow-[inset_3px_0_0_0_var(--color-primary)]",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="num text-xs font-semibold">{r.invoice_number}</span>
                        <span className="num text-xs">{money(r.amount)}</span>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {r.buyer_name} → {r.seller_name}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Badge tone="neutral">{pct(r.claimed_rate)} asked</Badge>
                        <ApprovalLevelBadge level={r.approval_level} />
                      </div>
                      <div className="mt-2 flex items-center gap-1.5">
                        <RiskMeter score={r.risk_score} compact />
                        <InfoTip label="What this risk score means">
                          {r.risk_score === null
                            ? r.workflow_id
                              ? "Not yet scored — the risk agent hasn't run on this request yet."
                              : "Not scored — this is seed data, never run through the pipeline."
                            : `${r.risk_score.toFixed(2)} on a 0.00–1.00 scale, where 0.00 is safest.`}
                          {r.risk_reason
                            ? ` Flagged because: ${r.risk_reason}`
                            : r.workflow_id
                              ? " No specific flag was raised; it came here on the escalation rule alone."
                              : ""}
                        </InfoTip>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
            )}
          </Panel>


          {selected ? (
            <RequestDetail
              request={selected}
              companies={companies}
              onDecide={decide}
              pending={decideMutation.isPending}
              error={decisionError}
            />
          ) : (
            <Panel>
              <EmptyState
                title="Nothing selected"
                body="Pick a request from the list to see the full reasoning behind it."
              />
            </Panel>
          )}
        </div>
      )}

    </AppShell>
  );
}

function RequestDetail({
  request: r,
  companies,
  onDecide,
  pending,
  error,
}: {
  request: PendingRequest;
  companies: Company[];
  onDecide: (id: string, outcome: "approved" | "declined") => void;
  pending: boolean;
  error: string | null;
}) {
  const buyerId = companyIdByName(companies, r.buyer_name);
  const sellerId = companyIdByName(companies, r.seller_name);
  return (
    <div className="space-y-6">
      <Panel>
        <div className="border-b border-border px-5 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="label-mono">Invoice</p>
              <h2 className="num mt-1 text-xl font-semibold">{r.invoice_number}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {buyerId ? (
                  <Link
                    to="/company/$id"
                    params={{ id: buyerId }}
                    className="underline underline-offset-4 hover:text-foreground"
                  >
                    {r.buyer_name}
                  </Link>
                ) : (
                  r.buyer_name
                )}{" "}
                is asking{" "}
                {sellerId ? (
                  <Link
                    to="/company/$id"
                    params={{ id: sellerId }}
                    className="underline underline-offset-4 hover:text-foreground"
                  >
                    {r.seller_name}
                  </Link>
                ) : (
                  r.seller_name
                )}{" "}
                for a discount.
              </p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <ApprovalLevelBadge level={r.approval_level} />
              <StatusBadge
                status={
                  r.contract_status === "none" || r.contract_status === null
                    ? "no_contract"
                    : r.contract_status
                }
              />
            </div>
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-px bg-border sm:grid-cols-4">
          <Cell label="Discount asked" value={pct(r.claimed_rate)} />
          <Cell label="Invoice amount" value={money(r.amount)} />
          <Cell label="Value of discount" value={money(r.amount * r.claimed_rate)} />
          <Cell label="Due date" value={shortDate(r.due_date)} />
        </dl>

        <div className="border-t border-border px-5 py-5">
          <p className="label-mono mb-2">Risk</p>
          <RiskMeter score={r.risk_score} />
        </div>
      </Panel>

      <Panel title="Why the pipeline could not settle this">
        <div className="space-y-5 px-5 py-5">
          {r.workflow_id ? (
            <>
              <div>
                <p className="label-mono mb-1.5">Grounding — what supports the claim</p>
                <p className="text-sm leading-relaxed">
                  {r.grounding_reason ?? "No grounding reasoning was recorded for this run."}
                </p>
              </div>
              <div>
                <p className="label-mono mb-1.5">Risk — what argues against it</p>
                {r.risk_reason ? (
                  <p className="text-sm leading-relaxed">{r.risk_reason}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    The risk agent ran and raised no flag. This reached you on the escalation rule
                    alone (approval level requires a human regardless of risk).
                  </p>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Requested {dateTime(r.requested_at)} · workflow{" "}
                <span className="num">{r.workflow_id}</span> ·{" "}
                <Link to="/audit" className="underline underline-offset-4 hover:text-foreground">
                  see every pipeline step
                </Link>
              </p>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              This request was loaded as seed data, not run through the agent pipeline — there's no
              grounding, risk score, or agent trace to show because no agent ever touched it. Submit
              a new discount request from a company page to see the real pipeline run end to end.
            </p>
          )}
        </div>
      </Panel>

      <Panel title="Your decision" description="Both outcomes are final and both are recorded.">
        {error ? (
          <p className="mx-5 mt-5 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        ) : null}
        <div className="flex flex-col gap-3 px-5 py-5 sm:flex-row">
          <Button
            variant="primary"
            className="flex-1"
            disabled={pending}
            onClick={() => onDecide(r.proposal_id, "approved")}
          >
            {pending ? "Saving…" : `Approve ${pct(r.claimed_rate)} on ${r.invoice_number}`}
          </Button>
          <Button
            variant="danger"
            className="flex-1"
            disabled={pending}
            onClick={() => onDecide(r.proposal_id, "declined")}
          >
            {pending ? "Saving…" : "Decline this request"}
          </Button>
        </div>
        <p className="px-5 pb-5 text-xs text-muted-foreground">
          Approving applies {pct(r.claimed_rate)} ({money(r.amount * r.claimed_rate)}) to{" "}
          {r.invoice_number}. Declining leaves the invoice at its full amount and notifies{" "}
          {r.buyer_name}. Pipeline status for this request:{" "}
          {humanStatus("escalated_no_match").toLowerCase()}.
        </p>
      </Panel>
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-5 py-4">
      <dt className="label-mono">{label}</dt>
      <dd className="num mt-1 text-sm font-semibold">{value}</dd>
    </div>
  );
}
