# Architecture guardrails (enterprise lens input)

<!-- Copy this file to the repo as architecture-guardrails.md (or docs/architecture/guardrails.md) and fill it in from your
     enterprise architecture standards. The architecture-reviewer agent checks solution designs against it.
     Keep it short: rules and lists, with links to the full standards. -->

## Principles
- <e.g. API-first: every capability is exposed through a versioned API behind the API gateway>
- <e.g. Reuse before buy before build>
- <e.g. Asynchronous, event-driven integration between domains; no shared databases across domains>

## Technology radar
| Area | Adopt | Hold / deprecated (needs waiver) |
|---|---|---|
| Languages / frameworks | <Java 25, Spring Boot> | <…> |
| Data stores | <PostgreSQL, Oracle> | <…> |
| Messaging | <Kafka, Pulsar> | <…> |
| Hosting | <OpenShift, on-prem DC> | <…> |
| Observability | <…> | <…> |

## Shared platforms to reuse
| Capability | Platform / owner |
|---|---|
| Identity & access | <…> |
| API gateway | <…> |
| Logging / monitoring | <…> |
| Secrets | <…> |

## Data ownership (system of record)
| Data domain | System of record |
|---|---|
| <Customer> | <…> |

## Integration standards
- <API style guide link, versioning rule, event naming, ISO 20022 for payment messages, …>

## Security & compliance baseline
- <data classification policy, encryption standard, regulatory frameworks that apply>

## Systems being decommissioned (don't build on them)
- <…>
