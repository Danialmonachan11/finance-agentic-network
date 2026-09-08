import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/fan/shell";
import {
  Button,
  EmptyState,
  FilterSelect,
  PageHeader,
  Panel,
  SearchInput,
  SkeletonRows,
  SortTh,
  StatusBadge,
  Table,
  Td,
  Th,
  Toolbar,
} from "@/components/fan/ui";
import { money, type InvoiceRow } from "@/lib/fan-data";
import { API_BASE, getInvoices } from "@/lib/api";

export const Route = createFileRoute("/invoices")({
  head: () => ({
    meta: [
      { title: "Invoices — Finance Agentic Network" },
      {
        name: "description",
        content:
          "Every invoice in the network with seller, buyer, amount and contract status.",
      },
      { property: "og:title", content: "Invoices — Finance Agentic Network" },
      { property: "og:description", content: "Network-wide invoice list." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: InvoicesPage,
});

type SortKey = "invoice_number" | "seller_name" | "buyer_name" | "amount";

const EMPTY_INVOICES: InvoiceRow[] = [];

function InvoicesPage() {
  const invoicesQuery = useQuery({ queryKey: ["invoices"], queryFn: getInvoices });
  const [query, setQuery] = useState("");
  const [contract, setContract] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("invoice_number");
  const [direction, setDirection] = useState<"asc" | "desc">("asc");

  const invoices = invoicesQuery.data ?? EMPTY_INVOICES;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = invoices.filter((i) => {
      if (
        q &&
        ![i.invoice_number, i.seller_name, i.buyer_name].some((f) => f.toLowerCase().includes(q))
      )
        return false;
      if (contract !== "all" && i.contract_status !== contract) return false;
      return true;
    });
    return [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const cmp =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      return direction === "asc" ? cmp : -cmp;
    });
  }, [invoices, query, contract, sortKey, direction]);

  function sortBy(key: SortKey) {
    if (key === sortKey) setDirection((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDirection(key === "amount" ? "desc" : "asc");
    }
  }

  const filtersOn = query.trim() !== "" || contract !== "all";

  return (
    <AppShell>
      <PageHeader
        eyebrow="Documents"
        title="Invoices"
        description="All invoices across the network, whichever side each company is on."
      />

      {invoicesQuery.isLoading ? (
        <Panel title="All invoices">
          <SkeletonRows rows={6} />
        </Panel>
      ) : invoicesQuery.isError ? (
        <Panel title="All invoices">
          <EmptyState
            title="Couldn't load this"
            body="Something went wrong fetching invoices. Try again."
            action={
              <Button size="sm" onClick={() => invoicesQuery.refetch()}>
                Try again
              </Button>
            }
          />
        </Panel>
      ) : (
        <Panel title="All invoices" description={`${invoices.length} invoice(s) across the network.`}>
          <Toolbar>
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder="Invoice number, seller or buyer"
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
            <div className="ml-auto flex items-center gap-3 pb-0.5">
              <span className="num text-2xs text-muted-foreground">
                {rows.length} of {invoices.length} rows
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={!filtersOn}
                onClick={() => {
                  setQuery("");
                  setContract("all");
                }}
              >
                Clear
              </Button>
            </div>
          </Toolbar>

          {rows.length === 0 ? (
            <EmptyState
              title="No invoice matches those filters"
              body="Try a shorter search term, or widen the contract filter."
              action={
                <Button
                  size="sm"
                  onClick={() => {
                    setQuery("");
                    setContract("all");
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <SortTh
                    active={sortKey === "invoice_number"}
                    direction={direction}
                    onClick={() => sortBy("invoice_number")}
                  >
                    Invoice
                  </SortTh>
                  <SortTh
                    active={sortKey === "seller_name"}
                    direction={direction}
                    onClick={() => sortBy("seller_name")}
                  >
                    Seller
                  </SortTh>
                  <SortTh
                    active={sortKey === "buyer_name"}
                    direction={direction}
                    onClick={() => sortBy("buyer_name")}
                  >
                    Buyer
                  </SortTh>
                  <SortTh
                    align="right"
                    active={sortKey === "amount"}
                    direction={direction}
                    onClick={() => sortBy("amount")}
                  >
                    Amount
                  </SortTh>
                  <Th>Direction</Th>
                  <Th>Contract</Th>
                  <Th>Document</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((inv) => (
                  <tr key={inv.invoice_number} className="transition-colors hover:bg-secondary/60">
                    <Td mono className="font-semibold">
                      {inv.invoice_number}
                    </Td>
                    <Td>{inv.seller_name}</Td>
                    <Td>{inv.buyer_name}</Td>
                    <Td>{inv.direction === "payable" ? "We owe" : "Owed to us"}</Td>
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
                    <Td>
                      {inv.has_pdf ? (
                        <a
                          href={`${API_BASE}/invoices/${inv.invoice_number}/pdf`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs font-medium text-primary underline underline-offset-4 hover:text-primary-hover"
                        >
                          View PDF
                        </a>
                      ) : (
                        <span className="text-xs text-muted-foreground">No document — seeded row</span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      )}
    </AppShell>
  );
}
