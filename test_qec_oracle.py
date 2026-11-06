#!/usr/bin/env python3
"""Verification suite for qec_wad18. Run: python -m unittest test_qec_oracle -v

Includes an independent reference implementation (explicit check rows, brute-force
minimum-weight decoding, exact Fraction arithmetic) that shares no code with the core.
"""
from __future__ import annotations

import unittest
from fractions import Fraction
from itertools import combinations
from typing import Dict, FrozenSet

import qec_wad18 as q

KEY = b"0123456789abcdef-test-key"


def fresh_blinder() -> q.SyndromeBlinder:
    return q.SyndromeBlinder(KEY)


# ---------------------------- independent reference -------------------------
REF_ROWS = (0b1010101, 0b1100110, 0b1111000)


def _pc(x: int) -> int:
    return bin(x).count("1")


def ref_syndrome(v: int) -> int:
    s = 0
    for j in range(7):
        if (v >> j) & 1:
            s ^= j + 1
    return s


def ref_stabilizers() -> FrozenSet[int]:
    out = {0}
    for row in REF_ROWS:
        out |= {x ^ row for x in out}
    return frozenset(out)


def ref_leaders() -> Dict[int, int]:
    best: Dict[int, int] = {}
    for v in range(128):
        s = ref_syndrome(v)
        if s not in best or _pc(v) < _pc(best[s]):
            best[s] = v
    return best


def ref_channel_failure(p: Fraction) -> Fraction:
    leaders, stabs = ref_leaders(), ref_stabilizers()
    total = Fraction(0)
    for v in range(128):
        residual = v ^ leaders[ref_syndrome(v)]
        if residual not in stabs:
            w = _pc(v)
            total += p**w * (1 - p) ** (7 - w)
    return total


def ref_risk_wad(px: int, pz: int) -> Fraction:
    fx = ref_channel_failure(Fraction(px, q.WAD))
    fz = ref_channel_failure(Fraction(pz, q.WAD))
    return (fx + fz - fx * fz) * q.WAD


