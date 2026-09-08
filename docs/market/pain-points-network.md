# Pain points an agentic network can solve

Written 2026-09-07. Companion to `ap-ar-primer.md`. The question here is
narrower than "what hurts in AP and AR": it is "which of those pains exist
*because the two sides don't talk*, and would therefore be solved by
agents on both sides of an invoice sharing a protocol, rather than by one
more single-side automation tool."

Test applied to every pain below: could Coupa, Tipalti, or HighRadius fix
this on their own side alone? If yes, it is not a network pain and we
should not lead with it. If no, it is ours.

Stats are from vendor and analyst blogs found via web search on the date
above. Directional, not audited.

## The pains, ranked by network fit

### 1. "Where is my payment?" (strong network fit)

**What happens.** A supplier's AR team emails or calls the buyer's AP team
to ask about invoice status. The buyer's AP team stops what it is doing to
look it up.

**Size.** AP teams spend roughly two hours of every eight-hour day on
supplier inquiries. Suppliers name following up on invoice status as
their number one pain in the whole payment process. Portals cut inquiry
volume by 70 to 80 percent where they exist.

**Why single-side tools cap out.** The buyer builds a supplier portal.
The supplier now has one portal per customer to log into, each different.
Nobody does it, so they call anyway.

**What a network changes.** The seller's agent asks the buyer's agent
directly, gets a structured answer (received, matched, approved, scheduled
for date X, or blocked because Y), and the human on neither side is
involved. The question and answer are both machine-readable, so the
seller's cash forecast updates automatically.

### 2. Disputes, deductions and short-pays (strong network fit)

**What happens.** Buyer pays less than invoiced, or claims a discount,
credit, or return. Seller must decide if the claim is valid against the
contract, then argue about it by email.

**Size.** 40 percent of B2B payment delays are caused by disputes, not
inability to pay. In-house resolution takes 5 to 15 business days with
documentation, up to 90 days without. Deductions eat 5 to 15 percent of
gross sales in consumer goods. About 40 percent of invalid claims slip
through when tracked in spreadsheets. Manual cost around $6 per claim.

**Why single-side tools cap out.** HighRadius and the deduction tools
automate the seller's investigation, but the evidence (PO, receipt,
contract clause, promotion agreement) is split across both companies.
The seller's agent reconstructs what the buyer already knows.

**What a network changes.** Both agents ground the same claim against the
same contract. This is exactly the current build's discount workflow,
generalised: the buyer's agent proposes with its evidence attached, the
seller's agent validates against the contract terms, and the human only
sees the genuinely contested middle. The 5 to 15 day loop collapses to
minutes for the 60 percent that are clear-cut.

### 3. Vendor bank-detail change fraud (strong network fit)

**What happens.** Attacker hijacks or spoofs a real invoice thread and
sends "updated bank details". AP updates the master record. Next payment
goes to the attacker.

**Size.** Business email compromise losses reached $3.05 billion in 2025,
average $123k per incident, 74 percent of organisations hit. The
recommended control is an out-of-band callback to a known number before
any change. Most teams skip it under time pressure.

**Why single-side tools cap out.** Fraud scoring on the buyer's side can
flag the change but cannot verify it. Verification needs the seller.

**What a network changes.** A bank-detail change becomes a signed message
from the seller's agent under the seller's identity, not an email. The
buyer's agent refuses any change that did not arrive over the network
channel. The callback becomes structural rather than procedural. Every other
pain on this list the network makes faster. This one it makes safer.

### 4. Early-payment discount capture (medium network fit)

**What happens.** Seller offers "2 percent off if paid in 10 days". Buyer's
AP is too slow to approve in time and the discount is lost. Dynamic
discounting programmes make the rate a curve rather than a cliff.

**Size.** Average AP teams capture 58 percent of available discounts;
automated ones 85 to 95 percent. Only 27 percent of companies fully use
the offers they receive.

**Why single-side tools cap out.** Buyer-side automation speeds approval,
but the offer itself is static text on an invoice. Seller does not know
whether the buyer has cash today.

**What a network changes.** Seller's agent offers a rate curve, buyer's
agent evaluates it against its cash position and policy, both sides
settle on a date and rate within pre-approved parameters. Forrester
expects about 20 percent of B2B sellers to face agent-led negotiation
before the end of 2026, so the market is moving here anyway. Note: this
is the pain the current build's "discount request" flow most resembles,
but it is negotiation, not claim validation, and needs treasury data
neither side exposes today.

### 5. Two-sided reconciliation (medium network fit)

