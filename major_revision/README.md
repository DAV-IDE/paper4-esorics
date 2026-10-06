# Paper 4 — Major Revision R1 (MDPI Future Internet, manuscript futureinternet-4592809)

Reproducibility artefacts of the revised manuscript "A Parameterised Entropy Control Plane and
SPARQL-Queryable Explanations for Auditable Neurosymbolic Digital Twin Security"
(R. Pazzi, D. Facheris, D. Tosi). Branch `major-revision-r1`, based on `mdpi-provenance-cleanup` @ c1b04d7
plus the real-data files of `real-data-integration-tau-sweep` @ d828a80.

## Layout

| Path | Content |
|---|---|
| `03_r1_experiments/mr/`, `mr_v2/` | Single implementation of Algorithm 1 and all experiment scripts (`mr_v2` adds the packet-capture pipeline) |
| `03_r1_experiments/mr_v2/pcap_to_per_second.py` | Deterministic per-second transformation of the official `Friday-WorkingHours.pcap` |
| `03_r1_experiments/pcap_provenance/` | Provenance record of the capture (MD5/SHA-256, headers) |
| `03_r1_experiments/results/` | Frozen raw results (CSV/JSON) |
| `03_r1_experiments/logs/`, `logs_v2/` | Run logs |
| `03_r1_experiments/SHA256SUMS_R1*.txt` | Checksum manifests of the frozen results |
| `03_r1_experiments/docs/METRICS_DEFINITIONS.md` | Metric definitions (t_event, t_detect, d, d_win, FP_A, AUC mapping) |
| `03_r1_experiments/sparql/Q1.rq`, `Q2.rq`, `Q3.rq` | Canonical SPARQL queries (also in `04_manuscript_r1/sparql/` and `/sparql/`) |
| `04_manuscript_r1/scripts/build_tables_r1.py` | Regenerates every table (`tables_r1/`) and the Pareto figure from the frozen results |
| `04_manuscript_r1/scripts/build_fig_stable_diag.py` | Regenerates Figure 1 |
| `04_manuscript_r1/sel_trial_check/` | Re-execution of the SEL worked example on the published trial graph (commit af7ccbc) |
| `04_manuscript_r1/SAFE_CLAIM_MATRIX_R1.md` | Claim-to-artefact matrix |

Canonical query digests (SHA-256): Q1 `1d82fdd3…`, Q2 `3d3aa7a7…`, Q3 `7eea6934…` (full values in `RELEASE_SHA256SUMS.txt`).

## Verify

```bash
cd major_revision && sha256sum -c RELEASE_SHA256SUMS.txt
cd 03_r1_experiments && for m in SHA256SUMS_R1*.txt; do sha256sum -c --ignore-missing "$m"; done
```

The `SHA256SUMS_R1*.txt` manifests are the frozen records of 2026-10-03/06 and are kept unchanged. They also list four
files that are deliberately not in this public release (`RELEASE_EXCLUDED.txt`): three internal working notes and the
derived per-second series, which is regenerated from the capture as shown below. Hence `--ignore-missing`.

## Regenerate the per-second series from the official capture

```bash
# Friday-WorkingHours.pcap from the CIC (see "Not included"); MD5 7366c552425956e610bd69f57feb7e7a
cd major_revision/03_r1_experiments/mr_v2
python3 pcap_to_per_second.py --pcap /path/to/Friday-WorkingHours.pcap \
  --out ../results/01_real_second_v2/friday_full_per_second.csv
sha256sum ../results/01_real_second_v2/friday_full_per_second.csv
# expected: 6559dce4219bc30487f32ede42e172a8d3dc1a77277419e3af917de3c4e57c7f
#           (output_sha256 in results/01_real_second_v2/friday_full_per_second.manifest.json)
```

Script SHA-256 `9fde8700e675eba985a345c4e1dbc251dcc9930a6d087c26d2619ac47b7562a0`; source capture SHA-256
`beff0dcce1eebc9b2454582f4dc8ed0ba0112b2c619a710bf03af93147254cd0` (both also in the manifest and in `pcap_provenance/`).

## Regenerate tables and figures (no experiment is re-run)

`build_tables_r1.py` reads the per-second series for the capture facts reported in the text, so regenerate it first
(previous section). All other inputs are in this release.

```bash
cd major_revision/04_manuscript_r1
python3 scripts/build_tables_r1.py
python3 scripts/build_fig_stable_diag.py
```

## Not included

- The CIC-IDS2017 packet capture is not redistributed; obtain it from the Canadian Institute for Cybersecurity
  (https://cicresearch.ca/CICDataset/CIC-IDS-2017/) and check MD5 `7366c552425956e610bd69f57feb7e7a`.
  The derived per-second series (`friday_full_per_second.csv`) is not redistributed either; it is regenerated
  deterministically from the capture (see above), and its checksum is in the manifest next to its expected path.
- The minute-level flow data (Hugging Face mirror `bvsam/cic-ids-2017`, unofficial; file `Friday_TrafficLabelling.parquet`)
  are not redistributed; the SHA-256 of the file used is recorded in `03_r1_experiments/FREEZE_R1_2026-10-03.md` and
  `03_r1_experiments/results/01_real_minute/real_minute_manifest.json`.
- RDF graphs used by the SPARQL benchmark are regenerated deterministically by the builder; their hashes are in the raw results.
- Manuscript sources, review correspondence and internal working notes are not part of this release.

Dataset citation: I. Sharafaldin, A. H. Lashkari, A. A. Ghorbani, "Toward Generating a New Intrusion Detection Dataset
and Intrusion Traffic Characterization", ICISSP 2018, doi:10.5220/0006639801080116.
