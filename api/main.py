#!/usr/bin/env python3
"""Beer Fund Bot — read-only REST + AI API.

Serves the Postgres read model to the Next.js frontend. Read-only by design:
no endpoint mutates trading state (the workers own that). The only writes are
to discovery_candidates (adding names to audit) and the insights cache.

Run (from repo root):
    pip install -r api/requirements.txt
    export DATABASE_URL=postgresql://beerfund:beerfund@localhost:5432/beerfund
    export ANTHROPIC_API_KEY=...        # only needed for /chat and /insights
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import queries

app = FastAPI(title="Beer Fund Bot API", version="1.0")

# Vercel frontend origin(s). Comma-separated in $CORS_ORIGINS, "*" for dev.
_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    # Liveness only — deliberately does NOT touch the DB. The platform health
    # check hits this; if it depended on Postgres, a transient DB blip (or a
    # not-yet-propagated DATABASE_URL) would crash-loop the whole API. DB
    # connectivity is checked separately at /ready.
    return {"ok": True}


@app.get("/ready")
def ready() -> dict:
    try:
        queries.db.fetch_one("SELECT 1 AS ok")
        return {"ok": True, "db": True}
    except Exception as e:
        raise HTTPException(503, f"db unavailable: {e}")


@app.get("/summary")
def summary() -> dict:
    return queries.summary()


@app.get("/criteria")
def criteria() -> dict:
    return queries.criteria()


@app.get("/drawdown")
def drawdown() -> dict:
    return queries.drawdown_sizes()


@app.get("/positions")
def positions() -> list[dict]:
    return queries.positions()


@app.get("/paper/positions")
def paper_positions() -> list[dict]:
    return queries.paper_positions()


# ---- manual paper trades (UI-entered) --------------------------------------
# Still zero-capital: every fill is a live Jupiter quote; no keys, no real
# transaction. Manual positions carry manual=true so the copy daemon never
# touches them; realized PnL is unified from the trade log (see queries.summary).

class BuyRequest(BaseModel):
    mint: str
    size_sol: float = 0.5


class SellRequest(BaseModel):
    mint: str


@app.post("/paper/buy")
def paper_buy(req: BuyRequest) -> dict:
    import time, datetime as dtm
    from paper_trader import jup_quote, SOL_MINT, PRIORITY_FEE
    from beerfund import db as bdb, paper_store
    mint = req.mint.strip()
    if len(mint) < 32:
        raise HTTPException(400, "invalid token mint")
    size = float(req.size_sol or 0)
    if size <= 0:
        raise HTTPException(400, "size_sol must be > 0")
    if bdb.fetch_one("SELECT 1 AS x FROM positions WHERE mint=%s", (mint,)):
        raise HTTPException(409, "a position for this token is already open")
    q = jup_quote(SOL_MINT, mint, int(size * 1e9))
    if not q or "outAmount" not in q:
        raise HTTPException(502, "no Jupiter route for this token right now")
    tokens = int(q["outAmount"])
    if tokens <= 0:
        raise HTTPException(502, "Jupiter returned a zero quote")
    price = size / tokens
    cost = size + PRIORITY_FEE
    now = int(time.time())
    ts = dtm.datetime.fromtimestamp(now, tz=dtm.timezone.utc)
    with bdb.connect() as conn:
        conn.execute(
            """INSERT INTO positions (mint, wallet, entry_ts, tokens, entry_price, peak,
                                      remaining, rung, banked_sol, cost_sol, manual, updated_at)
               VALUES (%s, 'manual', %s, %s, %s, %s, 1.0, 0, 0.0, %s, true, now())""",
            (mint, ts, tokens, price, price, cost),
        )
    paper_store.log_trade({"ts": now, "event": "ENTRY", "mint": mint, "wallet": "manual",
                           "fraction": 1.0, "sol": size, "tokens": tokens,
                           "price": f"{price:.3e}", "reason": "manual", "pnl_sol": ""})
    return {"ok": True, "mint": mint, "tokens": tokens, "price": price, "size_sol": size}


@app.post("/paper/sell")
def paper_sell(req: SellRequest) -> dict:
    import time
    from paper_trader import jup_quote, SOL_MINT, PRIORITY_FEE
    from beerfund import db as bdb, paper_store
    mint = req.mint.strip()
    pos = bdb.fetch_one("SELECT * FROM positions WHERE mint=%s AND manual=true", (mint,))
    if not pos:
        raise HTTPException(404, "no manual position for this token (the daemon manages its own exits)")
    rem_tokens = int(int(pos["tokens"]) * float(pos["remaining"]))
    q = jup_quote(mint, SOL_MINT, rem_tokens) if rem_tokens > 0 else None
    if q and "outAmount" in q:
        gross = int(q["outAmount"]) / 1e9
        price = gross / rem_tokens if rem_tokens else 0.0
    else:
        gross, price = 0.0, 0.0  # unroutable: token is dead, no bid
    sol_out = max(gross - PRIORITY_FEE, 0.0)
    pnl = sol_out - float(pos["cost_sol"])
    now = int(time.time())
    paper_store.log_trade({"ts": now, "event": "EXIT", "mint": mint, "wallet": "manual",
                           "fraction": 1.0, "sol": f"{sol_out:.4f}", "tokens": "",
                           "price": f"{price:.3e}", "reason": "manual", "pnl_sol": ""})
    paper_store.log_trade({"ts": now, "event": "CLOSE", "mint": mint, "wallet": "manual",
                           "fraction": "", "sol": "", "tokens": "", "price": "",
                           "reason": "manual", "pnl_sol": f"{pnl:+.4f}"})
    with bdb.connect() as conn:
        conn.execute("DELETE FROM positions WHERE mint=%s AND manual=true", (mint,))
    return {"ok": True, "mint": mint, "sol_out": sol_out, "pnl_sol": pnl}


@app.get("/trades")
def trades(limit: int = 200, mint: str | None = None) -> list[dict]:
    return queries.trades(limit=min(limit, 1000), mint=mint)


@app.get("/wallets")
def wallets() -> list[dict]:
    return queries.wallets()


@app.get("/wallets/{wallet}")
def wallet_detail(wallet: str) -> dict:
    d = queries.wallet_detail(wallet)
    if not d:
        raise HTTPException(404, "no audit for that wallet yet")
    return d


@app.get("/wallets/{wallet}/balances")
def wallet_balances(wallet: str) -> dict:
    """Live SOL + token holdings from Helius (read-only)."""
    import os
    from beerfund import db as bdb, fetch_helius
    bdb._load_dotenv()
    key = os.environ.get("HELIUS_API_KEY")
    if not key:
        raise HTTPException(503, "HELIUS_API_KEY not set on the API host")
    try:
        return fetch_helius.fetch_balances(wallet, key)
    except Exception as e:
        raise HTTPException(502, f"balance fetch failed: {e}")


@app.get("/coins")
def coins(limit: int = 200) -> list[dict]:
    return queries.coins(limit=min(limit, 1000))


@app.get("/coins/{mint}")
def coin_detail(mint: str) -> dict:
    return queries.coin_detail(mint)


@app.get("/discovery")
def discovery() -> list[dict]:
    return queries.discovery()


class DiscoveryRunRequest(BaseModel):
    gmgn: str | None = None          # GMGN window (1d|7d|30d) or null to skip
    wallets: list[str] = []          # manual addresses pasted in the UI


@app.post("/discovery/run")
def discovery_run(req: DiscoveryRunRequest, background: BackgroundTasks) -> dict:
    """Kick off discovery (GMGN best-effort + manual adds) and audit, in the
    background. Returns immediately; the UI polls /discovery + /discovery/status."""
    from . import discovery as disc
    if not disc.try_begin():
        return {"started": False, "running": True,
                "message": "a discovery run is already in progress"}
    background.add_task(disc.run_all, req.gmgn, req.wallets)
    src = req.gmgn and f"GMGN {req.gmgn}" or None
    bits = [b for b in (src, f"{len(req.wallets)} pasted" if req.wallets else None) if b]
    return {"started": True,
            "message": f"discovery started ({', '.join(bits) or 'no sources'}); "
                       f"results appear as wallets are audited"}


@app.get("/discovery/status")
def discovery_status() -> dict:
    from . import discovery as disc
    return disc.status()


# ---- wallet labels + tags (user annotations) --------------------------------

@app.get("/labels")
def labels() -> list[dict]:
    return queries.labels()


class LabelRequest(BaseModel):
    wallet: str
    label: str | None = None
    tags: list[str] = []


@app.post("/labels")
def set_label(req: LabelRequest) -> dict:
    if len(req.wallet) < 32:
        raise HTTPException(400, "invalid wallet address")
    label = (req.label or "").strip()[:80] or None
    tags = []
    seen = set()
    for t in req.tags:
        t = t.strip()[:24]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
        if len(tags) >= 12:
            break
    return queries.set_label(req.wallet, label, tags)


# ---- tunable criteria (Settings page) --------------------------------------

def _clamp(d: dict, key, default, lo, hi, cast=float):
    try:
        v = cast(d.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


@app.get("/settings")
def get_settings() -> dict:
    from beerfund import settings
    return settings.load()


class SettingsRequest(BaseModel):
    audit: dict | None = None
    golive: dict | None = None


@app.post("/settings")
def post_settings(req: SettingsRequest) -> dict:
    from beerfund import settings
    cur = settings.load()
    a = {**cur["audit"], **(req.audit or {})}
    g = {**cur["golive"], **(req.golive or {})}
    clean = {
        "audit": {
            "min_closed": _clamp(a, "min_closed", 8, 1, 100000, int),
            "insider_return_x": _clamp(a, "insider_return_x", 50.0, 1, 1e6),
            "min_median_hold_s": _clamp(a, "min_median_hold_s", 600, 0, 604800, int),
            "decay_ratio": _clamp(a, "decay_ratio", 0.5, 0.0, 1.0),
        },
        "golive": {
            "min_filled": _clamp(g, "min_filled", 20, 1, 100000, int),
            "min_weeks": _clamp(g, "min_weeks", 2.0, 0, 520),
            "max_drawdown_sizes": _clamp(g, "max_drawdown_sizes", 6.0, 0, 100000),
            "min_passing_wallets": _clamp(g, "min_passing_wallets", 2, 0, 100000, int),
        },
    }
    return settings.save(clean)


# ---- AI -------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    from . import ai
    try:
        return ai.chat([m.model_dump() for m in req.messages])
    except RuntimeError as e:          # missing key etc.
        raise HTTPException(400, str(e))


@app.get("/insights")
def insights() -> list[dict]:
    from . import ai
    return ai.latest_insights()


class InsightRequest(BaseModel):
    kind: str


@app.post("/insights/generate")
def generate_insight(req: InsightRequest) -> dict:
    from . import ai
    try:
        return ai.generate_insight(req.kind)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
