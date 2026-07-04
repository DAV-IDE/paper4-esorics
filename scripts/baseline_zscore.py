"""
baseline_zscore.py — Rolling z-score baseline detector for Paper 4 §5.2

Purpose
-------
Provide a transparent, parameter-free baseline against which EAL's
parameterised entropy gating is compared on the CIC-IDS2017 Friday
afternoon DDoS subset.

Design (anti-cheat constraints documented inline)
-------------------------------------------------
1.  Rolling window of W_seconds = 300 s (5 min) computed in *true wall-
    clock* time using the Timestamp column.  We never reset the window
    at an attack boundary (no oracle leakage).
2.  μ and σ are computed on a CAUSAL trailing window only (strict <t).
    Sample at boundary t is compared to (μ_{<t}, σ_{<t}); never to
    statistics that include t itself.
3.  Bootstrap phase: the first WARMUP_SECONDS seconds (default 600 s)
    are used to seed μ, σ.  During warm-up the detector ALWAYS emits 0
    (no firing), so no false positive can be claimed on under-fitted
    statistics.
4.  Detection rule: fire iff x_t > μ_{<t} + k·σ_{<t}, with k = 3.
5.  Three feature variants are run independently and reported side-by-
    side (so reviewers can see the variance of "z-score baseline"):
      F1: total packet rate per second
      F2: total byte rate per second
      F3: dst-port Shannon entropy per second
6.  No supervised threshold tuning.  k = 3 is fixed a priori.

Outputs
-------
For each feature F1, F2, F3 we emit:
  - results/baseline_zscore_<feature>.csv  with columns
      t,
      feature_value,
      mu_rolling,
      sigma_rolling,
      z_score,
      fire,        (0/1, post-warmup only)
      label        (0 benign, 1 attack — from CIC-IDS2017 ground truth)
  - results/baseline_zscore_<feature>_metrics.json with
      AUC_PR, AUC_ROC, FPR_at_warmup_threshold, detection_delay_s,
      n_total_seconds, n_attack_seconds, n_warmup_seconds.

The same I/O contract is consumed by the EAL-vs-baseline comparison
table generator (tables/real_data.tex).

Usage
-----
    python baseline_zscore.py \
        --input  ../data/cicids2017_friday_ddos.parquet \
        --output ../results/ \
        --warmup 600 --window 300 --k 3

Author : Paper 4 day-1 morning sprint
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import warnings
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

# sklearn is used only to compute ROC-AUC and PR-AUC. If it is not
# installed, we fall back to NaN for those two columns of the output
# JSON/CSV and PRINT AN EXPLICIT WARNING so the reader knows why AUC
# is NaN. Previously a bare `except Exception: return nan` also
# swallowed genuine value errors (e.g. all-same-class inputs) into a
# silent NaN, indistinguishable from a missing dependency.
try:
    from sklearn.metrics import (
        roc_auc_score as _roc_auc_score,
        average_precision_score as _average_precision_score,
    )
    _SKLEARN_AVAILABLE = True
except ImportError as _sklearn_err:
    _SKLEARN_AVAILABLE = False
    warnings.warn(
        f"scikit-learn is not installed ({_sklearn_err!s}); AUC-ROC and "
        "AUC-PR columns will be NaN in the baseline output. Install with "
        "`pip install scikit-learn` to enable AUC computation.",
        RuntimeWarning,
        stacklevel=2,
    )
    print(
        "[baseline_zscore] WARNING: scikit-learn missing; AUC-ROC and "
        "AUC-PR will be NaN. Install scikit-learn to enable.",
        file=sys.stderr,
    )

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
LOG = logging.getLogger("baseline_zscore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Config:
    input_path: Path
    output_dir: Path
    warmup_seconds: int = 600
    window_seconds: int = 300
    k: float = 3.0
    label_col: str = "Label"
    timestamp_col: str = "Timestamp"
    pkt_col: str = "Flow Packets/s"  # CIC-IDS2017 feature
    byte_col: str = "Flow Bytes/s"
    dst_port_col: str = "Destination Port"
    eps: float = 1e-9


# ---------------------------------------------------------------------
# Streaming rolling stats (anti-cheat: causal only)
# ---------------------------------------------------------------------
class CausalRollingStats:
    """Maintain rolling mean / std over a strictly causal window of
    duration `window_seconds` indexed by wall-clock t."""

    def __init__(self, window_seconds: int) -> None:
        self.window_seconds = window_seconds
        self.buffer: deque[tuple[float, float]] = deque()  # (t, x)
        self.sum_x = 0.0
        self.sum_x2 = 0.0

    def _evict(self, t_now: float) -> None:
        cutoff = t_now - self.window_seconds
        while self.buffer and self.buffer[0][0] < cutoff:
            _, x_old = self.buffer.popleft()
            self.sum_x -= x_old
            self.sum_x2 -= x_old * x_old

    def update_after(self, t_now: float, x_now: float) -> None:
        """Add x_now to the window AFTER it has been compared.
        This guarantees that the comparison at t_now uses statistics
        derived from samples strictly earlier than t_now (anti-cheat)."""
        self.buffer.append((t_now, x_now))
        self.sum_x += x_now
        self.sum_x2 += x_now * x_now

    def stats_before(self, t_now: float) -> tuple[float, float, int]:
        """Return (mu, sigma, n) from samples strictly earlier than t_now."""
        self._evict(t_now)
        n = len(self.buffer)
        if n < 2:
            return float("nan"), float("nan"), n
        mu = self.sum_x / n
        var = max(0.0, self.sum_x2 / n - mu * mu)
        return mu, math.sqrt(var), n


# ---------------------------------------------------------------------
# Feature extractors (per-second aggregations)
# ---------------------------------------------------------------------
def shannon_entropy_of_distribution(counts: Iterable[int]) -> float:
    counts = np.asarray(list(counts), dtype=np.float64)
    total = counts.sum()
    if total <= 0:
        return 0.0
    p = counts / total
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


def aggregate_per_second(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Aggregate flow-level CIC-IDS2017 records to 1-second buckets.

    Returns one row per second with columns
        t            : float seconds since min(Timestamp)
        pkt_rate     : sum of Flow Packets/s
        byte_rate    : sum of Flow Bytes/s
        dport_entropy: Shannon entropy of Destination Port distribution
        label        : 1 if any flow in the second is attack, else 0
    """
    df = df.copy()
    df[cfg.timestamp_col] = pd.to_datetime(df[cfg.timestamp_col], errors="coerce")
    df = df.dropna(subset=[cfg.timestamp_col])
    df["__sec"] = df[cfg.timestamp_col].astype("int64") // 10**9

    grouped = df.groupby("__sec")
    rows = []
    for sec, g in grouped:
        pkt = float(g[cfg.pkt_col].replace([np.inf, -np.inf], np.nan).fillna(0).sum())
        byte = float(g[cfg.byte_col].replace([np.inf, -np.inf], np.nan).fillna(0).sum())
        port_counts = g[cfg.dst_port_col].value_counts().tolist()
        ent = shannon_entropy_of_distribution(port_counts)
        label = int((g[cfg.label_col].astype(str).str.upper() != "BENIGN").any())
        rows.append((sec, pkt, byte, ent, label))

    out = pd.DataFrame(
        rows, columns=["__sec", "pkt_rate", "byte_rate", "dport_entropy", "label"]
    )
    out = out.sort_values("__sec").reset_index(drop=True)
    out["t"] = (out["__sec"] - out["__sec"].min()).astype(float)
    return out[["t", "pkt_rate", "byte_rate", "dport_entropy", "label"]]


