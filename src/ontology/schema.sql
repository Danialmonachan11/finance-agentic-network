-- Postgres schema: transactional truth for the finance-ops demo.
-- Network model (rewritten 2026-08-24 — see BRAIN.md decisions log): any
-- company can be a seller on one contract/invoice and a buyer on another.
-- There is no fixed "us" — that was the bug in the original design, which
-- baked in a single-company point of view (a `customer` table implying
-- everyone else always owes a fixed operator money). This is a network,
-- not a hub-and-spoke.

CREATE TABLE company (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    email_domain    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE contract (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_company_id  UUID NOT NULL REFERENCES company(id),
    buyer_company_id   UUID NOT NULL REFERENCES company(id),
    effective_date      DATE NOT NULL,
    expiry_date          DATE NOT NULL,
    status               TEXT NOT NULL CHECK (status IN ('active', 'expired', 'terminated')),
    CHECK (seller_company_id != buyer_company_id)
);

CREATE TABLE discount_policy (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id         UUID NOT NULL REFERENCES contract(id),
    max_rate            NUMERIC(5,4) NOT NULL,          -- e.g. 0.10 = 10%
    period_budget       NUMERIC(12,2) NOT NULL,          -- max discount $ per period
    period_days         INT NOT NULL DEFAULT 90,
    auto_approve_rate   NUMERIC(5,4) NOT NULL DEFAULT 0.05  -- <= this: Tier 3 autonomous
);

CREATE TABLE invoice (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_company_id  UUID NOT NULL REFERENCES company(id),  -- who issued it, who a discount request goes TO
    buyer_company_id   UUID NOT NULL REFERENCES company(id),  -- who owes the money, who CAN ask for a discount
    contract_id         UUID REFERENCES contract(id),
    invoice_number      TEXT NOT NULL UNIQUE,
    amount               NUMERIC(12,2) NOT NULL,
    currency              TEXT NOT NULL DEFAULT 'EUR',
    issued_date          DATE NOT NULL,
    due_date              DATE NOT NULL,
    status                TEXT NOT NULL DEFAULT 'received'
                        CHECK (status IN ('received', 'validated', 'disputed', 'paid')),
    source_email_id     TEXT,                                -- Gmail message id, for traceability
    raw_extraction       JSONB,                               -- what the extraction agent produced
    CHECK (seller_company_id != buyer_company_id)
);

CREATE TABLE invoice_line (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id      UUID NOT NULL REFERENCES invoice(id),
    description     TEXT NOT NULL,
    quantity        NUMERIC(10,2) NOT NULL,
    unit_price      NUMERIC(12,2) NOT NULL,
    line_total      NUMERIC(12,2) NOT NULL
);

CREATE TABLE discount_proposal (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id          UUID NOT NULL REFERENCES invoice(id),
    workflow_id         UUID,               -- links to audit_log/workflow_event for this proposal's full trace
    claimed_rate        NUMERIC(5,4) NOT NULL,
    approved_rate       NUMERIC(5,4),
    approval_level      TEXT NOT NULL CHECK (approval_level IN ('auto', 'manager', 'cfo')),
    status              TEXT NOT NULL DEFAULT 'proposed'
                        CHECK (status IN ('proposed', 'approved', 'rejected', 'executed')),
    risk_score          NUMERIC(3,2),                    -- 0.00-1.00 from Risk agent
    justification       TEXT,                            -- claim text extracted from email
    approved_by         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at          TIMESTAMPTZ
);

-- Append-only. Never UPDATE or DELETE a row here — this is the audit trail
-- from §3.5 of the architecture doc.
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    workflow_id     UUID NOT NULL,
    step            TEXT NOT NULL,
    agent           TEXT NOT NULL,
    model           TEXT,
    tool_calls      JSONB,
    decision        TEXT,
    reason          TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Event log (docs/architecture.md §3.2 event-driven handoffs): durable
-- record of every workflow-level event, paired with a live Postgres NOTIFY
-- on the same channel for real-time consumers (src/orchestration/events.py).
-- NOTIFY alone is ephemeral (only delivered to connections listening at
-- that instant); this table is what makes the event stream replayable —
-- a consumer that was offline can catch up by querying instead of losing
-- the notification.
CREATE TABLE workflow_event (
    id              BIGSERIAL PRIMARY KEY,
    workflow_id     UUID NOT NULL,
    event_type      TEXT NOT NULL,      -- e.g. 'workflow.proposed', 'workflow.escalated', 'workflow.executed'
    payload         JSONB NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflow_event_type ON workflow_event(event_type);

-- AI FinOps (docs/architecture.md §3.11): cost per LLM call. Closed after
-- comparing this build against a reference architecture that named "Cost
-- Tracker" as its own component — see src/guardrails/cost_tracker.py.
CREATE TABLE llm_call_cost (
    id                  BIGSERIAL PRIMARY KEY,
    workflow_id         UUID NOT NULL,
    step                TEXT NOT NULL,
    model               TEXT NOT NULL,
    input_tokens        INT NOT NULL,
    output_tokens       INT NOT NULL,
    estimated_cost_usd  NUMERIC(12,8) NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_call_cost_workflow ON llm_call_cost(workflow_id);

-- Server-verified approver identity (docs/BRAIN.md security audit,
-- 2026-08-25): closes the "approver_role is just a form field" finding.
-- execute_discount now reads role/display_name from the session, which was
-- set here at login — never from client-supplied form input.
CREATE TABLE approver (
    username        TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,      -- pbkdf2_hmac, salted (see src/api/auth.py)
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('manager', 'cfo'))
);

-- Intake idempotency (docs/architecture.md §3.2): tracks which Gmail
-- messages have already been turned into a workflow run, so a re-poll
-- doesn't reprocess one and create a duplicate proposal/draft. Deliberately
-- NOT implemented via Gmail's own UNREAD label + gmail.modify scope — that
-- scope also grants send capability, which would widen the OAuth grant
-- beyond what src/ingestion/gmail_oauth.py's read+compose-only design
-- intends (see BRAIN.md decisions log, 2026-08-24).
CREATE TABLE processed_email (
    message_id      TEXT PRIMARY KEY,
    workflow_id     UUID NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_invoice_seller ON invoice(seller_company_id);
CREATE INDEX idx_invoice_buyer ON invoice(buyer_company_id);
CREATE INDEX idx_contract_seller ON contract(seller_company_id);
CREATE INDEX idx_contract_buyer ON contract(buyer_company_id);
CREATE INDEX idx_discount_proposal_invoice ON discount_proposal(invoice_id);
CREATE INDEX idx_audit_log_workflow ON audit_log(workflow_id);
