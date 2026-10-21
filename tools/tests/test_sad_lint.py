import base64
import urllib.parse
import zlib
from pathlib import Path

import sad_lint
from sad_lint import lint

TEMPLATE = (Path(__file__).resolve().parents[2]
            / "plugins/solution-architecture/skills/solution-design-doc/templates/solution-design.md")

GOOD = """# Instant Payments — Solution Design
## Context and problem
Customers wait a day for transfers. The Payment API and Payment Processor fix this.
## Goals and non-goals
Settle in under 10 s.
## Functional requirements
FR-1 customer submits a payment.
## Quality attributes
- QA-1 p99 latency < 300 ms at 500 TPS
- QA-2 availability 99.95 % monthly
## Solution overview
### System context
```mermaid
C4Context
  Person(c, "Customer")
  System(s, "Instant Payments")
  System_Ext(csm, "Clearing Mechanism")
  Rel(c, s, "pays", "HTTPS")
```
The Customer uses Instant Payments, which talks to the Clearing Mechanism.
### Containers
```plantuml
@startuml
component "Payment API" as api
database "Payment DB" as db
@enduml
```
The Payment DB stores orders.
## Data
Orders in PostgreSQL.
## Integration
Kafka events.
## Security
OAuth2 and mTLS.
## Deployment
OpenShift, two zones.
## Operations
Dashboards per QA target.
## Testing approach
Performance tests at 500 TPS.
## Architecture decisions
ADR-001 Kafka.
## Alternatives considered
Batch SCT.
## Risks and open questions
Scheme certification date.
"""


def write(tmp_path, text, name="sdd.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def checks(rep, check=None, severity=None):
    return [f for f in rep.findings if (check is None or f.check == check)
            and (severity is None or f.severity == severity)]


def test_complete_document_has_no_findings(tmp_path):
    rep = lint(write(tmp_path, GOOD))
    assert rep.findings == []
    assert len(rep.sections_found) == len(sad_lint.SECTIONS)
    assert [d.kind for d in rep.diagrams] == ["mermaid", "plantuml"]
    assert rep.diagrams[0].is_context
    assert rep.diagrams[0].labels == ["Customer", "Instant Payments", "Clearing Mechanism"]
    assert rep.diagrams[1].labels == ["Payment API", "Payment DB"]


def test_missing_sections_and_diagrams_are_errors(tmp_path):
    rep = lint(write(tmp_path, "# Doc\n## Context\nSome text.\n## Data\nOrders.\n"))
    missing = {f.message for f in checks(rep, "section", "error")}
    assert "Missing section: Quality attributes / NFRs" in missing
    assert "Missing section: Security and compliance" in missing
    assert not any("Data" in m for m in missing)
    assert checks(rep, "diagram", "error")
    assert sad_lint.main([str(tmp_path / "sdd.md")]) == 1


def test_placeholders_in_prose_but_not_in_code(tmp_path):
    text = GOOD + "\nOwner: <solution architect>, TBD.\n```java\nList<String> x; // TODO\n```\n<https://x.org>\n"
    found = [f.message for f in checks(lint(write(tmp_path, text)), "placeholder")]
    assert len(found) == 2
    assert any("<solution architect>" in m for m in found) and any("TBD" in m for m in found)


def test_vague_nfr_flagged(tmp_path):
    text = GOOD.replace("- QA-2 availability 99.95 % monthly", "- The system must be highly available and fast")
    nfr = checks(lint(write(tmp_path, text)), "nfr")
    assert len(nfr) == 1 and "highly available" in nfr[0].message and nfr[0].line


def test_nfr_section_without_numbers(tmp_path):
    text = GOOD.replace("- QA-1 p99 latency < 300 ms at 500 TPS\n- QA-2 availability 99.95 % monthly",
                        "Good performance expected.")
    assert any("no numeric targets" in f.message for f in checks(lint(write(tmp_path, text)), "nfr"))


def test_diagram_element_not_in_text(tmp_path):
    text = GOOD.replace('database "Payment DB" as db', 'database "Payment DB" as db\nqueue "Fraud Engine" as f')
    cons = checks(lint(write(tmp_path, text)), "consistency")
    assert len(cons) == 1 and "Fraud Engine" in cons[0].message


def test_generic_suffix_is_ignored_when_matching_text():
    assert sad_lint.mentioned("Ledger Service", "the ledger keeps balances")
    assert not sad_lint.mentioned("Fraud Engine", "the ledger keeps balances")


def test_mermaid_flowchart_and_sequence_labels():
    flow = 'flowchart LR\n  a["Payment API"] -->|"HTTPS"| b[(Payment DB)]\n  b --> c{Fraud check}'
    assert sad_lint.labels_from_code("mermaid", flow) == ["Payment API", "Payment DB", "Fraud check"]
    seq = "sequenceDiagram\n  participant A as Payment API\n  participant B\n  A->>B: call"
    assert sad_lint.labels_from_code("mermaid", seq) == ["Payment API"]


def drawio_xml(compressed):
    model = ('<mxGraphModel><root><mxCell id="0"/><mxCell id="2" value="&lt;b&gt;Payment API&lt;/b&gt;" vertex="1"/>'
             '<mxCell id="3" value="calls" edge="1"/><mxCell id="4" value="Ledger" vertex="1"/></root></mxGraphModel>')
    if not compressed:
        return f'<mxfile><diagram name="p">{model}</diagram></mxfile>'
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    payload = base64.b64encode(c.compress(urllib.parse.quote(model).encode()) + c.flush()).decode()
    return f'<mxfile><diagram name="p">{payload}</diagram></mxfile>'


def test_linked_drawio_plain_and_compressed(tmp_path):
    for compressed in (False, True):
        (tmp_path / "context.drawio").write_text(drawio_xml(compressed), encoding="utf-8")
        rep = lint(write(tmp_path, "# X\n## Context\nThe Payment API.\n[diagram](context.drawio)\n"))
        d = rep.diagrams[0]
        assert (d.kind, d.labels, d.is_context) == ("drawio", ["Payment API", "Ledger"], True)
        assert any("Ledger" in f.message for f in checks(rep, "consistency"))


def test_broken_links_and_image_only_diagrams(tmp_path):
    (tmp_path / "ctx.png").write_bytes(b"png")
    rep = lint(write(tmp_path, "# X\n## System context\n![c](ctx.png)\n[spec](missing.yaml) [web](https://a.b/c)\n"))
    assert [f.message for f in checks(rep, "link")] == ["Broken relative link: missing.yaml"]
    assert rep.diagrams[0].kind == "image" and rep.diagrams[0].is_context
    assert any("Image-only" in f.message for f in checks(rep, "diagram"))


def test_template_has_all_sections_and_only_placeholder_findings(tmp_path):
    rep = lint(TEMPLATE)
    assert not checks(rep, "section")
    assert not checks(rep, severity="error")
    assert checks(rep, "placeholder")


def test_cli_json_and_strict(tmp_path, capsys):
    p = write(tmp_path, GOOD + "\nTBD\n")
    assert sad_lint.main([str(p)]) == 0
    assert sad_lint.main([str(p), "--strict"]) == 1
    capsys.readouterr()
    sad_lint.main([str(p), "--json"])
    assert '"check": "placeholder"' in capsys.readouterr().out
