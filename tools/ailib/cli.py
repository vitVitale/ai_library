"""Command line entry point: ``ailib validate | list | install``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import install as install_mod
from .library import default_root, load
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ailib", description=__doc__)
    parser.add_argument("--root", type=Path, help="library root (default: auto-detect)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="check skills, agents and plugin manifests")
    sub.add_parser("list", help="list plugins with their skills and agents")

    p_install = sub.add_parser("install", help="install/sync plugins into a target repository")
    p_install.add_argument("--target", type=Path, required=True, help="path to the target repository")
    p_install.add_argument("--plugins", help="comma-separated plugin names (default: last install, else all)")
    p_install.add_argument("--for", dest="targets", choices=["copilot", "claude", "both"],
                           help="which product layout to write (default: last install, else copilot)")
    p_install.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    p_install.add_argument("--force", action="store_true", help="overwrite/delete locally edited files")

    args = parser.parse_args(argv)
    root = (args.root or default_root()).resolve()

    if args.command == "validate":
        return _validate(root)
    if args.command == "list":
        return _list(root)
    return _install(root, args)


def _validate(root: Path) -> int:
    issues = validate(root)
    for issue in issues:
        print(issue.format(root))
    errors = sum(1 for i in issues if i.level == "error")
    warnings = len(issues) - errors
    print(f"{'FAILED' if errors else 'OK'}: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def _list(root: Path) -> int:
    lib = load(root)
    for plugin in lib.plugins:
        print(plugin.name)
        for skill in plugin.skills:
            print(f"  skill  {skill.name}")
        for agent in plugin.agents:
            print(f"  agent  {agent.name}")
    return 0


def _install(root: Path, args) -> int:
    target = args.target.expanduser().resolve()
    if not target.is_dir():
        print(f"target {target} is not a directory", file=sys.stderr)
        return 2
    plugins = [p.strip() for p in args.plugins.split(",") if p.strip()] if args.plugins else None
    targets = None if args.targets is None else (["copilot", "claude"] if args.targets == "both" else [args.targets])
    try:
        result = install_mod.install(load(root), target, plugins, targets, args.dry_run, args.force)
    except (KeyError, ValueError) as e:
        print(f"error: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2

    for a in result.actions:
        if a.kind != "unchanged":
            print(f"{a.kind:7} {a.rel}" + (f"  ({a.note})" if a.note else ""))
    for w in result.warnings:
        print(f"warning: {w}")
    counts = {k: sum(1 for a in result.actions if a.kind == k)
              for k in ("create", "update", "delete", "skip", "unchanged")}
    summary = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    prefix = "[dry run] " if args.dry_run else ""
    print(f"{prefix}{', '.join(result.plugins)} -> {target} ({'+'.join(result.targets)}): {summary or 'nothing to do'}")
    return 1 if counts["skip"] else 0


if __name__ == "__main__":
    sys.exit(main())
