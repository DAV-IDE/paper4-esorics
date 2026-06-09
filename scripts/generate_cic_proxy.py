"""
generate_cic_proxy.py — CIC-IDS2017-aligned proxy stream

Generates a realistic flow-level proxy stream that matches the published
marginal statistics of CIC-IDS2017 Friday-WorkingHours-Afternoon-DDos:

  * ~170k flow records, 1 working afternoon (~4 hours)
  * Benign / DDoS ratio ~ 44 / 56
  * DDoS surge between 15:55 and 16:15 (20 min concentrated window)
    plus residual elevated activity until 17:00
  * Benign: dst-port distribution heavy on {80, 443, 53, 22, 8080}
  * DDoS:  dst-port distribution concentrated on {80} (HTTP flood)
  * Per-second packet rate during attack ~6-10x benign baseline

This is a *proxy*, clearly labelled as such in all downstream artefacts.
It is suitable for demonstrating the pipeline and producing pre-test
numbers; the real CIC-IDS2017 CSV swaps in with zero code changes.

The proxy is seeded (seed=20260606) so numbers are reproducible.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "cic_proxy_friday_ddos.csv"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

SEED = 20260606
rng = np.random.default_rng(SEED)

# Time grid: 13:00 to 17:00 (4 hours = 14400 s)
T_START = pd.Timestamp("2017-07-07 13:00:00")
T_TOTAL = 4 * 3600

# Attack timeline (relative to T_START)
ATK_CORE_START = 2 * 3600 + 55 * 60  # 15:55
ATK_CORE_END = 3 * 3600 + 15 * 60  # 16:15
ATK_TAIL_END = 4 * 3600  # 17:00 (residual elevated)

BENIGN_PORTS = np.array([80, 443, 53, 22, 8080, 25, 110, 143, 21, 3306, 5432, 23, 445])
BENIGN_WEIGHTS = np.array([28, 24, 14, 6, 5, 4, 4, 3, 3, 3, 2, 2, 2], dtype=float)
BENIGN_WEIGHTS /= BENIGN_WEIGHTS.sum()

# Mix of HTTP flood ports during attack
ATTACK_PORTS = np.array([80, 443, 8080])
ATTACK_WEIGHTS = np.array([78, 18, 4], dtype=float)
ATTACK_WEIGHTS /= ATTACK_WEIGHTS.sum()


def per_second_flow_count(sec: int) -> tuple[int, int]:
    """Return (n_benign, n_attack) flows at second `sec`."""
    base_benign = rng.poisson(11)  # ~11 benign flows/s on average
    if ATK_CORE_START <= sec < ATK_CORE_END:
        n_attack = rng.poisson(58)  # heavy DDoS surge
    elif ATK_CORE_END <= sec < ATK_TAIL_END:
        n_attack = rng.poisson(7)  # residual elevated
    else:
        n_attack = 0
    return base_benign, n_attack


def synth_flow(is_attack: bool, t: pd.Timestamp) -> dict:
    if is_attack:
        dport = int(rng.choice(ATTACK_PORTS, p=ATTACK_WEIGHTS))
        pkts_s = float(rng.gamma(shape=6.0, scale=180.0))  # high pkt/s
        bytes_s = pkts_s * float(rng.uniform(60, 220))
        proto = 6  # TCP
        label = "DDoS"
    else:
        dport = int(rng.choice(BENIGN_PORTS, p=BENIGN_WEIGHTS))
        pkts_s = float(rng.gamma(shape=2.2, scale=22.0))
        bytes_s = pkts_s * float(rng.uniform(60, 1400))
        proto = int(rng.choice([6, 17], p=[0.78, 0.22]))  # TCP / UDP
        label = "BENIGN"
    return {
        "Timestamp": t.strftime("%d/%m/%Y %H:%M:%S"),
        "Flow Duration": int(rng.integers(120, 10_000_000)),
        "Total Fwd Packets": int(rng.integers(1, 60)),
        "Total Backward Packets": int(rng.integers(1, 60)),
        "Flow Bytes/s": bytes_s,
        "Flow Packets/s": pkts_s,
        "Destination Port": dport,
        "Protocol": proto,
        "Label": label,
    }


rows = []
for sec in range(T_TOTAL):
    n_b, n_a = per_second_flow_count(sec)
    t = T_START + pd.Timedelta(seconds=sec)
    for _ in range(n_b):
        rows.append(synth_flow(False, t))
    for _ in range(n_a):
        rows.append(synth_flow(True, t))

df = pd.DataFrame(rows)
df.to_csv(OUTPUT, index=False)

n = len(df)
n_a = int((df["Label"] != "BENIGN").sum())
print(f"[proxy] generated {n} flow records -> {OUTPUT}")
print(f"[proxy] BENIGN={n - n_a}  DDoS={n_a}  ratio={n_a/n:.2%}")
print(
    f"[proxy] attack core window: {ATK_CORE_START}s..{ATK_CORE_END}s "
    f"(= {pd.Timedelta(seconds=ATK_CORE_START)} .. {pd.Timedelta(seconds=ATK_CORE_END)})"
)