**What happens.** Seller's AR ledger says the invoice is open; buyer's AP
never booked it, booked a different amount, or paid a lump sum the seller
cannot apply. Intercompany (subsidiaries of one group) is the worst case
because both books consolidate.

**Size.** Cash application straight-through rates are the headline metric
AR vendors compete on, with 90 percent as the target. Supplier statement
reconciliation is still largely a spreadsheet exercise.

**Why single-side tools cap out.** Each side reconciles its own ledger
against documents received from the other. The documents are the
bottleneck.

**What a network changes.** Both agents hold the same invoice identity from
issue onward. Payment carries the invoice references as data. Cash
application becomes a lookup, not a match. Intercompany is the easiest
place to prove this because both sides are under one roof and can be
mandated to adopt.

### 6. Invoice delivery and format compliance (weak network fit, but the tailwind)

**What happens.** Seller must deliver invoices into each buyer's portal
or in each country's mandated format. Buyer must accept all of them.

**Why it matters for us.** Peppol and the EU mandates are already building
the delivery network. Germany sends from 2027, France from now. This is
not a pain to solve, it is the rail to ride: an agent network that speaks
Peppol BIS on the wire inherits the identity and delivery problem being
solved by regulation.

### Pains that are NOT network pains

Named so we do not drift back to them.

- Manual data entry and OCR quality. Solved on one side, and shrinking as
  e-invoicing makes capture unnecessary.
- GL coding. Buyer-internal.
- Approval routing speed. Buyer-internal, though a network reduces the
  exceptions that clog it.
- Credit decisions. Seller-internal, though network payment history is a
  useful input later.

## What this says about the product

The three strong fits share one shape: **a claim or question crosses the
company boundary, and today it crosses as unstructured email that a human
on the far side must interpret.** Status inquiry, dispute, bank change.
The current build already has the core loop for the second one
(extract, ground, risk-score, propose, human gate). The network version
is that same loop with an agent, not a human, at the far end of the
email.

The cheapest place to start is status inquiry (pain 1). It is read-only,
no money moves, it is safe by construction, and the same integration (an agent that can answer "what
is the state of invoice X" from the ERP) is the foundation for the other
two. Bank-change verification (pain 3) is the highest-value safety story
and the easiest to explain to a CFO. Disputes (pain 2) is where the
existing code lives and where the money is, but it needs both sides to
adopt before it works.

Open questions before any design:

1. Identity. How does the buyer's agent know the seller's agent is the
   seller? Peppol IDs, VAT numbers plus a signed registry, or something
   like A2A Agent Cards. This is the whole game for pain 3.
2. Cold start. Every pain above needs both sides on the network. The
   answer is probably that the agent works single-sided against email
   first (what the current build does) and upgrades to structured
   agent-to-agent when the counterparty is present. Never require both.
3. Where the ERP boundary sits. Every answer to "where is my payment"
   comes from the buyer's ERP. Read access to SAP, NetSuite, Dynamics and
   friends is the integration tax.

## Sources

- https://www.mineraltree.com/blog/supplier-payment-inquiries-how-ap-teams-can-eliminate-interruptions-and-boost-productivity/
- https://www.ispnext.com/en/resources/invoice-status-portal-delivers-value-to-ap-teams
- https://www.apexanalytix.com/solutions/supplier-management/invoice-and-payment-visibility/
- https://www.agentcollect.com/report/2026-b2b-payment-disputes
- https://www.tekst.com/blogs/deduction-management
- https://www.transformance.ai/blog-posts/what-is-deduction-management-software
- https://www.hlhunt.org/uncategorized/short-pays-and-deductions-recovering-the-money-b2b-customers-quietly-withhold/
- https://deepstrike.io/blog/business-email-compromise-statistics
- https://www.gigapay.com/blog/vendor-invoice-fraud-and-bec
- https://hivesecurity.gitlab.io/blog/business-email-compromise-vendor-invoice-fraud/
- https://rossum.ai/blog/early-payment-discounts-in-accounts-payable/
- https://www.apexanalytix.com/solutions/supplier-management/early-payment-programs/
- https://www.kognitos.com/blog/supplier-statement-reconciliation/
- https://invoicedataextraction.com/blog/intercompany-invoice-processing
- https://www.pymnts.com/news/b2b-payments/2026/agentic-b2b-is-here-are-your-contracts-and-invoices-ready/
- https://nevermined.ai/blog/agent-to-agent-payment-statistics
- https://elogic.co/blog/ai-agents-b2b-buying/
