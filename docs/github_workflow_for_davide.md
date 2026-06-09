# GitHub Workflow — Operational Guide for Davide

This is a focused operational handover for **Davide Facheris** to set up the GitHub repository so that Paper 4 stays reproducible across revisions and reviewer rounds.

## 0. One-time repository setup

```bash
# Create the repo on GitHub UI: paper4-eal-sel-reproducibility (private initially)
# Clone locally:
git clone git@github.com:<org>/paper4-eal-sel-reproducibility.git
cd paper4-eal-sel-reproducibility

# Drop the kit contents in (everything from this zip)
unzip ~/paper4_repro_kit.zip -d .

# First commit
git add .
git commit -m "v4.0.0 — initial reproducibility kit"
git tag -a v4.0.0 -m "Paper 4 v4 — real experiments, three placeholders filled"
git push origin main --tags
```

## 1. Recommended branch model

| Branch | Purpose |
|--------|---------|
| `main` | Always-reproducible state. Every commit must pass `make all`. |
| `paper-revision/*` | Per-reviewer-round LaTeX edits. Merge to `main` once experiments still pass. |
| `experiment/*` | New experiment scripts (new estimators, new datasets). |
| `archive/v1-v3` | Frozen old versions of the paper (do NOT touch `main_v[123].tex` on main). |

## 2. CI — GitHub Actions

Create `.github/workflows/reproduce.yml`:

```yaml
name: Reproduce Paper 4
on: [push, pull_request]

jobs:
  reproduce:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: make all
      - run: |
          # Check that the regenerated tables match the committed ones
          git diff --exit-code tables/ figures/ || \
            (echo "ERROR: regenerated artefacts differ from committed"; exit 1)
      - uses: actions/upload-artifact@v4
        with:
          name: regenerated-artefacts
          path: |
            tables/
            figures/
            results/
```

This ensures **every push** verifies that `make all` still produces bit-for-bit identical Tables 8 and 9 and the Pareto figure. If a script change accidentally changes the numbers, CI fails.

## 3. Pre-commit hooks (recommended)

Install `pre-commit` and add `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
        args: ['--maxkb=1000']  # block CSVs > 1 MB
      - id: check-yaml
      - id: check-json
  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        files: ^scripts/.*\.py$
```

This blocks accidental commits of large CSVs (the proxy is 20 MB — regenerate it instead).

## 4. Workflow for "I changed something"

### Scenario A — Edit LaTeX only (typos, prose, comments from reviewers)

```bash
git checkout -b paper-revision/r1-reviewer-A
# edit paper/main_v4.tex
git commit -am "address Reviewer A comment on §5.3"
git push -u origin paper-revision/r1-reviewer-A
# Open PR; CI passes if numbers unchanged → merge to main
```

### Scenario B — Add a new experiment (e.g., a 4th entropy estimator)

```bash
git checkout -b experiment/add-tsallis-entropy
# edit scripts/eal_factorial.py to add the new estimator
make eal table          # regenerate Table 8 + Pareto
# Update paper/main_v4.tex to describe the new estimator (1 sentence + table row)
git commit -am "add Tsallis estimator to EAL grid (12-row table, Pareto unchanged)"
# Open PR with CI green; merge to main; tag v4.1.0
```

### Scenario C — Swap proxy → real CIC-IDS2017 CSV

```bash
git checkout -b experiment/real-cic-ids2017
# Download the real CSV manually (NOT committed — see .gitignore)
make clean && make REAL=1 all
# This regenerates tables/figures with REAL numbers
git diff tables/ figures/     # inspect every changed digit
# Decide: do real numbers tell the same qualitative story?
# If YES — commit the new tables and tag v4.0.0-real
# If NO — write a CHANGELOG entry quantifying every divergence; discuss
git commit -am "v4.0.0-real — Table 8 + Pareto + Table 9 from real CIC-IDS2017"
git tag -a v4.0.0-real -m "Real CIC-IDS2017 — see CHANGELOG.md for deltas"
```

## 5. Releasing for submission

```bash
# Before pressing "Submit" on Overleaf / EasyChair:
git checkout main
git pull
make clean && make all              # verify from scratch
cd paper && pdflatex main_v4.tex    # compile
# Sanity-check the PDF matches what you'll submit
git tag -a v4.0.0-esorics-submitted -m "Frozen state at ESORICS submission"
git push --tags
```

The tagged commit becomes the **immutable record** of what was submitted. Reviewers asking "what code produced Table 8?" get a one-line answer: `git checkout v4.0.0-esorics-submitted`.

## 6. Handling reviewer comments

For each reviewer comment that requires a code change:

1. Open an issue: `R1.3 — reviewer asks about FPR at k=2`
2. Create a branch: `git checkout -b reviewer-response/r1-3`
3. Make the change (e.g., add a `--k` flag to `baseline_zscore.py`)
4. Regenerate artefacts: `make all`
5. Update `paper/main_v4.tex` and `CHANGELOG.md`
6. Open PR linked to the issue
7. Merge; close issue; tag minor version

## 7. Repository hygiene rules

* **NEVER commit `data/cic_proxy_friday_ddos.csv`** — it is regenerated deterministically.
* **NEVER commit `data/cic_real_friday_ddos.csv`** — licence does not allow redistribution.
* **NEVER edit `tables/real_data.tex` or `tables/sparql_scaling.tex` by hand** — they are generated.
* **NEVER edit `figures/pareto_design_space.pdf` in Illustrator** — regenerate from `scripts/build_table_and_pareto.py`.
* **DO commit** `results/` (last good run, helps reviewers without running anything).
* **DO commit** `paper/main_v4.tex` (it is the human-edited artefact).

## 8. Roberto ↔ Davide coordination

Suggested split:
* **Roberto** — owns `paper/main_v4.tex` (writes prose, responds to reviewers).
* **Davide** — owns `scripts/`, `Makefile`, CI, repository hygiene, releases.
* Both review each other's PRs before merge to `main`.

Anything in `tables/`, `figures/`, `results/` is **generated** — neither edits by hand.

## 9. Emergency rollback

If a bad commit breaks reproduction:

```bash
git revert <bad-sha>
make clean && make all       # verify rollback works
git push
```

If `main` is corrupted beyond `git revert`, the previous good tag is always there:

```bash
git reset --hard v4.0.0
git push --force-with-lease   # use with care, coordinate with Roberto first
```

## 10. Contact

Questions on this workflow → Roberto. Questions on the scripts → first check `REPRODUCIBILITY.md`, then ping Roberto.
