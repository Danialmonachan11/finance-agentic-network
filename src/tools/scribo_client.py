"""Real client for a third-party e-invoicing product, Scribo — see
data/seed/invoices/README.md and BRAIN.md's decisions log (2026-08-24) for
how this API was first reverse-engineered from the vendor's own docs.

Every sender email needs a fresh verification token (6-digit code, emailed,
~30 min TTL) before Scribo will create an invoice. The network's seeded
companies (kessler-mfg.com etc.) have no real inbox, so every invoice in
this demo is sent from one real address — whichever Gmail account
gmail_oauth.py is actually authorized against (see get_sender_email())
— regardless of which company is "acting" as seller. That's a demo
simplification, stated plainly rather than hidden.

Verification is fully automated: request a code, then poll the operator's
own Gmail (already OAuth'd — see gmail_oauth.py) for the email Scribo just
sent and read the code back out, no manual copy-paste. A verification
token is cached to credentials/scribo_verification.json and reused until
it's close to expiry, so a second invoice in quick succession doesn't
re-verify for no reason.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.gmail_oauth import fetch_unread_emails, get_gmail_service

BASE_URL = "https://scribo.causaprima.ai/api/v1"
CREDENTIALS_DIR = Path(__file__).resolve().parents[2] / "credentials"
TOKEN_CACHE_PATH = CREDENTIALS_DIR / "scribo_verification.json"


_sender_email_cache: str | None = None


def get_sender_email() -> str:
    """The address Scribo emails a code to must be the SAME inbox
    _poll_for_code reads from — that has to be whichever account actually
    authorized gmail_oauth, not a guessed/hardcoded address (a real bug
    hit during dev: system-prompt context named a different address than
    the one actually connected via OAuth, so no email ever showed up).
    Resolved lazily and cached — importing this module must never require
    a live Gmail call, or a Gmail hiccup would take down every page in the
    app, not just the invoice feature."""
    global _sender_email_cache
    if _sender_email_cache is None:
        _sender_email_cache = os.environ.get("SCRIBO_SENDER_EMAIL") or \
            get_gmail_service().users().getProfile(userId="me").execute()["emailAddress"]
    return _sender_email_cache

# Static legal details for the 3 seeded companies — Scribo needs a real
# postal address per party (EN 16931 / ZUGFeRD requirement), which the
# `company` table doesn't carry. Demo-only stand-ins, not real addresses.
COMPANY_LEGAL_DETAILS = {
    "Kessler Manufacturing": {
        "legal_name": "Kessler Manufacturing", "country_code": "DE",
        "address_line1": "Industriestrasse 12", "postcode": "70173", "city": "Stuttgart",
        "tax_id": "DE123456788",
    },
    "Nordwind Logistik GmbH": {
        "legal_name": "Nordwind Logistik GmbH", "country_code": "DE",
        "address_line1": "Hafenstrasse 45", "postcode": "20457", "city": "Hamburg",
        "tax_id": "DE234567894",
    },
    "Aurea Retail S.A.": {
        "legal_name": "Aurea Retail S.A.", "country_code": "ES",
        "address_line1": "Calle Mayor 8", "postcode": "28013", "city": "Madrid",
        "tax_id": "ESB12345674",
    },
}


class ScriboError(RuntimeError):
    pass


# Scribo Phase 1 only emits invoices for these seller jurisdictions — a
# real product limitation (hit live: passing an ES sender fails invoice
# creation outright, format_override doesn't route around it). Checked
# before ever calling the API, and surfaced in the UI, rather than letting
# every Aurea invoice attempt fail unexplained.
SUPPORTED_JURISDICTIONS = {"DE", "US"}


def is_seller_supported(company_name: str) -> bool:
    details = COMPANY_LEGAL_DETAILS.get(company_name)
    return bool(details) and details["country_code"] in SUPPORTED_JURISDICTIONS


def _request_verification(email: str) -> str:
    resp = requests.post(f"{BASE_URL}/scribo/email-verifications", json={"email": email}, timeout=15)
    if resp.status_code != 202:
        raise ScriboError(f"email-verifications request failed: {resp.status_code} {resp.text}")
    return resp.json()["challenge_id"]


def _redeem_verification(challenge_id: str, code: str) -> dict:
    resp = requests.post(
        f"{BASE_URL}/scribo/email-verifications/{challenge_id}/redeem", json={"code": code}, timeout=15
    )
    if resp.status_code != 200:
        raise ScriboError(f"redeem failed: {resp.status_code} {resp.text}")
    return resp.json()  # {"verification_token", "expires_at"}


def _poll_for_code(after: datetime, timeout_seconds: int = 90, interval_seconds: int = 5) -> str:
    """Reads the just-sent 6-digit code out of the operator's own Gmail
    inbox (already OAuth'd, read scope). Scans recent unread mail for a
    6-digit code, preferring messages that mention scribo/verification.

    Stale unread verification emails from earlier requests/retries pile up
    in the inbox (Scribo doesn't mark them read), so candidates are filtered
    to strictly after `after` and the newest match wins — otherwise this
    would happily redeem an old code against a brand new challenge_id and
    fail with "Verification challenge invalid, expired, or revoked."""
    deadline = time.monotonic() + timeout_seconds
    after_ms = int(after.timestamp() * 1000)
    six_digit = re.compile(r"\b(\d{6})\b")
    while time.monotonic() < deadline:
        emails = fetch_unread_emails(query="is:unread newer_than:1h", max_results=10)
        fresh = [e for e in emails if e["internal_date_ms"] > after_ms]
        candidates = [e for e in fresh if "scribo" in e["sender"].lower() or "verif" in e["subject"].lower()]
        matches = []
        for e in candidates or fresh:
            match = six_digit.search(e["subject"] + " " + e["body"])
            if match:
                matches.append((e["internal_date_ms"], match.group(1)))
        if matches:
            return max(matches, key=lambda m: m[0])[1]
        time.sleep(interval_seconds)
    raise ScriboError(
        f"no verification code arrived in {get_sender_email()}'s inbox within {timeout_seconds}s — "
        "check the address is right and Scribo isn't rate-limiting repeat requests."
    )


def _load_cached_token() -> str | None:
    if not TOKEN_CACHE_PATH.exists():
        return None
    data = json.loads(TOKEN_CACHE_PATH.read_text())
    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    # 60s safety margin so we don't hand Scribo a token that expires mid-request
    if expires_at > datetime.now(timezone.utc).astimezone(expires_at.tzinfo) and \
       (expires_at - datetime.now(timezone.utc).astimezone(expires_at.tzinfo)).total_seconds() > 60:
        return data["verification_token"]
    return None


def _save_cached_token(verification_token: str, expires_at: str) -> None:
    CREDENTIALS_DIR.mkdir(exist_ok=True)
    TOKEN_CACHE_PATH.write_text(json.dumps({"verification_token": verification_token, "expires_at": expires_at}))


def ensure_verified_sender() -> str:
    """Returns a valid verification token for the resolved sender email,
    reusing the cache when possible, otherwise running the full request ->
    poll Gmail -> redeem round trip (typically 10-40s for the email to
    land)."""
    cached = _load_cached_token()
    if cached:
        return cached

    requested_at = datetime.now(timezone.utc)
    challenge_id = _request_verification(get_sender_email())
    code = _poll_for_code(after=requested_at)
    result = _redeem_verification(challenge_id, code)
    _save_cached_token(result["verification_token"], result["expires_at"])
    return result["verification_token"]


def create_invoice(
    seller_name: str,
    buyer_name: str,
    line_items: list[dict],
    currency: str = "EUR",
    due_date: str | None = None,
) -> dict:
    """line_items: [{"description": str, "quantity": str, "unit_price": str, "tax_rate": str}, ...]
    Returns Scribo's InvoiceRecord: {invoice_id, document_id, download_url, ...}.

    Every party in this demo network resolves to the same real inbox
    (get_sender_email()) — there's only one real email address available,
    and faking distinct per-company inboxes would just be theater. Stated
    plainly rather than hidden; see module docstring."""
    if seller_name not in COMPANY_LEGAL_DETAILS:
        raise ScriboError(f"no legal details on file for seller {seller_name!r}")
    if not is_seller_supported(seller_name):
        country = COMPANY_LEGAL_DETAILS[seller_name]["country_code"]
        raise ScriboError(
            f"Scribo doesn't support invoices from {country} yet (Phase 1 covers {', '.join(sorted(SUPPORTED_JURISDICTIONS))} only) — "
            f"can't generate one on behalf of {seller_name}."
        )

    token = ensure_verified_sender()
    sender_email = get_sender_email()
    sender = {**COMPANY_LEGAL_DETAILS[seller_name], "contact_email": sender_email}
    recipient = {
        **COMPANY_LEGAL_DETAILS.get(buyer_name, {"legal_name": buyer_name, "country_code": "DE",
           "address_line1": "N/A", "postcode": "00000", "city": "N/A"}),
        "contact_email": sender_email,
    }

    payload = {
        "sender": sender,
        "recipient": recipient,
        "line_items": [
            {**item, "tax_category_code": item.get("tax_category_code", "S")} for item in line_items
        ],
        "currency": currency,
    }
    if due_date:
        payload["due_date"] = due_date

    resp = requests.post(
        f"{BASE_URL}/invoices", json=payload, headers={"X-Email-Verification-Token": token}, timeout=30
    )
    if resp.status_code >= 400:
        raise ScriboError(f"invoice creation failed: {resp.status_code} {resp.text}")
    return resp.json()


def demo() -> None:
    """Live, real-money-free smoke test — creates one real invoice via
    Scribo. Not run automatically (hits a real third-party API and sends a
    real verification email); run manually: python -m src.tools.scribo_client"""
    result = create_invoice(
        seller_name="Kessler Manufacturing",
        buyer_name="Nordwind Logistik GmbH",
        line_items=[{"description": "Demo smoke test line item", "quantity": "1", "unit_price": "100.00", "tax_rate": "19"}],
    )
    assert "download_url" in result, f"expected download_url in response, got: {result}"
    print(f"scribo_client.demo(): created invoice {result['invoice_id']}, download_url={result['download_url']}")


if __name__ == "__main__":
    demo()
