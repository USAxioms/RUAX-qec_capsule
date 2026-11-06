::: {align="center"}
# RUAX-QEC Reproducibility Capsule

**Deterministic quantum error-correction simulation with fixed-point
risk accounting**

[![Python
3.8+](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-standard%20library-2E7D32)](#requirements)
[![Reproducibility](https://img.shields.io/badge/release-byte--reproducible-5B4B8A)](#reproducible-release-workflow)

*A self-contained, auditable capsule for running, sealing, verifying,
and packaging a Steane-code Pauli-frame simulation.*
:::

------------------------------------------------------------------------

## Overview

`RUAX-qec_capsule` is a reproducibility-focused implementation of a
**Steane (\[\[7,1,3\]\]) quantum error-correction Pauli-frame
simulator** with **(10\^{18})-scale fixed-point risk accounting** using
WAD-18 arithmetic.

The repository is organized as a compact verification workflow rather
than as a simulator script alone. It separates the simulation and
arithmetic implementation, the independent-reference test suite, the
capsule commands used to seal and verify an execution, and the
release-packaging utility.

The goal is to make computational results inspectable and repeatable:
users can run the test suite, create a sealed record of the capsule
state, verify the recorded files and expected values, and build a
byte-reproducible release archive.

## What this capsule contains

  -----------------------------------------------------------------------
  Component                           Responsibility
  ----------------------------------- -----------------------------------
  `qec_wad18.py`                      WAD arithmetic, decoder, circuit
                                      breaker, syndrome blinding, and
                                      campaigns

  `test_qec_oracle.py`                Test suite with an independent
                                      reference oracle

  `capsule.py`                        `test`, `seal`, `verify`, and
                                      `digest` capsule commands

  `package_capsule.py`                Builds a byte-reproducible release
                                      ZIP

  `capsule.lock.json`                 Records hashes and golden values
                                      produced by the sealing workflow

  `README.md`                         Project description and operating
                                      instructions
  -----------------------------------------------------------------------

## Technical scope

### Steane (\[\[7,1,3\]\]) code

The simulator is identified with the Steane (\[\[7,1,3\]\]) quantum
error-correction code and a Pauli-frame simulation approach. The code
parameters indicate seven physical qubits encoding one logical qubit,
with code distance three.

The repository's implementation is the authoritative source for the
precise circuit, noise, decoding, and campaign semantics. This README
intentionally does not infer unsupported physical-device behavior or
claim that a software simulation is equivalent to execution on quantum
hardware.

### WAD-18 fixed-point risk accounting

Risk accounting is represented using fixed-point integer arithmetic at
an 18-decimal scale:

\[ S = 10\^{18} \]

The intended numerical benefit is an explicit, deterministic integer
representation at the accounting boundary, rather than relying on binary
floating-point values for those calculations. The implementation in
`qec_wad18.py` defines the actual arithmetic and domain behavior.

Fixed-point representation can improve reproducibility of numerical
operations when consistently applied. It does **not**, by itself,
establish that a risk model is physically complete, that its assumptions
are correct, or that a system is safe.

### Independent reference testing

The repository includes `test_qec_oracle.py`, described as a test suite
with an independent reference oracle. This provides a separate reference
path against which implementation behavior can be checked.

The existence of an independent oracle is a verification design feature;
the strength of the evidence depends on the oracle's independence,
coverage, test vectors, and the results obtained when the suite is run.

## Requirements

-   Python **3.8 or newer**
-   Python standard library only, according to the project specification
    shown in this repository
-   No third-party Python packages are required for the documented
    commands

Run commands from the repository root.

## Quick start

### 1. Run the test suite

``` bash
python capsule.py test
```

Runs the capsule's test workflow, including the project's configured
test suite.

### 2. Seal the capsule

``` bash
python capsule.py seal
```

Runs tests and determinism checks, then writes the capsule's recorded
hashes and golden values to `capsule.lock.json`.

Treat the resulting lock file as an output of the sealing process.
Review and preserve it with the corresponding source state when
recording a reproducible run.

### 3. Verify the sealed capsule

``` bash
python capsule.py verify
```

Re-checks the files, hashes, and recorded golden values against the
sealed capsule state.

A successful verification indicates that the checks implemented by this
repository passed for the files and values examined. It should not be
interpreted as proof of correctness beyond those checks.

### 4. Build the release archive

``` bash
python package_capsule.py build
```

Builds the byte-reproducible release ZIP using the repository's
packaging implementation.

For a clean reproducibility check, build from the same committed source
state and compare the resulting archive bytes or digest across
independent runs.

## Reproducible release workflow

A recommended sequence is:

``` bash
python capsule.py test
python capsule.py seal
python capsule.py verify
python package_capsule.py build
```

For a stronger independent review:

1.  Start from a clean checkout of the source revision being evaluated.
2.  Record the Python version and platform used for the run.
3.  Execute the test command and retain its complete output.
4.  Seal the capsule and preserve `capsule.lock.json`.
5.  Run verification after sealing.
6.  Build the release archive.
7.  Repeat the workflow in a separate clean environment.
8.  Compare the lock records and release archive digests; investigate
    any difference rather than silently replacing the original record.

The commands above describe the repository's documented interface. Exact
output formats, hash algorithms, included files, and golden-value
semantics should be taken from the implementation and generated records.

## Repository layout

``` text
RUAX-qec_capsule/
├── .gitattributes
├── .gitignore
├── README.md
├── capsule.lock.json
├── capsule.py
├── package_capsule.py
├── qec_wad18.py
└── test_qec_oracle.py
```

## Evidence and interpretation

This project is structured to support reproducible computational review.
Its evidence should be interpreted in distinct layers:

  -----------------------------------------------------------------------
  Evidence layer          What it can support     What it does not
                                                  establish by itself
  ----------------------- ----------------------- -----------------------
  Mathematical            Properties that follow  That the implementation
  specification           from stated definitions matches the
                          and assumptions         specification

  Implementation          What the source code    That the computation
                          actually computes       models every relevant
                                                  physical effect

  Tests and reference     Agreement on the tested Exhaustive correctness
  oracle                  cases and assertions    or complete fault
                                                  coverage

  Determinism and         Repeatability and       Scientific validity of
  integrity checks        integrity of the        the model or safety of
                          checked artifacts       a deployed system

  Physical validation     Agreement with relevant Anything beyond the
                          experimental or         tested conditions and
                          hardware evidence, if   measurement limits
                          performed               
  -----------------------------------------------------------------------

No claim of hardware validation, fault-tolerant quantum operation,
exhaustive correctness, or guaranteed safety is made here solely on the
basis of this capsule's structure. Such claims require separate,
appropriately scoped evidence.

## Design principles

-   **Deterministic representation:** use fixed-point integer accounting
    where defined by the WAD-18 implementation.
-   **Independent checking:** provide a reference-oracle test path
    rather than relying only on self-consistency checks.
-   **Explicit sealing:** record hashes and golden values in a lock
    file.
-   **Verifiable state:** provide a command to re-check the sealed files
    and values.
-   **Reproducible packaging:** provide a dedicated release-building
    utility.
-   **Bounded claims:** distinguish mathematical properties, software
    behavior, test evidence, and physical validation.

## Current status

This README describes the repository structure and command interface
visible in the project snapshot. It does not publish test counts, pass
rates, mutation scores, benchmark results, physical validation results,
or a certification level because those values are not established by the
repository information represented here.

For an evaluation or release, publish the exact source revision,
environment details, command outputs, generated lock file, and release
digest alongside any reported metrics.

## Contributing and review

Technical review is most useful when it is reproducible. Please include:

-   the exact commit or source archive reviewed;
-   Python version and execution environment;
-   commands executed and complete outputs;
-   any changed assumptions, test vectors, or model parameters;
-   independently reproduced discrepancies, with a minimal example where
    possible.

Changes to arithmetic, decoder behavior, simulation semantics, sealing,
or packaging should be accompanied by tests that make the intended
behavior explicit.

## License

No license is specified in the project snapshot represented by this
README. Until a license is added to the repository, users should not
assume that the source is available for unrestricted reuse,
modification, or redistribution.

------------------------------------------------------------------------

::: {align="center"}
**RUAX-QEC Reproducibility Capsule**\
*Reproducibility is an engineering property to be tested, recorded, and
independently checked.*
:::
