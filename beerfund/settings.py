"""Tunable criteria for finding + promoting wallets, and the go-live gates.

Code holds the DEFAULTS (matching the original hard-coded thresholds); the
Settings page can override them, persisted as one JSONB row. `load()` merges the
DB overrides over the defaults so a partial/empty row is always safe.

Used by audit_runner (applies `audit` thresholds before a sweep), api.queries
(go-live criteria), and the /settings API. Imports psycopg via beerfund.db, so —
like paper_store — it's only pulled in on the DB path; audit.py itself stays
dependency-free.
"""
from __future__ import annotations

import json

from beerfund import db

DEFAULTS = {
    # Wallet audit verdict thresholds — what makes a wallet copyable/promotable.
    "audit": {
        "min_closed": 8,          # fewer closed round-trips -> THIN (can't judge)
        "insider_return_x": 50.0,  # any trade >this many x -> INSIDER (launch-price)
        "min_median_hold_s": 600,  # faster median hold -> TOOFAST (dies in copy lag)
        "decay_ratio": 0.5,        # newer-half avg < this * older-half -> DECAYING
    },
    # Go-live gates (README criteria) shown on the dashboard.
    "golive": {
        "min_filled": 20,
        "min_weeks": 2,
        "max_drawdown_sizes": 6,
        "min_passing_wallets": 2,
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def load() -> dict:
    """Full effective config: DB overrides merged over DEFAULTS."""
    try:
        row = db.fetch_one("SELECT config FROM settings WHERE id = 1")
    except Exception:
        row = None
    return _merge(DEFAULTS, (row or {}).get("config") or {})


def save(config: dict) -> dict:
    """Persist a (validated) config; returns the new effective config."""
    clean = _merge(DEFAULTS, config or {})  # drop unknown keys, fill missing
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (id, config, updated_at) VALUES (1, %s::jsonb, now())
            ON CONFLICT (id) DO UPDATE SET config = EXCLUDED.config, updated_at = now()
            """,
            (json.dumps(clean),),
        )
    return clean
