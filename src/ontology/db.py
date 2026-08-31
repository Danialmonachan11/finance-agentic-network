"""Postgres connection helper. Single place that reads DATABASE_URL so every
module gets the same connection behavior."""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://finance:finance_dev_only@localhost:5432/finance_agentic"
)


def get_conn() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=True)
