"""Resolve which invoice an inbound message is about (PRD R2).

Match on counterparty plus reference plus amount, never on invoice-number
string equality alone: senders misquote numbers, quote several, or quote
none and give the amount instead. The counterparty comes from the sender's
email domain, which is the one thing the message cannot easily fake without
also failing DMARC at the mailbox.

No LLM here. Reference extraction is a regex, the match is one SQL query.
"""

import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn

INVOICE_NUMBER_PATTERN = re.compile(r"\bINV-\d+\b", re.IGNORECASE)
# 4,200.00 / 4200.00 / 4200,00 (European). Requires exactly two decimals so
# rates like "10%" and dates like "2026" do not become amounts.
AMOUNT_PATTERN = re.compile(r"(?<![\w.])(\d{1,3}(?:[.,]\d{3})*|\d+)[.,](\d{2})(?!\d)")


@dataclass(frozen=True)
class References:
    invoice_numbers: tuple[str, ...]
    amounts: tuple[Decimal, ...]


def extract_references(text: str) -> References:
    """Pure: pull every invoice number and every money-looking amount out of
    free text. Order preserved, duplicates removed."""
    numbers = []
    for m in INVOICE_NUMBER_PATTERN.finditer(text):
        n = m.group(0).upper()
        if n not in numbers:
            numbers.append(n)
    amounts = []
    for whole, cents in AMOUNT_PATTERN.findall(text):
        try:
            value = Decimal(re.sub(r"[.,]", "", whole) + "." + cents)
        except InvalidOperation:
            continue
        if value not in amounts:
            amounts.append(value)
    return References(tuple(numbers), tuple(amounts))


def sender_domain(sender: str) -> str:
    """'Anna Berg <anna@nordwind-logistik.de>' -> 'nordwind-logistik.de'."""
    match = re.search(r"@([\w.-]+)", sender)
    return match.group(1).lower() if match else ""


def find_invoice(domain: str, refs: References) -> tuple[str, str] | None:
    """(invoice_id, invoice_number) for the one invoice that involves the
    sender's company and matches a quoted number, else a quoted amount.
    None if nothing matches or the match is ambiguous: an ambiguous match
    goes to a human, never to a guess (R3)."""
    if not domain or (not refs.invoice_numbers and not refs.amounts):
        return None
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.invoice_number,
                   (i.invoice_number = ANY(%s)) AS by_number
            FROM invoice i
            JOIN company s ON s.id = i.seller_company_id
            JOIN company b ON b.id = i.buyer_company_id
            WHERE (s.email_domain = %s OR b.email_domain = %s)
              AND (i.invoice_number = ANY(%s) OR i.amount = ANY(%s))
            ORDER BY by_number DESC, i.issued_date DESC
            """,
            (list(refs.invoice_numbers), domain, domain, list(refs.invoice_numbers), list(refs.amounts)),
        )
        rows = cur.fetchall()
    if not rows:
        return None
    by_number = [r for r in rows if r[2]]
    candidates = by_number or rows
    if len(candidates) != 1:
        return None
    return str(candidates[0][0]), candidates[0][1]


def resolve_invoice(sender: str, text: str) -> tuple[str, str] | None:
    return find_invoice(sender_domain(sender), extract_references(text))


def demo() -> None:
    refs = extract_references("Re INV-1001 and inv-1002, total EUR 4,200.00 due 2026-07-01, 10% discount")
    assert refs.invoice_numbers == ("INV-1001", "INV-1002"), refs
    assert refs.amounts == (Decimal("4200.00"),), refs
    assert sender_domain("Anna <anna@Nordwind-Logistik.de>") == "nordwind-logistik.de"
    hit = resolve_invoice("ap@nordwind-logistik.de", "where is payment for the 4,200.00 invoice?")
    assert hit and hit[1] == "INV-1001", hit
    assert resolve_invoice("someone@unknown.example", "INV-1001") is None
    print("resolver.demo(): all checks passed")


if __name__ == "__main__":
    demo()
