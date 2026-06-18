"""Exit rules — code, not vibes (context.md, non-negotiable section).

The rules engine is deliberately mechanical:

- Stop loss: if price drops `stop_loss_pct` below entry, sell everything left.
- Take-profit ladder: at each (multiple, fraction) rung, sell that fraction of
  the ORIGINAL position. E.g. [(2.0, 0.5), (4.0, 0.25)] = sell half at 2x,
  another quarter at 4x, let the rest ride.
- Trailing stop (optional): after the first TP rung fires, sell the remainder
  if price falls `trailing_stop_pct` from its peak. Protects runners from
  round-tripping to zero.
- Max hold: time-box every position. Memecoins don't reward loyalty.

Triggers are evaluated on observed prices only, and fills happen at the first
observation at/after trigger_time + exit_lag — because in the real world your
stop "at" a price fills wherever the market is when your transaction lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExitRules:
    stop_loss_pct: float = 0.40                 # exit all if down 40% from entry
    take_profits: list[tuple[float, float]] = field(
        default_factory=lambda: [(2.0, 0.50), (4.0, 0.25)]
    )
    trailing_stop_pct: float | None = 0.35      # armed after first TP rung
    max_hold_s: float = 1800.0                  # 30 minutes, then out

    def validate(self) -> None:
        total = sum(f for _, f in self.take_profits)
        if total > 1.0 + 1e-9:
            raise ValueError("take-profit fractions exceed 100% of position")
        mults = [m for m, _ in self.take_profits]
        if mults != sorted(mults):
            raise ValueError("take-profit rungs must be in ascending order")
