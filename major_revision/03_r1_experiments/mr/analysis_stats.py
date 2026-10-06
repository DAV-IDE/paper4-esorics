"""STEP 3 statistics on the multi-seed outputs (synthetic + proxy) and the
real-minute bootstrap (robustness only).

Outputs in --out:
  cell_summary_synthetic.csv / cell_summary_proxy.csv   per-cell descriptive stats + CIs
  legacy_published_multiseed_synthetic.csv              published pipeline across 30 seeds
  stable_distribution_diagnostics.csv                   skew, kurtosis, Shapiro, ACF per cell/seed (summarised)
  threshold_rule_comparison.csv                         out-of-sample exceedance per rule
  factorial_tests.json                                  assumption checks, Friedman/Cochran/Wilcoxon(Holm)
  gating_comparison.csv                                 U_raw vs S_norm vs B_norm paired tests
  real_minute_bootstrap_summary.csv                     ROBUSTNESS ONLY
  figures/*.png
Notes: 30 independent seeds (published seed 42 / 20260606 reported separately,
not pooled).  Undetected runs are kept: detection rate uses all seeds; delay
statistics use detected seeds and are always reported with n_detected.  For
rank tests non-detection is coded as +inf delay (worst rank).
"""
import argparse, json, math, warnings
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore", category=RuntimeWarning)
CFG_ORDER = ["C1", "C2", "C3", "C4", "C5"]
EST = ["Shannon", "Sample", "Permutation"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def boot_ci_median(v, B=2000, seed=0):
    v = np.asarray(v, float)
    if v.size < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    m = np.median(rng.choice(v, size=(B, v.size), replace=True), axis=1)
    return tuple(np.percentile(m, [2.5, 97.5]))


def describe(g):
    n = len(g); det = g["detected"].astype(bool); k = int(det.sum())
    dl = g.loc[det, "delay"].astype(float).to_numpy()
    lo, hi = wilson(k, n)
    o = {"n_seeds": n, "n_detected": k, "det_rate": k / n if n else np.nan, "det_rate_ci_lo": lo, "det_rate_ci_hi": hi}
    if dl.size:
        q1, q3 = np.percentile(dl, [25, 75])
        o.update(delay_median=float(np.median(dl)), delay_q1=q1, delay_q3=q3, delay_iqr=q3 - q1, delay_mean=float(dl.mean()),
                 delay_sd=float(dl.std(ddof=1)) if dl.size > 1 else np.nan)
        if dl.size > 1:
            se = dl.std(ddof=1) / math.sqrt(dl.size); t = stats.t.ppf(0.975, dl.size - 1)
            o.update(delay_mean_ci_lo=dl.mean() - t * se, delay_mean_ci_hi=dl.mean() + t * se)
        o["delay_median_ci_lo"], o["delay_median_ci_hi"] = boot_ci_median(dl)
    for c in ["FPA_rate_pre", "FPR_window", "FP_per_1000_samples", "FP_per_hour", "fires_pre", "fires_attack", "fires_post",
              "AUCROC_window", "AUCPR_window", "AUCROC_persample", "AUCPR_persample", "tau"]:
        if c in g:
            v = pd.to_numeric(g[c], errors="coerce").to_numpy(float); v = v[np.isfinite(v)]
            if v.size:
                o[f"{c}_median"] = float(np.median(v)); o[f"{c}_mean"] = float(v.mean())
                if v.size > 1:
                    se = v.std(ddof=1) / math.sqrt(v.size); t = stats.t.ppf(0.975, v.size - 1)
                    o[f"{c}_ci_lo"], o[f"{c}_ci_hi"] = v.mean() - t * se, v.mean() + t * se
    return pd.Series(o)


def summarize(df, keys):
    return pd.DataFrame([{**dict(zip(keys, k if isinstance(k, tuple) else (k,))), **describe(g).to_dict()} for k, g in df.groupby(keys)])


def holm(p):
    p = np.asarray(p, float); o = np.argsort(p); m = len(p); adj = np.empty(m); run = 0
    for i, j in enumerate(o):
        run = max(run, min(1, (m - i) * p[j])); adj[j] = run
    return adj


def cochran_q(X):
    X = np.asarray(X, int); k = X.shape[1]; T = X.sum(0); R = X.sum(1); N = X.sum()
    den = k * N - (R ** 2).sum()
    if den == 0:
        return np.nan, np.nan
    Q = (k - 1) * (k * (T ** 2).sum() - N ** 2) / den
    return float(Q), float(stats.chi2.sf(Q, k - 1))


def factorial(df, cell_cols, label):
    """df: one row per (seed, cell) for one scenario/primary pipeline."""
    out = {"label": label}
    d = df.copy(); d["cell"] = d[cell_cols].astype(str).agg("|".join, axis=1)
    d["delay_c"] = np.where(d.detected.astype(bool), d.delay.astype(float), np.inf)
    P = d.pivot_table(index="seed", columns="cell", values="delay_c", aggfunc="first")
    D = d.pivot_table(index="seed", columns="cell", values="detected", aggfunc="first").astype(int)
    out["n_seeds"], out["n_cells"] = int(P.shape[0]), int(P.shape[1])
    # ANOVA assumption checks on detected-only finite delays
    fin = d[np.isfinite(d.delay_c)]
    try:
        import statsmodels.formula.api as smf
        if fin[cell_cols[0]].nunique() > 1 and fin[cell_cols[1]].nunique() > 1 and len(fin) > 10:
            f = f"delay_c ~ C({cell_cols[0]}) * C({cell_cols[1]})"
            m = smf.ols(f, data=fin).fit()
            res = m.resid.to_numpy()
            sh = stats.shapiro(res if res.size <= 5000 else np.random.default_rng(0).choice(res, 5000, replace=False))
            groups = [g.delay_c.to_numpy() for _, g in fin.groupby("cell") if len(g) > 1]
            lev = stats.levene(*groups) if len(groups) > 1 else None
            out["anova_assumptions"] = {"shapiro_resid_W": float(sh.statistic), "shapiro_resid_p": float(sh.pvalue),
                                        "levene_W": float(lev.statistic) if lev else None, "levene_p": float(lev.pvalue) if lev else None,
                                        "n_detected_rows": int(len(fin)), "censored_rows_excluded": int((~np.isfinite(d.delay_c)).sum())}
            ok = sh.pvalue > 0.05 and (lev is None or lev.pvalue > 0.05) and out["anova_assumptions"]["censored_rows_excluded"] == 0
            out["anova_used"] = bool(ok)
            if not ok:
                out["anova_note"] = "ANOVA NOT used: residual normality and/or homoscedasticity rejected, or censoring present"
    except Exception as e:
        out["anova_error"] = str(e)
    Pf = P.replace(np.inf, 1e12)
    if P.shape[1] > 2 and P.shape[0] > 2:
        fr = stats.friedmanchisquare(*[Pf[c].to_numpy() for c in Pf.columns])
        n, k = Pf.shape
        out["friedman_chi2"], out["friedman_p"], out["kendall_W"] = float(fr.statistic), float(fr.pvalue), float(fr.statistic / (n * (k - 1)))
        q, p = cochran_q(D.to_numpy())
        out["cochran_q"], out["cochran_p"] = q, p
        ranks = Pf.rank(axis=1).mean().sort_values()
        out["mean_rank_by_cell"] = {k_: float(v) for k_, v in ranks.items()}
    # post-hoc: estimators within each level of the second factor
    post = []
    for lvl, g in d.groupby(cell_cols[1]):
        Pe = g.pivot_table(index="seed", columns=cell_cols[0], values="delay_c", aggfunc="first").replace(np.inf, 1e12)
        pairs, ps = [], []
        for a_, b_ in combinations(Pe.columns, 2):
            x, y = Pe[a_].to_numpy(), Pe[b_].to_numpy()
            if np.all(x == y):
                p = 1.0
            else:
                p = float(stats.wilcoxon(x, y, zero_method="zsplit").pvalue)
            pairs.append((a_, b_, float(np.median(x - y)))); ps.append(p)
        for (a_, b_, md), p, pa in zip(pairs, ps, holm(ps) if ps else []):
            post.append({"level": str(lvl), "a": a_, "b": b_, "median_diff_delay(a-b)": md, "p": p, "p_holm": float(pa)})
    out["posthoc_wilcoxon_holm"] = post
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--res", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(); R = Path(a.res); out = Path(a.out); (out / "figures").mkdir(parents=True, exist_ok=True)
    rd = lambda p: pd.read_csv(p, keep_default_na=False, na_values=[""], low_memory=False)
    syn = rd(R / "03_synthetic_multiseed/synthetic_multiseed_long.csv.gz")
    syn_ind = syn[~syn.published_seed]
    # ---------------- legacy published pipeline across seeds ----------------
    leg = syn_ind[syn_ind.pipeline == "legacy_published"].copy()
    leg["detected"] = np.isfinite(leg.delay.astype(float))
    legs = leg.groupby(["scenario", "cfg", "est"]).apply(lambda g: pd.Series({
        **describe(g).reindex(["n_seeds", "n_detected", "det_rate", "det_rate_ci_lo", "det_rate_ci_hi", "delay_median", "delay_q1", "delay_q3", "delay_mean", "delay_sd", "delay_median_ci_lo", "delay_median_ci_hi"]).to_dict(),
        "fp_pre_median": g.fp.median(), "fp_pre_mean": g.fp.mean(), "fp_pre_sd": g.fp.std()}), include_groups=False).reset_index()
    pub42 = syn[(syn.published_seed) & (syn.pipeline == "legacy_published")][["scenario", "cfg", "est", "delay", "fp"]].rename(columns={"delay": "seed42_delay", "fp": "seed42_fp"})
    legs = legs.merge(pub42, on=["scenario", "cfg", "est"], how="left")
    legs.to_csv(out / "legacy_published_multiseed_synthetic.csv", index=False)
    # dominance claim check: (Shannon,C2) vs others on shock (published Table 4 selection)
    # ---------------- r1 cell summaries ----------------
    r1 = syn_ind[syn_ind.pipeline == "r1"]
    keys = ["scenario", "cfg", "W", "s", "est", "binning", "variant", "rule"]
    cs = summarize(r1, keys)
    cs.to_csv(out / "cell_summary_synthetic.csv", index=False)
    prx = rd(R / "03_proxy_multiseed/proxy_multiseed_long.csv.gz")
    prx_ind = prx[~prx.published_seed]
    pk = ["W", "s", "est", "binning", "variant", "rule"]
    pr1 = prx_ind[prx_ind.pipeline == "r1"]
    pcs = summarize(pr1, pk)
    pcs.to_csv(out / "cell_summary_proxy.csv", index=False)
    pl = prx_ind[prx_ind.pipeline == "legacy_published"].copy()
    pl["delay"] = pl.detection_delay_s; pl["FPR_window"] = pl.FPR_post_warmup
    pls = summarize(pl, ["W", "s", "est"])
    pls.to_csv(out / "legacy_published_multiseed_proxy.csv", index=False)
    # ---------------- stable-phase distribution diagnostics ----------------
    sv = json.load(open(R / "03_synthetic_multiseed/synthetic_stable_window_entropy.json"))
    from statsmodels.tsa.stattools import acf
    from datasets import SYN_CONFIGS
    drows = []
    for seed, cells in sv.items():
        for key, H in cells.items():
            cid, est = key.split("|"); W, s = SYN_CONFIGS[cid]
            H = np.asarray(H, float); H = H[np.isfinite(H)]
            if H.size < 10:
                continue
            step = max(1, W // s)  # non-overlapping thinning for Shapiro
            thin = H[::step]
            ac = acf(H, nlags=min(step, H.size - 1), fft=True)
            for stat_name, v in (("H", H), ("absdev", np.abs(H - H.mean()) / max(1e-9, abs(H.mean())))):
                vt = v[::step]
                drows.append({"seed": int(seed), "published_seed": seed == "42", "cfg": cid, "est": est, "statistic": stat_name, "n": v.size,
                              "skew": float(stats.skew(v)), "excess_kurtosis": float(stats.kurtosis(v)),
                              "shapiro_p_thinned": float(stats.shapiro(vt).pvalue) if vt.size >= 3 else np.nan, "n_thinned": int(vt.size),
                              "acf_lag1": float(ac[1]), "acf_lag_W_over_s": float(ac[min(step, len(ac) - 1)]),
                              "emp_exceed_mu3sigma_insample": float(np.mean(v > v.mean() + 3 * v.std())),
                              "q997_minus_mu3sigma_in_sd": float((np.quantile(v, 0.997) - (v.mean() + 3 * v.std())) / max(v.std(), 1e-12))})
    dd = pd.DataFrame(drows)
    dds = dd[~dd.published_seed].groupby(["cfg", "est", "statistic"]).agg(
        skew_median=("skew", "median"), skew_q1=("skew", lambda x: x.quantile(.25)), skew_q3=("skew", lambda x: x.quantile(.75)),
        kurt_median=("excess_kurtosis", "median"), shapiro_reject_rate=("shapiro_p_thinned", lambda x: float((x < 0.05).mean())),
        acf1_median=("acf_lag1", "median"), acfW_median=("acf_lag_W_over_s", "median"),
        exceed_mu3s_median=("emp_exceed_mu3sigma_insample", "median"), q997_vs_mu3s_sd_median=("q997_minus_mu3sigma_in_sd", "median")).reset_index()
    dds.to_csv(out / "stable_distribution_diagnostics.csv", index=False)
    # figures for seed 42 (published) — histogram, Q-Q, ACF
    for kind in ("hist", "qq", "acf"):
        fig, axs = plt.subplots(5, 3, figsize=(11, 14))
        for i, cid in enumerate(CFG_ORDER):
            for j, est in enumerate(EST):
                ax = axs[i, j]; H = np.asarray(sv["42"][f"{cid}|{est}"], float); H = H[np.isfinite(H)]
                W, s = SYN_CONFIGS[cid]
                if kind == "hist":
                    ax.hist(H, bins=40, density=True, color="#4a7ab0", alpha=.8)
                    xs = np.linspace(H.min(), H.max(), 200); ax.plot(xs, stats.norm.pdf(xs, H.mean(), H.std()), "k-", lw=1)
                    ax.axvline(H.mean() + 3 * H.std(), color="r", lw=1, label="mu+3sd"); ax.axvline(np.quantile(H, .997), color="g", ls="--", lw=1, label="q99.7")
                    med = np.median(H); ax.axvline(med + 3 * 1.4826 * np.median(np.abs(H - med)), color="m", ls=":", lw=1, label="MAD")
                    if i == 0 and j == 0: ax.legend(fontsize=6)
                elif kind == "qq":
                    stats.probplot(H, dist="norm", plot=ax); ax.get_lines()[0].set_markersize(2); ax.set_title("")
                else:
                    ac = acf(H, nlags=min(300, H.size - 1), fft=True); ax.plot(ac, lw=1); ax.axhline(0, color="k", lw=.5)
                    ax.axvline(W // s, color="r", ls="--", lw=.8)
                ax.set_title(f"{cid} (W={W},s={s}) {est}", fontsize=8); ax.tick_params(labelsize=6)
        fig.suptitle(f"Stable scenario, seed 42 (published), window entropy H: {kind}", fontsize=10)
        fig.tight_layout(); fig.savefig(out / "figures" / f"stable_{kind}_seed42.png", dpi=110); plt.close(fig)
    # ---------------- threshold-rule comparison ----------------
    th = r1[(r1.binning.isin(["per_window", "none"])) & (r1.variant.isin(["U_raw", "B_norm"]))]
    hold = th[th.scenario == "stable_holdout"].groupby(["cfg", "est", "variant", "rule"]).agg(
        oos_exceed_median=("FPA_rate_pre", "median"), oos_exceed_q1=("FPA_rate_pre", lambda x: x.quantile(.25)),
        oos_exceed_q3=("FPA_rate_pre", lambda x: x.quantile(.75)), oos_exceed_mean=("FPA_rate_pre", "mean"),
        tau_median=("tau", "median")).reset_index()
    det = th[th.scenario != "stable_holdout"].groupby(["scenario", "cfg", "est", "variant", "rule"]).apply(
        lambda g: pd.Series({"det_rate": g.detected.astype(bool).mean(), "delay_median": g.loc[g.detected.astype(bool), "delay"].median(),
                             "FPA_rate_pre_median": g.FPA_rate_pre.median()}), include_groups=False).reset_index()
    hold.to_csv(out / "threshold_rule_comparison_holdout.csv", index=False)
    det.to_csv(out / "threshold_rule_comparison_detection.csv", index=False)
    # ---------------- gating comparison (paired) ----------------
    gc = []
    base = r1[r1.binning.isin(["per_window", "none"]) & (r1.rule == "mu_sigma") & (r1.scenario != "stable_holdout")]
    for (sc, cid, est), g in base.groupby(["scenario", "cfg", "est"]):
        P = g.pivot_table(index="seed", columns="variant", values="detected", aggfunc="first").astype(bool)
        Dl = g.assign(dc=np.where(g.detected.astype(bool), g.delay.astype(float), 1e12)).pivot_table(index="seed", columns="variant", values="dc", aggfunc="first")
        F = g.pivot_table(index="seed", columns="variant", values="FPA_rate_pre", aggfunc="first")
        row = {"dataset": "synthetic", "scenario": sc, "cell": f"{cid}", "est": est}
        for v in ["U_raw", "S_norm", "B_norm", "legacy_diff"]:
            if v in P:
                row[f"det_rate_{v}"] = P[v].mean(); row[f"FPA_median_{v}"] = F[v].median()
                dv = g[(g.variant == v) & g.detected.astype(bool)].delay
                row[f"delay_median_{v}"] = dv.median() if len(dv) else np.nan
        row["U_equals_S_all_seeds"] = bool((P["U_raw"] == P["S_norm"]).all() and np.allclose(Dl["U_raw"], Dl["S_norm"]))
        b, c = int((P.B_norm & ~P.U_raw).sum()), int((~P.B_norm & P.U_raw).sum())
        row["mcnemar_B_vs_U_b"], row["mcnemar_B_vs_U_c"] = b, c
        row["mcnemar_p_exact"] = float(stats.binomtest(min(b, c), b + c, .5).pvalue) if b + c else 1.0
        x, y = Dl["B_norm"].to_numpy(), Dl["U_raw"].to_numpy()
        row["wilcoxon_delay_B_vs_U_p"] = float(stats.wilcoxon(x, y, zero_method="zsplit").pvalue) if not np.all(x == y) else 1.0
        fx, fy = F["B_norm"].to_numpy(), F["U_raw"].to_numpy()
        row["wilcoxon_FPA_B_vs_U_p"] = float(stats.wilcoxon(fx, fy, zero_method="zsplit").pvalue) if not np.all(fx == fy) else 1.0
        gc.append(row)
    pb = pr1[pr1.binning.isin(["per_window", "none"]) & (pr1.rule == "mu_sigma")]
    for (W, s, est), g in pb.groupby(["W", "s", "est"]):
        P = g.pivot_table(index="seed", columns="variant", values="detected", aggfunc="first").astype(bool)
        Dl = g.assign(dc=np.where(g.detected.astype(bool), g.delay.astype(float), 1e12)).pivot_table(index="seed", columns="variant", values="dc", aggfunc="first")
        F = g.pivot_table(index="seed", columns="variant", values="FPA_rate_pre", aggfunc="first")
        A = g.pivot_table(index="seed", columns="variant", values="AUCROC_persample", aggfunc="first")
        row = {"dataset": "proxy", "scenario": "ddos", "cell": f"W{W}s{s}", "est": est}
        for v in ["U_raw", "S_norm", "B_norm", "B_fixed015"]:
            row[f"det_rate_{v}"] = P[v].mean(); row[f"FPA_median_{v}"] = F[v].median(); row[f"AUC_median_{v}"] = A[v].median()
            dv = g[(g.variant == v) & g.detected.astype(bool)].delay
            row[f"delay_median_{v}"] = dv.median() if len(dv) else np.nan
        row["U_equals_S_all_seeds"] = bool((P["U_raw"] == P["S_norm"]).all() and np.allclose(Dl["U_raw"], Dl["S_norm"]))
        b, c = int((P.B_norm & ~P.U_raw).sum()), int((~P.B_norm & P.U_raw).sum())
        row["mcnemar_B_vs_U_b"], row["mcnemar_B_vs_U_c"] = b, c
        row["mcnemar_p_exact"] = float(stats.binomtest(min(b, c), b + c, .5).pvalue) if b + c else 1.0
        fx, fy = F["B_norm"].to_numpy(), F["U_raw"].to_numpy()
        row["wilcoxon_FPA_B_vs_U_p"] = float(stats.wilcoxon(fx, fy, zero_method="zsplit").pvalue) if not np.all(fx == fy) else 1.0
        gc.append(row)
    pd.DataFrame(gc).to_csv(out / "gating_comparison.csv", index=False)
    # ---------------- factorial tests ----------------
    ft = []
    for v in ("B_norm", "U_raw"):
        for sc in ("drift_gradual", "shock"):
            g = r1[(r1.scenario == sc) & (r1.variant == v) & (r1.rule == "mu_sigma") & r1.binning.isin(["per_window", "none"])]
            ft.append(factorial(g, ["est", "cfg"], f"synthetic/{sc}/{v}/mu_sigma/per_window"))
        g = pr1[(pr1.variant == v) & (pr1.rule == "mu_sigma") & pr1.binning.isin(["per_window", "none"])].copy()
        g["Ws"] = "W" + g.W.astype(str) + "s" + g.s.astype(str)
        ft.append(factorial(g, ["est", "Ws"], f"proxy/{v}/mu_sigma/per_window"))
    g = leg[leg.scenario.isin(["drift_gradual", "shock"])]
    for sc in ("drift_gradual", "shock"):
        ft.append(factorial(g[g.scenario == sc], ["est", "cfg"], f"synthetic/{sc}/legacy_published"))
    json.dump(ft, open(out / "factorial_tests.json", "w"), indent=1, default=float)
    # ---------------- Shannon binning effect ----------------
    sb = r1[(r1.est == "Shannon") & (r1.rule == "mu_sigma") & (r1.variant.isin(["U_raw", "B_norm"]))]
    sbs = summarize(sb, ["scenario", "cfg", "variant", "binning"])
    sbs.to_csv(out / "shannon_binning_synthetic.csv", index=False)
    pbs = pr1[(pr1.est == "Shannon") & (pr1.rule == "mu_sigma") & (pr1.variant.isin(["U_raw", "B_norm"]))]
    summarize(pbs, ["W", "s", "variant", "binning"]).to_csv(out / "shannon_binning_proxy.csv", index=False)
    # ---------------- figures: delay boxplots ----------------
    for sc in ("drift_gradual", "shock"):
        fig, axs = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
        for j, est in enumerate(EST):
            data, labels = [], []
            for cid in CFG_ORDER:
                for v, src in (("legacy", leg), ("U_raw", r1), ("B_norm", r1)):
                    if v == "legacy":
                        gg = src[(src.scenario == sc) & (src.cfg == cid) & (src.est == est)]
                        dv = gg[gg.detected].delay.astype(float)
                    else:
                        gg = src[(src.scenario == sc) & (src.cfg == cid) & (src.est == est) & (src.variant == v) & (src.rule == "mu_sigma") & src.binning.isin(["per_window", "none"])]
                        dv = gg[gg.detected.astype(bool)].delay.astype(float)
                    data.append(dv.to_numpy() if len(dv) else np.array([np.nan])); labels.append(f"{cid}\n{v}\n{len(dv)}/30")
            axs[j].boxplot(data, showfliers=True, flierprops={"markersize": 2}); axs[j].set_xticks(range(1, len(labels) + 1), labels, fontsize=5)
            axs[j].set_title(est, fontsize=9)
        axs[0].set_ylabel("delay (samples)"); fig.suptitle(f"Synthetic {sc}: delay over 30 seeds (legacy published vs R1 U_raw vs R1 B_norm; n detected/30)", fontsize=9)
        fig.tight_layout(); fig.savefig(out / "figures" / f"delay_box_{sc}.png", dpi=110); plt.close(fig)
    # ---------------- real-minute bootstrap (robustness) ----------------
    bp = R / "03_real_minute_bootstrap/real_minute_mbb_long.csv.gz"
    if bp.exists():
        b = rd(bp)
        b = b[b.variant != "ALL"]
        bs = b.groupby(["scheme", "est", "W", "s", "variant", "rule"]).apply(lambda g: pd.Series({
            "B": len(g), "det_rate": g.detected.astype(bool).mean(), **dict(zip(["det_ci_lo", "det_ci_hi"], wilson(int(g.detected.astype(bool).sum()), len(g)))),
            "delay_median": g.loc[g.detected.astype(bool), "delay"].median(), "tau_inf_rate": float(np.isinf(g.tau.astype(float)).mean()),
            "tau_median": g.tau.astype(float).replace(np.inf, np.nan).median(), "fires_post_median": g.fires_post.median(),
            "FP_per_hour_median": g.FP_per_hour.median()}), include_groups=False).reset_index()
        bs.insert(0, "status", "ROBUSTNESS ONLY - not primary evidence")
        bs.to_csv(out / "real_minute_bootstrap_summary.csv", index=False)
    print("analysis done")


if __name__ == "__main__":
    main()
