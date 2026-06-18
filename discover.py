#!/usr/bin/env python3
"""Wallet discovery: get candidate wallets into the pipeline, then audit them.

Candidates land in discovery_candidates with status 'new'. audit_runner.py
--candidates then audits them; a CANDIDATE verdict flips status to 'promoted'.

Sources:
  --gmgn [WINDOW]   best-effort pull from GMGN.ai leaderboard (1d/7d/30d).
                    GMGN sits behind Cloudflare; if it blocks the bot UA the
                    call degrades to a clear warning instead of fake data.
  --from-file PATH  one wallet address per line (paste from any leaderboard).
  --add WALLET...   add specific addresses by hand.

Honesty note (CLAUDE.md): discovery only *adds names to audit*. A wallet is
never followed because it was discovered — only because it passes the auditor.

Usage:
    python3 discover.py --gmgn 7d
    python3 discover.py --from-file candidates.txt --source telegram
    python3 discover.py --add 2QMC...2xvQ 9xZ...abcd
    python3 discover.py --gmgn 7d --audit        # add then immediately audit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from beerfund import db

GMGN_URL = ("https://gmgn.ai/defi/quotation/v1/rank/sol/wallets/"
            "{window}?orderby=pnl_{window}&direction=desc")


def add_candidates(rows: list[tuple[str, str]]) -> int:
    """rows = [(wallet, source)]. Returns number newly inserted."""
    added = 0
    with db.connect() as conn:
        for wallet, source in rows:
            wallet = wallet.strip()
            if len(wallet) < 32:  # crude Solana base58 sanity check
                continue
            res = conn.execute(
                """
                INSERT INTO discovery_candidates (wallet, source)
                VALUES (%s, %s)
                ON CONFLICT (wallet) DO NOTHING
                """,
                (wallet, source),
            )
            added += res.rowcount
    return added


def fetch_gmgn(window: str) -> list[str]:
    """Best-effort GMGN leaderboard pull. Returns wallet addresses or []."""
    url = GMGN_URL.format(window=window)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; beerfund-research/0.1)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"  [warn] GMGN fetch failed ({type(e).__name__}). GMGN is "
              f"Cloudflare-protected and often blocks server IPs.\n"
              f"        Workaround: copy wallet addresses from the leaderboard in "
              f"a browser into a file and use --from-file.", file=sys.stderr)
        return []
    # GMGN's shape is {"data": {"rank": [{"wallet_address": ...}, ...]}}
    rank = (((data or {}).get("data") or {}).get("rank")) or []
    wallets = [w.get("wallet_address") for w in rank if w.get("wallet_address")]
    if not wallets:
        print("  [warn] GMGN returned no rows in the expected shape "
              "(API may have changed) — use --from-file instead.", file=sys.stderr)
    return wallets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gmgn", nargs="?", const="7d", metavar="WINDOW",
                    help="pull GMGN leaderboard (1d|7d|30d, default 7d)")
    ap.add_argument("--from-file", metavar="PATH", help="file of wallet addresses")
    ap.add_argument("--add", nargs="*", default=[], metavar="WALLET")
    ap.add_argument("--source", default="manual", help="label for --from-file/--add")
    ap.add_argument("--audit", action="store_true",
                    help="run audit_runner --candidates after adding")
    ap.add_argument("--init", action="store_true")
    args = ap.parse_args()

    if args.init:
        db.init_schema()

    rows: list[tuple[str, str]] = []
    if args.gmgn:
        rows += [(w, f"gmgn:{args.gmgn}") for w in fetch_gmgn(args.gmgn)]
    if args.from_file:
        with open(args.from_file) as f:
            rows += [(line, args.source) for line in f if line.strip()]
    rows += [(w, args.source) for w in args.add]

    if not rows:
        sys.exit("nothing to add (use --gmgn, --from-file, or --add)")

    added = add_candidates(rows)
    print(f"added {added} new candidate(s) ({len(rows)} submitted)")

    if args.audit:
        os.system(f"{sys.executable} audit_runner.py --candidates")


if __name__ == "__main__":
    main()
