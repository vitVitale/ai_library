---
name: architecture-review
description: Review a solution design document (SDD / HLD / architecture document) and its architecture diagrams with a solution lens (requirements fit, measurable NFRs, data, integration, security, resilience, operations) and an enterprise lens (principles, tech radar, reuse, data ownership, standards), starting with a deterministic linter (sad_lint.py) that checks sections, placeholders, NFR targets, diagram/text consistency and links. Use when asked to review, assess, audit, critique or approve an architecture document or diagram, prepare for an architecture board, or check a design against enterprise guardrails.
---

# Architecture review

Scripts are in `scripts/` next to this file (`.github/skills/architecture-review/scripts/` in a Copilot repo). They need Python 3.11+ and only the standard library.

## Token budget rules
1. **Run the linter first**: it finds structural problems at zero AI cost.
   ```bash
   python <scripts>/sad_lint.py <path/to/sdd.md>          # Markdown report; exit 1 on errors
   python <scripts>/sad_lint.py <path/to/sdd.md> --json   # machine-readable
   ```
   Report the linter's findings in one grouped line each. Don't re-discover them by reading.
2. Then read the document once. Read linked ADRs and diagram sources only when a finding depends on them.
3. Diagrams kept only as images: look at an image only if the tool can read images, and say in the report that the diagram/text consistency check was not possible.
4. Don't scan the codebase. If a claim needs checking (e.g. "uses PostgreSQL"), grep for that one fact.

If the document is in Confluence, ask the user to export it to Markdown or to sync it with the `confluence-coverage` skill's `confluence_sync.py --page <url>`. Never ask for a token.

## Review process
1. **Lint** (above). Missing sections or diagrams are findings: Major, or Blocker when the context diagram, the quality attributes or the security section is missing.
2. **Understand**: problem, goals, top 3 quality attributes, constraints. If the document doesn't make these clear, that is the first finding.
3. **Solution lens**: work through section A of [references/review-checklist.md](references/review-checklist.md). Focus on whether the design really meets the top quality targets: trace the riskiest flow end to end through the diagrams and look for single points of failure, sync chains, missing idempotency and unowned data.
4. **Enterprise lens**: section B, checked against `architecture-guardrails.md` (or `docs/architecture/guardrails.md`) if the repo has one. To create one, start from [templates/architecture-guardrails.md](templates/architecture-guardrails.md). Without guardrails, raise the enterprise items as Questions.
5. **Verdict and report** in the format below.

## Report format
```markdown
# Architecture review: <document> (<date>)
**Verdict:** Approve | Approve with conditions | Rework — <one-sentence reason>

## Linter summary
<errors/warnings count + one line per group>

## Findings
| # | Severity | Lens | Where | Finding | Why it matters | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Blocker | Solution | §5.2 container view | … | QA-2 99.95 % … | … |

## Questions for the authors
1. …

## Strengths (max 3, one line each)
## Conditions for approval (if "Approve with conditions")
```
Sort the findings by severity. Each finding cites a section, diagram or line, and gives a concrete fix. No generic advice.
