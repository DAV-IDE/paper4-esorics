# Changelog

All notable changes to the Paper 4 manuscript and reproducibility kit.

## [v4.0.1] — 2026-07-04

Coherence audit fixes (see PR "Coherence audit fixes"). No changes to any
numerical result, script logic, or manuscript claim; only alignment of
three documentation surfaces that had drifted apart.

### Fixed
- **SPARQL latencies (B1)**: the paper §5.4 and `REPRODUCIBILITY.md`
  Stage E cited Q1/Q2/Q3 latencies ~3× higher than those actually
  committed in `tables/sparql_scaling.tex` and
  `results/sparql/sparql_scaling_summary.json`. Manuscript and protocol
  are now aligned to the committed JSON (Q1: 4.2→110 ms, Q2: 5.0→189 ms,
  Q3: 1.8→23.7 ms across 1k→50k triples).
- **AUC documentation (B2)**: `REPRODUCIBILITY.md` Stages B and C
  declared expected AUC values (0.502 / 0.505 / 0.488 / 0.440 / 0.404)
  that the scripts never produce (JSON has `AUC_ROC = AUC_PR = NaN`).
  The tables in the protocol now match what `baseline_zscore.py` and
  `eal_factorial.py` actually emit; a note explains why AUC is not
  computed on this pipeline (see also §5.2 reporting rules).
- **Non-existent `experiments/day1/` paths (B3)**: the paper §5.2/5.3/5.4
  captions, the auto-generated header of `tables/real_data.tex`, and
  `scripts/build_table_and_pareto.py` referenced a directory that does
  not exist in the repo. Replaced with the actual paths (`scripts/`,
  `data/`, `results/`).
- **CI over-strict on SPARQL table (M5)**: `.github/workflows/reproduce.yml`
  ran `git diff --exit-code` on all of `tables/`, which would fail on
  any runner with different CPU speed (SPARQL latency has ±20% tolerance).
  Split into a strict diff on `real_data.tex` (deterministic) and a
  structural check on `sparql_scaling.tex` (bindings and triple counts
  only; latency cells intentionally excluded).

### Note
- `tables/real_data.tex` renders AUC columns as `--` (unchanged). This
  is now consistent across manuscript, protocol and generated tables.

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
