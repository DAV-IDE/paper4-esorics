# Wording Audit — How the Safe-Claim Matrix is Enforced

This repository ships a `scripts/audit_wording.sh` gate that a
reviewer or CI job can run against `paper/main_v4.tex` to check
whether the paper accidentally reintroduces any of the forbidden
phrases enumerated in the Safe-Claim Matrix (Table
`tab:safe-claim`, §"Paper Lineage and Safe-Claim Matrix" of the
paper).

## What is forbidden

The Safe-Claim Matrix forbids the following exact phrases (or
regex-anchored variants) from appearing in the RENDERED paper
except as literal counter-examples inside the matrix itself:

| Phrase                          | Regex                        |
|---------------------------------|------------------------------|
| novel                           | `\bnovel\b`                  |
| first-of-a-kind                 | `\bfirst-of-a-kind\b`        |
| first-ever                      | `\bfirst-ever\b`             |
| world-first                     | `\bworld-first\b`            |
| proves                          | `\bproves\b`                 |
| AI Act compliant                | `AI Act compliant`           |
| NIS2 compliant                  | `NIS2 compliant`             |
| production-grade                | `production-grade`           |
| deployed CTI feed               | `deployed CTI feed`          |
| outperforms neural detectors    | `outperforms neural detectors` |
| SOTA                            | `\bSOTA\b`                   |
| fair comparison                 | `fair comparison`            |
| guaranteed by construction      | `guaranteed by construction` |

Note the following intentional exclusions from the forbidden list:

- **"first-class"** is explicitly ALLOWED (it means "as a proper
  citizen of the deployment model", not "first ever").
- **Ordinal "first"** ("the first sample", "the first 600 s",
  "the first attack-labelled second") is allowed. Only the
  claim-inflating variants above are matched.
- **"extension of"** is allowed generally; only the specific
  Safe-Claim Matrix wording restrictions on how Paper 4 relates
  to Paper 3 apply — those are enforced by human review, not by
  regex.

## What the audit script does

`scripts/audit_wording.sh paper/main_v4.tex` builds an audit view
of the paper and grep-checks it against the forbidden list. The
audit view is the paper source MINUS three regions that are not
part of the rendered content:

1. **Full-line LaTeX comments** (lines starting with `%`). Author
   TODOs and drafting notes are not part of the paper the reader
   sees, so they should not cause audit failures.
2. **The Safe-Claim Matrix table itself**. That table is where we
   enumerate the forbidden phrases as literal quoted examples of
   what NOT to say. Flagging those literal examples would produce
   a spurious hit on every run and would drown real regressions.
   The table is identified by the region between
   `\label{tab:safe-claim}` and the next `\end{table}`.
3. **Explicit-negation contexts**. Sentences that openly REJECT a
   claim (e.g. "we make no claim of a deployed CTI feed", "the
   contribution is not a new detector competing on SOTA metrics")
   are false positives: the paper is deliberately being careful,
   and rewriting those sentences would weaken the paper. The
   script checks the flagged line AND the immediately preceding
   line for a small negation cue list (`no claim of`, `we do
   not`, `we make no`, `is not a`, `not a new`, `never`, `is
   not`, `rather than`, `instead of`).

## Exit codes

| Exit | Meaning                                                     |
|------|-------------------------------------------------------------|
| 0    | No forbidden phrase found in the rendered content.          |
| 1    | At least one forbidden phrase found; audit failed.          |
| 2    | Invalid usage (paper file missing).                         |

## When the audit produces a false positive

If a legitimate use of a forbidden phrase (e.g. quoting a rival
paper's abstract, or an in-text reference to the matrix itself)
is flagged, do NOT edit the script to add a bespoke exception.
Instead:

1. Reword the paragraph, if the phrase can be avoided without
   loss of meaning.
2. If the phrase must remain (e.g. a direct quotation), extract
   it into the Safe-Claim Matrix table cell — the audit script
   already excludes that table region.
3. Only if neither of the above works, extend the
   `NEGATION_PATTERNS` array with a specific cue tied to the
   sentence in question. Do NOT add general-purpose escape
   patterns (e.g. `.*`) that would defeat the audit.

## When the audit produces a false negative

If a reviewer notices a claim-inflating word in the rendered PDF
that the script did not catch, add the corresponding regex to the
`FORBIDDEN` array of `scripts/audit_wording.sh` and open a
follow-up PR.

## Running the audit locally

    bash scripts/audit_wording.sh paper/main_v4.tex

Expected clean output:

    OK — no forbidden phrases in rendered content (comments and Safe-Claim Matrix excluded)

Recommended pre-submission workflow: run the audit last, after
all content edits and after the final `pdflatex` pass. If the
audit fails, fix the wording, re-run, and only then package the
ESORICS artefact.

## History

The audit script was reworked (commit `fix(scripts): suppress
false positives in audit_wording.sh`) after an audit review noted
that the previous version reported ~10 spurious hits — all inside
the Safe-Claim Matrix table or on ordinal uses of "first" — and
buried the only two real ambiguous hits (the "deployed CTI feed"
sentence at §"Selective STIX, MISP and CVE Alignment" and the
"SOTA metrics" sentence at §"Conclusions", both of which turned
out to be legitimate explicit negations).
