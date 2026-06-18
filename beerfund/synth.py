"""Synthetic Solana memecoin market.

We can't backtest against history we haven't downloaded yet, but we CAN build a
market with the statistical shape everyone agrees on, and measure how copy-trade
mechanics behave inside it. The proportions below are deliberately in line with
the folk numbers (most launches die, a thin tail runs):

  - 65% rugs: pump for 1-10 minutes, then instant collapse to ~2% and flatline.
  - 23% chop: drift and decay, ends at 0.3-0.9x. Death by a thousand cuts.
  - 12% runners: grind to 4-40x over an hour with real pullbacks.

The wallet we copy comes in two skill profiles, because the single most
important variable in copy trading is one you can't fully observe in advance:

  - ELITE — the pre-swarm god wallet. Detects 75% of rugs and exits near the
    top, rides runners to 50-90% of their move. These exist, briefly, until
    leaderboards expose them and copiers crowd the edge away.
  - DECENT — the typical wallet you'd realistically find and copy. Detects 55%
    of rugs, exits earlier and sloppier, paper-hands a quarter of its runners.
    Still genuinely profitable! Just... human.

The question the simulator answers: how much of EACH profile's edge survives
being copied N seconds late, at our size, in these pools?

Everything is seeded — same seed, same market, reproducible experiments.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .models import PriceSeries, WalletTrade


@dataclass
class WalletProfile:
    name: str
    rug_detect_prob: float        # chance of exiting before the collapse
    rug_exit_near_top: bool       # True: exits seconds before collapse; False: somewhere mid-pump
    runner_exit_lo: float         # exit window as a fraction of the runner's full move
    runner_exit_hi: float
    paper_hand_prob: float        # chance of bailing on a runner in the first few minutes


ELITE = WalletProfile("elite", rug_detect_prob=0.75, rug_exit_near_top=True,
                      runner_exit_lo=0.5, runner_exit_hi=0.9, paper_hand_prob=0.0)
DECENT = WalletProfile("decent", rug_detect_prob=0.55, rug_exit_near_top=False,
                       runner_exit_lo=0.3, runner_exit_hi=0.7, paper_hand_prob=0.25)


@dataclass
class SynthToken:
    name: str
    archetype: str
    series: PriceSeries
    depth_sol: float          # SOL-side pool depth, drives price impact
    wallet_trade: WalletTrade


def _walk(rng: random.Random, p0: float, seconds: int, drift_per_s: float,
          vol: float) -> list[float]:
    prices = [p0]
    p = p0
    for _ in range(seconds):
        p *= math.exp(drift_per_s + rng.gauss(0.0, vol))
        prices.append(max(p, p0 * 1e-4))
    return prices


def _make_rug(rng: random.Random, p0: float) -> tuple[list[float], float]:
    t_collapse = rng.uniform(60, 600)
    peak_mult = rng.uniform(1.5, 12)  # most pumps are modest, not moonshots
    up = _walk(rng, p0, int(t_collapse), math.log(peak_mult) / t_collapse, 0.05)
    floor = up[-1] * 0.02
    tail = [floor * math.exp(rng.gauss(0, 0.01)) for _ in range(120)]
    return up + tail, t_collapse


def _make_runner(rng: random.Random, p0: float) -> list[float]:
    duration = int(rng.uniform(1800, 3600))
    target = rng.uniform(4, 40)
    prices = _walk(rng, p0, duration, math.log(target) / duration, 0.025)
    # carve 2-3 genuine pullbacks of 20-40% so trailing stops get tested
    for _ in range(rng.randint(2, 3)):
        at = rng.randint(duration // 4, duration - 60)
        dip = rng.uniform(0.6, 0.8)
        for i in range(at, min(at + 45, len(prices))):
            prices[i] *= dip + (1 - dip) * (i - at) / 45.0
    return prices


def _make_chop(rng: random.Random, p0: float) -> list[float]:
    duration = int(rng.uniform(900, 1800))
    end_mult = rng.uniform(0.3, 0.9)
    return _walk(rng, p0, duration, math.log(end_mult) / duration, 0.03)


def generate_market(n_tokens: int = 300, seed: int = 42,
                    profile: WalletProfile = ELITE) -> list[SynthToken]:
    rng = random.Random(seed)
    tokens: list[SynthToken] = []

    for i in range(n_tokens):
        roll = rng.random()
        p0 = 10 ** rng.uniform(-8, -6)
        collapse_t = None

        if roll < 0.65:
            arch = "rug"
            prices, collapse_t = _make_rug(rng, p0)
            depth = rng.uniform(5, 50)
        elif roll < 0.88:
            arch = "chop"
            prices = _make_chop(rng, p0)
            depth = rng.uniform(5, 80)
        else:
            arch = "runner"
            prices = _make_runner(rng, p0)
            depth = rng.uniform(20, 200)

        series = PriceSeries()
        for t, p in enumerate(prices):
            series.append(float(t), p)

        entry_t = rng.uniform(5, 30)
        end = series.end_time

        if arch == "rug":
            if rng.random() < profile.rug_detect_prob:
                if profile.rug_exit_near_top:  # smells the rug, exits near the top
                    exit_t = max(entry_t + 5, collapse_t - rng.uniform(5, 45))
                else:                          # gets out somewhere mid-pump
                    exit_t = max(entry_t + 5, collapse_t * rng.uniform(0.4, 0.9))
            else:                              # caught in the collapse
                exit_t = min(end, collapse_t + rng.uniform(5, 60))
        elif arch == "runner":
            if rng.random() < profile.paper_hand_prob:
                exit_t = min(end, entry_t + rng.uniform(120, 300))
            else:
                exit_t = rng.uniform(profile.runner_exit_lo,
                                     profile.runner_exit_hi) * end
        else:
            exit_t = min(end, entry_t + rng.uniform(60, 600))

        wt = WalletTrade(
            token=f"TKN{i:03d}", archetype=arch,
            entry_t=entry_t, entry_price=series.price_at(entry_t),
            exit_t=exit_t, exit_price=series.price_at(exit_t),
        )
        tokens.append(SynthToken(f"TKN{i:03d}", arch, series, depth, wt))

    return tokens
