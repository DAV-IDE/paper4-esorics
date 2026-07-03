"""
ingest_real.py — Real CIC-IDS2017 Friday-Afternoon-DDoS ingestion driver.

Wraps ingest_cicids2017_friday_ddos.ingest() but accepts either the
authoritative CSV (Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv from
TrafficLabelling) or an equivalent parquet with the same schema
(Timestamp + all CICFlowMeter columns present).

Deterministic behaviour: fail loudly if the file lacks the expected
columns or label distribution, so downstream detector numbers cannot
silently drift from the paper's claimed source.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

LOG = logging.getLogger("ingest_real")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Columns we ultimately keep for downstream baseline_zscore.py / eal_factorial.py
KEEP_COLS = [
    "Timestamp",
    "Flow Duration",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Flow Bytes/s",
    "Flow Packets/s",
    "Destination Port",
    "Protocol",
    "Label",
]


def _strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    return df


def _coerce_numeric(df: pd.DataFrame, cols):
    for c in cols:
        if c in df.columns:
            df[c] = (
                df[c]
                .replace({"Infinity": np.inf, "-Infinity": -np.inf, "NaN": np.nan})
                .astype(str)
                .str.replace(",", ".", regex=False)
            )
            df[c] = pd.to_numeric(df[c], errors="coerce")
            df[c] = df[c].replace([np.inf, -np.inf], np.nan)
    return df


def load(input_path: Path) -> pd.DataFrame:
    LOG.info("Loading %s", input_path)
    if input_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(input_path)
    else:
        df = pd.read_csv(input_path, low_memory=False, encoding="latin-1")
    LOG.info("Raw shape: %s", df.shape)
    df = _strip_columns(df)
    return df


def ingest(input_path: Path, output_path: Path, report_path: Path) -> dict:
    df = load(input_path)

    missing = [c for c in KEEP_COLS if c not in df.columns]
    assert not missing, (
        f"Missing expected columns after strip: {missing}. "
        f"You likely have the MachineLearningCSV variant (no Timestamp). "
        f"Use the TrafficLabelling / GeneratedLabelledFlows variant instead."
    )

    df = df[KEEP_COLS].copy()

    # Timestamp handling (dayfirst for the DD/MM/YYYY CSV; parquet already datetime)
    if not np.issubdtype(df["Timestamp"].dtype, np.datetime64):
        df["Timestamp"] = pd.to_datetime(
            df["Timestamp"], errors="coerce", dayfirst=True
        )
    df = df.dropna(subset=["Timestamp", "Label"]).reset_index(drop=True)

    df = _coerce_numeric(
        df,
        [
            "Flow Duration",
            "Total Fwd Packets",
            "Total Backward Packets",
            "Flow Bytes/s",
            "Flow Packets/s",
            "Destination Port",
            "Protocol",
        ],
    )
    df = df.dropna(subset=["Flow Bytes/s", "Flow Packets/s"]).reset_index(drop=True)

    df["Label"] = df["Label"].astype(str).str.strip()
    label_dist_raw = df["Label"].value_counts().to_dict()
    LOG.info("Label distribution: %s", label_dist_raw)

    labels = set(df["Label"].unique())
    assert "BENIGN" in labels, f"Expected BENIGN in labels, got {labels}"
    attack_labels = labels - {"BENIGN"}
    assert attack_labels, "No attack labels present — wrong CIC-IDS2017 file?"
    LOG.info("Attack labels detected: %s", attack_labels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    LOG.info("Wrote parquet: %s (shape=%s)", output_path, df.shape)

    report = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "n_flows": int(len(df)),
        "n_benign": int((df["Label"] == "BENIGN").sum()),
        "n_attack": int((df["Label"] != "BENIGN").sum()),
        "attack_labels": sorted(attack_labels),
        "label_distribution_raw": label_dist_raw,
        "timestamp_min": str(df["Timestamp"].min()),
        "timestamp_max": str(df["Timestamp"].max()),
        "duration_seconds": float(
            (df["Timestamp"].max() - df["Timestamp"].min()).total_seconds()
        ),
        "columns_kept": KEEP_COLS,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str))
    LOG.info("Wrote report: %s", report_path)
    return report


def parse_args():
    p = argparse.ArgumentParser(
        description="Ingest real CIC-IDS2017 Friday-Afternoon DDoS (CSV or parquet)"
    )
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    ingest(a.input, a.output, a.report)
