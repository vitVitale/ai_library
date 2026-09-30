---
name: test-case-format
description: Standard format for manual and automation-ready test cases and test plans - IDs, priority, preconditions, steps, expected results, test design techniques (equivalence classes, boundaries, decision tables, state transitions). Use when writing, reviewing or converting test cases or a test plan, or when turning requirements or a user story into test scenarios.
---

# Test case format

## Test case
Write each case in this Markdown shape (keep IDs stable once published):

```markdown
### TC-<AREA>-<NNN>: <behaviour in one line, e.g. "Checkout rejects expired card">
- **Priority:** P1 | P2 | P3            (P1 = blocks release / money / security / data loss)
- **Type:** functional | negative | boundary | security | accessibility | performance | regression
- **Level:** unit | API | UI | manual   (lowest level that can prove it)
- **Requirement:** <story / ticket / spec link>
- **Preconditions:** <state, user role, data — concrete values>
- **Test data:** <exact inputs>

| # | Step | Expected result |
|---|------|-----------------|
| 1 | <one action> | <observable outcome> |
| 2 | ... | ... |

- **Automation:** candidate | automated (<test class#method>) | manual-only (<why>)
```

Rules
- One behaviour per case; the title alone should tell what broke if it fails.
- Steps are actions, expected results are observable (UI text, status code, DB row, event) — never "works correctly".
- Concrete data, not "valid email". Use `ann+tc001@example.com`, not real personal data.
- Negative and boundary cases are separate cases, not extra steps.

## Test design checklist
Apply what fits; say which technique produced each case.
- **Equivalence classes:** one case per valid/invalid class.
- **Boundaries:** min-1, min, min+1, max-1, max, max+1; empty, null, whitespace, very long, unicode/emoji.
- **Decision table:** for rules combining several conditions (role × status × flag).
- **State transitions:** valid and invalid transitions (e.g. cancel a shipped order).
- **Error guessing / risk:** concurrency (double submit), timeouts, retries/idempotency, permissions, time zones/DST, locale formats, pagination edges.
- **Non-functional smoke:** auth required, no sensitive data in responses/logs, basic a11y (labels, keyboard), acceptable response time.

## Test plan (short form)
```markdown
# Test plan: <feature>
## Scope — in / out
## Risks — ranked, with why (impact × likelihood)
## Approach — what is tested at unit / API / UI / manual level and why
## Test cases — table: ID | title | priority | level | automation
## Environments & data
## Entry / exit criteria
## Open questions — for devs/PO
```
