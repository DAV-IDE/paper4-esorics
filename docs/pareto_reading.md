# How to Read the Pareto Design-Space Figure

## What the figure shows

`figures/pareto_design_space.pdf` plots **12 detector configurations** in the (FPR, detection-delay) plane:

* **3 baseline points** (z-score on pkt-rate, byte-rate, dport-entropy) — open squares
* **9 EAL points** (3 estimators × 3 (W, s) configs) — coloured by estimator

## Axes

* **x-axis:** False-Positive Rate (lower is better)
* **y-axis:** Detection delay in seconds (lower is better)

Pareto front = points such that no other point is **strictly better on both axes**.

## What we found (and why it matters)

The Pareto front is composed of **two baseline points only**: `z/pkt-rate` (FPR=0.5%, delay=0s) and `z/dport-entropy` (FPR=0.01%, delay=1034s).

**None of the EAL configurations Pareto-dominates the baselines on this scenario.** Of the 9 EAL configs:
* 7 missed the attack entirely (shown as a clustered "missed" marker)
* 2 detected (Sample (128, 4) and Sample (256, 1)) but with **higher FPR and higher delay** than the cheapest baseline

## Why this is an honest result, not a failure

The thesis of Paper 4 is **NOT** that EAL detects better than z-score. The thesis is that:

> The next operational gap in neurosymbolic Digital Twin cybersecurity is **not detector accuracy but detector configurability and auditability**.

The Pareto figure provides **empirical support for this thesis** by showing that:

1. A single fixed (E, W, s) configuration cannot dominate even the simplest causal baseline across scenarios.
2. Therefore (E, W, s) must be exposed as **deployment-time variables**, not frozen at design time.
3. The auditability surface (knowing exactly which (E, W, s) was active at each second) is the operational contribution, not a detection-accuracy claim.

This honest framing is given in §5.3 "Three readings of the Pareto figure" of `main_v4.tex`.

## The miss cluster annotation

The 7 EAL configurations that missed the attack are shown as a **single open marker labelled "7 missed"** with a sublabel listing the configurations (2 per row, to avoid label overlap). This is a deliberate visual choice: showing 7 superimposed points at infinity would be misleading.

## Tolerance for reproduction

* Point positions: ±0.001 on x-axis, ±5 s on y-axis (rounding artefacts)
* Pareto front composition: must be **identical** to the committed figure
* Missed/detected partition: must be **identical** (7 / 2 split)

If your reproduction yields a different partition, this is a **finding to investigate**, not a tolerance issue.
