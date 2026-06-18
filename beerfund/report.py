"""Aggregate statistics and text reporting for simulation runs."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SimTrade


@dataclass
class Stats:
    label: str
    n_signals: int
    n_filled: int
    win_rate: float        # of filled trades
    avg_return: float
    median_return: float
    total_pnl_sol: float
    profit_factor: float   # gross wins / gross losses
    max_drawdown_sol: float
    wallet_avg_gross: float


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def compute_stats(label: str, trades: list[SimTrade]) -> Stats:
    filled = [t for t in trades if t.filled]
    rets = [t.net_return for t in filled]
    pnls = [t.pnl_sol for t in filled]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]

    equity, peak, max_dd = 0.0, 0.0, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    return Stats(
        label=label,
        n_signals=len(trades),
        n_filled=len(filled),
        win_rate=(len(wins) / len(filled)) if filled else 0.0,
        avg_return=(sum(rets) / len(rets)) if rets else 0.0,
        median_return=_median(rets),
        total_pnl_sol=sum(pnls),
        profit_factor=(sum(wins) / sum(losses)) if losses else float("inf"),
        max_drawdown_sol=max_dd,
        wallet_avg_gross=(sum(t.wallet_gross_return for t in filled) / len(filled))
        if filled else 0.0,
    )


def stats_table(rows: list[Stats]) -> str:
    hdr = (f"{'scenario':<28} {'signals':>7} {'filled':>6} {'win%':>6} "
           f"{'avg ret':>8} {'med ret':>8} {'PnL SOL':>9} {'PF':>6} {'maxDD':>7}")
    lines = [hdr, "-" * len(hdr)]
    for s in rows:
        pf = f"{s.profit_factor:.2f}" if s.profit_factor != float("inf") else "inf"
        lines.append(
            f"{s.label:<28} {s.n_signals:>7} {s.n_filled:>6} "
            f"{s.win_rate * 100:>5.1f}% {s.avg_return * 100:>7.1f}% "
            f"{s.median_return * 100:>7.1f}% {s.total_pnl_sol:>9.3f} "
            f"{pf:>6} {s.max_drawdown_sol:>7.3f}"
        )
    return "\n".join(lines)


def archetype_breakdown(trades: list[SimTrade]) -> str:
    archetypes = sorted({t.archetype for t in trades if t.archetype})
    lines = [f"{'archetype':<10} {'filled':>6} {'win%':>6} {'avg ret':>8} {'PnL SOL':>9}"]
    lines.append("-" * len(lines[0]))
    for a in archetypes:
        sub = [t for t in trades if t.archetype == a and t.filled]
        if not sub:
            continue
        wins = sum(1 for t in sub if t.pnl_sol > 0)
        avg = sum(t.net_return for t in sub) / len(sub)
        pnl = sum(t.pnl_sol for t in sub)
        lines.append(f"{a:<10} {len(sub):>6} {wins / len(sub) * 100:>5.1f}% "
                     f"{avg * 100:>7.1f}% {pnl:>9.3f}")
    return "\n".join(lines)


def trades_csv(trades: list[SimTrade], path: str) -> None:
    import csv

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["token", "archetype", "filled", "entry_t", "entry_price",
                    "exit_reasons", "net_return", "pnl_sol", "wallet_gross_return"])
        for t in trades:
            w.writerow([
                t.token, t.archetype, t.filled,
                f"{t.entry.t:.1f}" if t.entry else "",
                f"{t.entry.eff_price:.3e}" if t.entry else "",
                t.exit_reasons,
                f"{t.net_return:.4f}", f"{t.pnl_sol:.5f}",
                f"{t.wallet_gross_return:.4f}",
            ])
