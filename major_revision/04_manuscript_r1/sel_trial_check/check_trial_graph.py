"""Verification of the SEL worked example (Sec. 5.5) on the published trial graph.

Source artefact: Cvartic/psi-risk-dt @ af7ccbc, sparql/data/example_data.ttl
(140 triples) and the prototype queries sparql/queries/q{1,2,3}_*.rq, fetched
verbatim from raw.githubusercontent.com. This is a read-only check of numbers
already printed in the submitted manuscript; it is not a new experiment.
Usage: python3 check_trial_graph.py > trial_graph_check.json
"""
import hashlib, json, rdflib

FILES = ["example_data.ttl", "q1_entropy_spike.rq", "q2_rampup_compare.rq", "q3_gate_fired.rq"]
out = {"source": "https://github.com/Cvartic/psi-risk-dt/tree/af7ccbc/sparql",
       "sha256": {f: hashlib.sha256(open(f, "rb").read()).hexdigest() for f in FILES},
       "rdflib": rdflib.__version__}
g = rdflib.Graph(); g.parse("example_data.ttl")
out["triples"] = len(g)
out["windows"] = sorted(int(r[0]) for r in g.query(
    "PREFIX psi: <http://psi-risk-dt.insubria.it/ontology#> SELECT ?id WHERE { ?w a psi:Window ; psi:windowId ?id }"))
for q in FILES[1:]:
    rows = [[str(x) for x in r] for r in g.query(open(q).read())]
    out[q] = {"n_rows": len(rows), "rows": [r[:3] + r[-1:] for r in rows]}
out["window19_scores_direct_lookup"] = [[str(x) for x in r] for r in g.query(
    """PREFIX psi: <http://psi-risk-dt.insubria.it/ontology#>
SELECT ?config ?score WHERE { ?w psi:windowId 19 ; psi:hasRiskScore ?rs .
  ?rs psi:configuration ?config ; psi:scoreValue ?score } ORDER BY ?config""")]
out["phaseName_triples"] = len(list(g.query(
    "PREFIX psi: <http://psi-risk-dt.insubria.it/ontology#> SELECT ?p WHERE { ?p psi:phaseName ?n }")))
print(json.dumps(out, indent=1, ensure_ascii=False))
