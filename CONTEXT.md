# Finance Agentic Network

A network of companies invoicing each other, with AI agents handling
discount-request triage, grounding, and approval on both sides. Not a
single-operator AP/AR tool — any Company can be a seller on one deal and a
buyer on another.

## Language

**Company**:
A party in the network. Can be seller on one Contract and buyer on
another — there's no fixed "us" the network revolves around.
_Avoid_: Customer, Client, Vendor. (`Organization` was considered as the
more precise term — a Company here need not be an incorporated entity —
but rejected: the schema, code, and templates already use `company`
throughout, and renaming everything wasn't worth it for a demo project.
If this ever stops being a demo, that rename is still on the table.)

**Contract**:
An agreement between one seller Company and one buyer Company, governing
the DiscountPolicy for Invoices between them.
_Avoid_: Agreement, deal.

**DiscountPolicy**:
The rate ceiling, auto-approval threshold, and period budget attached to
one Contract.
_Avoid_: Terms, discount terms.

**Invoice**:
A bill from a seller Company to a buyer Company, referencing a Contract.
_Avoid_: Bill.

**DiscountProposal**:
One specific claimed rate on one Invoice, moving through triage,
grounding, risk scoring, and approval. Distinct from the Workflow that
produced it — a Company can end up with more than one DiscountProposal on
the same Invoice over time (each a separate attempt/request).
_Avoid_: Request, discount request (fine in casual conversation, but the
schema and code both say DiscountProposal — use that in anything written
down).

**Workflow**:
One run of the orchestration graph, from an inbound message to a terminal
outcome (proposed or escalated). Identified by `workflow_id`.
_Avoid_: Run, session (session is already an overloaded word elsewhere).

**Grounding**:
Verifying a claim (e.g. a claimed discount rate) against Postgres — the
system of record — rather than trusting what an LLM extracted from free
text. The claim is still the *input* being checked, not discarded in
favor of some other stored number.
_Avoid_: Validation (too generic — grounding specifically means checking
against transactional truth, not just schema-checking a shape).

**Approval level**:
`auto` / `manager` / `cfo` — derived from a claimed rate against a
DiscountPolicy, never asserted by an email, a claim, or an agent. Who is
authorized to approve a DiscountProposal at a given level is a separate
concept (see Approver role).
_Avoid_: Tier (used for autonomy tiers in docs/reference/architecture.md — a
related but distinct concept; don't conflate the two).

**Approver role**:
The rank (`auto` < `manager` < `cfo`) of whoever is executing a
DiscountProposal. Must be at least as senior as the DiscountProposal's
Approval level, checked at execution time — never inferred from anything
in the inbound message.
_Avoid_: Permission (this project has no user/permission system; role is
just a parameter passed to `execute_discount`).
