"""STEP 3 — 30 independent seeds per synthetic cell.

Seeds: numpy SeedSequence(20261003).generate_state(30) (uint32), recorded in the
manifest.  Seed 42 (published) is run as well and flagged `published_seed`.
For every seed:
  * pipeline 'legacy_published' : upstream semantics (first-difference |dH|,
    t_center timestamps, global range over all scenarios, in-sample tau on the
    stable scenario) -> reproduces Table 4 of the submission for seed 42;
  * pipeline 'r1' : trailing-edge (causal) timestamps, tau calibrated on the
    stable scenario, gating variants x threshold rules x Shannon binnings,
    out-of-sample FP measured on pre-event segments and on an independent
    stable_holdout series.
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
from multiprocessing import Pool
from eal_core import EventSpec, window_entropy
from runner import evaluate_cell
from datasets import synthetic, SYN_CONFIGS, SYN_EVENTS, N_SYN
from repro_check import legacy_synthetic

VARIANTS = ("U_raw", "S_norm", "B_norm", "legacy_diff")
RULES = ("mu_sigma", "q997", "mad")
BINNINGS = ("per_window", "global_stable", "fd", "legacy_global")


def one_seed(seed):
    t0 = time.time()
    d = synthetic(seed)
    rows = []
    leg = legacy_synthetic(seed)
    for r in leg.to_dict("records"):
        r.update(seed=seed, pipeline="legacy_published")
        rows.append(r)
    allv = np.concatenate([d["stable"], d["drift_gradual"], d["shock"]])
    tt = d["t"]
    stable_vals = {}
    for sc in ("drift_gradual", "shock", "stable_holdout"):
        if sc == "stable_holdout":
            ev = EventSpec(t_event=1e12, t_attack_end=1e12, t_eval_start=0, t_series_end=N_SYN - 1, dt=1, time_unit="sample")
            y = np.zeros(N_SYN, int)
        else:
            te, ta = SYN_EVENTS[sc]
            ev = EventSpec(t_event=te, t_attack_end=ta, t_eval_start=0, t_series_end=N_SYN - 1, dt=1, time_unit="sample")
            y = ((tt >= te) & (tt <= ta)).astype(int)
        for cid, (W, s) in SYN_CONFIGS.items():
            for est in ("Shannon", "Sample", "Permutation"):
                for b in (BINNINGS if est == "Shannon" else ("none",)):
                    res, ser = evaluate_cell(d[sc], tt, y, ev, est, W, s, x_cal=d["stable"],
                                             binning=b if est == "Shannon" else "per_window",
                                             variants=VARIANTS, rules=RULES, raw_cal_values=d["stable"], all_values=allv)
                    for r in res:
                        r.pop("fire_times", None)
                        r.update(seed=seed, pipeline="r1", scenario=sc, cfg=cid, binning=b)
                        rows.append(r)
    # stable-phase calibration statistics (for distribution diagnostics)
    for cid, (W, s) in SYN_CONFIGS.items():
        for est in ("Shannon", "Sample", "Permutation"):
            edges = None
            if est == "Shannon":
                from eal_core import make_edges
                edges = None  # per-window binning (current paper code) for the diagnostics
            _, H = window_entropy(d["stable"], W, s, est, edges=edges, sampen_degenerate="nan")
            stable_vals[f"{cid}|{est}"] = H.tolist()
    return seed, rows, stable_vals, time.time() - t0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    seeds = [int(v) for v in np.random.SeedSequence(20261003).generate_state(a.n)]
    allseeds = seeds + [42]
    manifest = {"command": " ".join(sys.argv), "seed_sequence_entropy": 20261003, "seeds": seeds, "published_seed": 42,
                "variants": VARIANTS, "rules": RULES, "binnings": BINNINGS, "configs": SYN_CONFIGS, "events": SYN_EVENTS,
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rows, stab = [], {}
    with Pool(a.procs) as p:
        for seed, r, sv, dt in p.imap_unordered(one_seed, allseeds):
            rows.extend(r); stab[str(seed)] = sv
            print(f"[synth] seed {seed} done in {dt:.1f}s", flush=True)
    df = pd.DataFrame(rows)
    df["published_seed"] = df["seed"] == 42
    df.to_csv(out / "synthetic_multiseed_long.csv.gz", index=False)
    json.dump(stab, open(out / "synthetic_stable_window_entropy.json", "w"))
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); manifest["n_rows"] = len(df)
    (out / "synthetic_multiseed_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))


if __name__ == "__main__":
    main()
