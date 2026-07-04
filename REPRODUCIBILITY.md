# Reproducibility Protocol

This document gives a **step-by-step protocol** for an independent reviewer to verify every number in §5.2, §5.3 and §5.4 of the paper. It complements `README.md`.

---

## Environment

```
OS:      Linux / macOS / WSL2 (tested on Ubuntu 22.04)
Python:  3.11.x (3.10–3.12 work)
RAM:     ≥ 4 GB
Disk:    ≥ 500 MB free
GPU:     not required
```

Pin your environment:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip freeze > my_environment.lock   # for your records
```

---

## Stage A — Data generation (proxy mode)

**Goal:** create a 246k-flow CIC-IDS2017-aligned proxy stream with a controlled DDoS attack core.

```bash
python scripts/generate_cic_proxy.py --seed 20260606 \
    --out data/cic_proxy_friday_ddos.csv
```

**Expected output:**
* File `data/cic_proxy_friday_ddos.csv` (~20 MB, 246,078 rows)
* Class balance: BENIGN ≈ 158,285 / DDoS ≈ 87,793
* Attack core: 15:55:00–16:15:00 (UTC, simulated wallclock)

**Verification:**

```bash
python -c "
import pandas as pd
df = pd.read_csv('data/cic_proxy_friday_ddos.csv')
print('rows:', len(df))
print('labels:', df['Label'].value_counts().to_dict())
"
```

Must print exactly:
```
rows: 246078
labels: {'BENIGN': 158285, 'DDoS': 87793}
```

---

## Stage B — Baseline z-score (3 features)

```bash
python scripts/baseline_zscore.py \
    --input data/cic_proxy_friday_ddos.csv \
    --out results/proxy
```

**Anti-cheat constraints enforced** (audited in §5.2 of the paper):
1. **Causal rolling window** — no future data leaks into the z-statistic.
2. **Stable-phase calibration only on pre-attack seconds**.
3. **k = 3** (frozen at design time, not tuned per run).
4. **Single-pass evaluation** — no early stopping on test labels.
5. **Detection delay** = first fire **at or after** first attack second (not before — bug fixed in v4).

**Expected outputs in `results/proxy/`:**
```
baseline_zscore_pktrate.csv             (per-second z-score time-series)
baseline_zscore_pktrate_metrics.json
baseline_zscore_byterate.csv
baseline_zscore_byterate_metrics.json
baseline_zscore_dportentropy.csv
baseline_zscore_dportentropy_metrics.json
baseline_zscore_summary.json
```

**Expected numbers** (also in Table 8, rows 1–3):

| Feature | AUC | FPR | Detection delay | Fires |
|---------|-----|-----|-----------------|-------|
| z/pkt-rate | 0.502 | 0.005 | 0 s | 96 |
| z/byte-rate | 0.505 | 0.006 | 0 s | 105 |
| z/dport-entropy | 0.488 | 0.0001 | 1034 s | 21 |

Tolerance: ±0.001 on AUC, ±1 fire (rounding).

---

## Stage C — EAL factorial grid (9 runs)

```bash
python scripts/eal_factorial.py \
    --input data/cic_proxy_friday_ddos.csv \
    --out results/eal
```

**Configuration grid:** estimator ∈ {Shannon, Sample, Permutation} × (W, s) ∈ {(64, 8), (128, 4), (256, 1)} = 9 runs.

**Estimator definitions** (from `scripts/eal_factorial.py`):
* **Shannon** — histogram-based, 16 bins, natural log.
* **Sample (SampEn)** — m = 2, r = 0.2 × σ_window.
* **Permutation** — Bandt–Pompe ordinal patterns, m = 3.

**Expected outputs in `results/eal/`:** 9 metric JSON files + `eal_factorial_summary.json`.

**Expected detection outcomes** (also in Table 8, rows 4–12):

| Config | AUC | FPR | Detection delay | Fires | Verdict |
|--------|-----|-----|-----------------|-------|---------|
| Shannon (64, 8) | — | — | n/a | 0 | **missed** |
| Shannon (128, 4) | — | — | n/a | 0 | **missed** |
| Shannon (256, 1) | — | — | n/a | 0 | **missed** |
| Sample (64, 8) | — | — | n/a | 0 | **missed** |
| Sample (128, 4) | 0.440 | 0.035 | 355 s | 400 | detected |
| Sample (256, 1) | 0.404 | 0.158 | 255 s | 1952 | detected |
| Permutation (64, 8) | — | — | n/a | 0 | **missed** |
| Permutation (128, 4) | — | — | n/a | 0 | **missed** |
| Permutation (256, 1) | — | — | n/a | 0 | **missed** |

**Interpretation:** only 2 of 9 EAL configs detect the attack on this scenario. This is reported honestly in §5.3 as empirical support for the design-space thesis (E, W, s must be deployment-time variables, not design-time constants).

---

## Stage D — Table 8 + Pareto figure assembly

```bash
python scripts/build_table_and_pareto.py \
    --baseline results/proxy/baseline_zscore_summary.json \
    --eal      results/eal/eal_factorial_summary.json \
    --tex      tables/real_data.tex \
    --fig      figures/pareto_design_space
