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


def run(df, grid, calib_modes, out_rows, tag, binnings=("per_window", "global_stable", "fd"), exclude=None):
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
                                            variants=VARIANTS, rules=RULES, raw_cal_values=x[raw_mask(t, y)], exclude=exclude)
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
    ap.add_argument("--feature", default="pkt_rate", choices=["pkt_rate", "n_bytes", "n_flows_started", "dport_entropy"])
    ap.add_argument("--start-epoch", type=int, default=None); ap.add_argument("--end-epoch", type=int, default=None)
    ap.add_argument("--tag", default=None)
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
        df["label"] = df["label_ddos"]  # primary event: DDoS LOIT (official CIC schedule)
        if a.feature != "pkt_rate":
            df["pkt_rate"] = df[a.feature].astype(float)  # sensitivity: alternative per-second feature
        if a.start_epoch is not None:
            df = df[(df.epoch_s >= a.start_epoch) & (df.epoch_s <= a.end_epoch)].copy()
        df = df.reset_index(drop=True)
        df["t"] = (df.epoch_s - df.epoch_s.iloc[0]).astype(float)
        other = ((df.label_botnet == 1) | (df.label_portscan == 1)).to_numpy()
        manifest.update({"dataset": "CIC-IDS2017 official PCAP Friday-WorkingHours.pcap, complete per-second reconstruction",
                         "input": a.input, "input_sha256": sha256(a.input), "feature": a.feature,
                         "interval_epoch": [int(df.epoch_s.iloc[0]), int(df.epoch_s.iloc[-1])], "n_seconds": len(df),
                         "ddos_seconds": int(df.label.sum()), "other_attack_seconds_excluded": int(other.sum()),
                         "exclusion_rule": "windows overlapping Botnet/PortScan seconds are excluded from calibration and from DDoS FP counts; their fires are reported as fires_excluded"})
        t, y = df.t.to_numpy(float), df.label.to_numpy()
        t_ev = float(t[y == 1].min())
        cs = np.concatenate([[0], np.cumsum(other)]); idx = {v: i for i, v in enumerate(t)}
        def clean(ts, te):  # window contains no other-attack second
            i0 = np.searchsorted(t, ts); i1 = np.searchsorted(t, te)
            return (cs[i1 + 1] - cs[i0]) == 0
        oth_start = [float(t[i]) for i in range(len(t)) if other[i] and (i == 0 or not other[i - 1])]
        t_first_other = min(oth_start) if oth_start else t_ev
        cal = {
            # primary: causal, clean benign morning before the first other attack; FP measured out-of-sample on all later benign time
            "morning_clean_causal": (t_first_other, lambda ts, te: (te < t_first_other) & clean(ts, te), lambda t_, y_: (t_ < t_first_other)),
            # sensitivity: all clean benign windows before the DDoS (pre-DDoS FP in-sample -> FP measured post-DDoS only)
            "preddos_clean_causal": (t_ev, lambda ts, te: (te < t_ev) & clean(ts, te), lambda t_, y_: (t_ < t_ev) & ~other & (y_ == 0)),
            # paper/proxy protocol: first 600 s of the series
            "warmup600": (600, lambda ts, te: (te < 600) & clean(ts, te), lambda t_, y_: (t_ < 600) & (y_ == 0)),
        }
        manifest["t_first_other_attack_s"] = t_first_other; manifest["t_event_ddos_s"] = t_ev
        run(df, ORIG_FULL, cal, rows, a.tag or "real_second", exclude=other)
    res = pd.DataFrame(rows)
    stem = a.tag or a.dataset
    res.drop(columns=["fire_times"]).to_csv(out / f"{stem}_cells.csv", index=False)
    res.to_json(out / f"{stem}_cells.json", orient="records", indent=1)
    manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["n_rows"] = len(res)
    (out / f"{stem}_manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
