"""Claude Code tool names -> GitHub Copilot custom agent tool aliases.

Source: https://docs.github.com/en/copilot/reference/custom-agents-configuration (tool aliases table).
"""

from __future__ import annotations

CLAUDE_TO_COPILOT: dict[str, str] = {
    "Bash": "execute",
    "Read": "read",
    "NotebookRead": "read",
    "Edit": "edit",
    "MultiEdit": "edit",
    "Write": "edit",
    "NotebookEdit": "edit",
    "Grep": "search",
    "Glob": "search",
    "Task": "agent",
    "Agent": "agent",
    "WebSearch": "web",
    "WebFetch": "web",
    "TodoWrite": "todo",
}


def parse_tools(value) -> list[str]:
    """Normalize a Claude ``tools`` value (comma-separated string or list) into a list of names."""
    if value is None:
        return []
    if isinstance(value, str):
        items = _split_top_level_commas(value)
    else:
        items = [str(v) for v in value]
    return [t.strip() for t in items if t.strip()]


def base_name(tool: str) -> str:
    """``Agent(worker, researcher)`` -> ``Agent``; ``Bash(git *)`` -> ``Bash``."""
    return tool.split("(", 1)[0].strip()


def to_copilot(tools: list[str]) -> tuple[list[str], list[str]]:
    """Map Claude tool names to Copilot aliases. Returns (mapped aliases, unmapped tool names)."""
    mapped: list[str] = []
    unmapped: list[str] = []
    for tool in tools:
        alias = CLAUDE_TO_COPILOT.get(base_name(tool))
        if alias is None:
            unmapped.append(tool)
        elif alias not in mapped:
            mapped.append(alias)
    return mapped, unmapped


def _split_top_level_commas(value: str) -> list[str]:
    # Commas inside parentheses belong to one tool spec, e.g. "Agent(a, b), Read".
    parts, depth, current = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts
