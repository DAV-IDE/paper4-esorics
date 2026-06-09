# SPARQL Measurement Protocol

## Why rdflib in-memory (and not Fuseki)?

The paper specifies that SEL is "accessible through an Apache Jena Fuseki endpoint". For reproducibility, the kit uses **rdflib in-memory** because:

1. **Zero external dependencies** — reviewers don't need to install Java + Jena + Fuseki.
2. **Deterministic** — no network, no cache, no JVM warm-up variance.
3. **Conservative** — rdflib is slower than Fuseki; reported latencies are **upper bounds** on what a tuned Fuseki deployment would achieve.

The paper §5.4 declares this substitution explicitly. A real Fuseki benchmark is left as future work (Paper 5 follow-up).

## Graph generator

`scripts/sparql_scaling.py` builds synthetic RDF graphs matching the 8-class SEL ontology:
* `psi:Window` instances with timestamps and entropy scores
* `psi:FeatureVector` instances linked to Windows
* `psi:EntropySignal` instances with stable/drift/shock phase labels
* `psi:AttackPhase` instances with start/end timestamps
* `psi:RiskScore` instances linked to AttackPhases
* `psi:Explanation` instances linked to gate-fired Windows
* `psi:MitigationHint` instances linked to Explanations
* `psi:Scenario` instances (top-level)

Graph sizes: 1k, 10k, 50k triples.

## Queries

### Q1 — Entropy-spike triage
"Return the N most recent windows whose entropy exceeded τ, ranked by timestamp descending."

### Q2 — Phase-based comparison
"Group risk scores by attack phase and return mean ± std per phase."

### Q3 — Gate-fired explainability lookup
"For each window that fired the symbolic gate, return its linked Explanation and the recommended MitigationHint."

## Measurement protocol

```python
for query in [Q1, Q2, Q3]:
    for size in [1000, 10000, 50000]:
        graph = build_graph(size, seed=20260606)
        latencies = []
        for rep in range(11):
            t0 = time.perf_counter_ns()
            results = list(graph.query(query))
            t1 = time.perf_counter_ns()
            latencies.append((t1 - t0) / 1e6)  # ms
        # Discard first rep (warm-up), report median of last 10
        report_median_latency = statistics.median(latencies[1:])
        report_bindings = len(results)
```

## Hardware variance

Latencies depend on CPU. Tolerance: **±20%** on absolute milliseconds.
Bindings counts must match **exactly** (determined by the graph generator's seed).

## Scaling claim

§5.4 of `main_v4.tex` is explicit:

> "We make no claim of scaling to production graphs of 10⁶ triples or above."

Q3 latency on 1M triples with rdflib is in the seconds, not milliseconds, regime. A persistent indexed store (Fuseki, Virtuoso, Stardog) would be required — this is left for the engineering follow-up.

## Honesty caveat

The numbers in Table 9 are **upper bounds**: rdflib in-memory is the slowest reasonable backend. A tuned Fuseki deployment would be 5-20× faster. We chose to report the **conservative** measurement to avoid overstating SEL's performance envelope.
