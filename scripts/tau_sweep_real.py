"""
tau_sweep_real.py — Tau (threshold-multiplier k) recalibration sweep on real
CIC-IDS2017 Friday-Afternoon-DDoS data.

Motivation
----------
On the real dataset with the default calibration tau = mu + 3*sigma, all 9
EAL configurations produce fires = 0 despite several having high AUC (e.g.
Permutation(W=32, s=1) reaches AUC-ROC = 0.990). This sweep asks:

    "For which k in {1.5, 2.0, 2.5, 3.0} does each configuration cross the
    detection threshold, and what FPR / detection-delay does that entail?"

The point is NOT to search a best k -- k stays a *configurable* knob, chosen
by the operator with the audit trail (mu, sigma, tau, k) exposed. This is
the configurability / auditability thesis of Paper 4 V2 made empirical.

Method
------
For each config in the native-minute grid, each warmup horizon and each k,
we call the exact same run_eal(...) machinery from eal_factorial_real.py
(imported below) with EALConfig(k=k, warmup_s=warmup). All other parameters
(W, s, stable-phase estimator, epsilon > tau firing rule) are unchanged.

Warmup horizons
---------------
Real CIC-IDS2017 Friday has 26 benign minutes before the DDoS starts at
t=1560 s. warmup=600 (default) uses only 10 of those 26 minutes, which is
not enough to compute mu_stable / sigma_stable for the larger windows
(W=32) -> tau=inf -> fires=0 regardless of k. This is a documented
empirical finding (Finding 6a in CHANGELOG_REAL.md), not a bug.

To isolate the *k* effect we also run the sweep at warmup ∈ {1200, 1500}
seconds (20 and 25 pre-attack minutes) so that mu_stable, sigma_stable are
well-defined and tau finite. This is not a silent recalibration -- both
result sets are preserved and reported side by side (Finding 6b).

Output
------
- results/eal_real/tau_sweep_summary.json                  : full grid
- results/eal_real/tau_sweep_by_k/warmup<W>_k<k>.json      : per warmup+k
- results/eal_real/tau_sweep/warmup<W>_<est>_W<W>_s<s>_k<k>.json : per cell
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

# Import machinery from the (unchanged) real-data factorial script.
import sys
sys.path.insert(0, str(Path(__file__).parent))
from eal_factorial_real import (  # noqa: E402
    EALConfig,
    aggregate_per_minute,
    run_eal,
)


NATIVE_MIN_GRID = [
    ("Shannon",      8, 4),
    ("Shannon",     16, 2),
    ("Shannon",     32, 1),
    ("Sample",       8, 4),
    ("Sample",      16, 2),
    ("Sample",      32, 1),
    ("Permutation",  8, 4),
    ("Permutation", 16, 2),
    ("Permutation", 32, 1),
]

K_VALUES = [1.5, 2.0, 2.5, 3.0]
WARMUP_VALUES = [600, 1200, 1500]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()

    a.output.mkdir(parents=True, exist_ok=True)
    per_cell_dir = a.output / "tau_sweep"
    by_k_dir = a.output / "tau_sweep_by_k"
    per_cell_dir.mkdir(exist_ok=True)
    by_k_dir.mkdir(exist_ok=True)

    df = pd.read_parquet(a.input)
    per_time = aggregate_per_minute(df)
    print(f"[tau-sweep] per-minute rows={len(per_time)}, "
          f"attack-minutes={int(per_time['label'].sum())}")

    all_rows: list[dict] = []
    for warmup in WARMUP_VALUES:
        print(f"\n[tau-sweep] ============ warmup = {warmup}s "
              f"({warmup/60:.0f} min pre-attack) ============")
        for k in K_VALUES:
            rows_k: list[dict] = []
            print(f"\n[tau-sweep] --- k = {k} ---")
            for est, W, s in NATIVE_MIN_GRID:
                cfg = EALConfig(estimator=est, W=W, s=s, warmup_s=warmup, k=k)
                _, m = run_eal(per_time, cfg)
                m["warmup_s"] = warmup
                tag = f"warmup{warmup}_{est.lower()}_W{W}_s{s}_k{k}"
                (per_cell_dir / f"{tag}.json").write_text(json.dumps(m, indent=2))
                rows_k.append(m)
                all_rows.append(m)
                delay = m["detection_delay_s"]
                delay_str = f"{delay:.0f}s" if not math.isnan(delay) else "miss"
                tau_str = ("inf" if math.isinf(m["tau"])
                           else f"{m['tau']:.3f}")
                print(f"  {est:11s} W={W:2d} s={s} | "
                      f"tau={tau_str:>7s}  "
                      f"AUC={m['AUC_ROC']:.3f}  "
                      f"fires={m['n_fires_post_warmup']:2d}  "
                      f"FPR={m['FPR_post_warmup']:.4f}  "
                      f"delay={delay_str}")
            (by_k_dir / f"warmup{warmup}_k{k}.json").write_text(json.dumps(rows_k, indent=2))

    (a.output / "tau_sweep_summary.json").write_text(json.dumps(all_rows, indent=2))
    print(f"\n[tau-sweep] wrote summary -> {a.output}/tau_sweep_summary.json")

    # Console summary: count detected per (warmup, k)
    print("\n[tau-sweep] Detection count per (warmup, k) (across 9 configs):")
    print("           k=1.5   k=2.0   k=2.5   k=3.0")
    for warmup in WARMUP_VALUES:
        cells = []
        for k in K_VALUES:
            det = sum(1 for r in all_rows
                      if r["warmup_s"] == warmup and r["k"] == k and r["detected"])
            cells.append(f"{det}/9")
        print(f"  warmup={warmup:4d}s  " + "   ".join(f"{c:>5s}" for c in cells))


if __name__ == "__main__":
    main()
