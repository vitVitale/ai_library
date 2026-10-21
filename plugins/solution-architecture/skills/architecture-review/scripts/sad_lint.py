#!/usr/bin/env python3
"""Lint a solution design document (Markdown) before a human/AI review. Offline, stdlib only.

Checks:
  section     required SDD sections present (matched by heading synonyms)
  placeholder TBD / TODO / ??? / <template markers> left in the text
  diagram     at least one diagram; a system-context diagram; diagram files parse
  consistency elements named in diagrams but never mentioned in the text
  nfr         quality-attribute statements without a measurable target ("highly available")
  link        relative links / images / diagram files that don't exist
Diagrams: ```mermaid / ```plantuml / ```puml blocks, and linked .mmd / .puml / .plantuml / .drawio files.

Usage: sad_lint.py <doc.md> [--json] [--strict]
Exit code 1 if there are errors (or warnings with --strict).
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

# key, display name, heading regex, severity when missing
SECTIONS = [
    ("context", "Context / problem statement", r"context|background|problem|introduction|purpose|executive summary", "error"),
    ("scope", "Goals, non-goals and scope", r"scope|goals?\b|non-goals|objectives", "error"),
    ("requirements", "Functional requirements", r"functional requirement|requirements|use cases?|user stor|capabilit", "error"),
    ("quality", "Quality attributes / NFRs", r"non-functional|nfrs?\b|quality attribute|quality requirement|service level|sl[ao]s?\b", "error"),
    ("architecture", "Solution overview / architecture views", r"solution overview|architecture|solution design|high[- ]level design|container|component|logical view", "error"),
    ("data", "Data", r"data|information model|domain model|persistence|storage", "warning"),
    ("integration", "Integration and interfaces", r"integration|interfaces?|apis?\b|contracts?|messaging|events?", "warning"),
    ("security", "Security and compliance", r"security|authentication|authori[sz]ation|privacy|compliance|threat", "error"),
    ("deployment", "Deployment and infrastructure", r"deployment|infrastructure|hosting|environments?|physical view", "warning"),
    ("operations", "Operations / observability / resilience", r"operations?|operability|observability|monitoring|resilience|disaster recovery|backup|support model", "warning"),
    ("testing", "Testing approach", r"testing|testability|test strategy|verification", "warning"),
    ("decisions", "Architecture decisions", r"decisions?|adrs?\b|rationale", "error"),
    ("alternatives", "Alternatives considered", r"alternatives?|options considered|trade-?offs?", "warning"),
    ("risks", "Risks, assumptions, open questions", r"risks?|assumptions?|open questions?|constraints?|dependencies", "error"),
]

PLACEHOLDER_RE = re.compile(
    r"\bTBD\b|\bTBC\b|\bTODO\b|\bFIXME\b|\bXXX\b|\?\?\?|lorem ipsum"
    r"|<(?!/?(?:br|p|b|i|u|a|em|strong|img|div|span|sup|sub|table|tr|td|th|ul|ol|li|code|pre|details|summary|hr)\b)"
    r"(?!https?:|mailto:)[a-z][^<>\n]{2,60}>",
    re.IGNORECASE,
)
VAGUE_RE = re.compile(
    r"\b(fast|quick(ly)?|scalable|highly available|high availability|performant|robust|reliable|secure|"
    r"real[- ]time|responsive|user[- ]friendly|efficient|low latency|minimal downtime|as soon as possible|asap|"
    r"near[- ]zero|seamless(ly)?)\b",
    re.IGNORECASE,
)
FENCE_RE = re.compile(r"^```[ \t]*([\w-]*)[^\n]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
DIAGRAM_LANGS = {"mermaid": "mermaid", "plantuml": "plantuml", "puml": "plantuml"}
DIAGRAM_EXT = {".mmd": "mermaid", ".mermaid": "mermaid", ".puml": "plantuml", ".plantuml": "plantuml",
               ".iuml": "plantuml", ".drawio": "drawio"}
CONTEXT_DIAGRAM_RE = re.compile(r"C4Context|C4_Context|System_Context|\bcontext\b", re.IGNORECASE)

C4_RE = re.compile(r"\b(?:Person|System|Container|Component|Deployment_Node|Node|Boundary|System_Boundary|"
                   r"Container_Boundary|Enterprise_Boundary)(?:Db|Queue)?(?:_Ext)?\s*\(\s*[\w.]+\s*,\s*\"([^\"]+)\"")
MERMAID_NODE_RE = re.compile(r"(?<![|\w])[A-Za-z_][\w-]*\s?[\[\(\{]+\"?([^\]\)\}\"|]+?)\"?[\]\)\}]+")
PARTICIPANT_RE = re.compile(
    r"^\s*(?:actor|participant|component|database|queue|node|cloud|boundary|control|entity|collections|"
    r"rectangle|interface|person|system)\s+(?:\"([^\"]+)\"|(\S+))(?:\s+as\s+(?:\"([^\"]+)\"|(.+?)))?\s*(?:<<.*)?$",
    re.IGNORECASE | re.MULTILINE,
)
GENERIC_WORDS = {"service", "services", "system", "api", "db", "database", "app", "application", "server",
                 "the", "svc", "ui", "module", "component", "container", "store", "queue", "topic"}
NOISE_LABELS = {"yes", "no", "true", "false", "start", "end"}


@dataclass
class Finding:
    severity: str  # error | warning
    check: str
    message: str
    line: int | None = None


@dataclass
class Diagram:
    kind: str
    source: str  # "L<n>" for inline blocks, file path for linked files
    labels: list[str] = field(default_factory=list)
    is_context: bool = False


@dataclass
class Report:
    doc: str
    findings: list[Finding] = field(default_factory=list)
    sections_found: dict[str, str] = field(default_factory=dict)
    diagrams: list[Diagram] = field(default_factory=list)

    def add(self, severity: str, check: str, message: str, line: int | None = None) -> None:
        self.findings.append(Finding(severity, check, message, line))

    def count(self, severity: str) -> int:
        return sum(f.severity == severity for f in self.findings)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks but keep line numbers stable."""
    return FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def headings(prose: str) -> list[tuple[int, int, str]]:
    """(line_no, level, title) for every Markdown heading outside code blocks."""
    out = []
    for i, line in enumerate(prose.splitlines(), 1):
        m = HEADING_RE.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def section_body(lines: list[str], heads: list[tuple[int, int, str]], idx: int) -> list[tuple[int, str]]:
    """Lines under heading idx up to the next heading of the same or higher level."""
    start, level, _ = heads[idx]
    end = len(lines) + 1
    for ln, lvl, _ in heads[idx + 1:]:
        if lvl <= level:
            end = ln
            break
    return [(n, lines[n - 1]) for n in range(start + 1, end)]