# ---------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------
@dataclass
class FeatureRun:
    name: str
    column: str
    series: list = field(default_factory=list)


def run_zscore_detector(
    per_second: pd.DataFrame, feature_col: str, cfg: Config
) -> pd.DataFrame:
    """Apply the causal z-score detector to one feature series.

    Returns the per-second DataFrame extended with mu, sigma, z, fire.
    During warm-up (t < warmup_seconds) fire == 0 by construction.
    """
    stats = CausalRollingStats(window_seconds=cfg.window_seconds)
    mus, sigmas, zs, fires = [], [], [], []

    for _, row in per_second.iterrows():
        t = float(row["t"])
        x = float(row[feature_col])

        mu, sigma, n = stats.stats_before(t)
        if t < cfg.warmup_seconds or n < 2 or sigma < cfg.eps or math.isnan(sigma):
            mus.append(mu)
            sigmas.append(sigma)
            zs.append(float("nan"))
            fires.append(0)
        else:
            z = (x - mu) / sigma
            mus.append(mu)
            sigmas.append(sigma)
            zs.append(z)
            fires.append(int(z > cfg.k))

        # Update AFTER comparison: enforces causality.
        stats.update_after(t, x)

    out = per_second.copy()
    out[f"mu_rolling_{feature_col}"] = mus
    out[f"sigma_rolling_{feature_col}"] = sigmas
    out[f"z_score_{feature_col}"] = zs
    out[f"fire_{feature_col}"] = fires
    return out


# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------
def compute_metrics(df: pd.DataFrame, feature_col: str, cfg: Config) -> dict:
    """AUC-ROC, AUC-PR, FPR @ k=3 threshold, detection delay (seconds
    from first attack-labelled second to first post-warmup fire)."""

    post_warmup = df[df["t"] >= cfg.warmup_seconds].copy()
    y_true = post_warmup["label"].to_numpy()
    z = post_warmup[f"z_score_{feature_col}"].to_numpy()
    fire = post_warmup[f"fire_{feature_col}"].to_numpy()

    # Drop NaN z scores from AUC computation (warm-up residue)
    mask = ~np.isnan(z)
    y_m = y_true[mask]
    z_m = z[mask]
    f_m = fire[mask]

    def auc_roc(y, s):
        if not _SKLEARN_AVAILABLE:
            return float("nan")
        if len(set(y)) <= 1:
            # AUC undefined when only one class present.
            return float("nan")
        return float(_roc_auc_score(y, s))

    def auc_pr(y, s):
        if not _SKLEARN_AVAILABLE:
            return float("nan")
        if len(set(y)) <= 1:
            return float("nan")
        return float(_average_precision_score(y, s))

    # FPR at fixed k=3 threshold
    n_neg = int((y_m == 0).sum())
    fp = int(((y_m == 0) & (f_m == 1)).sum())
    fpr_at_k = (fp / n_neg) if n_neg > 0 else float("nan")

    # Detection delay: first fire AT OR AFTER first attack second.
    # This is the only honest definition: pre-attack fires are FPs and
    # cannot count as "early detection".  If no fire occurs inside or
    # after the attack window, delay is reported as NaN and a separate
    # field `detected` flags the miss.
    attack_t = post_warmup.loc[post_warmup["label"] == 1, "t"]
    fire_t = post_warmup.loc[post_warmup[f"fire_{feature_col}"] == 1, "t"]
    detected = False
    delay = float("nan")
    if len(attack_t):
        first_attack = float(attack_t.min())
        fires_after = fire_t[fire_t >= first_attack]
        if len(fires_after) > 0:
            first_fire_after = float(fires_after.min())
            delay = first_fire_after - first_attack
            detected = True

    return {
        "feature": feature_col,
        "AUC_ROC": auc_roc(y_m, z_m),
        "AUC_PR": auc_pr(y_m, z_m),
        "FPR_at_k3": fpr_at_k,
        "detected": detected,
        "detection_delay_s": delay,
        "n_fires_post_warmup": int(f_m.sum()),
        "n_total_seconds": int(len(df)),
        "n_post_warmup_seconds": int(len(post_warmup)),
        "n_attack_seconds": int((df["label"] == 1).sum()),
        "n_warmup_seconds": int(cfg.warmup_seconds),
        "k": cfg.k,
        "window_seconds": cfg.window_seconds,
    }


# ---------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------
def main(cfg: Config) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    LOG.info("Loading %s", cfg.input_path)

    if cfg.input_path.suffix == ".parquet":
        df = pd.read_parquet(cfg.input_path)
    else:
        df = pd.read_csv(cfg.input_path, low_memory=False)

    LOG.info("Loaded %d flow records", len(df))
    LOG.info("Aggregating per-second features...")
    per_second = aggregate_per_second(df, cfg)
    LOG.info(
        "Per-second rows: %d, attack-seconds: %d",
        len(per_second),
        int(per_second["label"].sum()),
    )

    features = [
        ("pktrate", "pkt_rate"),
        ("byterate", "byte_rate"),
        ("dportentropy", "dport_entropy"),
    ]

    all_metrics = {}
    for short, col in features:
        LOG.info("Running z-score detector on feature %s", col)
        enriched = run_zscore_detector(per_second, col, cfg)
        out_csv = cfg.output_dir / f"baseline_zscore_{short}.csv"
        enriched.to_csv(out_csv, index=False)
        LOG.info("  -> wrote %s", out_csv)

        m = compute_metrics(enriched, col, cfg)
        out_json = cfg.output_dir / f"baseline_zscore_{short}_metrics.json"
        out_json.write_text(json.dumps(m, indent=2))
        LOG.info("  -> wrote %s", out_json)
        all_metrics[short] = m

    summary = cfg.output_dir / "baseline_zscore_summary.json"
    summary.write_text(json.dumps(all_metrics, indent=2))
    LOG.info("Summary written to %s", summary)


def parse_args() -> Config:
    p = argparse.ArgumentParser(
        description="Causal rolling z-score baseline (Paper 4 §5.2)"
    )
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--warmup", type=int, default=600)
    p.add_argument("--window", type=int, default=300)
    p.add_argument("--k", type=float, default=3.0)
    a = p.parse_args()
    return Config(
        input_path=a.input,
        output_dir=a.output,
        warmup_seconds=a.warmup,
        window_seconds=a.window,
        k=a.k,
    )


if __name__ == "__main__":
    main(parse_args())
