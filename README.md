# Paper 4 — Reproducibility Kit

**Title:** Sensitivity-Aware Entropy Analysis and Semantic Explainability Layers for Neurosymbolic Digital Twin Monitoring
**Authors:** Roberto Pazzi, Davide Facheris, Davide Tosi — Università degli Studi dell'Insubria, DiSTA
**Version:** v4 (June 2026)
**Target venue:** ESORICS 2026 (workshop track candidate)

This repository contains everything needed to **regenerate from scratch** Tables 8 and 9 and Figure (Pareto design space) of the paper. All numeric results in §5.2, §5.3 and §5.4 of `paper/main_v4.tex` are produced by the scripts in `scripts/` with fixed random seed `20260606`.

---

## Reviewer status (July 2026)

This section summarises the current state of the repository from a
reviewer's point of view. See the individual documents referenced
below for full detail.

### What is regenerated end-to-end inside this repository

- **Table 8** (real-data / proxy factorial) and its Pareto figure —
  from `scripts/baseline_zscore.py`, `scripts/eal_factorial.py`,
  `scripts/build_table_and_pareto.py`, seed `20260606`. Full
   4-command reproduction in §3 below.
- **Table 9** (SPARQL scaling Q1/Q2/Q3 × {1k, 10k, 50k}) — from
  `scripts/sparql_scaling.py`, 11 reps, first dropped as warm-up.
  Protocol in [`docs/sparql_protocol.md`](docs/sparql_protocol.md).
- **Wording audit** — `scripts/audit_wording.sh` enforces the
  Safe-Claim Matrix. Protocol in
  [`docs/wording_audit.md`](docs/wording_audit.md).

### What is imported as a verified snapshot (NOT regenerated here)

- **Table 6** (45-run synthetic entropy factorial) — the two curated
  outputs of the upstream companion pipeline
  [`LoreBerto03/psi-risk-dt-pipeline`](https://github.com/LoreBerto03/psi-risk-dt-pipeline)
  are stored as a verified static snapshot under
  [`results/synthetic/`](results/synthetic/), pinned by SHA-256 in
  [`results/synthetic/provenance.json`](results/synthetic/provenance.json)
  and re-checkable via
  `python scripts/verify_synthetic_provenance.py`. The rationale for
  a snapshot instead of a submodule or re-implementation is in
  [`docs/synthetic_factorial_provenance.md`](docs/synthetic_factorial_provenance.md).
  The upstream generative pipeline (Docker + Fuseki + RDF ingest +
  sliding-window entropy) is not re-implemented in this repository.

### Known limitations reviewers should be aware of

- **AUC-ROC / AUC-PR are NaN in the current baseline JSONs** because
  the older version of `scripts/eal_factorial.py` and
  `scripts/baseline_zscore.py` silently swallowed a missing
  `scikit-learn` import. This is now fixed: `scikit-learn` is listed
  in `requirements.txt`, the fallback prints an explicit stderr
  warning, and a genuine value error no longer masquerades as
  "AUC undefined". After `pip install -r requirements.txt` and a
  re-run, the AUC columns will be populated on the next regeneration
  (not carried out in this commit to keep the diff focused on the
  fix; the JSONs continue to reflect the state observed at v4.0.0).
- **License status of the imported synthetic snapshot is currently
  unresolved** — the upstream companion repository has no LICENSE
  file and no license declaration in its README. Redistribution
  status must be confirmed with Lorenzo Bertoletti and Davide
  Facheris before this repository is published or its ESORICS
  artefact submitted. See
  [`results/synthetic/provenance.json`](results/synthetic/provenance.json)
  and
  [`docs/synthetic_factorial_provenance.md`](docs/synthetic_factorial_provenance.md)
  for the mitigation steps already applied.
- **PR #3 is not yet merged into `main`**, so the paper text still
  describes the proxy-only rerun of §5.2. The real CIC-IDS2017
  rerun (PR #3 branch `real-data-integration-tau-sweep`) will be
  merged separately; the paper narrative for that rerun will be
  updated in a follow-up PR after the merge, per the empirical-
  honesty rule (any change in ordering must be reported as an
  empirical finding, not silently overwritten).

### Empirical honesty rule

The fundamental methodological rule of this repository is:
if the repository produces numbers, paths, tables or figures
different from the paper manuscript, **the paper is updated so as
to be consistent with the reproducible repository, not the other
way around**. The source of truth is the verified repository:
scripts, JSONs, generated tables, generated figures, and manifests.
Claims are never strengthened; if the repository does not support a
claim, the claim is reduced or qualified in the paper.

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
│   ├── proxy/                         # baseline z-score outputs
│   ├── eal/                           # 9 per-config metrics + summary
│   ├── sparql/                        # latency × graph-size summary
│   └── table_pareto_manifest.json     # provenance manifest
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
