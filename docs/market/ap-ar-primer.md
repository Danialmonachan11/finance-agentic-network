# AP and AR: the market we are building for

Written 2026-09-07 as the "fresh start" primer. Purpose: understand the
process, the pain, and who already sells into it before designing anything.
Statistics below come from vendor blogs and analyst summaries found via
web search on that date. Treat them as directional, not audited.

## 1. What AP and AR are

Every B2B trade has two sides of the same invoice.

- **Accounts receivable (AR)** is the seller's side. "We sold something,
  now we need to get paid." Owned by the seller's finance team, often
  called order-to-cash (O2C).
- **Accounts payable (AP)** is the buyer's side. "We received an invoice,
  now we need to check it and pay it." Owned by the buyer's finance team,
  often called procure-to-pay (P2P).

The same document is one company's AR and another company's AP. That is
why a network model (any company can be on either side) is the correct
shape, and why most vendors still only sell one side.

## 2. The AP process, step by step (buyer side)

1. **Purchase order (PO).** Buyer raises a PO, sometimes not (non-PO spend
   is the messy half of AP).
2. **Invoice receipt.** Arrives by email PDF, paper, supplier portal,
   EDI, or structured e-invoice (XRechnung, Factur-X, Peppol BIS).
3. **Capture.** OCR or vision model turns the document into fields:
   supplier, invoice number, date, line items, tax, total, bank details.
4. **Validation.** Is this supplier known? Is the VAT ID valid? Duplicate
   invoice number? Bank account changed since last time (fraud signal)?
5. **Matching.** Two-way (invoice vs PO) or three-way (invoice vs PO vs
   goods receipt). Tolerances decide what counts as a match.
6. **Coding.** Assign GL account, cost centre, project, tax code.
7. **Exception handling.** Anything that failed steps 4 to 6 goes to a
   human queue. This is where the hours go.
8. **Approval routing.** Based on amount, department, and policy.
   Approvers are slow; this is the main cause of the 9-day cycle time.
9. **Payment.** Batch payment run, early-payment discount capture if the
   terms allow it, remittance advice sent to supplier.
10. **Posting and close.** Journal entries into the ERP, accruals for
    unposted invoices at month end.

## 3. The AR process, step by step (seller side)

1. **Credit decision.** Should we extend terms to this buyer, and how much.
2. **Invoicing.** Generate and deliver the invoice in whatever format the
   buyer's AP portal or country mandate demands.
3. **Dunning and collections.** Reminders before and after due date,
   escalating tone, calls for the big ones.
4. **Dispute and deduction handling.** Buyer short-pays or asks for a
   discount, credit, or correction. Someone must decide whether the claim
   is valid against the contract.
5. **Cash application.** Money lands in the bank. Match it to open
   invoices. Remittances arrive as PDFs, emails, portal downloads, or
   nothing at all. Partial payments and lump sums across many invoices
   are normal.
6. **Forecasting and reporting.** Days sales outstanding (DSO), ageing
   buckets, expected cash by week.

## 4. Where the pain is

**AP pain, ranked by what practitioners report:**

| Pain | Evidence |
|---|---|
| Manual data entry | Top pain point for 37% of AP staff; 68% still key invoices into the ERP by hand |
| Exceptions | Became the number one challenge in Ardent Partners' 2025 study for the first time in 19 years |
| Slow approvals | Average 9.2 days per invoice; 63% of teams spend over 10 hours a week on processing |
| Cost per invoice | Roughly $9 to $16 manual, $2 to $3 best-in-class automated |
| Errors and fraud | About 39% of invoices carry at least one error; changed bank details is the classic fraud shape |
| Late payment | Over half of US invoices are paid after due date, which is the AR side's pain mirrored |

**AR pain:**

| Pain | Evidence |
|---|---|
| Cash application | Matching unstructured remittances to open invoices; vendors advertise 90%+ straight-through as the target |
| Collections | Manual follow-up, wrong contact, invoice rejected by buyer portal |
| Deductions and disputes | Deciding claim validity against contract terms, slow and inconsistent |
| DSO | HighRadius claims up to 68% DSO reduction with agentic AI on its own customer base |
| Fragmented data | ERP, bank, CRM, email all hold part of the truth |

The common thread on both sides is the same: a claim arrives as free text
or a messy document, someone must check it against a system of record and
a policy, then route a decision. That is exactly the grounded-decision
loop the current build already has. The market pain is not the decision
logic. It is the volume of exceptions and the human time spent on them.

## 5. Who sells into this today

**AP side**

