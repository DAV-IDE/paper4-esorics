# MDPI *Future Internet* Submission Bundle — Paper 4

> Formal template adaptation of `paper/main_v4.tex` (post-PR#5 aligned
> manuscript, commit `f0ec2a5`, merged in `d4e3068`) to the MDPI
> *Future Internet* article class. **No scientific content, numerical
> value, table row, figure, claim, caveat, boundary, threat to validity,
> or reproducibility statement has been altered from the source.**

---

## 1. Provenance

| Item                | Value                                                                     |
| ------------------- | ------------------------------------------------------------------------- |
| Source manuscript   | `paper/main_v4.tex`                                                       |
| Source commit       | `f0ec2a5` (align: manuscript v4.0 → v4.1.2)                               |
| Source merge commit | `d4e3068` (PR #5 into `paper-alignment-repo-truth`)                       |
| Bundle branch       | `mdpi-futureinternet-submission-bundle`                                   |
| Target venue        | MDPI *Future Internet*                                                    |
| Target class        | `Definitions/mdpi` with option `futureinternet`                           |
| Compile target      | Overleaf (local `pdflatex`/`latexmk` unavailable in the local build environment) |
| Primary reproducibility artefact | `DAV-IDE/paper4-esorics` (this repository)                   |

## 2. Bundle layout

```
paper/mdpi/
├── main_mdpi_futureinternet.tex   # main document (MDPI class)
├── references.bib                 # BibTeX -- converted from \bibitem entries
├── tables/
│   ├── real_data.tex              # copied verbatim from repo /tables/
│   └── sparql_scaling.tex         # copied verbatim from repo /tables/
├── figures/
│   └── pareto_design_space.pdf    # copied verbatim from repo /figures/
└── README_MDPI_OVERLEAF.md        # this file
```

Paths inside `main_mdpi_futureinternet.tex` reference `tables/` and
`figures/` **without** the `../` prefix used in `paper/main_v4.tex`.

## 3. What changed vs. `paper/main_v4.tex` (formal-only)

The following changes are **purely formal**, imposed by the target
template. None modifies the scientific content.

| # | Change                                                             | Rationale                                                          |
| - | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| 1 | `\documentclass{llncs}` → `\documentclass[futureinternet,article,submit,pdftex,moreauthors]{Definitions/mdpi}` | Target class of the venue                        |
| 2 | LNCS `\author{}` / `\institute{}` → MDPI `\Title{}` / `\AuthorNames{}` / `\Author{}` / `\address{}` / `\corres{}` | MDPI frontmatter API                             |
| 3 | Affiliation for all three authors set to **DiSUIT — Department of Human Sciences and Territorial Innovation, University of Insubria, Varese/Como, Italy** | Author-provided authoritative affiliation (Fase 9) |
| 4 | LNCS `\begin{abstract}...\end{abstract}` → MDPI `\abstract{...}` | MDPI frontmatter API                             |
| 5 | LNCS `\keywords{...}` (inside abstract) → MDPI `\keyword{...}` (outside) | MDPI frontmatter API                             |
| 6 | `\section*{Reproducibility Statement}` body → moved verbatim into `\dataavailability{}` | MDPI final-statements API                        |
| 7 | `\section*{Acknowledgements}` body → moved verbatim into `\acknowledgments{}` | MDPI final-statements API                        |
| 8 | `\begin{thebibliography}` / `\bibitem` list → `references.bib` (BibTeX) referenced via `\externalbibliography{yes}` + `\bibliography{references}` | MDPI BibTeX pipeline                             |
| 9 | Table/figure include paths: `../tables/...` / `../figures/...` → `tables/...` / `figures/...` | Bundle is self-contained under `paper/mdpi/`     |
| 10 | Added `\providecommand{\orcidA}{}` etc. as safety net for older `mdpi.cls` releases | Prevents `Undefined control sequence` on legacy Overleaf toolchains |
| 11 | `\datereceived` / `\daterevised` / `\dateaccepted` / `\datepublished` commented out with a TODO note | Populated by editorial office at submission time; some `mdpi.cls` releases don't define them |
| 12 | Preserved custom macros verbatim: `\psiop`, `\Hsh`, `\Hsa`, `\Hpe`, `\DH`, `\taus` | Cross-referenced throughout the body            |

**Not changed:** any numerical value; any row of any table (Table 6, 7,
8, 9); the Pareto figure; the abstract's scientific content; the four
Contributions bullets; the scope boundary; the Threats to Validity
section; the Safe-Claim Matrix; the Reproducibility Statement wording
(including the *"licence resolution pending"* note — see follow-up
below); the claim boundaries B1/B2/B3; the AUC diagnostic caveat
(0.40–0.55 ROC, 0.24–0.31 PR); the SPARQL scaling numbers
(4.17 / 24.72 / 109.90 ms for Q1; 4.99 / 34.82 / 189.01 ms for Q2;
1.77 / 5.65 / 23.70 ms for Q3; ~26× / ~38× / ~13×; 100 ms crossover at
range 10⁴); the Pareto interpretation; the provenance snapshot
(`LoreBerto03/psi-risk-dt-pipeline @ edac16e`); the inherited Paper 3
figures (AUC ≈ 0.993, FPR ≈ 0.021, latency ≈ 25.8 ms, MSU ≤ 88%); or
the wording that the SEL is a prototype conceptual layer, not a
deployed CTI system.

## 4. TODO before submission (author-side actions)

These items are **explicitly** flagged inside
`main_mdpi_futureinternet.tex` as `\textbf{TODO: ...}` and must be
resolved by the corresponding author before the manuscript is submitted
to *Future Internet*.

### 4.1 Editorial / administrative

- [ ] **Author contributions (CRediT):** confirm the roles listed in
  `\authorcontributions{}` with D.F.\ and D.T.
- [ ] **Funding:** replace the TODO placeholder with the exact funding
  statement (either "This research received no external funding." or a
  grant reference). *Do not invent funders.*
- [ ] **Acknowledgments:** review the acknowledgments text and add any
  additional support (grants, computational resources, colleagues) to
  be recognised.
- [ ] **Conflicts of interest:** confirm the conflict-of-interest
  statement with all co-authors.
- [ ] **Academic Editor:** replace `TODO` once the handling editor is
  assigned by the editorial office.

### 4.2 Reproducibility (post-merge follow-ups from PR #5)

- [ ] **Zenodo DOI:** mint a Zenodo snapshot pinning
  `DAV-IDE/paper4-esorics`, `DAV-IDE/Alpha123`,
  `LoreBerto03/psi-risk-dt-pipeline`, and `Cvartic/psi-risk-dt` at
  submission time, then replace the "(DOI to be added)" placeholder
  inside `\dataavailability{}`.
- [ ] **Licence resolution:** the current `\dataavailability{}` text
  copies the wording from `paper/main_v4.tex`, which states that
  *"licence coverage across the three companions is tracked in the
  Paper 4 repository."* PR #5 follow-up: `LoreBerto03/psi-risk-dt-pipeline`
  now carries an explicit `LICENSE` file (MIT + CC BY 4.0); before
  submission, update the wording to reflect the resolved licence
  status. **Do not silently edit the number of pending items** — treat
  it as an editorial update, not a numerical claim.
- [ ] **Provenance tag:** request Lorenzo to tag the pipeline commit
  `edac16e` as `v-paper4-snapshot` in
  `LoreBerto03/psi-risk-dt-pipeline`. The paper cites `edac16e`
  explicitly; this tag makes the pinning immutable.

### 4.3 ORCID rendering

- [ ] Verify in the Overleaf compile output that the `\orcidA{}` /
  `\orcidB{}` / `\orcidC{}` markers render as the expected ORCID
  glyphs next to author names. If the `Definitions/mdpi` class shipped
  by Overleaf already defines them, the `\providecommand` no-ops
  become inert; if not, replace the `\providecommand` block with the
  ORCID artwork macros distributed with the class package.

### 4.4 Verify `mdpi.cls` version on Overleaf

- [ ] Some `Definitions/mdpi` releases define
  `\datereceived` / `\daterevised` / `\dateaccepted` / `\datepublished`;
  others expect them to be injected by the production system. Both
  paths compile cleanly with the bundle as delivered (the commands are
  commented out); if the editorial office requests them at submission,
  uncomment the block and populate the values they specify.

## 5. Sanity checks (must hold after any regeneration)

The build script `build_mdpi_bundle.py` (kept in the workspace, not
committed) runs 25 regex assertions on the generated .tex. All must
pass; the current bundle passes 25/25.

Key invariants:

| # | Assertion                                                                    | Rationale                                          |
| - | ---------------------------------------------------------------------------- | -------------------------------------------------- |
| 1 | Table 7 rows `65 & 31`, `69 & 27`, `38 & 40`, `82 & 52` are present verbatim | Preserves headline factorial table                 |
| 2 | SPARQL numbers `4.17`, `4.99`, `1.77`, `109.90`, `189.01`, `23.70` present   | Preserves Table 9 latency figures                  |
| 3 | AUC `0.993` present (inherited from Paper 3)                                 | Preserves scope-boundary anchor                    |
| 4 | AUC caveat range `0.40--0.55` present                                        | Preserves diagnostic proxy statement               |
| 5 | `Boundary B1` string present                                                 | Preserves claim-boundary vocabulary                |
| 6 | `edac16e` provenance hash present                                            | Preserves reproducibility anchor                   |
| 7 | `baseline_zscore` 401-lines statement present                                | Preserves baseline artefact reference              |
| 8 | `DAV-IDE/paper4-esorics` present                                             | Preserves primary reproducibility artefact         |
| 9 | `experiments/day1` **absent**                                                | Fase 9 rule: the aligned paper drops this legacy path |
| 10 | `../tables/` / `../figures/` **absent**                                     | Bundle is self-contained; only relative paths      |
| 11 | `DiSTA` and `Dipartimento di Informatica` **absent**                        | Fase 9 rule: unified DiSUIT affiliation            |
| 12 | `DiSUIT` present; the three ORCIDs present                                  | Fase 9 rule: correct authoritative frontmatter     |

If any of these fails after a regeneration, **stop and investigate**;
do not silently patch.

## 6. Overleaf instructions

1. **Create the Overleaf project** by uploading either (a) the entire
   `paper4-esorics` repository (Overleaf will use `paper/mdpi/` as the
   project root once you set the compile target), or (b) *only* the
   contents of `paper/mdpi/` plus the MDPI `Definitions/` folder
   provided by the *Future Internet* template.
2. **Set the main document** to
   `paper/mdpi/main_mdpi_futureinternet.tex` in *Menu → Settings →
   Main document*.
3. **Compiler:** pdfLaTeX (do not switch to XeLaTeX or LuaLaTeX; the
   MDPI class ships targeted for pdfLaTeX).
4. **First compile pass:** expect the "Undefined citation" warnings
   during the first run. Compile a second time so that BibTeX (or
   Biber, whichever the class invokes) populates the references. The
   third pass resolves the cross-references.
5. **Verify visually:**
   - The Table 6 / Table 7 / Table 8 / Table 9 rendered numbers match
     the values listed in §5 of this README.
   - The Pareto figure renders (not a missing-image placeholder).
   - The `\orcidA{}` / `\orcidB{}` / `\orcidC{}` markers render as
     ORCID glyphs next to the author names, not as empty space or as
     `??`.
   - The `\dataavailability{}` section contains the full
     Reproducibility Statement text.
   - The `\acknowledgments{}` section contains the original
     Acknowledgements text plus the TODO note.
6. **Do not merge** this bundle into the paper's canonical
   `paper/main_v4.tex` build. The MDPI bundle lives beside it, not on
   top of it. Both must remain compilable independently.

## 7. Local compilation status

Local `pdflatex` / `latexmk` / `tectonic` are **not available** in the
local build environment that produced this bundle. Compilation is delegated to
Overleaf, where the MDPI `Definitions/mdpi` class and its dependencies
(cite, hyperref, ORCID artwork, etc.) are pre-installed by the venue's
template.

## 8. How to regenerate this bundle

The bundle is deterministically produced by
`build_mdpi_bundle.py` (kept in the workspace at
`/home/user/workspace/build_mdpi_bundle.py`, **not committed** — it is
a scaffolding script, not part of the manuscript). To regenerate:

```bash
cd /home/user/workspace/davide_repo_audit/paper4-esorics
git checkout mdpi-futureinternet-submission-bundle
git pull --rebase origin paper-alignment-repo-truth  # if the base moved
python3 /home/user/workspace/build_mdpi_bundle.py
# Copy static tables/figures if they moved:
cp tables/real_data.tex        paper/mdpi/tables/
cp tables/sparql_scaling.tex   paper/mdpi/tables/
cp figures/pareto_design_space.pdf paper/mdpi/figures/
```

The script exits non-zero if any of the 25 sanity checks fails. **Never
commit a bundle that fails sanity checks.**

## 9. Explicit non-goals

This bundle does **not**:

- Change any AI-Act, NIS 2, or compliance wording (the source paper
  contains none, and none is added here).
- Introduce SOTA claims (the source paper explicitly avoids them).
- Introduce a Zenodo DOI (the DOI is minted separately; a placeholder
  is preserved).
- Change the venue-neutral wording of the SEL as a *prototype
  conceptual layer, not a deployed CTI system*.
- Change any AUC caveat, Boundary B1/B2/B3 statement, or claim
  boundary.
- Compile locally.
- Auto-merge into `main` or into `paper-alignment-repo-truth`.

## 10. Contact

Corresponding author for this submission bundle:
**Roberto Pazzi**, `roberto.pazzi@uninsubria.it`, DiSUIT — University
of Insubria.
