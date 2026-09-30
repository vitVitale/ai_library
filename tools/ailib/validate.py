"""Check the library against the authoring conventions in docs/authoring.md."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter, tool_map
from .library import MARKETPLACE_FILE, PLUGIN_FILE, Library, load

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_SKILL_LINES = 500


@dataclass
class Issue:
    level: str  # "error" | "warning"
    path: Path
    message: str

    def format(self, root: Path) -> str:
        try:
            rel = self.path.relative_to(root)
        except ValueError:
            rel = self.path
        return f"{self.level.upper():7} {rel}: {self.message}"


def validate(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    mp_path = root / MARKETPLACE_FILE
    try:
        lib = load(root)
    except (ValueError, json.JSONDecodeError) as e:
        return [Issue("error", mp_path, str(e))]

    _check_marketplace(lib, issues)
    skill_owners: dict[str, Path] = {}
    agent_owners: dict[str, Path] = {}
    for plugin in lib.plugins:
        _check_plugin(plugin, issues)
        for skill in plugin.skills:
            _check_skill(skill.path, issues)
            _check_unique("skill", skill.name, skill.path, skill_owners, issues)
        for agent in plugin.agents:
            name = _check_agent(agent.path, issues)
            _check_unique("agent", name or agent.name, agent.path, agent_owners, issues)
        if not plugin.skills and not plugin.agents:
            issues.append(Issue("warning", plugin.path, "plugin has no skills or agents"))
    return issues


def _check_marketplace(lib: Library, issues: list[Issue]) -> None:
    mp = lib.marketplace
    path = lib.root / MARKETPLACE_FILE
    if not _is_name(mp.get("name")):
        issues.append(Issue("error", path, "'name' must be lowercase-hyphenated"))
    if not isinstance(mp.get("owner"), dict) or not mp["owner"].get("name"):
        issues.append(Issue("error", path, "'owner.name' is required"))
    entries = mp.get("plugins")
    if not isinstance(entries, list) or not entries:
        issues.append(Issue("error", path, "'plugins' must be a non-empty list"))
        return
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        name = entry.get("name")
        where = f"plugins[{i}] ({name})"
        if not _is_name(name):
            issues.append(Issue("error", path, f"{where}: 'name' must be lowercase-hyphenated"))
        if name in seen:
            issues.append(Issue("error", path, f"{where}: duplicate plugin name"))
        seen.add(name)
        source = entry.get("source")
        if isinstance(source, str):
            if ".." in Path(source).parts:
                issues.append(Issue("error", path, f"{where}: source must not contain '..'"))
            elif not source.startswith("./"):
                issues.append(Issue("error", path, f"{where}: relative source must start with './'"))
            elif not (lib.root / source).is_dir():
                issues.append(Issue("error", path, f"{where}: source directory does not exist"))
        if not entry.get("description"):
            issues.append(Issue("warning", path, f"{where}: add a 'description' for the /plugin browser"))


def _check_plugin(plugin, issues: list[Issue]) -> None:
    manifest_path = plugin.path / PLUGIN_FILE
    if not manifest_path.is_file():
        issues.append(Issue("error", manifest_path, "missing plugin manifest"))
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        issues.append(Issue("error", manifest_path, f"invalid JSON: {e}"))
        return
    if manifest.get("name") != plugin.name:
        issues.append(Issue("error", manifest_path,
                            f"name '{manifest.get('name')}' must equal marketplace entry name '{plugin.name}'"))
    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        issues.append(Issue("error", manifest_path, "'version' must be semver, e.g. 0.1.0"))
    entry_version = plugin.entry.get("version")
    if entry_version is not None and entry_version != version:
        issues.append(Issue("error", manifest_path,
                            f"version {version} differs from marketplace entry version {entry_version}"))
    extra = [p.name for p in (plugin.path / ".claude-plugin").iterdir() if p.name != "plugin.json"]
    if extra:
        issues.append(Issue("error", manifest_path.parent,
                            f"only plugin.json belongs in .claude-plugin/, found: {', '.join(extra)}"))


def _check_skill(skill_dir: Path, issues: list[Issue]) -> None:
    path = skill_dir / "SKILL.md"
    meta, body = _parse(path, issues)
    if meta is None:
        return
    name = meta.get("name")
    if not _is_name(name) or len(name) > MAX_NAME:
        issues.append(Issue("error", path, f"'name' must be lowercase-hyphenated and <= {MAX_NAME} chars"))
    elif name != skill_dir.name:
        issues.append(Issue("error", path, f"'name' ({name}) must equal the directory name ({skill_dir.name})"))
    _check_description(meta, path, issues)
    if body.count("\n") > MAX_SKILL_LINES:
        issues.append(Issue("warning", path,
                            f"body is over {MAX_SKILL_LINES} lines; move detail into references/"))
    for target in LINK_RE.findall(body):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        if not (skill_dir / target.split("#", 1)[0]).exists():
            issues.append(Issue("error", path, f"broken relative link: {target}"))


def _check_agent(path: Path, issues: list[Issue]) -> str | None:
    meta, _ = _parse(path, issues)
    if meta is None:
        return None
    name = meta.get("name")
    if not _is_name(name):
        issues.append(Issue("error", path, "'name' is required and must be lowercase-hyphenated"))
    elif name != path.stem:
        issues.append(Issue("error", path, f"'name' ({name}) must equal the file name ({path.stem})"))
    _check_description(meta, path, issues)
    _, unmapped = tool_map.to_copilot(tool_map.parse_tools(meta.get("tools")))
    for tool in unmapped:
        if not tool.startswith("mcp__"):
            issues.append(Issue("warning", path, f"tool '{tool}' has no Copilot equivalent and will be dropped"))
    return name


def _check_description(meta: dict, path: Path, issues: list[Issue]) -> None:
    desc = meta.get("description")
    if not isinstance(desc, str) or not desc.strip():
        issues.append(Issue("error", path, "'description' is required"))
    elif len(desc) > MAX_DESCRIPTION:
        issues.append(Issue("error", path, f"'description' is over {MAX_DESCRIPTION} chars"))
    elif "use when" not in desc.lower() and "use this" not in desc.lower():
        issues.append(Issue("warning", path, "'description' should say when to use it (e.g. 'Use when ...')"))


def _check_unique(kind: str, name: str, path: Path, owners: dict[str, Path], issues: list[Issue]) -> None:
    # Installed skills/agents share one directory in the target repo, so names must be library-wide unique.
    if name in owners:
        issues.append(Issue("error", path, f"{kind} name '{name}' is also used by {owners[name]}"))
    else:
        owners[name] = path


def _parse(path: Path, issues: list[Issue]):
    try:
        return frontmatter.parse(path.read_text(encoding="utf-8"))
    except frontmatter.FrontmatterError as e:
        issues.append(Issue("error", path, str(e)))
        return None, ""


def _is_name(value) -> bool:
    return isinstance(value, str) and bool(NAME_RE.match(value))
