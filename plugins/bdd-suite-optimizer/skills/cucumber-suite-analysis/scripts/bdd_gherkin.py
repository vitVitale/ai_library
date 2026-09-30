"""Minimal Gherkin (.feature) parser, standard library only. English keywords.

Handles Feature/Rule/Background/Scenario/Scenario Outline/Examples, tags (inherited from Feature and
Rule), And/But (resolved to the previous Given/When/Then), data tables and doc strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SCENARIO_KWS = ("Scenario Outline:", "Scenario Template:", "Scenario:", "Example:")
EXAMPLES_KWS = ("Examples:", "Scenarios:")
STEP_RE = re.compile(r"^(Given|When|Then|And|But|\*)\s+(.*)$")


@dataclass
class Step:
    kind: str  # Given | When | Then
    text: str
    line: int
    table_header: list[str] | None = None
    table_rows: int = 0
    docstring: bool = False


@dataclass
class Examples:
    tags: list[str]
    header: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    line: int
    tags: list[str]
    rule: str
    background: list[Step]
    steps: list[Step] = field(default_factory=list)
    examples: list[Examples] = field(default_factory=list)

    @property
    def outline(self) -> bool:
        return bool(self.examples)

    @property
    def example_rows(self) -> int:
        return sum(len(e.rows) for e in self.examples)

    def first_row(self) -> dict[str, str]:
        for e in self.examples:
            if e.rows:
                return dict(zip(e.header, e.rows[0]))
        return {}


@dataclass
class Feature:
    path: Path
    name: str = ""
    tags: list[str] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)


def _tags(line: str) -> list[str]:
    return [t for t in line.split("#", 1)[0].split() if t.startswith("@")]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(path: Path) -> Feature:
    feature = Feature(path)
    pending: list[str] = []
    feature_bg: list[Step] = []
    rule, rule_tags, rule_bg = "", [], []
    background: list[Step] | None = None  # the Background currently being filled
    scenario: Scenario | None = None
    examples: Examples | None = None
    last_step: Step | None = None
    last_kind = "Given"
    docstring = None

    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = raw.strip()
        if docstring:
            if s.startswith(docstring):
                docstring = None
            continue
        if not s or s.startswith("#"):
            continue
        if s.startswith("@"):
            pending += _tags(s)
            continue
        if s.startswith('"""') or s.startswith("```"):
            docstring = s[:3]
            if last_step:
                last_step.docstring = True
            continue

        if s.startswith("Feature:"):
            feature.name, feature.tags, pending = s[8:].strip(), pending, []
            background, scenario, examples, last_step = None, None, None, None
        elif s.startswith("Rule:"):
            rule, rule_tags, rule_bg, pending = s[5:].strip(), pending, [], []
            background, scenario, examples, last_step = None, None, None, None
        elif s.startswith("Background:"):
            background = rule_bg if rule else feature_bg
            scenario, examples, last_step, pending = None, None, None, []
        elif s.startswith(SCENARIO_KWS):
            name = s.split(":", 1)[1].strip()
            scenario = Scenario(name, lineno, feature.tags + rule_tags + pending, rule, feature_bg + rule_bg)
            feature.scenarios.append(scenario)
            background, examples, last_step, pending = None, None, None, []
        elif s.startswith(EXAMPLES_KWS):
            if scenario is not None:
                examples = Examples(pending)
                scenario.examples.append(examples)
            last_step, pending = None, []
        elif (m := STEP_RE.match(s)) and (scenario is not None or background is not None):
            kw = m.group(1)
            kind = last_kind if kw in ("And", "But", "*") else kw
            last_kind = kind
            last_step = Step(kind, m.group(2).strip(), lineno)
            (background if background is not None else scenario.steps).append(last_step)
            examples = None
        elif s.startswith("|"):
            if examples is not None:
                if not examples.header:
                    examples.header = _cells(s)
                else:
                    examples.rows.append(_cells(s))
            elif last_step is not None:
                if last_step.table_header is None:
                    last_step.table_header = _cells(s)
                else:
                    last_step.table_rows += 1
        # anything else is free-text description: ignored
    return feature
