import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell } from "@/components/fan/shell";
import {
  ApprovalLevelBadge,
  Badge,
  Button,
  EmptyState,
  Field,
  InfoTip,
  PageHeader,
  Panel,
  RiskMeter,
  SkeletonRows,
  Stat,
  StatusBadge,
  Table,
  Td,
  Th,
  inputClass,
} from "@/components/fan/ui";
import { money, pct, shortDate, type Company, type InvoiceRow } from "@/lib/fan-data";
import {
  generateInvoice,
  getCompanies,
  getExecuted,
  getInvoices,
  getProposals,
  submitRequest,
} from "@/lib/api";

export const Route = createFileRoute("/company/$id")({
  head: () => ({
    meta: [
      { title: "Company — Finance Agentic Network" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: CompanyPage,
});

function CompanyPage() {
  const { id } = Route.useParams();
  const [showForms, setShowForms] = useState(false);

  const companiesQuery = useQuery({ queryKey: ["companies"], queryFn: getCompanies });
  const proposalsQuery = useQuery({ queryKey: ["proposals"], queryFn: getProposals });
  const invoicesQuery = useQuery({ queryKey: ["invoices"], queryFn: getInvoices });
  const executedQuery = useQuery({ queryKey: ["executed"], queryFn: getExecuted });

  const isLoading =
    companiesQuery.isLoading ||
    proposalsQuery.isLoading ||
    invoicesQuery.isLoading ||
    executedQuery.isLoading;
  const isError =
    companiesQuery.isError ||
    proposalsQuery.isError ||
    invoicesQuery.isError ||
    executedQuery.isError ||
    !companiesQuery.data ||
    !proposalsQuery.data ||
    !invoicesQuery.data ||
    !executedQuery.data;

  if (isLoading) {
    return (
      <AppShell>
        <PageHeader eyebrow="Company" title="Loading…" description="" />
        <Panel>
          <SkeletonRows rows={6} />
        </Panel>
      </AppShell>
    );
  }
  if (isError) {
    return (
      <AppShell>
        <PageHeader eyebrow="Company" title="Couldn't load this" description="" />
        <Panel>
          <EmptyState
            title="Couldn't load this"
            body="Something went wrong fetching this company. Try again."
            action={
              <Button
                size="sm"
                onClick={() => {
                  companiesQuery.refetch();
                  proposalsQuery.refetch();
                  invoicesQuery.refetch();
                  executedQuery.refetch();
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

  if (!companiesQuery.data || !proposalsQuery.data || !invoicesQuery.data || !executedQuery.data) {
    return null; // unreachable — the isError branch above covers this
  }

  const companies = companiesQuery.data;
  const company = companies.find((c) => c.id === id);

  if (!company) {
    return (
      <AppShell>
        <PageHeader eyebrow="Company" title="Not found" description="" />
        <Panel>
          <EmptyState
            title="Company not found"
            body="No company with this id exists in the network."
            action={
              <Link to="/">
                <Button size="sm">Back to companies</Button>
              </Link>
            }
          />
        </Panel>
      </AppShell>
    );
  }

  const pending = proposalsQuery.data.filter((r) => r.seller_name === company.name);
  const rows = invoicesQuery.data.filter(
    (i) => i.seller_name === company.name || i.buyer_name === company.name,
  );
  const executedCount = executedQuery.data.filter(
    (e) => e.seller_name === company.name || e.buyer_name === company.name,
  ).length;
  const receivedInvoices = rows.filter((i) => i.buyer_name === company.name);

  return (
    <AppShell>
      <PageHeader
        eyebrow="Company"
        title={company.name}
        description={`${money(company.receivable)} owed to them and ${money(
          company.payable,
        )} owed by them, across open invoices only.`}
        actions={
          pending.length > 0 ? (
            <Link to="/queue">
              <Button variant="primary" size="sm">
                Review {pending.length} request(s)
              </Button>
            </Link>
          ) : null
        }
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Invoices issued" value={company.invoices_as_seller} hint="as the seller" />
        <Stat label="Invoices received" value={company.invoices_as_buyer} hint="as the buyer" />
        <Stat
          label="Awaiting review"
          value={company.pending_as_seller}
          hint="discount requests they must decide"
          tone="accent"
        />
        <Stat label="Executed" value={executedCount} hint="already settled either way" />
      </div>

      <div className="space-y-6">
        <Panel
          title="Pending discount requests"
          description={`Requests where ${company.name} is the seller and a decision is owed.`}
        >
          {pending.length === 0 ? (
            <EmptyState
              title="Nothing to review"
              body={`No buyer is currently asking ${company.name} for a discount that needs a human.`}
            />
          ) : (
            <ul>
              {pending.map((r) => (
                <li
                  key={r.proposal_id}
                  className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4 last:border-b-0"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="num text-sm font-semibold">{r.invoice_number}</span>
                      <ApprovalLevelBadge level={r.approval_level} />
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {r.buyer_name} asks {pct(r.claimed_rate)} off {money(r.amount)} · due{" "}
                      {shortDate(r.due_date)}
                    </p>
                    <div className="mt-2 flex items-center gap-1.5">
                      <RiskMeter score={r.risk_score} compact />
                      <InfoTip label="What this risk score means">
                        {r.risk_score === null
                          ? "Not yet scored — the risk agent hasn't run on this request yet."
                          : `${r.risk_score.toFixed(2)} on a 0.00–1.00 scale, where 0.00 is safest.`}
                        {r.risk_reason
                        ? ` Flagged because: ${r.risk_reason}`
                        : " No specific flag was raised; it came here on the escalation rule alone."}
                      </InfoTip>
                      </div>
                  </div>
                  <Link to="/queue">
                    <Button size="sm" variant="primary">
                      Open in queue
                    </Button>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Invoice tracker" description="Every invoice this company is a party to.">
          <Table>
            <thead>
              <tr>
                <Th>Invoice</Th>
                <Th>Role</Th>
                <Th>Counterparty</Th>
                <Th align="right">Amount</Th>
                <Th>Contract</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((inv) => {
                const issued = inv.seller_name === company.name;
                return (
                  <tr
                    key={inv.invoice_number}
                    className="transition-colors hover:bg-secondary/60"
                  >
                    <Td mono className="font-semibold">
                      {inv.invoice_number}
                    </Td>
                    <Td>
                      <Badge tone="neutral">{issued ? "issued" : "received"}</Badge>
                    </Td>
                    <Td>{issued ? inv.buyer_name : inv.seller_name}</Td>
                    <Td mono align="right">
                      {money(inv.amount)}
                    </Td>
                    <Td>
                      <StatusBadge
                        status={
                          inv.contract_status === "none" || inv.contract_status === null
                            ? "no_contract"
                            : inv.contract_status
                        }
                      />
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </Panel>

        <section className="border-t border-border pt-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold">Occasional actions</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Issuing an invoice or asking for a discount, for the rare times this company is
                the one starting something.
              </p>
            </div>
            <Button size="sm" onClick={() => setShowForms((s) => !s)} aria-expanded={showForms}>
              {showForms ? "Hide" : "Show"}
            </Button>
          </div>

          {showForms ? (
            <div className="mt-5 grid gap-5 lg:grid-cols-2">
              <InvoiceForm company={company} companies={companies} />
              <DiscountRequestForm company={company} receivedInvoices={receivedInvoices} />
            </div>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}

function InvoiceForm({ company, companies }: { company: Company; companies: Company[] }) {
  const queryClient = useQueryClient();
  const [buyerId, setBuyerId] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [dueDate, setDueDate] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      generateInvoice(company.id, {
        buyer_company_id: buyerId,
        description,
        quantity: "1",
        unit_price: amount,
        due_date: dueDate,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      setDescription("");
      setAmount("");
      setDueDate("");
    },
  });

  return (
    <Panel
      title="Generate and send an invoice"
      description="Produces a real PDF on disk and emails it to the buyer."
    >
      <form
        className="space-y-4 px-5 py-5"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <Field label="Buyer">
          <select
            className={inputClass}
            value={buyerId}
            onChange={(e) => setBuyerId(e.target.value)}
            required
          >
            <option value="" disabled>
              Pick a company
            </option>
            {companies
              .filter((c) => c.id !== company.id)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Description">
          <input
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Consulting services, March"
            required
          />
        </Field>
        <Field label="Amount" hint="Euro, before any discount.">
          <input
            className={inputClass}
            type="number"
            step="0.01"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </Field>
        <Field label="Due date">
          <input
            className={inputClass}
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            required
          />
        </Field>
        {mutation.isError ? (
          <p className="text-xs text-destructive">
            {mutation.error instanceof Error ? mutation.error.message : "Couldn't generate the invoice. Try again."}
          </p>
        ) : null}
        <Button variant="primary" type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? "Sending…" : "Generate and send"}
        </Button>
      </form>
    </Panel>
  );
}

function DiscountRequestForm({
  company,
  receivedInvoices,
}: {
  company: Company;
  receivedInvoices: InvoiceRow[];
}) {
  const queryClient = useQueryClient();
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [rate, setRate] = useState("");
  const [justification, setJustification] = useState("");

  const mutation = useMutation({
    mutationFn: () => {
      const invoice = receivedInvoices.find((i) => i.invoice_number === invoiceNumber);
      if (!invoice) throw new Error("no invoice selected");
      return submitRequest(company.id, {
        invoice_id: invoice.invoice_id,
        message: `Requesting a ${rate}% discount. ${justification}`,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["proposals"] });
      queryClient.invalidateQueries({ queryKey: ["executed"] });
      setInvoiceNumber("");
      setRate("");
      setJustification("");
    },
  });

  return (
    <Panel
      title="Request a discount as the buyer"
      description="Goes into the pipeline; the seller sees it only if a human is needed."
    >
      <form
        className="space-y-4 px-5 py-5"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <Field label="Invoice received">
          <select
            className={inputClass}
            value={invoiceNumber}
            onChange={(e) => setInvoiceNumber(e.target.value)}
            required
          >
            <option value="" disabled>
              Pick an invoice
            </option>
            {receivedInvoices.map((i) => (
              <option key={i.invoice_number} value={i.invoice_number}>
                {i.invoice_number} — {i.seller_name} — {money(i.amount)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Rate asked for" hint="A share of the invoice, e.g. 10 for 10%.">
          <input
            className={inputClass}
            type="number"
            step="0.5"
            placeholder="10"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            required
          />
        </Field>
        <Field
          label="Justification"
          hint="The pipeline grounds this against the contract on file."
        >
          <textarea
            className={`${inputClass} h-24 resize-y py-2`}
            placeholder="Volume up 22% this quarter, tier B reached on…"
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            required
          />
        </Field>
        {mutation.isError ? (
          <p className="text-xs text-destructive">
            {mutation.error instanceof Error ? mutation.error.message : "Couldn't submit the request. Try again."}
          </p>
        ) : null}
        <Button
          type="submit"
          className="w-full"
          disabled={receivedInvoices.length === 0 || mutation.isPending}
        >
          {mutation.isPending
            ? "Sending…"
            : receivedInvoices.length === 0
              ? "No received invoices to discount"
              : "Send request"}
        </Button>
      </form>
    </Panel>
  );
}
