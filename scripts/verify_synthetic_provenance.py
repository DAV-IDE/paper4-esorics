#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_synthetic_provenance.py — Paper 4 ESORICS artefact
==========================================================

Verifies that the imported 45-run entropy factorial artefacts under
``results/synthetic/`` still match the SHA-256 hashes pinned in
``results/synthetic/provenance.json``.

Usage (from repo root):

    python scripts/verify_synthetic_provenance.py

Exit codes:
    0  all files present and hashes match
    1  at least one file missing or hash mismatch

This is a static verification script: it does NOT re-download files
from the companion repository, and it does NOT execute the upstream
pipeline. It only re-computes local SHA-256s and compares them to the
pinned values.

Rationale: the 45-run entropy factorial (Paper 4, Table 6) is generated
by the upstream companion pipeline
https://github.com/LoreBerto03/psi-risk-dt-pipeline (reference [3] in
the paper). Two of its output files are imported here as a verified
snapshot so that paper4-esorics can be built and reviewed without
running the upstream Docker/Fuseki stack. Any drift between the
imported files and the pinned hashes must be caught by this script.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "results" / "synthetic" / "provenance.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not MANIFEST.exists():
        print(f"[FAIL] Manifest not found: {MANIFEST}", file=sys.stderr)
        return 1

    with MANIFEST.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    imported = manifest.get("imported_files", [])
    if not imported:
        print("[FAIL] Manifest has no 'imported_files' entries.", file=sys.stderr)
        return 1

    print(f"Verifying {len(imported)} imported artefact(s) against {MANIFEST.name}")
    print(f"Source: {manifest['source']['repository']} @ {manifest['source']['commit_sha']}")
    print("-" * 72)

    all_ok = True
    for entry in imported:
        local_rel = entry["local_path"]
        expected = entry["sha256"]
        local_path = REPO_ROOT / local_rel

        if not local_path.exists():
            print(f"[MISS] {local_rel}  (file not found)")
            all_ok = False
            continue

        actual = sha256_of(local_path)
        if actual == expected:
            print(f"[ OK ] {local_rel}  sha256={actual}")
        else:
            print(f"[FAIL] {local_rel}")
            print(f"       expected: {expected}")
            print(f"       actual:   {actual}")
            all_ok = False

    print("-" * 72)
    if all_ok:
        print("All imported artefacts verified successfully.")
        return 0
    else:
        print("Verification FAILED — at least one artefact is missing or altered.")
        print("If this is intentional (e.g., re-import from a newer companion commit),")
        print("update the SHA-256 values and source.commit_sha in provenance.json.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
