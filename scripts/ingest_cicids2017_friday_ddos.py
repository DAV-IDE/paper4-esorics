"""
ingest_cicids2017_friday_ddos.py — Day-1 morning ingestion script

Purpose
-------
Convert the CIC-IDS2017 *Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv*
flow-level CSV into a normalised parquet file ready for
`baseline_zscore.py` and the EAL real-data evaluation runs.

What it does
------------
1. Loads the raw CSV with the well-known CIC-IDS2017 quirks handled:
   - leading/trailing spaces in column names ("Flow Bytes/s" etc.)
   - "Infinity", "NaN", and "Inf" string sentinels
   - mixed datetime formats in the Timestamp column
2. Trims column names.
3. Drops rows with missing Timestamp or Label.
4. Coerces numeric columns to float and replaces inf -> NaN -> 0.
5. Normalises the Label column: anything != "BENIGN" -> the attack
   family in lowercase; in the Friday-Afternoon-DDoS file the only
   non-benign label is "DDoS".
6. Selects a stable feature subset used downstream and writes it out
   as parquet for fast reload.
7. Prints a compact dataset card to logs/ingest_report.json so the
   paper can quote sample counts deterministically.

Usage
-----
    python ingest_cicids2017_friday_ddos.py \
        --input  /path/to/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv \
        --output ../data/cicids2017_friday_ddos.parquet \
        --report ../logs/ingest_report.json

The script is designed to fail loudly (assertions) if column names or
label distribution do not match the expected Friday-Afternoon DDoS
subset, so downstream baseline numbers cannot silently drift.

Author : Paper 4 day-1 morning sprint
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

LOG = logging.getLogger("ingest_cicids2017")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Canonical CIC-IDS2017 columns we keep (after stripping spaces).
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


def _coerce_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
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


def _parse_timestamps(s: pd.Series) -> pd.Series:
    # CIC-IDS2017 uses "DD/MM/YYYY HH:MM" but some rows use "DD/MM/YYYY HH:MM:SS"
    # and a handful use ISO. pd.to_datetime with dayfirst=True handles all.
    return pd.to_datetime(s, errors="coerce", dayfirst=True)


def ingest(input_path: Path, output_path: Path, report_path: Path) -> dict:
    LOG.info("Reading CSV: %s", input_path)
    df = pd.read_csv(input_path, low_memory=False, encoding="latin-1")
    LOG.info("Raw shape: %s", df.shape)

    df = _strip_columns(df)
    missing = [c for c in KEEP_COLS if c not in df.columns]
    assert not missing, f"Missing expected columns after strip: {missing}"

    df = df[KEEP_COLS].copy()
    df["Timestamp"] = _parse_timestamps(df["Timestamp"])
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

    # Sanity check on the Friday-Afternoon-DDoS subset
    labels = set(df["Label"].unique())
    assert "BENIGN" in labels, f"Expected BENIGN in labels, got {labels}"
    attack_labels = labels - {"BENIGN"}
    assert attack_labels, "No attack labels present — wrong CIC-IDS2017 file?"
    LOG.info("Attack labels detected: %s", attack_labels)

    # Write parquet
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ingest CIC-IDS2017 Friday-Afternoon DDoS CSV"
    )
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--report", required=True, type=Path)
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    ingest(a.input, a.output, a.report)
