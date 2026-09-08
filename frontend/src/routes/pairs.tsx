import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell } from "@/components/fan/shell";
import {
  Badge,
  Button,
  EmptyState,
  Field,
  PageHeader,
  Panel,
  SkeletonRows,
  Table,
  Td,
  Th,
  inputClass,
} from "@/components/fan/ui";
import { pct, shortDate } from "@/lib/fan-data";
import {
  acceptPair,
  getCompanies,
  getMe,
  getPairs,
  invitePair,
  setPairAutoReply,
  type Pair,
} from "@/lib/api";

/**
 * The company home screen (PRD R21): this company's own pairs and nothing
 * about anyone else's. A pair is one A-to-B relationship: its contracts,
 * the approvers on each side, and the switches that decide what the agent
 * may do on its own inside this pair.
 */
export const Route = createFileRoute("/pairs")({
  head: () => ({
    meta: [
      { title: "Pairs — Finance Agentic Network" },
      {
        name: "description",
        content: "Your company's counterparty pairs: invite, accept, and set what the agent may do inside each one.",
      },
    ],
  }),
  component: PairsPage,
});

function PairsPage() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe });
  const pairs = useQuery({ queryKey: ["pairs"], queryFn: getPairs, enabled: !!me.data });
  const companies = useQuery({ queryKey: ["companies"], queryFn: getCompanies });
  const [error, setError] = useState<string | null>(null);
  const [inviteId, setInviteId] = useState("");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["pairs"] });
  const onError = (e: Error) => setError(e.message || "That didn't work. Try again.");

  const invite = useMutation({ mutationFn: invitePair, onSuccess: () => { setError(null); setInviteId(""); refresh(); }, onError });
  const accept = useMutation({ mutationFn: acceptPair, onSuccess: () => { setError(null); refresh(); }, onError });
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => setPairAutoReply(id, enabled),
    onSuccess: () => { setError(null); refresh(); },
    onError,
  });

  if (me.isLoading || pairs.isLoading || companies.isLoading) {
    return (
      <AppShell>
        <PageHeader eyebrow="Home" title="Pairs" description="Loading…" />
        <Panel><SkeletonRows rows={4} /></Panel>
      </AppShell>
    );
  }

  if (!me.data) {
    return (
      <AppShell>
        <PageHeader eyebrow="Home" title="Pairs" />
        <Panel>
          <EmptyState title="Sign in to see your pairs" body="Pairs belong to a company. Sign in as one of its approvers." />
        </Panel>
      </AppShell>
    );
  }

  const list = pairs.data ?? [];
  const pairedIds = new Set(list.map((p) => p.counterparty_id));
  const candidates = (companies.data ?? []).filter((c) => c.id !== me.data!.company_id && !pairedIds.has(c.id));

  return (
    <AppShell>
      <PageHeader
        eyebrow="Home"
        title="Pairs"
        description="Each pair is one relationship with one counterparty: its own contract, policy, approvers, and switches. Nothing here crosses into another pair."
      />

      {error ? (
        <p role="alert" className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm">
          {error}
        </p>
      ) : null}

      <div className="grid gap-6">
        {list.length === 0 ? (
          <Panel>
            <EmptyState title="No pairs yet" body="Invite a counterparty below. Until they accept, the agent answers them by plain email only." />
          </Panel>
        ) : (
          list.map((pair) => (
            <PairCard
              key={pair.id}
              pair={pair}
              onAccept={() => accept.mutate(pair.id)}
              onToggle={(enabled) => toggle.mutate({ id: pair.id, enabled })}
              busy={accept.isPending || toggle.isPending}
            />
          ))
        )}

        <Panel title="Invite a counterparty" description="Creates a pair in the invited state. It becomes active when their side accepts.">
          <form
            className="flex flex-wrap items-end gap-3 px-5 py-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (inviteId) invite.mutate(inviteId);
            }}
          >
            <div className="min-w-[260px]">
              <Field label="Company">
                <select value={inviteId} onChange={(e) => setInviteId(e.target.value)} className={inputClass}>
                  <option value="">Choose a company</option>
                  {candidates.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </Field>
            </div>
            <Button variant="primary" type="submit" disabled={!inviteId || invite.isPending}>
              Send invite
            </Button>
          </form>
        </Panel>
      </div>
    </AppShell>
  );
}

function PairCard({
  pair,
  onAccept,
  onToggle,
  busy,
}: {
  pair: Pair;
  onAccept: () => void;
  onToggle: (enabled: boolean) => void;
  busy: boolean;
}) {
  const canAccept = pair.status === "invited" && !pair.invited_by_me;
  return (
    <Panel
      title={pair.counterparty}
      description={
        pair.status === "active"
          ? `Active since ${pair.accepted_at ? shortDate(pair.accepted_at) : "—"}`
          : pair.invited_by_me
            ? "Invite sent, waiting for their side. Email-only until then."
            : `Invited by ${pair.invited_by}. Accept to activate the pair.`
      }
      actions={
        <div className="flex items-center gap-2">
          <Badge tone={pair.status === "active" ? "success" : "pending"}>{pair.status}</Badge>
          {canAccept ? (
            <Button size="sm" variant="primary" onClick={onAccept} disabled={busy}>
              Accept
            </Button>
          ) : null}
        </div>
      }
    >
      <div className="grid gap-0 lg:grid-cols-[1fr_320px]">
        <div>
          <Table>
            <thead>
              <tr>
                <Th>Contract</Th>
                <Th>Status</Th>
                <Th>Valid</Th>
                <Th align="right">Max rate</Th>
                <Th align="right">Auto-approve up to</Th>
              </tr>
            </thead>
            <tbody>
              {pair.contracts.length === 0 ? (
                <tr><Td className="text-muted-foreground">No contract on file between these two companies yet.</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td><Td>{""}</Td></tr>
              ) : (
                pair.contracts.map((c, i) => (
                  <tr key={i}>
                    <Td>{c.seller} sells to {c.buyer}</Td>
                    <Td><Badge tone={c.status === "active" ? "success" : "neutral"}>{c.status}</Badge></Td>
                    <Td mono>{shortDate(c.effective_date)} to {shortDate(c.expiry_date)}</Td>
                    <Td align="right" mono>{c.max_rate == null ? "—" : pct(Number(c.max_rate))}</Td>
                    <Td align="right" mono>{c.auto_approve_rate == null ? "—" : pct(Number(c.auto_approve_rate))}</Td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>
        </div>
        <div className="border-t border-border px-5 py-4 lg:border-t-0 lg:border-l">
          <p className="label-mono mb-2">Approvers</p>
          <ul className="space-y-1 text-sm">
            {pair.approvers.map((a, i) => (
              <li key={i}>
                <span className="font-medium">{a.display_name}</span>
                <span className="text-muted-foreground"> · {a.role} · {a.company}</span>
              </li>
            ))}
            {pair.approvers.length === 0 ? <li className="text-muted-foreground">None named yet.</li> : null}
          </ul>

          <p className="label-mono mt-5 mb-2">Agent switches</p>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={pair.auto_reply_status_inquiry}
              disabled={pair.status !== "active" || busy}
              onChange={(e) => onToggle(e.target.checked)}
            />
            <span>
              Send status replies without review
              <span className="block text-2xs text-muted-foreground">
                Off means every reply is a draft. Only "where is my payment" answers are affected. Money never moves on its own.
              </span>
            </span>
          </label>
        </div>
      </div>
    </Panel>
  );
}
