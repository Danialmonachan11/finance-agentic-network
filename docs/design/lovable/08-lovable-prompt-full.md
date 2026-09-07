Design the full UI for an internal finance-ops tool called the Finance Agentic Network. This is a complete, page-by-page brief, not a single-screen ask, since the goal this round is a consistent design across the whole app.

## What this is

A network of companies invoices each other. Every company is a seller on some invoices and a buyer on others, there's no fixed "us vs customers" setup. An AI agent pipeline reviews discount requests a buyer sends a seller: it auto-approves the safe ones, auto-declines the obviously bad ones, and routes anything genuinely uncertain to a human. The human reviewer signs in once and can act on behalf of whichever company's data they're looking at, they aren't locked to one company.

## Who uses it and their one real task

A finance-ops person, signed in, reviewing pending discount requests and deciding: approve or decline. Everything else in the app (browsing invoices, seeing history, issuing a new invoice, requesting a discount as a buyer) is secondary to that one task.

## Every screen, what it shows, and its real field names

Give Lovable the exact field names below so it doesn't invent placeholder data that doesn't match anything real.

**1. Companies (network overview).** A card per company: name, invoices issued, invoices received, an "N awaiting review" badge if the company has pending requests as a seller, and two money figures: `receivable` (open invoices they're owed, not yet paid) and `payable` (open invoices they owe). Example:
```
{ "name": "Kessler Manufacturing", "invoices_as_seller": 3, "invoices_as_buyer": 1,
  "pending_as_seller": 1, "receivable": 15750.00, "payable": 5450.00 }
```

**2. Approval queue (the primary screen).** A master-detail view: a compact list of pending requests, and a detail panel for whichever one is selected, showing full reasoning, plus Approve and Decline actions. Example of one item:
```
{ "invoice_number": "INV-2001", "seller_name": "Nordwind Logistik GmbH", "buyer_name": "Aurea Retail S.A.",
  "claimed_rate": 0.10, "approval_level": "manager", "amount": 1500.00, "due_date": "2026-09-04",
  "contract_status": "active", "risk_score": 0.61, "grounding_reason": "Order volume up 22% this quarter...",
  "risk_reason": null, "workflow_id": "..." }
```
`risk_score` is 0.00-1.00, 0 is safest, 1 is riskiest, always show that scale next to the number, don't show a raw float alone. `approval_level` is one of `auto`, `manager`, `cfo`, show it as a badge. Approve and Decline are both real actions here, side by side, Decline is not a lesser or hidden option.

**3. A single company's page.** Combines: a stat strip (invoices issued/received, awaiting review, executed), the same kind of pending-request list scoped to this one company, an invoice tracker table (invoice number, role as issued/received, counterparty, amount, discount status, whether it was emailed), and two occasional secondary forms tucked away, not competing for space with the review queue: generate-and-send a new invoice, and request a discount as a buyer on an invoice this company received.

**4. Invoices (network-wide document list).** Invoice number, seller, buyer, amount, contract status, and whether a real PDF document exists on file (most seeded rows don't, only real generated ones do, show that honestly, don't fake a document icon for rows with no PDF).

**5. Executed (history).** Invoice, seller, buyer, claimed rate, approved rate, approval level, who approved it, when, and whether it was decided by a human or automatically (`path: "human"` vs `path: "auto"`), keep that distinction visible, don't collapse it into one column.

**6. Raw audit log (technical view, secondary nav item).** One row per pipeline step: workflow id, step name, agent, status, reason, timestamp. Also shows network-wide LLM spend (workflows, calls, real dollar cost). This is the "how the AI actually decided" view for anyone who wants to check the pipeline's work, not the primary screen, style it as clearly secondary/technical.

**7. Login.** Username, password, nothing fancy. Two seeded demo accounts exist (a manager and a cfo role), the login screen can note that demo accounts exist without hardcoding the real credentials in the UI copy.

## What each user-facing string needs to avoid

The current app was audited and flagged for unglossed jargon. Don't repeat these mistakes:
- Any raw score or numeric scale (`risk_score`, confidence, etc.) needs its range stated inline, not just a bare number.
- Don't show a raw backend status string (like `auto_rejected` or `escalated_no_match`) directly to a user, translate it to a short human phrase.
- The technical/audit-log view should read as clearly secondary to the approval queue, both in nav position and visual weight.

## What NOT to soften or reword

Some copy in the current app is deliberately, factually honest, keep that spirit if you write new copy in the same spots:
- Claims like "a real generated PDF on disk" or "real OpenRouter-reported cost, not an estimate" exist because most of this data is genuinely mixed (some real, some seeded demo rows), and the app says so plainly instead of hiding the difference. Don't write copy that implies everything is uniformly real or uniformly polished, that would be less honest than what's there now, not more polished.

## Visual direction: what we already committed to

An earlier Lovable-built reference for this same app set the direction we already adopted and shipped: dark near-black sidebar/nav chrome, warm cream content background, near-black ink text (not pure black), monospace type for labels, numbers, and badges, and one orange/rust accent color used for primary actions and emphasis, not spread across everything. These are the actual token values currently live in the app's CSS:
```
--token-bg-sidebar: #16171c;
--token-bg-page: #FAF8F0;
--token-bg-card: #FFFFFF;
--token-ink: #1C1B18;
--token-ink-soft: #6B6858;
--token-accent: #D9743C;
--token-accent-hover: #B45A28;
```
Plus a preserved three-color status system for pending/success/danger states (amber `#fff3cd`/`#7a5b00`, green `#d1e7dd`/`#0f5132`, red `#f8d7da`/`#842029`) that already passes accessibility contrast checks, keep that triad, don't invent new status colors.

Use these as your starting point and push the whole system further, consistent spacing scale, a real type scale, proper empty/loading/focus/disabled states for every interactive element (the current app was flagged for having none of these designed, that's the single biggest gap to close). This is a data-dense internal tool, not a marketing page, restraint over decoration throughout.

## One structural thing to get right this time

The approval queue needs to be reachable as its own destination, not buried in a scroll position on another page, with a live count visible in navigation. That's the single highest-impact fix from the last audit, don't lose it in a redesign.

## What this hands back, and what it doesn't

This produces a separate reference build (Lovable's own React/Vite stack). The real app is server-rendered Python (FastAPI + Jinja2 templates), so nothing gets pasted in directly, the layout, spacing, and interaction decisions get manually ported back into the real templates afterward. Don't design around a component library or state-management pattern that only makes sense in a client-rendered SPA, keep every screen achievable as a page render with plain forms and links, since that's what it has to become.
