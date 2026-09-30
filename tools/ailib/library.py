"""Discover plugins, skills and agents in the library (Claude Code marketplace layout)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

MARKETPLACE_FILE = Path(".claude-plugin") / "marketplace.json"
PLUGIN_FILE = Path(".claude-plugin") / "plugin.json"


@dataclass
class Skill:
    name: str  # directory name
    path: Path  # skill directory containing SKILL.md


@dataclass
class Agent:
    name: str  # file stem
    path: Path  # agents/<name>.md


@dataclass
class Plugin:
    name: str
    path: Path
    entry: dict
    skills: list[Skill] = field(default_factory=list)
    agents: list[Agent] = field(default_factory=list)


@dataclass
class Library:
    root: Path
    marketplace: dict
    plugins: list[Plugin]

    def plugin(self, name: str) -> Plugin:
        for p in self.plugins:
            if p.name == name:
                return p
        known = ", ".join(p.name for p in self.plugins)
        raise KeyError(f"unknown plugin '{name}' (known: {known})")

    def version(self) -> str:
        """Git commit of the library checkout, or 'unknown'."""
        try:
            out = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=True,
            )
            return out.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"


def default_root() -> Path:
    """Repo root: walk up from cwd looking for the marketplace file, else the checkout this package lives in."""
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / MARKETPLACE_FILE).is_file():
            return d
    return Path(__file__).resolve().parents[2]


def load(root: Path) -> Library:
    """Load the library. Raises ValueError on problems that prevent discovery (validate reports the rest)."""
    mp_path = root / MARKETPLACE_FILE
    if not mp_path.is_file():
        raise ValueError(f"{mp_path} not found")
    marketplace = json.loads(mp_path.read_text(encoding="utf-8"))
    plugins = []
    for entry in marketplace.get("plugins", []):
        source = entry.get("source")
        if not isinstance(source, str):
            continue  # remote sources are not part of this checkout
        ppath = (root / source).resolve()
        plugin = Plugin(name=entry.get("name", ""), path=ppath, entry=entry)
        skills_dir = ppath / "skills"
        if skills_dir.is_dir():
            plugin.skills = [
                Skill(d.name, d) for d in sorted(skills_dir.iterdir()) if (d / "SKILL.md").is_file()
            ]
        agents_dir = ppath / "agents"
        if agents_dir.is_dir():
            plugin.agents = [Agent(f.stem, f) for f in sorted(agents_dir.glob("*.md"))]
        plugins.append(plugin)
    return Library(root=root, marketplace=marketplace, plugins=plugins)
