"""Read-only query helpers over the Postgres read model.

Everything here is SELECT-only. The API never writes trading state; the workers
own that. Drawdown / criteria logic lives here so both the REST endpoints and
the AI tools share one definition of "how are we doing".
"""

from __future__ import annotations

import datetime as dt
import json
import os

from beerfund import db

# Go-live criteria (README "Go-live criteria", agreed 2026-06-11).
MIN_FILLED = 20
MIN_WEEKS = 2
MAX_DRAWDOWN_SIZES = 6
MIN_PASSING_WALLETS = 2


def _position_size() -> float:
    """Infer the per-trade size from ENTRY rows; fall back to PAPER_SIZE/0.5."""
    row = db.fetch_one(
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY sol) AS s "
        "FROM trades WHERE event='ENTRY' AND sol IS NOT NULL"
    )
    if row and row["s"]:
        return float(row["s"])
    try:
        return float(os.environ.get("PAPER_SIZE", "0.5"))
    except ValueError:
        return 0.5


def summary() -> dict:
    st = db.fetch_one("SELECT * FROM paper_state WHERE id=1") or {}
    n_entries = (db.fetch_one("SELECT count(*) c FROM trades WHERE event='ENTRY'") or {}).get("c", 0)
    n_open = (db.fetch_one("SELECT count(*) c FROM positions") or {}).get("c", 0)
    first = db.fetch_one("SELECT min(ts) t FROM trades")
    last = db.fetch_one("SELECT max(ts) t FROM trades")
    return {
        "realized_sol": st.get("realized_sol", 0.0),
        "n_closed": st.get("n_closed", 0),
        "n_skipped": st.get("n_skipped", 0),
        "n_filled": n_entries,
        "n_open": n_open,
        "position_size_sol": _position_size(),
        "first_trade": (first or {}).get("t"),
        "last_trade": (last or {}).get("t"),
        "updated_at": st.get("updated_at"),
    }


def drawdown_sizes() -> dict:
    """Peak-to-trough of the realized-PnL curve (CLOSE rows), in position-sizes."""
    rows = db.fetch_all(
        "SELECT ts, pnl_sol FROM trades WHERE event='CLOSE' AND pnl_sol IS NOT NULL ORDER BY ts"
    )
    size = _position_size()
    cum = peak = max_dd = 0.0
    curve = []
    for r in rows:
        cum += r["pnl_sol"]
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        curve.append({"ts": r["ts"], "cum_sol": round(cum, 4)})
    return {
        "max_drawdown_sol": round(max_dd, 4),
        "max_drawdown_sizes": round(max_dd / size, 2) if size else None,
        "position_size_sol": size,
        "curve": curve,
    }


def passing_wallets() -> list[dict]:
    """Follow-pool wallets whose most-recent audit verdict is CANDIDATE."""
    return db.fetch_all(
        """
        SELECT DISTINCT ON (wallet) wallet, verdict_code, verdict_reason, ts,
               win_rate, total_realized_sol
        FROM wallet_audits
        WHERE in_follow_pool = true
        ORDER BY wallet, ts DESC
        """
    )


def criteria() -> dict:
    s = summary()
    dd = drawdown_sizes()
    passing = [w for w in passing_wallets() if w["verdict_code"] == "CANDIDATE"]

    weeks_live = None
    if s["first_trade"]:
        first = s["first_trade"]
        now = dt.datetime.now(tz=first.tzinfo)
        weeks_live = round((now - first).days / 7.0, 2)

    checks = {
        "duration": {
            "label": f"≥2 weeks live & ≥20 filled positions",
            "weeks_live": weeks_live, "n_filled": s["n_filled"],
            "pass": bool(weeks_live is not None and weeks_live >= MIN_WEEKS
                         and s["n_filled"] >= MIN_FILLED),
        },
        "net_positive": {
            "label": "Net-positive realized PnL after costs",
            "realized_sol": s["realized_sol"],
            "pass": s["realized_sol"] > 0,
        },
        "drawdown": {
            "label": f"Max drawdown ≤ {MAX_DRAWDOWN_SIZES} position-sizes",
            "max_drawdown_sizes": dd["max_drawdown_sizes"],
            "pass": bool(dd["max_drawdown_sizes"] is not None
                         and dd["max_drawdown_sizes"] <= MAX_DRAWDOWN_SIZES),
        },
        "follow_pool": {
            "label": f"≥2 wallets passing audit in follow pool",
            "n_passing": len(passing),
            "wallets": passing,
            "pass": len(passing) >= MIN_PASSING_WALLETS,
        },
    }
    checks["all_pass"] = all(c["pass"] for c in checks.values() if isinstance(c, dict) and "pass" in c)
    return checks


