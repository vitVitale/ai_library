"""Convert Confluence storage format (XHTML + ac:/ri: macros) into compact Markdown.

Keeps what carries meaning for QA work (headings, text, lists, tables, links, code, Jira keys, task
lists, status lozenges) and drops what only costs tokens (styles, images, layout, TOC/navigation macros).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = {"br", "hr", "img", "col", "input", "meta", "link", "wbr"}
# Macros whose output is navigation/decoration or dynamic content not present in storage format.
DROP_MACROS = {
    "toc", "toc-zone", "children", "pagetree", "pagetreesearch", "anchor", "recently-updated",
    "attachments", "gallery", "livesearch", "contentbylabel", "profile", "profile-picture",
    "viewfile", "view-file", "multimedia", "widget", "gadget", "roadmap", "chart", "blog-posts",
    "space-attachments", "popular-labels", "related-labels", "create-from-template", "drawio",
    "gliffy", "plantuml",
}
INCLUDE_MACROS = {"include", "excerpt-include"}
CODE_MACROS = {"code", "noformat"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


@dataclass
class Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)

    def find(self, tag: str) -> "Node | None":
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    return child
                found = child.find(tag)
                if found is not None:
                    return found
        return None

    def params(self) -> dict[str, str]:
        """ac:parameter children of a macro as {name: text}."""
        return {
            c.attrs.get("ac:name", ""): _text(c).strip()
            for c in self.children
            if isinstance(c, Node) and c.tag == "ac:parameter"
        }


@dataclass
class Converted:
    markdown: str
    headings: list[str]
    jira_macro_keys: list[str]
    link_titles: list[str]


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(storage: str) -> Node:
    # CDATA (code macro bodies) is escaped first so the HTML parser keeps it as plain text.
    storage = CDATA_RE.sub(lambda m: html.escape(m.group(1), quote=False), storage)
    builder = _TreeBuilder()
    builder.feed(storage)
    builder.close()
    return builder.root


def convert(storage: str) -> Converted:
    renderer = _Renderer()
    md = renderer.render(parse(storage))
    md = _tidy(md.replace("\xa0", " "))
    return Converted(md, renderer.headings, renderer.jira, renderer.links)


def _tidy(md: str) -> str:
    """Collapse stray spaces outside code fences (list indentation of 2+ spaces is kept)."""
    lines, in_fence = [], False
    for line in md.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            line = re.sub(r"(?<=\S) {2,}", " ", line.rstrip())
            line = re.sub(r"(?<=\S) +([.,;:!?)])", r"\1", line)
            if re.match(r" \S", line):
                line = line[1:]
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _text(node) -> str:
    if isinstance(node, str):
        return node
    return "".join(_text(c) for c in node.children)


def _inline(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class _Renderer:
    def __init__(self) -> None:
        self.headings: list[str] = []
        self.jira: list[str] = []
        self.links: list[str] = []

    def render(self, node) -> str:
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node)
        method = getattr(self, "_" + re.sub(r"[^a-z0-9]", "_", node.tag), None)
        if method is not None:
            return method(node)
        if node.tag in HEADINGS:
            return self._heading(node, HEADINGS[node.tag])
        if node.tag.startswith("ri:"):
            return ""
        return self.children(node)

    def children(self, node: Node) -> str:
        return "".join(self.render(c) for c in node.children)

    # --- block elements -------------------------------------------------------------------------
    def _heading(self, node, level):
        text = _inline(self.children(node))
        if not text:
            return ""
        self.headings.append(text)
        return f"\n\n{'#' * level} {text}\n\n"

    def _p(self, node):
        return f"\n\n{self.children(node).strip()}\n\n"

    def _br(self, node):
        return "\n"

    def _hr(self, node):
        return "\n\n"

    def _blockquote(self, node):
        inner = self.children(node).strip()
        return "\n\n" + "\n".join("> " + line for line in inner.splitlines()) + "\n\n"

    def _pre(self, node):
        return f"\n\n```\n{_text(node).strip()}\n```\n\n"

    def _ul(self, node):
        return self._list(node, ordered=False)

    def _ol(self, node):
        return self._list(node, ordered=True)

    def _list(self, node, ordered):
        lines = []
        items = [c for c in node.children if isinstance(c, Node) and c.tag == "li"]
        for i, li in enumerate(items, 1):
            prefix = f"{i}. " if ordered else "- "
            body = [ln for ln in self.children(li).strip().splitlines() if ln.strip()]
            if not body:
                continue
            lines.append(prefix + body[0].strip())
            lines.extend(" " * len(prefix) + ln for ln in body[1:])
        return "\n\n" + "\n".join(lines) + "\n\n" if lines else ""

    def _table(self, node):
        rows = []
        for tr in _descendants(node, "tr"):
            cells = [c for c in tr.children if isinstance(c, Node) and c.tag in ("td", "th")]
            rows.append([_inline(self.children(c)).replace("|", "\\|") for c in cells])
        rows = [r for r in rows if any(r)]
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
        out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n\n" + "\n".join(out) + "\n\n"

    # --- inline elements ------------------------------------------------------------------------
    def _a(self, node):
        text = _inline(self.children(node))
        href = node.attrs.get("href") or ""
        if not href or href.startswith("#") or text == href:
            return text or href
        return f"[{text or href}]({href})"

    def _code(self, node):
        text = _inline(_text(node))
        return f"`{text}`" if text else ""

    def _img(self, node):
        return ""

    def _colgroup(self, node):
        return ""

    def _time(self, node):
        return node.attrs.get("datetime", "")

    # --- Confluence-specific --------------------------------------------------------------------
    def _ac_image(self, node):
        return ""

    def _ac_emoticon(self, node):
        return ""

    def _ac_placeholder(self, node):
        return ""

    def _ac_parameter(self, node):
        return ""

    def _ac_link(self, node):
        page = node.find("ri:page")
        body = node.find("ac:plain-text-link-body") or node.find("ac:link-body")
        text = _inline(_text(body)) if body is not None else ""
        if page is None:
            return text  # links to attachments, users, anchors: keep the visible text only
        title = page.attrs.get("ri:content-title", "")
        if not title:
            return text
        if title not in self.links:
            self.links.append(title)
        return f"[[{title}]]" if not text or text == title else f"{text} [[{title}]]"

    def _ac_task_list(self, node):
        lines = []
        for task in _descendants(node, "ac:task"):
            status = task.find("ac:task-status")
            body = task.find("ac:task-body")
            done = status is not None and _text(status).strip() == "complete"
            text = _inline(self.children(body)) if body is not None else ""
            if text:
                lines.append(f"- [{'x' if done else ' '}] {text}")
        return "\n\n" + "\n".join(lines) + "\n\n" if lines else ""

    def _ac_structured_macro(self, node):
        name = node.attrs.get("ac:name", "")
        params = node.params()
        if name in DROP_MACROS:
            return ""
        if name == "jira":
            key = params.get("key", "")
            if key:
                if key not in self.jira:
                    self.jira.append(key)
                return f" {key} "
            return ""
        if name == "status":
            title = params.get("title", "")
            return f" [{title}] " if title else ""
        if name in CODE_MACROS:
            body = node.find("ac:plain-text-body")
            lang = params.get("language", "")
            return f"\n\n```{lang}\n{_text(body).strip() if body is not None else ''}\n```\n\n"
        if name in INCLUDE_MACROS:
            return self._ac_link(node)
        body = node.find("ac:rich-text-body")
        if body is None:
            return ""
        inner = self.children(body)
        title = params.get("title", "")
        return f"\n\n**{title}**\n\n{inner}" if title else inner

    _ac_macro = _ac_structured_macro


def _descendants(node: Node, tag: str):
    for child in node.children:
        if isinstance(child, Node):
            if child.tag == tag:
                yield child
            else:
                yield from _descendants(child, tag)
