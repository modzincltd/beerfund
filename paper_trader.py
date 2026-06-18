#!/usr/bin/env python3
"""Live paper-trading daemon. Zero capital — every fill is a Jupiter quote.

Follows real wallets in real time. When a followed wallet buys a token, we
"buy" at the price Jupiter would ACTUALLY fill us at right now (their quote
includes route fees and price impact), then manage the position with our
mechanical exit rules, marking exits at live sell-quotes. Everything is logged
so paper results can later be compared against real execution.

Usage:
    python3 paper_trader.py <WALLET> [more wallets...]
        [--size 0.5] [--poll 15] [--min-signal-sol 1.0] [--max-positions 8]

Stop with Ctrl-C — state survives restarts (data/paper/state.json).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from beerfund.fetch_helius import parse_swaps
from beerfund.rules import ExitRules
from run_audit import load_dotenv

SOL_MINT = "So11111111111111111111111111111111111111112"
JUP = "https://lite-api.jup.ag/swap/v1/quote"
HELIUS = "https://api.helius.xyz/v0/addresses"
PRIORITY_FEE = 0.001  # SOL per simulated transaction

STATE_PATH = "data/paper/state.json"
TRADES_CSV = "results/paper_trades.csv"


def http_json(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "beerfund-paper/0.1 (read-only research)",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"    [warn] {type(e).__name__} on {url[:60]}…", file=sys.stderr)
        return None


def jup_quote(in_mint: str, out_mint: str, amount: int) -> dict | None:
    q = urllib.parse.urlencode({"inputMint": in_mint, "outputMint": out_mint,
                                "amount": amount, "slippageBps": 100})
    d = http_json(f"{JUP}?{q}")
    return d if d and "outAmount" in d else None


def ds_price_sol(mint: str) -> float | None:
    """DexScreener fallback price when Jupiter can't route (dying tokens)."""
    d = http_json(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    for p in (d or {}).get("pairs") or []:
        if (p.get("quoteToken") or {}).get("symbol", "").upper() in ("SOL", "WSOL"):
            try:
                return float(p["priceNative"])
            except (KeyError, ValueError):
                continue
    return None


def log_trade(row: dict) -> None:
    new = not os.path.exists(TRADES_CSV)
    with open(TRADES_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "event", "mint", "wallet",
                                          "fraction", "sol", "tokens", "price",
                                          "reason", "pnl_sol"])
        if new:
            w.writeheader()
        w.writerow(row)


