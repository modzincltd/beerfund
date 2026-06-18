"""Wallet auditor: turn a wallet's swap history into an honest report card.

This is the real edge from our research: wallet SELECTION is the product.
Leaderboards show gross cherry-picked stats; we compute our own from chain
data, including the two things leaderboards hide:

  1. Realized PnL on an average-cost basis, per token, in SOL.
  2. DECAY — is the wallet's recent performance worse than its older
     performance? Copied wallets rot as copiers crowd in. We split closed
     positions chronologically and compare halves, plus a last-20 window.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .fetch_helius import Swap

# Verdict thresholds — defaults match beerfund.settings.DEFAULTS["audit"].
# audit_runner overrides these from the Settings store before a sweep. Kept as a
# plain mutable dict so this module stays dependency-free (no DB import).
THRESHOLDS = {
    "min_closed": 8,
    "insider_return_x": 50.0,
    "min_median_hold_s": 600,
    "decay_ratio": 0.5,
}


@dataclass
class TokenPosition:
    mint: str
    sol_in: float = 0.0          # total SOL spent buying
    sol_out: float = 0.0         # total SOL received selling
    tokens_bought: float = 0.0
    tokens_sold: float = 0.0
    first_t: int = 0
    last_t: int = 0
    n_swaps: int = 0

    @property
    def sold_fraction(self) -> float:
        return self.tokens_sold / self.tokens_bought if self.tokens_bought else 0.0

    @property
    def closed(self) -> bool:
        """Treat as a closed round trip once ~95% of bought tokens are sold."""
        return self.tokens_bought > 0 and self.sold_fraction >= 0.95

    @property
    def realized_pnl_sol(self) -> float:
        """Average-cost realized PnL on the portion actually sold."""
        if not self.tokens_bought:
            return 0.0
        cost_of_sold = self.sol_in * min(self.sold_fraction, 1.0)
        return self.sol_out - cost_of_sold

    @property
    def realized_return(self) -> float:
        cost = self.sol_in * min(self.sold_fraction, 1.0)
        return self.realized_pnl_sol / cost if cost > 0 else 0.0

    @property
    def hold_seconds(self) -> int:
        return self.last_t - self.first_t

    @property
    def transfer_fed(self) -> bool:
        """Sold meaningfully more tokens than it bought on-DEX: the surplus
        arrived by transfer (dev allocation, airdrop, sister wallet). That's
        an insider pattern, and its 'returns' are not achievable by copying."""
        return self.tokens_bought > 0 and self.tokens_sold > self.tokens_bought * 1.05


def build_positions(swaps: list[Swap]) -> list[TokenPosition]:
    pos: dict[str, TokenPosition] = {}
    for s in swaps:
        p = pos.setdefault(s.mint, TokenPosition(mint=s.mint, first_t=s.timestamp))
        p.last_t = max(p.last_t, s.timestamp)
        p.first_t = min(p.first_t, s.timestamp)
        p.n_swaps += 1
        if s.side == "buy":
            p.sol_in += s.sol_amount
            p.tokens_bought += s.token_amount
        else:
            p.sol_out += s.sol_amount
            p.tokens_sold += s.token_amount
    # Ignore positions that were sells-only in our window (bought before the
    # data we fetched) — we can't price their cost basis honestly.
    return [p for p in pos.values() if p.tokens_bought > 0]


@dataclass
class AuditReport:
    wallet: str
    n_swaps: int
    n_positions: int
    closed: list[TokenPosition] = field(default_factory=list)
    open_: list[TokenPosition] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        if not self.closed:
            return 0.0
        return sum(1 for p in self.closed if p.realized_pnl_sol > 0) / len(self.closed)

    @property
    def total_realized_sol(self) -> float:
        return sum(p.realized_pnl_sol for p in self.closed)


def audit(wallet: str, swaps: list[Swap]) -> AuditReport:
    positions = build_positions(swaps)
    rep = AuditReport(wallet=wallet, n_swaps=len(swaps), n_positions=len(positions))
    for p in sorted(positions, key=lambda p: p.last_t):
        (rep.closed if p.closed else rep.open_).append(p)
    return rep


def _fmt_hold(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"


def verdict(rep: AuditReport) -> tuple[str, str]:
    """One-line copyability verdict: (code, reason). Codes sort best-first."""
    closed = rep.closed
    if len(closed) < THRESHOLDS["min_closed"]:
        return "THIN", f"only {len(closed)} closed trades in window — can't judge"

    fed = sum(1 for p in closed if p.transfer_fed)
    huge = sum(1 for p in closed if p.realized_return > THRESHOLDS["insider_return_x"])
    if fed or huge:
        bits = []
        if fed:
            bits.append(f"{fed} transfer-fed")
        if huge:
            bits.append(f"{huge} launch-price entries")
        return "INSIDER", ", ".join(bits)

    holds = sorted(p.hold_seconds for p in closed)
    med_hold = holds[len(holds) // 2]
    if med_hold < THRESHOLDS["min_median_hold_s"]:
        return "TOOFAST", f"median hold {_fmt_hold(med_hold)} — dies in our copy lag"

    if rep.total_realized_sol <= 0:
        return "LOSER", f"realized {rep.total_realized_sol:+.2f} SOL"

    half = len(closed) // 2
    old_avg = sum(p.realized_pnl_sol for p in closed[:half]) / half
    new_avg = sum(p.realized_pnl_sol for p in closed[half:]) / (len(closed) - half)
    if new_avg < old_avg * THRESHOLDS["decay_ratio"] and old_avg > 0:
        return "DECAYING", f"avg/trade {old_avg:+.2f} -> {new_avg:+.2f} SOL"

    return "CANDIDATE", (f"{len(closed)} closed, wr {rep.win_rate * 100:.0f}%, "
                         f"{rep.total_realized_sol:+.2f} SOL, hold {_fmt_hold(med_hold)}")


def suggest_trading_account(txs: list[dict], wallet: str) -> str | None:
    """When an address fee-pays swaps but never moves funds itself, find the
    account that actually trades (bot pattern: disposable signer + vault)."""
    from collections import Counter

    counts: Counter[str] = Counter()
    for tx in txs:
        if tx.get("feePayer") != wallet:
            continue
        ev = (tx.get("events") or {}).get("swap") or {}
        ni = ev.get("nativeInput") or {}
        if ni.get("account") and ni["account"] != wallet:
            counts[ni["account"]] += 1
        no = ev.get("nativeOutput") or {}
        if no.get("account") and no["account"] != wallet:
            counts[no["account"]] += 1
    if not counts:
        return None
    acct, n = counts.most_common(1)[0]
    return acct if n >= max(3, len(txs) // 4) else None


def render(rep: AuditReport) -> str:
    L: list[str] = []
    closed = rep.closed
    L.append(f"WALLET AUDIT: {rep.wallet}")
    L.append(f"  parsed swaps: {rep.n_swaps}, positions: {rep.n_positions} "
             f"({len(closed)} closed, {len(rep.open_)} still open/partial)")
    if not closed:
        L.append("  no closed round trips in window — nothing to audit honestly.")
        return "\n".join(L)

    pnls = sorted(p.realized_pnl_sol for p in closed)
    median = pnls[len(pnls) // 2]
    holds = sorted(p.hold_seconds for p in closed)
    L.append(f"  win rate: {rep.win_rate * 100:.1f}%   "
             f"realized PnL: {rep.total_realized_sol:+.2f} SOL   "
             f"median PnL/trade: {median:+.3f} SOL   "
             f"median hold: {_fmt_hold(holds[len(holds) // 2])}")

    # Concentration: how much of total PnL is the single best trade?
    best = max(p.realized_pnl_sol for p in closed)
    if rep.total_realized_sol > 0:
        L.append(f"  concentration: best trade is {best / rep.total_realized_sol * 100:.0f}% "
                 f"of total PnL (high % = luck-shaped, fragile to copy)")

    # Copyability red flags — a great record can still be useless to us
    flags = []
    fed = [p for p in closed if p.transfer_fed]
    if fed:
        flags.append(f"{len(fed)}/{len(closed)} closed positions sold more than "
                     f"they bought (transfer-fed: insider/dev/sister-wallet pattern)")
    huge = [p for p in closed if p.realized_return > 50]
    if huge:
        flags.append(f"{len(huge)} positions returned >5000% — entry prices that "
                     f"only exist at/before launch (sniper/insider, not copyable)")
    if rep.win_rate == 1.0 and len(closed) >= 10:
        flags.append("100% win rate over 10+ trades — nobody trades this well; "
                     "they KNOW (insider) or they snipe (infrastructure)")
    if flags:
        L.append("  ⚠ UNCOPYABLE-EDGE FLAGS:")
        for fl in flags:
            L.append(f"    - {fl}")

    # Decay: older half vs newer half, and the last-20 window
    half = len(closed) // 2
    if half >= 5:
        old, new = closed[:half], closed[half:]
        old_avg = sum(p.realized_pnl_sol for p in old) / len(old)
        new_avg = sum(p.realized_pnl_sol for p in new) / len(new)
        L.append(f"  decay check: older-half avg {old_avg:+.3f} SOL/trade vs "
                 f"newer-half {new_avg:+.3f} SOL/trade"
                 + ("   << EDGE DECAYING" if new_avg < old_avg * 0.5 else ""))
    last = closed[-20:]
    if len(last) >= 10:
        wr = sum(1 for p in last if p.realized_pnl_sol > 0) / len(last)
        pnl = sum(p.realized_pnl_sol for p in last)
        L.append(f"  last {len(last)} closed trades: win rate {wr * 100:.0f}%, "
                 f"PnL {pnl:+.2f} SOL")

    L.append("\n  top 5 wins / worst 5 losses (closed positions):")
    ranked = sorted(closed, key=lambda p: p.realized_pnl_sol, reverse=True)
    show = ranked if len(ranked) <= 10 else ranked[:5] + ranked[-5:]
    for p in show:
        L.append(f"    {p.mint[:8]}…  pnl {p.realized_pnl_sol:+8.3f} SOL  "
                 f"ret {p.realized_return * 100:+7.1f}%  hold {_fmt_hold(p.hold_seconds):>6}  "
                 f"swaps {p.n_swaps}")
    return "\n".join(L)
