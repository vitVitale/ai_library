import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from bdd_fixture import build
from conftest import BDD_SCRIPTS, CONFLUENCE_SCRIPTS
from test_bdd_suite import FEATURE_PAGES


def install(repo: Path, confluence: bool = True) -> Path:
    """The layout `ailib install` creates: both skills side by side under .github/skills/."""
    skills = repo / ".github/skills"
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(BDD_SCRIPTS, skills / "cucumber-suite-analysis/scripts", ignore=ignore)
    if confluence:
        shutil.copytree(CONFLUENCE_SCRIPTS, skills / "confluence-coverage/scripts", ignore=ignore)
    return skills / "cucumber-suite-analysis/scripts/qa_refresh.py"


def refresh(repo: Path, script: Path, *args: str):
    env = {k: v for k, v in os.environ.items() if k != "CONFLUENCE_PAT"}
    return subprocess.run([sys.executable, str(script), "--repo", str(repo), *args],
                          cwd=repo, env=env, capture_output=True, text=True)


def test_full_offline_pipeline(tmp_path):
    repo = build(tmp_path)
    script = install(repo)
    snap = repo / "qa-knowledge/confluence"
    snap.mkdir(parents=True)
    (snap / "index.jsonl").write_text("\n".join(json.dumps({**p, "ancestors": [], "labels": []})
                                                for p in FEATURE_PAGES) + "\n")
    (repo / "confluence-coverage.toml").write_text('[features]\npages = ["1", "2", "3", "4", "5"]\n')

    proc = refresh(repo, script, "--sync")

    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "sync: skipped (set CONFLUENCE_URL and CONFLUENCE_PAT" in out
    assert "e2e: 11 scenarios -> golden" in out
    assert out.strip().splitlines()[-1].startswith(("Next:", "Ready"))
    # coverage_map ran first, and bdd_suite used its curated feature list
    assert (repo / "qa-knowledge/coverage.md").is_file()
    features = json.loads((repo / "qa-knowledge/coverage.json").read_text())["features"]
    assert {f["id"] for f in features} == {"1", "2", "3", "4", "5"}
    impact = (repo / "qa-knowledge/e2e/feature-impact.md").read_text()
    assert "Team retro notes" not in impact and "Card chargebacks (3)" in impact


def test_without_snapshot_or_confluence_skill(tmp_path):
    repo = build(tmp_path / "a")
    proc = refresh(repo, install(repo))
    assert proc.returncode == 0
    assert "feature map: skipped (no Confluence snapshot yet" in proc.stdout

    repo = build(tmp_path / "b")
    proc = refresh(repo, install(repo, confluence=False))
    assert proc.returncode == 0
    assert "feature map: skipped (confluence-coverage not installed)" in proc.stdout
    assert not (repo / "qa-knowledge/e2e/feature-impact.md").exists()
