---
name: bug-report-template
description: Template and rules for clear, reproducible bug reports - title formula, environment, minimal steps, expected vs actual, evidence, severity vs priority, suspected cause. Use when writing or improving a bug report or issue from a test failure, log, stack trace or user complaint.
---

# Bug report template

```markdown
**Title:** [<Area>] <What is wrong> when <condition>
          e.g. "[Checkout] Order total ignores coupon when cart has 10+ items"

**Severity:** Blocker | Critical | Major | Minor | Trivial      (impact on the user/system)
**Priority:** P1 | P2 | P3                                      (suggested; PO decides)
**Environment:** <env/URL>, build/commit <sha>, browser/OS or client version, user role, feature flags
**Frequency:** always | intermittent (<n>/<m> runs) | once

## Steps to reproduce
1. <minimal steps, starting from a known state, with exact data>
2. ...

## Expected result
<what should happen, with the source: spec / story / previous behaviour>

## Actual result
<what happens — exact error text, status code, wrong value>

## Evidence
- Failing test: `<class#method>` / CI run link
- Request/response (curl), log excerpt with timestamp, screenshot/trace
- Stack trace (trimmed to the relevant frames)

## Notes
- Regression? last known good build/commit
- Suspected cause / area of code (clearly marked as a hypothesis)
- Workaround, if any
```

## Rules
- **Minimal**: remove every step that isn't needed to reproduce. Reproduce once more after trimming.
- **One bug per report.** Split if there are two different wrong behaviours.
- **Facts vs guesses**: keep hypotheses in *Notes*, never in *Actual result*.
- **No secrets/PII**: mask tokens, passwords, emails, card numbers in logs and screenshots.
- Severity guide: Blocker = no workaround, blocks testing/release; Critical = data loss, security, money, crash; Major = main flow broken with workaround; Minor = secondary flow/cosmetic with impact; Trivial = typo/cosmetic.
- For a failing automated test, first confirm it's a product bug and not a test bug (wrong expectation, env/data issue, flakiness) and say which.
