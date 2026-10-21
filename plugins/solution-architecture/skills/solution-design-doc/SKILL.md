---
name: solution-design-doc
description: Write or update a solution design document (SDD / solution architecture document / HLD) with C4 architecture diagrams as code (Mermaid, PlantUML, draw.io), measurable quality attributes (NFRs) and architecture decision records (ADRs). Use when asked to design a solution, draft or restructure an architecture document, draw a system context / container / sequence / deployment diagram, write an ADR, or turn requirements into a solution design.
---

# Solution design documents and diagrams

Work at **solution-architect level**: one solution, one business problem, and an explicit fit with the enterprise standards. The document has to let a reviewer decide whether we are building this thing right, and whether it fits the rest of the landscape.

## Inputs to gather first
1. Requirements or business case. Ask for the pages or files, or read the ones that were linked.
2. The project's existing architecture docs, diagram tool and template. **Follow the project's conventions first**; use [templates/solution-design.md](templates/solution-design.md) only when there is none.
3. The enterprise guardrails, if any: principles, approved tech, integration and data standards. Look for `architecture-guardrails.md` or `docs/architecture/`.
4. If the codebase exists, skim only its build files, deployment manifests and API specs to get the real container and technology names. Don't read the whole repo.

Don't invent facts. Anything unknown goes into section 14 as an **assumption** or **open question** with an owner.

## Workflow
1. **Frame**: context, goals and non-goals, constraints. Confirm these with the user before designing if they're unclear.
2. **Quality attributes**: turn every "fast / scalable / secure" into a scenario with a numeric target (QA-x). Prioritise them, because they drive the design.
3. **Design the views** following [references/diagrams.md](references/diagrams.md): a system context diagram, a container diagram, sequence diagrams for the 2–4 riskiest flows (including a failure path), and a deployment diagram if infrastructure changes. Write diagrams as code, or as a `.drawio` file saved next to the document.
4. **Describe each element** in text using exactly the name it has in the diagram: responsibility, technology, owner.
5. **Cross-cutting sections**: data, integration, security, operations and resilience, testing approach. Use the per-section guidance in [references/writing-guide.md](references/writing-guide.md).
6. **Decisions**: write one ADR per significant decision from [templates/adr.md](templates/adr.md) in `adr/ADR-NNN-<slug>.md` next to the SDD, compare at least two options plus "do nothing", and link each ADR from section 12.
7. **Enterprise alignment**: list the standards you followed and the platforms you reused. Every deviation needs an ADR.
8. **Lint**, then fix everything the linter reports that isn't a deliberate template placeholder:
   ```bash
   python <skills>/architecture-review/scripts/sad_lint.py <path/to/sdd.md>
   ```
   (`<skills>` is the folder this skill is in: `.github/skills` in a Copilot repo, or the plugin's `skills/` folder.)

## Done when
- Every template section is filled in, or marked "N/A" with a one-line reason.
- Every quality attribute has a numeric target. The context and container diagrams exist, and every diagram element is described in the text.
- Every significant decision has an ADR with alternatives. Every risk and open question has an owner.
- `sad_lint.py` reports 0 errors, and every remaining warning is deliberate.
- To check the design against the review checklist before submitting it, use the `architecture-review` skill or the `architecture-reviewer` agent.
