"""Verify swap parsing and PnL accounting against a hand-built Helius-shaped fixture."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from beerfund.audit import audit, build_positions
from beerfund.fetch_helius import WSOL_MINT, parse_swaps

WALLET = "WaLLet1111111111111111111111111111111111111"
MINT_A = "MintAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
MINT_B = "MintBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


def tok(mint, amount, decimals=6, user=WALLET):
    return {"userAccount": user, "mint": mint,
            "rawTokenAmount": {"tokenAmount": str(int(amount * 10 ** decimals)),
                               "decimals": decimals}}


def tx(sig, ts, *, native_in=None, native_out=None, tok_in=None, tok_out=None):
    return {
        "signature": sig, "timestamp": ts, "transactionError": None,
        "events": {"swap": {
            "nativeInput": {"account": WALLET, "amount": str(int(native_in * 1e9))} if native_in else None,
            "nativeOutput": {"account": WALLET, "amount": str(int(native_out * 1e9))} if native_out else None,
            "tokenInputs": tok_in or [],
            "tokenOutputs": tok_out or [],
        }},
    }


def main():
    fixtures = [
        # Buy 1000 A for 2 SOL (native), sell all for 5 SOL -> +3 SOL win
        tx("s1", 1000, native_in=2.0, tok_out=[tok(MINT_A, 1000)]),
        tx("s2", 1600, native_out=5.0, tok_in=[tok(MINT_A, 1000)]),
        # Buy 500 B for 1 SOL via wSOL, sell 480 (96% -> closed) for 0.4 -> loss
        tx("s3", 2000, tok_in=[tok(WSOL_MINT, 1.0, decimals=9)],
           tok_out=[tok(MINT_B, 500)]),
        tx("s4", 2300, native_out=0.4, tok_in=[tok(MINT_B, 480)]),
        # Failed tx and token-to-token swap must both be skipped
        {"signature": "s5", "timestamp": 2400, "transactionError": "x",
         "events": {"swap": {"nativeInput": {"account": WALLET, "amount": "1000000000"},
                             "tokenInputs": [], "tokenOutputs": [tok(MINT_A, 1)]}}},
        tx("s6", 2500, tok_in=[tok(MINT_A, 10)], tok_out=[tok(MINT_B, 20)]),
    ]

    swaps = parse_swaps(fixtures, WALLET)
    assert len(swaps) == 4, f"expected 4 clean swaps, got {len(swaps)}"
    assert [s.side for s in swaps] == ["buy", "sell", "buy", "sell"]
    assert abs(swaps[2].sol_amount - 1.0) < 1e-9, "wSOL leg must count as SOL"

    positions = build_positions(swaps)
    assert len(positions) == 2
    a = next(p for p in positions if p.mint == MINT_A)
    b = next(p for p in positions if p.mint == MINT_B)

    assert a.closed and abs(a.realized_pnl_sol - 3.0) < 1e-9
    assert a.hold_seconds == 600
    # B: sold 96% of 500 -> closed; cost basis of sold = 1.0 * 0.96
    assert b.closed and abs(b.realized_pnl_sol - (0.4 - 0.96)) < 1e-9

    rep = audit(WALLET, swaps)
    assert len(rep.closed) == 2 and abs(rep.win_rate - 0.5) < 1e-9
    assert abs(rep.total_realized_sol - (3.0 - 0.56)) < 1e-9

    print("audit pipeline: all assertions passed "
          "(parse -> positions -> PnL -> report)")


if __name__ == "__main__":
    main()
