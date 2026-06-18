"""Derive pump.fun bonding-curve addresses offline (no API needed).

Every pump.fun token's bonding curve lives at a Program Derived Address:
    PDA(seeds=[b"bonding-curve", mint], program=pump.fun)

A PDA is the first sha256(seeds + bump + program + marker) digest that is NOT
a valid ed25519 curve point, searching bump from 255 downward. The curve check
needs a little field arithmetic, all stdlib.
"""

from __future__ import annotations

import hashlib

PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_P = 2 ** 255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P


def b58decode(s: str) -> bytes:
    n = 0
    for ch in s:
        n = n * 58 + _B58.index(ch)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


def b58encode(b: bytes) -> str:
    n = int.from_bytes(b, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    pad = len(b) - len(b.lstrip(b"\x00"))
    return "1" * pad + out


def _is_on_curve(point: bytes) -> bool:
    """Can these 32 bytes decompress to a valid ed25519 point?"""
    y = int.from_bytes(point, "little") & ((1 << 255) - 1)
    if y >= _P:
        return False
    y2 = y * y % _P
    u = (y2 - 1) % _P
    v = (_D * y2 + 1) % _P
    # x^2 = u/v; sqrt exists iff (u/v) is a quadratic residue
    x2 = u * pow(v, _P - 2, _P) % _P
    if x2 == 0:
        return True
    return pow(x2, (_P - 1) // 2, _P) == 1


def find_pda(seeds: list[bytes], program: str) -> str:
    prog = b58decode(program)
    for bump in range(255, -1, -1):
        h = hashlib.sha256(
            b"".join(seeds) + bytes([bump]) + prog + b"ProgramDerivedAddress"
        ).digest()
        if not _is_on_curve(h):
            return b58encode(h)
    raise ValueError("no valid PDA bump found")


def bonding_curve_address(mint: str) -> str:
    return find_pda([b"bonding-curve", b58decode(mint)], PUMP_FUN_PROGRAM)
