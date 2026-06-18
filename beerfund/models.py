"""Core data structures: price series, wallet trades, simulation results."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field


@dataclass
class PriceSeries:
    """A token's price observations over time. Times in seconds, price in SOL per token."""

    times: list[float] = field(default_factory=list)
    prices: list[float] = field(default_factory=list)

    def append(self, t: float, price: float) -> None:
        if self.times and t < self.times[-1]:
            raise ValueError("observations must be appended in time order")
        self.times.append(t)
        self.prices.append(price)

    def price_at(self, t: float) -> float:
        """Last observed price at or before t (first observation if t precedes all)."""
        i = bisect.bisect_right(self.times, t) - 1
        return self.prices[max(i, 0)]

    def first_at_or_after(self, t: float) -> tuple[float, float] | None:
        """First (time, price) observation at or after t, or None if series ended.

        This is the honest fill model: you can't trade at a price nobody printed.
        A trigger that fires at t fills at the next real observation >= t.
        """
        i = bisect.bisect_left(self.times, t)
        if i >= len(self.times):
            return None
        return self.times[i], self.prices[i]

    def observations_between(self, t0: float, t1: float) -> list[tuple[float, float]]:
        i = bisect.bisect_left(self.times, t0)
        j = bisect.bisect_right(self.times, t1)
        return list(zip(self.times[i:j], self.prices[i:j]))

    @property
    def end_time(self) -> float:
        return self.times[-1]


@dataclass
class WalletTrade:
    """One round trip by the smart wallet we're copying. This is our signal source."""

    token: str
    entry_t: float
    entry_price: float
    exit_t: float
    exit_price: float
    archetype: str = ""  # rug / runner / chop — known only in synthetic mode

    @property
    def gross_return(self) -> float:
        """What a leaderboard would show: exit/entry with no costs, no lag."""
        return self.exit_price / self.entry_price - 1.0


@dataclass
class Fill:
    t: float
    price: float          # raw observed price
    eff_price: float      # price after impact
    fraction: float       # fraction of original position
    reason: str           # entry / mirror / stop / tp / trail / max_hold / eod


@dataclass
class SimTrade:
    """Result of simulating one copied trade."""

    token: str
    archetype: str
    size_sol: float
    entry: Fill | None            # None => we never got a fill
    exits: list[Fill] = field(default_factory=list)
    pnl_sol: float = 0.0
    wallet_gross_return: float = 0.0

    @property
    def filled(self) -> bool:
        return self.entry is not None

    @property
    def net_return(self) -> float:
        return self.pnl_sol / self.size_sol if self.size_sol else 0.0

    @property
    def exit_reasons(self) -> str:
        return "+".join(f.reason for f in self.exits) or "none"
