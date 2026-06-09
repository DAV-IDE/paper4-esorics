"""
sparql_scaling.py — SEL SPARQL scaling experiment for Paper 4 §5.4

Generates synthetic RDF graphs aligned with the SEL ontology (Paper 4 §4)
at three sizes — N ∈ {1000, 10000, 50000} triples — and runs the three
canonical query primitives:

  Q1: entropy-spike triage  — list Windows with EntropySignal H > threshold
  Q2: phase-based comparison — for each AttackPhase, list Windows + RiskScore
  Q3: gate-fired explainability lookup — given GateFired event, return
       Explanation triples + MitigationHint

Latency is reported as median over R repetitions (default 11, warmup discarded).
We also report triples scanned and bindings returned.
Uses rdflib in-memory store.
"""

from __future__ import annotations
import json
import time
import argparse
from pathlib import Path
from rdflib import Graph, Namespace, URIRef, Literal, RDF
from rdflib.namespace import XSD


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent


parser = argparse.ArgumentParser()
parser.add_argument("--sizes", nargs="+", type=int, default=[1000, 10000, 50000])
parser.add_argument("--reps", type=int, default=11)
parser.add_argument("--out", type=str, default=str(REPO_ROOT / "results" / "sparql"))
parser.add_argument(
    "--tex", type=str, default=str(REPO_ROOT / "tables" / "sparql_scaling.tex")
)
args = parser.parse_args()

OUT_DIR = Path(args.out)
TABLES_OUT = Path(args.tex)

OUT_DIR.mkdir(parents=True, exist_ok=True)
TABLES_OUT.parent.mkdir(parents=True, exist_ok=True)

PSI = Namespace("http://example.org/psi#")


def build_graph(target_triples: int, seed: int = 42) -> Graph:
    """Build a synthetic SEL-aligned graph close to target_triples size."""
    import random

    rng = random.Random(seed)
    g = Graph()
    g.bind("psi", PSI)

    n_windows = max(1, target_triples // 10)
    for i in range(n_windows):
        w = URIRef(f"http://example.org/psi#w{i}")
        fv = URIRef(f"http://example.org/psi#fv{i}")
        es = URIRef(f"http://example.org/psi#es{i}")
        ph = URIRef(f"http://example.org/psi#ph{i % 4}")
        rs = URIRef(f"http://example.org/psi#rs{i}")
        ex = URIRef(f"http://example.org/psi#ex{i}")
        mh = URIRef(f"http://example.org/psi#mh{i % 8}")

        h_val = rng.uniform(0.0, 5.0)
        risk_val = rng.uniform(0.0, 1.0)
        gate_fired = rng.random() < 0.10

        g.add((w, RDF.type, PSI.Window))
        g.add((w, PSI.hasFeatureVector, fv))
        g.add((w, PSI.hasEntropySignal, es))
        g.add((w, PSI.belongsToPhase, ph))
        g.add((w, PSI.hasRiskScore, rs))
        g.add((es, RDF.type, PSI.EntropySignal))
        g.add((es, PSI.entropyValue, Literal(h_val, datatype=XSD.float)))
        g.add((rs, RDF.type, PSI.RiskScore))
        g.add((rs, PSI.riskValue, Literal(risk_val, datatype=XSD.float)))
        g.add((ph, RDF.type, PSI.AttackPhase))
        if gate_fired:
            g.add((w, PSI.gateFired, Literal(True, datatype=XSD.boolean)))
            g.add((w, PSI.hasExplanation, ex))
            g.add((ex, RDF.type, PSI.Explanation))
            g.add((ex, PSI.suggestsMitigation, mh))
            g.add((mh, RDF.type, PSI.MitigationHint))

    return g


# ------------------- Queries SPARQL -------------------
Q1 = """
PREFIX psi: <http://example.org/psi#>
SELECT ?w ?h WHERE {
  ?w a psi:Window ;
     psi:hasEntropySignal ?es .
  ?es psi:entropyValue ?h .
  FILTER (?h > 3.5)
}
"""

Q2 = """
PREFIX psi: <http://example.org/psi#>
SELECT ?phase ?w ?r WHERE {
  ?w a psi:Window ;
     psi:belongsToPhase ?phase ;
     psi:hasRiskScore ?rs .
  ?rs psi:riskValue ?r .
}
ORDER BY ?phase ?r
"""

Q3 = """
PREFIX psi: <http://example.org/psi#>
SELECT ?w ?ex ?mh WHERE {
  ?w a psi:Window ;
     psi:gateFired ?gf ;
     psi:hasExplanation ?ex .
  ?ex psi:suggestsMitigation ?mh .
}
"""

QUERIES = {"Q1": Q1, "Q2": Q2, "Q3": Q3}


def time_query(g: Graph, q: str, repetitions: int = 11) -> tuple[float, int]:
    timings = []
    n_bindings = 0
    for r in range(repetitions):
        t0 = time.perf_counter()
        rows = list(g.query(q))
        t1 = time.perf_counter()
        timings.append((t1 - t0) * 1000.0)
        n_bindings = len(rows)
    rest = sorted(timings[1:])
    median = rest[len(rest) // 2] if rest else timings[0]
    return median, n_bindings


# ------------------- Driver -------------------
def main():
    results = []
    for n_target in args.sizes:
        print(f"\n=== Building graph ~{n_target} triples ===")
        t0 = time.perf_counter()
        g = build_graph(n_target)
        load_s = time.perf_counter() - t0
        n_actual = len(g)
        print(f"    built {n_actual} triples in {load_s*1000:.1f} ms")

        row = {
            "target_triples": n_target,
            "actual_triples": n_actual,
            "build_ms": load_s * 1000.0,
        }
        for qname, q in QUERIES.items():
            ms, n_b = time_query(g, q, repetitions=args.reps)
            row[f"{qname}_latency_ms"] = ms
            row[f"{qname}_bindings"] = n_b
            print(f"    {qname}: {ms:.2f} ms median, {n_b} bindings")
        results.append(row)

    (OUT_DIR / "sparql_scaling_summary.json").write_text(json.dumps(results, indent=2))
    print(f"\n[sparql] summary -> {OUT_DIR / 'sparql_scaling_summary.json'}")

    # Costruzione tabella LaTeX
    tex = []
    tex.append("% Auto-generated by sparql_scaling.py.")
    tex.append("% In-memory rdflib SPARQL evaluation, 11 reps, median of last 10,")
    tex.append("% on synthetic SEL-aligned graphs (Paper 4 §4 ontology).")
    tex.append("\\begin{tabular}{lrrrrrrr}")
    tex.append("\\toprule")
    tex.append(
        "Graph size & Triples & Build (ms) & "
        "Q$_1$ (ms) & Q$_2$ (ms) & Q$_3$ (ms) & "
        "$|Q_1|$ & $|Q_3|$ \\\\"
    )
    tex.append("\\midrule")
    for r in results:
        tex.append(
            f"{r['target_triples']:,} & {r['actual_triples']:,} & "
            f"{r['build_ms']:.1f} & "
            f"{r['Q1_latency_ms']:.2f} & {r['Q2_latency_ms']:.2f} & {r['Q3_latency_ms']:.2f} & "
            f"{r['Q1_bindings']:,} & {r['Q3_bindings']:,} \\\\"
        )
    tex.append("\\bottomrule")
    tex.append("\\end{tabular}")
    TABLES_OUT.write_text("\n".join(tex))
    print(f"[sparql] table  -> {TABLES_OUT}")


if __name__ == "__main__":
    main()
