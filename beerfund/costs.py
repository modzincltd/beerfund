"""Cost model: the part every screenshot leaves out.

Three costs eat small-size Solana DEX trading:

1. Pool fee — Raydium/Pump.fun AMM pools charge ~0.25% per side. Paid twice per round trip.
2. Priority fee — a flat SOL amount per transaction to get included quickly.
   At small position sizes this is brutally regressive: 0.001 SOL on a 0.5 SOL
   position is 20 bps per tx before anything else happens.
3. Price impact — constant-product AMM math. Buying `size` SOL from a pool with
   `depth` SOL on the SOL side moves the price against you by roughly
   size / (size + depth). Thin pools (the ones small capital "owns") have
   depths of 5-50 SOL, so even a 0.5 SOL buy can cost 1-9% of impact —
   and you pay it again on the way out.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostModel:
    pool_fee_bps: float = 25.0       # per side
    priority_fee_sol: float = 0.001  # per transaction

    @property
    def pool_fee(self) -> float:
        return self.pool_fee_bps / 10_000.0

    def price_impact(self, size_sol: float, depth_sol: float) -> float:
        """Fraction the price moves against us for a trade of size_sol."""
        if depth_sol <= 0:
            return 1.0
        return size_sol / (size_sol + depth_sol)

    def buy(self, size_sol: float, price: float, depth_sol: float) -> tuple[float, float, float]:
        """Spend size_sol buying at observed `price`.

        Returns (tokens_received, effective_price, total_sol_cost_incl_priority).
        """
        impact = self.price_impact(size_sol, depth_sol)
        eff_price = price * (1.0 + impact)
        tokens = size_sol * (1.0 - self.pool_fee) / eff_price
        return tokens, eff_price, size_sol + self.priority_fee_sol

    def sell(self, tokens: float, price: float, depth_sol: float,
             approx_size_sol: float) -> tuple[float, float]:
        """Sell `tokens` at observed `price`.

        approx_size_sol: notional used for the impact calculation.
        Returns (sol_proceeds_after_all_costs, effective_price).
        """
        impact = self.price_impact(approx_size_sol, depth_sol)
        eff_price = price * (1.0 - impact)
        proceeds = tokens * eff_price * (1.0 - self.pool_fee) - self.priority_fee_sol
        return proceeds, eff_price
