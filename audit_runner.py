#!/usr/bin/env python3
"""Run the wallet auditor over the follow pool + discovery candidates -> Postgres.

Reuses beerfund.audit and beerfund.fetch_helius verbatim (the research logic is
untouched). For each wallet we store the report-card summary in wallet_audits,
every closed/open position in audit_positions, and bump per-coin appearance
counts. The frontend's "wallet analysis" and "coin analysis" views read these.

Usage:
    export HELIUS_API_KEY=...
    python3 audit_runner.py <WALLET> [<WALLET>...]      # explicit list
    python3 audit_runner.py --follow                    # wallets in $WALLETS
    python3 audit_runner.py --candidates                # discovery_candidates table
    python3 audit_runner.py --follow --candidates --interval 86400   # weekly-ish loop
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import statistics
import sys
import time

from beerfund import db, settings
from beerfund import audit as _audit_mod
from beerfund.audit import audit, verdict, AuditReport, TokenPosition
from beerfund.fetch_helius import fetch_swap_txs, parse_swaps
from run_audit import load_dotenv

FOLLOW_POOL = [w for w in os.environ.get("WALLETS", "").split() if w]


def _ts(unix: int) -> dt.datetime | None:
    return dt.datetime.fromtimestamp(unix, tz=dt.timezone.utc) if unix else None


def metrics(rep: AuditReport) -> dict:
    """Derive the same numbers render()/verdict() compute, as plain fields."""
    closed = rep.closed
    code, reason = verdict(rep)
    out = {
        "n_swaps": rep.n_swaps, "n_positions": rep.n_positions,
        "n_closed": len(closed), "n_open": len(rep.open_),
        "win_rate": rep.win_rate, "total_realized_sol": rep.total_realized_sol,
        "median_pnl_sol": None, "median_hold_s": None, "best_trade_sol": None,
        "concentration": None, "old_avg": None, "new_avg": None,
        "decaying": False, "verdict_code": code, "verdict_reason": reason,
    }
    if not closed:
        return out
    pnls = sorted(p.realized_pnl_sol for p in closed)
    holds = sorted(p.hold_seconds for p in closed)
    out["median_pnl_sol"] = pnls[len(pnls) // 2]
    out["median_hold_s"] = holds[len(holds) // 2]
    out["best_trade_sol"] = max(pnls)
    if rep.total_realized_sol > 0:
        out["concentration"] = out["best_trade_sol"] / rep.total_realized_sol
    half = len(closed) // 2
    if half >= 1:
        out["old_avg"] = statistics.fmean(p.realized_pnl_sol for p in closed[:half])
        out["new_avg"] = statistics.fmean(p.realized_pnl_sol for p in closed[half:])
        out["decaying"] = bool(out["new_avg"] < out["old_avg"] * 0.5 and out["old_avg"] > 0)
    return out


def store(conn, wallet: str, rep: AuditReport, in_follow: bool) -> int:
    m = metrics(rep)
    audit_id = conn.execute(
        """
        INSERT INTO wallet_audits
          (wallet, n_swaps, n_positions, n_closed, n_open, win_rate,
           total_realized_sol, median_pnl_sol, median_hold_s, best_trade_sol,
           concentration, old_avg, new_avg, decaying, verdict_code,
           verdict_reason, in_follow_pool)
        VALUES (%(w)s,%(n_swaps)s,%(n_positions)s,%(n_closed)s,%(n_open)s,
                %(win_rate)s,%(total_realized_sol)s,%(median_pnl_sol)s,
                %(median_hold_s)s,%(best_trade_sol)s,%(concentration)s,
                %(old_avg)s,%(new_avg)s,%(decaying)s,%(verdict_code)s,
                %(verdict_reason)s,%(in_follow)s)
        RETURNING id
        """,
        {**m, "w": wallet, "in_follow": in_follow},
    ).fetchone()["id"]

    for p in rep.closed + rep.open_:
        conn.execute(
            """
            INSERT INTO audit_positions
              (audit_id, wallet, mint, sol_in, sol_out, tokens_bought,
               tokens_sold, first_t, last_t, n_swaps, realized_pnl_sol,
               realized_return, hold_seconds, closed, transfer_fed)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (audit_id, wallet, p.mint, p.sol_in, p.sol_out,
             int(p.tokens_bought), int(p.tokens_sold), _ts(p.first_t),
             _ts(p.last_t), p.n_swaps, p.realized_pnl_sol, p.realized_return,
             p.hold_seconds, p.closed, p.transfer_fed),
        )

    # Bump coin appearance counts + a simple structural risk flag.
    for p in rep.closed + rep.open_:
        flags = []
        if p.transfer_fed:
            flags.append("transfer_fed")
        if p.realized_return > 50:
            flags.append("launch_price_entry")
        conn.execute(
            """
            INSERT INTO coins (mint, first_seen, last_seen, n_audit_appearances,
                               risk_flags, updated_at)
            VALUES (%s,%s,%s,1,%s::jsonb, now())
            ON CONFLICT (mint) DO UPDATE SET
                n_audit_appearances = coins.n_audit_appearances + 1,
                first_seen = LEAST(coins.first_seen, EXCLUDED.first_seen),
                last_seen  = GREATEST(coins.last_seen, EXCLUDED.last_seen),
                risk_flags = COALESCE((
                    SELECT jsonb_agg(DISTINCT e)
                    FROM jsonb_array_elements(coins.risk_flags || EXCLUDED.risk_flags) e
                ), '[]'::jsonb),
                updated_at = now()
            """,
            (p.mint, _ts(p.first_t), _ts(p.last_t),
             __import__("json").dumps(flags)),
        )

    # Keep the discovery row (if any) in sync with the latest verdict.
    conn.execute(
        """
        UPDATE discovery_candidates
           SET status = CASE WHEN %s = 'CANDIDATE' THEN 'promoted'
                             WHEN status = 'new' THEN 'audited' ELSE status END,
               last_verdict = %s, audit_id = %s
         WHERE wallet = %s
        """,
        (m["verdict_code"], m["verdict_code"], audit_id, wallet),
    )
    return audit_id


