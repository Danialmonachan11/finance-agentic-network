Design the main screen of an internal finance-ops tool called the Finance Agentic Network. A network of companies invoices each other. Every company is a seller on some invoices and a buyer on others, there's no fixed "us vs customers" setup. An AI agent pipeline reviews discount requests, auto-approves or auto-declines the low-risk ones, and routes anything uncertain to a human.

The user is a finance-ops person signed in as one company. Their job on this screen has three parts, in priority order:

1. Review discount requests other companies sent them. This is the primary task. Each request shows an invoice number, the amount requested, who's asking, why the AI flagged it for human review, and an approve action.
2. See the invoice tracker: every invoice touching this company, its discount status (executed, awaiting approval, rejected, or none), contract status, and whether it was emailed.
3. Two occasional secondary actions: generate and send a new invoice, and request a discount as a buyer on an invoice they received.

Two more read-only logs exist but are rarely needed: auto-declined requests (with the AI's stated reason), and a history of executed discounts.

Example data shape for the review queue:
```
{
  "invoice_number": "INV-3004",
  "buyer_name": "Nordwind Logistik GmbH",
  "claimed_rate": 0.10,
  "approval_level": "manager",
  "reason": "Order volume up 22% this quarter, within manager discretion."
}
```

Example data shape for the invoice tracker:
```
{
  "invoice_number": "INV-3001",
  "role": "issued",
  "counterparty": "Aurea Solutions",
  "amount": 12500.00,
  "discount_status": "executed",
  "emailed_to": "ap@aurea.example"
}
```

Design direction, pulled from a reference site:
- Warm paper background, not white or dark. Roughly #FAF8F3 to #FDFCFB.
- Dark ink text, not pure black. Roughly #242320.
- Navy (#314488) and baby blue (#ABCEFE) as the primary accent pair.
- One orange (#D96F35) reserved only for confirm and success actions. Don't spread it everywhere.
- Pill-shaped buttons, soft layered shadows instead of hard borders, generous whitespace.

Attached screenshots show the current version of this screen. Don't copy that layout, it stacks six sections in one flat scroll with no priority and failed a design review on exactly that point. Use the screenshots only to see the real data fields and current copy, not as a layout reference.

Requirements:
- The review queue is the figure. It should be the first thing visible and get the most visual weight.
- The invoice tracker stays visible but secondary.
- The two occasional-action forms and the two read-only logs should not compete with the review queue for space. Collapse them, tab them, or push them below the fold, your call on the mechanism.
- This is a data-dense internal tool, not a marketing page. Favor restraint over decoration.
- Design the empty state, the loading state, and the focus state for the approve button, not just the happy path with data.
