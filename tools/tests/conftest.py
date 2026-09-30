import json
import sys
from pathlib import Path

import pytest

# The confluence-coverage scripts are standalone files (run as `python script.py`), not a package.
CONFLUENCE_SCRIPTS = (Path(__file__).resolve().parents[2]
                      / "plugins/confluence-coverage/skills/confluence-coverage/scripts")
BDD_SCRIPTS = (Path(__file__).resolve().parents[2]
               / "plugins/bdd-suite-optimizer/skills/cucumber-suite-analysis/scripts")
sys.path.insert(0, str(CONFLUENCE_SCRIPTS))
sys.path.insert(0, str(BDD_SCRIPTS))

SKILL = """---
name: {name}
description: Does {name} things. Use when testing {name}.
---
# {name}

See [details](references/details.md).
"""

AGENT = """---
name: {name}
description: Reviews things. Use when reviewing.
tools: Read, Grep, Glob, Bash
model: sonnet
---
You are {name}.
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def make_library(tmp_path):
    """Build a minimal valid library: plugin 'alpha' (skill 'one', agent 'rev') and plugin 'beta' (skill 'two')."""

    def build(root: Path = tmp_path / "lib") -> Path:
        write(root / ".claude-plugin/marketplace.json", json.dumps({
            "name": "test-lib",
            "owner": {"name": "me"},
            "plugins": [
                {"name": "alpha", "source": "./plugins/alpha", "description": "A"},
                {"name": "beta", "source": "./plugins/beta", "description": "B"},
            ],
        }))
        for plugin, skill in (("alpha", "one"), ("beta", "two")):
            base = root / "plugins" / plugin
            write(base / ".claude-plugin/plugin.json", json.dumps({"name": plugin, "version": "0.1.0"}))
            write(base / "skills" / skill / "SKILL.md", SKILL.format(name=skill))
            write(base / "skills" / skill / "references/details.md", "details\n")
        write(root / "plugins/alpha/agents/rev.md", AGENT.format(name="rev"))
        return root

    return build


@pytest.fixture
def target(tmp_path) -> Path:
    t = tmp_path / "target"
    t.mkdir()
    return t
