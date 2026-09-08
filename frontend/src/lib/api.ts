/**
 * Fetch client for the FastAPI backend's JSON API (/api/*).
 * See docs/design/lovable/09-frontend-integration-plan.md, Phase 1-4.
 */
import type { AuditRow, Company, ExecutedRow, InvoiceRow, PendingRequest } from "./fan-data";

export const API_BASE = import.meta.env["VITE_API_URL"] ?? "http://localhost:8000";

/** Thrown by apiFetch on a non-2xx response. `status` lets a caller branch on
 * 401/409/etc. without sniffing digits out of `message` — message is the
 * real backend `detail` text and won't reliably contain the status code. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include", // carry the session cookie across the CORS boundary
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    // FastAPI's HTTPException(status, detail) sends {"detail": "..."} — that's
    // the real, specific reason (e.g. "Scribo doesn't support invoices from
    // ES yet"). Surface it instead of a bare status code, every caller's
    // error UI reads from this message.
    let detail: string | undefined;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // body wasn't JSON (or was empty) — fall through to the generic message
    }
    throw new ApiError(detail ?? `${init?.method ?? "GET"} ${path} failed: ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export interface Approver {
  username: string;
  display_name: string;
  role: string;
  company_id: string;
  pair_id: string | null;
}

/** GET /api/pairs: the signed-in company's own pairs (PRD R21). */
export interface PairContract {
  seller: string;
  buyer: string;
  status: string;
  effective_date: string;
  expiry_date: string;
  max_rate: number | null;
  auto_approve_rate: number | null;
  period_budget: number | null;
}

export interface PairApprover {
  display_name: string;
  role: string;
  company: string;
}

export interface Pair {
  id: string;
  status: "invited" | "active";
  accepted_at: string | null;
  auto_reply_status_inquiry: boolean;
  invited_by: string;
  invited_by_me: boolean;
  counterparty_id: string;
  counterparty: string;
  contracts: PairContract[];
  approvers: PairApprover[];
}

export interface NetworkCost {
  workflows: number;
  calls: number;
  total_cost_usd: number;
}

export interface AuditResponse {
  workflows: AuditRow[];
  network_cost: NetworkCost;
}

export interface ModelUsageRow {
  model: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface DecisionRow {
  invoice_number: string;
  seller_name: string;
  buyer_name: string;
  claimed_rate: number;
  approved_rate: number | null;
  approved_by: string | null;
  decided_at: string;
  outcome: "auto_declined" | "auto_executed" | "human_decided";
}

export interface AutomationResponse {
  decided_or_pending: {
    total: number;
    auto_declined: number;
    auto_executed: number;
    human_decided: number;
    still_pending: number;
  };
  weekly: { week: string; auto_declined: number; auto_executed: number; human_decided: number }[];
  models: ModelUsageRow[];
  network_cost: NetworkCost;
  decisions: DecisionRow[];
}

/**
 * Shape of GET /api/companies/{id} — the company detail page context.
 * Nested query results not consumed by the frontend yet are left as
 * `unknown[]`, honest about what this client actually reads today rather
 * than guessing at fields nothing renders.
 */
export interface CompanyDetail {
  company: { id: string; name: string; email_domain: string };
  invoices: unknown[];
  invoices_as_seller_count: number;
  invoices_as_buyer: unknown[];
  other_companies: Company[];
  pending: unknown[];
  auto_rejected: unknown[];
  executed: unknown[];
  scribo_sender_email: string;
  scribo_seller_supported: boolean;
}

export const getCompanies = () => apiFetch<Company[]>("/api/companies");
export const getCompany = (id: string) => apiFetch<CompanyDetail>(`/api/companies/${id}`);
export const getProposals = () => apiFetch<PendingRequest[]>("/api/proposals");
export const getInvoices = () => apiFetch<InvoiceRow[]>("/api/invoices");
export const getExecuted = () => apiFetch<ExecutedRow[]>("/api/executed");
export const getAudit = () => apiFetch<AuditResponse>("/api/audit");
export const getAutomation = () => apiFetch<AutomationResponse>("/api/automation?days=30");
export const getMe = () => apiFetch<Approver | null>("/api/me");
export const getPairs = () => apiFetch<Pair[]>("/api/pairs");
export const invitePair = (counterparty_company_id: string) =>
  apiFetch<{ ok: boolean; pair_id: string }>("/api/pairs", {
    method: "POST",
    body: JSON.stringify({ counterparty_company_id }),
  });
export const acceptPair = (id: string) =>
  apiFetch<{ ok: boolean }>(`/api/pairs/${id}/accept`, { method: "POST" });
export const setPairAutoReply = (id: string, enabled: boolean) =>
  apiFetch<{ ok: boolean }>(`/api/pairs/${id}/settings`, {
    method: "POST",
    body: JSON.stringify({ auto_reply_status_inquiry: enabled }),
  });

// --- Mutations (Phase 2 backend routes, wired here in Phase 5) -----------

export interface InvoiceRequestBody {
  buyer_company_id: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate?: string;
  due_date: string;
}

export interface DiscountRequestBody {
  invoice_id: string;
  message: string;
}

export const approveProposal = (id: string) =>
  apiFetch<{ ok: boolean }>(`/api/proposals/${id}/approve`, { method: "POST" });

export const declineProposal = (id: string) =>
  apiFetch<{ ok: boolean; proposal_id: string; status: string }>(
    `/api/proposals/${id}/decline`,
    { method: "POST" },
  );

export const generateInvoice = (companyId: string, body: InvoiceRequestBody) =>
  apiFetch<{ ok: boolean; invoice_number: string }>(`/api/companies/${companyId}/invoice`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const submitRequest = (companyId: string, body: DiscountRequestBody) =>
  apiFetch<{ workflow_id: string; outcome: string }>(`/api/companies/${companyId}/request`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const login = (username: string, password: string) =>
  apiFetch<Approver>("/api/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });

export const logout = () => apiFetch<{ ok: boolean }>("/api/logout", { method: "POST" });

// --- Live events (Phase 3 SSE endpoint) -----------------------------------

export interface LiveEvent {
  id?: number;
  workflow_id: string;
  event_type: string;
  payload?: Record<string, unknown>;
  occurred_at?: string;
}

/**
 * Opens a manual fetch-stream reader against /api/events/stream, not
 * EventSource: native EventSource has no way to send `credentials:
 * 'include'` cross-origin (its constructor takes no init options), and this
 * app's auth is a session cookie, so EventSource would connect unauthenticated.
 */
export function subscribeToLiveEvents(onEvent: (event: LiveEvent) => void): () => void {
  const controller = new AbortController();

  (async () => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/events/stream`, {
        credentials: "include",
        signal: controller.signal,
      });
    } catch {
      return; // aborted before connecting, or network error — nothing to clean up
    }
    if (!res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";
        for (const chunk of lines) {
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          try {
            onEvent(JSON.parse(line.slice("data: ".length)) as LiveEvent);
          } catch {
            // malformed event line — skip it, don't kill the stream
          }
        }
      }
    } catch {
      // stream aborted (unsubscribe) or connection dropped — nothing more to do
    }
  })();

  return () => controller.abort();
}
