"""Read-only facts on the two tabular inputs (real CIC CSV mirror, proxy CSV) used in Table 'dataset comparison'.
Usage: python3 dataset_facts.py /tmp/repo/data > ../tables_r1/dataset_facts.json"""
import hashlib, json, sys, pandas as pd
D = sys.argv[1]
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
out = {}
p = f"{D}/Friday_TrafficLabelling.parquet"; r = pd.read_parquet(p); lab = [c for c in r.columns if c.strip().lower() == "label"][0]
vc = r[lab].str.strip().value_counts()
out["real_csv"] = {"file": p, "sha256": sha(p), "rows": len(r), "labels": vc.to_dict(), "ddos_frac": float(vc.get("DDoS", 0) / len(r))}
p = f"{D}/cic_proxy_friday_ddos.csv"; x = pd.read_csv(p); lab = [c for c in x.columns if c.strip().lower() == "label"][0]
vc = x[lab].str.strip().value_counts()
out["proxy_csv"] = {"file": p, "sha256": sha(p), "rows": len(x), "labels": vc.to_dict(), "ddos_frac": float(vc.get("DDoS", 0) / len(x))}
print(json.dumps(out, indent=1, default=str))
