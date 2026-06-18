# Beer Fund Bot — web & analysis layer

A live dashboard + AI analyst layered on top of the existing research workers.
**Nothing here changes how the bot trades.** `paper_trader.py`, `run_audit.py`
and `run_replay.py` stay exactly as they were — stdlib-only, zero-capital, no
keys. This layer is a *read model*: new processes copy the workers' output into
Postgres, a read-only API serves it, and a Next.js frontend (with an AI analyst)
renders it.

## How it fits together

```
  EXISTING WORKERS (unchanged)            NEW READ LAYER
  ───────────────────────────            ──────────────
  paper_trader.py ──► results/paper_trades.csv ┐
                  └─► data/paper/state.json     ├─► ingest.py ──┐
                                                │                │
  beerfund.audit ◄── audit_runner.py ◄──────────┘                ▼
       ▲                  │  (reuses beerfund.audit verbatim)   ┌──────────┐
  discover.py ────────────┘  candidate wallets → audit          │ Postgres │
                                                                 │ (read    │
                                                                 │  model)  │
                                                                 └────┬─────┘
                                                                      │ read-only
                                                          api/ (FastAPI) ──► /chat, /insights
                                                                      │       (Anthropic)
                                                                      ▼
                                                            web/ (Next.js, Vercel)
```

The split you chose: **Postgres** read model, **chat + auto-insights** AI,
frontend on **Vercel**, API + workers on the **droplet**. v1 covers all four
features — live trades, wallet analysis, coin analysis, and discovery.

## The pieces

| file | role | runtime |
|---|---|---|
| `schema.sql` | the read model (trades, positions, wallet_audits, audit_positions, coins, discovery_candidates, insights) | — |
| `beerfund/db.py` | psycopg connection helper + `python -m beerfund.db` to apply the schema | venv |
| `ingest.py` | tails the daemon's CSV + state.json into Postgres (idempotent, decoupled) | venv |
| `audit_runner.py` | runs `beerfund.audit` over the follow pool + candidates → `wallet_audits` | venv |
| `discover.py` | adds candidate wallets (GMGN best-effort / file / manual) → audit pipeline | venv |
| `api/` | FastAPI read API + `/chat` + `/insights` (Anthropic, read-only SQL tools) | venv |
| `web/` | Next.js dashboard, wallet/coin/discovery views, AI chat + insight panels | Vercel |

The workers remain stdlib-only. Only this layer needs the venv
(`api/requirements.txt`: fastapi, uvicorn, psycopg, anthropic).

## Run it locally

Postgres is hosted on **Supabase** — no Docker, nothing to run locally for the
database. Put your connection details in `.env` and everything reads from there.

```bash
# 1. config — copy the template and fill in your values
cp .env.example .env
#   set DATABASE_URL to your Supabase string (Project Settings → Database →
#   "Direct connection" or "Session pooler", port 5432, add ?sslmode=require),
#   plus HELIUS_API_KEY and (optional) ANTHROPIC_API_KEY.

# 2. deps + schema  (DATABASE_URL is read from .env automatically)
python3 -m venv .venv && . .venv/bin/activate
pip install -r api/requirements.txt
python -m beerfund.db                       # creates the tables in Supabase

# 3. load whatever the daemon has produced + (optional) audit a wallet
python ingest.py --once
python audit_runner.py 2QMCjkbBAkgvW9Az4ThWCUjB6L5oFfTgpbxeCrLi2xvQ

# 4. API
uvicorn api.main:app --reload --port 8000

# 5. frontend (separate shell)
cd web && npm install
echo 'NEXT_PUBLIC_API_BASE=http://localhost:8000' > .env.local
npm run dev                                  # http://localhost:3000
```

`DATABASE_URL`, `HELIUS_API_KEY`, `ANTHROPIC_API_KEY`, `CORS_ORIGINS` and the
`BEERFUND_AI_MODEL` all live in `.env`; a real exported env var still overrides
the file. Use the port-5432 connection (direct or session pooler), **not** the
6543 transaction pooler. Without `ANTHROPIC_API_KEY` everything works except the
AI chat/insights, which show a clear "AI unavailable" message rather than
erroring the page.

## Deploy

**Droplet (API + workers; Postgres is on Supabase).** After the existing
`deploy/setup.sh`:

```bash
deploy/sync.sh root@<DROPLET_IP>           # push code (unchanged step)
ssh root@<DROPLET_IP>
sudo nano /etc/beerfund/beerfund.env          # set DATABASE_URL (Supabase), ANTHROPIC_API_KEY, CORS_ORIGINS
sudo bash /opt/beerfund/deploy/setup-web.sh   # venv + new units, applies schema to Supabase
sudo systemctl start beerfund-ingest beerfund-api beerfund-audit
```

`setup-web.sh` is additive and idempotent — it installs no database (it reads
your Supabase `DATABASE_URL` from the env file and applies the schema there) and
never touches the paper-daemon service or its stdlib runtime. New units:
`beerfund-ingest` (loop),
`beerfund-api` (uvicorn on 127.0.0.1:8000), and `beerfund-audit.timer` (daily
re-sweep — wallets rot). Put Caddy or nginx in front of the API for TLS, since
the browser calls it from Vercel.

**Frontend (Vercel).** Point Vercel at the `web/` directory, set
`NEXT_PUBLIC_API_BASE` to your public API URL, deploy. Set `CORS_ORIGINS` on the
droplet to the Vercel origin.

## Safety notes (per CLAUDE.md)

- The API is **read-only** over trading state. The only writes it makes are to
  `discovery_candidates` (adding names to audit) and the `insights` cache.
- The AI analyst's `sql_select` tool is guarded: single statement, `SELECT`
  only, anything mutating is rejected.
- No process in this layer holds a private key or signs anything. Discovery
  never causes a wallet to be followed — only a CANDIDATE audit verdict does.

## Verified

Backend was exercised end-to-end against a real Postgres 14: schema applies,
`ingest.py` parsed the real `paper_trades.csv` + `state.json`, the go-live
criteria math and drawdown curve compute, `audit_runner.store()` writes report
cards + per-position rows (correctly flagging a synthetic transfer-fed wallet as
INSIDER), and the FastAPI endpoints serve it over HTTP with CORS. The frontend
type-checks and `next build` passes (6 routes).
