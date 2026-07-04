# Paper 4 — Reproducibility Kit

**Title:** Sensitivity-Aware Entropy Analysis and Semantic Explainability Layers for Neurosymbolic Digital Twin Monitoring
**Authors:** Roberto Pazzi, Davide Facheris, Davide Tosi — Università degli Studi dell'Insubria, DiSTA
**Version:** v4 (June 2026)
**Target venue:** ESORICS 2026 (workshop track candidate)

This repository contains everything needed to **regenerate from scratch** Tables 8 and 9 and Figure (Pareto design space) of the paper. All numeric results in §5.2, §5.3 and §5.4 of `paper/main_v4.tex` are produced by the scripts in `scripts/` with fixed random seed `20260606`.

---

## TL;DR — full reproduction in one command

```bash
make all
```

This runs the entire pipeline (≈ 3–5 minutes on a laptop) and overwrites `tables/real_data.tex`, `tables/sparql_scaling.tex`, and `figures/pareto_design_space.{pdf,png}`. Re-compiling `paper/main_v4.tex` afterwards yields the identical PDF.

---

## 1. Repository layout

```
paper4-reproducibility-kit/
├── README.md                  ← this file
├── REPRODUCIBILITY.md         ← step-by-step protocol (read this second)
├── CHANGELOG.md               ← v1 → v4 history
├── Makefile                   ← orchestrates the full pipeline
├── requirements.txt           ← Python deps (pinned)
├── .gitignore
├── LICENSE                    ← MIT (code) / CC-BY-4.0 (paper)
│
├── scripts/                   ← all experiment code (7 files, ~1.4k LOC)
│   ├── generate_cic_proxy.py          # step 1: synthesise proxy stream
│   ├── ingest_cicids2017_friday_ddos.py  # step 2: ingest real CSV (optional)
│   ├── baseline_zscore.py             # step 3: 3-feature causal baseline
│   ├── eal_factorial.py               # step 4: 3×3 EAL grid (9 runs)
│   ├── build_table_and_pareto.py      # step 5: assemble Table 8 + Pareto fig
│   ├── sparql_scaling.py              # step 6: Q1/Q2/Q3 × {1k,10k,50k}
│   └── smoke_test_baseline.py         # end-to-end smoke test on tiny synth data
│
├── tables/                    ← LaTeX fragments \input'd by the paper
│   ├── real_data.tex                  # Table 8 (baseline + EAL)
│   └── sparql_scaling.tex             # Table 9 (SPARQL latency)
│
├── figures/                   ← Pareto design-space figure
│   ├── pareto_design_space.pdf
│   └── pareto_design_space.png
│
├── results/                   ← raw numerical artefacts (JSON + CSV)
│   ├── proxy/                         # baseline z-score outputs (proxy)
│   ├── real/                          # baseline z-score outputs (real parquet)
│   ├── eal/                           # 9 per-config metrics + summary (proxy)
│   ├── eal_real/                      # real-data EAL + tau_sweep/ (108) + tau_sweep_by_k/ (12)
│   ├── sparql/                        # latency × graph-size summary
│   ├── table_pareto_manifest.json     # provenance manifest (proxy)
│   └── table_pareto_manifest_real.json  # provenance manifest (real)
│
├── paper/
│   └── main_v4.tex                    # current LaTeX source (Springer LNCS)
│
└── docs/
    ├── proxy_vs_real.md               # what the proxy is / how to swap in real CSV
    ├── pareto_reading.md              # how to read the Pareto figure
    └── sparql_protocol.md             # SPARQL measurement protocol
```

---

## 2. Requirements

* Python ≥ 3.10 (tested on 3.11, 3.12)
* ~500 MB free disk
* No GPU required

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Pinned packages (see `requirements.txt`): `numpy`, `pandas`, `scipy`, `matplotlib`, `rdflib`, `pyarrow`.

---

## 3. Quick reproduction (proxy mode — default)

```bash
make all
```

is equivalent to:

```bash
# 1. Generate the CIC-IDS2017-aligned proxy stream (246k flows, seed=20260606)
python scripts/generate_cic_proxy.py \
    --out data/cic_proxy_friday_ddos.csv \
    --seed 20260606

# 2. Run the 3-feature z-score baseline (causal rolling window)
python scripts/baseline_zscore.py \
    --input data/cic_proxy_friday_ddos.csv \
    --out results/proxy

# 3. Run the 3 × 3 EAL grid (9 configs, ~30 s)
python scripts/eal_factorial.py \
    --input data/cic_proxy_friday_ddos.csv \
    --out results/eal

# 4. Build Table 8 + Pareto figure
python scripts/build_table_and_pareto.py \
    --baseline results/proxy/baseline_zscore_summary.json \
    --eal results/eal/eal_factorial_summary.json \
    --tex tables/real_data.tex \
    --fig figures/pareto_design_space

# 5. SPARQL scaling on synthetic graphs (rdflib in-memory, 11 reps)
python scripts/sparql_scaling.py \
    --sizes 1000 10000 50000 \
    --out results/sparql \
    --tex tables/sparql_scaling.tex
```

Expected wall-clock on a 2024 laptop (8-core CPU, no GPU): **≈ 4 min total**.

---

## 4. Honest reproduction (swap proxy → real CIC-IDS2017)

The default pipeline uses a **proxy stream** that matches the published marginal statistics of CIC-IDS2017 *Friday-WorkingHours-Afternoon-DDos*. This is declared explicitly in the paper (header note, §5.2, captions of Table 8 and Figure Pareto, §5.4).

