"""I-16 (R1-5): detection delay in number of windows. Post-processing only, no experiment re-run.
Definition (causal grid of Algorithm 1, window k ends at sample e_k = W-1+k*s, decision at t[e_k]):
  d_win = #{k : t_event <= t_end_k <= t_detect}
        = number of window decisions taken from attack onset up to and including the first detecting one (d_win >= 1).
All series used here have uniform time steps starting at t=0 (synthetic dt=1 sample, per-second dt=1 s,
minute dt=60 s), so t_end_k = (W-1+k*s)*dt. Each t_detect is checked to lie on that grid.
The proxy drops seconds without flows (datasets.proxy_per_second), so its time axis is NOT uniform for every seed:
for the proxy the exact time axis of each seed is regenerated with the frozen generator and d_win is counted
directly on t[e_k] (time axis only; no entropy, gate or metric is recomputed).
"""
import argparse, hashlib, json, sys, platform, math
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from analysis_stats import boot_ci_median

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
ap = argparse.ArgumentParser(); ap.add_argument("--res", required=True); a = ap.parse_args()
R = Path(a.res); O = R / "04_stats"
rd = lambda p: pd.read_csv(p, keep_default_na=False, na_values=[""], low_memory=False)

def add_dwin(df, dt):
    df = df.copy(); W = df.W.astype(float); s = df.s.astype(float)
    det = df.detected.astype(str).str.lower().eq("true")
    kd = (df.t_detect.astype(float) / dt - (W - 1)) / s
    kf = np.maximum(0, np.ceil((df.t_event.astype(float) / dt - (W - 1)) / s - 1e-9))
    on_grid = np.isclose(kd, np.round(kd)) | ~det
    dwin = np.where(det, np.round(kd) - kf + 1, np.nan)
    df["delay_windows"] = dwin
    chk = {"rows": int(len(df)), "detected": int(det.sum()), "off_grid": int((~on_grid).sum()),
           "dwin_lt1": int((dwin[det] < 1).sum()), "dwin_min": float(np.nanmin(dwin)) if det.any() else None,
           "dwin_max": float(np.nanmax(dwin)) if det.any() else None}
    return df, chk

def summarize(df, keys):
    rows = []
    for k, g in df.groupby(keys, dropna=False):
        v = g.delay_windows.dropna().to_numpy(float); n = len(g)
        o = dict(zip(keys, k), n_runs=n, n_detected=int(v.size))
        if v.size:
            q1, q3 = np.percentile(v, [25, 75]); lo, hi = boot_ci_median(v)
            o.update(delay_windows_median=float(np.median(v)), delay_windows_q1=q1, delay_windows_q3=q3,
                     delay_windows_median_ci_lo=lo, delay_windows_median_ci_hi=hi,
                     delay_median=float(g.delay.dropna().median()))
        rows.append(o)
    return pd.DataFrame(rows)

man = {"item": "I-16", "script": "mr/derive_delay_windows.py", "script_sha256": sha(__file__), "definition": __doc__.strip(),
       "bootstrap_for_median_ci": {"type": "percentile", "B": 2000, "seed": 0}, "inputs": {}, "outputs": {}, "checks": {},
       "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
def reg_in(p): man["inputs"][str(p.relative_to(R.parent))] = sha(p)
def reg_out(p): man["outputs"][str(p.relative_to(R.parent))] = sha(p)

# synthetic (r1 pipeline, 30 independent seeds)
p = R / "03_synthetic_multiseed/synthetic_multiseed_long.csv.gz"; reg_in(p)
syn = rd(p); syn = syn[(~syn.published_seed) & (syn.pipeline == "r1") & syn.scenario.isin(["drift_gradual", "shock"])]
syn, man["checks"]["synthetic"] = add_dwin(syn, 1.0)
keys = ["scenario", "cfg", "W", "s", "est", "binning", "variant", "rule"]
out = O / "delay_windows_synthetic_runs.csv.gz"; syn[keys + ["seed", "detected", "t_event", "t_detect", "delay", "delay_windows"]].to_csv(out, index=False); reg_out(out)
out = O / "delay_windows_synthetic_cells.csv"; summarize(syn, keys).to_csv(out, index=False); reg_out(out)

# proxy (stress test, 30 seeds): exact count on the regenerated time axis of each seed
import datasets
p = R / "03_proxy_multiseed/proxy_multiseed_long.csv.gz"; reg_in(p)
px = rd(p); px = px[(~px.published_seed) & (px.pipeline == "r1")].copy()
tax = {}; gaps = {}
for sd in sorted(px.seed.unique()):
    t = datasets.proxy_per_second(int(sd)).t.to_numpy(float); tax[sd] = t; gaps[int(sd)] = int(14400 - t.size)
dw = []; off = 0
for r in px.itertuples():
    if str(r.detected).lower() != "true": dw.append(np.nan); continue
    t = tax[r.seed]; W, s_ = int(r.W), int(r.s); te = t[np.arange(W - 1, t.size, s_)]
    if not np.any(np.isclose(te, float(r.t_detect))): off += 1
    dw.append(float(((te >= float(r.t_event)) & (te <= float(r.t_detect))).sum()))
px["delay_windows"] = dw; v = px.delay_windows.dropna()
man["checks"]["proxy"] = {"rows": int(len(px)), "detected": int(v.size), "off_grid": off, "dwin_lt1": int((v < 1).sum()),
                          "dwin_min": float(v.min()), "dwin_max": float(v.max()), "seeds_with_dropped_seconds": {k: g for k, g in gaps.items() if g}}
out = O / "delay_windows_proxy_cells.csv"; summarize(px, ["W", "s", "est", "binning", "variant", "rule"]).to_csv(out, index=False); reg_out(out)

# real per-second (official capture), one run per configuration and calibration
frames = []
for f in sorted((R / "01_real_second_v2").glob("real_second_*_cells.csv")):
    reg_in(f); d = rd(f); d["source_file"] = f.name; frames.append(d)
rs = pd.concat(frames, ignore_index=True); rs, man["checks"]["real_second"] = add_dwin(rs, 1.0)
cols = ["source_file", "calibration", "est", "W", "s", "binning", "variant", "rule", "detected", "t_event", "t_detect", "delay", "delay_windows"]
out = O / "delay_windows_real_second.csv"; rs[cols].to_csv(out, index=False); reg_out(out)

# real minute (robustness, flow CSV mirror)
p = R / "01_real_minute/real_minute_cells.csv"; reg_in(p)
rm = rd(p); rm, man["checks"]["real_minute"] = add_dwin(rm, 60.0)
out = O / "delay_windows_real_minute.csv"; rm[cols[1:]].to_csv(out, index=False); reg_out(out)

mp = O / "delay_windows.manifest.json"; mp.write_text(json.dumps(man, indent=1))
print(json.dumps(man["checks"]))
