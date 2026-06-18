#!/usr/bin/env python3
"""Experiment 1: how much of a smart wallet's edge survives being copied?

Generates a seeded synthetic memecoin market, lets a wallet of a given skill
profile trade it, then copies that wallet under honest mechanics (lag, fees,
price impact) across a sweep of latencies and both exit modes.

Usage: python3 run_synthetic.py [--tokens 300] [--seed 42] [--size 0.5]
"""

from __future__ import annotations

import argparse
import os

from beerfund.models import SimTrade
from beerfund.report import archetype_breakdown, compute_stats, stats_table, trades_csv
from beerfund.sim import SimConfig, simulate_copy
from beerfund.synth import DECENT, ELITE, generate_market


def run_scenario(market, cfg: SimConfig) -> list[SimTrade]:
    return [simulate_copy(t.wallet_trade, t.series, t.depth_sol, cfg)
            for t in market]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--size", type=float, default=0.5, help="position size in SOL")
    args = ap.parse_args()

    os.makedirs("results", exist_ok=True)

    for profile in (ELITE, DECENT):
        market = generate_market(n_tokens=args.tokens, seed=args.seed,
                                 profile=profile)
        counts = {}
        for t in market:
            counts[t.archetype] = counts.get(t.archetype, 0) + 1

        print("=" * 95)
        print(f"WALLET PROFILE: {profile.name.upper()}   "
              f"(market: {counts}, size {args.size} SOL/trade, seed {args.seed})")
        print("=" * 95)

        # The leaderboard number (gross, no lag, no costs) — what lures everyone in
        gross = [t.wallet_trade.gross_return for t in market]
        wins = sum(1 for g in gross if g > 0)
        pnl = sum(g * args.size for g in gross)
        print(f"wallet's own gross stats (the 'leaderboard' view): "
              f"win rate {wins / len(gross) * 100:.1f}%, "
              f"avg {sum(gross) / len(gross) * 100:+.1f}%/trade, "
              f"total {pnl:+.2f} SOL\n")

        rows = []
        for lag in [0, 1, 2, 3, 5, 10]:
            cfg = SimConfig(entry_lag_s=lag, exit_lag_s=lag, size_sol=args.size,
                            mode="mirror")
            rows.append(compute_stats(f"mirror copy, lag {lag}s",
                                      run_scenario(market, cfg)))

        rules_trades = None
        for lag in [2, 3, 5]:
            cfg = SimConfig(entry_lag_s=lag, exit_lag_s=lag, size_sol=args.size,
                            mode="rules")
            trades = run_scenario(market, cfg)
            rows.append(compute_stats(f"rules copy, lag {lag}s", trades))
            if lag == 3:
                rules_trades = trades

        print(stats_table(rows))
        print(f"\nrules mode (lag 3s) by archetype — {profile.name} wallet:")
        print(archetype_breakdown(rules_trades))

        out = f"results/synthetic_{profile.name}_rules_lag3.csv"
        trades_csv(rules_trades, out)
        print(f"per-trade detail -> {out}\n")


if __name__ == "__main__":
    main()
