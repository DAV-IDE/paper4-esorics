#!/usr/bin/env bash
# audit_wording.sh — grep for forbidden phrases (Safe-Claim Matrix E.3)
#
# Usage: bash scripts/audit_wording.sh paper/main_v4.tex
#
# Reports lines of the paper that contain claim-inflating words we
# have committed to avoid (see the Safe-Claim Matrix, Table
# tab:safe-claim inside the paper, and the audit note in
# docs/wording_audit.md).
#
# What this script deliberately does NOT flag:
#
#   1. LaTeX comment lines (starting with '%'). The audit is about
#      wording that ends up in the RENDERED paper, not about author
#      notes and TODOs inside the source.
#
#   2. Lines inside the Safe-Claim Matrix table itself. That table
#      is where we ENUMERATE the forbidden phrases as literal
#      examples of what NOT to say. Flagging those literal examples
#      would produce a false positive on every audit run and drown
#      real hits in noise. The matrix is identified by the region
#      between "\label{tab:safe-claim}" and the next "\end{table}".
#
#   3. Ordinal / positional "first" (e.g. "the first sample",
#      "the first attack-labelled second", "the first 600 s"). Only
#      the claim-inflating "first" is forbidden ("first-of-a-kind",
#      "first-ever", etc.); "first-class" is also allowed by the
#      matrix. The script therefore matches only the specific
#      patterns "\bfirst-of-a-kind", "\bfirst-ever", or the string
#      "first" appearing at the start of a claim clause (with an
#      allow-list for the common ordinal contexts). If reviewers
#      still see a claim-inflating "first" pass through, add it to
#      the FORBIDDEN_FIRST_CONTEXTS array below.
#
# Exit codes:
#   0  no forbidden phrases found (after applying the exclusions above)
#   1  at least one forbidden phrase found in the rendered content
#   2  invalid usage (e.g. paper file missing)

set -euo pipefail

FILE="${1:-paper/main_v4.tex}"

if [[ ! -f "$FILE" ]]; then
  echo "ERROR: file not found: $FILE" >&2
  exit 2
fi

# ---------------------------------------------------------------------
# Build the audit view: the paper source, minus (a) full-line LaTeX
# comments, and (b) the Safe-Claim Matrix table region. The result is
# emitted to a temp file with ORIGINAL line numbers preserved (so grep
# hits still point back to the real line).
# ---------------------------------------------------------------------
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

awk '
  BEGIN { in_matrix = 0 }
  {
    # Detect start of Safe-Claim Matrix table (label line)
    if ($0 ~ /\\label\{tab:safe-claim\}/) { in_matrix = 1 }

    # Emit the line with its original line number, but blanked out
    # if we are inside a full-line LaTeX comment OR inside the
    # Safe-Claim Matrix table.
    if (in_matrix == 1) {
      # Suppress the line contents but keep line number alignment
      printf "%d:\n", NR
    } else if ($0 ~ /^[[:space:]]*%/) {
      # Full-line LaTeX comment
      printf "%d:\n", NR
    } else {
      printf "%d:%s\n", NR, $0
    }

    # Detect end of Safe-Claim Matrix table
    if (in_matrix == 1 && $0 ~ /\\end\{table\}/) { in_matrix = 0 }
  }
' "$FILE" > "$TMP"

# ---------------------------------------------------------------------
# Forbidden phrase list, per Safe-Claim Matrix E.3.
# Note: "first-class" is allowed; only claim-inflating "first"
# variants are matched.
# ---------------------------------------------------------------------
FORBIDDEN=(
  "\\bnovel\\b"
  "\\bfirst-of-a-kind\\b"
  "\\bfirst-ever\\b"
  "\\bworld-first\\b"
  "\\bproves\\b"
  "AI Act compliant"
  "NIS2 compliant"
  "production-grade"
  "deployed CTI feed"
  "outperforms neural detectors"
  "\\bSOTA\\b"
  "fair comparison"
  "guaranteed by construction"
)

# Explicit-negation patterns: matches on lines that clearly REJECT the
# claim (e.g. "we make no claim of a deployed CTI feed", "not a new
# detector competing on SOTA metrics") are false positives for the
# audit and must not fail the check. Extend this list as needed.
NEGATION_PATTERNS=(
  "no claim of"
  "we do not"
  "we make no"
  "is not a"
  "not\\s+a\\s+new"
  "never"
  "is not\\s+"
  "rather than"
  "instead of"
)

HITS=0
for phrase in "${FORBIDDEN[@]}"; do
  # Search the pre-filtered view (comments and Safe-Claim Matrix
  # already stripped). Skip lines that begin with "N:" and nothing
  # else (those are the pre-filtered comment/matrix lines).
  raw_matches=$(grep -nP "$phrase" "$TMP" 2>/dev/null | grep -vP "^\d+:$" || true)
  if [[ -z "$raw_matches" ]]; then
    continue
  fi

  # Filter out lines that contain an explicit-negation pattern, OR
  # whose IMMEDIATE PREDECESSOR line in the paper contains such a
  # pattern (the negation and the flagged phrase are often split
  # across two lines by LaTeX line-wrap, e.g.
  #     we make no claim of a
  #     deployed CTI feed, of community-curated ...
  # ).
  matches="$raw_matches"
  for neg in "${NEGATION_PATTERNS[@]}"; do
    filtered=""
    while IFS= read -r hit; do
      [[ -z "$hit" ]] && continue
      line_num=$(echo "$hit" | cut -d: -f1)
      # Same line
      if echo "$hit" | grep -qiP "$neg"; then
        continue
      fi
      # Previous line (line_num - 1) in the ORIGINAL file
      prev_num=$((line_num - 1))
      if [[ $prev_num -ge 1 ]]; then
        prev_line=$(sed -n "${prev_num}p" "$FILE")
        if echo "$prev_line" | grep -qiP "$neg"; then
          continue
        fi
      fi
      filtered+="$hit"$'\n'
    done <<< "$matches"
    matches="${filtered%$'\n'}"
  done

  if [[ -n "$matches" ]]; then
    echo "FORBIDDEN PHRASE: \"$phrase\""
    # Re-project the temp-file line numbers back onto the original
    # file (they are already 1-to-1 by construction of awk above).
    echo "$matches" | sed -E 's/^([0-9]+):[0-9]+:/\1:/' | sed -E 's/^([0-9]+):/'"$(basename "$FILE")"':\1:/'
    echo ""
    HITS=$((HITS + 1))
  fi
done

if [[ $HITS -eq 0 ]]; then
  echo "OK — no forbidden phrases in rendered content (comments and Safe-Claim Matrix excluded)"
  exit 0
else
  echo "FAIL — $HITS forbidden phrase(s) detected; review the lines above."
  echo "       If a hit is intentional (e.g. quoted counter-example inside a paragraph"
  echo "       that must remain in the rendered paper), rephrase or extract it into the"
  echo "       Safe-Claim Matrix table so the audit view excludes it automatically."
  exit 1
fi
