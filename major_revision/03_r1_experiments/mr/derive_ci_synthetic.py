"""I-15b (R1-4): 95% CIs for the per-cell medians of the synthetic 30-seed factorial.
Post-processing only: reads the frozen long table, re-runs NO experiment.
- delay median CI : percentile bootstrap, B=2000, seed=0 (same function as analysis_stats.boot_ci_median);
                    recomputed and checked against the frozen cell_summary_synthetic.csv
- FPA median CI   : NEW, same bootstrap applied to FPA_rate_pre over all 30 seeds
- detection rate  : Wilson 95% (copied from frozen summary, recomputed as check)
"""
import argparse, hashlib, json, sys, platform
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from analysis_stats import boot_ci_median, wilson

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

ap = argparse.ArgumentParser(); ap.add_argument("--res", required=True); a = ap.parse_args()
R = Path(a.res); inp = R / "03_synthetic_multiseed/synthetic_multiseed_long.csv.gz"; frz = R / "04_stats/cell_summary_synthetic.csv"
out = R / "04_stats/synthetic_cell_median_ci.csv"; man = R / "04_stats/synthetic_cell_median_ci.manifest.json"
rd = lambda p: pd.read_csv(p, keep_default_na=False, na_values=[""], low_memory=False)
syn = rd(inp); r1 = syn[(~syn.published_seed) & (syn.pipeline == "r1")]
keys = ["scenario", "cfg", "W", "s", "est", "binning", "variant", "rule"]
rows = []
for k, g in r1.groupby(keys, dropna=False):
    det = g.detected.astype(bool); n = len(g); kd = int(det.sum())
    dl = g.loc[det, "delay"].astype(float).to_numpy()
    fpa = pd.to_numeric(g.FPA_rate_pre, errors="coerce").to_numpy(float); fpa = fpa[np.isfinite(fpa)]
    lo, hi = wilson(kd, n)
    dlo, dhi = boot_ci_median(dl) if dl.size else (np.nan, np.nan)
    flo, fhi = boot_ci_median(fpa) if fpa.size else (np.nan, np.nan)
    rows.append(dict(zip(keys, k), n_seeds=n, n_detected=kd, det_rate=kd / n, det_rate_ci_lo=lo, det_rate_ci_hi=hi,
                     delay_median=np.median(dl) if dl.size else np.nan, delay_median_ci_lo=dlo, delay_median_ci_hi=dhi,
                     n_fpa=fpa.size, FPA_rate_pre_median=np.median(fpa) if fpa.size else np.nan,
                     FPA_rate_pre_median_ci_lo=flo, FPA_rate_pre_median_ci_hi=fhi))
o = pd.DataFrame(rows)
f = rd(frz); m = o.merge(f[keys + ["delay_median", "delay_median_ci_lo", "delay_median_ci_hi", "det_rate_ci_lo", "FPA_rate_pre_median"]],
                         on=keys, suffixes=("", "_frozen"), how="outer", indicator=True)
chk = {"cells_new": len(o), "cells_frozen": len(f), "unmatched": int((m._merge != "both").sum())}
for c in ["delay_median", "delay_median_ci_lo", "delay_median_ci_hi", "det_rate_ci_lo", "FPA_rate_pre_median"]:
    x, y = m[c].astype(float), m[c + "_frozen"].astype(float)
    bad = ~((np.isclose(x, y, rtol=0, atol=1e-9)) | (x.isna() & y.isna()))
    chk[f"mismatch_{c}"] = int(bad.sum())
o.to_csv(out, index=False)
man.write_text(json.dumps({"item": "I-15b", "script": "mr/derive_ci_synthetic.py", "script_sha256": sha(__file__),
    "input": {str(inp.relative_to(R.parent)): sha(inp), str(frz.relative_to(R.parent)): sha(frz)},
    "output": {str(out.relative_to(R.parent)): sha(out)}, "bootstrap": {"type": "percentile", "B": 2000, "seed": 0, "level": 0.95},
    "filter": "pipeline=='r1' & published_seed==False", "group_keys": keys, "consistency_check_vs_frozen": chk,
    "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}, indent=1))
print(json.dumps(chk))
