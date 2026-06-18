"""Postgres access for the read-model layer.

This is the ONLY new dependency the project takes on: psycopg (v3). The trading
workers (paper_trader.py, run_audit.py, run_replay.py) stay stdlib-only and are
never imported here — db.py is used exclusively by ingest.py, audit_runner.py,
discover.py and the API. Nothing here can sign a transaction.

Connection string comes from $DATABASE_URL, e.g.
    postgresql://beerfund:beerfund@localhost:5432/beerfund
"""

from __future__ import annotations

import os

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as e:  # pragma: no cover - clearer message than a raw traceback
    raise SystemExit(
        "psycopg is required for the web layer.\n"
        "    pip install 'psycopg[binary]'\n"
        "(the trading workers do not need this — only ingest/audit/api do)"
    ) from e


def _load_dotenv() -> None:
    """Pull KEY=value lines from the project-root .env into os.environ.

    Lets you keep DATABASE_URL (e.g. your Supabase string) in .env and have
    ingest.py / the API / audit_runner all pick it up. setdefault: a real
    environment variable always wins over the file.
    """
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def dsn() -> str:
    _load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set.\n"
            "Add your Supabase connection string to .env (or export it), e.g.\n"
            "    DATABASE_URL=postgresql://postgres:PASSWORD@db.<ref>.supabase.co:5432/postgres?sslmode=require"
        )
    return url


def connect(autocommit: bool = True) -> "psycopg.Connection":
    """Open a dict-row connection. autocommit on by default for simple upserts."""
    return psycopg.connect(dsn(), autocommit=autocommit, row_factory=dict_row)


def init_schema(schema_path: str | None = None) -> None:
    """Apply schema.sql (idempotent — every statement is IF NOT EXISTS)."""
    if schema_path is None:
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql"
        )
    with open(schema_path) as f:
        sql = f.read()
    with connect() as conn:
        conn.execute(sql)


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return conn.execute(query, params).fetchall()


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    with connect() as conn:
        return conn.execute(query, params).fetchone()


if __name__ == "__main__":  # `python3 -m beerfund.db` applies the schema
    init_schema()
    print(f"schema applied to {dsn().rsplit('@', 1)[-1]}")
