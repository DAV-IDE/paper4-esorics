# Changelog

All notable changes to the Paper 4 manuscript and reproducibility kit.

## [v4.1.0] — 2026-07-04

Extends the reproducibility kit with a **real-data rerun** on CIC-IDS2017
Friday-WorkingHours-Afternoon-DDoS (parquet redistribution) and a
**τ recalibration sweep** (4 k × 3 warmup × 9 EAL configs = 108 cells).
All proxy artefacts are untouched: the two pipelines coexist. This entry
summarises the additions; the detailed empirical narrative (Findings 1–6)
lives in `CHANGELOG_REAL.md`.

### Added
- `scripts/{ingest_real,baseline_zscore_real,eal_factorial_real,build_table_and_pareto_real,tau_sweep_real,build_tau_sweep_artifacts,_inspect_parquet}.py` — 7 new scripts.
- `results/real/` (4 baseline JSON — the 3 per-second CSV are `.gitignore`d by `results/**/*.csv`) and `results/eal_real/` (21 top-level EAL JSON + `tau_sweep/` 108 cells + `tau_sweep_by_k/` 12 aggregates).
- `results/table_pareto_manifest_real.json` — provenance manifest for the real run.
- `figures/pareto_design_space_real.{pdf,png}` and `figures/tau_sweep_heatmap.{pdf,png}`.
- `tables/real_data_real.tex` and `tables/real_tau_sweep.tex`.
- `CHANGELOG_REAL.md` — Findings 1–6 (rerun and τ sweep).
- Makefile targets `real-rerun`, `tau-sweep`, `real-all`.
- README §4b documenting the parquet source (`bvsam/cic-ids-2017` on HuggingFace, SHA256 pinned) and the new Make targets.

### Key empirical finding (V2 thesis support)
- Best operating point on real data: **Permutation entropy (W=16, s=2), warmup=1200 s, k=1.5** → FPR=0.038, delay=60 s, fires=8, AUC=0.710. Pareto-dominates the transparent z-score baseline (dport-entr., FPR=0.065, delay=600 s) on both axes.
- Detection matrix (warmup=1200 s): 4/9 configs at k=1.5, 3/9 at k=2.0, 2/9 at k=2.5, 2/9 at k=3.0.
- warmup=600 s yields σ_stable=NaN for all 9 configs — too few pre-attack minutes for stable-phase calibration.

### Not changed
- No proxy artefacts modified. `results/proxy/`, `results/eal/`, `figures/pareto_design_space.{pdf,png}`, `tables/real_data.tex`, `tables/sparql_scaling.tex` remain the baseline for §5.4 proxy-vs-real comparison.

---

## [v4.0.0] — 2026-06-06

### Added
- **Real experimental data** replacing all three V3 placeholders:
  - Table 8 (§5.2) — 3 baseline + 9 EAL rows with measured numbers
  - Pareto figure (§5.3) — 12 points, real Pareto front, miss-cluster annotation
  - Table 9 (§5.4) — SPARQL scaling on rdflib in-memory, 3 graph sizes × 3 queries
- Header changelog block declaring CIC-IDS2017 **proxy provenance** (lines 1–56)
- §5.2 "Dataset and pipeline" paragraph declaring proxy honestly
- §5.2 five anti-cheat constraints on the baseline pipeline
- §5.3 "Three readings" interpretation paragraph (parameterised gating does NOT dominate)
- §5.4 "Measurement protocol and proxy declaration" paragraph
- "What changes on real CSV" reproducibility statement
- Pareto figure annotation: 7-miss cluster as single open marker
- This reproducibility kit (`scripts/`, `Makefile`, `README.md`, `REPRODUCIBILITY.md`)

### Changed
- Detection-delay metric fixed: now "first fire **at or after** first attack second" (V3 returned pre-attack false-positive times)
- "production-grade" → "indexed-store" (line 1145, forbidden-wording audit)
- Reframed EAL section: parameterised gating is presented as a **design space** to be configured per deployment, NOT as a uniformly superior detector
- Honesty stance: every numerical claim now traceable to a script + JSON artefact

### Fixed
- Detection-delay computation (V3 bug)
- Pareto figure label overlap (final layout 7.6 × 5.2 in)

### Reproducibility
- Full pipeline runs in ≈ 4 min via `make all`
- Bit-for-bit reproducible on fixed seed `20260606`
- Real CIC-IDS2017 CSV swap-in is a one-line change (`make REAL=1 all`)

---

## [v3.0.0] — 2026-06-05 (superseded)

### Added
- Reframed as "parameterised and auditable design space" (NOT extension paper)
- Safe-Claim Matrix (E.3) with forbidden-wording audit
- EAL specification (E, W, s as first-class parameters)
- SEL specification (8-class RDF ontology, 3 SPARQL primitives)

### Known issues (fixed in v4)
- Three "tbd" placeholders (Table 8, Pareto fig, Table 9)
- Detection-delay metric bug

---

## [v2.0.0] — 2026-06-04 (superseded)

### Added
- Reframing from "extension of Ψ-Risk-DT" to "parameter-aware layers atop Ψ-Risk-DT"
- Inheritance statement for Paper 3 results
- Companion paper reference (Paper 5, in preparation)

---

## [v1.0.0] — 2026-06-03 (initial draft, archived)

- First draft of the paper as ESORICS submission candidate
- 45-run factorial study on synthetic Stable/Drift/Shock regimes only
- Illustrative SPARQL evaluation on synthetic escalation trial graph
