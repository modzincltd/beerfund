#!/usr/bin/env python3
"""Ingest paper-trading output into Postgres — without touching the daemon.

The paper daemon keeps writing results/paper_trades.csv and data/paper/state.json
exactly as before (it stays the source of truth). This process tails those files
and mirrors them into the read model the API/frontend serve from. Decoupled on
purpose: if Postgres is down, the daemon is unaffected and we just catch up later.

Run once:        python3 ingest.py --once
Run as a loop:   python3 ingest.py --interval 15
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import time

from beerfund import db

TRADES_CSV = os.environ.get("PAPER_TRADES_CSV", "results/paper_trades.csv")
STATE_PATH = os.environ.get("PAPER_STATE_PATH", "data/paper/state.json")


def _ts(unix: float | str) -> dt.datetime:
    return dt.datetime.fromtimestamp(float(unix), tz=dt.timezone.utc)


def _f(v) -> float | None:
    """CSV cells are strings; blanks mean NULL."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _row_hash(row: dict) -> str:
    key = "|".join(str(row.get(k, "")) for k in
                   ("ts", "event", "mint", "wallet", "fraction", "sol",
                    "tokens", "price", "reason", "pnl_sol"))
    return hashlib.sha256(key.encode()).hexdigest()


def ingest_trades(conn) -> int:
    if not os.path.exists(TRADES_CSV):
        return 0
    inserted = 0
    with open(TRADES_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("ts"):
                continue
            h = _row_hash(row)
            tokens = row.get("tokens") or None
            res = conn.execute(
                """
                INSERT INTO trades (ts, event, mint, wallet, fraction, sol,
                                    tokens, price, reason, pnl_sol, row_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (row_hash) DO NOTHING
                """,
                (_ts(row["ts"]), row["event"], row["mint"], row.get("wallet"),
                 _f(row.get("fraction")), _f(row.get("sol")),
                 tokens if tokens not in ("", None) else None,
                 _f(row.get("price")), row.get("reason"),
                 _f(row.get("pnl_sol")), h),
            )
            inserted += res.rowcount
    return inserted


def ingest_state(conn) -> None:
    if not os.path.exists(STATE_PATH):
        return
    with open(STATE_PATH) as f:
        st = json.load(f)

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
        (st.get("realized_sol", 0.0), st.get("n_closed", 0),
         st.get("n_skipped", 0), json.dumps(st.get("last_sig", {}))),
    )

    # Replace the open-positions snapshot wholesale (it's small and authoritative).
    live = st.get("positions", {})
    conn.execute("DELETE FROM positions WHERE mint <> ALL(%s)",
                 (list(live.keys()) or [""],))
    for mint, p in live.items():
        conn.execute(
            """
            INSERT INTO positions (mint, wallet, entry_ts, tokens, entry_price,
                                   peak, remaining, rung, banked_sol, cost_sol, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (mint) DO UPDATE SET
                wallet=EXCLUDED.wallet, entry_ts=EXCLUDED.entry_ts,
                tokens=EXCLUDED.tokens, entry_price=EXCLUDED.entry_price,
                peak=EXCLUDED.peak, remaining=EXCLUDED.remaining,
                rung=EXCLUDED.rung, banked_sol=EXCLUDED.banked_sol,
                cost_sol=EXCLUDED.cost_sol, updated_at=now()
            """,
            (mint, p["wallet"], _ts(p["entry_ts"]), int(p["tokens"]),
             p["entry_price"], p["peak"], p["remaining"], p["rung"],
             p["banked_sol"], p["cost_sol"]),
        )


def refresh_coins(conn) -> None:
    """Roll trade activity up into the coins table (paper-trade side)."""
    conn.execute(
        """
        INSERT INTO coins (mint, first_seen, last_seen, n_paper_trades, updated_at)
        SELECT mint, min(ts), max(ts), count(*), now()
        FROM trades GROUP BY mint
        ON CONFLICT (mint) DO UPDATE SET
            first_seen = LEAST(coins.first_seen, EXCLUDED.first_seen),
            last_seen  = GREATEST(coins.last_seen, EXCLUDED.last_seen),
            n_paper_trades = EXCLUDED.n_paper_trades,
            updated_at = now()
        """
    )


def cycle() -> int:
    with db.connect() as conn:
        n = ingest_trades(conn)
        ingest_state(conn)
        refresh_coins(conn)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="ingest once and exit")
    ap.add_argument("--interval", type=float, default=15.0,
                    help="seconds between ingest cycles (loop mode)")
    ap.add_argument("--init", action="store_true",
                    help="apply schema.sql before ingesting")
    args = ap.parse_args()

    if args.init:
        db.init_schema()
        print("schema applied")

    if args.once:
        print(f"ingested {cycle()} new trade rows")
        return

    print(f"ingest loop up (every {args.interval:.0f}s) — Ctrl-C to stop")
    while True:
        try:
            n = cycle()
            if n:
                print(f"[{time.strftime('%H:%M:%S')}] +{n} trade rows")
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nbye")
            return
        except Exception as e:  # never die on a transient DB/file hiccup
            print(f"  [warn] {type(e).__name__}: {e}")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
