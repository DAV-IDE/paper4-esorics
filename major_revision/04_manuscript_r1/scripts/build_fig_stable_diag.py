#!/usr/bin/env python3
"""I-15a: compact stable-phase diagnostic figure (histogram, normal Q-Q, ACF) for the manuscript.
Plotting only: reads the frozen per-window entropy of the stable scenario
(results/03_synthetic_multiseed/synthetic_stable_window_entropy.json, seed 42, configuration C1)
and reproduces the plotting logic of mr/analysis_stats.py (frozen PNGs results/04_stats/figures/stable_*_seed42.png,
which show all five configurations). No value is recomputed beyond what those PNGs already display."""
import json, os, hashlib
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy import stats
from statsmodels.tsa.stattools import acf
HERE = os.path.dirname(os.path.abspath(__file__)); M = os.path.dirname(HERE)
RES = os.path.join(os.path.dirname(M), "03_r1_experiments", "results")
src = os.path.join(RES, "03_synthetic_multiseed/synthetic_stable_window_entropy.json")
sv = json.load(open(src)); CID, W, S = "C1", 128, 1
EST = [("Shannon", "Shannon"), ("Sample", "Sample"), ("Permutation", "Permutation")]
plt.rcParams.update({"font.size": 7})
fig, axs = plt.subplots(3, 3, figsize=(7.0, 6.2))
for j, (est, lab) in enumerate(EST):
    H = np.asarray(sv["42"][f"{CID}|{est}"], float); H = H[np.isfinite(H)]
    ax = axs[0, j]; ax.hist(H, bins=40, density=True, color="#4a7ab0", alpha=.8)
    xs = np.linspace(H.min(), H.max(), 200); ax.plot(xs, stats.norm.pdf(xs, H.mean(), H.std()), "k-", lw=.8, label="normal fit")
    ax.axvline(H.mean() + 3 * H.std(), color="r", lw=.9, label=r"$\mu+3\sigma$")
    ax.axvline(np.quantile(H, .997), color="g", ls="--", lw=.9, label=r"$\hat{q}_{0.997}$")
    med = np.median(H); ax.axvline(med + 3 * 1.4826 * np.median(np.abs(H - med)), color="m", ls=":", lw=.9, label="MAD rule")
    ax.set_title(f"{lab} entropy: histogram"); ax.set_xlabel(r"$H_k$")
    if j == 0: ax.legend(fontsize=5.5, loc="upper left")
    ax = axs[1, j]; (osm, osr), (sl, ic, _) = stats.probplot(H, dist="norm")
    ax.plot(osm, osr, ".", ms=1.5, color="#4a7ab0"); ax.plot(osm, sl * osm + ic, "r-", lw=.8)
    ax.set_title("normal Q-Q"); ax.set_xlabel("theoretical quantile"); ax.set_ylabel("ordered $H_k$")
    ax = axs[2, j]; ac = acf(H, nlags=min(300, H.size - 1), fft=True); ax.plot(ac, lw=.9); ax.axhline(0, color="k", lw=.5)
    ax.axvline(W // S, color="r", ls="--", lw=.8, label="lag $W/s$"); ax.set_title("autocorrelation"); ax.set_xlabel("lag (windows)")
    if j == 0: ax.legend(fontsize=5.5)
fig.tight_layout()
out = os.path.join(M, "figures", "stable_diag_C1_seed42.pdf"); fig.savefig(out); fig.savefig(out.replace(".pdf", ".png"), dpi=150)
print(out, hashlib.sha256(open(src, "rb").read()).hexdigest()[:16])
