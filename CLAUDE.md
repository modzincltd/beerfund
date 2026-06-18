# Beer Fund Bot — session context

Read [context.md](context.md) (the why) and [README.md](README.md) (what's
built + findings) before doing anything.

## Hard rules

- **Zero capital at risk. Ever.** This is a research/simulation project. No
  code that signs transactions or touches private keys without Taylor
  explicitly changing this rule.
- Honesty over hopium: model fees, slippage, lag, and failed fills. If a
  result looks too good, suspect the simulation before celebrating.

## State of play

- Phase 1 done: synthetic copy-trade experiment (`run_synthetic.py`).
  Established: copy entries never exits; lag destroys exit-timing edge;
  wallet selection/decay-detection is the real product.
- Phase 2 ready: real wallet auditor (`run_audit.py`) — needs free Helius key
  in `HELIUS_API_KEY`. Candidate wallets come from GMGN.ai leaderboards.
- Phase 3 next: real price-series replay, then live zero-capital paper trading.

## Conventions

- Python 3.11, stdlib only (urllib for HTTP, no pip deps so far).
- Everything seeded/reproducible; API responses cached in `data/cache/`.
- Tests are plain-assert scripts: `python3 tests/test_audit.py`.