| Vendor | Position |
|---|---|
| Coupa | Enterprise procurement plus AP, chosen to align buying and paying |
| Basware | Global e-invoicing network, compliance across country mandates |
| Medius | Mid-market and enterprise, complex approval workflows, high volume |
| Tipalti | Global payouts, multi-entity, 1k to 5k invoices a month sweet spot |
| Bill.com | SMB, US-centric, AP plus payments |
| Stampli | Invoice-centric collaboration, AI coding |
| Vic.ai | "Autonomous AP", front-of-process capture and coding |
| Ramp | Cards and spend, now pitching AI agents for coding and fraud |

**AR side**

| Vendor | Position |
|---|---|
| HighRadius | Enterprise, 18+ named AI agents across collections, credit, cash application |
| Billtrust | B2B billing and delivery into buyer AP portals via its payments network |
| Tesorio | "Agentic financial operations", collections plus cash app plus forecasting; roughly $25k to $200k a year |
| Versapay | Collaborative AR, buyer and seller share a portal |
| BlackLine | Close and reconciliation, now with AR agents |

**Pattern to note.** Every one of these rewrote its homepage around
"agents" in 2025 and 2026. Independent reviewers say most are LLM layers
on existing rules engines. The honest test is how they behave on messy
input: no invoice number, partial payment, credit memo applied.

**Nobody sells the network.** AP vendors serve buyers, AR vendors serve
sellers. Billtrust and Versapay get closest with buyer-facing portals, but
the relationship is still one seller to many buyers. A model where every
participant is both is not on the market. That is either the gap or the
reason nobody has done it. Worth finding out which.

## 6. Regulation that changes the game

E-invoicing mandates are replacing PDFs with structured XML across Europe.

- Germany: must receive e-invoices since January 2025; must send from
  2027 (large companies) and 2028 (all).
- France: receive from September 2026; large companies send from the same
  date; SMEs from September 2027.
- Belgium, Nordics, and Germany use Peppol. France uses accredited
  platforms (PDPs) aligned to it.
- EU ViDA: near real-time digital reporting on cross-border B2B by 2030.

Consequence for a product: capture (OCR, vision) becomes less important
over the next three years, because invoices arrive as data. Matching,
exception handling, policy decisions, and cross-company communication
become the whole job. That favours the parts of the current build that
are already strong and de-emphasises document extraction.

## 7. What this means for a fresh start

Questions to answer before designing:

1. Which side pays? Buyers (AP) have the bigger software budgets and the
   clearer ROI story (cost per invoice). Sellers (AR) have the sharper
   pain (cash) but tighter budgets.
2. Which company size? SMB (Bill.com territory) versus mid-market
   (Medius, Tipalti) versus enterprise (Coupa, HighRadius). Each has a
   different buyer, integration burden, and sales motion.
3. Which exception type to own first? Discount and deduction claims are
   one narrow, well-defined exception with a contract to ground against.
   Bank-detail changes (fraud) and PO mismatches are the other two big
   ones.
4. Is the network real? Two companies both running the same platform is
   a chicken-and-egg problem every marketplace has. Peppol solved it by
   being a protocol, not a product. There may be a lesson there.

## Sources

- https://parseur.com/blog/ai-invoice-processing-benchmarks
- https://www.docuclipper.com/blog/accounts-payable-statistics/
- https://www.lido.app/blog/invoice-processing-cost-benchmarks
- https://www.vic.ai/blog/manual-data-entry-still-tops-ap-pain-points
- https://www.vic.ai/blog/top-5-challenges-ap-teams-face
- https://www.tesorio.com/blog/best-accounts-receivable-ar-automation-solutions-for-2025
- https://www.highradius.com/resources/Blog/top-accounts-receivable-tools/
- https://www.kognitos.com/blog/how-to-reduce-dso-with-ai-2026-playbook/
- https://www.medius.com/blog/top-ap-automation-software-compared-features-fit-and-tradeoffs/
- https://www.zamp.ai/blogs/best-ap-automation-software-in-2025-tipalti-vs-coupa-vs-bill-com-vs-ai-agents
- https://www.kenfromfinance.com/blog/ap-automation-pricing-comparison
- https://www.techno-pulse.com/2026/06/best-ai-accounts-receivable-automation.html
- https://www.lunos.ai/blog/highradius-vs-billtrust
- https://www.fonoa.com/resources/blog/peppol-adoption-europe-2026-mandates-vida
- https://www.spscommerce.com/community/articles/e-invoicing-mandates-in-europe-the-2026-business-guide
- https://www.invoicenavigator.eu/deadlines
