# A day inside company A's finance team, and where the agent sits

Written 2026-09-08 after the question "is this how an AP and AR relationship
actually works, and what should Alice see when she logs in?" This is the
ground truth the screens are built from. Process facts come from
`ap-ar-primer.md` and its sources; the daily rhythm is the standard shape
of a mid-market finance team of two to five people.

## 1. Who Alice is

Kessler Manufacturing is company A. It has a finance team, not an AP
department and an AR department. The same two or three people do both:

- **The AP side of the day.** Kessler buys from suppliers. In our seed data
  that is Aurea Retail (the expired-contract leg). Kessler receives
  supplier invoices, gets asked "where is my payment", and gets asked to
  change bank details. Kessler pays.
- **The AR side of the day.** Kessler sells to customers. In the seed data
  that is Nordwind Logistik. Kessler sends invoices, chases payment, and
  gets discount and deduction claims from Nordwind. Kessler collects.
- **The controller.** Alice, in the demo. Approves anything the policy
  cannot settle, signs off bank changes, and is the one who gets blamed
  when money goes to the wrong account.

So Alice does not think "I am AP" or "I am AR". She thinks "Aurea" and
"Nordwind". Every counterparty is one relationship with both directions in
it. That is the pair.

## 2. What lands in the finance mailbox

One shared mailbox, `invoices@` or `finance@`, read by everyone. On a
normal day at a company with 500 to 5,000 invoices a month, the mail
sorts into these piles. Rough shares are from the AP automation surveys in
the primer; the point is the order, not the decimals.

| Pile | Who sends it | Direction for Kessler | Share of inbound | Our pain |
|---|---|---|---|---|
| Supplier invoices (PDF attached) | Suppliers | AP | 35 to 45% | none, capture is a solved market |
| "Where is my payment?" | Suppliers | AP | 15 to 25% | P1 |
| "Did you receive our invoice?", "please confirm the PO" | Suppliers | AP | 5 to 10% | P1 |
| Remittance advices, "we paid you today" | Customers | AR | 5 to 10% | none, cash application |
| "We are short-paying by X because..." | Customers | AR | 5 to 10% | P2 |
| "Per contract we take the N% discount" | Customers | AR | 2 to 5% | P2 |
| "Our bank details have changed" | Suppliers | AP | under 1% | P3 |
| Statements, reconciliation requests, dunning replies | Both | Both | the rest | not yet |

Two things fall out of the table. First, three of the four biggest piles
are questions, not documents. Nobody's software answers them today; a
person does, by opening the ERP and typing a reply. Second, the one pile
that is under one percent is the one that costs six figures when it goes
wrong.

## 3. A day, hour by hour

What happens now, and what the agent does at the same moment.

**08:30, open the mailbox.** Forty new messages since last night.

Now: skim subject lines, drag invoices to the capture tool, star the
questions to answer later, flag the angry ones.

Agent: every message is already classified and matched to an invoice and
a counterparty. Supplier invoices are passed through untouched to
whatever capture tool the company uses. The questions are answered or
drafted. The two that could not be matched to anything sit in a short
human queue with the reason.

**09:00 to 10:30, supplier questions (AP, pain 1).** Eight "where is my
payment" emails from suppliers.

Now: for each one, find the invoice in the ERP, read its state, write a
reply. Two hours a day of this is the figure in the primer.

Agent: for each one, the resolver has found the invoice from the sender's
domain plus the number or amount. The reply states the row's facts:
received, approved, scheduled, paid with reference, or blocked with a
reason. If the pair with that supplier has the switch on, it was sent
at 08:31. If not, the draft is waiting for one click.

**10:30, one email from a supplier: new IBAN, please update (AP, pain 3).**

Now: if the team is careful, someone phones the supplier at the number
already on file. If the team is busy, someone updates the vendor master
and the next payment run goes to a fraudster.

Agent: the message is classified as a bank change and never applied. It
opens a verification task with the contact already on file, not the one
in the email. Alice sees it in her queue as the one thing that needs a
phone call. If the supplier runs the product, the change would have
arrived signed from their agent instead, and would still wait for Alice.

**11:00 to 12:00, customer claims (AR, pain 2).** Three emails from
customers. One takes a 2% early-payment discount, one short-pays by a
credit they think they are owed, one asks for 12% "as agreed".

Now: pull the contract, check the rate, check whether the discount period
was met, check the budget, decide, reply. If it is over your authority,
forward to the controller and wait a day.

Agent: each claim is extracted, grounded against the contract in the
system of record, risk-scored. The 2% within terms executed on its own.
The 12% is above the contract and was declined with the reason. The
short-pay sits in Alice's queue with the contract clause and the
evidence attached, because it is inside policy but the risk score is in
the middle band.

**14:00, the controller's queue.** Alice opens the approval queue.

Now: a thread of forwarded emails, half of them missing the invoice.

Agent: five items. Each shows the claim, the contract clause it was
checked against, the amount at stake, the risk score, and one approve or
decline button. Nothing she approves can execute unless the policy
function agrees again at that moment and she is on Kessler's side of the
pair.

**16:00, chasing customers (AR).** Kessler's own "where is my payment"
emails go out to Nordwind.

Now: someone writes them by hand from an ageing report.

Agent: not built yet. This is the seller side of pain 1, and it is where
the network starts to pay off: if Nordwind runs the product, Kessler's
agent asks Nordwind's agent, and the answer comes back structured in
seconds. Until then it goes by email and Nordwind's team answers by hand.

**17:00, month end approaching.** The controller wants to know what the
agent did and what it cost.

Agent: the audit page lists every case with one trace each: message,
classification, resolution, decision, reason, model calls, cost. The
agent performance page shows how many messages were handled without a
person, and the daily spend against the cap.

## 4. What this means for Alice's screens

Alice works for one company. Everything on screen is about Kessler and
Kessler's counterparties. Nothing on screen is about how Nordwind and
Aurea deal with each other; that is their pair, not hers.

| Screen | What it shows | What it must not show |
|---|---|---|
| Home (Pairs) | Kessler's counterparties, one card each, with status and switches | Any other company's pairs |
| Queue | Cases waiting for Alice: contested claims, bank changes to verify, unresolved mail | Cases on other companies' sides |
| Invoices | Two lists: what Kessler owes (payables, by supplier) and what Kessler is owed (receivables, by customer) | Invoices between two other companies |
| Executed | Discounts released on Kessler's receivables | Anything else |
| Agent activity | What Kessler's agent did today: answered, drafted, executed, declined, escalated, and spend | Network totals |
| Audit | Traces for Kessler's cases | Other companies' traces |

The "Companies" list with all three names is the old bird's-eye view and
goes. A counterparty page can stay, but it is the pair page: Kessler and
Aurea, the invoices between them in both directions, the contract, the
approvers, the switches.

## 5. What the product is not

To keep the wedge honest, these stay outside:

- Invoice capture and matching. The agent passes supplier invoices through
  to the tool the company already has.
- Payment runs and cash application. Money moves in the ERP, not here.
- Dunning campaigns. The seller side of pain 1 is on the roadmap as an
  agent-to-agent question, not as a reminder scheduler.
- Statements and reconciliation. Real, painful, and a later phase.

The product sits on the mailbox, between the ERP and the counterparties,
and answers the questions that nobody's software answers today.
