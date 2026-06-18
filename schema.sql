-- Beer Fund Bot — Postgres schema for the web/analysis layer.
--
-- Design rule (mirrors CLAUDE.md): the Python workers stay the source of truth.
-- Nothing here signs a transaction or holds a key. This schema is a *read model*
-- populated by ingest.py (paper trades/state), audit_runner.py (wallet audits)
-- and discover.py (candidate wallets). The API and frontend only ever read it.
--
-- Columns match the real Python shapes:
--   paper_trades.csv rows  -> trades
--   data/paper/state.json  -> positions + paper_state
--   beerfund.audit.AuditReport / TokenPosition -> wallet_audits + audit_positions

CREATE TABLE IF NOT EXISTS trades (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,      -- from the row's unix `ts`
    event       TEXT NOT NULL,             -- ENTRY | EXIT | CLOSE
    mint        TEXT NOT NULL,
    wallet      TEXT,                       -- 8-char prefix as logged by the daemon
    fraction    DOUBLE PRECISION,
    sol         DOUBLE PRECISION,
    tokens      NUMERIC,                    -- raw token units (can be huge)
    price       DOUBLE PRECISION,
    reason      TEXT,
    pnl_sol     DOUBLE PRECISION,           -- only set on CLOSE rows
    row_hash    TEXT UNIQUE NOT NULL        -- idempotent ingest key
);
CREATE INDEX IF NOT EXISTS trades_ts_idx   ON trades (ts);
CREATE INDEX IF NOT EXISTS trades_mint_idx ON trades (mint);
CREATE INDEX IF NOT EXISTS trades_event_idx ON trades (event);

-- Current open positions (full snapshot, replaced every ingest cycle).
CREATE TABLE IF NOT EXISTS positions (
    mint        TEXT PRIMARY KEY,
    wallet      TEXT NOT NULL,
    entry_ts    TIMESTAMPTZ NOT NULL,
    tokens      NUMERIC NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    peak        DOUBLE PRECISION NOT NULL,
    remaining   DOUBLE PRECISION NOT NULL,
    rung        INTEGER NOT NULL,
    banked_sol  DOUBLE PRECISION NOT NULL,
    cost_sol    DOUBLE PRECISION NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Singleton daemon counters from state.json.
CREATE TABLE IF NOT EXISTS paper_state (
    id           INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    realized_sol DOUBLE PRECISION NOT NULL DEFAULT 0,
    n_closed     INTEGER NOT NULL DEFAULT 0,
    n_skipped    INTEGER NOT NULL DEFAULT 0,
    last_sig     JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per wallet per audit run.
CREATE TABLE IF NOT EXISTS wallet_audits (
    id                BIGSERIAL PRIMARY KEY,
    wallet            TEXT NOT NULL,
    ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
    n_swaps           INTEGER NOT NULL,
    n_positions       INTEGER NOT NULL,
    n_closed          INTEGER NOT NULL,
    n_open            INTEGER NOT NULL,
    win_rate          DOUBLE PRECISION NOT NULL,
    total_realized_sol DOUBLE PRECISION NOT NULL,
    median_pnl_sol    DOUBLE PRECISION,
    median_hold_s     INTEGER,
    best_trade_sol    DOUBLE PRECISION,
    concentration     DOUBLE PRECISION,       -- best trade / total PnL
    old_avg           DOUBLE PRECISION,       -- older-half avg PnL/trade
    new_avg           DOUBLE PRECISION,       -- newer-half avg PnL/trade
    decaying          BOOLEAN NOT NULL DEFAULT false,
    verdict_code      TEXT NOT NULL,          -- CANDIDATE/DECAYING/THIN/TOOFAST/LOSER/INSIDER
    verdict_reason    TEXT,
    in_follow_pool    BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (wallet, ts)
);
CREATE INDEX IF NOT EXISTS wallet_audits_wallet_idx ON wallet_audits (wallet, ts DESC);

-- Per-position detail for each audit (drives coin analysis + drill-down).
CREATE TABLE IF NOT EXISTS audit_positions (
    id               BIGSERIAL PRIMARY KEY,
    audit_id         BIGINT NOT NULL REFERENCES wallet_audits(id) ON DELETE CASCADE,
    wallet           TEXT NOT NULL,
    mint             TEXT NOT NULL,
    sol_in           DOUBLE PRECISION NOT NULL,
    sol_out          DOUBLE PRECISION NOT NULL,
    tokens_bought    NUMERIC NOT NULL,
    tokens_sold      NUMERIC NOT NULL,
    first_t          TIMESTAMPTZ,
    last_t           TIMESTAMPTZ,
    n_swaps          INTEGER NOT NULL,
    realized_pnl_sol DOUBLE PRECISION NOT NULL,
    realized_return  DOUBLE PRECISION NOT NULL,
    hold_seconds     INTEGER NOT NULL,
    closed           BOOLEAN NOT NULL,
    transfer_fed     BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_positions_mint_idx  ON audit_positions (mint);
CREATE INDEX IF NOT EXISTS audit_positions_audit_idx ON audit_positions (audit_id);

-- Per-token rollup for coin analysis (price/liquidity cache + risk flags).
CREATE TABLE IF NOT EXISTS coins (
    mint                TEXT PRIMARY KEY,
    symbol              TEXT,
    name                TEXT,
    first_seen          TIMESTAMPTZ,
    last_seen           TIMESTAMPTZ,
    liquidity_sol       DOUBLE PRECISION,
    price_sol           DOUBLE PRECISION,
    last_priced_at      TIMESTAMPTZ,
    n_audit_appearances INTEGER NOT NULL DEFAULT 0,
    n_paper_trades      INTEGER NOT NULL DEFAULT 0,
    risk_flags          JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- User annotations: a friendly label + freeform tags per wallet, set from the UI
-- so wallets of interest are easy to identify. Pure metadata — never affects
-- trading, audit verdicts, or the follow decision.
CREATE TABLE IF NOT EXISTS wallet_labels (
    wallet      TEXT PRIMARY KEY,
    label       TEXT,
    tags        JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Wallet discovery pipeline (GMGN leaderboards -> audit -> promote/reject).
CREATE TABLE IF NOT EXISTS discovery_candidates (
    wallet        TEXT PRIMARY KEY,
    source        TEXT NOT NULL,            -- e.g. gmgn:7d, manual, telegram
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        TEXT NOT NULL DEFAULT 'new', -- new|audited|promoted|rejected
    last_verdict  TEXT,
    audit_id      BIGINT REFERENCES wallet_audits(id) ON DELETE SET NULL,
    notes         TEXT
);

-- AI-generated insight panels (cached so we don't re-bill the model per page view).
CREATE TABLE IF NOT EXISTS insights (
    id         BIGSERIAL PRIMARY KEY,
    kind       TEXT NOT NULL,               -- wallet_health|coin_risk|decay_alert|summary
    subject    TEXT,                        -- wallet or mint, null for global
    body       TEXT NOT NULL,
    model      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS insights_kind_idx ON insights (kind, created_at DESC);
