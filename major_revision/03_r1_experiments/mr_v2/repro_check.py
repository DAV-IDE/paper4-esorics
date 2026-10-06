"""R1 reproduction check: the unified core must reproduce the PUBLISHED numbers
when run in 'legacy' mode, before any methodological change is evaluated.

  (a) synthetic, seed 42, upstream semantics -> results/synthetic/results_ready_summary.csv
  (b) proxy, seed 20260606, scripts/eal_factorial.py semantics -> results/eal/eal_factorial_summary.json
  (c) real minute, PR #3 semantics -> results/eal_real/eal_factorial_summary.json
Usage: python repro_check.py --repo /tmp/repo --out <dir>
"""
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
from eal_core import window_entropy, make_edges, auc_pair
from datasets import synthetic, proxy_per_second, real_minute, SYN_CONFIGS, SYN_EVENTS

EST = ["Shannon", "Sample", "Permutation"]


def legacy_synthetic(seed=42):
    d = synthetic(seed)
    allv = np.concatenate([d["stable"], d["drift_gradual"], d["shock"]])
    edges = make_edges("legacy_global", None, all_values=allv)
    rows = []
    for cid, (W, s) in SYN_CONFIGS.items():
        for est in EST:
            sig = {}
            for sc in ["stable", "drift_gradual", "shock"]:
                ends, H = window_entropy(d[sc], W, s, est, edges=edges if est == "Shannon" else None, sampen_degenerate="upstream")
                dh = np.abs(np.diff(H, prepend=np.nan))
                dh = np.where(np.isnan(dh), 0.0, dh)  # fillna(0); inf stays inf
                tc = d["t"][ends - W + 1 + W // 2]  # t_center = window_times[W//2]
                sig[sc] = (tc, dh)
            v = sig["stable"][1]
            tau = v.mean() + 3 * v.std()
            for sc in ["stable", "drift_gradual", "shock"]:
                tc, dh = sig[sc]
                if sc == "stable":
                    rows.append(dict(scenario=sc, cfg=cid, est=est, t_detect=np.nan, delay=np.nan, fp=int((dh > tau).sum()), peak=float(np.max(dh)), tau=tau))
                    continue
                te = SYN_EVENTS[sc][0]
                fp = int((dh[tc < te] > tau).sum())
                det = tc[(tc >= te) & (dh > tau)]
                rows.append(dict(scenario=sc, cfg=cid, est=est, t_detect=float(det[0]) if det.size else np.nan,
                                 delay=float(det[0] - te) if det.size else np.nan, fp=fp, peak=float(np.max(dh)), tau=tau))
    return pd.DataFrame(rows)


def legacy_proxy_like(per, W, s, est, warmup=600):
    x = per["pkt_rate"].to_numpy(); t = per["t"].to_numpy(); y = per["label"].to_numpy()
    ends, H = window_entropy(x, W, s, est, sampen_degenerate="zero")
    eps = np.full(len(x), np.nan); eps[ends] = H
    eps = pd.Series(eps).ffill().to_numpy()
    sv = eps[(t < warmup) & (y == 0)]; sv = sv[~np.isnan(sv)]
    if len(sv) < 5:
        mu = sig = np.nan; tau = math.inf
    else:
        mu, sig = float(sv.mean()), float(sv.std()); tau = mu + 3 * sig
    fires = (~np.isnan(eps)) & (eps > tau) & (t >= warmup)
    pw = t >= warmup; m = pw & ~np.isnan(eps)
    a, p = auc_pair(y[m], eps[m])
    fp = int(((y[m] == 0) & fires[m]).sum()); nneg = int((y[m] == 0).sum())
    at = t[pw & (y == 1)]
    ft = t[pw & fires]
    delay = np.nan; det = False
    if at.size:
        fa = ft[ft >= at.min()]
        if fa.size:
            det = True; delay = float(fa.min() - at.min())
    return dict(estimator=est, W=W, s=s, tau=tau, mu_stable=mu, sigma_stable=sig, AUC_ROC=a, AUC_PR=p,
                FPR_post_warmup=fp / nneg if nneg else np.nan, detected=det, detection_delay_s=delay, n_fires_post_warmup=int(fires[m].sum()))


def close(a, b, tol=1e-6):
    if isinstance(a, (bool, np.bool_)) or isinstance(b, bool):
        return bool(a) == bool(b)
    a = float(a) if a is not None else np.nan; b = float(b) if b is not None else np.nan
    if np.isnan(a) and np.isnan(b): return True
    if np.isinf(a) and np.isinf(b): return True
    return abs(a - b) <= tol * max(1, abs(b))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--repo", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--real", default=None)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True); repo = Path(a.repo)
    report = {}
    # (a) synthetic
    syn = legacy_synthetic(42); syn.to_csv(out / "repro_synthetic_seed42.csv", index=False)
    pub = pd.read_csv(repo / "results/synthetic/results_ready_summary.csv")
    smap = {"A (stable)": "stable", "B (gradual drift)": "drift_gradual", "C (shock)": "shock"}
    mism = []
    for _, r in pub.iterrows():
        sc = smap.get(r.scenario, r.scenario)
        q = syn[(syn.scenario == sc) & (syn.cfg == r.configuration_id) & (syn.est == r.entropy_metric)].iloc[0]
        pd_ = np.nan if str(r.detection_delay) == "N/A" else float(r.detection_delay)
        ok = close(q.delay, pd_) and int(q.fp) == int(r.pre_event_false_positives) and close(q.peak, float(r.peak_abs_delta_h), 1e-4)
        if not ok:
            mism.append(dict(scenario=sc, cfg=r.configuration_id, est=r.entropy_metric, pub_delay=pd_, rep_delay=q.delay, pub_fp=int(r.pre_event_false_positives), rep_fp=int(q.fp), pub_peak=float(r.peak_abs_delta_h), rep_peak=q.peak))
    report["synthetic_seed42"] = {"rows": len(pub), "mismatches": mism}
    # (b) proxy
    per = proxy_per_second(20260606)
    pubp = json.load(open(repo / "results/eal/eal_factorial_summary.json"))
    res = []; mm = []
    for m in pubp:
        r = legacy_proxy_like(per, m["W"], m["s"], m["estimator"]); res.append(r)
        for k in ["tau", "AUC_ROC", "AUC_PR", "FPR_post_warmup", "detected", "detection_delay_s", "n_fires_post_warmup"]:
            if not close(r[k], m[k], 1e-6):
                mm.append(dict(cell=f"{m['estimator']}/{m['W']}/{m['s']}", key=k, pub=m[k], rep=r[k]))
    json.dump(res, open(out / "repro_proxy_seed20260606.json", "w"), indent=1, default=float)
    report["proxy_seed20260606"] = {"cells": len(pubp), "mismatches": mm}
    # (c) real minute
    if a.real:
        rm = real_minute(a.real)
        pubr = json.load(open(repo / "results/eal_real/eal_factorial_summary.json"))
        res = []; mm = []
        for m in pubr:
            r = legacy_proxy_like(rm, m["W"], m["s"], m["estimator"]); res.append(r)
            for k in ["tau", "AUC_ROC", "AUC_PR", "detected", "n_fires_post_warmup"]:
                if not close(r[k], m[k], 1e-6):
                    mm.append(dict(cell=f"{m['estimator']}/{m['W']}/{m['s']}", key=k, pub=m[k], rep=r[k]))
        json.dump(res, open(out / "repro_real_minute_pr3.json", "w"), indent=1, default=float)
        report["real_minute_pr3"] = {"cells": len(pubr), "mismatches": mm, "n_minutes": len(rm), "attack_minutes": int(rm.label.sum())}
    json.dump(report, open(out / "repro_report.json", "w"), indent=1, default=float)
    print(json.dumps({k: {"n_mismatch": len(v["mismatches"])} for k, v in report.items()}))


if __name__ == "__main__":
    main()
