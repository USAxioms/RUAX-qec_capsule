#!/usr/bin/env python3
"""Build a deterministic release zip of the QEC reproducibility capsule.

  python package_capsule.py build           seal, then write dist/qec_capsule.zip
  python package_capsule.py verify-zip PATH extract to a temp dir and run capsule verify

Determinism: entries are sorted, stored uncompressed (no zlib-version drift),
fixed timestamp (1980-01-01), fixed permissions, LF line endings. Stdlib only.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List

import capsule

PREFIX = "qec_capsule/"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
SUMS_NAME = "SHA256SUMS"

README = """\
QEC Reproducibility Capsule
===========================
Steane [[7,1,3]] Pauli-frame simulator with 10^18 fixed-point risk accounting.
Stdlib only. Python 3.8+.

Files
  capsule.py            seal/verify tooling
  qec_wad18.py          core: WAD arithmetic, decoder, circuit breaker, blinding
  test_qec_oracle.py    verification suite with an independent reference oracle
  capsule.lock.json     hashes and golden values recorded at seal time
  SHA256SUMS            hashes of every other file in this archive

Verify (from the extracted folder)
  sha256sum -c SHA256SUMS
  python capsule.py verify

Scope
  Classical Pauli-frame simulation, not quantum amplitudes. Blinding is a 3-bit
  keyed XOR mask, not strong privacy. The Compton limit is the constant 2500
  WAD units (2.5e-15).
"""


def collect(here: Path) -> Dict[str, bytes]:
    capsule_py = (here / "capsule.py").read_bytes()
    lock = (here / capsule.LOCK_NAME).read_bytes()
    for label, data in (("capsule.py", capsule_py), ("lock", lock)):
        if b"\r" in data:
            raise ValueError(f"{label}: contains CR; normalise to LF before packaging")
    files: Dict[str, bytes] = {
        "capsule.py": capsule_py,
        capsule.LOCK_NAME: lock,
        "README.txt": README.encode("utf-8"),
    }
    for name in capsule.SOURCES:
        files[name] = capsule.source_bytes(name)
    sums = "".join(f"{capsule.sha256_hex(files[n])}  {n}\n" for n in sorted(files))
    files[SUMS_NAME] = sums.encode("ascii")
    return files


def write_zip(files: Dict[str, bytes], out: Path) -> str:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(PREFIX + name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])
    digest = capsule.sha256_hex(out.read_bytes())
    out.with_name(out.name + ".sha256").write_text(
        f"{digest}  {out.name}\n", encoding="ascii"
    )
    return digest


def extract_safely(zip_path: Path, dest: Path) -> List[str]:
    names: List[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            n = info.filename
            if not n.startswith(PREFIX) or ".." in n.split("/") or n.endswith("/"):
                raise ValueError(f"unexpected archive entry: {n!r}")
            rel = n[len(PREFIX):]
            (dest / rel).write_bytes(zf.read(info))
            names.append(rel)
    return sorted(names)


def check_zip(zip_path: Path) -> int:
    sidecar = zip_path.with_name(zip_path.name + ".sha256")
    if sidecar.is_file():
        want = sidecar.read_text(encoding="ascii").split()[0]
        got = capsule.sha256_hex(zip_path.read_bytes())
        print(f"[{'PASS' if want == got else 'FAIL'}] zip sha256 matches sidecar")
        if want != got:
            return 1
    else:
        print("[WARN] no .sha256 sidecar; skipping archive hash check")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        names = extract_safely(zip_path, root)
        listed: Dict[str, str] = {}
        for line in (root / SUMS_NAME).read_text(encoding="ascii").splitlines():
            h, _, n = line.partition("  ")
            listed[n] = h
        bad = [n for n in names if n != SUMS_NAME
               and capsule.sha256_hex((root / n).read_bytes()) != listed.get(n)]
        print(f"[{'PASS' if not bad else 'FAIL'}] SHA256SUMS match extracted files"
              + (f" ({', '.join(bad)})" if bad else ""))
        if bad:
            return 1
        proc = subprocess.run([sys.executable, "capsule.py", "verify"], cwd=str(root))
        return proc.returncode


def build() -> int:
    here = Path(__file__).resolve().parent
    rc = capsule.seal(here / capsule.LOCK_NAME)
    if rc != 0:
        print("[package] REFUSED: seal failed")
        return rc
    out = here / "dist" / "qec_capsule.zip"
    digest = write_zip(collect(here), out)
    second = here / "dist" / "_rebuild.zip"
    d2 = write_zip(collect(here), second)
    second.unlink()
    second.with_name(second.name + ".sha256").unlink()
    if digest != d2 or digest != capsule.sha256_hex(out.read_bytes()):
        print("[package] REFUSED: zip is not byte-reproducible")
        return 1
    print(f"[package] wrote {out}")
    print(f"[package] zip sha256:     {digest}")
    print(f"[package] capsule digest: {capsule.capsule_digest()}")
    print("[package] verifying the archive as a recipient would...")
    return check_zip(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    vz = sub.add_parser("verify-zip")
    vz.add_argument("path")
    args = ap.parse_args()
    if args.cmd == "build":
        return build()
    return check_zip(Path(args.path))


if __name__ == "__main__":
    sys.exit(main())
