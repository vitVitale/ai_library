---
name: confluence-coverage
description: Map product features documented in Confluence (Server/Data Center) to test plans, test strategies, test cases and automated tests in the repo, and report coverage gaps - without MCP and with minimal AI tokens. Python scripts download a compact Markdown snapshot and build the coverage table offline; the AI only decides ambiguous matches. Use when asked about test coverage of features, which features lack test plans or automation, mapping requirements/Confluence pages to tests, or refreshing the Confluence snapshot.
---

# Confluence → test coverage map

Scripts live in `scripts/` next to this file (in a Copilot repo: `.github/skills/confluence-coverage/scripts/`). They need Python 3.11+ and only the standard library. No MCP, no pip install.

## Token budget rules (follow strictly)
1. **Never scrape or read Confluence through the AI.** The scripts do all downloading, conversion and matching at zero AI cost.
2. The AI reads **only** `qa-knowledge/review.md` (to decide pairs) or `qa-knowledge/coverage.md` (to answer questions). Do not open `qa-knowledge/coverage.json` or `qa-knowledge/confluence/pages/` unless one specific fact is missing.
3. When a page detail is needed, search first: `grep -n "<term>" qa-knowledge/confluence/index.jsonl`, or `grep -n` in the one page file. Then read only the lines around the hit, never whole pages or folders.
4. Record each decision once in `qa-knowledge/mapping-overrides.txt`, so later runs need no AI.
5. Answer with compact tables that cite page ids. Don't repeat page content back.

## Workflow
**1. Configure (once).** Copy [templates/confluence-coverage.toml](templates/confluence-coverage.toml) to the repo root and fill in:
- the space keys;
- the feature pages or folders (ids, URLs or exact titles);
- the test-doc folders.

All keys are listed in [references/config.md](references/config.md).

**2. Sync.** The user runs this in their own terminal, because it needs their token:
```bash
export CONFLUENCE_URL=https://confluence.example.com
export CONFLUENCE_PAT=<personal access token>
python <scripts>/confluence_sync.py                   # spaces/pages from the config
python <scripts>/confluence_sync.py --page "<page URL>" --page "<another page URL>"   # just these pages + subtrees
```
- `--page` accepts a page URL (`…?pageId=123`, `/display/SPACE/Title`), a page id or an exact title, from any space. Each page is synced together with its child pages (limit the depth with `--max-depth N`).
- Re-running downloads only pages whose version changed.
- If the corporate CA is not trusted, set `CONFLUENCE_CA_BUNDLE=/path/ca.pem`.
- The AI must never ask for, print or store the token.

**3. Map.** This is offline and takes seconds:
```bash
python <scripts>/coverage_map.py
```
It writes three files to `qa-knowledge/`:
- `coverage.md`: the deliverable, one row per feature with plan, strategy, cases, automation and gap flags.
- `coverage.json`: the same data in full detail.
- `review.md`: only the uncertain matches.

**4. Review (AI, one batch).** Read `review.md`. For each line `- <feature> <doc> ? — …`, decide whether the doc really tests that feature, using the titles, headings and intro shown. Append all decisions to `qa-knowledge/mapping-overrides.txt` in one edit, one per line:
```
14 26 yes
11 31 no
ignore 40          # page is neither a feature nor a test doc
doc 23 cases       # force the doc type
feature 55         # force a page to be a feature
```
Then re-run `coverage_map.py`; `review.md` should shrink to 0. If a pair really cannot be decided from `review.md`, grep that one page for the feature's key terms. Don't open the whole page.

**5. Answer questions** from `coverage.md`, for example "which P1 features have no automation?" or "where is the plan for X?".

## Gap flags
- `NO_PLAN`: no test plan or test cases doc matched.
- `STALE`: the feature page was edited after its newest test doc.
- `NO_AUTO`: no test file references the feature's Jira keys, Allure `@Feature`/`@Story`, or its distinctive title words.
- `REVIEW`: has undecided pairs in `review.md`.

In the Plan/Cases columns, `~` marks a text-similarity match. Everything else was matched by a page link, a shared Jira key, a child page or a manual override.

## Combined workflow with bdd-suite-optimizer (E2E repos)
1. You: `confluence_sync.py --page <links>` (needs your token).
2. `python .github/skills/cucumber-suite-analysis/scripts/qa_refresh.py` runs this skill's `coverage_map.py`, then the E2E analysis. The last line says which agent to run next.
3. `coverage-mapper` decides `review.md`. This curates the feature list in `coverage.json`.
4. `e2e-suite-optimizer` decides the E2E batches. Scenarios are linked to *your curated features*, and every feature keeps one golden path.
5. Per-feature result: `qa-knowledge/e2e/feature-impact.md`.

## Data handling
The snapshot contains internal documentation. Commit `qa-knowledge/` only to internal repositories. To keep page text out of git, add `qa-knowledge/confluence/pages/` to `.gitignore`: coverage still works from `index.jsonl`.
