#!/usr/bin/env python3
"""Reproducibility capsule tooling for the Steane [[7,1,3]] QEC core.

Commands (run from the repo root):
  test    run the verification suite
  seal    run tests + determinism checks, then write capsule.lock.json
  verify  check files, hashes, golden values and tests against the lock
  digest  print the capsule digest
Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

SCHEMA = 1
LOCK_NAME = "capsule.lock.json"
HERE = Path(__file__).resolve().parent
SOURCES = ("qec_wad18.py", "test_qec_oracle.py")

# Probe executed in a subprocess; prints golden values as canonical JSON.
_GOLDEN_PROBE = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import qec_wad18 as q
KEY = b"capsule-golden-key-0001"
out = {"risk": {}, "campaigns": {}}
for label, p in (("1e-9", 10**9), ("7e-9", 7 * 10**9), ("1e-3", 10**15), ("1e-2", 10**16)):
    out["risk"][label] = q.logical_failure_wad(p, p)
for seed, p, n in ((1, 10**16, 5000), (2024, 10**15, 5000)):
    r = q.run_campaign(seed, p, p, n, KEY)
    out["campaigns"][f"{seed}:{p}:{n}"] = {"failures": r.failures, "digest": r.digest}
print(json.dumps(out, sort_keys=True))
'''


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_bytes(name: str) -> bytes:
    data = (HERE / name).read_bytes()
    if b"\r" in data:
        raise ValueError(f"{name}: contains CR; files must use LF line endings")
    if not data.endswith(b"\n"):
        raise ValueError(f"{name}: missing trailing newline")
    return data


def source_hashes() -> Dict[str, str]:
    return {n: sha256_hex(source_bytes(n)) for n in sorted(SOURCES)}


def capsule_digest() -> str:
    h = hashlib.sha256()
    for name, digest in sorted(source_hashes().items()):
        h.update(name.encode("utf-8") + b"\0" + digest.encode("ascii") + b"\n")
    return h.hexdigest()


def _env() -> Dict[str, str]:
    return dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")


def run_tests() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "test_qec_oracle", "-v"],
        cwd=str(HERE), env=_env(),
    )
    return proc.returncode


def golden() -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _GOLDEN_PROBE, str(HERE)],
        capture_output=True, text=True, env=_env(), check=True,
    )
    return json.loads(proc.stdout)


def seal(lock_path: Path) -> int:
    source_hashes()  # validates LF / trailing newline
    if run_tests() != 0:
        print("[seal] REFUSED: test suite failed; lock not written")
        return 1
    g1, g2 = golden(), golden()
    if g1 != g2:
        print("[seal] REFUSED: golden probe is not repeatable")
        return 1
    lock = {
        "schema": SCHEMA,
        "capsule_digest": capsule_digest(),
        "files": source_hashes(),
        "golden": g1,
        "recorded_with": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
    }
    payload = json.dumps(lock, indent=2, sort_keys=True) + "\n"
    lock_path.write_bytes(payload.encode("utf-8"))
    print(f"[seal] wrote {lock_path}")
    print(f"[seal] capsule digest: {lock['capsule_digest']}")
    return 0


def verify(lock_path: Path, skip_tests: bool) -> int:
    results: List[bool] = []

    def rec(label: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        suffix = f" ({detail})" if detail and not ok else ""
        print(f"[{'PASS' if ok else 'FAIL'}] {label}{suffix}")

    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[FAIL] cannot read lock {lock_path}: {exc}")
        return 2

    rec("lock schema", lock.get("schema") == SCHEMA)
    try:
        hashes = source_hashes()
    except (OSError, ValueError) as exc:
        rec("source files readable and LF-only", False, str(exc))
        print("VERIFICATION FAILED")
        return 1
    rec("source files readable and LF-only", True)
    rec("file hashes match lock", lock.get("files") == hashes)
    rec("capsule digest matches lock", lock.get("capsule_digest") == capsule_digest())
    for name in sorted(SOURCES):
        try:
            compile(source_bytes(name), name, "exec")
            rec(f"{name} compiles", True)
        except SyntaxError as exc:
            rec(f"{name} compiles", False, str(exc))
    try:
        now = golden()
        rec("golden risk values reproduce", now.get("risk") == lock["golden"]["risk"])
        rec("golden campaign digests reproduce",
            now.get("campaigns") == lock["golden"]["campaigns"])
    except (subprocess.CalledProcessError, KeyError, ValueError) as exc:
        rec("golden probe", False, str(exc))
    if not skip_tests:
        rec("test suite passes", run_tests() == 0)

    ok = all(results)
    print("VERIFIED" if ok else "VERIFICATION FAILED")
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--lock", default=str(HERE / LOCK_NAME), help="lock file path")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("test", "seal", "digest"):
        sub.add_parser(name, parents=[parent])
    vp = sub.add_parser("verify", parents=[parent])
    vp.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "test":
        return run_tests()
    if args.cmd == "seal":
        return seal(Path(args.lock))
    if args.cmd == "verify":
        return verify(Path(args.lock), args.skip_tests)
    print(capsule_digest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
