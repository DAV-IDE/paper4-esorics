"""
eal_factorial_real.py — Real-data variant of eal_factorial.py

Same 9-run reduced factorial (E × (W, s)) as `eal_factorial.py`, but
adapted to the native per-minute granularity of the CIC-IDS2017 Friday-
Afternoon-DDoS CSV (TrafficLabelling variant).

Empirical finding
-----------------
CIC-IDS2017 TrafficLabelling timestamps round to the minute, so the
original per-second aggregation yields ~6 points — too few for any
window/stride combination in the factorial grid.  Here we aggregate per
minute and expose `t` in seconds so `build_table_and_pareto.py` remains
untouched.

Grid, warm-up, k, stable-phase calibration and epsilon>tau firing rule
are identical to `eal_factorial.py`.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


# ------------------- Entropy estimators (unchanged) -------------------
def shannon_entropy(x: np.ndarray, n_bins: int = 16) -> float:
    if len(x) < 2:
        return 0.0
    hist, _ = np.histogram(x, bins=n_bins)
    total = hist.sum()
    if total == 0:
        return 0.0
    p = hist[hist > 0] / total
    return float(-np.sum(p * np.log2(p)))


def sample_entropy(x: np.ndarray, m: int = 2, r_factor: float = 0.2) -> float:
    n = len(x)
    if n < m + 2:
        return 0.0
    s = x.std()
    if s < 1e-9:
        return 0.0
    r = r_factor * s

    def _count(m_size: int) -> int:
        n_templates = n - m_size + 1
        if n_templates < 2:
            return 0
        templates = np.lib.stride_tricks.sliding_window_view(x, m_size)
        count = 0
        for i in range(n_templates - 1):
            d = np.max(np.abs(templates[i + 1 :] - templates[i]), axis=1)
            count += int((d <= r).sum())
        return count

    B = _count(m)
    A = _count(m + 1)
    if B == 0 or A == 0:
        return 0.0
    return float(-math.log(A / B))


def permutation_entropy(x: np.ndarray, m: int = 3, delay: int = 1) -> float:
    n = len(x)
    if n < m * delay + 1:
        return 0.0
    patterns = []
    for i in range(n - (m - 1) * delay):
        window = x[i : i + m * delay : delay]
        patterns.append(tuple(np.argsort(window)))
    counts = Counter(patterns)
    total = sum(counts.values())
    p = np.array(list(counts.values())) / total
    h = -np.sum(p * np.log2(p))
    return float(h / math.log2(math.factorial(m)))


ESTIMATORS = {
    "Shannon": shannon_entropy,
    "Sample": sample_entropy,
    "Permutation": permutation_entropy,
}


# ------------------- Per-minute aggregation -------------------
def aggregate_per_minute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.dropna(subset=["Timestamp"])
    df["Timestamp"] = df["Timestamp"].astype("datetime64[ns]")
    df["__min"] = df["Timestamp"].astype("int64") // (10**9 * 60)
    grouped = df.groupby("__min")
    rows = []
    for m, g in grouped:
        pkt = float(
            g["Flow Packets/s"].replace([np.inf, -np.inf], np.nan).fillna(0).sum()
        )
        label = int((g["Label"].astype(str).str.strip().str.upper() != "BENIGN").any())
        rows.append((m, pkt, label))
    out = pd.DataFrame(rows, columns=["__min", "pkt_rate", "label"])
    out = out.sort_values("__min").reset_index(drop=True)
    out["t"] = ((out["__min"] - out["__min"].min()) * 60).astype(float)
    return out[["t", "pkt_rate", "label"]]


# ------------------- EAL run -------------------
@dataclass
class EALConfig:
    estimator: str
    W: int
    s: int
    warmup_s: int = 600
    k: float = 3.0


def run_eal(per_time: pd.DataFrame, cfg: EALConfig) -> tuple[pd.DataFrame, dict]:
    f = ESTIMATORS[cfg.estimator]
    x = per_time["pkt_rate"].to_numpy()
    n = len(x)

    eps_t = np.full(n, np.nan)
    for i in range(cfg.W - 1, n, cfg.s):
        window = x[i - cfg.W + 1 : i + 1]
        eps_t[i] = f(window)

    eps_series = pd.Series(eps_t).ffill().to_numpy()

    stable_mask = (per_time["t"].to_numpy() < cfg.warmup_s) & (
        per_time["label"].to_numpy() == 0
    )
    stable_vals = eps_series[stable_mask]
    stable_vals = stable_vals[~np.isnan(stable_vals)]
    if len(stable_vals) < 5:
        mu, sigma = np.nan, np.nan
    else:
        mu = float(np.mean(stable_vals))
        sigma = float(np.std(stable_vals))
    tau = mu + cfg.k * sigma if not math.isnan(mu) else float("inf")

    fires = (
        (~np.isnan(eps_series))
        & (eps_series > tau)
        & (per_time["t"].to_numpy() >= cfg.warmup_s)
    )

    out = per_time.copy()
    out["H_t"] = eps_series
    out["fire"] = fires.astype(int)

    pw = out[out["t"] >= cfg.warmup_s].copy()
    y = pw["label"].to_numpy()
    h = pw["H_t"].to_numpy()
    f_ = pw["fire"].to_numpy()
    mask = ~np.isnan(h)
    y_m, h_m, f_m = y[mask], h[mask], f_[mask]

    try:
        from sklearn.metrics import roc_auc_score, average_precision_score

        auc_roc = float(roc_auc_score(y_m, h_m)) if len(set(y_m)) > 1 else float("nan")
        auc_pr = (
            float(average_precision_score(y_m, h_m))
            if len(set(y_m)) > 1
            else float("nan")
        )
    except Exception:
        auc_roc = auc_pr = float("nan")

    n_neg = int((y_m == 0).sum())
    fp = int(((y_m == 0) & (f_m == 1)).sum())
    fpr = (fp / n_neg) if n_neg > 0 else float("nan")

    attack_t = pw.loc[pw["label"] == 1, "t"]
    fire_t = pw.loc[pw["fire"] == 1, "t"]
    detected, delay = False, float("nan")
    if len(attack_t):
        first_attack = float(attack_t.min())
        fires_after = fire_t[fire_t >= first_attack]
        if len(fires_after) > 0:
            delay = float(fires_after.min()) - first_attack
            detected = True

    return out, {
        "estimator": cfg.estimator,
        "W": cfg.W,
        "s": cfg.s,
        "k": cfg.k,
        "mu_stable": mu,
        "sigma_stable": sigma,
        "tau": tau,
        "AUC_ROC": auc_roc,
        "AUC_PR": auc_pr,
        "FPR_post_warmup": fpr,
        "detected": detected,
        "detection_delay_s": delay,
        "n_fires_post_warmup": int(f_m.sum()),
        "n_attack_seconds": int((per_time["label"] == 1).sum() * 60),
        "n_warmup_seconds": cfg.warmup_s,
        "granularity": "native minute",
    }


# ------------------- Driver -------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--warmup", type=int, default=600)
    p.add_argument(
        "--native-min",
        action="store_true",
        help="Use rescaled (W,s) grid matching the native per-minute granularity.",
    )
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(a.input)
    per_time = aggregate_per_minute(df)
    print(
        f"[eal-real] per-minute rows={len(per_time)}, attack-minutes={int(per_time['label'].sum())}"
    )

    # Two grids are run back-to-back:
    #   ORIGINAL: (W, s) = (64, 8), (128, 4), (256, 1) as in the proxy run.
    #     On real data (93 minutes) all 9 configurations miss because the
    #     smallest window (64) already exceeds the 25-minute pre-attack
    #     buffer.  This is a documented empirical finding, not hidden.
    #   NATIVE-MIN: (W, s) rescaled to the real granularity (minutes).
    #     Interpretation: 8 min = short window, 16 min = medium, 32 min =
    #     long.  Stride s tracks the proxy pattern (long-window fine-step).
    ORIGINAL_GRID = [
        ("Shannon", 64, 8),
        ("Shannon", 128, 4),
        ("Shannon", 256, 1),
        ("Sample", 64, 8),
        ("Sample", 128, 4),
        ("Sample", 256, 1),
        ("Permutation", 64, 8),
        ("Permutation", 128, 4),
        ("Permutation", 256, 1),
    ]
    NATIVE_MIN_GRID = [
        ("Shannon", 8, 4),
        ("Shannon", 16, 2),
        ("Shannon", 32, 1),
        ("Sample", 8, 4),
        ("Sample", 16, 2),
        ("Sample", 32, 1),
        ("Permutation", 8, 4),
        ("Permutation", 16, 2),
        ("Permutation", 32, 1),
    ]
    GRID = NATIVE_MIN_GRID if a.native_min else ORIGINAL_GRID
    results = []
    for est, W, s in GRID:
        cfg = EALConfig(estimator=est, W=W, s=s, warmup_s=a.warmup)
        print(f"[eal-real] running E={est} W={W} s={s} ...")
        _, m = run_eal(per_time, cfg)
        results.append(m)
        tag = f"{est.lower()}_W{W}_s{s}"
        (a.output / f"eal_{tag}_metrics.json").write_text(json.dumps(m, indent=2))
        delay = m["detection_delay_s"]
        delay_str = f"{delay:.0f}" if not math.isnan(delay) else "miss"
        print(
            f"      AUC_ROC={m['AUC_ROC']:.4f}  FPR={m['FPR_post_warmup']:.4f}  "
            f"delay={delay_str}  fires={m['n_fires_post_warmup']}"
        )

    (a.output / "eal_factorial_summary.json").write_text(json.dumps(results, indent=2))
    print(f"[eal-real] summary -> {a.output}/eal_factorial_summary.json")


if __name__ == "__main__":
    main()
