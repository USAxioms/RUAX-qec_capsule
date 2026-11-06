#!/usr/bin/env python3
"""Steane [[7,1,3]] Pauli-frame QEC simulator with 10^18 fixed-point risk accounting.

Stdlib only. All arithmetic on probabilities is integer-based. Fault injection
uses an integer PRNG (SplitMix64), so runs are bit-reproducible across platforms.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Final, Optional, Sequence, Tuple

# ----------------------------------------------------------------------------
# Fixed-point engine
# ----------------------------------------------------------------------------
WAD: Final[int] = 10**18
COMPTON_LIMIT_WAD: Final[int] = 2_500  # 2.5e-15 expressed in WAD units
N_QUBITS: Final[int] = 7
N_CHECKS: Final[int] = 3
CHANNEL_X: Final[int] = 0
CHANNEL_Z: Final[int] = 1
_M64: Final[int] = (1 << 64) - 1


def _check_int(x: object, name: str) -> int:
    if type(x) is not int:
        raise TypeError(f"{name} must be int, got {type(x).__name__}")
    return x


def round_div(num: int, den: int) -> int:
    """Round-half-away-from-zero integer division, den > 0."""
    if den <= 0:
        raise ZeroDivisionError("round_div requires den > 0")
    if num >= 0:
        return (2 * num + den) // (2 * den)
    return -((-2 * num + den) // (2 * den))


def mul_wad(a: int, b: int) -> int:
    return round_div(_check_int(a, "a") * _check_int(b, "b"), WAD)


def div_wad(a: int, b: int) -> int:
    _check_int(a, "a")
    _check_int(b, "b")
    if b == 0:
        raise ZeroDivisionError("WAD division by zero")
    if b < 0:
        return div_wad(-a, -b)
    return round_div(a * WAD, b)


def parse_wad(text: str) -> int:
    """Exact decimal string -> WAD int. No floats; at most 18 fractional digits."""
    if not isinstance(text, str):
        raise TypeError("parse_wad takes a decimal string")
    s = text.strip()
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    whole, _, frac = s.partition(".")
    digits = "0123456789"
    if (not whole and not frac) or len(frac) > 18:
        raise ValueError(f"invalid WAD literal: {text!r}")
    if not all(c in digits for c in whole + frac):
        raise ValueError(f"invalid WAD literal: {text!r}")
    value = int(whole or "0") * WAD + int(frac.ljust(18, "0") if frac else "0")
    return -value if neg else value


def format_wad(w: int) -> str:
    _check_int(w, "w")
    sign = "-" if w < 0 else ""
    q, r = divmod(abs(w), WAD)
    return f"{sign}{q}.{r:018d}"


class SplitMix64:
    """Deterministic integer PRNG; identical output on every platform."""

    def __init__(self, seed: int) -> None:
        self._s: int = _check_int(seed, "seed") & _M64

    def next_u64(self) -> int:
        self._s = (self._s + 0x9E3779B97F4A7C15) & _M64
        z = self._s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
        return z ^ (z >> 31)

    def bernoulli_wad(self, p_wad: int) -> bool:
        """True with probability p_wad / WAD, integer arithmetic only."""
        return ((self.next_u64() * WAD) >> 64) < p_wad


# ----------------------------------------------------------------------------
# Steane code structure (CSS: same classical Hamming checks for X and Z errors)
# ----------------------------------------------------------------------------
def popcount(x: int) -> int:
    return bin(x).count("1")


def _row_masks() -> Tuple[int, ...]:
    # Check r covers qubit i iff bit r of (i+1) is set -> Hamming parity-check matrix.
    return tuple(
        sum(1 << i for i in range(N_QUBITS) if ((i + 1) >> r) & 1)
        for r in range(N_CHECKS)
    )


CHECK_ROWS: Final[Tuple[int, ...]] = _row_masks()


def _check_vec(v: int) -> int:
    _check_int(v, "vector")
    if not 0 <= v < (1 << N_QUBITS):
        raise ValueError("error vector out of range for 7 qubits")
    return v


def syndrome(v: int, rows: Sequence[int] = CHECK_ROWS) -> int:
    """3-bit syndrome; bit r is the parity of v under check r."""
    _check_vec(v)
    s = 0
    for r, mask in enumerate(rows):
        s |= (popcount(v & mask) & 1) << r
    return s


def build_decode_table() -> Tuple[int, ...]:
    """Syndrome value s (1..7) names the faulty qubit s-1; 0 means no correction."""
    return tuple(0 if s == 0 else 1 << (s - 1) for s in range(1 << N_CHECKS))


DECODE_TABLE: Final[Tuple[int, ...]] = build_decode_table()


def stabilizer_product(s: int) -> int:
    """Product of the three stabilizer eigenvalues: +1 iff syndrome weight is even.
    This is weaker than syndrome == 0; it is reported, not used as the decoder gate."""
    return 1 if popcount(s) % 2 == 0 else -1


def in_stabilizer_group(v: int) -> bool:
    """Residual is harmless iff it has zero syndrome and even weight (the 8 stabilizers)."""
    return syndrome(v) == 0 and popcount(v) % 2 == 0


def correct(v: int, table: Sequence[int] = DECODE_TABLE) -> int:
    return _check_vec(v) ^ table[syndrome(v)]


def verify_decoder(
    table: Sequence[int] = DECODE_TABLE, rows: Sequence[int] = CHECK_ROWS
) -> bool:
    """Every single-qubit error (and no error) must be reversed exactly."""
    if len(table) != (1 << N_CHECKS):
        return False
    if table[syndrome(0, rows)] != 0:
        return False
    for i in range(N_QUBITS):
        e = 1 << i
        if e ^ table[syndrome(e, rows)] != 0:
            return False
    return True


# ----------------------------------------------------------------------------
# Exact logical-failure probability (WAD)
# ----------------------------------------------------------------------------
def _fail_numerator(p_wad: int, table: Sequence[int]) -> int:
    """Sum over all 128 patterns of p^w q^(7-w) for patterns the decoder fails on,
    as an exact integer over denominator WAD**7."""
    q_wad = WAD - p_wad
    total = 0
    for pattern in range(1 << N_QUBITS):
        residual = pattern ^ table[syndrome(pattern)]
        if not in_stabilizer_group(residual):
            w = popcount(pattern)
            total += p_wad**w * q_wad ** (N_QUBITS - w)
    return total


def logical_failure_wad(
    px_wad: int, pz_wad: int, table: Sequence[int] = DECODE_TABLE
) -> int:
    """P(logical X or logical Z failure) for independent X/Z noise, in WAD."""
    for name, p in (("px_wad", px_wad), ("pz_wad", pz_wad)):
        _check_int(p, name)
        if not 0 <= p <= WAD:
            raise ValueError(f"{name} outside [0, WAD]")
    scale = WAD ** (N_QUBITS - 1)
    fx = round_div(_fail_numerator(px_wad, table), scale)
    fz = round_div(_fail_numerator(pz_wad, table), scale)
    return fx + fz - mul_wad(fx, fz)


# ----------------------------------------------------------------------------
# Circuit breaker
# ----------------------------------------------------------------------------
class CircuitFreeze(RuntimeError):
    """Raised when a safety gate trips. The breaker latches; build a new one to resume."""


class CircuitBreaker:
    def __init__(self, limit_wad: int = COMPTON_LIMIT_WAD) -> None:
        _check_int(limit_wad, "limit_wad")
        if not 0 <= limit_wad <= COMPTON_LIMIT_WAD:
            raise ValueError("limit may only be tightened below the Compton limit")
        self._limit: int = limit_wad
        self._frozen: bool = False
        self._reason: str = ""

    @property
    def frozen(self) -> bool:
        return self._frozen

    def _trip(self, reason: str) -> None:
        self._frozen = True
        self._reason = reason
        raise CircuitFreeze(reason)

    def require_live(self) -> None:
        if self._frozen:
            raise CircuitFreeze(f"circuit frozen: {self._reason}")

    def gate(
        self, px_wad: object, pz_wad: object, table: Sequence[int] = DECODE_TABLE
    ) -> int:
        """Return predicted logical-failure risk (WAD) or freeze."""
        self.require_live()
        for name, p in (("px_wad", px_wad), ("pz_wad", pz_wad)):
            if type(p) is not int or p < 0 or p > WAD:
                self._trip(f"{name} out of bounds: {p!r}")
        assert isinstance(px_wad, int) and isinstance(pz_wad, int)
        if not verify_decoder(table):
            self._trip("decoder table failed single-error verification")
        risk = logical_failure_wad(px_wad, pz_wad, table)
        if risk > self._limit:
            self._trip(f"risk {risk} WAD exceeds limit {self._limit} WAD")
        return risk


# ----------------------------------------------------------------------------
# Syndrome blinding (keyed XOR mask, fresh per round and channel)
# ----------------------------------------------------------------------------
class SyndromeBlinder:
    def __init__(self, key: bytes) -> None:
        if not isinstance(key, (bytes, bytearray)) or len(key) < 16:
            raise ValueError("key must be at least 16 bytes")
        self._key = bytes(key)

    def mask(self, round_index: int, channel: int) -> int:
        _check_int(round_index, "round_index")
        if not 0 <= round_index <= _M64 or channel not in (CHANNEL_X, CHANNEL_Z):
            raise ValueError("bad round_index or channel")
        msg = round_index.to_bytes(8, "big") + channel.to_bytes(1, "big")
        return hmac.new(self._key, msg, hashlib.sha256).digest()[0] & 0b111

    def blind(self, s: int, round_index: int, channel: int) -> int:
        return s ^ self.mask(round_index, channel)

    unblind = blind  # XOR is its own inverse


# ----------------------------------------------------------------------------
# Pauli frame, decoding round, campaigns
# ----------------------------------------------------------------------------
@dataclass
class PauliFrame:
    """x: qubits carrying an X error; z: qubits carrying a Z error (Y = both)."""

    x: int = 0
    z: int = 0

    def inject_x(self, mask: int) -> None:
        self.x ^= _check_vec(mask)

    def inject_z(self, mask: int) -> None:
        self.z ^= _check_vec(mask)

    def inject_y(self, mask: int) -> None:
        self.inject_x(mask)
        self.inject_z(mask)


@dataclass(frozen=True)
class RoundReport:
    round_index: int
    blinded_sx: int
    blinded_sz: int
    parity_x: int
    parity_z: int
    correction_x: int
    correction_z: int
    residual_x: int
    residual_z: int
    logical_failure: bool

    def serialize(self) -> bytes:
        fields = (
            self.round_index, self.blinded_sx, self.blinded_sz, self.parity_x,
            self.parity_z, self.correction_x, self.correction_z,
            self.residual_x, self.residual_z, int(self.logical_failure),
        )
        return (",".join(map(str, fields)) + ";").encode("ascii")


def run_round(
    frame: PauliFrame,
    blinder: SyndromeBlinder,
    round_index: int,
    breaker: Optional[CircuitBreaker] = None,
    table: Sequence[int] = DECODE_TABLE,
) -> RoundReport:
    if breaker is not None:
        breaker.require_live()
    # Z-type checks detect X errors; X-type checks detect Z errors.
    sx, sz = syndrome(frame.x), syndrome(frame.z)
    bx = blinder.blind(sx, round_index, CHANNEL_X)
    bz = blinder.blind(sz, round_index, CHANNEL_Z)
    # Decoder side: unblind, look up, apply.
    sx_d = blinder.unblind(bx, round_index, CHANNEL_X)
    sz_d = blinder.unblind(bz, round_index, CHANNEL_Z)
    cx, cz = table[sx_d], table[sz_d]
    frame.x ^= cx
    frame.z ^= cz
    failed = not (in_stabilizer_group(frame.x) and in_stabilizer_group(frame.z))
    return RoundReport(
        round_index, bx, bz, stabilizer_product(sx), stabilizer_product(sz),
        cx, cz, frame.x, frame.z, failed,
    )


def sample_frame(rng: SplitMix64, px_wad: int, pz_wad: int) -> PauliFrame:
    for name, p in (("px_wad", px_wad), ("pz_wad", pz_wad)):
        _check_int(p, name)
        if not 0 <= p <= WAD:
            raise ValueError(f"{name} outside [0, WAD]")
    x = z = 0
    for qb in range(N_QUBITS):
        if rng.bernoulli_wad(px_wad):
            x |= 1 << qb
        if rng.bernoulli_wad(pz_wad):
            z |= 1 << qb
    return PauliFrame(x, z)


@dataclass(frozen=True)
class CampaignResult:
    rounds: int
    failures: int
    digest: str


def run_campaign(
    seed: int, px_wad: int, pz_wad: int, rounds: int, key: bytes
) -> CampaignResult:
    rng = SplitMix64(seed)
    blinder = SyndromeBlinder(key)
    h = hashlib.sha256()
    failures = 0
    for i in range(rounds):
        rep = run_round(sample_frame(rng, px_wad, pz_wad), blinder, i)
        h.update(rep.serialize())
        failures += int(rep.logical_failure)
    return CampaignResult(rounds, failures, h.hexdigest())


if __name__ == "__main__":
    breaker = CircuitBreaker()
    print("risk @ p=1e-9:", format_wad(breaker.gate(10**9, 10**9)))
    try:
        breaker.gate(10**11, 10**11)
    except CircuitFreeze as exc:
        print("FREEZE:", exc)
