"""
build_tau_sweep_artifacts.py — Generate Table 9 (LaTeX) and heatmap figure
from tau_sweep_summary.json.

Reports the tau-recalibration study honestly:
- Per-(warmup, k, config) outcome grid
- Highlights that AUC ranking does NOT transfer to operational regime
- Two artefacts: real_tau_sweep.tex + tau_sweep_heatmap.pdf/png
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).parent.parent
SUMMARY = ROOT / "results" / "eal_real" / "tau_sweep_summary.json"
TEX_OUT = ROOT / "tables" / "real_tau_sweep.tex"
FIG_OUT_PDF = ROOT / "figures" / "tau_sweep_heatmap.pdf"
FIG_OUT_PNG = ROOT / "figures" / "tau_sweep_heatmap.png"

CONFIGS = [
    ("Shannon", 8, 4),
    ("Shannon", 16, 2),
    ("Shannon", 32, 1),
    ("Sample", 8, 4),
    ("Sample", 16, 2),
    ("Sample", 32, 1),
    ("Permutation", 8, 4),
    ("Permutation", 16, 2),
    ("Permutation", 32, 1),
]
KS = [1.5, 2.0, 2.5, 3.0]
WARMUPS = [600, 1200, 1500]

rows = json.loads(SUMMARY.read_text())


def find(warmup: int, k: float, est: str, W: int, s: int) -> dict:
    for r in rows:
        if (
            r["warmup_s"] == warmup
            and r["k"] == k
            and r["estimator"] == est
            and r["W"] == W
            and r["s"] == s
        ):
            return r
    raise KeyError((warmup, k, est, W, s))


# ---------------------------------------------------------------------------
# TABLE 9 - LaTeX (compact, one row per config, columns grouped by warmup+k)
# ---------------------------------------------------------------------------
def outcome(r: dict) -> str:
    """One-cell string: fires/FPR/delay OR 'inf' OR 'miss'."""
    if math.isinf(r["tau"]):
        return r"$\tau{=}\infty$"
    if not r["detected"]:
        return "miss"
    delay = r["detection_delay_s"]
    delay_str = f"{int(delay)}" if not math.isnan(delay) else "-"
    return f"{r['n_fires_post_warmup']}/{r['FPR_post_warmup']:.2f}/{delay_str}"


lines: list[str] = []
lines.append(r"% Table 9: tau-recalibration sweep (real CIC-IDS2017)")
lines.append(r"\begin{table*}[t]")
lines.append(r"\centering")
lines.append(
    r"\caption{Threshold recalibration sweep on real CIC-IDS2017 "
    r"Friday-Afternoon DDoS. Cells report "
    r"\emph{fires}/\emph{FPR}/\emph{delay(s)} when detected, "
    r"``miss'' when $\varepsilon_t$ never exceeds a finite $\tau$, "
    r"and ``$\tau{=}\infty$'' when the stable-phase window is too "
    r"short to estimate $(\mu,\sigma)$. AUC$_{ROC}$ is measured "
    r"once per $(W,s)$ and independent of $k$ or warmup.}"
)
lines.append(r"\label{tab:real-tau-sweep}")
lines.append(r"\resizebox{\textwidth}{!}{%")
lines.append(r"\begin{tabular}{lccc|" + "cccc|" * len(WARMUPS) + "}")
lines.append(r"\toprule")
header1 = [r"", r"", r"", r"AUC"]
for w in WARMUPS:
    header1.append(
        r"\multicolumn{4}{c|}{warmup="
        + str(w)
        + r"s ("
        + f"{w//60}"
        + r" min pre-atk)}"
    )
lines.append(" & ".join(header1) + r" \\")
header2 = [r"Estimator", r"$W$", r"$s$", r"ROC"]
for _ in WARMUPS:
    for k in KS:
        header2.append(f"$k{{=}}{k}$")
lines.append(" & ".join(header2) + r" \\")
lines.append(r"\midrule")

for est, W, s in CONFIGS:
    auc = find(WARMUPS[0], KS[0], est, W, s)["AUC_ROC"]
    row = [est, str(W), str(s), f"{auc:.3f}"]
    for w in WARMUPS:
        for k in KS:
            row.append(outcome(find(w, k, est, W, s)))
    lines.append(" & ".join(row) + r" \\")

lines.append(r"\bottomrule")
lines.append(r"\end{tabular}}")
lines.append(r"\vspace{2pt}")
lines.append(r"\begin{minipage}{\textwidth}\footnotesize")
lines.append(
    r"\emph{Reading key.} A cell shows how many post-warmup minutes "
    r"the detector fires (\emph{fires}), the false-positive rate on "
    r"pre-attack benign minutes (\emph{FPR}), and the detection "
    r"delay from first attack minute (\emph{delay}). ``$\tau{=}\infty$'' "
    r"cells indicate the number of stable-phase samples was below "
    r"the estimator's minimum (5), so $\sigma$ could not be "
    r"estimated \textemdash\ a configurability/auditability finding, "
    r"not a bug. Notice that AUC ranking does \emph{not} transfer to "
    r"the operational cells: Permutation$(32,1)$ with "
    r"AUC$=0.990$ remains inoperative because $W=32$ requires more "
    r"than 25 benign minutes; Permutation$(16,2)$ with "
    r"AUC$=0.732$ becomes operative at warmup$=$1200~s, $k=1.5$ "
    r"(fires=8, FPR=0.04, delay=60~s), outperforming the baseline "
    r"Pareto point."
)
lines.append(r"\end{minipage}")
lines.append(r"\end{table*}")

TEX_OUT.write_text("\n".join(lines) + "\n")
print(f"[table9] wrote {TEX_OUT}")


# ---------------------------------------------------------------------------
# HEATMAP FIGURE - 3 subplots (one per warmup), configs on Y, k on X, colored
# by detection delay; annotations for FPR and 'inf'/'miss'
# ---------------------------------------------------------------------------
fig, axes = plt.subplots(
    1, 3, figsize=(14.0, 5.6), dpi=150, gridspec_kw={"wspace": 0.42}
)

cfg_labels = [f"{e[:4]}({W},{s})" for e, W, s in CONFIGS]

# Colormap: yellow (fast) -> orange (slow). Cap at 1200s so the darkest
# observed cells stay legible for BLACK text; longer delays (3060s, 3180s)
# are clipped to the same shade and labeled explicitly in the cell text.
cmap = plt.cm.YlOrRd
delay_vmax = 1200  # visual cap; actual delays annotated in each cell

for ax, warmup in zip(axes, WARMUPS):
    grid = np.full((len(CONFIGS), len(KS)), np.nan)
    annot = np.full((len(CONFIGS), len(KS)), "", dtype=object)
    for i, (est, W, s) in enumerate(CONFIGS):
        for j, k in enumerate(KS):
            r = find(warmup, k, est, W, s)
            if math.isinf(r["tau"]):
                grid[i, j] = np.nan
                annot[i, j] = r"$\tau$=$\infty$"
            elif not r["detected"]:
                grid[i, j] = np.nan
                annot[i, j] = "miss"
            else:
                # Clip color intensity so text stays legible, but display real delay
                grid[i, j] = min(r["detection_delay_s"], delay_vmax)
                annot[i, j] = (
                    f"{r['FPR_post_warmup']:.2f}\n{int(r['detection_delay_s'])}s"
                )

    ax.set_facecolor("#d5d5d5")  # darker grey so miss/tau=inf text stands out
    im = ax.imshow(grid, cmap=cmap, vmin=0, vmax=delay_vmax, aspect="auto")
    ax.set_xticks(range(len(KS)))
    ax.set_xticklabels([f"k={k}" for k in KS], fontsize=10)
    ax.set_yticks(range(len(CONFIGS)))
    ax.set_yticklabels(cfg_labels, fontsize=9)
    ax.set_title(
        f"warmup = {warmup}s ({warmup//60} min pre-attack)", fontsize=10.5, pad=8
    )

    # Annotate each cell
    for i in range(len(CONFIGS)):
        for j in range(len(KS)):
            val = grid[i, j]
            if math.isnan(val):
                # miss / inf: dark grey text on medium grey background - strong contrast
                ax.text(
                    j,
                    i,
                    annot[i, j],
                    ha="center",
                    va="center",
                    fontsize=8.5,
                    color="#222",
                    fontweight="bold",
                )
            else:
                # detected: black text on YlOrRd (capped at 1200s -> orange max)
                ax.text(
                    j,
                    i,
                    annot[i, j],
                    ha="center",
                    va="center",
                    fontsize=8.5,
                    color="black",
                    fontweight="bold",
                )

    ax.set_xticks(np.arange(-0.5, len(KS)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(CONFIGS)), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", length=0)

# Shared colorbar - use a dedicated axes so numbers and label do not overlap
fig.subplots_adjust(left=0.06, right=0.90, top=0.82, bottom=0.14, wspace=0.42)
cbar_ax = fig.add_axes((0.925, 0.14, 0.014, 0.68))
cbar = fig.colorbar(im, cax=cbar_ax, extend="max")
cbar.ax.tick_params(labelsize=9)
cbar.set_label(
    "Detection delay (s) \u2014 color capped at 1200s; "
    "actual delay annotated in cell",
    fontsize=9,
    labelpad=10,
)

fig.suptitle(
    "Tau-recalibration sweep on real CIC-IDS2017 Friday DDoS\n"
    "(cells: FPR / delay;  grey: miss;  \u03c4=\u221e: too few stable-phase samples)",
    fontsize=11,
    y=0.965,
)
plt.savefig(FIG_OUT_PDF)
plt.savefig(FIG_OUT_PNG)
print(f"[fig] wrote {FIG_OUT_PDF}")
print(f"[fig] wrote {FIG_OUT_PNG}")


# ---------------------------------------------------------------------------
# Console summary for the paper draft
# ---------------------------------------------------------------------------
print("\n=== Detection matrix (detected / 9 configs) ===")
print("             " + "   ".join(f"k={k}" for k in KS))
for w in WARMUPS:
    cells = []
    for k in KS:
        det = sum(
            1 for r in rows if r["warmup_s"] == w and r["k"] == k and r["detected"]
        )
        cells.append(f"{det}/9")
    print(f"  warmup={w:4d}s  " + "   ".join(f"{c:>4s}" for c in cells))

print("\n=== Best operating point (lowest FPR, delay <= 300s) ===")
best = None
for r in rows:
    if (
        r["detected"]
        and r["detection_delay_s"] <= 300
        and (best is None or r["FPR_post_warmup"] < best["FPR_post_warmup"])
    ):
        best = r
if best:
    print(
        f"  {best['estimator']}(W={best['W']},s={best['s']})  "
        f"warmup={best['warmup_s']}s  k={best['k']}  "
        f"AUC={best['AUC_ROC']:.3f}  "
        f"FPR={best['FPR_post_warmup']:.3f}  "
        f"delay={best['detection_delay_s']:.0f}s  "
        f"fires={best['n_fires_post_warmup']}"
    )
