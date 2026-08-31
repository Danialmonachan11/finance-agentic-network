"""PII redaction before untrusted free text reaches a third-party LLM
(docs/architecture.md §3.10; closed 2026-08-25 after comparing against a
reference banking-agent architecture that put "PII Redaction" between the
API layer and the agents, specifically gating what a third-party LLM ever
sees). The raw, unredacted email_text is still what gets stored in
Postgres (discount_proposal.justification, audit_log) — redaction only
changes what's sent OUT to OpenRouter in the two prompts that embed raw
free text (intake_triage, extract_claim). Internal/human-facing views keep
the original.

Honest scope note: this is regex-based pattern matching (email addresses,
phone numbers), not a real PII-detection library (e.g. Microsoft Presidio,
which does NER-based name/address detection too). Good enough to
demonstrate the actual architectural point — the LLM boundary is where
redaction happens, not a human review step — but it will miss PII that
doesn't match these two patterns (a name on its own, a street address).
Swapping the detection method later doesn't change where in the pipeline
this runs.
"""

import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Deliberately narrow: 3+ groups of 2-4 digits joined by the same separator,
# at least 7 digits total. Avoids false-positiving on "12%", "€9,800.00", or
# "INV-1002" — all real strings that show up in this domain's free text and
# would otherwise get mangled by a looser phone-number pattern.
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s])?\(?\d{2,4}\)?[-.\s]\d{3,4}[-.\s]\d{3,4}\b")


def redact_pii(text: str) -> str:
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    return redacted


def demo() -> None:
    # Real-shaped business email text, not a synthetic PII test string —
    # matches the actual free-text this function runs on in nodes.py.
    sample = (
        "Hi, following up on invoice INV-1002 for €9,800.00 — could we get a 12% discount? "
        "You can reach me at jane.doe@example.com or +49 30 1234 5678 if you have questions."
    )
    redacted = redact_pii(sample)
    print(f"before: {sample}")
    print(f"after:  {redacted}")

    assert "jane.doe@example.com" not in redacted
    assert "[REDACTED_EMAIL]" in redacted
    assert "+49 30 1234 5678" not in redacted
    assert "[REDACTED_PHONE]" in redacted

    # False-positive guard: domain-specific strings that look numeric/dashed
    # but are NOT phone numbers must survive untouched.
    assert "INV-1002" in redacted, "invoice numbers must not be redacted"
    assert "€9,800.00" in redacted, "currency amounts must not be redacted"
    assert "12%" in redacted, "percentages must not be redacted"

    print("pii_redaction.demo(): PII redacted, domain-specific strings survived untouched")


if __name__ == "__main__":
    demo()
