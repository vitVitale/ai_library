"""Read and write Markdown files with a YAML frontmatter block."""

from __future__ import annotations

import yaml


class FrontmatterError(ValueError):
    pass


def parse(text: str) -> tuple[dict, str]:
    """Split ``text`` into (frontmatter dict, body). Raises FrontmatterError if missing or invalid."""
    if not text.startswith("---"):
        raise FrontmatterError("file must start with a '---' frontmatter block")
    lines = text.splitlines(keepends=True)
    if lines[0].strip() != "---":
        raise FrontmatterError("first line must be exactly '---'")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw = "".join(lines[1:i])
            body = "".join(lines[i + 1 :])
            break
    else:
        raise FrontmatterError("frontmatter block is not closed with '---'")
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise FrontmatterError(f"invalid YAML in frontmatter: {e}") from e
    if not isinstance(meta, dict):
        raise FrontmatterError("frontmatter must be a YAML mapping")
    return meta, body


def dump(meta: dict, body: str) -> str:
    raw = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=10_000)
    return f"---\n{raw}---\n{body}"
