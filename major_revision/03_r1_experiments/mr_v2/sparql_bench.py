"""STEP 4 — SPARQL audit + scaling rerun.

Queries are READ FROM FILES (sparql/Q1.rq, Q2.rq, Q3.rq): they are the single
source of truth for benchmark and manuscript.  For the audit, the verbatim
manuscript listings (sparql/legacy/paper_v1_Q*.rq) and the verbatim queries of
scripts/sparql_scaling.py (sparql/legacy/bench_v1_Q*.rq) are run as well.

Graphs:
  canonical : SEL-aligned builder following Table 3 / Sec. 4.4 vocabulary
              (namespace https://insubria.it/psi-risk-dt#), with ground truth
              for correctness checks;
  legacy    : verbatim copy of scripts/sparql_scaling.py::build_graph
              (namespace http://example.org/psi#), used only for bench_v1.
Timing: 1 warm-up + R timed repetitions (default 30) per (size, query, mode),
rdflib in-memory store, time.perf_counter; report median, IQR, mean, SD.
"""
import argparse, json, platform, random, statistics, sys, time
from pathlib import Path
import numpy as np
import rdflib
from rdflib import Graph, Namespace, URIRef, Literal, RDF
from rdflib.namespace import XSD

PSI = Namespace("https://insubria.it/psi-risk-dt#")
LPSI = Namespace("http://example.org/psi#")
ROOT = Path(__file__).resolve().parents[2]
SPARQL_DIR = ROOT / "sparql"
PHASES = ["stable", "ramp-up", "saturation", "burst", "silence"]


