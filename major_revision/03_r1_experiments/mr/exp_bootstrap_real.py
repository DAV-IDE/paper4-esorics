"""STEP 3 (real data) — ROBUSTNESS ANALYSIS, NOT PRIMARY EVIDENCE.

Data: analysis A (minute aggregation of the CIC-IDS2017 TrafficLabelling file,
HF mirror bvsam/cic-ids-2017, PR #3).  There is no generative seed for real
data, so "30 real seeds" do not exist; instead we quantify the sensitivity of
the gate to the *calibration sample* only:

  (i)  moving-block bootstrap (MBB) of the 26 benign pre-attack minutes,
       block length L in {3,4,6} min (L=4 primary, ~n^(1/3)+1), B=1000 (AUC not recomputed per replicate: it does not depend on tau);
       each replicate yields a surrogate calibration series, from which
       H_base, tau (and Shannon fixed edges) are re-estimated; the gate is
       then applied to the OBSERVED attack + post-attack windows;
       surrogate length = 26 (native) and 64 (extended surrogate, labelled);
  (ii) documented calibration sub-windows: last 26 / 20 / 15 benign minutes
       before t_event (deterministic).
The evaluation stream itself is never resampled (the attack is a single event).
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
from eal_core import window_entropy, make_edges, threshold, metrics, EventSpec
from runner import stat_fn
from datasets import real_minute

GRID = [(8, 4), (16, 2), (32, 1)]
VARIANTS = ("U_raw", "S_norm", "B_norm", "B_fixed015")
RULES = ("mu_sigma", "q997", "mad")


def mbb(x, L, n_out, rng):
    starts = rng.integers(0, len(x) - L + 1, size=int(np.ceil(n_out / L)))
    return np.concatenate([x[s:s + L] for s in starts])[:n_out]


def eval_with_calibration(x, t, y, ev, est, W, s, x_cal, binning, auc=True):
    edges = make_edges(binning, x_cal) if est == "Shannon" else None
    ends, H = window_entropy(x, W, s, est, edges=edges)
    _, Hc = window_entropy(x_cal, W, s, est, edges=edges)
    fin = np.isfinite(Hc)
    Hb = float(Hc[fin].mean()) if fin.sum() else float("nan")
    out = []
    for v in VARIANTS:
        st = stat_fn(H, v, Hb); stc = stat_fn(Hc, v, Hb)
        for r in RULES:
            if v == "B_fixed015":
                tau, info = (0.15, {"n_calib": int(np.isfinite(stc).sum())}) if np.isfinite(Hb) else (float("inf"), {"n_calib": 0})
            else:
                tau, info = threshold(stc, r)
            fires = np.isfinite(st) & (st > tau)
            m = metrics(t, ends, W, fires, st, ev, label_per_sample=y if auc else None, compute_auc=auc)
            m.pop("fire_times", None)
            out.append(dict(est=est, W=W, s=s, binning=binning, variant=v, rule=r, tau=tau, H_base=Hb, n_calib_windows=info["n_calib"], **m))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--input", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--B", type=int, default=1000); ap.add_argument("--seed", type=int, default=20261005)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    df = real_minute(a.input)
    x, t, y = df.pkt_rate.to_numpy(float), df.t.to_numpy(float), df.label.to_numpy(int)
    i_ev = int(np.argmax(y == 1)); t_ev, t_ae = float(t[y == 1].min()), float(t[y == 1].max())
    ev = EventSpec(t_event=t_ev, t_attack_end=t_ae, t_eval_start=t_ev, t_series_end=float(t.max()), dt=60.0)
    pre = x[:i_ev]
    rows = []
    # (ii) deterministic calibration sub-windows
    for span in (26, 20, 15):
        xc = pre[-span:]
        for est in ("Shannon", "Sample", "Permutation"):
            for W, s in GRID:
                for b in (("per_window", "global_stable", "fd") if est == "Shannon" else ("per_window",)):
                    for r in eval_with_calibration(x, t, y, ev, est, W, s, xc, b):
                        r.update(scheme=f"subwindow_last{span}", rep=-1); rows.append(r)
    pd.DataFrame(rows).to_csv(out / "real_minute_calib_subwindows.csv", index=False)
    # (i) MBB
    rng = np.random.default_rng(a.seed)
    brows = []
    t0 = time.time()
    for L in (3, 4, 6):
        for n_out in (26, 64):
            for rep in range(a.B):
                xc = mbb(pre, L, n_out, rng)
                for est in ("Shannon", "Sample", "Permutation"):
                    for W, s in GRID:
                        if n_out < W:  # cannot hold one window: tau undefined -> recorded
                            brows.append(dict(scheme=f"MBB_L{L}_n{n_out}", rep=rep, est=est, W=W, s=s, binning="per_window", variant="ALL",
                                              rule="ALL", tau=float("inf"), n_calib_windows=0, detected=False, note="surrogate shorter than W"))
                            continue
                        for r in eval_with_calibration(x, t, y, ev, est, W, s, xc, "per_window", auc=False):
                            r.update(scheme=f"MBB_L{L}_n{n_out}", rep=rep); brows.append(r)
            print(f"[mbb] L={L} n={n_out} done ({time.time()-t0:.0f}s)", flush=True)
    bd = pd.DataFrame(brows)
    bd.to_csv(out / "real_minute_mbb_long.csv.gz", index=False)
    man = {"command": " ".join(sys.argv), "status": "ROBUSTNESS ANALYSIS - NOT PRIMARY EVIDENCE", "rng_seed": a.seed, "B": a.B,
           "block_lengths": [3, 4, 6], "surrogate_lengths": [26, 64], "pre_attack_benign_minutes": int(i_ev),
           "t_event_s": t_ev, "t_attack_end_s": t_ae, "grid": GRID, "variants": VARIANTS, "rules": RULES,
           "note": "evaluation stream never resampled; only calibration sample is bootstrapped"}
    (out / "real_minute_bootstrap_manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
