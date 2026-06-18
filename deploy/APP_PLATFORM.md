# Deploy everything on DigitalOcean App Platform

One managed app runs the whole stack from this repo — **`git push` redeploys all
of it**, HTTPS and routing are handled for you, and there's no server, Caddy, or
CORS to manage. Postgres stays on Supabase.

```
            ┌──────────── one App Platform app (HTTPS) ────────────┐
 browser ──▶│  /        →  web    (static dashboard, free)         │
            │  /api/*   →  api    (FastAPI, prefix stripped)       │
            └──────────────────────────────────────────────────────┘
   workers (no public URL):  paper (live daemon)   audit (weekly sweep)
                                   └──────────── Supabase Postgres ───────────┘
```

The dashboard calls `/api/...` on its **own origin**, so there's no CORS and no
separate API host. The spec is in [`.do/app.yaml`](../.do/app.yaml).

## Why the daemon changed
App Platform containers have **ephemeral, isolated disks**, so the old
file-based flow (`paper_trades.csv` + `state.json` → `ingest.py`) won't survive a
redeploy. When `DATABASE_URL` is set, the daemon now reads/writes its state and
trades straight to Postgres ([`beerfund/paper_store.py`](../beerfund/paper_store.py)),
so it survives redeploys and `ingest.py` is no longer needed here. (Run it
file-based as before by simply not setting `DATABASE_URL`.)

## One-time setup

1. **Schema** — make sure the Supabase tables exist (already done for the
   current DB). For a fresh database, run once from your laptop:
   `DATABASE_URL=... .venv/bin/python -m beerfund.db`

2. **Create the app.** DigitalOcean → **Create → Apps** → connect GitHub and
   pick **`modzincltd/beerfund`**, branch `main`. It auto-loads `.do/app.yaml`
   and shows four components: `web`, `api`, `paper`, `audit`.

3. **Set the secret env vars** (app-level, in the Environment section) — these
   are NOT in git:
   - `DATABASE_URL` — your Supabase **session pooler** string (port 5432,
     `?sslmode=require`; the workers/api use psycopg, so the pooler is right).
   - `HELIUS_API_KEY`
   - `ANTHROPIC_API_KEY` — optional (AI chat/insights; everything else works
     without it).
   - `WALLETS` is pre-filled to the follow wallet — change it to your list.

4. **Create.** The first deploy builds the static dashboard, the API, and starts
   both workers. Open the app URL → live dashboard, talking to `/api`.

## Day-to-day
- **Deploy:** `git push` → App Platform rebuilds the changed components. That's it.
- **Logs:** per-component **Runtime Logs** in the dashboard (watch `paper` for
  the entry/exit heartbeat, `audit` for sweep verdicts).
- **Change followed wallets / tuning:** edit `WALLETS` / `PAPER_*` env vars →
  it redeploys the worker.

## Cost (~$10–15/mo)
`web` is a free static site; `api`, `paper`, and `audit` are ~$5/mo each on the
smallest `basic-xxs`. Drop the **`audit`** worker (delete it from the spec or in
the UI) to save ~$5 — the dashboard's "Find new wallets" button still audits on
demand; you'd just lose the automated weekly re-sweep.

## Notes
- `region: lon` in the spec — change to your nearest (`nyc`, `fra`, `sgp`, …).
- `instance_size_slug: basic-xxs` is the cheapest; bump it in the UI if a worker
  needs more memory.
- This replaces the droplet entirely. The `deploy/` droplet scripts
  (`setup.sh`, `sync.sh`, `setup-proxy.sh`, systemd units) remain for anyone who
  prefers a single VM, but you don't need them on App Platform.
