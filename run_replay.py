#!/usr/bin/env python3
"""Replay a wallet's trades against REAL on-chain price paths.

Usage:
    python3 run_replay.py <WALLET> [--size 0.5] [--lag 3] [--depth 30]
                          [--mint-pages 60] [--pages 5]

For every closed round trip the wallet made, rebuilds the token's actual price
path from chain data and answers: had our bot copied this entry with realistic
lag/fees/impact, what would OUR exit rules have made?
"""

from __future__ import annotations

import argparse
import os
import sys

from beerfund.fetch_helius import fetch_swap_txs, parse_swaps
from beerfund.pda import bonding_curve_address
from beerfund.replay import (build_series, clean_points, closed_round_trips,
                             fetch_candles, fetch_mint_window,
                             parse_mint_trades, resolve_pools,
                             resolve_pools_gecko)
from beerfund.rules import ExitRules
from beerfund.sim import SimConfig, simulate_copy
from run_audit import load_dotenv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("wallet")
    ap.add_argument("--size", type=float, default=0.5)
    ap.add_argument("--lag", type=float, default=3.0)
    ap.add_argument("--depth", type=float, default=30.0,
                    help="assumed pool depth in SOL for impact (sensitivity-check this)")
    ap.add_argument("--mint-pages", type=int, default=60)
    ap.add_argument("--pages", type=int, default=5)
    args = ap.parse_args()

    load_dotenv()
    api_key = os.environ.get("HELIUS_API_KEY")
    if not api_key:
        sys.exit("HELIUS_API_KEY not set (project .env or env var)")

    txs = fetch_swap_txs(args.wallet, api_key, max_pages=args.pages)
    swaps = parse_swaps(txs, args.wallet)
    trips = closed_round_trips(swaps)
    print(f"wallet {args.wallet[:8]}…: {len(trips)} clean closed round trips to replay\n")

    rules = ExitRules()  # stop -40%, TP ladder 2x/4x, trail 35%, max hold 30m
    base = dict(entry_lag_s=args.lag, exit_lag_s=args.lag, size_sol=args.size)
    cfg_mirror = SimConfig(mode="mirror", **base)
    cfg_rules = SimConfig(mode="rules", rules=rules, **base)

    hdr = (f"{'token':<12} {'obs':>5} {'wallet':>8} {'mirror':>8} {'rules':>8}  "
           f"{'exit reasons':<20} note")
    print(hdr)
    print("-" * len(hdr))

    tot_wallet = tot_mirror = tot_rules = 0.0
    n_replayed = 0
    for trip in trips:
        wt = trip.wallet_trade
        t_start = wt.entry_t - 600
        t_end = max(wt.exit_t, wt.entry_t + rules.max_hold_s) + 300

        seen: set[str] = set()
        pools = [p for p in resolve_pools(trip.mint) + resolve_pools_gecko(trip.mint)
                 if not (p["pair"] in seen or seen.add(p["pair"]))]
        per_pool: list[list[tuple[float, float]]] = []
        depth = args.depth
        for pool in pools:
            per_pool.append(fetch_candles(pool["pair"], t_start, t_end))
            if pool["depth_sol"] and pool["depth_sol"] >= 5:
                # sub-5-SOL pools are dead TODAY — that says nothing about
                # depth at trade time, so keep the default instead
                depth = pool["depth_sol"]

        # Merge pools on a common price scale: the densest pool is the
        # reference; drop any pool whose median price disagrees by >3x
        # (mis-scaled or broken venues poison the series otherwise).
        per_pool.sort(key=len, reverse=True)
        points: list[tuple[float, float]] = []
        ref_med = None
        for pp in per_pool:
            if not pp:
                continue
            med = sorted(p for _, p in pp)[len(pp) // 2]
            if ref_med is None:
                ref_med = med
            elif not (ref_med / 3 <= med <= ref_med * 3):
                continue
            points.extend(pp)
        points.sort()

        def entry_density() -> int:
            return sum(1 for t, _ in points if wt.entry_t <= t <= wt.entry_t + 600)

        src = "candles"
        if entry_density() < 8 and trip.mint.endswith("pump"):
            # pre-migration window: pull real ticks from the bonding curve PDA
            curve = bonding_curve_address(trip.mint)
            window, reached = fetch_mint_window(curve, api_key, t_start, t_end,
                                                max_pages=args.mint_pages,
                                                tx_type=None)
            ticks = parse_mint_trades(window, trip.mint, focus=curve)
            if ticks:
                if ref_med is not None:
                    # candles already define the price scale; curve ticks are a
                    # different (pre-migration) basis — only merge ticks that
                    # agree, else a mis-scaled tick trips a phantom stop
                    tick_med = sorted(p for _, p in ticks)[len(ticks) // 2]
                    if not (ref_med / 3 <= tick_med <= ref_med * 3):
                        ticks = [(t, p) for t, p in ticks
                                 if ref_med / 3 <= p <= ref_med * 3]
                if ticks:
                    points = sorted(points + ticks)
                    src = f"curve-ticks({'full' if reached else 'partial'})"

        n_raw = len(points)
        points = clean_points(points)
        trip.n_obs = len(points)
        print(f"  {trip.mint[:8]}… pools={len(pools)} obs={len(points)} "
              f"(dropped {n_raw - len(points)} outliers) src={src} "
              f"depth={depth:.0f}", file=sys.stderr)

        series = build_series(points)
        if len(points) < 10 or entry_density() < 2:
            print(f"{trip.mint[:10]}  {len(points):>5} {'':>8} {'':>8} {'':>8}  "
                  f"{'':<20} SKIP: no price data near entry on any source")
            continue

        mirror = simulate_copy(wt, series, args.depth, cfg_mirror)
        ours = simulate_copy(wt, series, args.depth, cfg_rules)
        note = ""
        if not ours.filled:
            note = "no fill (chase guard or no prints)"
        n_replayed += 1
        tot_wallet += wt.gross_return * args.size
        tot_mirror += mirror.pnl_sol if mirror.filled else 0.0
        tot_rules += ours.pnl_sol if ours.filled else 0.0
        print(f"{trip.mint[:10]}  {len(points):>5} "
              f"{wt.gross_return * 100:>+7.1f}% "
              f"{(mirror.net_return * 100 if mirror.filled else 0):>+7.1f}% "
              f"{(ours.net_return * 100 if ours.filled else 0):>+7.1f}%  "
              f"{ours.exit_reasons:<20} {note}")

    print("-" * len(hdr))
    print(f"replayed {n_replayed}/{len(trips)} positions at size {args.size} SOL, "
          f"lag {args.lag}s, depth {args.depth} SOL")
    print(f"totals: wallet-gross {tot_wallet:+.3f} SOL   "
          f"mirror {tot_mirror:+.3f} SOL   rules {tot_rules:+.3f} SOL")


if __name__ == "__main__":
    main()