def clean_label(label: str) -> str:
    label = html.unescape(re.sub(r"<[^>]+>", " ", label))
    label = re.sub(r"\\n|<br\s*/?>", " ", label)
    return re.sub(r"\s+", " ", label).strip(" \"'`")


def labels_from_code(kind: str, code: str) -> list[str]:
    found = [m.group(1) for m in C4_RE.finditer(code)]
    for m in PARTICIPANT_RE.finditer(code):
        quoted, bare, as_quoted, as_bare = m.groups()
        if kind == "mermaid":  # mermaid: participant <id> as <label>
            found.append(as_quoted or as_bare or quoted or bare)
        else:  # plantuml: component "<label>" as <alias>
            found.append(quoted or bare)
    if kind == "mermaid" and not found:
        found += [m.group(1) for m in MERMAID_NODE_RE.finditer(code)]
    out: list[str] = []
    for raw in found:
        label = clean_label(raw or "")
        if len(label) >= 2 and label.lower() not in NOISE_LABELS and label not in out:
            out.append(label)
    return out


def drawio_labels(path: Path) -> list[str]:
    """Vertex labels from a .drawio file (plain or compressed <diagram> content)."""
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    models = list(root.iter("mxGraphModel"))
    for diagram in root.iter("diagram"):
        payload = (diagram.text or "").strip()
        if payload and not models:
            raw = zlib.decompress(base64.b64decode(payload), -15).decode("utf-8")
            models.append(ET.fromstring(urllib.parse.unquote(raw)))
    labels: list[str] = []
    for model in models:
        for cell in model.iter("mxCell"):
            if cell.get("vertex") == "1" and cell.get("value"):
                label = clean_label(cell.get("value", ""))
                if len(label) >= 2 and label not in labels:
                    labels.append(label)
    return labels


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def mentioned(label: str, prose_norm: str) -> bool:
    n = norm(label)
    if not n or f" {n} " in f" {prose_norm} ":
        return True
    core = " ".join(w for w in n.split() if w not in GENERIC_WORDS)
    return len(core) >= 3 and f" {core} " in f" {prose_norm} "