class Daemon:
    def __init__(self, wallets: list[str], api_key: str, size: float,
                 min_signal: float, max_positions: int, rules: ExitRules):
        self.wallets = wallets
        self.api_key = api_key
        self.size = size
        self.min_signal = min_signal
        self.max_positions = max_positions
        self.rules = rules
        # On a server with Postgres (e.g. DO App Platform, whose disk is
        # ephemeral) persist state to the DB so it survives redeploys; otherwise
        # keep the stdlib-only local-file behaviour.
        self.use_db = bool(os.environ.get("DATABASE_URL"))
        self.store = None
        default = {"last_sig": {}, "positions": {}, "realized_sol": 0.0,
                   "n_closed": 0, "n_skipped": 0}
        if self.use_db:
            from beerfund import paper_store
            self.store = paper_store
            self.state = self.store.load_state()
        else:
            self.state = default
            if os.path.exists(STATE_PATH):
                self.state = json.load(open(STATE_PATH))

    def save(self) -> None:
        if self.use_db:
            self.store.save_state(self.state)
            return
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=1)

    def _log(self, row: dict) -> None:
        if self.use_db:
            self.store.log_trade(row)
        else:
            log_trade(row)

    # ---- signal detection ----
    def poll_wallet(self, wallet: str) -> None:
        url = (f"{HELIUS}/{wallet}/transactions?"
               + urllib.parse.urlencode({"api-key": self.api_key,
                                         "type": "SWAP", "limit": "20"}))
        txs = http_json(url)
        if not isinstance(txs, list) or not txs:
            return
        last = self.state["last_sig"].get(wallet)
        if last is None:  # first run: arm without replaying history
            self.state["last_sig"][wallet] = txs[0]["signature"]
            return
        fresh = []
        for tx in txs:
            if tx["signature"] == last:
                break
            fresh.append(tx)
        if not fresh:
            return
        self.state["last_sig"][wallet] = txs[0]["signature"]
        for swap in parse_swaps(fresh, wallet):
            if swap.side != "buy" or swap.sol_amount < self.min_signal:
                continue
            self.enter(wallet, swap.mint,
                       wallet_price=swap.sol_amount / swap.token_amount)

    # ---- entries ----
    def enter(self, wallet: str, mint: str, wallet_price: float) -> None:
        if mint in self.state["positions"]:
            return
        if len(self.state["positions"]) >= self.max_positions:
            print(f"  SKIP {mint[:8]}… (position cap)")
            return
        q = jup_quote(SOL_MINT, mint, int(self.size * 1e9))
        if not q:
            print(f"  SKIP {mint[:8]}… (no Jupiter route)")
            self.state["n_skipped"] += 1
            return
        tokens = int(q["outAmount"])  # raw units; consistent for resale quotes
        eff_price = self.size / tokens
        # Chase guard: wallet_price is SOL per UI token, ours per raw unit, so
        # the units aren't comparable. Quoted price impact is the executable
        # proxy: refuse entries where our own fill would cost more than 8%.
        impact = abs(float(q.get("priceImpactPct") or 0))
        if impact > 0.08:
            print(f"  SKIP {mint[:8]}… (impact {impact * 100:.1f}% — thin pool)")
            self.state["n_skipped"] += 1
            return
        now = time.time()
        self.state["positions"][mint] = {
            "wallet": wallet, "entry_ts": now, "tokens": tokens,
            "entry_price": eff_price, "peak": eff_price, "remaining": 1.0,
            "rung": 0, "banked_sol": 0.0,
            "cost_sol": self.size + PRIORITY_FEE,
        }
        self._log({"ts": int(now), "event": "ENTRY", "mint": mint,
                   "wallet": wallet[:8], "fraction": 1.0, "sol": self.size,
                   "tokens": tokens, "price": f"{eff_price:.3e}",
                   "reason": "copy", "pnl_sol": ""})
        print(f"  ENTRY {mint[:8]}… {self.size} SOL "
              f"(copying {wallet[:6]}…, impact {impact * 100:.2f}%)")

    # ---- exits ----
    def sell_fraction(self, mint: str, frac: float, price: float,
                      reason: str) -> None:
        pos = self.state["positions"][mint]
        frac = min(frac, pos["remaining"])
        sol_out = pos["tokens"] * frac * price - PRIORITY_FEE
        pos["banked_sol"] += max(sol_out, 0.0)
        pos["remaining"] = round(pos["remaining"] - frac, 9)
        self._log({"ts": int(time.time()), "event": "EXIT", "mint": mint,
                   "wallet": pos["wallet"][:8], "fraction": frac,
                   "sol": f"{max(sol_out, 0):.4f}", "tokens": "",
                   "price": f"{price:.3e}", "reason": reason, "pnl_sol": ""})
        if pos["remaining"] <= 1e-9:
            pnl = pos["banked_sol"] - pos["cost_sol"]
            self.state["realized_sol"] += pnl
            self.state["n_closed"] += 1
            self._log({"ts": int(time.time()), "event": "CLOSE", "mint": mint,
                       "wallet": pos["wallet"][:8], "fraction": "", "sol": "",
                       "tokens": "", "price": "", "reason": reason,
                       "pnl_sol": f"{pnl:+.4f}"})
            print(f"  CLOSE {mint[:8]}… {reason} pnl {pnl:+.4f} SOL "
                  f"(total {self.state['realized_sol']:+.4f})")
            del self.state["positions"][mint]
        else:
            print(f"  EXIT  {mint[:8]}… {frac * 100:.0f}% @ {reason}")

    def manage(self, mint: str) -> None:
        pos = self.state["positions"][mint]
        r = self.rules
        rem_tokens = int(pos["tokens"] * pos["remaining"])
        if rem_tokens <= 0:
            return
        q = jup_quote(mint, SOL_MINT, rem_tokens)
        if q:
            price = int(q["outAmount"]) / 1e9 / rem_tokens
        elif ds_price_sol(mint) is None:
            # unroutable on Jupiter AND unlisted on DexScreener: token is dead,
            # and dead tokens have no bid — write the position off at zero
            self.sell_fraction(mint, pos["remaining"], 0.0, "dead")
            return
        else:
            # unroutable but still listed (DS price is per UI token — wrong
            # units for our raw-unit ledger): hold at entry price this cycle
            price = pos["entry_price"]
        mult = price / pos["entry_price"]
        pos["peak"] = max(pos["peak"], price)

        if mult <= 1.0 - r.stop_loss_pct:
            self.sell_fraction(mint, pos["remaining"], price, "stop")
            return
        if pos["rung"] > 0 and r.trailing_stop_pct is not None \
                and price <= pos["peak"] * (1.0 - r.trailing_stop_pct):
            self.sell_fraction(mint, pos["remaining"], price, "trail")
            return
        while pos["rung"] < len(r.take_profits) \
                and mult >= r.take_profits[pos["rung"]][0]:
            frac = r.take_profits[pos["rung"]][1]
            pos["rung"] += 1
            self.sell_fraction(mint, frac, price, f"tp{pos['rung']}")
            if mint not in self.state["positions"]:
                return
        if time.time() - pos["entry_ts"] > r.max_hold_s:
            self.sell_fraction(mint, pos["remaining"], price, "max_hold")

    # ---- main loop ----
    def run(self, poll_s: float) -> None:
        print(f"paper daemon up: following {len(self.wallets)} wallet(s), "
              f"size {self.size} SOL, rules: stop -{self.rules.stop_loss_pct:.0%} "
              f"tp {self.rules.take_profits} trail {self.rules.trailing_stop_pct} "
              f"max {self.rules.max_hold_s / 60:.0f}m")
        while True:
            try:
                for w in self.wallets:
                    self.poll_wallet(w)
                    time.sleep(0.3)
                for mint in list(self.state["positions"]):
                    self.manage(mint)
                    time.sleep(0.3)
                self.save()
                open_n = len(self.state["positions"])
                print(f"[{time.strftime('%H:%M:%S')}] open={open_n} "
                      f"closed={self.state['n_closed']} "
                      f"skipped={self.state['n_skipped']} "
                      f"realized={self.state['realized_sol']:+.4f} SOL")
                time.sleep(poll_s)
            except KeyboardInterrupt:
                self.save()
                print("\nstate saved — bye")
                return


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def main() -> None:
    # Env (set by the systemd EnvironmentFile on the server) supplies defaults;
    # explicit CLI args still win for hand-runs.
    load_dotenv()
    env_wallets = os.environ.get("WALLETS", "").split()

    ap = argparse.ArgumentParser()
    ap.add_argument("wallets", nargs="*", default=env_wallets,
                    help="wallet addresses (falls back to $WALLETS)")
    ap.add_argument("--size", type=float, default=_env_float("PAPER_SIZE", 0.5))
    ap.add_argument("--poll", type=float, default=_env_float("PAPER_POLL", 15.0))
    ap.add_argument("--min-signal-sol", type=float,
                    default=_env_float("PAPER_MIN_SIGNAL", 1.0),
                    help="ignore the wallet's buys smaller than this")
    ap.add_argument("--max-positions", type=int,
                    default=int(_env_float("PAPER_MAX_POSITIONS", 8)))
    args = ap.parse_args()
    wallets = args.wallets or env_wallets
    if not wallets:
        sys.exit("no wallets given (pass as args or set WALLETS in the env)")

    api_key = os.environ.get("HELIUS_API_KEY")
    if not api_key:
        sys.exit("HELIUS_API_KEY not set")
    os.makedirs("results", exist_ok=True)
    Daemon(wallets, api_key, args.size, args.min_signal_sol,
           args.max_positions, ExitRules()).run(args.poll)


if __name__ == "__main__":
    main()
