"""Dataset builders for the R1 experiments.

synthetic(seed)      : identical draw order to LoreBerto03/psi-risk-dt-pipeline
                       @57fc6d1 generate_synthetic_dataset(); an extra
                       independent 'stable_holdout' series is drawn AFTER the
                       three published scenarios (so they stay bit-identical).
proxy_per_second(seed): exact re-implementation of scripts/generate_cic_proxy.py
                       (same RNG call order) aggregated per second as in
                       scripts/eal_factorial.py::aggregate_per_second.
real_minute(path)    : CIC-IDS2017 TrafficLabelling parquet (HF mirror
                       bvsam/cic-ids-2017), aggregated per minute exactly as
                       scripts/eal_factorial_real.py (PR #3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------- synthetic (upstream constants, configs/config.py) ----------
N_SYN = 3000
DRIFT_START, DRIFT_END, DRIFT_MAX = 1000, 2000, 2.5
SHOCK_CENTER, SHOCK_WIDTH, SHOCK_AMPLITUDE = 1500, 25, 4.0
NOISE_STD = 0.15
SYN_EVENTS = {  # t_event, t_attack_end (inclusive)
    "drift_gradual": (DRIFT_START, DRIFT_END),
    "shock": (SHOCK_CENTER - 2 * SHOCK_WIDTH, SHOCK_CENTER + 2 * SHOCK_WIDTH),
}
SYN_CONFIGS = {"C1": (128, 1), "C2": (64, 1), "C3": (256, 1), "C4": (128, 4), "C5": (128, 8)}


def synthetic(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    t = np.arange(N_SYN)
    stable = rng.normal(0.0, NOISE_STD, size=N_SYN)
    drift = np.zeros(N_SYN)
    m = (t >= DRIFT_START) & (t <= DRIFT_END)
    drift[m] = np.linspace(0.0, DRIFT_MAX, m.sum())
    drift[t > DRIFT_END] = DRIFT_MAX
    drift = drift + rng.normal(0.0, NOISE_STD, size=N_SYN)
    shock = SHOCK_AMPLITUDE * np.exp(-0.5 * ((t - SHOCK_CENTER) / SHOCK_WIDTH) ** 2) + rng.normal(0.0, NOISE_STD, size=N_SYN)
    holdout = rng.normal(0.0, NOISE_STD, size=N_SYN)
    return {"t": t.astype(float), "stable": stable, "drift_gradual": drift, "shock": shock, "stable_holdout": holdout}


# ---------------- proxy (scripts/generate_cic_proxy.py) ----------------------
T_TOTAL = 4 * 3600
ATK_CORE_START, ATK_CORE_END, ATK_TAIL_END = 2 * 3600 + 55 * 60, 3 * 3600 + 15 * 60, 4 * 3600
BENIGN_PORTS = np.array([80, 443, 53, 22, 8080, 25, 110, 143, 21, 3306, 5432, 23, 445])
BW = np.array([28, 24, 14, 6, 5, 4, 4, 3, 3, 3, 2, 2, 2], float); BW /= BW.sum()
ATTACK_PORTS = np.array([80, 443, 8080])
AW = np.array([78, 18, 4], float); AW /= AW.sum()


def proxy_per_second(seed: int = 20260606) -> pd.DataFrame:
    """Same RNG call sequence as the original per-flow generator."""
    rng = np.random.default_rng(seed)
    pkt = np.zeros(T_TOTAL)
    lab = np.zeros(T_TOTAL, int)
    nflows = np.zeros(T_TOTAL, int)
    for sec in range(T_TOTAL):
        nb = rng.poisson(11)
        if ATK_CORE_START <= sec < ATK_CORE_END:
            na = rng.poisson(58)
        elif ATK_CORE_END <= sec < ATK_TAIL_END:
            na = rng.poisson(7)
        else:
            na = 0
        tot = 0.0
        for _ in range(nb):
            rng.choice(BENIGN_PORTS, p=BW)
            p = float(rng.gamma(shape=2.2, scale=22.0))
            rng.uniform(60, 1400)
            rng.choice([6, 17], p=[0.78, 0.22])
            rng.integers(120, 10_000_000); rng.integers(1, 60); rng.integers(1, 60)
            tot += p
        for _ in range(na):
            rng.choice(ATTACK_PORTS, p=AW)
            p = float(rng.gamma(shape=6.0, scale=180.0))
            rng.uniform(60, 220)
            rng.integers(120, 10_000_000); rng.integers(1, 60); rng.integers(1, 60)
            tot += p
        pkt[sec] = tot
        lab[sec] = int(na > 0)
        nflows[sec] = nb + na
    keep = nflows > 0  # aggregate_per_second only emits seconds with flows
    df = pd.DataFrame({"sec": np.arange(T_TOTAL)[keep], "pkt_rate": pkt[keep], "label": lab[keep]})
    df["t"] = (df["sec"] - df["sec"].min()).astype(float)
    return df[["t", "pkt_rate", "label"]].reset_index(drop=True)


# ---------------- real, minute aggregation (PR #3) ---------------------------
def real_minute(path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df.dropna(subset=["Timestamp"])
    df["__min"] = df["Timestamp"].astype("int64") // (10**9 * 60) if df["Timestamp"].dtype == "datetime64[ns]" else df["Timestamp"].values.astype("datetime64[s]").astype("int64") // 60
    rows = []
    for mn, g in df.groupby("__min"):
        pkt = float(g["Flow Packets/s"].replace([np.inf, -np.inf], np.nan).fillna(0).sum())
        lab = int((g["Label"].astype(str).str.strip().str.upper() != "BENIGN").any())
        rows.append((mn, pkt, lab, len(g)))
    out = pd.DataFrame(rows, columns=["__min", "pkt_rate", "label", "n_flows"]).sort_values("__min")
    out["t"] = ((out["__min"] - out["__min"].min()) * 60).astype(float)
    return out[["t", "pkt_rate", "label", "n_flows"]].reset_index(drop=True)