def lint(doc: Path) -> Report:
    text = doc.read_text(encoding="utf-8")
    prose = strip_fences(text)
    lines = prose.splitlines()
    heads = headings(prose)
    rep = Report(str(doc))

    # sections
    for key, name, pattern, severity in SECTIONS:
        rx = re.compile(rf"\b(?:{pattern})", re.IGNORECASE)
        hit = next((title for _, _, title in heads if rx.search(title)), None)
        if hit:
            rep.sections_found[key] = hit
        else:
            rep.add(severity, "section", f"Missing section: {name}")

    # placeholders (prose only, so generics like List<String> in code are ignored)
    for m in PLACEHOLDER_RE.finditer(prose):
        rep.add("warning", "placeholder", f"Unresolved placeholder: {m.group(0)!r}", line_of(prose, m.start()))

    # diagrams: inline blocks
    for m in FENCE_RE.finditer(text):
        kind = DIAGRAM_LANGS.get(m.group(1).lower())
        if kind:
            ln = line_of(text, m.start())
            near = [t for hl, _, t in heads if hl < ln][-1:]
            is_ctx = bool(CONTEXT_DIAGRAM_RE.search(m.group(2)) or (near and CONTEXT_DIAGRAM_RE.search(near[0])))
            rep.diagrams.append(Diagram(kind, f"L{ln}", labels_from_code(kind, m.group(2)), is_ctx))

    # links, images and linked diagram files
    for m in LINK_RE.finditer(prose):
        target = urllib.parse.unquote(m.group(1).split("#", 1)[0])
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        ln = line_of(prose, m.start())
        path = (doc.parent / target).resolve()
        if not path.exists():
            rep.add("warning", "link", f"Broken relative link: {target}", ln)
            continue
        kind = DIAGRAM_EXT.get(path.suffix.lower())
        if m.group(0).startswith("!") and not kind:
            near = [t for hl, _, t in heads if hl <= ln][-1:]
            rep.diagrams.append(Diagram("image", target, [], bool(near and CONTEXT_DIAGRAM_RE.search(near[0]))))
        elif kind:
            try:
                labels = drawio_labels(path) if kind == "drawio" else labels_from_code(kind, path.read_text(encoding="utf-8"))
            except (ET.ParseError, ValueError, zlib.error, UnicodeDecodeError) as e:
                rep.add("warning", "diagram", f"Cannot parse diagram {target}: {e}", ln)
                labels = []
            near = [t for hl, _, t in heads if hl <= ln][-1:]
            is_ctx = bool(CONTEXT_DIAGRAM_RE.search(target) or (near and CONTEXT_DIAGRAM_RE.search(near[0])))
            rep.diagrams.append(Diagram(kind, target, labels, is_ctx))

    if not rep.diagrams:
        rep.add("error", "diagram", "No diagrams found (expected at least a system-context and a container diagram)")
    elif not any(d.is_context for d in rep.diagrams):
        rep.add("warning", "diagram", "No system-context (C4 level 1) diagram detected")
    if any(d.kind == "image" for d in rep.diagrams):
        rep.add("warning", "diagram", "Image-only diagrams can't be cross-checked against the text; keep the "
                                      ".drawio/.puml/.mmd source next to the document and link it")

    # diagram <-> text consistency
    prose_norm = norm(prose)
    for d in rep.diagrams:
        missing = [lb for lb in d.labels if not mentioned(lb, prose_norm)]
        if missing:
            rep.add("warning", "consistency",
                    f"Diagram {d.source}: elements not described in the text: {', '.join(missing)}")

    # NFR measurability
    q_idx = [i for i, (_, _, t) in enumerate(heads) if re.search(rf"\b(?:{SECTIONS[3][2]})", t, re.IGNORECASE)]
    for i in q_idx:
        body = section_body(lines, heads, i)
        if body and not any(re.search(r"\d", ln) for _, ln in body):
            rep.add("warning", "nfr", f"Section '{heads[i][2]}' has no numeric targets at all", heads[i][0])
        for n, ln in body:
            if VAGUE_RE.search(ln) and not re.search(r"\d", ln):
                rep.add("warning", "nfr", f"Unmeasurable quality statement: {ln.strip()[:120]!r}", n)
    return rep


def render(rep: Report) -> str:
    out = [f"# sad_lint: {rep.doc}", f"Result: {rep.count('error')} errors, {rep.count('warning')} warnings", ""]
    for severity, title in (("error", "Errors"), ("warning", "Warnings")):
        items = [f for f in rep.findings if f.severity == severity]
        if items:
            out.append(f"## {title}")
            out += [f"- [{f.check}]{f' L{f.line}' if f.line else ''} {f.message}" for f in items]
            out.append("")
    kinds = {}
    for d in rep.diagrams:
        kinds[d.kind] = kinds.get(d.kind, 0) + 1
    out.append("## Stats")
    out.append(f"- sections: {len(rep.sections_found)}/{len(SECTIONS)} "
               f"({', '.join(k for k in rep.sections_found)})")
    out.append(f"- diagrams: {len(rep.diagrams)} ({', '.join(f'{k} {v}' for k, v in kinds.items()) or 'none'}), "
               f"elements: {sum(len(d.labels) for d in rep.diagrams)}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc", type=Path, help="solution design document (.md)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    args = ap.parse_args(argv)
    if not args.doc.is_file():
        print(f"not a file: {args.doc}", file=sys.stderr)
        return 2
    rep = lint(args.doc)
    print(json.dumps(asdict(rep), indent=2) if args.json else render(rep), end="" if not args.json else "\n")
    failed = rep.count("error") or (args.strict and rep.count("warning"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
