#!/usr/bin/env python3
"""Audit a real Solana wallet's trading record from chain data.

Usage:
    export HELIUS_API_KEY=...          # free key from https://helius.dev
    python3 run_audit.py <WALLET_ADDRESS> [more addresses...] [--pages 10] [--fresh]

Candidate wallets come from GMGN.ai / gmgn leaderboards, Telegram alpha
channels, or any wallet you've watched make a suspiciously good trade.
This tool tells you whether their record is real, recent, and copyable —
BEFORE any capital ever follows them.
"""

from __future__ import annotations

import argparse
import os
import sys

from beerfund.audit import audit, render, suggest_trading_account, verdict
from beerfund.fetch_helius import fetch_swap_txs, parse_swaps


def load_dotenv() -> None:
    """Load KEY=value lines from a project-root .env into os.environ."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("wallets", nargs="+", help="Solana wallet address(es)")
    ap.add_argument("--pages", type=int, default=10,
                    help="pages of 100 swaps to fetch per wallet (default 10)")
    ap.add_argument("--fresh", action="store_true", help="ignore local cache")
    ap.add_argument("--summary", action="store_true",
                    help="one verdict line per wallet, candidates first")
    args = ap.parse_args()

    api_key = os.environ.get("HELIUS_API_KEY")
    if not api_key:
        sys.exit("HELIUS_API_KEY is not set.\n"
                 "Get a free key at https://helius.dev (free tier is plenty "
                 "for auditing), then:\n    export HELIUS_API_KEY=<your key>")

    order = {"CANDIDATE": 0, "DECAYING": 1, "THIN": 2, "TOOFAST": 3,
             "LOSER": 4, "INSIDER": 5}
    rows = []
    for i, wallet in enumerate(args.wallets):
        try:
            txs = fetch_swap_txs(wallet, api_key, max_pages=args.pages,
                                 use_cache=not args.fresh)
        except Exception as e:  # one bad wallet shouldn't kill a 30-wallet sweep
            print(f"  fetch failed for {wallet}: {e}", file=sys.stderr)
            continue
        swaps = parse_swaps(txs, wallet)
        rep = audit(wallet, swaps)
        if args.summary:
            code, reason = verdict(rep)
            rows.append((order.get(code, 9), code, reason, wallet))
            print(f"  [{i + 1}/{len(args.wallets)}] {wallet[:6]}… {code}",
                  file=sys.stderr)
            continue
        print(render(rep))
        if not swaps and txs:
            hint = suggest_trading_account(txs, wallet)
            if hint:
                print(f"  hint: this address fee-pays swaps but funds move through\n"
                      f"        {hint}\n"
                      f"        (signer/vault bot pattern) — audit that address instead.")
        print()

    if args.summary:
        rows.sort()
        print(f"\n{'verdict':<10} {'wallet':<44} reason")
        print("-" * 100)
        for _, code, reason, wallet in rows:
            print(f"{code:<10} {wallet:<44} {reason}")


if __name__ == "__main__":
    main()