def build_canonical(target, seed=42, triples_per_window=24, fire_rate=0.10):
    rng = random.Random(seed)
    g = Graph(); g.bind("psi", PSI)
    for p in PHASES:
        g.add((PSI[f"phase_{p}"], RDF.type, PSI.AttackPhase))
    n_w = max(1, target // triples_per_window)
    truth = {"q1": [], "q3": [], "windows": n_w, "fired": []}
    for i in range(n_w):
        w, fv, es = PSI[f"w{i}"], PSI[f"fv{i}"], PSI[f"es{i}"]
        rn, rs = PSI[f"rn{i}"], PSI[f"rs{i}"]
        cfg = rng.choice(["Shannon;W=64;s=8", "Shannon;W=128;s=4", "Permutation;W=256;s=1"])
        tau = 0.15
        dh = rng.gauss(0, 0.07) + (rng.choice([-1, 1]) * rng.uniform(0.15, 0.6) if rng.random() < 0.08 else 0.0)
        fired = rng.random() < fire_rate
        g.add((w, RDF.type, PSI.Window)); g.add((w, PSI.configuration, Literal(cfg)))
        g.add((w, PSI.tStart, Literal(i * 4, datatype=XSD.integer)))
        g.add((w, PSI.hasFeatureVector, fv)); g.add((fv, RDF.type, PSI.FeatureVector))
        g.add((w, PSI.hasEntropySignal, es)); g.add((es, RDF.type, PSI.EntropySignal))
        g.add((es, PSI.deltaH, Literal(dh, datatype=XSD.double))); g.add((es, PSI.tauS, Literal(tau, datatype=XSD.double)))
        g.add((es, PSI.estimator, Literal(cfg.split(";")[0])))
        g.add((w, PSI.belongsToPhase, PSI[f"phase_{PHASES[i % len(PHASES)]}"]))
        g.add((w, PSI.gateFired, Literal(fired, datatype=XSD.boolean)))
        for r, conf in ((rn, "neural"), (rs, "nesy")):
            g.add((r, RDF.type, PSI.RiskScore)); g.add((r, PSI.onWindow, w)); g.add((r, PSI.configuration, Literal(conf)))
            g.add((r, PSI.scoreValue, Literal(rng.random(), datatype=XSD.double)))
            g.add((r, PSI.priority, Literal(rng.randint(1, 5), datatype=XSD.integer)))
            g.add((r, PSI.provenance, Literal(f"{conf}@{cfg}")))
        if fired:
            ex, mh = PSI[f"ex{i}"], PSI[f"mh{i}"]
            g.add((rs, PSI.hasExplanation, ex)); g.add((ex, RDF.type, PSI.Explanation)); g.add((ex, PSI.text, Literal(f"gate fired on w{i}")))
            g.add((rs, PSI.hasMitigation, mh)); g.add((mh, RDF.type, PSI.MitigationHint)); g.add((mh, PSI.text, Literal("rate-limit")))
            if rng.random() < 0.5:
                g.add((mh, PSI.referencedCVE, Literal("CVE-2017-0144")))
            truth["fired"].append(str(w))
        if abs(dh) > tau:
            truth["q1"].append((str(w), dh))
    truth["q1_count"] = len(truth["q1"]); truth["q3_count_full"] = 2 * len(truth["fired"])
    truth["q2_count_full"] = n_w
    return g, truth


def build_legacy(target_triples, seed=42):  # verbatim logic of scripts/sparql_scaling.py
    rng = random.Random(seed); g = Graph(); g.bind("psi", LPSI)
    for i in range(max(1, target_triples // 10)):
        w = URIRef(f"http://example.org/psi#w{i}"); fv = URIRef(f"http://example.org/psi#fv{i}")
        es = URIRef(f"http://example.org/psi#es{i}"); ph = URIRef(f"http://example.org/psi#ph{i % 4}")
        rs = URIRef(f"http://example.org/psi#rs{i}"); ex = URIRef(f"http://example.org/psi#ex{i}")
        mh = URIRef(f"http://example.org/psi#mh{i % 8}")
        h_val = rng.uniform(0.0, 5.0); risk_val = rng.uniform(0.0, 1.0); gate_fired = rng.random() < 0.10
        g.add((w, RDF.type, LPSI.Window)); g.add((w, LPSI.hasFeatureVector, fv)); g.add((w, LPSI.hasEntropySignal, es))
        g.add((w, LPSI.belongsToPhase, ph)); g.add((w, LPSI.hasRiskScore, rs)); g.add((es, RDF.type, LPSI.EntropySignal))
        g.add((es, LPSI.entropyValue, Literal(h_val, datatype=XSD.float))); g.add((rs, RDF.type, LPSI.RiskScore))
        g.add((rs, LPSI.riskValue, Literal(risk_val, datatype=XSD.float))); g.add((ph, RDF.type, LPSI.AttackPhase))
        if gate_fired:
            g.add((w, LPSI.gateFired, Literal(True, datatype=XSD.boolean))); g.add((w, LPSI.hasExplanation, ex))
            g.add((ex, RDF.type, LPSI.Explanation)); g.add((ex, LPSI.suggestsMitigation, mh)); g.add((mh, RDF.type, LPSI.MitigationHint))
    return g


def timeit(g, q, reps, bindings=None):
    kw = {"initBindings": bindings} if bindings else {}
    rows = list(g.query(q, **kw))  # warm-up (discarded)
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter(); rows = list(g.query(q, **kw)); ts.append((time.perf_counter() - t0) * 1000)
    a = np.array(ts)
    return {"median_ms": float(np.median(a)), "q1_ms": float(np.percentile(a, 25)), "q3_ms": float(np.percentile(a, 75)),
            "iqr_ms": float(np.percentile(a, 75) - np.percentile(a, 25)), "mean_ms": float(a.mean()), "sd_ms": float(a.std(ddof=1)),
            "min_ms": float(a.min()), "max_ms": float(a.max()), "reps": reps, "n_bindings": len(rows), "raw_ms": ts}, rows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sizes", nargs="+", type=int, default=[1000, 5000, 10000, 25000, 50000])
    ap.add_argument("--reps", type=int, default=30); ap.add_argument("--out", required=True)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    canon = {q: (SPARQL_DIR / f"{q}.rq").read_text() for q in ("Q1", "Q2", "Q3")}
    paper = {q: (SPARQL_DIR / "legacy" / f"paper_v1_{q}.rq").read_text() for q in ("Q1", "Q2", "Q3")}
    bench = {q: (SPARQL_DIR / "legacy" / f"bench_v1_{q}.rq").read_text() for q in ("Q1", "Q2", "Q3")}
    res = {"meta": {"command": " ".join(sys.argv), "rdflib": rdflib.__version__, "python": platform.python_version(),
                    "machine": platform.machine(), "reps": a.reps, "warmup": 1}, "runs": [], "correctness": []}
    for n in a.sizes:
        g, truth = build_canonical(n)
        nt = len(g); fired_w = URIRef(truth["fired"][0]) if truth["fired"] else None
        print(f"[sparql] canonical target={n} triples={nt} windows={truth['windows']}", flush=True)
        for qset, qs in (("canonical_v1", canon), ("paper_v1", paper)):
            for q, txt in qs.items():
                modes = [("full", None)] + ([("point", {"w": fired_w})] if q in ("Q2", "Q3") else [])
                for mode, b in modes:
                    st, rows = timeit(g, txt, a.reps, b)
                    st.update(graph="canonical", query_set=qset, query=q, mode=mode, target=n, triples=nt)
                    res["runs"].append(st)
                    if mode == "full":
                        exp = {"Q1": truth["q1_count"], "Q2": truth["q2_count_full"], "Q3": truth["q3_count_full"]}[q]
                        chk = {"target": n, "query_set": qset, "query": q, "expected": exp, "returned": len(rows)}
                        if q == "Q1":
                            vals = [float(r[2] if qset == "canonical_v1" else r[1]) for r in rows]
                            chk["sorted_by_abs_desc"] = all(abs(vals[i]) >= abs(vals[i + 1]) for i in range(len(vals) - 1))
                        if q == "Q3":
                            chk["only_gate_fired"] = all(str(r[0]) in set(truth["fired"]) for r in rows) if qset == "canonical_v1" else "n/a (no ?w projected)"
                        res["correctness"].append(chk)
        gl = build_legacy(n); ntl = len(gl)
        for q, txt in bench.items():
            st, rows = timeit(gl, txt, a.reps)
            st.update(graph="legacy", query_set="bench_v1", query=q, mode="full", target=n, triples=ntl)
            res["runs"].append(st)
    # log-log slopes
    slopes = []
    for key in sorted({(r["graph"], r["query_set"], r["query"], r["mode"]) for r in res["runs"]}):
        rs = [r for r in res["runs"] if (r["graph"], r["query_set"], r["query"], r["mode"]) == key]
        x = np.log([r["triples"] for r in rs]); y = np.log([r["median_ms"] for r in rs])
        if len(rs) >= 2:
            b = np.polyfit(x, y, 1)[0]
            slopes.append({"graph": key[0], "query_set": key[1], "query": key[2], "mode": key[3], "loglog_slope": float(b)})
    res["slopes"] = slopes
    (out / "sparql_bench_raw.json").write_text(json.dumps(res, indent=1))
    import csv
    with open(out / "sparql_bench_summary.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["graph", "query_set", "query", "mode", "target", "triples", "n_bindings", "median_ms", "q1_ms", "q3_ms", "iqr_ms", "mean_ms", "sd_ms", "min_ms", "max_ms", "reps"])
        wr.writeheader()
        for r in res["runs"]:
            wr.writerow({k: r[k] for k in wr.fieldnames})
    print(json.dumps(slopes, indent=1)); print(json.dumps(res["correctness"], indent=1))


if __name__ == "__main__":
    main()