def run_once(wallets: list[str], api_key: str, pages: int, fresh: bool) -> None:
    # Apply the latest tunable criteria (Settings page) before judging wallets.
    _audit_mod.THRESHOLDS.update(settings.load().get("audit", {}))
    with db.connect() as conn:
        for i, w in enumerate(wallets, 1):
            try:
                txs = fetch_swap_txs(w, api_key, max_pages=pages, use_cache=not fresh)
            except Exception as e:
                print(f"  [{i}/{len(wallets)}] fetch failed {w[:8]}…: {e}", file=sys.stderr)
                continue
            rep = audit(w, parse_swaps(txs, w))
            code, _ = verdict(rep)
            store(conn, w, rep, in_follow=w in FOLLOW_POOL)
            print(f"  [{i}/{len(wallets)}] {w[:8]}… {code} "
                  f"({rep.win_rate*100:.0f}% wr, {rep.total_realized_sol:+.2f} SOL)")


def candidate_wallets(conn) -> list[str]:
    return [r["wallet"] for r in conn.execute(
        "SELECT wallet FROM discovery_candidates WHERE status IN ('new','audited','promoted')"
    ).fetchall()]


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("wallets", nargs="*")
    ap.add_argument("--follow", action="store_true", help="include $WALLETS follow pool")
    ap.add_argument("--candidates", action="store_true", help="include discovery_candidates")
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--interval", type=float, default=0.0,
                    help="seconds between sweeps; 0 = run once and exit")
    ap.add_argument("--init", action="store_true")
    args = ap.parse_args()

    if args.init:
        db.init_schema()

    api_key = os.environ.get("HELIUS_API_KEY")
    if not api_key:
        sys.exit("HELIUS_API_KEY not set")

    def collect() -> list[str]:
        ws = list(args.wallets)
        if args.follow:
            ws += FOLLOW_POOL
        if args.candidates:
            with db.connect() as c:
                ws += candidate_wallets(c)
        return sorted(set(ws))

    while True:
        wallets = collect()
        if not wallets:
            sys.exit("no wallets to audit (pass addresses, --follow, or --candidates)")
        print(f"[{time.strftime('%H:%M:%S')}] sweeping {len(wallets)} wallet(s)…")
        run_once(wallets, api_key, args.pages, args.fresh)
        if args.interval <= 0:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
