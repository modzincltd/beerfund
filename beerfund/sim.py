"""The copy-trade simulator.

Models the full, honest chain of events when you mirror a wallet:

  wallet's tx lands on chain
    -> you observe it (websocket/poll latency)
    -> you build + send your tx (signing, RPC hop, priority fee auction)
    -> your tx lands N seconds after theirs
    -> you fill at whatever the price is THEN, plus impact, plus fees

Two exit modes:
  - "mirror": copy the wallet's exit too (with the same lag). This is what
    naive copy bots do. The wallet's sell IS the price drop you sell into.
  - "rules": ignore the wallet after entry; exit purely on our ExitRules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .costs import CostModel
from .models import Fill, PriceSeries, SimTrade, WalletTrade
from .rules import ExitRules


@dataclass
class SimConfig:
    entry_lag_s: float = 3.0
    exit_lag_s: float = 3.0
    size_sol: float = 0.5
    mode: str = "rules"  # "mirror" or "rules"
    costs: CostModel = field(default_factory=CostModel)
    rules: ExitRules = field(default_factory=ExitRules)
    # Skip entries where price already ran more than this above the wallet's
    # entry price by the time we can fill (chasing protection). None = always chase.
    max_entry_chase_pct: float | None = 0.25


def simulate_copy(trade: WalletTrade, series: PriceSeries, depth_sol: float,
                  cfg: SimConfig) -> SimTrade:
    result = SimTrade(token=trade.token, archetype=trade.archetype,
                      size_sol=cfg.size_sol, entry=None,
                      wallet_gross_return=trade.gross_return)

    # ---- Entry: we see the wallet's buy, we land entry_lag_s later ----
    obs = series.first_at_or_after(trade.entry_t + cfg.entry_lag_s)
    if obs is None:
        return result  # token died before we could even fill
    fill_t, fill_price = obs

    if cfg.max_entry_chase_pct is not None:
        if fill_price > trade.entry_price * (1.0 + cfg.max_entry_chase_pct):
            return result  # price ran away; chasing is how copiers become exit liquidity

    tokens, eff_buy, sol_cost = cfg.costs.buy(cfg.size_sol, fill_price, depth_sol)
    result.entry = Fill(fill_t, fill_price, eff_buy, 1.0, "entry")

    proceeds = 0.0
    if cfg.mode == "mirror":
        proceeds = _mirror_exit(trade, series, depth_sol, cfg, tokens, result)
    else:
        proceeds = _rules_exit(trade, series, depth_sol, cfg, tokens, eff_buy, fill_t, result)

    result.pnl_sol = proceeds - sol_cost
    return result


def _fill_sell(series: PriceSeries, trigger_t: float, lag: float, tokens: float,
               fraction: float, depth: float, cfg: SimConfig, reason: str,
               result: SimTrade) -> float:
    """Sell `fraction` of original position; fill at first obs >= trigger + lag.

    Falls back to the last observed price if the series ends first (a dead
    token still lets you dump at its final, awful print).
    """
    obs = series.first_at_or_after(trigger_t + lag)
    if obs is None:
        t, price = series.end_time, series.prices[-1]
    else:
        t, price = obs
    sell_tokens = tokens * fraction
    notional = sell_tokens * price
    proceeds, eff = cfg.costs.sell(sell_tokens, price, depth, notional)
    result.exits.append(Fill(t, price, eff, fraction, reason))
    return max(proceeds, 0.0)


def _mirror_exit(trade: WalletTrade, series: PriceSeries, depth: float,
                 cfg: SimConfig, tokens: float, result: SimTrade) -> float:
    return _fill_sell(series, trade.exit_t, cfg.exit_lag_s, tokens, 1.0,
                      depth, cfg, "mirror", result)


def _rules_exit(trade: WalletTrade, series: PriceSeries, depth: float,
                cfg: SimConfig, tokens: float, entry_eff_price: float,
                entry_fill_t: float, result: SimTrade) -> float:
    r = cfg.rules
    r.validate()
    remaining = 1.0
    rung = 0
    trail_armed = False
    peak = entry_eff_price
    deadline = entry_fill_t + r.max_hold_s
    proceeds = 0.0

    for t, price in series.observations_between(entry_fill_t, series.end_time):
        if remaining <= 1e-12:
            break
        if t > deadline:
            proceeds += _fill_sell(series, t, cfg.exit_lag_s, tokens, remaining,
                                   depth, cfg, "max_hold", result)
            remaining = 0.0
            break

        peak = max(peak, price)
        mult = price / entry_eff_price

        # Stop loss on remaining position
        if mult <= 1.0 - r.stop_loss_pct:
            proceeds += _fill_sell(series, t, cfg.exit_lag_s, tokens, remaining,
                                   depth, cfg, "stop", result)
            remaining = 0.0
            break

        # Trailing stop (armed once we've banked the first rung)
        if trail_armed and r.trailing_stop_pct is not None:
            if price <= peak * (1.0 - r.trailing_stop_pct):
                proceeds += _fill_sell(series, t, cfg.exit_lag_s, tokens, remaining,
                                       depth, cfg, "trail", result)
                remaining = 0.0
                break

        # Take-profit ladder
        while rung < len(r.take_profits) and mult >= r.take_profits[rung][0]:
            frac = min(r.take_profits[rung][1], remaining)
            proceeds += _fill_sell(series, t, cfg.exit_lag_s, tokens, frac,
                                   depth, cfg, f"tp{rung + 1}", result)
            remaining -= frac
            rung += 1
            trail_armed = True

    if remaining > 1e-12:  # series ended while still holding
        proceeds += _fill_sell(series, series.end_time, 0.0, tokens, remaining,
                               depth, cfg, "eod", result)
    return proceeds
