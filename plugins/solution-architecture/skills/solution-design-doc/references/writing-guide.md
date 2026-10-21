# Writing a solution design: section by section

The SDD answers four questions for its readers: **why** (context, goals), **what** (requirements, quality targets), **how** (views, data, interfaces, deployment), and **what could go wrong** (risks, decisions, alternatives). Write for a reviewer who has 30 minutes.

| Section | Good | Common mistakes |
|---|---|---|
| Context and problem | Business problem, affected users, why now, cost of doing nothing; links to the source requirements | Starting with the solution; copying the whole business case |
| Goals / non-goals | Measurable goals; non-goals that rule out things people might assume | Goals that restate features; no non-goals |
| Functional requirements | IDs (FR-x) so decisions and tests can refer to them; prioritised | Wall of prose; requirements invented by the author |
| Quality attributes | Scenario + measurable target per attribute (ISO 25010: performance, availability, security, maintainability, …), prioritised | "Must be fast/scalable/secure"; every attribute rated top priority |
| Constraints | Regulation, mandated platforms, deadlines, budget, skills | Treating preferences as constraints |
| Context diagram | One box for the solution, every external party and the data exchanged | Showing internals at level 1 |
| Containers | Responsibility + technology + owner for each; protocols on arrows | Boxes named "Service", "Backend"; missing databases/queues |
| Key flows | Happy path **and** a failure/timeout path for the riskiest flows | Only happy paths |
| Data | System of record per entity, classification, retention, consistency model | No owner for shared data; PII not identified |
| Integration | Style (sync/async/batch), contract link, volumes, error handling, versioning | "Integrates with X" without protocol, volume or failure behaviour |
| Security | AuthN/AuthZ, encryption, secrets, trust boundaries, threats + mitigations, compliance mapping | "Security per company standard" with nothing specific |
| Deployment | Environments, zones/regions, scaling unit, network zones | Copying a generic platform diagram |
| Operations | Observability tied to the quality targets, resilience patterns, DR achieving RPO/RTO, cost | Ignoring idempotency on retries; no DR test |
| Testing approach | How each quality target and integration is verified (contract, performance, resilience tests) | "QA will test it" |
| Decisions | One ADR per significant, hard-to-reverse decision, linked to the QA/FR it serves | Decisions buried in prose; no rationale |
| Alternatives | At least one real alternative + "do nothing", compared on the same criteria | Straw-man alternatives |
| Risks / assumptions / open questions | Owner and mitigation or due date for each | Empty table; risks with no owner |
| Enterprise alignment | Standards followed, platforms reused, deviations with ADR + waiver | Silently introducing new technology |
| Transition | Migration, coexistence with legacy, rollback, decommissioning | Big-bang cut-over with no rollback |

## What counts as a significant decision (needs an ADR)
Hard to reverse, affects several teams, adds a technology or vendor, trades one quality attribute off against another, or deviates from an enterprise standard.

## Style
- Use the same names for things in the diagrams, tables and text.
- Prefer tables and bullets over prose. Link to details (OpenAPI, threat model, runbooks) rather than pasting them in.
- Write "we will…" for decisions, and mark unknowns as an **assumption** or **open question** with an owner. Never invent facts to fill a section.
- Every section stays. If something truly doesn't apply, write "N/A" and one sentence explaining why.
