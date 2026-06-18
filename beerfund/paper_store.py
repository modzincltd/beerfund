"""Durable paper-trade persistence in Postgres.

The paper daemon was file-based (state.json + paper_trades.csv) with ingest.py
mirroring those into Postgres. On a single droplet that's fine. On DO App
Platform — where each component has an ephemeral, isolated disk — the daemon
must read and write its state to a durable store, or every redeploy loses the
open-position book. So when DATABASE_URL is set, paper_trader.py uses THIS
module instead of local files: it loads its state from Postgres on boot and
writes state + every trade straight to the same read-model tables ingest.py used
(trades, positions, paper_state, coins). ingest.py then becomes unnecessary.

This is the one place the daemon takes a non-stdlib dependency (psycopg, via
beerfund.db) — only on the DB path; the file path stays stdlib-only. Nothing
here signs a transaction or holds a key.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from beerfund import db


def _ts(unix: float | str) -> dt.datetime:
    return dt.datetime.fromtimestamp(float(unix), tz=dt.timezone.utc)


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_state() -> dict:
    """Reconstruct the daemon's in-memory state dict from Postgres."""
    state = {"last_sig": {}, "positions": {}, "realized_sol": 0.0,
             "n_closed": 0, "n_skipped": 0}
    with db.connect() as conn:
        ps = conn.execute(
            "SELECT realized_sol, n_closed, n_skipped, last_sig "
            "FROM paper_state WHERE id = 1"
        ).fetchone()
        if ps:
            state["realized_sol"] = float(ps["realized_sol"] or 0.0)
            state["n_closed"] = ps["n_closed"] or 0
            state["n_skipped"] = ps["n_skipped"] or 0
            # last_sig is JSONB -> already a dict via psycopg
            state["last_sig"] = ps["last_sig"] or {}
        for p in conn.execute("SELECT * FROM positions WHERE manual = false").fetchall():
            state["positions"][p["mint"]] = {
                "wallet": p["wallet"],
                "entry_ts": p["entry_ts"].timestamp(),
                "tokens": int(p["tokens"]),
                "entry_price": float(p["entry_price"]),
                "peak": float(p["peak"]),
                "remaining": float(p["remaining"]),
                "rung": int(p["rung"]),
                "banked_sol": float(p["banked_sol"]),
                "cost_sol": float(p["cost_sol"]),
            }
    return state


def save_state(state: dict) -> None:
    """Persist counters + the open-position book (authoritative snapshot)."""
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_state (id, realized_sol, n_closed, n_skipped, last_sig, updated_at)
            VALUES (1, %s, %s, %s, %s, now())
            ON CONFLICT (id) DO UPDATE SET
                realized_sol = EXCLUDED.realized_sol,
                n_closed     = EXCLUDED.n_closed,
                n_skipped    = EXCLUDED.n_skipped,
                last_sig     = EXCLUDED.last_sig,
                updated_at   = now()
            """,
            (state["realized_sol"], state["n_closed"], state["n_skipped"],
             json.dumps(state["last_sig"])),
        )
        live = state["positions"]
        # Only ever touch daemon-owned rows; manual (UI) positions are isolated.
        conn.execute("DELETE FROM positions WHERE manual = false AND mint <> ALL(%s)",
                     (list(live.keys()) or [""],))
        for mint, p in live.items():
            conn.execute(
                """
                INSERT INTO positions (mint, wallet, entry_ts, tokens, entry_price,
                                       peak, remaining, rung, banked_sol, cost_sol, manual, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, false, now())
                ON CONFLICT (mint) DO UPDATE SET
                    wallet=EXCLUDED.wallet, entry_ts=EXCLUDED.entry_ts,
                    tokens=EXCLUDED.tokens, entry_price=EXCLUDED.entry_price,
                    peak=EXCLUDED.peak, remaining=EXCLUDED.remaining,
                    rung=EXCLUDED.rung, banked_sol=EXCLUDED.banked_sol,
                    cost_sol=EXCLUDED.cost_sol, updated_at=now()
                WHERE positions.manual = false
                """,
                (mint, p["wallet"], _ts(p["entry_ts"]), int(p["tokens"]),
                 p["entry_price"], p["peak"], p["remaining"], int(p["rung"]),
                 p["banked_sol"], p["cost_sol"]),
            )


def log_trade(row: dict) -> None:
    """Append one ENTRY/EXIT/CLOSE row + bump the coin's paper-trade count."""
    key = "|".join(str(row.get(k, "")) for k in
                   ("ts", "event", "mint", "wallet", "fraction", "sol",
                    "tokens", "price", "reason", "pnl_sol"))
    h = hashlib.sha256(key.encode()).hexdigest()
    tokens = row.get("tokens")
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO trades (ts, event, mint, wallet, fraction, sol,
                                tokens, price, reason, pnl_sol, row_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (row_hash) DO NOTHING
            """,
            (_ts(row["ts"]), row["event"], row["mint"], row.get("wallet"),
             _f(row.get("fraction")), _f(row.get("sol")),
             tokens if tokens not in ("", None) else None,
             _f(row.get("price")), row.get("reason"), _f(row.get("pnl_sol")), h),
        )
        conn.execute(
            """
            INSERT INTO coins (mint, first_seen, last_seen, n_paper_trades, updated_at)
            VALUES (%s, %s, %s, 1, now())
            ON CONFLICT (mint) DO UPDATE SET
                first_seen = LEAST(coins.first_seen, EXCLUDED.first_seen),
                last_seen  = GREATEST(coins.last_seen, EXCLUDED.last_seen),
                n_paper_trades = coins.n_paper_trades + 1,
                updated_at = now()
            """,
            (row["mint"], _ts(row["ts"]), _ts(row["ts"])),
        )
