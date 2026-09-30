import json
from pathlib import Path

from ailib.validate import validate

from conftest import write

REPO_ROOT = Path(__file__).resolve().parents[2]


def errors(root):
    return [i.message for i in validate(root) if i.level == "error"]


def test_valid_library_has_no_issues(make_library):
    root = make_library()
    assert validate(root) == []


def test_skill_name_must_match_directory(make_library):
    root = make_library()
    skill = root / "plugins/alpha/skills/one/SKILL.md"
    skill.write_text(skill.read_text().replace("name: one", "name: uno"))
    assert any("must equal the directory name" in m for m in errors(root))


def test_missing_description_and_bad_frontmatter(make_library):
    root = make_library()
    write(root / "plugins/alpha/skills/bad/SKILL.md", "---\nname: bad\n---\n")
    write(root / "plugins/beta/skills/worse/SKILL.md", "no frontmatter")
    msgs = errors(root)
    assert "'description' is required" in msgs
    assert any("must start with a '---'" in m for m in msgs)


def test_broken_relative_link(make_library):
    root = make_library()
    (root / "plugins/alpha/skills/one/references/details.md").unlink()
    assert "broken relative link: references/details.md" in errors(root)


def test_duplicate_skill_names_across_plugins(make_library):
    root = make_library()
    write(root / "plugins/beta/skills/one/SKILL.md",
          "---\nname: one\ndescription: Dup. Use when duplicating.\n---\n")
    assert any("skill name 'one' is also used by" in m for m in errors(root))


def test_plugin_manifest_name_and_version(make_library):
    root = make_library()
    write(root / "plugins/beta/.claude-plugin/plugin.json", json.dumps({"name": "gamma", "version": "1"}))
    msgs = errors(root)
    assert any("must equal marketplace entry name 'beta'" in m for m in msgs)
    assert any("semver" in m for m in msgs)


def test_marketplace_source_rules(make_library):
    root = make_library()
    mp = root / ".claude-plugin/marketplace.json"
    data = json.loads(mp.read_text())
    data["plugins"][1]["source"] = "./plugins/missing"
    mp.write_text(json.dumps(data))
    assert any("source directory does not exist" in m for m in errors(root))


def test_agent_unknown_tool_warns(make_library):
    root = make_library()
    agent = root / "plugins/alpha/agents/rev.md"
    agent.write_text(agent.read_text().replace("tools: Read", "tools: Frobnicate, Read"))
    warnings = [i.message for i in validate(root) if i.level == "warning"]
    assert any("Frobnicate" in w for w in warnings)


def test_real_library_is_valid():
    assert errors(REPO_ROOT) == []
