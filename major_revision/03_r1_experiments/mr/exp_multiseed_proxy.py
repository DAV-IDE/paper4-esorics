"""STEP 3 — 30 independent generator seeds of the CIC-IDS2017-aligned proxy
(scripts/generate_cic_proxy.py re-implemented with identical RNG call order,
see datasets.proxy_per_second; seed 20260606 is the published one).
Grid: original diagonal (64,8),(128,4),(256,1).  Same variants/rules/metrics as
the synthetic multi-seed (legacy_diff excluded: it is the upstream synthetic
statistic, never used on the proxy).  Per seed, pipeline `legacy_published`
reproduces scripts/eal_factorial.py exactly (Table 8 semantics)."""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
from multiprocessing import Pool
from eal_core import EventSpec
from runner import evaluate_cell
from datasets import proxy_per_second
from repro_check import legacy_proxy_like

GRID = [(64, 8), (128, 4), (256, 1)]
VARIANTS = ("U_raw", "S_norm", "B_norm", "B_fixed015")
RULES = ("mu_sigma", "q997", "mad")
BINNINGS = ("per_window", "global_stable", "fd")


def one_seed(seed):
    t0 = time.time()
    df = proxy_per_second(seed)
    x, t, y = df.pkt_rate.to_numpy(float), df.t.to_numpy(float), df.label.to_numpy(int)
    ev = EventSpec(t_event=float(t[y == 1].min()), t_attack_end=float(t[y == 1].max()), t_eval_start=600.0,
                   t_series_end=float(t.max()), dt=1.0)
    rows = []
    for est in ("Shannon", "Sample", "Permutation"):
        for (W, s) in GRID:
            r = legacy_proxy_like(df, W, s, est); r.update(seed=seed, pipeline="legacy_published", est=est, binning="per_window")
            rows.append(r)
    for est in ("Shannon", "Sample", "Permutation"):
        for (W, s) in GRID:
            for b in (BINNINGS if est == "Shannon" else ("none",)):
                res, _ = evaluate_cell(x, t, y, ev, est, W, s, cal_window_filter=lambda ts, te: te < 600,
                                       binning=b if est == "Shannon" else "per_window", variants=VARIANTS, rules=RULES,
                                       raw_cal_values=x[(t < 600) & (y == 0)])
                for r in res:
                    r.pop("fire_times", None); r.update(seed=seed, binning=b, pipeline="r1")
                    rows.append(r)
    return seed, rows, time.time() - t0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--procs", type=int, default=2)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    seeds = [int(v) for v in np.random.SeedSequence(20261004).generate_state(a.n)] + [20260606]
    man = {"command": " ".join(sys.argv), "seed_sequence_entropy": 20261004, "seeds": seeds[:-1], "published_seed": 20260606,
           "grid": GRID, "variants": VARIANTS, "rules": RULES, "binnings": BINNINGS, "calibration": "windows with t_end<600 s",
           "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rows = []
    with Pool(a.procs) as p:
        for seed, r, dt in p.imap_unordered(one_seed, seeds):
            rows.extend(r); print(f"[proxy-ms] seed {seed} {dt:.1f}s", flush=True)
    d = pd.DataFrame(rows); d["published_seed"] = d.seed == 20260606
    d.to_csv(out / "proxy_multiseed_long.csv.gz", index=False)
    man["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()); man["n_rows"] = len(d)
    (out / "proxy_multiseed_manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
