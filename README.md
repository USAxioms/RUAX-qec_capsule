# RUAX-QEC Reproducibility Capsule

Steane [[7,1,3]] Pauli-frame simulator with 10^18 fixed-point (WAD) risk
accounting. Python 3.8+, standard library only.

| File | Purpose |
|---|---|
| `qec_wad18.py` | WAD arithmetic, decoder, circuit breaker, syndrome blinding, campaigns |
| `test_qec_oracle.py` | Test suite with an independent reference oracle |
| `capsule.py` | `test`, `seal`, `verify`, `digest` commands |
| `package_capsule.py` | Builds a byte-reproducible release zip |
| `capsule.lock.json` | Hashes and golden values recorded by `seal` |

## Usage

```
python capsule.py test       # run the suite
python capsule.py seal       # tests + determinism checks, writes capsule.lock.json
python capsule.py verify     # re-check files, hashes, golden values, tests
python package_capsule.py build
```

## Scope and limits

- Simulates classical Pauli error frames, not quantum amplitudes.
- Syndrome blinding is a keyed 3-bit XOR mask. It is not strong privacy.
- The "Compton" limit is the constant 2500 WAD units (2.5e-15), applied to the
  exact predicted logical-failure probability.
- The first `seal` is trust-on-first-use. Run `verify` on a second machine to
  check cross-platform reproducibility.
