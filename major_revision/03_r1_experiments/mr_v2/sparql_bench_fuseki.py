"""STEP 4 — SPARQL audit + scaling rerun on Apache Jena Fuseki (primary engine,
consistent with the manuscript), rdflib kept only as secondary diagnostic.

Single source of truth: sparql/Q1.rq, Q2.rq, Q3.rq are read verbatim.  The
point-lookup mode ("for a chosen window") appends a SPARQL 1.1 trailing
ValuesClause `VALUES ?w { <iri> }` to the unchanged file text.
Also run, for the audit: sparql/legacy/paper_v1_Q*.rq (verbatim manuscript
listings) on the canonical graph, and sparql/legacy/bench_v1_Q*.rq (verbatim
scripts/sparql_scaling.py queries) on the legacy graph builder.

Per (engine, graph size, query set, query, mode): 1 warm-up + R timed
repetitions (default 30), client-side round-trip latency (HTTP POST
application/sparql-query, JSON results fully parsed), median/IQR/mean/SD.
Fuseki: in-memory read-only dataset loaded from a Turtle file
(fuseki-server --file), one server per graph, JVM restarted per graph.
rdflib: per-query wall-clock cap; queries whose first execution exceeds the
cap are recorded as CENSORED (not dropped).
"""
import argparse, json, os, platform, signal, subprocess, sys, time, hashlib, csv
from pathlib import Path
import numpy as np
import requests
from sparql_bench import build_canonical, build_legacy, SPARQL_DIR

QS = ("Q1", "Q2", "Q3")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


STORE = "mem"


def start_fuseki(fuseki_dir, ttl, port, log):
    if STORE == "tdb2":
        import shutil
        loc = Path(log).with_suffix(".tdb2"); shutil.rmtree(loc, ignore_errors=True); loc.mkdir(parents=True)
        cmd = [str(Path(fuseki_dir) / "fuseki-server"), "--tdb2", f"--loc={loc}", "--update", f"--port={port}", "/ds"]
    else:
        cmd = [str(Path(fuseki_dir) / "fuseki-server"), f"--file={ttl}", f"--port={port}", "/ds"]
    env = dict(os.environ, JVM_ARGS="-Xmx3g")
    p = subprocess.Popen(cmd, stdout=open(log, "w"), stderr=subprocess.STDOUT, env=env, start_new_session=True)
    for _ in range(240):
        try:
            if requests.get(f"http://localhost:{port}/$/ping", timeout=2).ok:
                if STORE == "tdb2":  # load via Graph Store Protocol into the default graph, persisted in TDB2
                    r = requests.post(f"http://localhost:{port}/ds/data?default", data=Path(ttl).read_bytes(),
                                      headers={"Content-Type": "text/turtle"}, timeout=600)
                    r.raise_for_status()
                return p, cmd
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("fuseki did not start")


def stop(p):
    try:
        os.killpg(p.pid, signal.SIGTERM); p.wait(timeout=20)
    except Exception:
        os.killpg(p.pid, signal.SIGKILL)


def fuseki_query(port, q, timeout):
    r = requests.post(f"http://localhost:{port}/ds/query", data=q.encode(),
                      headers={"Content-Type": "application/sparql-query", "Accept": "application/sparql-results+json"}, timeout=timeout)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def bench(fn, reps, cap_s):
    t0 = time.perf_counter(); rows = fn(); first = time.perf_counter() - t0  # warm-up
    if first > cap_s:
        return {"censored": True, "warmup_s": first, "reps": 0, "n_bindings": len(rows)}, rows
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter(); rows = fn(); ts.append((time.perf_counter() - t0) * 1000)
    a = np.array(ts)
    return {"censored": False, "warmup_s": first, "median_ms": float(np.median(a)), "q1_ms": float(np.percentile(a, 25)),
            "q3_ms": float(np.percentile(a, 75)), "iqr_ms": float(np.subtract(*np.percentile(a, [75, 25]))),
            "mean_ms": float(a.mean()), "sd_ms": float(a.std(ddof=1)), "min_ms": float(a.min()), "max_ms": float(a.max()),
            "reps": reps, "n_bindings": len(rows), "raw_ms": ts}, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", type=int, default=[1000, 5000, 10000, 25000, 50000])
    ap.add_argument("--reps", type=int, default=30); ap.add_argument("--out", required=True)
    ap.add_argument("--fuseki", required=True); ap.add_argument("--port", type=int, default=3399)
    ap.add_argument("--rdflib-cap", type=float, default=20.0, help="censor rdflib query if warm-up exceeds this (s)")
    ap.add_argument("--skip-rdflib", action="store_true")
    ap.add_argument("--store", choices=["mem", "tdb2"], default="mem")
    a = ap.parse_args(); global STORE; STORE = a.store; out = Path(a.out); (out / "graphs").mkdir(parents=True, exist_ok=True); (out / "logs").mkdir(exist_ok=True)
    files = {**{f"canonical_v1/{q}": SPARQL_DIR / f"{q}.rq" for q in QS},
             **{f"paper_v1/{q}": SPARQL_DIR / "legacy" / f"paper_v1_{q}.rq" for q in QS},
             **{f"bench_v1/{q}": SPARQL_DIR / "legacy" / f"bench_v1_{q}.rq" for q in QS}}
    text = {k: v.read_text() for k, v in files.items()}
    meta = {"command": " ".join(sys.argv), "python": platform.python_version(), "machine": platform.machine(),
            "nproc": os.cpu_count(), "java": subprocess.run(["java", "-version"], capture_output=True, text=True).stderr.splitlines()[0],
            "fuseki_dir": a.fuseki, "fuseki_jar_sha256": sha(Path(a.fuseki) / "fuseki-server.jar"),
            "query_sha256": {k: sha(v) for k, v in files.items()}, "reps": a.reps, "warmup": 1,
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    runs, corr = [], []
    censored_keys = set()
    for n in a.sizes:
        g, truth = build_canonical(n); gl = build_legacy(n)
        ttl = out / "graphs" / f"canonical_{n}.ttl"; ttl_l = out / "graphs" / f"legacy_{n}.ttl"
        g.serialize(ttl, format="turtle"); gl.serialize(ttl_l, format="turtle")
        fired = truth["fired"][0]
        jobs = [("canonical", ttl, g, ["canonical_v1", "paper_v1"]), ("legacy", ttl_l, gl, ["bench_v1"])]
        for gname, path, graph, sets in jobs:
            p, cmd = start_fuseki(a.fuseki, path, a.port, out / "logs" / f"fuseki_{gname}_{n}.log")
            try:
                for qs in sets:
                    for q in QS:
                        modes = [("full", "")]
                        if gname == "canonical" and q in ("Q2", "Q3"):
                            modes.append(("point", f"\nVALUES ?w {{ <{fired}> }}\n"))
                        for mode, suffix in modes:
                            qt = text[f"{qs}/{q}"] + suffix
                            st, rows = bench(lambda: fuseki_query(a.port, qt, 600), a.reps, 600)
                            st.update(engine="fuseki" if a.store == "mem" else "fuseki_tdb2", graph=gname, query_set=qs, query=q, mode=mode, target=n, triples=len(graph),
                                      ttl_sha256=sha(path))
                            runs.append(st)
                            print(f"[fuseki] n={n} {gname} {qs} {q} {mode} median={st.get('median_ms', float('nan')):.2f}ms bindings={st['n_bindings']}", flush=True)
                            if gname == "canonical" and mode == "full":
                                exp = {"Q1": truth["q1_count"], "Q2": truth["q2_count_full"], "Q3": truth["q3_count_full"]}[q]
                                c = {"engine": "fuseki" if a.store == "mem" else "fuseki_tdb2", "target": n, "query_set": qs, "query": q, "expected": exp, "returned": len(rows)}
                                if q == "Q1":
                                    v = [float(r["dh"]["value"]) for r in rows]
                                    c["sorted_by_abs_desc"] = all(abs(v[i]) >= abs(v[i + 1]) for i in range(len(v) - 1))
                                if q == "Q3":
                                    c["only_gate_fired"] = (all(r["w"]["value"] in set(truth["fired"]) for r in rows) if qs == "canonical_v1" else "not checkable (?w not projected)")
                                corr.append(c)
            finally:
                stop(p)
            if not a.skip_rdflib:
                for qs in sets:
                    for q in QS:
                        qt = text[f"{qs}/{q}"]
                        if (gname, qs, q) in censored_keys:  # monotone censoring: larger graphs are not re-run
                            st = {"censored": True, "warmup_s": float("nan"), "reps": 0, "n_bindings": None,
                                  "note": f"not executed: censored at smaller size (>{a.rdflib_cap}s)"}
                            st.update(engine="rdflib", graph=gname, query_set=qs, query=q, mode="full", target=n, triples=len(graph))
                            runs.append(st); print(f"[rdflib] n={n} {gname} {qs} {q} SKIPPED (censored earlier)", flush=True)
                            continue
                        st, rows = bench(lambda: list(graph.query(qt)), a.reps, a.rdflib_cap)
                        if st["censored"]:
                            censored_keys.add((gname, qs, q))
                        st.update(engine="rdflib", graph=gname, query_set=qs, query=q, mode="full", target=n, triples=len(graph))
                        runs.append(st)
                        print(f"[rdflib] n={n} {gname} {qs} {q} censored={st['censored']} warmup={st['warmup_s']:.2f}s", flush=True)
        json.dump({"meta": meta, "runs": runs, "correctness": corr}, open(out / "sparql_fuseki_raw.json", "w"), indent=1)
    slopes = []
    for key in sorted({(r["engine"], r["graph"], r["query_set"], r["query"], r["mode"]) for r in runs}):
        rs = [r for r in runs if (r["engine"], r["graph"], r["query_set"], r["query"], r["mode"]) == key and not r["censored"]]
        if len(rs) >= 2:
            b = np.polyfit(np.log([r["triples"] for r in rs]), np.log([r["median_ms"] for r in rs]), 1)[0]
            slopes.append(dict(zip(["engine", "graph", "query_set", "query", "mode"], key), loglog_slope=float(b), n_sizes=len(rs)))
    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    json.dump({"meta": meta, "runs": runs, "correctness": corr, "slopes": slopes}, open(out / "sparql_fuseki_raw.json", "w"), indent=1)
    keys = ["engine", "graph", "query_set", "query", "mode", "target", "triples", "n_bindings", "censored", "warmup_s", "median_ms", "q1_ms", "q3_ms", "iqr_ms", "mean_ms", "sd_ms", "min_ms", "max_ms", "reps"]
    with open(out / "sparql_fuseki_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); [w.writerow(r) for r in runs]
    print(json.dumps(slopes, indent=1)); print(json.dumps(corr, indent=1))


if __name__ == "__main__":
    main()