# ---------------------------------- tests -----------------------------------
class WadArithmeticTests(unittest.TestCase):
    def test_parse_and_format_roundtrip(self) -> None:
        self.assertEqual(q.parse_wad("0.1"), 10**17)
        self.assertEqual(q.parse_wad("2"), 2 * q.WAD)
        self.assertEqual(q.format_wad(q.parse_wad("0.000000000000000001")),
                         "0.000000000000000001")

    def test_rejects_floats_and_excess_precision(self) -> None:
        with self.assertRaises(TypeError):
            q.mul_wad(0.5, q.WAD)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            q.parse_wad(0.1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            q.parse_wad("0.0000000000000000001")  # 19 decimals
        with self.assertRaises(ValueError):
            q.parse_wad("1e-9")

    def test_identities(self) -> None:
        for x in (0, 1, 12345, 10**9, q.WAD - 1, q.WAD):
            self.assertEqual(q.mul_wad(q.WAD, x), x)
            self.assertEqual(q.div_wad(x, q.WAD), x)
        self.assertEqual(q.mul_wad(10**9, 10**9), 1)
        with self.assertRaises(ZeroDivisionError):
            q.div_wad(1, 0)

    def test_prng_is_deterministic(self) -> None:
        a, b = q.SplitMix64(42), q.SplitMix64(42)
        self.assertEqual([a.next_u64() for _ in range(16)],
                         [b.next_u64() for _ in range(16)])


class CodeStructureTests(unittest.TestCase):
    def test_single_qubit_syndrome_names_the_qubit(self) -> None:
        for i in range(q.N_QUBITS):
            self.assertEqual(q.syndrome(1 << i), i + 1)

    def test_decoder_verifies(self) -> None:
        self.assertTrue(q.verify_decoder())

    def test_stabilizer_group_has_eight_elements(self) -> None:
        members = [v for v in range(128) if q.in_stabilizer_group(v)]
        self.assertEqual(len(members), 8)
        self.assertTrue(all(q.popcount(v) in (0, 4) for v in members))

    def test_logical_operator_is_not_stabilizer(self) -> None:
        self.assertEqual(q.syndrome(0b1111111), 0)
        self.assertFalse(q.in_stabilizer_group(0b1111111))

    def test_all_weight_two_errors_fail_distance_three(self) -> None:
        for a, b in combinations(range(7), 2):
            residual = q.correct((1 << a) | (1 << b))
            self.assertFalse(q.in_stabilizer_group(residual))

    def test_stabilizer_product_sign(self) -> None:
        self.assertEqual(q.stabilizer_product(0), 1)
        self.assertEqual(q.stabilizer_product(0b011), 1)
        self.assertEqual(q.stabilizer_product(0b001), -1)


class IndependentOracleTests(unittest.TestCase):
    def test_check_rows_are_pinned_literals(self) -> None:
        self.assertEqual(q.CHECK_ROWS, REF_ROWS)

    def test_syndrome_matches_reference_for_all_128_patterns(self) -> None:
        for v in range(128):
            self.assertEqual(q.syndrome(v), ref_syndrome(v), v)

    def test_css_orthogonality(self) -> None:
        for a, b in combinations(REF_ROWS, 2):
            self.assertEqual(_pc(a & b) % 2, 0)
        for a in REF_ROWS:
            self.assertEqual(_pc(a) % 2, 0)

    def test_decode_table_equals_minimum_weight_coset_leaders(self) -> None:
        leaders = ref_leaders()
        for s in range(8):
            self.assertEqual(q.DECODE_TABLE[s], leaders[s], s)

    def test_stabilizer_predicate_equals_row_span(self) -> None:
        stabs = ref_stabilizers()
        self.assertEqual(len(stabs), 8)
        for v in range(128):
            self.assertEqual(q.in_stabilizer_group(v), v in stabs, v)

    def test_exact_risk_matches_fraction_oracle(self) -> None:
        pairs = [(0, 0), (1, 1), (10**9, 10**9), (7 * 10**9, 7 * 10**9),
                 (10**9, 10**15), (10**12, 10**12), (10**15, 10**15),
                 (10**16, 10**16), (q.WAD // 10, q.WAD // 10),
                 (q.WAD // 2, q.WAD // 2), (q.WAD, q.WAD), (0, q.WAD)]
        for px, pz in pairs:
            got = Fraction(q.logical_failure_wad(px, pz))
            self.assertLessEqual(abs(got - ref_risk_wad(px, pz)), 3, (px, pz))


class FaultInjectionTests(unittest.TestCase):
    def test_every_single_qubit_x_z_y_is_recovered(self) -> None:
        for i in range(q.N_QUBITS):
            for kind in ("x", "z", "y"):
                frame = q.PauliFrame()
                getattr(frame, f"inject_{kind}")(1 << i)
                rep = q.run_round(frame, fresh_blinder(), i)
                self.assertFalse(rep.logical_failure, (i, kind))
                self.assertEqual((frame.x, frame.z), (0, 0), (i, kind))

    def test_simultaneous_x_and_z_on_any_qubit_pair_recovered(self) -> None:
        for a in range(7):
            for b in range(7):
                frame = q.PauliFrame()
                frame.inject_x(1 << a)
                frame.inject_z(1 << b)
                rep = q.run_round(frame, fresh_blinder(), 0)
                self.assertFalse(rep.logical_failure)
                self.assertEqual((frame.x, frame.z), (0, 0))

    def test_double_x_error_is_detected_as_logical_failure(self) -> None:
        frame = q.PauliFrame()
        frame.inject_x(0b0000011)
        self.assertTrue(q.run_round(frame, fresh_blinder(), 0).logical_failure)

    def test_double_z_error_is_detected_as_logical_failure(self) -> None:
        frame = q.PauliFrame()
        frame.inject_z(0b1010000)
        self.assertTrue(q.run_round(frame, fresh_blinder(), 0).logical_failure)

    def test_error_free_round_is_silent(self) -> None:
        frame = q.PauliFrame()
        rep = q.run_round(frame, fresh_blinder(), 7)
        self.assertEqual((rep.correction_x, rep.correction_z), (0, 0))
        self.assertEqual((rep.parity_x, rep.parity_z), (1, 1))
        self.assertFalse(rep.logical_failure)

    def test_injection_rejects_out_of_range_masks(self) -> None:
        with self.assertRaises(ValueError):
            q.PauliFrame().inject_x(1 << 7)


class BlindingTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        b = fresh_blinder()
        for s in range(8):
            for r in (0, 1, 99):
                for ch in (q.CHANNEL_X, q.CHANNEL_Z):
                    self.assertEqual(b.unblind(b.blind(s, r, ch), r, ch), s)

    def test_mask_varies_with_round_and_channel(self) -> None:
        b = fresh_blinder()
        self.assertGreater(len({b.mask(r, 0) for r in range(64)}), 1)
        self.assertTrue(any(b.mask(r, 0) != b.mask(r, 1) for r in range(64)))

    def test_different_keys_give_different_masks(self) -> None:
        other = q.SyndromeBlinder(b"another-key-another-key")
        b = fresh_blinder()
        self.assertTrue(any(b.mask(r, 0) != other.mask(r, 0) for r in range(64)))

    def test_short_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            q.SyndromeBlinder(b"short")

    def test_wrong_key_unblinds_to_wrong_syndrome(self) -> None:
        a = fresh_blinder()
        b = q.SyndromeBlinder(b"a-completely-different-key")
        wrong = sum(1 for r in range(64)
                    if b.unblind(a.blind(5, r, q.CHANNEL_X), r, q.CHANNEL_X) != 5)
        self.assertGreater(wrong, 0)

    def test_report_exposes_only_blinded_syndromes(self) -> None:
        frame = q.PauliFrame()
        frame.inject_x(1 << 4)  # true syndrome 5
        rep = q.run_round(frame, fresh_blinder(), 3)
        self.assertEqual(rep.blinded_sx, 5 ^ fresh_blinder().mask(3, q.CHANNEL_X))
        self.assertEqual(rep.correction_x, 1 << 4)


class RiskAndBreakerTests(unittest.TestCase):
    def test_exact_values(self) -> None:
        self.assertEqual(q.logical_failure_wad(0, 0), 0)
        self.assertEqual(q.logical_failure_wad(q.WAD, q.WAD), q.WAD)
        self.assertEqual(q.logical_failure_wad(10**9, 10**9), 42)

    def test_risk_is_monotone(self) -> None:
        ps = [10**9, 10**10, 10**12, 10**15, 10**16]
        risks = [q.logical_failure_wad(p, p) for p in ps]
        self.assertEqual(risks, sorted(risks))

    def test_gate_passes_below_and_trips_above_limit(self) -> None:
        self.assertEqual(q.CircuitBreaker().gate(7 * 10**9, 7 * 10**9), 2058)
        with self.assertRaises(q.CircuitFreeze):
            q.CircuitBreaker().gate(8 * 10**9, 8 * 10**9)  # risk 2688 > 2500

    def test_boundary_is_tight_to_one_wad_unit_of_p(self) -> None:
        def risk(p: int) -> int:
            return q.logical_failure_wad(p, p)

        lo, hi = 0, 10**10
        self.assertLessEqual(risk(lo), q.COMPTON_LIMIT_WAD)
        self.assertGreater(risk(hi), q.COMPTON_LIMIT_WAD)
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if risk(mid) <= q.COMPTON_LIMIT_WAD:
                lo = mid
            else:
                hi = mid
        self.assertTrue(7 * 10**9 < lo < 8 * 10**9)
        self.assertEqual(q.CircuitBreaker().gate(lo, lo), risk(lo))
        with self.assertRaises(q.CircuitFreeze):
            q.CircuitBreaker().gate(hi, hi)

    def test_realistic_hardware_rate_trips(self) -> None:
        with self.assertRaises(q.CircuitFreeze):
            q.CircuitBreaker().gate(10**15, 10**15)  # p = 1e-3

    def test_breaker_latches(self) -> None:
        br = q.CircuitBreaker()
        with self.assertRaises(q.CircuitFreeze):
            br.gate(q.WAD // 2, q.WAD // 2)
        self.assertTrue(br.frozen)
        with self.assertRaises(q.CircuitFreeze):
            br.gate(10**9, 10**9)  # valid input, still frozen
        with self.assertRaises(q.CircuitFreeze):
            q.run_round(q.PauliFrame(), fresh_blinder(), 0, breaker=br)

    def test_out_of_bounds_rates_freeze(self) -> None:
        for bad in (q.WAD + 1, -1, 0.5, "0.1", None):
            br = q.CircuitBreaker()
            with self.assertRaises(q.CircuitFreeze, msg=repr(bad)):
                br.gate(bad, 0)
            self.assertTrue(br.frozen)

    def test_limit_cannot_be_loosened(self) -> None:
        with self.assertRaises(ValueError):
            q.CircuitBreaker(q.COMPTON_LIMIT_WAD + 1)
        self.assertEqual(q.CircuitBreaker(100).gate(10**9, 10**9), 42)


class MutationTests(unittest.TestCase):
    def test_corrupted_decode_table_is_detected(self) -> None:
        mutated = list(q.DECODE_TABLE)
        mutated[3] = 1 << 0  # should be 1 << 2
        self.assertFalse(q.verify_decoder(mutated))
        with self.assertRaises(q.CircuitFreeze):
            q.CircuitBreaker().gate(10**9, 10**9, table=mutated)

    def test_corrupted_check_matrix_is_detected(self) -> None:
        rows = list(q.CHECK_ROWS)
        rows[0] ^= 0b1
        self.assertFalse(q.verify_decoder(q.DECODE_TABLE, rows))

    def test_mutated_table_changes_failure_probability(self) -> None:
        mutated = list(q.DECODE_TABLE)
        mutated[5] = 0
        self.assertNotEqual(q.logical_failure_wad(10**9, 10**9, mutated),
                            q.logical_failure_wad(10**9, 10**9))

    def test_wrong_length_table_rejected(self) -> None:
        self.assertFalse(q.verify_decoder([0, 1, 2]))


class ReproducibilityTests(unittest.TestCase):
    def test_same_seed_same_digest(self) -> None:
        p = 10**16
        self.assertEqual(q.run_campaign(2024, p, p, 2000, KEY),
                         q.run_campaign(2024, p, p, 2000, KEY))

    def test_different_seed_different_digest(self) -> None:
        p = 10**16
        a = q.run_campaign(1, p, p, 2000, KEY)
        b = q.run_campaign(2, p, p, 2000, KEY)
        self.assertNotEqual(a.digest, b.digest)

    def test_monte_carlo_agrees_with_exact_risk(self) -> None:
        p = 10**16  # 0.01
        rounds = 20000
        res = q.run_campaign(7, p, p, rounds, KEY)
        predicted = q.logical_failure_wad(p, p)
        observed = res.failures * q.WAD // rounds
        self.assertGreaterEqual(observed, predicted // 2)
        self.assertLessEqual(observed, predicted * 2)

    def test_zero_noise_never_fails(self) -> None:
        self.assertEqual(q.run_campaign(5, 0, 0, 500, KEY).failures, 0)


if __name__ == "__main__":
    unittest.main()
