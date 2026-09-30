"""Find Cucumber step definitions in Java/Kotlin glue code and what systems each one touches.

Supports annotation style (@Given("...")) and Java 8 lambda style (Given("...", (...) -> {...})),
both Cucumber expressions and regular expressions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

ANNOTATION_RE = re.compile(r'@(Given|When|Then|And|But|Step)\s*\(\s*(?:value\s*=\s*)?"((?:[^"\\]|\\.)*)"')
LAMBDA_RE = re.compile(r'(?<![@\w.])(Given|When|Then|And|But)\s*\(\s*"((?:[^"\\]|\\.)*)"\s*,')
METHOD_RE = re.compile(r"(?:public|protected|private|fun|void)\s[^;{]*?(\w+)\s*\(")
PARAM_TYPES = {
    "int": r"-?\d+", "long": r"-?\d+", "byte": r"-?\d+", "short": r"-?\d+", "biginteger": r"-?\d+",
    "float": r"-?\d*[.,]?\d+", "double": r"-?\d*[.,]?\d+", "bigdecimal": r"-?\d*[.,]?\d+",
    "word": r"[^\s]+", "string": r"(?:\"[^\"]*\"|'[^']*')", "": r".*",
}
MAX_BODY = 6000


@dataclass
class StepDef:
    pattern: str
    regex: re.Pattern
    location: str  # path:line
    method: str
    layers: set[str] = field(default_factory=set)


def expression_to_regex(expr: str) -> str:
    """Cucumber expression -> regex: {params}, (optional) text, alternative/text, \\ escapes."""
    out = []
    for token in re.split(r"(\s+)", expr):
        if not token or token.isspace():
            out.append(r"\s+" if token else "")
            continue
        if "/" in token and "{" not in token and "(" not in token:
            out.append("(?:" + "|".join(re.escape(alt) for alt in token.split("/")) + ")")
            continue
        i = 0
        while i < len(token):
            ch = token[i]
            if ch == "\\" and i + 1 < len(token):
                out.append(re.escape(token[i + 1]))
                i += 2
            elif ch == "{":
                end = token.find("}", i)
                if end < 0:
                    out.append(re.escape(ch))
                    i += 1
                    continue
                name = token[i + 1:end].lower()
                out.append(PARAM_TYPES.get(name, r".*"))
                i = end + 1
            elif ch == "(":
                end = token.find(")", i)
                if end < 0:
                    out.append(re.escape(ch))
                    i += 1
                    continue
                out.append("(?:" + re.escape(token[i + 1:end]) + ")?")
                i = end + 1
            else:
                out.append(re.escape(ch))
                i += 1
    return "".join(out)


def compile_pattern(pattern: str) -> re.Pattern | None:
    rx = pattern if pattern.startswith("^") or pattern.endswith("$") else "^" + expression_to_regex(pattern) + "$"
    try:
        return re.compile(rx)
    except re.error:
        return None


def _unescape_java(s: str) -> str:
    return re.sub(r"\\([\"'\\])", r"\1", s)


def _body(text: str, start: int, end: int) -> str:
    """Text of the first {...} block in text[start:end] (brace matching, skipping string literals).

    ``end`` is the next step definition, so odd code (unbalanced quotes) can't leak into other steps."""
    open_at = text.find("{", start, end)
    if open_at < 0:
        return ""
    depth, i, n = 0, open_at, min(end, open_at + MAX_BODY)
    while i < n:
        ch = text[i]
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_at:i + 1]
        i += 1
    return text[open_at:n]


def scan(files: list[Path], root: Path, layer_patterns: dict[str, list[str]]) -> list[StepDef]:
    layers_rx = {name: re.compile("|".join(pats), re.I) for name, pats in layer_patterns.items() if pats}
    defs: list[StepDef] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        matches = sorted([(m, rx is ANNOTATION_RE) for rx in (ANNOTATION_RE, LAMBDA_RE) for m in rx.finditer(text)],
                         key=lambda mm: mm[0].start())
        for i, (m, annotated) in enumerate(matches):
            pattern = _unescape_java(m.group(2))
            compiled = compile_pattern(pattern)
            if compiled is None:
                continue
            end = matches[i + 1][0].start() if i + 1 < len(matches) else len(text)
            method = METHOD_RE.search(text, m.end(), end) if annotated else None
            body = _body(text, m.end(), end)
            line = text.count("\n", 0, m.start()) + 1
            defs.append(StepDef(
                pattern=pattern, regex=compiled,
                location=f"{path.relative_to(root).as_posix()}:{line}",
                method=method.group(1) if method else "lambda",
                layers={name for name, lrx in layers_rx.items() if lrx.search(body)},
            ))
    return defs


class StepMatcher:
    """Resolve step text to a step definition (cached; many steps repeat across scenarios)."""

    def __init__(self, defs: list[StepDef]):
        self.defs = defs
        self._cache: dict[str, StepDef | None] = {}

    def match(self, text: str) -> StepDef | None:
        if text not in self._cache:
            self._cache[text] = next((d for d in self.defs if d.regex.search(text)), None)
        return self._cache[text]
