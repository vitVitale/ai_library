# Architecture review checklist

Review with **two lenses**. The **solution lens** asks whether we are building this thing right. The **enterprise lens** asks whether it is the right thing and whether it fits the landscape. Severity guide: **Blocker** = can't be approved; **Major** = must fix before build or go-live; **Minor** = improve; **Question** = the reviewer can't judge without an answer.

## A. Solution lens
### A1. Problem and requirements fit
- [ ] The problem, goals and non-goals are clear; the scope boundaries are explicit.
- [ ] Every Must functional requirement is visibly handled by some container or flow. Spot-check 3–5 FR IDs.
- [ ] Quality attributes have **measurable targets** and priorities. *Major* if the top attributes have no targets.
- [ ] The design actually achieves the targets: e.g. a p99 latency target vs. the synchronous call chain, or an availability target vs. single points of failure. *Blocker* if a top target is clearly unreachable.

### A2. Structure and diagrams
- [ ] A context and a container diagram exist. Their elements have name, type and technology, and their arrows have labels and protocols.
- [ ] The diagrams and the text agree: same names, no orphan elements, no components described in the text but missing from the diagrams.
- [ ] Responsibilities are cohesive: no "god service", no two containers owning the same data or rule.
- [ ] Sync and async choices are justified; coupling between teams' services is minimised.

### A3. Data
- [ ] Each entity has one system of record; shared databases between services are justified.
- [ ] PII / PCI / confidential data is identified, minimised, encrypted, and its retention is defined.
- [ ] The consistency model is stated (strong vs eventual), and so is how duplicates and out-of-order messages are handled.
- [ ] Migration of existing data is planned.

### A4. Integration
- [ ] Every interface has a style, a contract (OpenAPI/AsyncAPI), volumes, an SLA, error handling and a versioning strategy.
- [ ] Retries are **idempotent** (idempotency keys, dedup). Timeouts are set and are less than the caller's timeout.
- [ ] The behaviour when each dependency is down or slow is defined (fallback, queueing, degraded mode).

### A5. Security and compliance
- [ ] AuthN/AuthZ for users **and** service-to-service; least privilege.
- [ ] Encryption in transit and at rest; secrets in a vault, never in config or code.
- [ ] Trust boundaries are drawn; top threats have mitigations, and there is a threat model or link.
- [ ] Regulatory requirements (e.g. GDPR, PSD2, PCI-DSS, DORA) are mapped to controls; audit logging is in place.

### A6. Operations and resilience
- [ ] Observability (metrics, logs, traces, alerts) is tied to the quality targets; on-call ownership and runbooks exist.
- [ ] No single point of failure for the top-availability components; resilience patterns are named.
- [ ] RPO/RTO are stated, the DR mechanism achieves them, and DR testing is planned.
- [ ] Capacity is sized for peak plus growth; a cost estimate exists.

### A7. Delivery
- [ ] A testing approach covers the quality targets (performance, resilience, contract tests) and the test environments and data.
- [ ] Rollout: feature flags or phased rollout, coexistence with legacy, a **rollback plan**, decommissioning.
- [ ] The team has the skills to build and run it (or a plan to get them); dependencies on other teams are listed with dates.

### A8. Decisions and risks
- [ ] Each significant decision has an ADR with real alternatives and stated trade-offs.
- [ ] Risks, assumptions and open questions have owners and mitigations. *Major* if obvious risks are missing.

## B. Enterprise lens
Check against the organisation's guardrails file if one is provided (see [../templates/architecture-guardrails.md](../templates/architecture-guardrails.md)). Without one, ask which standards apply and mark the items **Question**.
- [ ] **Principles**: the design follows the stated architecture principles (e.g. API-first, cloud-first, buy-before-build, event-driven integration).
- [ ] **Technology**: everything used is on the approved list or tech radar. Anything on hold, deprecated or new needs an ADR + waiver; *Major* if missing.
- [ ] **Reuse**: existing enterprise capabilities and platforms (IdP, API gateway, messaging, logging, payments hub, MDM) are reused, and the design doesn't duplicate a capability another system already owns.
- [ ] **Capability and data ownership**: the solution fits the capability map; it doesn't become a second system of record for data owned elsewhere.
- [ ] **Integration standards**: it uses the approved integration patterns and middleware, and follows the API and event naming and versioning guidelines.
- [ ] **Security and compliance baseline**: it meets enterprise security standards and data classification policy.
- [ ] **Roadmap fit**: it moves towards the target architecture, doesn't build on systems scheduled for decommissioning, and new technical debt is recorded.

## Output expectations
- Each finding gives: location (section / diagram / line), what's wrong, why it matters (which QA, FR or standard), and a concrete recommendation.
- Verdict: **Approve**, **Approve with conditions** (list the conditions), or **Rework**. Any Blocker means Rework.
