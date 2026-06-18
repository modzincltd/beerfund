# Beer Fund Bot — research harness

Zero-capital research into Solana copy trading. See [context.md](context.md)
for the why. Nothing in here signs a transaction or touches a private key —
by design, and that stays true until the research says the edge is real.

## What's here

| piece | what it does |
|---|---|
| `run_synthetic.py` | Experiment 1: simulate copying elite vs decent wallets across lag levels, with honest fees/slippage/lag mechanics |
| `run_audit.py` | Audit a **real** wallet's on-chain record: realized PnL, win rate, concentration, edge decay. Needs a free Helius key |
| `beerfund/sim.py` | Copy-trade simulator (mirror exits vs our rules) |
| `beerfund/costs.py` | Pool fees, priority fees, price impact |
| `beerfund/rules.py` | Mechanical exits: stop-loss, TP ladder, trailing stop, max hold |
| `beerfund/synth.py` | Synthetic memecoin market (65% rugs / 23% chop / 12% runners) |
| `beerfund/fetch_helius.py` + `beerfund/audit.py` | Real chain data → report card |
| `tests/test_audit.py` | Fixture tests for the parse/PnL pipeline |

## Run it

```bash
python3 run_synthetic.py                  # no keys needed, fully offline
python3 tests/test_audit.py               # verify the audit pipeline

export HELIUS_API_KEY=...                 # free at https://helius.dev
python3 run_audit.py <WALLET_ADDRESS>     # audit a real wallet
```

## What the synthetic experiment established (2026-06-11)

1. **Copy entries, never exits.** Mirroring a wallet's exits means selling into
   the dump their sell started; their exit-timing skill cannot survive a lagged
   pipe. Our own mechanical exits ("rules mode") gave a higher win rate (73%),
   ~3x lower drawdown, and made results independent of the wallet's exit skill
   and honesty.
2. **Lag hurts most when copying the best wallets** — elite edge lives in exit
   timing, which is exactly what lag destroys. At 10s lag the median mirrored
   trade fell from +99% to +33%.
3. **Mirror-copying a merely-decent wallet is drawdown hell**: median trade
   ~+15%, PnL concentrated in a few runners, 7 position-sizes of drawdown.
   Survivorship bias, reproduced numerically.
4. **Caveat: absolute numbers are NOT believable** — the synthetic market is
   too generous (every rug pumps before collapsing; entries always early).
   Structural/relative findings only. Absolute viability needs real data,
   which is what the auditor is for.

## Known simplifications (fix before trusting anything)

- No failed/dropped transactions (real fill rate < 100%, failures cost fees).
- Price impact uses a constant-depth approximation, not real pool reserves.
- The synthetic wallet's entries are always early; real wallet entries must be
  validated with the auditor + (next) real price-series replay.
- Audit uses average-cost basis and treats ≥95% sold as a closed position.

## Pipeline status

1. ~~Audit candidate wallets~~ — done. 35 audited, 1 copy candidate (`2QMC…2xvQ`).
2. ~~Real price-series replay~~ — done (`run_replay.py`). Rules-mode +4.34 SOL
   vs wallet-gross −0.72 on the same 9 signals. Chase guard dodged 2 rugs.
3. **Paper trading — LIVE NOW** (`paper_trader.py`). Fills marked at real
   Jupiter quotes, exits managed by the rules engine, everything logged to
   `results/paper_trades.csv`.
4. Real capital — gated on the criteria below.

**Web & AI analysis layer (`WEBAPP.md`)** — a Postgres read model + FastAPI +
Next.js dashboard with an AI analyst, layered on top without changing any
worker. `ingest.py` mirrors the paper trade log/state into Postgres,
`audit_runner.py` runs the auditor over the follow pool + discovery candidates,
`discover.py` feeds new candidates in, and `web/` renders live trades, wallet
audits, coin analysis and the discovery pipeline. See `WEBAPP.md` to run it.

## Go-live criteria (agreed 2026-06-11, £50 execution-validation tranche)

- ≥2 weeks of live paper trading and ≥20 filled positions
- Net-positive realized PnL after all simulated costs
- Max drawdown ≤ 6 position-sizes
- ≥2 wallets currently passing audit in the follow pool (re-sweep weekly —
  wallets rot; rank #1 on our first sweep was already decaying)
- Any live funding/execution is performed by Taylor personally, never by tooling

## Running the paper daemon

```bash
python3 paper_trader.py <WALLET> [<WALLET>...]   # Ctrl-C to stop; state survives
```

State: `data/paper/state.json`. Trade log: `results/paper_trades.csv`.
First run arms on each wallet's latest tx — it never replays history.
