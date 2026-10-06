"""STEP 1 / 2 / 5 / 6 on single (non-generative or fixed-seed) streams.

  --dataset proxy        : CIC-IDS2017-aligned proxy, seed 20260606 (per second)
  --dataset real_minute  : PR #3 minute aggregation of the TrafficLabelling file (analysis A)
  --dataset real_second  : per-second series reconstructed from the official PCAP (analysis C)
                           (input CSV produced by pcap_to_per_second.py)
Writes <out>/<dataset>_cells.csv (+ .json with fire times) and a run manifest.
"""
import argparse, json, hashlib, platform, subprocess, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
from eal_core import EventSpec
from runner import evaluate_cell, ESTIMATORS
from datasets import proxy_per_second, real_minute

VARIANTS = ("U_raw", "S_norm", "B_norm", "B_fixed015")
RULES = ("mu_sigma", "q997", "mad")
ORIG_DIAG = [(64, 8), (128, 4), (256, 1)]
ORIG_FULL = [(W, s) for W in (64, 128, 256) for s in (1, 4, 8)]
MIN_GRID = [(8, 4), (16, 2), (32, 1)]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git_head(repo):
    try:
        return subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def event_from_labels(df, eval_start):
    t, y = df["t"].to_numpy(), df["label"].to_numpy()
    return EventSpec(t_event=float(t[y == 1].min()), t_attack_end=float(t[y == 1].max()),
                     t_eval_start=float(eval_start), t_series_end=float(t.max()), dt=float(np.median(np.diff(t))))


def run(df, grid, calib_modes, out_rows, tag, binnings=("per_window", "global_stable", "fd")):
    x, t, y = df["pkt_rate"].to_numpy(float), df["t"].to_numpy(float), df["label"].to_numpy(int)
    t_ev, t_ae = float(t[y == 1].min()), float(t[y == 1].max())
    for cm_name, (eval_start, filt, raw_mask) in calib_modes.items():
        ev = event_from_labels(df, eval_start)
        for est in ESTIMATORS:
            for (W, s) in grid:
                for b in (binnings if est == "Shannon" else ("none",)):
                    t0 = time.time()
                    rows, _ = evaluate_cell(x, t, y, ev, est, W, s, cal_window_filter=filt,
                                            binning=b if est == "Shannon" else "per_window",
                                            variants=VARIANTS, rules=RULES, raw_cal_values=x[raw_mask(t, y)])
                    for r in rows:
                        r.update({"dataset": tag, "calibration": cm_name, "binning": b, "runtime_s": round(time.time() - t0, 3)})
                    out_rows.extend(rows)
                    print(f"[{tag}] {cm_name} {est} W={W} s={s} bin={b} done ({time.time()-t0:.1f}s)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=["proxy", "real_minute", "real_second"])
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20260606)
    ap.add_argument("--full-grid", action="store_true")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    manifest = {"command": " ".join(sys.argv), "python": platform.python_version(), "numpy": np.__version__,
                "pandas": pd.__version__, "commit": git_head(str(Path(__file__).resolve().parents[2])),
                "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rows = []
    if a.dataset == "proxy":
        df = proxy_per_second(a.seed)
        manifest.update({"dataset": "CIC-IDS2017-aligned proxy (synthetic flows)", "seed": a.seed,
                         "series_sha256": hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()})
        cal = {"warmup600": (600, lambda ts, te: te < 600, lambda t, y: (t < 600) & (y == 0))}
        run(df, ORIG_FULL if a.full_grid else ORIG_DIAG, cal, rows, "proxy")
    elif a.dataset == "real_minute":
        df = real_minute(a.input)
        manifest.update({"dataset": "CIC-IDS2017 Friday-Afternoon-DDoS TrafficLabelling, HF mirror bvsam/cic-ids-2017, minute aggregation",
                         "input": a.input, "input_sha256": sha256(a.input), "n_minutes": len(df), "attack_minutes": int(df.label.sum())})
        t, y = df.t.to_numpy(), df.label.to_numpy()
        t_ev, t_ae = float(t[y == 1].min()), float(t[y == 1].max())
        cal = {
            "pr3_warmup600": (600, lambda ts, te: te < 600, lambda t, y: (t < 600) & (y == 0)),
            "preattack_causal": (t_ev, lambda ts, te: te < t_ev, lambda t, y: (t < t_ev)),
            "post_retrospective_NONCAUSAL": (600, lambda ts, te: ts > t_ae, lambda t, y: (t > t_ae)),
        }
        run(df, MIN_GRID + ORIG_DIAG, cal, rows, "real_minute")
    else:
        df = pd.read_csv(a.input)
        df["label"] = df["label_schedule"]  # official CIC schedule; label_packets kept for audit
        manifest.update({"dataset": "CIC-IDS2017 official PCAP, per-second reconstruction", "input": a.input, "input_sha256": sha256(a.input)})
        t, y = df.t.to_numpy(), df.label.to_numpy()
        cal = {"warmup600": (600, lambda ts, te: te < 600, lambda t, y: (t < 600) & (y == 0))}
        run(df, ORIG_FULL, cal, rows, "real_second")
    res = pd.DataFrame(rows)
    res.drop(columns=["fire_times"]).to_csv(out / f"{a.dataset}_cells.csv", index=False)
    res.to_json(out / f"{a.dataset}_cells.json", orient="records", indent=1)
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["n_rows"] = len(res)
    (out / f"{a.dataset}_manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
