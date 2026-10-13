#!/usr/bin/env python3
"""Refresh every offline QA report in one go, then say which agent to run next. No AI involved.

    python qa_refresh.py            # coverage_map.py (if confluence-coverage is installed) + bdd_suite.py
    python qa_refresh.py --sync     # first confluence_sync.py, if CONFLUENCE_PAT is set in your environment

Order matters: coverage_map.py writes qa-knowledge/coverage.json (the curated feature list), which
bdd_suite.py uses to link scenarios to features and to keep one golden path per feature.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKIP_DIRS = {".git", "target", "build", "node_modules", ".gradle", ".idea", ".venv", "venv", "out"}


def find_confluence_scripts(repo: Path, max_depth: int = 6) -> Path | None:
    """confluence-coverage/scripts: next to this skill (ailib install layout) or anywhere shallow in the repo."""
    sibling = HERE.parents[1] / "confluence-coverage" / "scripts"
    if (sibling / "coverage_map.py").is_file():
        return sibling
    for dirpath, dirnames, _ in os.walk(repo):
        depth = len(Path(dirpath).relative_to(repo).parts)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and depth < max_depth]
        candidate = Path(dirpath) / "confluence-coverage" / "scripts"
        if (candidate / "coverage_map.py").is_file():
            return candidate
    return None


def run_script(script: Path, repo: Path, *args: str) -> int:
    return subprocess.run([sys.executable, str(script), *args], cwd=repo).returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="repository root (default: cwd)")
    parser.add_argument("--sync", action="store_true", help="run confluence_sync.py first (needs CONFLUENCE_PAT)")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()

    conf_scripts = find_confluence_scripts(repo)
    status = []
    if args.sync:
        if conf_scripts is None:
            status.append("sync: skipped (confluence-coverage scripts not found)")
        elif not os.environ.get("CONFLUENCE_PAT"):
            status.append("sync: skipped (set CONFLUENCE_URL and CONFLUENCE_PAT in your terminal first)")
        elif run_script(conf_scripts / "confluence_sync.py", repo) != 0:
            return 1
    if conf_scripts is None:
        status.append("feature map: skipped (confluence-coverage not installed)")
    else:
        code = run_script(conf_scripts / "coverage_map.py", repo)
        if code == 2:
            status.append("feature map: skipped (no Confluence snapshot yet: run confluence_sync.py)")
        elif code != 0:
            return code

    sys.path.insert(0, str(HERE))
    import bdd_suite  # noqa: E402  (same folder)

    result, out = bdd_suite.run(repo)
    t = result["tiers"]
    status.append(f"e2e: {len(result['scenarios'])} scenarios -> golden {t.get('golden', 0)}, e2e {t.get('e2e', 0)}, "
                  f"component {t.get('component', 0)}, unit {t.get('unit', 0)}, merge {t.get('merge', 0)}, "
                  f"drop {t.get('drop', 0)} · {out.relative_to(repo) if out.is_relative_to(repo) else out}/summary.md")
    status.append(result["next"])
    print("\n".join(status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
