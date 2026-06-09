# Proxy vs Real CIC-IDS2017

## Why a proxy?

The published CIC-IDS2017 dataset requires registration and licence acceptance from UNB, which makes a fully self-contained reproduction kit impossible if we hard-depended on the real CSV. The proxy lets reviewers verify the **pipeline** without dataset access; the real CSV swap is a single config change.

## What the proxy is

`scripts/generate_cic_proxy.py` produces a 246k-flow stream **aligned to the published marginals** of CIC-IDS2017 *Friday-WorkingHours-Afternoon-DDos*:

| Property | Proxy value | CIC-IDS2017 reference |
|----------|-------------|-----------------------|
| Total flows | 246,078 | ~225k (published) |
| BENIGN / DDoS | 158,285 / 87,793 | published ratio |
| Time window | 13:00–17:00 | 13:00–17:00 |
| Attack core | 15:55–16:15 | 15:56–16:16 |
| Mean flow duration (BENIGN) | matches | matches |
| Destination port entropy (BENIGN) | matches | matches |

What the proxy does **not** replicate:
* Exact per-packet timings (we work at flow level)
* Joint distributions between features (only marginals)
* PCAP-level adversarial artefacts

## What the proxy is NOT

The proxy is **not a substitute for the real CSV** for any claim that requires joint feature distributions or per-packet timing. The paper is explicit about this in:
* Header changelog (lines 45–56 of `main_v4.tex`)
* §5.2 "Dataset and pipeline" paragraph
* Caption of Table 8
* Caption of Pareto figure
* §5.4 "Measurement protocol and proxy declaration"

## How to swap in the real CSV

```bash
# 1. Register and download from https://www.unb.ca/cic/datasets/ids-2017.html
# 2. Place the file at:
mv ~/Downloads/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv data/

# 3. Run the ingester (normalises ~80 columns → 9-column schema)
python scripts/ingest_cicids2017_friday_ddos.py \
    --input data/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv \
    --out data/cic_real_friday_ddos.csv

# 4. Re-run with REAL=1
make clean && make REAL=1 all
```

## Honesty commitment

From `main_v4.tex` §5.4:

> "Any change in the qualitative ordering of estimators between proxy and real CSV will be reported as an empirical finding, never silently edited away."

If the real CSV produces a different Pareto front, a different miss/detect split for EAL, or different detection delays, the kit's job is to **document the delta**, not to hide it. The repository tag `v4.0.0-real` will be cut from the real-CSV run with a `CHANGELOG.md` entry quantifying every divergence.
