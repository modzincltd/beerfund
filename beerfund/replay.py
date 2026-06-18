"""Real price-series replay: the last simulation gate before paper trading.

For each closed position of a target wallet:
  1. Fetch the token's on-chain trade history (every swap by every trader)
     covering [entry - 10min, exit + 5min] by paginating backwards.
  2. Rebuild the price path from those swaps: price = SOL leg / token leg.
  3. Replay our copy strategy against that REAL path — entry lag, exit rules,
     fees, impact — and compare against what the wallet itself made.

Coverage is reported honestly: if we couldn't paginate far enough back, or the
token printed no trades near the entry, the position is SKIPPED, not faked.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from .fetch_helius import API_BASE, CACHE_DIR, WSOL_MINT, _get, Swap
from .models import PriceSeries, WalletTrade

import urllib.parse

DEXSCREENER = "https://api.dexscreener.com/latest/dex/tokens/"
GECKO = "https://api.geckoterminal.com/api/v2"
POOLS_CACHE = os.path.join(CACHE_DIR, "pools.json")


def resolve_pools_gecko(mint: str) -> list[dict]:
    """Fallback pool resolution via GeckoTerminal — still lists delisted rugs.

    Only SOL-quoted pools are returned; depth is estimated as half the pool's
    USD reserve converted at the quote token's USD price.
    """
    try:
        data = _get(f"{GECKO}/networks/solana/tokens/{mint}/pools")
    except Exception:
        return []
    pools = []
    for p in data.get("data") or []:
        a = p.get("attributes") or {}
        name = a.get("name") or ""
        if not name.endswith("/ SOL"):
            continue
        depth = None
        try:
            reserve = float(a.get("reserve_in_usd") or 0)
            sol_usd = float(a.get("quote_token_price_usd") or 0)
            if reserve > 0 and sol_usd > 0:
                depth = reserve / 2.0 / sol_usd
        except (TypeError, ValueError):
            pass
        pools.append({"pair": a["address"], "dex": "gecko", "depth_sol": depth})
    return pools


def fetch_candles(pool: str, t_start: float, t_end: float,
                  use_cache: bool = True) -> list[tuple[float, float]]:
    """Minute OHLCV from GeckoTerminal -> price observations in SOL.

    Each candle contributes (ts, open) and (ts+59, close). Intra-minute highs
    and lows are NOT observable, so simulated stops fire a touch late and TPs
    a touch early — net effect is mildly conservative on winners and mildly
    optimistic on stop-loss fills. Good enough for a go/no-go verdict.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"candles_{pool}.json")
    candles: dict[str, list] = {}
    if use_cache and os.path.exists(cache_path):
        candles = json.load(open(cache_path))

    have = sorted(float(t) for t in candles)
    if not have or min(have) > t_start or max(have) < t_end - 120:
        before = int(t_end) + 60
        for _ in range(12):  # 12 pages x 1000 minute-candles ≈ 8 days
            url = (f"{GECKO}/networks/solana/pools/{pool}/ohlcv/minute"
                   f"?aggregate=1&limit=1000&currency=token"
                   f"&before_timestamp={before}")
            try:
                data = _get(url)
            except Exception:
                break
            rows = ((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
            if not rows:
                break
            for ts, o, h, l, c, v in rows:
                candles[str(int(ts))] = [o, c]
            oldest = min(int(r[0]) for r in rows)
            if oldest <= t_start:
                break
            before = oldest
            time.sleep(0.6)  # GeckoTerminal free tier: ~30 calls/min
        with open(cache_path, "w") as f:
            json.dump(candles, f)

    points: list[tuple[float, float]] = []
    for ts_str, (o, c) in candles.items():
        ts = float(ts_str)
        if t_start <= ts <= t_end:
            points.append((ts, float(o)))
            points.append((ts + 59.0, float(c)))
    points.sort()
    return points


def resolve_pools(mint: str) -> list[dict]:
    """Token mint -> its DEX pools via DexScreener (free, keyless).

    Swap txs involve the POOL's accounts, not the mint, so price history must
    be fetched from pool addresses. Returns [{pair, dex, depth_sol}] sorted by
    liquidity (DexScreener's default order). depth_sol is the CURRENT SOL side
    of the pool — decent impact estimate, but it is today's depth, not the
    depth at trade time.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache: dict = {}
    if os.path.exists(POOLS_CACHE):
        cache = json.load(open(POOLS_CACHE))
    if mint in cache:
        return cache[mint]

    data = _get(DEXSCREENER + mint)
    pools = []
    for p in data.get("pairs") or []:
        if p.get("chainId") != "solana":
            continue
        depth = None
        if (p.get("quoteToken") or {}).get("symbol", "").upper() in ("SOL", "WSOL"):
            depth = (p.get("liquidity") or {}).get("quote")
        pools.append({"pair": p["pairAddress"], "dex": p.get("dexId"),
                      "depth_sol": depth})
    cache[mint] = pools
    with open(POOLS_CACHE, "w") as f:
        json.dump(cache, f)
    return pools


def fetch_mint_window(mint: str, api_key: str, t_start: float, t_end: float,
                      max_pages: int = 60, use_cache: bool = True,
                      tx_type: str | None = "SWAP") -> tuple[list[dict], bool]:
    """Paginate an address's txs backwards until we cover t_start.

    Returns (txs_within_window, reached_start). Pass tx_type=None for pump.fun
    bonding curves — Helius types their trades UNKNOWN, so a SWAP filter
    silently returns nothing.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    suffix = tx_type or "all"
    cache_path = os.path.join(CACHE_DIR, f"mint_{mint}_{suffix}.json")
    if use_cache and os.path.exists(cache_path):
        txs = json.load(open(cache_path))
        if txs and min(t["timestamp"] for t in txs) <= t_start:
            window = [t for t in txs if t_start <= t["timestamp"] <= t_end]
            return window, True

    txs: list[dict] = []
    before = None
    reached = False
    for _ in range(max_pages):
        params = {"api-key": api_key, "limit": "100"}
        if tx_type:
            params["type"] = tx_type
        if before:
            params["before"] = before
        url = f"{API_BASE}/{mint}/transactions?" + urllib.parse.urlencode(params)
        page = _get(url)
        if not page:
            break
        txs.extend(page)
        page_min = min(t["timestamp"] for t in page)
        before = page[-1]["signature"]
        if page_min <= t_start:
            reached = True
            break
        if len(page) < 100:
            break
        time.sleep(0.4)

    with open(cache_path, "w") as f:
        json.dump(txs, f)
    window = [t for t in txs if t_start <= t["timestamp"] <= t_end]
    return window, reached


def parse_mint_trades(txs: list[dict], mint: str,
                      focus: str | None = None) -> list[tuple[float, float]]:
    """(timestamp, price-in-SOL) for every parseable swap of this mint.

    Tries the parsed swap event first; falls back to raw token/native
    transfers (pump.fun and PumpSwap txs carry no events.swap). `focus` is the
    pool/curve address — used to attribute native-SOL legs to the trade.
    """
    points: list[tuple[float, float]] = []
    for tx in txs:
        if tx.get("transactionError"):
            continue
        tok = 0.0
        sol = 0.0
        ev = (tx.get("events") or {}).get("swap")
        if ev:
            for leg in (ev.get("tokenInputs") or []) + (ev.get("tokenOutputs") or []):
                raw = leg.get("rawTokenAmount") or {}
                amt = float(raw.get("tokenAmount", 0)) / 10 ** raw.get("decimals", 0)
                if leg.get("mint") == mint:
                    tok += amt
                elif leg.get("mint") == WSOL_MINT:
                    sol += amt
            for native in (ev.get("nativeInput"), ev.get("nativeOutput")):
                if native and native.get("amount"):
                    sol += float(native["amount"]) / 1e9
        if tok <= 1e-9 or sol < 0.001:  # no/partial event: read raw transfers
            tok = sol = 0.0
            for tt in tx.get("tokenTransfers") or []:
                amt = float(tt.get("tokenAmount") or 0)
                if tt.get("mint") == mint:
                    tok += amt
                elif tt.get("mint") == WSOL_MINT:
                    sol += amt
            if sol < 0.001 and focus:
                for nt in tx.get("nativeTransfers") or []:
                    if focus in (nt.get("fromUserAccount"), nt.get("toUserAccount")):
                        sol += float(nt.get("amount", 0)) / 1e9
        if tok > 1e-9 and sol >= 0.001:  # ignore dust prints
            points.append((float(tx["timestamp"]), sol / tok))
    points.sort()
    return points


@dataclass
class ReplayTrade:
    """The wallet's round trip, reconstructed at swap level for the replay."""

    mint: str
    wallet_trade: WalletTrade
    n_obs: int = 0
    covered: bool = False


def closed_round_trips(swaps: list[Swap]) -> list[ReplayTrade]:
    """First-buy -> last-sell round trips per mint, skipping transfer-fed ones."""
    by_mint: dict[str, list[Swap]] = {}
    for s in swaps:
        by_mint.setdefault(s.mint, []).append(s)

    out: list[ReplayTrade] = []
    for mint, ss in by_mint.items():
        buys = [s for s in ss if s.side == "buy"]
        sells = [s for s in ss if s.side == "sell"]
        if not buys or not sells:
            continue
        bought = sum(s.token_amount for s in buys)
        sold = sum(s.token_amount for s in sells)
        if sold < bought * 0.95 or sold > bought * 1.05:  # open or transfer-fed
            continue
        first_buy = buys[0]
        last_sell = sells[-1]
        if last_sell.timestamp <= first_buy.timestamp:
            continue
        wt = WalletTrade(
            token=mint,
            entry_t=float(first_buy.timestamp),
            entry_price=first_buy.sol_amount / first_buy.token_amount,
            exit_t=float(last_sell.timestamp),
            exit_price=last_sell.sol_amount / last_sell.token_amount,
        )
        out.append(ReplayTrade(mint=mint, wallet_trade=wt))
    out.sort(key=lambda r: r.wallet_trade.entry_t)
    return out


def clean_points(points: list[tuple[float, float]],
                 max_ratio: float = 8.0) -> list[tuple[float, float]]:
    """Drop lone absurd prints (broken dust pools, mis-scaled routes).

    A real pump climbs across many consecutive observations; a bad print is a
    single point sitting far off its neighbours. Keep a point only if it's
    within max_ratio of the median of its 7-point neighbourhood.
    """
    if len(points) < 5:
        return points
    out = []
    for i, (t, p) in enumerate(points):
        lo = max(0, i - 3)
        nbrs = sorted(q for _, q in points[lo:i + 4])
        med = nbrs[len(nbrs) // 2]
        if med > 0 and 1.0 / max_ratio <= p / med <= max_ratio:
            out.append((t, p))
    return out


def build_series(points: list[tuple[float, float]]) -> PriceSeries:
    series = PriceSeries()
    for t, p in points:
        series.append(t, p)
    return series
