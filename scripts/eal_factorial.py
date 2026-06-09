"""
eal_factorial.py — Reduced-factorial EAL run on the CIC-IDS2017 proxy

Implements the Entropy Analysis Layer (EAL) gating rule from Paper 4 §3:
fire iff |ε_t| > τ_s(W, s, E), with τ_s = μ_stable + 3·σ_stable computed
on a labelled stable warm-up phase, where ε_t is the entropy deviation
H(X_t) - H_base normalised by H_base.

Reduced 9-run factorial:
  E ∈ {Shannon, Sample, Permutation}  ×  (W, s) ∈ {(64, 8), (128, 4), (256, 1)}

For each run we emit detection_delay (first fire at or after first attack
second), FPR (post warm-up, pre-attack benign), AUC_ROC, fires_total.

Anti-cheat constraints (same as baseline_zscore.py):
  - Stable phase is the first WARMUP_SECONDS of the parquet (causal).
  - τ_s is computed once from that stable phase only.  No tuning on
    attack data.  No re-fit during streaming.
  - At time t, only entropy over the trailing (W, s) window using
    samples strictly before or at t is used; threshold comparison is
    `ε_t > τ_s`.
"""

from __future__ import annotations
import argparse, json, math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import numpy as np, pandas as pd


# ------------------- Entropy estimators -------------------
def shannon_entropy(x: np.ndarray, n_bins: int = 16) -> float:
    """Shannon entropy of a 1-D real signal via histogram binning."""
    if len(x) < 2:
        return 0.0
    hist, _ = np.histogram(x, bins=n_bins)
    total = hist.sum()
    if total == 0:
        return 0.0
    p = hist[hist > 0] / total
    return float(-np.sum(p * np.log2(p)))


def sample_entropy(x: np.ndarray, m: int = 2, r_factor: float = 0.2) -> float:
    """SampEn(m, r=r_factor·std(x)). Returns 0 for degenerate inputs."""
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
    """Bandt–Pompe permutation entropy of order m with given delay."""
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
    return float(h / math.log2(math.factorial(m)))  # normalised in [0,1]


ESTIMATORS = {
    "Shannon": shannon_entropy,
    "Sample": sample_entropy,
    "Permutation": permutation_entropy,
}


# ------------------- Per-second aggregation (reuse logic) -------------------
def aggregate_per_second(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["Timestamp"])
    df["__sec"] = df["Timestamp"].astype("int64") // 10**9
    grouped = df.groupby("__sec")
    rows = []
    for sec, g in grouped:
        pkt = float(
            g["Flow Packets/s"].replace([np.inf, -np.inf], np.nan).fillna(0).sum()
        )
        label = int((g["Label"].astype(str).str.strip().str.upper() != "BENIGN").any())
        rows.append((sec, pkt, label))
    out = pd.DataFrame(rows, columns=["__sec", "pkt_rate", "label"])
    out = out.sort_values("__sec").reset_index(drop=True)
    out["t"] = (out["__sec"] - out["__sec"].min()).astype(float)
    return out[["t", "pkt_rate", "label"]]


# ------------------- EAL run -------------------
@dataclass
class EALConfig:
    estimator: str
    W: int
    s: int
    warmup_s: int = 600
    k: float = 3.0
    n_bins_shannon: int = 16


def run_eal(per_second: pd.DataFrame, cfg: EALConfig) -> tuple[pd.DataFrame, dict]:
    f = ESTIMATORS[cfg.estimator]
    x = per_second["pkt_rate"].to_numpy()
    n = len(x)

    # Compute entropy at every stride-s position using trailing W samples
    eps_t = np.full(n, np.nan)
    for i in range(cfg.W - 1, n, cfg.s):
        window = x[i - cfg.W + 1 : i + 1]
        eps_t[i] = f(window)

    # Forward-fill so each t has the latest available entropy estimate
    eps_series = pd.Series(eps_t).ffill().to_numpy()

    # Stable-phase calibration: only seconds strictly inside warm-up AND
    # labelled benign.  μ_stable, σ_stable, τ_s = μ + k·σ.
    stable_mask = (per_second["t"].to_numpy() < cfg.warmup_s) & (
        per_second["label"].to_numpy() == 0
    )
    stable_vals = eps_series[stable_mask]
    stable_vals = stable_vals[~np.isnan(stable_vals)]
    if len(stable_vals) < 5:
        mu, sigma = np.nan, np.nan
    else:
        mu = float(np.mean(stable_vals))
        sigma = float(np.std(stable_vals))
    tau = mu + cfg.k * sigma if not math.isnan(mu) else float("inf")

    # Deviation epsilon_t = H_t - H_base, no normalisation needed because
    # tau is already on the same scale as H_t.
    fires = (
        (~np.isnan(eps_series))
        & (eps_series > tau)
        & (per_second["t"].to_numpy() >= cfg.warmup_s)
    )

    out = per_second.copy()
    out["H_t"] = eps_series
    out["fire"] = fires.astype(int)

    # Metrics post-warmup
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
    detected = False
    delay = float("nan")
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
        "n_attack_seconds": int((per_second["label"] == 1).sum()),
        "n_warmup_seconds": cfg.warmup_s,
    }


# ------------------- Driver -------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--warmup", type=int, default=600)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(a.input)
    per_sec = aggregate_per_second(df)

    GRID = [
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
    results = []
    for est, W, s in GRID:
        cfg = EALConfig(estimator=est, W=W, s=s, warmup_s=a.warmup)
        print(f"[eal] running E={est} W={W} s={s} ...")
        _, m = run_eal(per_sec, cfg)
        results.append(m)
        tag = f"{est.lower()}_W{W}_s{s}"
        (a.output / f"eal_{tag}_metrics.json").write_text(json.dumps(m, indent=2))
        print(
            f"      AUC_ROC={m['AUC_ROC']:.4f}  FPR={m['FPR_post_warmup']:.4f}  "
            f"delay={m['detection_delay_s']}  fires={m['n_fires_post_warmup']}"
        )

    summary_path = a.output / "eal_factorial_summary.json"
    summary_path.write_text(json.dumps(results, indent=2))
    print(f"\n[eal] summary -> {summary_path}")


if __name__ == "__main__":
    main()
