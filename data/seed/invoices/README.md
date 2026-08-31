# Real invoice test data

`INV-1002.pdf` is a genuine, Invopop-validator-passed, ZUGFeRD-compliant
invoice generated via Scribo, a real third-party invoicing API, not a
synthetic mock. Ground truth matches the
seeded Postgres row exactly: Kessler Manufacturing → Nordwind Logistik
GmbH, EUR 9,800.00, 19% VAT, due 2026-09-01.

**Not reproducible by re-running a script** — Scribo requires a one-time
email verification per sender address (6-digit code, ~15 min TTL), which is
an interactive step. The PDF is committed as a static asset instead of
regenerated on setup. See `BRAIN.md`'s decisions log (2026-08-24) for the
exact API calls used, if you need to generate another one:

```
POST https://scribo.causaprima.ai/api/v1/scribo/email-verifications  {"email": "..."}
  -> {challenge_id}
# read the 6-digit code from the resulting email (don't click the magic link —
# it consumes the same challenge the code belongs to)
POST https://scribo.causaprima.ai/api/v1/scribo/email-verifications/{challenge_id}/redeem  {"code": "..."}
  -> {verification_token}   (valid ~30 min)
POST https://scribo.causaprima.ai/api/v1/invoices
  -H "X-Email-Verification-Token: {verification_token}"
  {sender, recipient, line_items, currency}
  -> {invoice_id, download_url}
```
