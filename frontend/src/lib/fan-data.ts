/**
 * Types and formatting helpers for the Finance Agentic Network frontend.
 * Field names mirror the real FastAPI /api/* payloads — see
 * frontend/src/lib/api.ts for the live fetch functions that
 * now back every route (docs/design/lovable/09-frontend-integration-plan.md,
 * Phase 4).
 *
 * Two fields are deliberately absent from these types because they don't
 * exist server-side ("Known gaps from Phase 1" in that doc):
 * InvoiceRow.discount_status/emailed, and ExecutedRow.path (every
 * real executed row is a human decision, so the UI just says "human").
 * InvoiceRow.has_pdf DOES exist server-side (list_all_invoices, main.py) —
 * it's real, not a mock.
 * Company uses the real `id` (UUID), not a slug — the backend has no slug
 * concept.
 */

export type ApprovalLevel = "auto" | "manager" | "cfo";
export type ContractStatus = "active" | "expired" | "none";

export interface Company {
  id: string;
  name: string;
  invoices_as_seller: number;
  invoices_as_buyer: number;
  pending_as_seller: number;
  receivable: number;
  payable: number;
}

export interface PendingRequest {
  proposal_id: string; // real identity for approve/decline — workflow_id is null for non-pipeline proposals
  workflow_id: string | null;
  invoice_number: string;
  seller_name: string;
  buyer_name: string;
  claimed_rate: number;
  approval_level: ApprovalLevel;
  amount: number;
  due_date: string;
  contract_status: ContractStatus | null; // LEFT JOIN contract — null when the invoice has no contract row at all
  risk_score: number | null; // nullable column (schema.sql) — not every proposal has been risk-scored
  grounding_reason: string | null; // null for seeded proposals — no workflow_id means the agent pipeline never ran
  risk_reason: string | null;
  requested_at: string;
}

export interface InvoiceRow {
  invoice_id: string; // present on list_all_invoices() rows, needed to submit a discount request
  invoice_number: string;
  seller_name: string;
  buyer_name: string;
  amount: number;
  contract_status: ContractStatus | null; // LEFT JOIN contract — null when the invoice has no contract row at all
  has_pdf: boolean; // real generated invoices have a PDF on disk; seeded rows don't
  direction: "payable" | "receivable"; // relative to the signed-in company
}

export interface ExecutedRow {
  invoice_number: string;
  seller_name: string;
  buyer_name: string;
  claimed_rate: number;
  approved_rate: number;
  approval_level: ApprovalLevel;
  approved_by: string;
  decided_at: string;
}

export interface AuditRow {
  workflow_id: string;
  step: string;
  agent: string;
  status: string;
  reason: string;
  timestamp: string;
}

/** Backend status strings are never shown raw — translate every one here. */
const STATUS_PHRASES: Record<string, string> = {
  ok: "Step completed",
  pending: "Awaiting review",
  approved: "Approved",
  declined: "Declined",
  none: "No request",
  auto_approved: "Approved automatically",
  auto_executed: "Executed automatically",
  auto_declined: "Declined automatically",
  auto_rejected: "Declined automatically",
  human_decided: "Decided by a person",
  escalated_no_match: "Sent to a human — no contract match",
  escalated_cfo: "Sent to a human — CFO sign-off needed",
  no_contract: "No contract on file",
  active: "Contract active",
  expired: "Contract expired",
};

export function humanStatus(status: string): string {
  return STATUS_PHRASES[status] ?? status.replace(/_/g, " ");
}

export function statusTone(status: string): "pending" | "success" | "danger" | "neutral" {
  if (["approved", "auto_approved", "auto_executed", "ok", "active"].includes(status)) return "success";
  if (["declined", "auto_rejected", "auto_declined", "expired"].includes(status)) return "danger";
  if (["pending", "escalated_no_match", "escalated_cfo", "no_contract"].includes(status))
    return "pending";
  return "neutral";
}

export function money(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  });
}

export function pct(rate: number): string {
  return `${(rate * 100).toFixed(rate * 100 % 1 === 0 ? 0 : 1)}%`;
}

export function shortDate(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function companyIdByName(companies: Company[], name: string): string | undefined {
  return companies.find((c) => c.name === name)?.id;
}

/* ------------------------------------------------------------------------ */
/* Documents — only rows that really have a generated PDF appear here.       */
/* ------------------------------------------------------------------------ */

/* ------------------------------------------------------------------------ */
/* Automation & cost, and per-model usage now come from GET /api/automation  */
/* — see frontend/src/lib/api.ts's getAutomation() and          */
/* AutomationResponse. The hardcoded automation/models/evals fixtures that   */
/* used to live here are gone (docs/design/lovable/10-agents-page-plan.md,  */
/* Phase 2): p50/p95 latency, agreement_rate, and the evals suite have no    */
/* backing data anywhere in this codebase and were dropped rather than       */
/* faked.                                                                    */
/* ------------------------------------------------------------------------ */
