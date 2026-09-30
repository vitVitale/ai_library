import json

from ailib import frontmatter
from ailib.install import LOCK_FILE, install
from ailib.library import load


def kinds(result):
    return {a.rel: a.kind for a in result.actions}


def test_fresh_install_for_copilot(make_library, target):
    lib = load(make_library())
    result = install(lib, target)

    assert (target / ".github/skills/one/SKILL.md").is_file()
    assert (target / ".github/skills/one/references/details.md").is_file()
    assert (target / ".github/skills/two/SKILL.md").is_file()
    meta, _ = frontmatter.parse((target / ".github/agents/rev.agent.md").read_text())
    assert meta["tools"] == ["read", "search", "execute"]
    assert "model" not in meta
    assert set(kinds(result).values()) == {"create"}

    lock = json.loads((target / LOCK_FILE).read_text())
    assert lock["plugins"] == ["alpha", "beta"] and lock["targets"] == ["copilot"]
    assert lock["library"]["plugins"] == {"alpha": "0.1.0", "beta": "0.1.0"}


def test_claude_layout_copies_agent_verbatim(make_library, target):
    root = make_library()
    install(load(root), target, targets=["claude"])
    assert (target / ".claude/agents/rev.md").read_text() == (root / "plugins/alpha/agents/rev.md").read_text()
    assert (target / ".claude/skills/one/SKILL.md").is_file()


def test_dry_run_writes_nothing(make_library, target):
    result = install(load(make_library()), target, dry_run=True)
    assert result.actions and list(target.iterdir()) == []


def test_reinstall_updates_and_removes(make_library, target):
    root = make_library()
    install(load(root), target)

    skill = root / "plugins/alpha/skills/one/SKILL.md"
    skill.write_text(skill.read_text() + "\nMore.\n")
    (root / "plugins/alpha/skills/one/references/details.md").unlink()
    skill.write_text(skill.read_text().replace("See [details](references/details.md).", ""))

    result = install(load(root), target)
    k = kinds(result)
    assert k[".github/skills/one/SKILL.md"] == "update"
    assert k[".github/skills/one/references/details.md"] == "delete"
    assert not (target / ".github/skills/one/references").exists()  # empty dir pruned
    assert k[".github/skills/two/SKILL.md"] == "unchanged"


def test_second_install_reuses_recorded_selection(make_library, target):
    root = make_library()
    install(load(root), target, plugins=["beta"], targets=["claude"])
    result = install(load(root), target)
    assert result.plugins == ["beta"] and result.targets == ["claude"]
    assert not (target / ".github").exists()


def test_narrowing_plugins_removes_their_files(make_library, target):
    root = make_library()
    install(load(root), target)
    install(load(root), target, plugins=["beta"])
    assert not (target / ".github/skills/one").exists()
    assert not (target / ".github/agents").exists()
    assert (target / ".github/skills/two/SKILL.md").is_file()


def test_local_edits_are_not_overwritten_without_force(make_library, target):
    root = make_library()
    install(load(root), target)
    installed = target / ".github/skills/one/SKILL.md"
    installed.write_text("my local edit\n")
    skill = root / "plugins/alpha/skills/one/SKILL.md"
    skill.write_text(skill.read_text() + "\nNew.\n")

    result = install(load(root), target)
    assert kinds(result)[".github/skills/one/SKILL.md"] == "skip"
    assert installed.read_text() == "my local edit\n"

    # still tracked, so the edit keeps being detected
    assert kinds(install(load(root), target))[".github/skills/one/SKILL.md"] == "skip"

    install(load(root), target, force=True)
    assert installed.read_text() == skill.read_text()


def test_existing_user_file_is_not_clobbered(make_library, target):
    user_agent = target / ".github/agents/rev.agent.md"
    user_agent.parent.mkdir(parents=True)
    user_agent.write_text("user's own agent\n")
    result = install(load(make_library()), target)
    assert kinds(result)[".github/agents/rev.agent.md"] == "skip"
    assert user_agent.read_text() == "user's own agent\n"
    lock = json.loads((target / LOCK_FILE).read_text())
    assert ".github/agents/rev.agent.md" not in lock["files"]
