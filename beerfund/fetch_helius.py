"""Fetch and parse a real wallet's swap history via the Helius enhanced API.

Free tier is fine for auditing: https://helius.dev -> create key, then
    export HELIUS_API_KEY=...

We use the parsed-transactions endpoint so we don't have to decode raw Solana
instructions ourselves:
    GET https://api.helius.xyz/v0/addresses/{wallet}/transactions
        ?api-key=KEY&type=SWAP&limit=100[&before=<sig>]

Every response is cached to data/cache/ so re-runs don't burn rate limits.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

WSOL_MINT = "So11111111111111111111111111111111111111112"
API_BASE = "https://api.helius.xyz/v0/addresses"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache")


@dataclass
class Swap:
    """One parsed swap by the wallet: SOL <-> some token."""

    signature: str
    timestamp: int          # unix seconds
    side: str               # "buy" (SOL -> token) or "sell" (token -> SOL)
    mint: str
    token_amount: float
    sol_amount: float


def _get(url: str, retries: int = 3) -> list | dict:
    # Cloudflare 403s the default urllib user-agent; identify ourselves instead.
    req = urllib.request.Request(url, headers={
        "User-Agent": "beerfund-research/0.1 (+wallet auditing, read-only)",
        "Accept": "application/json",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))  # rate limited: back off, retry
                continue
            raise
    raise RuntimeError("unreachable")


def fetch_swap_txs(wallet: str, api_key: str, max_pages: int = 10,
                   use_cache: bool = True) -> list[dict]:
    """Fetch up to max_pages * 100 parsed SWAP transactions, newest first."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{wallet}.json")
    if use_cache and os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    txs: list[dict] = []
    before = None
    for _ in range(max_pages):
        params = {"api-key": api_key, "type": "SWAP", "limit": "100"}
        if before:
            params["before"] = before
        url = f"{API_BASE}/{wallet}/transactions?" + urllib.parse.urlencode(params)
        page = _get(url)
        if not page:
            break
        txs.extend(page)
        before = page[-1]["signature"]
        if len(page) < 100:
            break
        time.sleep(0.5)  # be polite to the free tier

    with open(cache_path, "w") as f:
        json.dump(txs, f)
    return txs


def _sol_legs(ev: dict, wallet: str) -> tuple[float, float]:
    """SOL the wallet paid / received in this swap (native SOL or wrapped SOL)."""
    paid = received = 0.0
    ni, no = ev.get("nativeInput") or {}, ev.get("nativeOutput") or {}
    if ni.get("account") == wallet:
        paid += float(ni.get("amount", 0)) / 1e9
    if no.get("account") == wallet:
        received += float(no.get("amount", 0)) / 1e9
    for ti in ev.get("tokenInputs") or []:
        if ti.get("userAccount") == wallet and ti.get("mint") == WSOL_MINT:
            paid += float(ti["rawTokenAmount"]["tokenAmount"]) / 10 ** ti["rawTokenAmount"]["decimals"]
    for to in ev.get("tokenOutputs") or []:
        if to.get("userAccount") == wallet and to.get("mint") == WSOL_MINT:
            received += float(to["rawTokenAmount"]["tokenAmount"]) / 10 ** to["rawTokenAmount"]["decimals"]
    return paid, received


def _token_legs(ev: dict, wallet: str) -> tuple[dict[str, float], dict[str, float]]:
    """Non-SOL tokens the wallet paid / received, by mint."""
    paid: dict[str, float] = {}
    received: dict[str, float] = {}
    for ti in ev.get("tokenInputs") or []:
        if ti.get("userAccount") == wallet and ti.get("mint") != WSOL_MINT:
            amt = float(ti["rawTokenAmount"]["tokenAmount"]) / 10 ** ti["rawTokenAmount"]["decimals"]
            paid[ti["mint"]] = paid.get(ti["mint"], 0.0) + amt
    for to in ev.get("tokenOutputs") or []:
        if to.get("userAccount") == wallet and to.get("mint") != WSOL_MINT:
            amt = float(to["rawTokenAmount"]["tokenAmount"]) / 10 ** to["rawTokenAmount"]["decimals"]
            received[to["mint"]] = received.get(to["mint"], 0.0) + amt
    return paid, received


def _from_transfers(tx: dict, wallet: str) -> Swap | None:
    """Fallback: derive the swap from token transfers + the wallet's SOL delta.

    Some bots route swaps through intermediate accounts, so the parsed swap
    event never names the wallet. The wallet's own balance changes don't lie.
    """
    net_tok: dict[str, float] = {}
    wsol_flow = 0.0
    for tt in tx.get("tokenTransfers") or []:
        amt = float(tt.get("tokenAmount") or 0)
        mint = tt.get("mint")
        if tt.get("toUserAccount") == wallet:
            d = amt
        elif tt.get("fromUserAccount") == wallet:
            d = -amt
        else:
            continue
        if mint == WSOL_MINT:
            wsol_flow += d
        else:
            net_tok[mint] = net_tok.get(mint, 0.0) + d

    sol_delta = wsol_flow
    for ad in tx.get("accountData") or []:
        if ad.get("account") == wallet:
            sol_delta += float(ad.get("nativeBalanceChange", 0)) / 1e9
    if tx.get("feePayer") == wallet:
        sol_delta += float(tx.get("fee", 0)) / 1e9  # fee isn't part of the swap price

    moved = {m: a for m, a in net_tok.items() if abs(a) > 0}
    if len(moved) != 1:
        return None  # token-to-token or multi-leg: skip rather than misparse
    mint, amt = next(iter(moved.items()))

    if amt > 0 and sol_delta < 0:
        return Swap(tx["signature"], tx["timestamp"], "buy", mint, amt, -sol_delta)
    if amt < 0 and sol_delta > 0:
        return Swap(tx["signature"], tx["timestamp"], "sell", mint, -amt, sol_delta)
    return None


def parse_swaps(txs: list[dict], wallet: str) -> list[Swap]:
    """Reduce parsed transactions to clean SOL<->token swaps by this wallet.

    Tries the parsed swap event first, falls back to balance-change parsing.
    Skips token-to-token swaps and anything ambiguous — auditing only needs the
    clean majority, and a skipped trade is better than a misparsed one.
    """
    swaps: list[Swap] = []
    for tx in txs:
        if tx.get("transactionError"):
            continue
        ev = (tx.get("events") or {}).get("swap")
        parsed = None
        if ev:
            sol_paid, sol_recv = _sol_legs(ev, wallet)
            tok_paid, tok_recv = _token_legs(ev, wallet)
            if sol_paid > 0 and len(tok_recv) == 1 and not tok_paid:
                mint, amt = next(iter(tok_recv.items()))
                parsed = Swap(tx["signature"], tx["timestamp"], "buy",
                              mint, amt, sol_paid)
            elif sol_recv > 0 and len(tok_paid) == 1 and not tok_recv:
                mint, amt = next(iter(tok_paid.items()))
                parsed = Swap(tx["signature"], tx["timestamp"], "sell",
                              mint, amt, sol_recv)
        if parsed is None:
            parsed = _from_transfers(tx, wallet)
        if parsed:
            swaps.append(parsed)

    swaps.sort(key=lambda s: s.timestamp)
    return swaps
