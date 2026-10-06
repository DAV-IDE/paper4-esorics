"""Unified, documented EAL core for the Paper 4 Major Revision (R1).

Every methodological choice is an explicit parameter so that the legacy
pipelines (upstream synthetic pipeline LoreBerto03/psi-risk-dt-pipeline@57fc6d1
and scripts/eal_factorial.py of the Paper 4 repo) can be reproduced *and*
compared against the corrected pipeline on identical inputs.

Conventions (see major_revision/docs/METRICS_DEFINITIONS.md):
  * A window k covers samples [e_k-W+1, e_k]; its decision time is the
    trailing edge t_end = t[e_k] (causal).  The legacy synthetic pipeline
    timestamps windows at t_center (non-causal, look-ahead W/2).
  * Window label = 1 iff the window overlaps the attack interval.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

EPS = 1e-9


# --------------------------------------------------------------------------
# Estimators
# --------------------------------------------------------------------------
def shannon_hist(x, bins=16, edges=None):
    """Shannon entropy in bits.  edges=None -> per-window range (numpy default).
    With fixed edges, values are clipped into the first/last bin (overflow)."""
    x = np.asarray(x, float)
    if x.size < 2:
        return 0.0
    if edges is None:
        if np.isclose(x.min(), x.max()):
            return 0.0
        c, _ = np.histogram(x, bins=bins)
    else:
        xc = np.clip(x, edges[0], edges[-1])
        c, _ = np.histogram(xc, bins=edges)
    tot = c.sum()
    if tot == 0:
        return 0.0
    p = c[c > 0] / tot
    return float(-(p * np.log2(p)).sum())


def sampen_fast(x, m=2, r_ratio=0.2, degenerate="nan"):
    """SampEn with the template convention shared by both legacy codes
    (N-m+1 templates of length m, N-m of length m+1, pairs i<j, Chebyshev).
    degenerate: 'nan' (new), 'zero' (repo eal_factorial.py),
    'upstream' (std=0 ->0, B=0 -> nan, A=0 -> -log(1/(B+1)))."""
    x = np.asarray(x, float)
    n = x.size
    if n < m + 2:
        return 0.0 if degenerate == "zero" else float("nan")
    sd = x.std()
    if sd < 1e-9:
        return 0.0 if degenerate in ("zero", "upstream") else float("nan")
    r = r_ratio * sd
    A0 = np.abs(x[:, None] - x[None, :])
    D = A0[: n - m + 1, : n - m + 1].copy()
    for k in range(1, m):
        D = np.maximum(D, A0[k : n - m + 1 + k, k : n - m + 1 + k])
    iu = np.triu_indices(n - m + 1, k=1)
    B = int((D[iu] <= r).sum())
    D1 = np.maximum(D[: n - m, : n - m], A0[m:n, m:n])
    iu1 = np.triu_indices(n - m, k=1)
    A = int((D1[iu1] <= r).sum())
    if B == 0 or A == 0:
        if degenerate == "zero":
            return 0.0
        if degenerate == "upstream":  # continuity_correction=1.0 (upstream default)
            return float("nan") if B == 0 else float(-math.log(1.0 / (B + 1.0)))
        return float("nan")
    return float(-math.log(A / B))


def _perm_codes(x, order=3, delay=1):
    x = np.asarray(x, float)
    L = 1 + (order - 1) * delay
    if x.size < L:
        return np.empty(0, int)
    sw = np.lib.stride_tricks.sliding_window_view(x, L)[:, ::delay]
    ranks = np.argsort(sw, axis=1, kind="mergesort")
    base = order ** np.arange(order)[::-1]
    return ranks @ base


def permutation_entropy(x, order=3, delay=1):
    codes = _perm_codes(x, order, delay)
    if codes.size == 0:
        return float("nan")
    _, c = np.unique(codes, return_counts=True)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum() / math.log2(math.factorial(order)))


# --------------------------------------------------------------------------
# Binning for Shannon (STEP 6)
# --------------------------------------------------------------------------
def make_edges(mode, calib_values, bins=16, all_values=None):
    """Return fixed bin edges or None (per-window range).
    per_window     : None (current Paper 4 code)
    global_stable  : 16 equal bins on [min,max] of calibration samples, clipping
    fd             : Freedman-Diaconis width from calibration samples, clipping
    legacy_global  : range over ALL scenarios incl. attacks (upstream synthetic;
                     look-ahead leakage, kept only for reproduction)"""
    if mode == "per_window":
        return None
    if mode == "legacy_global":
        lo, hi = float(np.min(all_values)), float(np.max(all_values))
        if np.isclose(lo, hi):
            hi = lo + 1e-9
        return np.linspace(lo, hi, bins + 1)
    cv = np.asarray(calib_values, float)
    lo, hi = float(cv.min()), float(cv.max())
    if np.isclose(lo, hi):
        hi = lo + 1e-9
    if mode == "global_stable":
        return np.linspace(lo, hi, bins + 1)
    if mode == "fd":
        q75, q25 = np.percentile(cv, [75, 25])
        h = 2 * (q75 - q25) * cv.size ** (-1 / 3)
        if h <= 0:
            return np.linspace(lo, hi, bins + 1)
        nb = int(min(max(math.ceil((hi - lo) / h), 2), 512))
        return np.linspace(lo, hi, nb + 1)
    raise ValueError(mode)


# --------------------------------------------------------------------------
# Windowing
# --------------------------------------------------------------------------
def window_entropy(x, W, s, est, edges=None, sampen_degenerate="nan", bins=16):
    """Trailing windows ending at e_k = W-1, W-1+s, ...  Returns (ends, H)."""
    x = np.asarray(x, float)
    n = x.size
    ends = np.arange(W - 1, n, s)
    if ends.size == 0:
        return ends, np.empty(0)
    if est == "Shannon":
        H = np.array([shannon_hist(x[e - W + 1 : e + 1], bins, edges) for e in ends])
    elif est == "Sample":
        H = np.array([sampen_fast(x[e - W + 1 : e + 1], degenerate=sampen_degenerate) for e in ends])
    elif est == "Permutation":
        codes = _perm_codes(x)  # pattern j covers samples j..j+2
        H = np.empty(ends.size)
        for i, e in enumerate(ends):
            c = codes[e - W + 1 : e - 1]  # patterns fully inside window
            _, cnt = np.unique(c, return_counts=True)
            p = cnt / cnt.sum()
            H[i] = float(-(p * np.log2(p)).sum() / math.log2(6))
    else:
        raise ValueError(est)
    return ends, H


# --------------------------------------------------------------------------
# Thresholds and gating (STEP 2 / STEP 3)
# --------------------------------------------------------------------------
def threshold(vals, rule="mu_sigma", k=3.0):
    v = np.asarray(vals, float)
    v = v[np.isfinite(v)]
    if v.size < 5:
        return float("inf"), {"n_calib": int(v.size), "warning": "calibration<5 -> tau=inf"}
    if rule == "mu_sigma":
        t = v.mean() + k * v.std()
    elif rule == "q997":
        t = float(np.quantile(v, 0.997))
    elif rule == "mad":
        med = np.median(v)
        t = med + k * 1.4826 * np.median(np.abs(v - med))
    else:
        raise ValueError(rule)
    return float(t), {"n_calib": int(v.size)}


GATING_VARIANTS = ("U_raw", "S_norm", "B_norm", "B_fixed015", "legacy_diff")


def gate_statistic(H, calib_mask, variant, H_base=None):
    """Return (stat, stat_calib, H_base).
    U_raw      : stat = H_t                        (scripts/eal_factorial.py)
    S_norm     : stat = DeltaH_t, Eq.(1), signed   (Eq.(2) literal, one-sided)
    B_norm     : stat = |DeltaH_t|, Eq.(1)         (Sec.4.4 / Q1 / user STEP 2)
    B_fixed015 : stat = |DeltaH_t|, tau_s = 0.15   (hyper-parameter of [7])
    legacy_diff: stat = |H_k - H_{k-1}|            (upstream synthetic pipeline)"""
    H = np.asarray(H, float)
    cal = H[calib_mask & np.isfinite(H)]
    if H_base is None:
        H_base = float(np.mean(cal)) if cal.size else float("nan")
    if variant == "U_raw":
        st = H.copy()
    elif variant in ("S_norm", "B_norm", "B_fixed015"):
        d = (H - H_base) / max(EPS, abs(H_base)) if np.isfinite(H_base) else np.full_like(H, np.nan)
        st = d if variant == "S_norm" else np.abs(d)
    elif variant == "legacy_diff":
        st = np.abs(np.diff(H, prepend=np.nan))
        st = np.where(np.isfinite(st), st, 0.0)  # upstream fillna(0)
    else:
        raise ValueError(variant)
    return st, st[calib_mask], H_base


def apply_gate(stat, stat_calib, variant, rule="mu_sigma", k=3.0):
    if variant == "B_fixed015":
        return np.isfinite(stat) & (stat > 0.15), 0.15, {"n_calib": int(np.isfinite(stat_calib).sum())}
    tau, info = threshold(stat_calib, rule, k)
    return np.isfinite(stat) & (stat > tau), tau, info


# --------------------------------------------------------------------------
# Metrics (STEP 5)
# --------------------------------------------------------------------------
def auc_pair(y, score):
    from sklearn.metrics import roc_auc_score, average_precision_score
    y = np.asarray(y)
    sc = np.asarray(score, float)
    m = np.isfinite(sc)
    y, sc = y[m], np.round(sc[m], 12)  # tie-robust: PE/Shannon take few distinct values
    if y.size == 0 or len(set(y.tolist())) < 2:
        return float("nan"), float("nan")
    return float(roc_auc_score(y, sc)), float(average_precision_score(y, sc))


@dataclass
class EventSpec:
    t_event: float           # first attack sample time
    t_attack_end: float      # last attack sample time (inclusive)
    t_eval_start: float      # first time that may raise an alarm (end of warm-up)
    t_series_end: float      # last sample time
    dt: float                # sampling period (s, or 1 sample)
    time_unit: str = "s"


def metrics(t, ends, W, fires, stat, ev: EventSpec, label_per_sample=None, legacy_t=None, compute_auc=True, exclude=None):
    """All STEP 5 metrics.  t: per-sample times; ends: window end indices.
    exclude: optional per-sample bool mask (e.g. OTHER attacks in the same capture);
    windows overlapping it are removed from pre/post negatives and FP denominators,
    their fires are reported separately (fires_excluded); excluded samples are
    removed from per-sample AUC/FPR and from benign duration."""
    t = np.asarray(t, float)
    t_end = t[ends]
    t_start = t[ends - W + 1]
    ev_mask = t_end >= ev.t_eval_start
    overlap = (t_end >= ev.t_event) & (t_start <= ev.t_attack_end)
    pre = ev_mask & (t_end < ev.t_event)
    post = ev_mask & (t_start > ev.t_attack_end)
    if exclude is not None:
        exc = np.asarray(exclude, bool)
        cs = np.concatenate([[0], np.cumsum(exc)])
        excl_w = (cs[ends + 1] - cs[ends - W + 1]) > 0
        excl_w &= ~overlap
        pre &= ~excl_w; post &= ~excl_w
    else:
        exc = None; excl_w = np.zeros(ends.size, bool)
    att = ev_mask & overlap
    f = fires & ev_mask
    n_pre, n_att, n_post = int(f[pre].sum()), int(f[att].sum()), int(f[post].sum())
    fire_times_att = t_end[f & att]
    detected = fire_times_att.size > 0
    t_detect = float(fire_times_att.min()) if detected else float("nan")
    delay = t_detect - ev.t_event if detected else float("nan")
    neg = pre | post
    pre_dur = max(0.0, min(ev.t_event, ev.t_series_end + ev.dt) - ev.t_eval_start)
    post_dur = max(0.0, ev.t_series_end - ev.t_attack_end) if ev.t_attack_end < ev.t_series_end else 0.0
    if exc is not None:  # remove excluded (other-attack) time from the benign exposure
        pre_dur -= ev.dt * float(np.sum(exc & (t >= ev.t_eval_start) & (t < ev.t_event)))
        post_dur -= ev.dt * float(np.sum(exc & (t > ev.t_attack_end)))
    benign_dur = pre_dur + post_dur
    benign_dur_h = benign_dur / 3600.0
    out = {
        "detected": bool(detected),
        "t_event": ev.t_event,
        "t_detect": t_detect,
        "delay": delay,
        "fires_pre": n_pre, "fires_attack": n_att, "fires_post": n_post,
        "windows_pre": int(pre.sum()), "windows_attack": int(att.sum()), "windows_post": int(post.sum()),
        "FPA_rate_pre": n_pre / pre.sum() if pre.sum() else float("nan"),
        "FPR_window": (n_pre + n_post) / neg.sum() if neg.sum() else float("nan"),
        "FP_per_hour": (n_pre + n_post) / benign_dur_h if benign_dur_h > 0 else float("nan"),
        "FP_per_1000_samples": 1000.0 * (n_pre + n_post) / (benign_dur / ev.dt) if benign_dur > 0 else float("nan"),
        "TPR_window": n_att / att.sum() if att.sum() else float("nan"),
        "first_fire_t": float(t_end[f].min()) if f.any() else float("nan"),
        "fire_times": [float(v) for v in t_end[f][:200]],
        "fires_excluded": int(f[excl_w].sum()), "windows_excluded": int((excl_w & ev_mask).sum()),
        "benign_hours": benign_dur_h,
    }
    a, p = auc_pair(overlap[ev_mask].astype(int), stat[ev_mask]) if compute_auc else (float("nan"), float("nan"))
    out["AUCROC_window"], out["AUCPR_window"] = a, p
    # per-sample (zero-order hold of the latest window statistic: causal)
    if label_per_sample is not None:
        idx = np.searchsorted(ends, np.arange(t.size), side="right") - 1
        ok = idx >= 0
        st_s = np.full(t.size, np.nan)
        st_s[ok] = stat[idx[ok]]
        fire_s = np.zeros(t.size, bool)
        fire_s[ok] = fires[idx[ok]]
        m = t >= ev.t_eval_start
        if exc is not None:
            m = m & ~(exc & (np.asarray(label_per_sample) == 0))
        y = np.asarray(label_per_sample)[m]
        a, p = auc_pair(y, st_s[m])
        out["AUCROC_persample"], out["AUCPR_persample"] = a, p
        fs = fire_s[m]
        out["FPR_persample"] = float((fs & (y == 0)).sum() / max(1, (y == 0).sum()))
        out["fire_samples"] = int(fs.sum())
        # legacy detection rule of scripts/eal_factorial.py: first fire-second
        # >= first attack second, at any later time (even after attack end)
        tt = t[m]
        la = tt[(fs) & (tt >= ev.t_event)]
        out["legacy_detected"] = bool(la.size)
        out["legacy_delay"] = float(la.min() - ev.t_event) if la.size else float("nan")
    return out
