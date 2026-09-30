---
name: cucumber-suite-analysis
description: Analyse a large Cucumber/Gherkin E2E suite (Java/Spring glue) for risk, coverage and redundancy, recommend the right test level for each scenario (golden E2E, extended E2E, component, unit, merge, drop), and select a coverage-driven golden path set. Scripts do the analysis offline; the AI only reviews small batches. Use when asked to shrink, prioritise, deduplicate or audit BDD/E2E scenarios, decide what moves to lower test levels, or pick smoke/golden tests, especially for payment flows (SCT, SCT Inst, SDD).
---

# Cucumber suite analysis (risk · coverage · redundancy · test level)

The script is `scripts/bdd_suite.py`, next to this file (in a Copilot repo: `.github/skills/cucumber-suite-analysis/scripts/`). It needs Python 3.11+ and the standard library only. It reads `.feature` files and Java/Kotlin step definitions and never runs the tests.

## Token budget rules (follow strictly)
1. **Never read feature files or step definitions to "analyse the suite".** Run the script; it parses all scenarios at zero AI cost.
2. Read `qa-knowledge/e2e/summary.md` first (about 1–2k tokens). Then read **one** `review-NN.md` batch per request.
3. Don't open `analysis.json`, `scenarios.csv`, `moves.md` or whole feature files. If one scenario needs context, read only its lines (`path:line` is given, about 20 lines).
4. For requirement context, grep the Confluence snapshot for the page id shown as `req <id>` (`grep -n "" qa-knowledge/confluence/pages/<id>-*.md | head -60`). Never read whole folders.
5. Write each judgement once as a line in `qa-knowledge/e2e/decisions.txt`. Re-running the script then costs nothing.

## Workflow
**1. Configure (optional).** Copy [templates/bdd-suite.toml](templates/bdd-suite.toml) to the E2E repo root. Without it, the features folder is auto-detected and payment-engine defaults are used.

The two settings that matter most:
- `[layers]`: add your own client/stub class names, so the script knows which scenarios reach the CSM, Kafka/MQ or files.
- `[dimensions]`: your business vocabulary (status codes, R-transaction names, scheme terms).

**2. (Optional) Confluence context.** Sync design and requirement pages with the `confluence-coverage` skill's `confluence_sync.py --page <link>`. The analysis then links each scenario to its best-matching page and lists pages that no scenario exercises.

**3. Run:**
```bash
python <scripts>/bdd_suite.py
```
It writes these files to `qa-knowledge/e2e/`:
- `summary.md`: tiers per folder, outcome coverage matrix, redundancy counts, signal quality.
- `golden-set.md` and `golden-set.rerun.txt`: the golden set. Run it with `-Dcucumber.features=@qa-knowledge/e2e/golden-set.rerun.txt`.
- `moves.md`: what to move down, merge or drop, with reasons.
- `scenarios.csv`: for Excel.
- `review-NN.md`: the batches for step 4.

**4. Review, one batch per request.** For each item, decide using [references/test-levels.md](references/test-levels.md). Append one line per item to `decisions.txt`:
```
S1a2b3c e2e        # keeps the only SDD R-transaction flow with real CSM
S4d5e6f component  # status query only touches engine API + DB
S7a8b9c merge:S1a2b3c
```
Allowed values: `golden` (force), `e2e` (keep, eligible for golden), `component`, `unit`, `drop`, `merge:<id>`.

Re-run the script after each batch; the batches shrink as decisions accumulate.

**5. Deliver.** Summarise from `summary.md` for stakeholders. For the migration backlog, point people to `moves.md` and `scenarios.csv` rather than copying them.

## What the tiers mean
| Tier | Meaning |
|---|---|
| golden | Smallest set covering every payment type × outcome/check found in the suite. Runs on every build. |
| e2e | Keep end-to-end, but only nightly or in the extended regression. Candidates to retire later. |
| component | Engine-only behaviour (API + DB, stubs for the CSM). Belongs in Spring Boot tests of the engine. |
| unit | Validation or rules without settlement or external systems. Table-driven unit tests. |
| merge | Same flow, different data. Make it an Outline row, or test the variation lower down. |
| drop | Exact duplicate, or all its steps are contained in another scenario. |

Before deleting anything in `moves.md`, confirm the lower-level test exists. The summary lists the coverage that would otherwise be lost.
