# Test level rules for a payment engine

Use these rules to decide review items. Pick the **lowest level that can prove the behaviour**, and keep E2E for what only E2E can prove.

## Keep in E2E: golden (every build)
One scenario per **payment type × business outcome**, through the real integration points:
- Happy path per scheme and channel: SCT, SCT Inst, SDD CORE/B2B. The payment is accepted, reaches the CSM (or its simulator in the E2E environment), settles, and is booked.
- Each R-transaction lifecycle that crosses systems: reject, return (pacs.004), recall (camt.056/029), refund, reversal (pacs.007).
- Instant timeout and late-response handling (SCT Inst time limits).
- Flows where ordering or asynchrony between systems matters: Kafka/MQ events, callbacks, status reports (pacs.002).
- Money-safety flows with a real integration: duplicate submission/idempotency, screening hit → payment held/rejected, cut-off → next business day.

## Keep in E2E, but extended (nightly)
- Secondary variants of the above: other channels, other currencies/amount bands, second-level R-transaction reasons.
- Flows whose risk is high but that are already covered at another level. Keep them until that level is trusted.

## Move to component level
Spring Boot tests of the engine, with WireMock/stubs for the CSM, Testcontainers for DB/Kafka, `@SpringBootTest` or slices.
- Behaviour that only involves the engine's own API and DB: status queries, listing/search, state transitions triggered by a stubbed CSM message, persistence and mapping.
- Error handling for a **stubbed** external response: CSM rejects with reason X → status Y. Only one reason needs a real E2E test.
- Retries, timeouts and circuit breakers against a stub (deterministic, fast).
- Kafka/MQ message contents (schema, headers). Pair with contract tests for the consumer side.

## Move to unit level
- Field and format validation: IBAN/BIC, mandatory fields, lengths, character sets, amount precision, ISO 20022 schema rules.
- Business rules computed in code: fee calculation, limits/thresholds, cut-off and business-day calendars, value dates, SDD sequence-type rules (FRST/RCUR/FNAL/OOFF), mandate amendment rules, reason-code mapping.
- ISO 20022 mapping (pain.001 → pacs.008, pacs.002 status mapping). These should be table-driven tests with many rows.
- **Signal:** a Scenario Outline with many rows that only changes input data and expects a rejection or error code belongs in unit tests. Keep at most one row E2E, if the rejection path itself crosses systems.

## Merge
- Scenarios with the same steps and different data become one Scenario Outline with the few rows that matter. The remaining rows go to unit/component tests.
- Scenarios that differ only in a setup detail irrelevant to the outcome should be merged.

## Drop
- Exact duplicates.
- A scenario whose steps are all contained in another scenario, for example "payment booked" when "payment booked then returned" exists. Keep the smaller one only if it is the fastest golden smoke for that payment type; in that case decide `e2e` or `golden`.
- Disabled/@wip scenarios nobody has fixed: fix them or delete them. Don't keep them as documentation.

## Tie-breakers when unsure
1. Would a production incident in this flow move or lose money, or break a scheme rulebook obligation? If yes, keep it E2E (at least extended).
2. Does the scenario prove an interaction between two or more deployed systems that no contract/component test covers? If yes, keep it E2E.
3. Otherwise move it down. Record in the decision comment which lower-level test must exist before deletion.