```

**Outputs:**
* `tables/real_data.tex` (LaTeX fragment, 22 lines, `\input`-ed by `main_v4.tex`)
* `figures/pareto_design_space.pdf` + `.png` (12 points: 3 baseline + 9 EAL)

**Pareto front composition:** the front is composed of **baseline points only** (z/pkt-rate and z/dport-entropy). EAL configurations **do not Pareto-dominate** the baselines on this scenario. This is the central empirical finding of §5.3.

---

## Stage E — SPARQL scaling

```bash
python scripts/sparql_scaling.py \
    --sizes 1000 10000 50000 \
    --reps 11 \
    --out results/sparql \
    --tex tables/sparql_scaling.tex
```

**Engine:** `rdflib` in-memory store (no Fuseki / Jena required for the reproduction).
**Measurement protocol:** 11 reps per (query, graph-size) cell; first rep discarded as warm-up; report median of last 10.

**Queries:**
* **Q1** — entropy-spike triage (most recent N windows above τ)
* **Q2** — phase-based comparison (group by attack phase)
* **Q3** — gate-fired explainability lookup (joins Window → Explanation → Mitigation)

**Expected latencies** (also in Table 9, generated from `results/sparql/sparql_scaling_summary.json`):

| Graph size | Q1 (ms) | Q2 (ms) | Q3 (ms) | Q1 bindings | Q3 bindings |
|------------|---------|---------|---------|-------------|-------------|
| 1k triples | 4.17 | 4.99 | 1.77 | 34 | 13 |
| 10k triples | 24.72 | 34.82 | 5.65 | 321 | 110 |
| 50k triples | 109.90 | 189.01 | 23.70 | 1,543 | 505 |

Tolerance: ±20% on latency (hardware-dependent — the values above are the ones committed in `tables/sparql_scaling.tex` and reported in the paper §5.4); bindings must match exactly.

**Honesty caveat (paper, §5.4):** "We make no claim of scaling to production graphs of 10⁶ triples or above."

---

## Stage F — LaTeX compile

```bash
cd paper/
pdflatex main_v4.tex
bibtex main_v4
pdflatex main_v4.tex
pdflatex main_v4.tex
```

**On Overleaf:** ensure `main_v4.tex` is set as the **Main document** in Menu → Settings.

---

## Stage G — Forbidden-wording audit

The paper enforces a list of forbidden phrases (E.3 wording matrix). Run:

```bash
bash scripts/audit_wording.sh paper/main_v4.tex
```

(If `audit_wording.sh` is absent, see `docs/wording_audit.md` for the manual grep command.)

Expected output: `OK — no forbidden phrases in non-citation context`.

---

## Sign-off checklist for Davide

- [ ] `make all` completes with exit code 0
- [ ] `tables/real_data.tex` matches the committed version (or diff explained in commit msg)
- [ ] `tables/sparql_scaling.tex` matches the committed version (or diff explained)
- [ ] `figures/pareto_design_space.pdf` is identical (`pdfinfo` + visual diff)
- [ ] `pdflatex` compiles `main_v4.tex` without missing references
- [ ] No forbidden phrases (Stage G)
- [ ] `git tag v4.0.0` cut from the verified commit
