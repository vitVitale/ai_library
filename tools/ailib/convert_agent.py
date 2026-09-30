"""Convert a Claude Code subagent file into a GitHub Copilot custom agent (.agent.md)."""

from __future__ import annotations

from . import frontmatter, tool_map


def to_copilot(text: str) -> tuple[str, list[str]]:
    """Return (converted file content, warnings).

    Keeps ``name`` and ``description``, maps ``tools`` to Copilot aliases and drops Claude-only
    fields (``model``, ``permissionMode``, ``skills``, ...). The body is copied verbatim.
    Omitting ``tools`` means "all tools" in both products, so it stays omitted.
    """
    meta, body = frontmatter.parse(text)
    warnings: list[str] = []
    out: dict = {}
    if "name" in meta:
        out["name"] = meta["name"]
    out["description"] = meta.get("description", "")

    if "tools" in meta:
        mapped, unmapped = tool_map.to_copilot(tool_map.parse_tools(meta["tools"]))
        if unmapped:
            warnings.append(f"no Copilot equivalent for tools: {', '.join(unmapped)}")
        out["tools"] = mapped

    if meta.get("skills"):
        warnings.append(
            "'skills' preload is Claude-only; mention the skill names in the body so Copilot can find them"
        )
    return frontmatter.dump(out, body), warnings
