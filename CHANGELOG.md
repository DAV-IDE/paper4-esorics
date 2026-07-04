# Changelog

All notable changes to the Paper 4 manuscript and reproducibility kit.

## [v4.1.1] — 2026-07-04

Paper alignment with reproducible repository state (PR #4). No
regeneration of headline numbers; the goal of this release is to make
the LaTeX manuscript and the repository consistent, and to make the
reviewer-facing surface (README, docs, provenance, wording audit,
audit scripts) match what actually runs.

Methodological rule applied throughout: **the paper is updated to match
the reproducible repository, not the other way around**. When the
repository produces numbers, paths, tables or figures different from
the paper manuscript v4.0 of 2026-07-01, the manuscript is corrected;
no claim is silently strengthened. Any change in ordering that would
qualify as an empirical finding is reported explicitly, never
overwritten.

### Added
- `results/synthetic/` — verified static snapshot of the 45-run
  synthetic entropy factorial imported from the upstream companion
  pipeline `LoreBerto03/psi-risk-dt-pipeline` @ SHA `edac16e`,
  comprising `results_ready_summary.csv` (45 rows) and
  `results_ready_summary.tex` (longtable).
- `results/synthetic/provenance.json` — SHA-256 pinned manifest
  documenting upstream repository, SHA, per-file digests, license
  status, and re-verification protocol.
- `scripts/verify_synthetic_provenance.py` — re-checks each snapshot
  file against the pinned SHA-256 and exits non-zero on mismatch.
- `docs/synthetic_factorial_provenance.md` — rationale for a static
  snapshot instead of a submodule or re-implementation, mitigation
  plan for the unresolved license status, and re-verification
  protocol.
- `docs/pareto_byte_rate_exclusion.md` — Pareto-dominance argument
  justifying the exclusion of the byte-rate detector from the front
  and its representation as a dominated point in the figure.
- `docs/wording_audit.md` — Safe-Claim Matrix enforcement protocol
  and false-positive suppression rationale for `audit_wording.sh`.
- README "Reviewer status (July 2026)" section: regenerated vs.
  imported artefacts, known limitations (AUC NaN, license unresolved,
  PR #3 not yet merged), and the empirical-honesty rule verbatim.
- `.gitignore` whitelist entry `!results/synthetic/*.csv` so that the
  imported snapshot is tracked despite the global `*.csv` ignore.

### Changed
- `paper/main_v4.tex` — LaTeX build paths corrected from `tables/`
  and `figures/` to `../tables/` and `../figures/` (3 replacements) so
  that the manuscript compiles against the out-of-tree layout used by
  the repository (paper sources under `paper/`, generated artefacts
  under top-level `tables/` and `figures/`).
- `paper/main_v4.tex` §5.1 — narrative and caption of Table 6 aligned
  with the imported 45-run snapshot: description of the factorial
  design, cardinality, per-cell aggregation, and provenance now match
  what is actually in `results/synthetic/results_ready_summary.csv`.
- `paper/main_v4.tex` Table 7 (real-data factorial) — description
  corrected from an inaccurate "2×2×2+1" formulation to the actual
  diagonal 3×3 design (Shannon / Sample / Permutation × (W,s) in
  {(64,8), (128,4), (256,1)}) that `scripts/eal_factorial.py`
  produces and that `results/eal/eal_factorial_summary.json`
  contains.
- `scripts/eal_factorial.py` and `scripts/baseline_zscore.py` —
  explicit `ImportError` handling for `scikit-learn`: the AUC fallback
  now prints an unambiguous stderr warning instead of silently
  emitting `NaN` for AUC-ROC and AUC-PR.
- `requirements.txt` — pin `scikit-learn>=1.4,<1.7` so that AUC
  metrics are computed by default and the fallback branch is exercised
  only in genuinely constrained environments.
- `scripts/audit_wording.sh` — false-positive suppression: full-line
  comments, the Safe-Claim Matrix region, single-line and multi-line
  negations of forbidden terms are excluded from the audit.

### Known limitations (unresolved in this release)
- **AUC-ROC / AUC-PR remain NaN** in the current `results/eal/*.json`
  and `results/pareto/*.json`: the root cause is fixed in this
  release, but a full regeneration is intentionally deferred to keep
  the diff focused on the alignment. The values will be populated on
  the next regeneration after `pip install -r requirements.txt`.
- **License status of the imported synthetic snapshot is unresolved**:
  the upstream companion repository has no LICENSE file and no
  license declaration in its README. Redistribution must be
  confirmed with Lorenzo Bertoletti and Davide Facheris before this
  repository is published or its ESORICS artefact submitted. The
  mitigation steps already applied are documented in
  `results/synthetic/provenance.json` and
  `docs/synthetic_factorial_provenance.md`.
- **PR #3 (real CIC-IDS2017 rerun on branch `real-data-integration
  -tau-sweep`) is not yet merged**: the paper narrative therefore
  still describes the proxy-only rerun of §5.2. The real-rerun
  narrative will be updated in a follow-up PR after PR #3 is
  merged, per the empirical-honesty rule.
- **`tab:headline` FP_A discrepancy** between the paper text and the
  imported CSV cross-check (Drift Shannon C1: paper=82 vs CSV=65;
  Shock Permutation C1: paper=26 vs CSV=38) is left as-is in this
  release: it cannot be resolved without input from Lorenzo
  Bertoletti. The discrepancy is flagged in the PR #4 description
  so it is not lost.

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
