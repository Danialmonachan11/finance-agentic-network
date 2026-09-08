"""Alembic runner. Migrations here are plain SQL in Python files, no ORM
models and no autogenerate. The database URL is DATABASE_URL, the same
variable the app reads, so the app and the migrations can never point at
two different databases by accident."""

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://finance:finance_dev_only@localhost:5432/finance_agentic")
# SQLAlchemy needs the driver named; the app uses psycopg 3.
SQLALCHEMY_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_offline() -> None:
    context.configure(url=SQLALCHEMY_URL, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(SQLALCHEMY_URL)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
