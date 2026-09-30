from ailib import frontmatter
from ailib.convert_agent import to_copilot
from ailib.tool_map import parse_tools


def test_maps_tools_and_drops_claude_only_fields():
    text = "---\nname: rev\ndescription: Reviews. Use when reviewing.\ntools: Read, Grep, Glob, Bash, Write\nmodel: sonnet\npermissionMode: plan\n---\nBody here.\n"
    out, warnings = to_copilot(text)
    meta, body = frontmatter.parse(out)
    assert meta == {"name": "rev", "description": "Reviews. Use when reviewing.",
                    "tools": ["read", "search", "execute", "edit"]}
    assert body == "Body here.\n"
    assert warnings == []


def test_omitted_tools_stay_omitted():
    out, _ = to_copilot("---\nname: a\ndescription: d\n---\nx\n")
    assert "tools" not in frontmatter.parse(out)[0]


def test_unmapped_tools_warn():
    _, warnings = to_copilot("---\nname: a\ndescription: d\ntools: [Read, mcp__jira__search]\n---\n")
    assert warnings == ["no Copilot equivalent for tools: mcp__jira__search"]


def test_skills_preload_warns():
    _, warnings = to_copilot("---\nname: a\ndescription: d\nskills: [x]\n---\n")
    assert "Claude-only" in warnings[0]


def test_parse_tools_keeps_parenthesised_commas():
    assert parse_tools("Agent(worker, researcher), Read") == ["Agent(worker, researcher)", "Read"]
