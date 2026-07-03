"""
baseline_zscore_real.py — Real-data variant of baseline_zscore.py

Same causal rolling z-score detector as `baseline_zscore.py`, but adapted
to the *native* temporal granularity of the CIC-IDS2017 Friday-Afternoon
DDoS CSV (TrafficLabelling variant on HuggingFace bvsam/cic-ids-2017),
which reports Timestamp values rounded to the minute — not the second.

Empirical finding (documented, not hidden)
------------------------------------------
The claim in `baseline_zscore.py`'s docstring that CIC-IDS2017 provides
per-second timestamps is *not* true for this file: only 93 unique
timestamps (one per minute) span the 92-minute afternoon.  Running the
per-second aggregator on real data therefore produces 6-7 rows and no
usable warm-up window.

Fix
---
1. Aggregate per *minute* (native granularity).
2. Report the time axis `t` in seconds (t = minute_index * 60), so the
   downstream table and Pareto plot code (which uses `t` in seconds) can
   be reused without modification.
3. Warm-up remains WARMUP_SECONDS = 600 s (= 10 minutes at native
   granularity), window WINDOW_SECONDS = 300 s (= 5 minutes).
4. All anti-cheat properties of the original detector are preserved:
   causal μ, σ; no oracle reset at attack boundary; k = 3 fixed a priori.

Everything else — feature triplet (pkt-rate, byte-rate, dport-entropy),
metrics, output filenames — matches `baseline_zscore.py` so
`build_table_and_pareto.py` consumes the results transparently.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

LOG = logging.getLogger("baseline_zscore_real")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@dataclass(frozen=True)
class Config:
    input_path: Path
    output_dir: Path
    warmup_seconds: int = 600
    window_seconds: int = 300
    k: float = 3.0


# ----------------------------- Rolling stats -----------------------------
class CausalRollingStats:
    def __init__(self, window_seconds: int) -> None:
        self.window_seconds = window_seconds
        self.buffer: deque = deque()
        self.sum_x = 0.0
        self.sum_x2 = 0.0

    def _evict(self, t_now: float) -> None:
        cutoff = t_now - self.window_seconds
        while self.buffer and self.buffer[0][0] < cutoff:
            _, x_old = self.buffer.popleft()
            self.sum_x -= x_old
            self.sum_x2 -= x_old * x_old

    def update_after(self, t_now: float, x_now: float) -> None:
        self.buffer.append((t_now, x_now))
        self.sum_x += x_now
        self.sum_x2 += x_now * x_now

    def stats_before(self, t_now: float):
        self._evict(t_now)
        n = len(self.buffer)
        if n < 2:
            return float("nan"), float("nan"), n
        mu = self.sum_x / n
        var = max(0.0, self.sum_x2 / n - mu * mu)
        return mu, math.sqrt(var), n


# ----------------------------- Aggregation -----------------------------
def shannon_entropy(counts) -> float:
    counts = np.asarray(list(counts), dtype=np.float64)
    total = counts.sum()
    if total <= 0:
        return 0.0
    p = counts / total
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


def aggregate_per_minute(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.dropna(subset=["Timestamp"])
    # Force nanosecond precision then group by unique minute
    df["Timestamp"] = df["Timestamp"].astype("datetime64[ns]")
    df["__min"] = df["Timestamp"].astype("int64") // (10**9 * 60)
    grouped = df.groupby("__min")
    rows = []
    for m, g in grouped:
        pkt = float(
            g["Flow Packets/s"].replace([np.inf, -np.inf], np.nan).fillna(0).sum()
        )
        byte = float(
            g["Flow Bytes/s"].replace([np.inf, -np.inf], np.nan).fillna(0).sum()
        )
        port_counts = g["Destination Port"].value_counts().tolist()
        ent = shannon_entropy(port_counts)
        label = int((g["Label"].astype(str).str.upper() != "BENIGN").any())
        rows.append((m, pkt, byte, ent, label))
    out = pd.DataFrame(
        rows, columns=["__min", "pkt_rate", "byte_rate", "dport_entropy", "label"]
    )
    out = out.sort_values("__min").reset_index(drop=True)
    # Convert to seconds so downstream tooling remains identical
    out["t"] = ((out["__min"] - out["__min"].min()) * 60).astype(float)
    return out[["t", "pkt_rate", "byte_rate", "dport_entropy", "label"]]


# ----------------------------- Detector -----------------------------
def run_zscore(per_time: pd.DataFrame, feature_col: str, cfg: Config) -> pd.DataFrame:
    stats = CausalRollingStats(window_seconds=cfg.window_seconds)
    mus, sigmas, zs, fires = [], [], [], []
    eps = 1e-9
    for _, row in per_time.iterrows():
        t = float(row["t"])
        x = float(row[feature_col])
        mu, sigma, n = stats.stats_before(t)
        if t < cfg.warmup_seconds or n < 2 or sigma < eps or math.isnan(sigma):
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
        stats.update_after(t, x)
    out = per_time.copy()
    out[f"mu_rolling_{feature_col}"] = mus
    out[f"sigma_rolling_{feature_col}"] = sigmas
    out[f"z_score_{feature_col}"] = zs
    out[f"fire_{feature_col}"] = fires
    return out


def compute_metrics(df: pd.DataFrame, feature_col: str, cfg: Config) -> dict:
    post = df[df["t"] >= cfg.warmup_seconds].copy()
    y = post["label"].to_numpy()
    z = post[f"z_score_{feature_col}"].to_numpy()
    f = post[f"fire_{feature_col}"].to_numpy()
    mask = ~np.isnan(z)
    y_m, z_m, f_m = y[mask], z[mask], f[mask]

    try:
        from sklearn.metrics import roc_auc_score, average_precision_score

        auc_roc = float(roc_auc_score(y_m, z_m)) if len(set(y_m)) > 1 else float("nan")
        auc_pr = (
            float(average_precision_score(y_m, z_m))
            if len(set(y_m)) > 1
            else float("nan")
        )
    except Exception:
        auc_roc = auc_pr = float("nan")

    n_neg = int((y_m == 0).sum())
    fp = int(((y_m == 0) & (f_m == 1)).sum())
    fpr = (fp / n_neg) if n_neg > 0 else float("nan")

    attack_t = post.loc[post["label"] == 1, "t"]
    fire_t = post.loc[post[f"fire_{feature_col}"] == 1, "t"]
    detected, delay = False, float("nan")
    if len(attack_t):
        first_attack = float(attack_t.min())
        fires_after = fire_t[fire_t >= first_attack]
        if len(fires_after) > 0:
            delay = float(fires_after.min()) - first_attack
            detected = True

    return {
        "feature": feature_col,
        "AUC_ROC": auc_roc,
        "AUC_PR": auc_pr,
        "FPR_at_k3": fpr,
        "detected": detected,
        "detection_delay_s": delay,
        "n_fires_post_warmup": int(f_m.sum()),
        "n_total_seconds": int(len(df) * 60),  # informative: total wall-clock coverage
        "n_post_warmup_seconds": int(len(post) * 60),
        "n_attack_seconds": int((df["label"] == 1).sum() * 60),
        "n_warmup_seconds": int(cfg.warmup_seconds),
        "k": cfg.k,
        "window_seconds": cfg.window_seconds,
        "granularity": "native minute (CIC-IDS2017 TrafficLabelling rounds to minute)",
    }


# ----------------------------- Main -----------------------------
def main(cfg: Config) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    if cfg.input_path.suffix == ".parquet":
        df = pd.read_parquet(cfg.input_path)
    else:
        df = pd.read_csv(cfg.input_path, low_memory=False)
    LOG.info("Loaded %d flow records", len(df))
    per_time = aggregate_per_minute(df)
    LOG.info(
        "Per-minute rows: %d, attack-minutes: %d",
        len(per_time),
        int(per_time["label"].sum()),
    )

    features = [
        ("pktrate", "pkt_rate"),
        ("byterate", "byte_rate"),
        ("dportentropy", "dport_entropy"),
    ]
    all_metrics = {}
    for short, col in features:
        enriched = run_zscore(per_time, col, cfg)
        (cfg.output_dir / f"baseline_zscore_{short}.csv").write_text(
            enriched.to_csv(index=False)
        )
        m = compute_metrics(enriched, col, cfg)
        (cfg.output_dir / f"baseline_zscore_{short}_metrics.json").write_text(
            json.dumps(m, indent=2)
        )
        all_metrics[short] = m
        LOG.info(
            "  %s: AUC_ROC=%.4f FPR=%.4f delay=%s fires=%d",
            col,
            m["AUC_ROC"],
            m["FPR_at_k3"],
            m["detection_delay_s"],
            m["n_fires_post_warmup"],
        )

    (cfg.output_dir / "baseline_zscore_summary.json").write_text(
        json.dumps(all_metrics, indent=2)
    )
    LOG.info("Summary written")


def parse_args() -> Config:
    p = argparse.ArgumentParser(
        description="Causal rolling z-score baseline on real CIC-IDS2017 (native minute)"
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
