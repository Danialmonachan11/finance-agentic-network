"""Server-verified approver identity. Closes the security-audit finding
(BRAIN.md, 2026-08-25) that approver_role was just a form field anyone
could set — role and display_name now come from a Postgres-backed login,
read out of the signed session, never from client input again.

Password hashing uses stdlib hashlib.pbkdf2_hmac (salted) — no new
dependency for something this small; this isn't a real user-management
system, just enough to make "who is this" a server fact instead of a
client claim.
"""

import hashlib
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ontology.db import get_conn

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return f"{salt}:{digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split(":", 1)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()
    return secrets.compare_digest(candidate, digest)


def authenticate(username: str, password: str) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT username, password_hash, display_name, role, company_id, pair_id FROM approver WHERE username = %s", (username,))
        row = cur.fetchone()
    if row is None:
        return None
    _, password_hash, display_name, role, company_id, pair_id = row
    if not verify_password(password, password_hash):
        return None
    return {"username": username, "display_name": display_name, "role": role,
            "company_id": str(company_id), "pair_id": str(pair_id)}


def session_is_current(username: str, company_id: str) -> bool:
    """True if this username still exists with this company id. Cheap, one
    indexed lookup, and it is what turns a stale cookie into 'signed out'
    rather than 'signed in to an empty company'."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM approver WHERE username = %s AND company_id = %s", (username, company_id))
        return cur.fetchone() is not None


def seed_approvers() -> None:
    """Idempotent demo seed. Each approver sits on one side of one pair
    (PRD R8): Alice approves for Kessler on the Kessler-Nordwind pair, Bob
    for Nordwind on the Nordwind-Aurea pair. Runs after data.seed.seed
    because it needs the company and pair rows."""
    demo_users = [
        ("alice", "manager-demo-pw", "Alice (Manager)", "manager", "Kessler Manufacturing", "Nordwind Logistik GmbH"),
        ("bob", "cfo-demo-pw", "Bob (CFO)", "cfo", "Nordwind Logistik GmbH", "Aurea Retail S.A."),
    ]
    with get_conn() as conn, conn.cursor() as cur:
        for username, password, display_name, role, company, counterparty in demo_users:
            cur.execute(
                """
                INSERT INTO approver (username, password_hash, display_name, role, company_id, pair_id)
                SELECT %s, %s, %s, %s, c.id, p.id
                FROM company c
                JOIN company o ON o.name = %s
                JOIN pair p ON p.company_a_id = LEAST(c.id, o.id) AND p.company_b_id = GREATEST(c.id, o.id)
                WHERE c.name = %s
                ON CONFLICT (username) DO NOTHING
                """,
                (username, hash_password(password), display_name, role, counterparty, company),
            )
    print(f"seeded {len(demo_users)} demo approvers: " + ", ".join(f"{u}/{p} ({c})" for u, p, _, _, c, _ in demo_users))


if __name__ == "__main__":
    seed_approvers()
