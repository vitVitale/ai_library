"""Install library skills/agents into a target repository and keep them in sync.

A lock file (``.ailib.lock.json``) in the target records what was installed and each file's hash, so
re-running install updates changed files, removes files dropped from the library, and never
overwrites files that were edited locally or not installed by ailib (unless ``force``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import convert_agent
from .library import Library

LOCK_FILE = ".ailib.lock.json"
TARGETS = ("copilot", "claude")

# Where each target product looks for repo-level skills and agents.
LAYOUT = {
    "copilot": {"skills": ".github/skills", "agents": ".github/agents", "agent_suffix": ".agent.md"},
    "claude": {"skills": ".claude/skills", "agents": ".claude/agents", "agent_suffix": ".md"},
}


@dataclass
class Action:
    kind: str  # create | update | unchanged | delete | skip
    rel: str
    note: str = ""


@dataclass
class Result:
    actions: list[Action]
    warnings: list[str]
    plugins: list[str]
    targets: list[str]


def read_lock(target: Path) -> dict:
    path = target / LOCK_FILE
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def install(
    lib: Library,
    target: Path,
    plugins: list[str] | None = None,
    targets: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> Result:
    """Sync ``target`` to contain exactly the selected plugins for the selected products.

    ``plugins``/``targets`` default to what the lock file recorded last time, else all plugins / copilot.
    """
    lock = read_lock(target)
    plugins = plugins if plugins is not None else lock.get("plugins") or [p.name for p in lib.plugins]
    targets = targets if targets is not None else lock.get("targets") or ["copilot"]
    for t in targets:
        if t not in TARGETS:
            raise ValueError(f"unknown target '{t}' (expected one of: {', '.join(TARGETS)})")

    desired, warnings = _desired_files(lib, plugins, targets)
    old: dict[str, str] = lock.get("files", {})
    new: dict[str, str] = {}
    actions: list[Action] = []

    for rel, content in sorted(desired.items()):
        dest = target / rel
        digest = _sha(content)
        if not dest.exists():
            actions.append(Action("create", rel))
        else:
            current = _sha(dest.read_bytes())
            if current == digest:
                actions.append(Action("unchanged", rel))
            elif old.get(rel) == current or force:
                actions.append(Action("update", rel))
            else:
                why = "edited locally" if rel in old else "exists and was not installed by ailib"
                actions.append(Action("skip", rel, f"{why}; use --force to overwrite"))
                if rel in old:
                    new[rel] = old[rel]  # keep tracking so the edit is still detected next time
                continue
        new[rel] = digest

    for rel in sorted(set(old) - set(desired)):
        dest = target / rel
        if not dest.exists():
            continue
        if _sha(dest.read_bytes()) == old[rel] or force:
            actions.append(Action("delete", rel))
        else:
            actions.append(Action("skip", rel, "no longer in library but edited locally; left in place"))

    if not dry_run:
        for a in actions:
            dest = target / a.rel
            if a.kind in ("create", "update"):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(desired[a.rel])
            elif a.kind == "delete":
                dest.unlink()
                _prune_empty_dirs(dest.parent, target)
        lock_data = {
            "library": {
                "commit": lib.version(),
                "plugins": {p: _plugin_version(lib, p) for p in plugins},
            },
            "plugins": plugins,
            "targets": targets,
            "files": new,
        }
        (target / LOCK_FILE).write_text(json.dumps(lock_data, indent=2) + "\n", encoding="utf-8")

    return Result(actions, warnings, plugins, targets)


def _desired_files(lib: Library, plugins: list[str], targets: list[str]) -> tuple[dict[str, bytes], list[str]]:
    files: dict[str, bytes] = {}
    warnings: list[str] = []
    for pname in plugins:
        plugin = lib.plugin(pname)
        for t in targets:
            layout = LAYOUT[t]
            for skill in plugin.skills:
                for src in sorted(skill.path.rglob("*")):
                    if src.is_file() and not _is_junk(src.relative_to(skill.path)):
                        rel = Path(layout["skills"]) / skill.name / src.relative_to(skill.path)
                        files[rel.as_posix()] = src.read_bytes()
            for agent in plugin.agents:
                rel = f"{layout['agents']}/{agent.name}{layout['agent_suffix']}"
                text = agent.path.read_text(encoding="utf-8")
                if t == "copilot":
                    text, agent_warnings = convert_agent.to_copilot(text)
                    warnings += [f"{agent.name}: {w}" for w in agent_warnings]
                files[rel] = text.encode("utf-8")
    return files, warnings


def _is_junk(rel: Path) -> bool:
    """Build/OS leftovers that must not be installed into target repos."""
    return rel.name == ".DS_Store" or rel.suffix == ".pyc" or "__pycache__" in rel.parts


def _plugin_version(lib: Library, name: str) -> str:
    manifest = lib.plugin(name).path / ".claude-plugin" / "plugin.json"
    return json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prune_empty_dirs(directory: Path, stop: Path) -> None:
    while directory != stop and directory.is_dir() and not any(directory.iterdir()):
        directory.rmdir()
        directory = directory.parent
