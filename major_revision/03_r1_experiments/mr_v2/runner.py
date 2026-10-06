"""Generic evaluation loop used by all R1 experiments (STEP 1, 2, 3, 5, 6)."""
from __future__ import annotations

import numpy as np
from eal_core import window_entropy, make_edges, threshold, metrics, EventSpec, EPS

ESTIMATORS = ("Shannon", "Sample", "Permutation")


def stat_fn(H, variant, H_base):
    H = np.asarray(H, float)
    if variant == "U_raw":
        return H.copy()
    if variant in ("S_norm", "B_norm", "B_fixed015"):
        d = (H - H_base) / max(EPS, abs(H_base)) if np.isfinite(H_base) else np.full_like(H, np.nan)
        return d if variant == "S_norm" else np.abs(d)
    if variant == "legacy_diff":
        st = np.abs(np.diff(H, prepend=np.nan))
        return np.where(np.isnan(st), 0.0, st)
    raise ValueError(variant)


def evaluate_cell(x_eval, t_eval, y_eval, ev: EventSpec, est, W, s, *, x_cal=None, cal_window_filter=None,
                  binning="per_window", variants=("U_raw", "B_norm"), rules=("mu_sigma",), k=3.0,
                  sampen_degenerate="nan", raw_cal_values=None, all_values=None, keep_series=False, exclude=None):
    """x_cal=None -> calibrate on windows of x_eval selected by cal_window_filter(t_start, t_end).
    Otherwise calibrate on every window of x_cal (synthetic stable scenario)."""
    edges = None
    if est == "Shannon":
        rcv = raw_cal_values if raw_cal_values is not None else (x_cal if x_cal is not None else None)
        edges = make_edges(binning, rcv, all_values=all_values)
    ends, H = window_entropy(x_eval, W, s, est, edges=edges, sampen_degenerate=sampen_degenerate)
    out_rows, series = [], {}
    if ends.size == 0:
        return [{"est": est, "W": W, "s": s, "binning": binning, "variant": v, "rule": r, "error": "no window fits series"}
                for v in variants for r in rules], series
    if x_cal is None:
        ts, te = t_eval[ends - W + 1], t_eval[ends]
        cmask = cal_window_filter(ts, te)
        H_cal_seq = H[cmask]
    else:
        _, H_cal_seq = window_entropy(x_cal, W, s, est, edges=edges, sampen_degenerate=sampen_degenerate)
        cmask = None
    fin = np.isfinite(H_cal_seq)
    H_base = float(np.mean(H_cal_seq[fin])) if fin.sum() else float("nan")
    clip_frac = float(np.mean((x_eval < edges[0]) | (x_eval > edges[-1]))) if edges is not None else 0.0
    nan_frac = float(np.mean(~np.isfinite(H)))
    for v in variants:
        st = stat_fn(H, v, H_base)
        if x_cal is None:
            st_cal = st[cmask]
        else:
            st_cal = stat_fn(H_cal_seq, v, H_base)
        for r in rules:
            if v == "B_fixed015":
                tau, info = 0.15, {"n_calib": int(np.isfinite(st_cal).sum())}
            else:
                tau, info = threshold(st_cal, r, k)
            fires = np.isfinite(st) & (st > tau)
            m = metrics(t_eval, ends, W, fires, st, ev, label_per_sample=y_eval, exclude=exclude)
            row = {"est": est, "W": W, "s": s, "binning": binning, "variant": v, "rule": r, "k": k,
                   "tau": tau, "H_base": H_base, "n_calib_windows": info["n_calib"], "calib_warning": info.get("warning", ""),
                   "n_windows": int(ends.size), "nan_frac_H": nan_frac, "clip_frac": clip_frac,
                   "n_bins": (len(edges) - 1) if edges is not None else 16}
            row.update(m)
            out_rows.append(row)
            if keep_series:
                series[(v, r)] = {"t_end": t_eval[ends], "stat": st, "tau": tau, "fires": fires}
    return out_rows, series
