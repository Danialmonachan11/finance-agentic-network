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
        cur.execute("SELECT username, password_hash, display_name, role FROM approver WHERE username = %s", (username,))
        row = cur.fetchone()
    if row is None:
        return None
    _, password_hash, display_name, role = row
    if not verify_password(password, password_hash):
        return None
    return {"username": username, "display_name": display_name, "role": role}


def seed_approvers() -> None:
    """Idempotent demo seed — two approvers, one per role, so the login
    demo is self-contained without a real user-registration flow."""
    demo_users = [
        ("alice", "manager-demo-pw", "Alice (Manager)", "manager"),
        ("bob", "cfo-demo-pw", "Bob (CFO)", "cfo"),
    ]
    with get_conn() as conn, conn.cursor() as cur:
        for username, password, display_name, role in demo_users:
            cur.execute(
                "INSERT INTO approver (username, password_hash, display_name, role) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (username) DO NOTHING",
                (username, hash_password(password), display_name, role),
            )
    print(f"seeded {len(demo_users)} demo approvers: " + ", ".join(f"{u}/{p}" for u, p, _, _ in demo_users))


if __name__ == "__main__":
    seed_approvers()
