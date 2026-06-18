"""Server-side wallet discovery, triggered from the dashboard.

Wraps the existing CLI workers (discover.py, audit_runner.py) so the UI can do
what `python3 discover.py --gmgn 7d --audit` does. Honesty rule (CLAUDE.md):
this only *adds names to audit* and runs the auditor — discovery never causes a
wallet to be followed; only a CANDIDATE verdict does. No keys, no transactions.

The whole run (GMGN fetch + add + audit) happens in a FastAPI BackgroundTask so
the HTTP request returns instantly — important behind a reverse proxy / Vercel.
The UI polls /discovery and /discovery/status to watch progress.
"""
from __future__ import annotations

import os
import threading

from beerfund import db
import discover
import audit_runner

_lock = threading.Lock()
_state = {"running": False, "last": None, "added": 0}


def status() -> dict:
    return dict(_state)


def try_begin() -> bool:
    """Atomically claim the single run slot. False if one is already running."""
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
        _state["last"] = "running…"
        return True


def _new_candidates() -> list[str]:
    with db.connect() as c:
        return [
            r["wallet"]
            for r in c.execute(
                "SELECT wallet FROM discovery_candidates WHERE status='new'"
            ).fetchall()
        ]


def run_all(gmgn: str | None, wallets: list[str]) -> None:
    """Background worker: add candidates (GMGN best-effort + manual), audit new."""
    try:
        rows: list[tuple[str, str]] = []
        gmgn_status = "skipped"
        if gmgn:
            found = discover.fetch_gmgn(gmgn)  # [] if Cloudflare-blocked
            gmgn_status = "ok" if found else "blocked"
            rows += [(w, f"gmgn:{gmgn}") for w in found]
        rows += [(w.strip(), "ui") for w in wallets if w and w.strip()]

        added = discover.add_candidates(rows) if rows else 0
        _state["added"] = added

        new = _new_candidates()  # also triggers .env load -> HELIUS_API_KEY
        api_key = os.environ.get("HELIUS_API_KEY")
        if not api_key:
            _state["last"] = (
                f"added {added} (gmgn: {gmgn_status}); HELIUS_API_KEY not set on the "
                f"API host, so no audit ran"
            )
        elif not new:
            _state["last"] = f"added {added} (gmgn: {gmgn_status}); nothing new to audit"
        else:
            audit_runner.run_once(new, api_key, pages=6, fresh=False)
            _state["last"] = (
                f"added {added}, audited {len(new)} wallet(s) (gmgn: {gmgn_status})"
            )
    except Exception as e:  # never leave the slot stuck on an error
        _state["last"] = f"error: {type(e).__name__}: {e}"
    finally:
        _state["running"] = False
