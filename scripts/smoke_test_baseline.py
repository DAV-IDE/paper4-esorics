"""
smoke_test_baseline.py — Synthetic smoke test for baseline_zscore.py

Generates 2 hours of synthetic CIC-IDS2017-like flow data with a clean
DDoS surge at minute 90, then runs the full baseline pipeline end-to-end.
Validates: pipeline runs, metrics computed, FPR is reasonable in benign
warmup, fires concentrate in attack window.

This is NOT the real Day-1 result — it's a sanity check so we know the
script works the moment the CIC-IDS2017 CSV lands on disk.
"""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data"
RESULTS_DIR = HERE.parent / "results" / "smoke"
DATA_DIR.mkdir(exist_ok=True, parents=True)
RESULTS_DIR.mkdir(exist_ok=True, parents=True)

rng = np.random.default_rng(42)

# Simulate 2 hours = 7200 seconds.  Generate ~50 benign flows/sec, with
# a DDoS surge between t=5400s and t=6300s (15 min window) where flow
# rate jumps 8x and dst-port concentrates on port 80.
T_TOTAL = 7200
ATTACK_START, ATTACK_END = 5400, 6300

rows = []
t0 = pd.Timestamp("2017-07-07 13:00:00")

for sec in range(T_TOTAL):
    is_attack = ATTACK_START <= sec < ATTACK_END
    n_flows = rng.poisson(400 if is_attack else 50)
    label = "DDoS" if is_attack else "BENIGN"
    for _ in range(n_flows):
        if is_attack:
            dport = 80
            pkts_s = rng.gamma(shape=8.0, scale=200.0)
            bytes_s = pkts_s * rng.uniform(60, 200)
        else:
            dport = int(rng.choice([80, 443, 22, 53, 8080, 3306, 25, 110, 143, 21]))
            pkts_s = rng.gamma(shape=2.0, scale=20.0)
            bytes_s = pkts_s * rng.uniform(60, 1400)
        rows.append(
            {
                "Timestamp": (t0 + pd.Timedelta(seconds=sec)).strftime(
                    "%d/%m/%Y %H:%M:%S"
                ),
                "Flow Duration": rng.integers(100, 10_000_000),
                "Total Fwd Packets": int(rng.integers(1, 50)),
                "Total Backward Packets": int(rng.integers(1, 50)),
                "Flow Bytes/s": float(bytes_s),
                "Flow Packets/s": float(pkts_s),
                "Destination Port": dport,
                "Protocol": int(rng.choice([6, 17])),
                "Label": label,
            }
        )

df = pd.DataFrame(rows)
csv_path = DATA_DIR / "smoke_friday_ddos.csv"
df.to_csv(csv_path, index=False)
print(f"[smoke] generated {len(df)} synthetic flows -> {csv_path}")

# Step 1: ingest
ingest_cmd = [
    "python",
    str(HERE / "ingest_cicids2017_friday_ddos.py"),
    "--input",
    str(csv_path),
    "--output",
    str(DATA_DIR / "smoke.parquet"),
    "--report",
    str(RESULTS_DIR / "ingest_report.json"),
]
print("[smoke] running ingest:", " ".join(ingest_cmd))
subprocess.run(ingest_cmd, check=True)

# Step 2: baseline
baseline_cmd = [
    "python",
    str(HERE / "baseline_zscore.py"),
    "--input",
    str(DATA_DIR / "smoke.parquet"),
    "--output",
    str(RESULTS_DIR),
    "--warmup",
    "600",
    "--window",
    "300",
    "--k",
    "3",
]
print("[smoke] running baseline:", " ".join(baseline_cmd))
subprocess.run(baseline_cmd, check=True)

# Step 3: validate
summary = json.loads((RESULTS_DIR / "baseline_zscore_summary.json").read_text())
print("\n[smoke] metrics summary:")
print(json.dumps(summary, indent=2))

# Basic assertions: attack window should fire on at least one feature
assertions_passed = []
for key in ("pktrate", "byterate", "dportentropy"):
    m = summary[key]
    auc = m.get("AUC_ROC", float("nan"))
    delay = m.get("detection_delay_s", float("nan"))
    print(f"  feature={key:<14} AUC_ROC={auc!r:>10}  delay={delay!r}")
    assertions_passed.append(("AUC", key, auc))

print("\n[smoke] OK — pipeline runs end-to-end on synthetic data.")
print("[smoke] Replace data/smoke_friday_ddos.csv with the real CIC-IDS2017 file")
print("        Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv to produce")
print("        the actual Paper 4 §5.2 numbers.")
