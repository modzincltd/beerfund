"""AI layer: chat over the live read model + auto-generated insight panels.

Uses Anthropic with a small set of READ-ONLY tools. The model can pull live
numbers (summary, criteria, wallet audits, coins, trades) or run a guarded
single-statement SELECT — it can never write, and the workers' state is never
touched. Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import os
import re

from beerfund import db
from . import queries

MODEL = os.environ.get("BEERFUND_AI_MODEL", "claude-sonnet-4-6")

SYSTEM = """You are the analyst for "Beer Fund Bot", a ZERO-CAPITAL research
project that paper-trades Solana copy-trades. Honesty over hopium: model fees,
slippage and lag; if a result looks too good, suspect the simulation. Never
suggest signing transactions or risking real capital — this is research.

You have read-only tools over a live Postgres read model fed by the paper
daemon and the wallet auditor. Always ground answers in tool data, cite the
concrete numbers, and flag when the sample is too small to conclude. Verdict
codes: CANDIDATE (copyable), DECAYING, THIN (too few trades), TOOFAST (median
hold dies in copy lag), LOSER, INSIDER (transfer-fed / launch-price / 100%% wr).
Be concise and direct."""

# Read-only tool schemas exposed to the model.
TOOLS = [
    {"name": "get_summary", "description": "Live paper-trading totals: realized PnL, "
     "filled/closed/skipped counts, open positions, position size, first/last trade.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_criteria", "description": "Evaluate the four go-live criteria with "
     "current numbers (duration+filled, net-positive PnL, drawdown in position-sizes, "
     "≥2 follow-pool wallets passing audit).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_wallets", "description": "Latest audit report card for every audited "
     "wallet (verdict, win rate, realized SOL, decay).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_wallet", "description": "Full latest audit for one wallet incl. its "
     "closed/open positions and verdict history.",
     "input_schema": {"type": "object", "properties": {
         "wallet": {"type": "string"}}, "required": ["wallet"]}},
    {"name": "list_coins", "description": "Coin rollup: appearances across audits, paper "
     "trades, risk flags, cached price/liquidity.",
     "input_schema": {"type": "object", "properties": {
         "limit": {"type": "integer"}}}},
    {"name": "get_coin", "description": "One token: which wallets traded it and how, plus "
     "our paper trades on it.",
     "input_schema": {"type": "object", "properties": {
         "mint": {"type": "string"}}, "required": ["mint"]}},
    {"name": "recent_trades", "description": "Most recent paper trade log rows (ENTRY/EXIT/CLOSE).",
     "input_schema": {"type": "object", "properties": {
         "limit": {"type": "integer"}}}},
    {"name": "sql_select", "description": "Run ONE read-only SELECT against the read model "
     "(tables: trades, positions, paper_state, wallet_audits, audit_positions, coins, "
     "discovery_candidates, insights). Use for anything the other tools don't cover.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}}, "required": ["query"]}},
]

_SELECT_OK = re.compile(r"^\s*select\b", re.IGNORECASE)
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|copy)\b",
                        re.IGNORECASE)


def _safe_select(q: str) -> list[dict]:
    if ";" in q.strip().rstrip(";"):
        raise ValueError("only a single statement is allowed")
    if not _SELECT_OK.match(q) or _FORBIDDEN.search(q):
        raise ValueError("only read-only SELECT queries are allowed")
    if " limit " not in q.lower():
        q = q.rstrip().rstrip(";") + " LIMIT 200"
    return db.fetch_all(q)


def run_tool(name: str, args: dict) -> object:
    if name == "get_summary":
        return queries.summary()
    if name == "get_criteria":
        return queries.criteria()
    if name == "list_wallets":
        return queries.wallets()
    if name == "get_wallet":
        return queries.wallet_detail(args["wallet"])
    if name == "list_coins":
        return queries.coins(limit=args.get("limit", 100))
    if name == "get_coin":
        return queries.coin_detail(args["mint"])
    if name == "recent_trades":
        return queries.trades(limit=args.get("limit", 50))
    if name == "sql_select":
        return _safe_select(args["query"])
    raise ValueError(f"unknown tool {name}")


def _client():
    try:
        import anthropic
    except ImportError as e:  # treat as "AI unavailable", not a server crash
        raise RuntimeError(
            "anthropic SDK not installed — `pip install anthropic` on the API host"
        ) from e
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set on the API host")
    return anthropic.Anthropic(api_key=key)


def _default(o):
    import datetime as dt
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    return str(o)


def chat(messages: list[dict], max_steps: int = 6) -> dict:
    """Run a tool-use loop. messages = [{role, content}]. Returns final text + trace."""
    client = _client()
    convo = [{"role": m["role"], "content": m["content"]} for m in messages]
    trace = []
    for _ in range(max_steps):
        resp = client.messages.create(
            model=MODEL, max_tokens=1500, system=SYSTEM, tools=TOOLS, messages=convo
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"reply": text, "trace": trace, "model": MODEL}
        convo.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            try:
                out = run_tool(b.name, b.input or {})
                payload = json.dumps(out, default=_default)[:12000]
            except Exception as e:
                payload = json.dumps({"error": str(e)})
            trace.append({"tool": b.name, "input": b.input})
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": payload})
        convo.append({"role": "user", "content": results})
    return {"reply": "(stopped: too many tool steps)", "trace": trace, "model": MODEL}


# ---- auto-insight panels ----------------------------------------------------

INSIGHT_PROMPTS = {
    "summary": "Give a 3-4 sentence status read on the whole experiment: are we on "
               "track for the go-live criteria, and what's the single biggest risk right now?",
    "wallet_health": "Review the follow pool and audited wallets. Which are decaying or "
                     "should be dropped, which still look copyable? 4 sentences max.",
    "coin_risk": "Look at the coins with risk flags (transfer_fed / launch_price_entry) and "
                 "our open positions. Flag anything that looks like a trap. 4 sentences max.",
    "decay_alert": "Compare each follow-pool wallet's older-half vs newer-half average "
                   "PnL/trade. Name any wallet whose edge is decaying. 3 sentences max.",
}


def generate_insight(kind: str) -> dict:
    prompt = INSIGHT_PROMPTS.get(kind)
    if not prompt:
        raise ValueError(f"unknown insight kind {kind}")
    out = chat([{"role": "user", "content": prompt}])
    body = out["reply"]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO insights (kind, subject, body, model) VALUES (%s, NULL, %s, %s)",
            (kind, body, out["model"]),
        )
    return {"kind": kind, "body": body, "model": out["model"]}


def latest_insights() -> list[dict]:
    return db.fetch_all(
        """
        SELECT DISTINCT ON (kind) kind, subject, body, model, created_at
        FROM insights ORDER BY kind, created_at DESC
        """
    )
