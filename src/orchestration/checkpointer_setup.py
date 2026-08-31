"""One-time setup for the Postgres-backed LangGraph checkpointer — creates
its internal checkpoint/writes tables. Run once against a fresh database:
  python -m src.orchestration.checkpointer_setup
Safe to re-run (idempotent, CREATE TABLE IF NOT EXISTS under the hood).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.checkpoint.postgres import PostgresSaver

from src.orchestration.graph import DATABASE_URL


def setup() -> None:
    with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
        checkpointer.setup()
    print("checkpointer_setup: PostgresSaver tables created (or already existed)")


if __name__ == "__main__":
    setup()