def positions() -> list[dict]:
    return db.fetch_all(
        """
        SELECT p.*, EXTRACT(EPOCH FROM (now() - p.entry_ts)) AS age_seconds,
               c.symbol, c.risk_flags
        FROM positions p LEFT JOIN coins c USING (mint)
        ORDER BY p.entry_ts DESC
        """
    )


def trades(limit: int = 200, mint: str | None = None) -> list[dict]:
    if mint:
        return db.fetch_all(
            "SELECT * FROM trades WHERE mint=%s ORDER BY ts DESC LIMIT %s", (mint, limit)
        )
    return db.fetch_all("SELECT * FROM trades ORDER BY ts DESC LIMIT %s", (limit,))


def wallets() -> list[dict]:
    return db.fetch_all(
        """
        SELECT DISTINCT ON (wallet) *
        FROM wallet_audits
        ORDER BY wallet, ts DESC
        """
    )


def wallet_detail(wallet: str) -> dict:
    latest = db.fetch_one(
        "SELECT * FROM wallet_audits WHERE wallet=%s ORDER BY ts DESC LIMIT 1", (wallet,)
    )
    if not latest:
        return {}
    positions_ = db.fetch_all(
        "SELECT * FROM audit_positions WHERE audit_id=%s ORDER BY realized_pnl_sol DESC",
        (latest["id"],),
    )
    history = db.fetch_all(
        "SELECT ts, verdict_code, win_rate, total_realized_sol, decaying "
        "FROM wallet_audits WHERE wallet=%s ORDER BY ts DESC LIMIT 12", (wallet,)
    )
    return {"audit": latest, "positions": positions_, "history": history}


def coins(limit: int = 200) -> list[dict]:
    return db.fetch_all(
        """
        SELECT c.*,
               (SELECT count(DISTINCT wallet) FROM audit_positions ap WHERE ap.mint=c.mint) AS n_wallets
        FROM coins c
        ORDER BY c.n_audit_appearances DESC, c.last_seen DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )


def coin_detail(mint: str) -> dict:
    coin = db.fetch_one("SELECT * FROM coins WHERE mint=%s", (mint,))
    appearances = db.fetch_all(
        """
        SELECT DISTINCT ON (ap.wallet) ap.wallet, ap.realized_pnl_sol, ap.realized_return,
               ap.hold_seconds, ap.closed, ap.transfer_fed, ap.last_t
        FROM audit_positions ap
        JOIN wallet_audits wa ON wa.id = ap.audit_id
        WHERE ap.mint=%s
        ORDER BY ap.wallet, wa.ts DESC
        """,
        (mint,),
    )
    paper = trades(limit=100, mint=mint)
    return {"coin": coin, "wallet_appearances": appearances, "paper_trades": paper}


def discovery() -> list[dict]:
    return db.fetch_all(
        """
        SELECT d.*, wa.win_rate, wa.total_realized_sol, wa.verdict_reason
        FROM discovery_candidates d
        LEFT JOIN wallet_audits wa ON wa.id = d.audit_id
        ORDER BY d.discovered_at DESC
        """
    )


# ---- wallet labels + tags (user annotations) --------------------------------

def labels() -> list[dict]:
    return db.fetch_all("SELECT wallet, label, tags, updated_at FROM wallet_labels")


def set_label(wallet: str, label: str | None, tags: list[str]) -> dict:
    """Upsert a wallet's label + tags. Deletes the row if both are empty."""
    if not label and not tags:
        db.fetch_all("DELETE FROM wallet_labels WHERE wallet=%s", (wallet,))
        return {"wallet": wallet, "label": None, "tags": []}
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO wallet_labels (wallet, label, tags, updated_at)
            VALUES (%s, %s, %s::jsonb, now())
            ON CONFLICT (wallet) DO UPDATE SET
                label = EXCLUDED.label, tags = EXCLUDED.tags, updated_at = now()
            """,
            (wallet, label or None, json.dumps(tags or [])),
        )
    return {"wallet": wallet, "label": label or None, "tags": tags or []}
