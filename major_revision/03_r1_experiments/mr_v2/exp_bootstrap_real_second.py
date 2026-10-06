"""STEP 3 on real per-second data (analysis C) — calibration-sample uncertainty.

No generative seed exists for real traffic.  As for analysis A, only the
calibration sample is resampled: moving-block bootstrap (MBB) of the benign
calibration segment (block length L s, B replicates, documented seed).  The
observed evaluation stream is never resampled; its window entropies are
computed once (they do not depend on the calibration, except Shannon
global_stable whose bin edges are re-estimated per replicate).
Calibration scheme (primary, causal): morning_clean_causal = benign seconds
before the first other attack (Botnet 10:02 ADT); evaluation from that point on,
with Botnet/PortScan seconds excluded from FP counts (fires_excluded reported).  Grid: W={64,128,256} x s={1,4,8}.
Variants U_raw, B_norm; rules mu_sigma, q997.
"""
import argparse, json, sys, time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
import pandas as pd
from eal_core import EventSpec, window_entropy, make_edges, threshold, metrics
from runner import stat_fn
from exp_bootstrap_real import mbb

GRID = [(W, s) for W in (64, 128, 256) for s in (1, 4, 8)]
CELLS = [(e, W, s, b) for e in ("Shannon", "Sample", "Permutation") for (W, s) in GRID
         for b in (("per_window", "global_stable") if e == "Shannon" else ("per_window",))]
G = {}


def init(x, t, y, ev_by_scheme, H_obs, other):
    G.update(x=x, t=t, y=y, ev=ev_by_scheme, H=H_obs, other=other)


def job(args):
    sname, xc_obs, L, B, seed = args
    rng = np.random.default_rng(seed); out = []
    x, t, y, ev = G["x"], G["t"], G["y"], G["ev"][sname]
    for rep in range(B):
        xc = mbb(xc_obs, L, len(xc_obs), rng)
        for est, W, s, b in CELLS:
            if b == "global_stable":
                edges = make_edges("global_stable", xc)
                ends, H = window_entropy(x, W, s, est, edges=edges)
            else:
                edges = None; ends, H = G["H"][(est, W, s)]
            _, Hc = window_entropy(xc, W, s, est, edges=edges)
            fin = np.isfinite(Hc); Hb = float(Hc[fin].mean()) if fin.sum() else float("nan")
            for v in ("U_raw", "B_norm"):
                st = stat_fn(H, v, Hb); stc = stat_fn(Hc, v, Hb)
                for r in ("mu_sigma", "q997"):
                    tau, info = threshold(stc, r)
                    fires = np.isfinite(st) & (st > tau)
                    m = metrics(t, ends, W, fires, st, ev, compute_auc=False, exclude=G["other"]); m.pop("fire_times", None)
                    out.append(dict(scheme=f"{sname}_MBB_L{L}", rep=rep, est=est, W=W, s=s, binning=b, variant=v, rule=r,
                                    tau=tau, H_base=Hb, n_calib_windows=info["n_calib"], **m))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--input", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--start-epoch", type=int, default=None); ap.add_argument("--end-epoch", type=int, default=None)
    ap.add_argument("--B", type=int, default=200); ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--blocks", nargs="+", type=int, default=[60, 120]); ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(a.input)
    if a.start_epoch is not None:
        df = df[(df.epoch_s >= a.start_epoch) & (df.epoch_s <= a.end_epoch)]
    df = df.reset_index(drop=True); df["t"] = (df.epoch_s - df.epoch_s.iloc[0]).astype(float)
    x, t, y = df.pkt_rate.to_numpy(float), df.t.to_numpy(float), df.label_ddos.to_numpy(int)
    other = ((df.label_botnet == 1) | (df.label_portscan == 1)).to_numpy()
    t_ev, t_ae = float(t[y == 1].min()), float(t[y == 1].max())
    i_o = int(np.argmax(other))
    schemes = {"morning_clean_causal": (float(t[i_o]), x[:i_o])}
    evs = {k: EventSpec(t_event=t_ev, t_attack_end=t_ae, t_eval_start=v[0], t_series_end=float(t.max()), dt=1.0) for k, v in schemes.items()}
    t0 = time.time()
    H_obs = {(e, W, s): window_entropy(x, W, s, e) for e in ("Shannon", "Sample", "Permutation") for (W, s) in GRID}
    print(f"[mbb-s] observed entropies cached ({time.time()-t0:.0f}s)", flush=True)
    ss = np.random.SeedSequence(a.seed)
    jobs = []
    children = ss.spawn(len(schemes) * len(a.blocks)); i = 0
    for sname, (_, xc) in schemes.items():
        for L in a.blocks:
            jobs.append((sname, xc, L, a.B, children[i])); i += 1
    rows = []
    with Pool(a.procs, initializer=init, initargs=(x, t, y, evs, H_obs, other)) as p:
        for r in p.imap_unordered(job, jobs):
            rows.extend(r); print(f"[mbb-s] {r[0]['scheme']} done ({time.time()-t0:.0f}s)", flush=True)
    pd.DataFrame(rows).to_csv(out / "real_second_mbb_long.csv.gz", index=False)
    (out / "real_second_bootstrap_manifest.json").write_text(json.dumps({
        "command": " ".join(sys.argv), "status": "calibration-uncertainty analysis on primary real data (C)",
        "rng_seed": a.seed, "B": a.B, "blocks_s": a.blocks, "t_event_s": t_ev, "t_attack_end_s": t_ae,
        "n_seconds": len(df), "variants": ["U_raw", "B_norm"], "rules": ["mu_sigma", "q997"], "grid": GRID,
        "note": "evaluation stream never resampled; only calibration sample is bootstrapped"}, indent=1))


if __name__ == "__main__":
    main()
