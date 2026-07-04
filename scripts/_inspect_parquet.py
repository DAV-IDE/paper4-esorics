"""Inspect the TrafficLabelling parquet to confirm Timestamp presence."""
import pandas as pd, sys
p = "/home/user/workspace/paper4_repro_kit/data/Friday_TrafficLabelling.parquet"
df = pd.read_parquet(p)
print("Shape:", df.shape)
print("dtypes:")
print(df.dtypes)
print()
print("Columns (sorted):")
for c in df.columns:
    print(f"  {c!r}")
print()
# Look for timestamp-like columns
ts_cols = [c for c in df.columns if "time" in c.lower() or "stamp" in c.lower()]
print("Timestamp-like cols:", ts_cols)
if ts_cols:
    for tc in ts_cols:
        print(f"{tc}: dtype={df[tc].dtype}, min={df[tc].min()}, max={df[tc].max()}")
        print(f"   sample: {df[tc].head(3).tolist()}")
label_cols = [c for c in df.columns if "label" in c.lower()]
print("Label cols:", label_cols)
for lc in label_cols:
    print(f"{lc}: {df[lc].value_counts().to_dict()}")
