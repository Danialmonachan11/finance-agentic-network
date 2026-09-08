"""Baseline: the schema as of 2026-09-08, including the pair table.

Revision ID: 0001
Revises: None
Create Date: 2026-09-08

This runs src/ontology/schema.sql verbatim. From here on, schema.sql is the
starting point and every change is a new file in this directory. A database
that already has this schema (the demo database before migrations existed)
is marked with `alembic stamp 0001` instead of upgraded.
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "ontology" / "schema.sql"

TABLES = [
    "processed_email", "approver", "llm_call_cost", "workflow_event", "audit_log",
    "discount_proposal", "invoice_line", "invoice", "discount_policy", "pair", "contract", "company",
]


def upgrade() -> None:
    op.execute(SCHEMA.read_text(encoding="utf-8"))


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