### 4a. Swap proxy → real CSV via `make REAL=1 all` (legacy path)

To run the **identical pipeline** on the real CSV (zero code change):

```bash
# 1. Download CIC-IDS2017 from https://www.unb.ca/cic/datasets/ids-2017.html
#    (registration required; accept the licence)
# 2. Place the file (after CSV concatenation) at:
#    data/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv

# 3. Run the ingester (normalises column names → same schema as the proxy)
python scripts/ingest_cicids2017_friday_ddos.py \
    --input data/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv \
    --out data/cic_real_friday_ddos.csv

# 4. Re-run steps 2–4 of §3 above pointing --input to data/cic_real_friday_ddos.csv
make REAL=1 all
```

The scripts emit identical CSV/JSON schemas regardless of source. **Any change in the qualitative ordering between proxy and real will be reported as an empirical finding**, never silently edited away (see §5.4 of the paper).

### 4b. Real-data rerun on parquet + τ recalibration sweep (new)

A parallel real-data pipeline lives alongside the proxy pipeline: it operates on the parquet redistribution of CIC-IDS2017 Friday DDoS (`bvsam/cic-ids-2017` on HuggingFace, SHA256 `7c5876d52189fc01af54bad6cf23afe9f7fbc0e3ca6c3595920754f0c3ba8f66`) and includes a 108-cell τ recalibration sweep (4 k × 3 warmup × 9 configs).

```bash
# 1. Fetch the parquet (23 MB) into data/
#    (see CHANGELOG_REAL.md §1 for the exact URL and SHA256 check)

# 2. Run the real-data pipeline (baseline + 9 EAL configs on real parquet)
make real-rerun

# 3. Run the tau recalibration sweep (~10 min single-thread)
make tau-sweep

# Or both at once:
make real-all
```

Outputs land in `results/eal_real/`, `results/real/`, `figures/*_real.*` and `figures/tau_sweep_heatmap.*`, `tables/real_data_real.tex` and `tables/real_tau_sweep.tex`. **The proxy artefacts are untouched** — the two pipelines coexist so proxy-vs-real deltas remain visible for §5.4 comparison. Full empirical narrative (Findings 1–6, including the operational τ recalibration result) is in `CHANGELOG_REAL.md`.

---

## 5. What each script produces

| Script | Inputs | Outputs | Time |
|--------|--------|---------|------|
| `generate_cic_proxy.py` | `--seed`, `--out` | `cic_proxy_friday_ddos.csv` (~20 MB) | 5 s |
| `ingest_cicids2017_friday_ddos.py` | real CIC CSV | normalised CSV (same schema) | 10 s |
| `baseline_zscore.py` | flow CSV | 3 per-feature metric JSON + summary + per-second CSV | 15 s |
| `eal_factorial.py` | flow CSV | 9 per-config metric JSON + summary | 30 s |
| `build_table_and_pareto.py` | baseline + EAL summaries | `tables/real_data.tex`, `figures/pareto_design_space.{pdf,png}` | 3 s |
| `sparql_scaling.py` | `--sizes` | per-query latency JSON + `tables/sparql_scaling.tex` | 90 s |
| `smoke_test_baseline.py` | (none, synthetic) | end-to-end sanity check | 5 s |

---

## 6. Determinism

* All randomness is seeded (`numpy.random.default_rng(20260606)`).
* `baseline_zscore.py` uses a **causal rolling window** (no future leakage) and enforces five anti-cheat constraints documented in §5.2 of the paper.
* SPARQL latencies are reported as **median of last 10 of 11 reps** (first rep discarded as warm-up).
* On the same Python + numpy version, results are bit-for-bit reproducible.

---

## 7. Connection to the paper

| Paper element | Reproduced by |
|---------------|---------------|
| Table 8 (§5.2) | `scripts/build_table_and_pareto.py` → `tables/real_data.tex` |
| Figure Pareto (§5.3) | `scripts/build_table_and_pareto.py` → `figures/pareto_design_space.pdf` |
| Table 9 (§5.4) | `scripts/sparql_scaling.py` → `tables/sparql_scaling.tex` |
| Inherited Paper 3 numbers (AUC=0.993, FPR=0.021, MSU≤88%) | **NOT** reproduced here — cited as prior work |
| EAL formal stability theorem | **NOT** here — Paper 5 (in preparation) |

---

## 8. Compiling the paper

```bash
cd paper/
pdflatex main_v4.tex
bibtex main_v4
pdflatex main_v4.tex
pdflatex main_v4.tex
```

On Overleaf: **set Main document = `main_v4.tex`** before compiling (V3 was mistakenly compiled as `main_v2.tex` once — do not repeat).

---

## 9. Repository hygiene (for Davide)

* The CSV proxy (~20 MB) is **not** committed — it is regenerated deterministically. See `.gitignore`.
* `results/` contains the **last good run** committed for review convenience; CI should regenerate it.
* Tag releases on the LaTeX revision: `v4.0.0` = the current state.
* Keep `main_v1.tex`, `main_v2.tex`, `main_v3.tex` in an `archive/` branch, not on `main`.

---

## 10. License

* Code (`scripts/`, `Makefile`): **MIT**
* Paper text (`paper/`): **CC-BY-4.0**
* Datasets: subject to CIC-IDS2017 original licence (UNB)

---

## 11. Contact

* Roberto Pazzi — `roberto.pazzi@uninsubria.it`
* Davide Facheris — `davide.facheris@uninsubria.it`
* Davide Tosi — `davide.tosi@uninsubria.it`

Open an issue on GitHub for reproducibility problems.
