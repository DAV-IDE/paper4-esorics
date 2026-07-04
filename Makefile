# Paper 4 — Reproducibility Makefile
# Usage:
#   make all          # full pipeline (proxy mode)
#   make REAL=1 all   # use real CIC-IDS2017 CSV (must be placed manually)
#   make clean        # remove generated files
#   make smoke        # quick end-to-end sanity check

PYTHON  ?= python3
SEED    ?= 20260606

# Ottiene il percorso assoluto della directory corrente (la radice del kit)
ROOT_DIR := $(shell pwd)

DATA    := $(ROOT_DIR)/data
RESULTS := $(ROOT_DIR)/results
TABLES  := $(ROOT_DIR)/tables
FIGURES := $(ROOT_DIR)/figures

ifeq ($(REAL),1)
  INPUT_CSV := $(DATA)/cic_real_friday_ddos.csv
  INPUT_LABEL := real
else
  INPUT_CSV := $(DATA)/cic_proxy_friday_ddos.csv
  INPUT_LABEL := proxy
endif

.PHONY: all data baseline eal table sparql smoke clean help real-rerun tau-sweep real-all

help:
	@echo "Paper 4 reproducibility targets:"
	@echo "  make all          - run full pipeline (proxy mode, default)"
	@echo "  make REAL=1 all   - run on real CIC-IDS2017 CSV"
	@echo "  make data         - regenerate the proxy CSV"
	@echo "  make baseline     - run 3-feature z-score baseline"
	@echo "  make eal          - run 3x3 EAL factorial grid"
	@echo "  make table        - rebuild Table 8 + Pareto figure"
	@echo "  make sparql       - run SPARQL scaling experiments"
	@echo "  make smoke        - end-to-end smoke test (5 s)"
	@echo "  make clean        - remove generated artefacts"

all: data baseline eal table sparql
	@echo ""
	@echo "=== Pipeline complete ($(INPUT_LABEL) mode) ==="
	@echo "  - $(TABLES)/real_data.tex"
	@echo "  - $(TABLES)/sparql_scaling.tex"
	@echo "  - $(FIGURES)/pareto_design_space.pdf"
	@echo ""
	@echo "Next: cd paper && pdflatex main_v4.tex"

data: $(INPUT_CSV)

$(DATA)/cic_proxy_friday_ddos.csv:
	@mkdir -p $(DATA)
	$(PYTHON) scripts/generate_cic_proxy.py --seed $(SEED) --out $@

baseline: $(RESULTS)/$(INPUT_LABEL)/baseline_zscore_summary.json

$(RESULTS)/$(INPUT_LABEL)/baseline_zscore_summary.json: $(INPUT_CSV)
	@mkdir -p $(RESULTS)/$(INPUT_LABEL)
	$(PYTHON) scripts/baseline_zscore.py --input $< --out $(RESULTS)/$(INPUT_LABEL)

eal: $(RESULTS)/eal/eal_factorial_summary.json

$(RESULTS)/eal/eal_factorial_summary.json: $(INPUT_CSV)
	@mkdir -p $(RESULTS)/eal
	$(PYTHON) scripts/eal_factorial.py --input $< --out $(RESULTS)/eal

table: $(TABLES)/real_data.tex

$(TABLES)/real_data.tex: $(RESULTS)/$(INPUT_LABEL)/baseline_zscore_summary.json $(RESULTS)/eal/eal_factorial_summary.json
	@mkdir -p $(TABLES) $(FIGURES)
	$(PYTHON) scripts/build_table_and_pareto.py \
		--baseline $(RESULTS)/$(INPUT_LABEL)/baseline_zscore_summary.json \
		--eal      $(RESULTS)/eal/eal_factorial_summary.json \
		--tex      $(TABLES)/real_data.tex \
		--fig      $(FIGURES)/pareto_design_space

sparql: $(TABLES)/sparql_scaling.tex

$(TABLES)/sparql_scaling.tex:
	@mkdir -p $(RESULTS)/sparql $(TABLES)
	$(PYTHON) scripts/sparql_scaling.py \
		--sizes 1000 10000 50000 \
		--reps 11 \
		--out $(RESULTS)/sparql \
		--tex $(TABLES)/sparql_scaling.tex

smoke:
	$(PYTHON) scripts/smoke_test_baseline.py

clean:
	rm -rf $(DATA)/cic_proxy_friday_ddos.csv
	rm -rf $(RESULTS)/proxy $(RESULTS)/real $(RESULTS)/eal $(RESULTS)/sparql
	rm -f  $(TABLES)/real_data.tex $(TABLES)/sparql_scaling.tex
	rm -f  $(FIGURES)/pareto_design_space.pdf $(FIGURES)/pareto_design_space.png
	@echo "Cleaned."

# ---------------------------------------------------------------------
# Real-data rerun on CIC-IDS2017 Friday DDoS parquet + tau recalibration
# See CHANGELOG_REAL.md for the empirical findings (1-6).
# ---------------------------------------------------------------------

REAL_PARQUET := $(DATA)/Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv.parquet

real-rerun: $(TABLES)/real_data_real.tex

$(RESULTS)/real/baseline_zscore_summary.json: $(REAL_PARQUET)
	@mkdir -p $(RESULTS)/real
	$(PYTHON) scripts/ingest_real.py --input $< --out $(RESULTS)/real
	$(PYTHON) scripts/baseline_zscore_real.py --input $< --out $(RESULTS)/real

$(RESULTS)/eal_real/eal_factorial_summary.json: $(REAL_PARQUET)
	@mkdir -p $(RESULTS)/eal_real
	$(PYTHON) scripts/eal_factorial_real.py --input $< --out $(RESULTS)/eal_real

$(TABLES)/real_data_real.tex: $(RESULTS)/real/baseline_zscore_summary.json $(RESULTS)/eal_real/eal_factorial_summary.json
	$(PYTHON) scripts/build_table_and_pareto_real.py \
		--baseline $(RESULTS)/real/baseline_zscore_summary.json \
		--eal      $(RESULTS)/eal_real/eal_factorial_summary.json \
		--tex      $(TABLES)/real_data_real.tex \
		--fig      $(FIGURES)/pareto_design_space_real

tau-sweep: $(TABLES)/real_tau_sweep.tex

$(TABLES)/real_tau_sweep.tex: $(RESULTS)/eal_real/eal_factorial_summary.json
	$(PYTHON) scripts/tau_sweep_real.py --input $(REAL_PARQUET) --out $(RESULTS)/eal_real
	$(PYTHON) scripts/build_tau_sweep_artifacts.py --sweep $(RESULTS)/eal_real/tau_sweep_summary.json --tex $(TABLES)/real_tau_sweep.tex --fig $(FIGURES)/tau_sweep_heatmap

real-all: real-rerun tau-sweep
	@echo ""
	@echo "=== Real-data pipeline complete ==="
	@echo "  - $(TABLES)/real_data_real.tex"
	@echo "  - $(TABLES)/real_tau_sweep.tex"
	@echo "  - $(FIGURES)/pareto_design_space_real.pdf"
	@echo "  - $(FIGURES)/tau_sweep_heatmap.pdf"
	@echo ""
	@echo "See CHANGELOG_REAL.md for the empirical findings (1-6)."
