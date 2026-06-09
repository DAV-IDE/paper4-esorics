#!/usr/bin/env bash
# audit_wording.sh — grep for forbidden phrases (Safe-Claim Matrix E.3)
# Usage: bash scripts/audit_wording.sh paper/main_v4.tex

set -euo pipefail

FILE="${1:-paper/main_v4.tex}"

if [[ ! -f "$FILE" ]]; then
  echo "ERROR: file not found: $FILE" >&2
  exit 2
fi

# Forbidden phrases per Safe-Claim Matrix E.3 of the paper
# Note: "first-class" is allowed; "first" alone is forbidden.
FORBIDDEN=(
  "novel"
  "\\bfirst\\b(?!-class)"
  "proves"
  "AI Act compliant"
  "NIS2 compliant"
  "production-grade"
  "deployed CTI feed"
  "outperforms neural detectors"
  "\\bSOTA\\b"
  "fair comparison"
  "guaranteed by construction"
  "extension of .Risk-DT"
  "prototype only"
)

HITS=0
for phrase in "${FORBIDDEN[@]}"; do
  # Exclude lines that are obviously citations or negations
  matches=$(grep -nP "$phrase" "$FILE" 2>/dev/null | \
    grep -viE '\\cite\{|\\citep\{|\\citet\{|% forbidden:|we do not|never|not\s+a' || true)
  if [[ -n "$matches" ]]; then
    echo "FORBIDDEN PHRASE: \"$phrase\""
    echo "$matches"
    echo ""
    HITS=$((HITS + 1))
  fi
done

if [[ $HITS -eq 0 ]]; then
  echo "OK — no forbidden phrases in non-citation context"
  exit 0
else
  echo "FAIL — $HITS forbidden phrase(s) detected; review and fix or annotate with '% forbidden:' if intentional"
  exit 1
fi
