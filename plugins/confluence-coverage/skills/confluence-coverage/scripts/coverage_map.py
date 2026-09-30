#!/usr/bin/env python3
"""Map features to test plans / strategies / test cases (Confluence snapshot) and automated tests (repo).

Offline and deterministic: no network, no AI. Reads the snapshot written by confluence_sync.py and
writes to qa-knowledge/ (configurable):
  coverage.md     compact feature x coverage table with gap flags  <- the deliverable
  coverage.json   same data, full detail
  review.md       only the ambiguous feature<->doc pairs for a human/AI to decide
Decisions go into mapping-overrides.txt and are applied on every run:
  <feature_id> <doc_id> yes|no     accept/reject a pair
  feature <page_id>                force a page to be a feature
  doc <page_id> plan|strategy|cases  force a page to be a test doc of that type
  ignore <page_id>                 exclude a page from features and test docs
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from cc_common import DEFAULT_CONFIG, DEFAULT_OUT, jira_keys, load_config, load_index, norm_title, resolve_refs

DOC_TYPES = ("plan", "strategy", "cases")
DEFAULT_KEYWORDS = {
    "strategy": ["test strategy", "testing strategy", "qa strategy", "quality strategy"],
    "plan": ["test plan", "testplan", "testing plan", "qa plan", "test approach", "test scope"],
    "cases": ["test case", "test scenario", "checklist", "test suite", "regression", "smoke test",
              "acceptance test", "uat"],
}
DEFAULT_FEATURE_KEYWORDS = ["requirement", "prd", "specification", "feature", "epic", "user stor"]
DEFAULT_TEST_GLOBS = ["**/src/test/**/*.java", "**/src/test/**/*.kt", "**/*IT.java",
                      "**/tests/**/*.py", "**/test_*.py", "**/*_test.py"]
DEFAULT_EXCLUDE = [".git", "node_modules", "target", "build", ".venv", "venv", ".gradle", ".idea"]
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into", "is", "it", "of", "on",
    "or", "the", "this", "that", "to", "with", "we", "will", "should", "can", "all", "new", "page",
    "draft", "old", "copy", "wip", "tbd", "todo", "notes", "overview", "doc", "docs", "documentation",
}
GENERIC_QA = {
    "test", "tests", "testing", "plan", "plans", "strategy", "case", "cases", "qa", "quality", "assurance",
    "checklist", "scenario", "scenarios", "requirement", "requirements", "feature", "features", "spec",
    "specification", "prd", "epic", "story", "stories", "approach", "scope", "suite", "regression",
    "smoke", "acceptance", "uat", "e2e", "api", "ui", "manual", "automation", "automated",
}
STRUCTURAL = ("manual", "link", "jira", "child")
TEST_COUNT_RE = re.compile(r"@(?:Test|ParameterizedTest|RepeatedTest|TestFactory)\b|^\s*(?:async\s+)?def test_", re.M)
DESCRIPTOR_RES = [
    re.compile(r"\bclass\s+(\w+)"),
    re.compile(r"\bvoid\s+(\w+)\s*\("),
    re.compile(r"\bfun\s+`?([^`(]+)`?\s*\("),
    re.compile(r"\bdef\s+(test_\w+)"),
    re.compile(r"@DisplayName\(\s*\"([^\"]+)\""),
    re.compile(r"@Tag\(\s*\"([^\"]+)\""),
    re.compile(r"@pytest\.mark\.(\w+)"),
]
ALLURE_RE = re.compile(r"(?:@(?:Feature|Story|Epic)\(\s*\"|allure\.(?:feature|story|epic)\(\s*[\"'])([^\"']+)")


# --- text utilities -----------------------------------------------------------------------------
def tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    out = []
    for t in re.split(r"[^A-Za-z0-9]+", text.lower()):
        if len(t) < 2 or t in STOPWORDS:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def core_terms(title: str) -> list[str]:
    """Distinctive words of a title: without stopwords and generic QA vocabulary."""
    generic = {g.rstrip("s") if len(g) > 3 else g for g in GENERIC_QA} | GENERIC_QA
    return [t for t in dict.fromkeys(tokens(title)) if t not in generic]


class Tfidf:
    def __init__(self, docs: dict[str, list[str]]):
        df = Counter(t for toks in docs.values() for t in set(toks))
        n = len(docs) or 1
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.vectors = {k: self._vector(v) for k, v in docs.items()}

    def _vector(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        vec = {t: c * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def cosine(self, a: str, b: str) -> float:
        va, vb = self.vectors[a], self.vectors[b]
        if len(va) > len(vb):
            va, vb = vb, va
        return sum(v * vb.get(t, 0.0) for t, v in va.items())


def match_text(page: dict) -> list[str]:
    title = [t for t in tokens(page["title"]) if t not in GENERIC_QA]
    return title * 3 + tokens(" ".join(page.get("headings") or [])) + tokens(page.get("intro") or "")


# --- overrides ----------------------------------------------------------------------------------
def load_overrides(path: Path) -> dict:
    ov = {"pairs": {}, "feature": set(), "doc": {}, "ignore": set()}
    if not path.is_file():
        return ov
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = raw.split("#", 1)[0].split()
        if not parts:
            continue
        if parts[0] == "ignore" and len(parts) == 2:
            ov["ignore"].add(parts[1])
        elif parts[0] == "feature" and len(parts) == 2:
            ov["feature"].add(parts[1])
        elif parts[0] == "doc" and len(parts) == 3 and parts[2] in DOC_TYPES:
            ov["doc"][parts[1]] = parts[2]
        elif len(parts) == 3 and parts[2].lower() in ("yes", "y", "true", "no", "n", "false"):
            ov["pairs"][(parts[0], parts[1])] = parts[2].lower() in ("yes", "y", "true")
        else:
            print(f"warning: {path.name}:{n}: cannot parse '{raw.strip()}'", file=sys.stderr)
    return ov


# --- selection ----------------------------------------------------------------------------------
def descendants(pages: dict, roots: list[str], depth: int | None) -> list[str]:
    out = []
    for pid, p in pages.items():
        anc = p.get("ancestors") or []
        for i, a in enumerate(anc):
            if a in roots and (depth is None or len(anc) - i <= depth):
                out.append(pid)
                break
    return out


def has_keyword(text: str, words) -> bool:
    text = norm_title(text)
    return any(w.lower() in text for w in words)


def select(pages: dict, cfg: dict, ov: dict, warn) -> tuple[list[str], dict[str, str]]:
    fcfg, tcfg = cfg.get("features", {}), cfg.get("test_docs", {})
    keywords = {**DEFAULT_KEYWORDS, **(tcfg.get("keywords") or {})}

    def refs(section: str, key: str) -> list[str]:
        ids, missing = resolve_refs(cfg.get(section, {}).get(key), pages)
        for m in missing:
            warn(f"[{section}].{key}: '{m}' not found in snapshot")
        return ids

    # test docs
    doc_ids = set(refs("test_docs", "pages")) | set(descendants(pages, refs("test_docs", "folders"), None))
    doc_labels = set(tcfg.get("labels") or ["test-plan", "test-strategy", "test-cases", "testplan", "qa"])
    all_keywords = [w for ws in keywords.values() for w in ws]
    for pid, p in pages.items():
        if doc_labels & set(p.get("labels") or []) or has_keyword(p["title"], all_keywords):
            doc_ids.add(pid)
    doc_ids |= set(ov["doc"])

    # features
    configured = any(fcfg.get(k) for k in ("pages", "folders", "labels"))
    explicit_features = set(refs("features", "pages")) | ov["feature"]
    folders = refs("features", "folders")
    feature_ids = explicit_features | set(descendants(pages, folders, fcfg.get("depth", 1)))
    feature_ids |= {pid for pid, p in pages.items() if set(fcfg.get("labels") or []) & set(p.get("labels") or [])}
    if not configured:
        warn("no [features] configured; guessing features from titles (add pages/folders for better results)")
        words = fcfg.get("keywords") or DEFAULT_FEATURE_KEYWORDS
        feature_ids = {pid for pid, p in pages.items() if has_keyword(p["title"], words)}
    feature_ids |= ov["feature"]
    doc_ids -= explicit_features
    feature_ids -= doc_ids
    feature_ids -= ov["ignore"]
    doc_ids -= ov["ignore"]
    feature_ids = {f for f in feature_ids if f in pages}

    doc_types = {}
    for pid in doc_ids:
        if pid not in pages:
            continue
        p = pages[pid]
        doc_types[pid] = ov["doc"].get(pid) or _doc_type(p, keywords)
    return sorted(feature_ids, key=lambda i: norm_title(pages[i]["title"])), doc_types


def _doc_type(page: dict, keywords: dict) -> str:
    title_words = set(re.findall(r"[a-z]+", page["title"].lower()))
    for kind in ("strategy", "plan"):  # an explicit word in the title beats keyword lists
        if kind in title_words:
            return kind
    sources = [page["title"], " ".join(page.get("labels") or []).replace("-", " "),
               " ".join(page.get("path") or []), " ".join(page.get("headings") or [])]
    for text in sources:
        for kind in ("strategy", "plan", "cases"):
            if has_keyword(text, keywords.get(kind, [])):
                return kind
    return "plan"


# --- code scan ----------------------------------------------------------------------------------
def scan_tests(repo: Path, globs: list[str], exclude: list[str], projects) -> list[dict]:
    files, seen = [], set()
    for pattern in globs:
        for path in repo.glob(pattern):
            rel = path.relative_to(repo)
            if path in seen or not path.is_file() or any(part in exclude for part in rel.parts):
                continue
            seen.add(path)
            text = path.read_text(encoding="utf-8", errors="ignore")
            descriptors = [path.stem] + [m for rx in DESCRIPTOR_RES for m in rx.findall(text)]
            allure = [norm_title(m) for m in ALLURE_RE.findall(text)]
            files.append({
                "path": rel.as_posix(),
                "tests": len(TEST_COUNT_RE.findall(text)),
                "jira": set(jira_keys(text, projects)),
                "terms": set(tokens(" ".join(descriptors + allure))),
                "allure": set(allure),
            })
    return files


def match_code(feature: dict, files: list[dict]) -> list[dict]:
    keys = set(feature.get("jira") or [])
    core = core_terms(feature["title"])
    title_norm = norm_title(feature["title"])
    hits = []
    for f in files:
        reason = None
        if keys & f["jira"]:
            reason = "jira:" + ",".join(sorted(keys & f["jira"])[:2])
        elif title_norm in f["allure"]:
            reason = "allure"
        elif core and len(core) <= 4 and set(core) <= f["terms"]:
            reason = "terms"
        if reason:
            hits.append({"path": f["path"], "tests": f["tests"], "reason": reason})
    rank = {"jira": 0, "allure": 1, "terms": 2}
    hits.sort(key=lambda h: (rank[h["reason"].split(":")[0]], -h["tests"], h["path"]))
    return hits


# --- mapping ------------------------------------------------------------------------------------
def build(pages: dict, cfg: dict, ov: dict, repo: Path, warn=print) -> dict:
    mcfg = cfg.get("match", {})
    strong, weak = float(mcfg.get("strong", 0.55)), float(mcfg.get("weak", 0.30))
    per_feature = int(mcfg.get("max_review_per_feature", 3))
    feature_ids, doc_types = select(pages, cfg, ov, warn)
    tfidf = Tfidf({pid: match_text(pages[pid]) for pid in [*feature_ids, *doc_types]})

    ccfg = cfg.get("code", {})
    out_dir = cfg.get("output", {}).get("dir", DEFAULT_OUT)
    exclude = list(ccfg.get("exclude") or DEFAULT_EXCLUDE) + [Path(out_dir).name]
    files = scan_tests(repo, ccfg.get("test_globs") or DEFAULT_TEST_GLOBS, exclude,
                       cfg.get("confluence", {}).get("jira_projects"))

    features, review, matched_docs = [], [], set()
    for fid in feature_ids:
        f = pages[fid]
        row = {"id": fid, "title": f["title"], "url": f.get("url"), "updated": f.get("updated", ""),
               **{t: [] for t in DOC_TYPES}}
        candidates = []
        for did, dtype in doc_types.items():
            d = pages[did]
            decision = ov["pairs"].get((fid, did))
            if decision is False:
                continue
            reason, score = None, 0.0
            if decision is True:
                reason = "manual"
            elif did in (f.get("links") or []) or fid in (d.get("links") or []):
                reason = "link"
            elif set(f.get("jira") or []) & set(d.get("jira") or []):
                reason = "jira"
            elif fid in (d.get("ancestors") or []):
                reason = "child"
            else:
                score = tfidf.cosine(fid, did)
                core = set(core_terms(f["title"]))
                if core and core <= set(core_terms(d["title"])):
                    score = max(score, strong)
                if score >= strong:
                    reason = "similar"
                elif score >= weak:
                    candidates.append((score, did, dtype))
            if reason:
                row[dtype].append({"id": did, "title": d["title"], "reason": reason, "score": round(score, 2),
                                   "updated": d.get("updated", "")})
                matched_docs.add(did)
        for t in DOC_TYPES:
            row[t].sort(key=lambda m: (m["reason"] not in STRUCTURAL, -m["score"], m["title"]))
        for score, did, dtype in sorted(candidates, reverse=True)[:per_feature]:
            review.append({"feature": fid, "doc": did, "type": dtype, "score": round(score, 2)})

        hits = match_code(f, files)
        row["automation"] = {"tests": sum(h["tests"] for h in hits), "files": hits}
        row["gaps"] = _gaps(row, any(r["feature"] == fid for r in review))
        features.append(row)

    unmatched = sorted((did for did in doc_types if did not in matched_docs),
                       key=lambda i: (doc_types[i], norm_title(pages[i]["title"])))
    return {
        "generated": date.today().isoformat(),
        "stats": {"pages": len(pages), "features": len(features), "test_docs": len(doc_types),
                  "test_files": len(files)},
        "features": features,
        "unmatched_docs": [{"id": d, "title": pages[d]["title"], "type": doc_types[d]} for d in unmatched],
        "review": review,
    }


def _gaps(row: dict, needs_review: bool) -> list[str]:
    gaps = []
    docs = row["plan"] + row["cases"]
    if not docs:
        gaps.append("NO_PLAN")
    elif row["updated"] and max(d["updated"] for d in docs) < row["updated"]:
        gaps.append("STALE")
    if not row["automation"]["files"]:
        gaps.append("NO_AUTO")
    if needs_review:
        gaps.append("REVIEW")
    return gaps


# --- rendering ----------------------------------------------------------------------------------
def _short(title: str, n: int = 32) -> str:
    title = title.replace("|", "/")
    return title if len(title) <= n else title[: n - 1] + "…"


def _docs_cell(docs: list[dict]) -> str:
    if not docs:
        return "—"
    shown = [("~" if d["reason"] == "similar" else "") + f"{_short(d['title'], 28)} ({d['id']})" for d in docs[:3]]
    return ", ".join(shown) + (f" +{len(docs) - 3}" if len(docs) > 3 else "")


def render_coverage(result: dict, warnings: list[str]) -> str:
    feats, s = result["features"], result["stats"]
    count = Counter(g for f in feats for g in f["gaps"])
    with_docs = sum(1 for f in feats if "NO_PLAN" not in f["gaps"])
    with_auto = sum(1 for f in feats if "NO_AUTO" not in f["gaps"])
    lines = [
        "# Test coverage map",
        f"Generated {result['generated']} · pages {s['pages']} · features {s['features']} · "
        f"test docs {s['test_docs']} · test files {s['test_files']}",
        f"With test docs {with_docs}/{len(feats)} · with automation {with_auto}/{len(feats)} · "
        + " · ".join(f"{g} {count[g]}" for g in ("NO_PLAN", "STALE", "NO_AUTO", "REVIEW") if count[g]),
        "Legend: (id) = Confluence page id; ~ = text-similarity match (others: link/jira/child/manual); "
        "automation = tests/files, first file; STALE = feature edited after its test docs.",
    ]
    lines += [f"Warning: {w}" for w in warnings]
    lines += ["", "| Feature | Plan | Strategy | Cases | Automation | Gaps |", "|---|---|---|---|---|---|"]
    for f in feats:
        auto = f["automation"]
        auto_cell = (f"{auto['tests']}/{len(auto['files'])} {Path(auto['files'][0]['path']).name}"
                     if auto["files"] else "—")
        lines.append(f"| {_short(f['title'], 40)} ({f['id']}) | {_docs_cell(f['plan'])} | "
                     f"{_docs_cell(f['strategy'])} | {_docs_cell(f['cases'])} | {auto_cell} | "
                     f"{' '.join(f['gaps'])} |")
    unmatched = result["unmatched_docs"]
    if unmatched:
        lines += ["", f"## Test docs not linked to any feature ({len(unmatched)})"]
        lines += [f"- {d['type']}: {_short(d['title'], 60)} ({d['id']})" for d in unmatched[:40]]
        if len(unmatched) > 40:
            lines.append(f"- … +{len(unmatched) - 40} more in coverage.json")
    return "\n".join(lines) + "\n"


def render_review(result: dict, pages: dict, overrides_name: str) -> str:
    review = result["review"]
    lines = [
        f"# Ambiguous matches to decide ({len(review)})",
        f"Append one line per pair to {overrides_name}: `<feature_id> <doc_id> yes|no`, then re-run coverage_map.py.",
        "Also possible: `ignore <id>` (not a feature/test doc), `feature <id>`, `doc <id> plan|strategy|cases`.",
    ]
    by_feature: dict[str, list] = {}
    for r in review:
        by_feature.setdefault(r["feature"], []).append(r)
    for fid, items in by_feature.items():
        f = pages[fid]
        lines += ["", f"## {fid} {f['title']}", f"F: {_brief(f)}"]
        for r in items:
            d = pages[r["doc"]]
            lines.append(f"- {fid} {r['doc']} ? — {r['type']} {r['score']} \"{d['title']}\" — {_brief(d)}")
    return "\n".join(lines) + "\n"


def _brief(page: dict) -> str:
    heads = "; ".join((page.get("headings") or [])[:5])
    intro = " ".join((page.get("intro") or "").split()[:20])
    return " — ".join(x for x in (heads and f"H: {heads}", intro and f'"{intro}"') if x) or "(no text)"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"TOML config (default {DEFAULT_CONFIG})")
    parser.add_argument("--repo", default=".", help="repository root to scan for tests (default: cwd)")
    parser.add_argument("--out", help=f"output dir (default [output].dir or {DEFAULT_OUT})")
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config))
    out = Path(args.out or cfg.get("output", {}).get("dir") or DEFAULT_OUT)
    cfg.setdefault("output", {})["dir"] = str(out)
    snapshot = Path(cfg.get("confluence", {}).get("out_dir") or out / "confluence")
    pages = load_index(snapshot / "index.jsonl")
    if not pages:
        print(f"no snapshot at {snapshot}/index.jsonl — run confluence_sync.py first", file=sys.stderr)
        return 2

    overrides_path = out / "mapping-overrides.txt"
    warnings: list[str] = []
    result = build(pages, cfg, load_overrides(overrides_path), Path(args.repo), warn=warnings.append)
    out.mkdir(parents=True, exist_ok=True)
    (out / "coverage.md").write_text(render_coverage(result, warnings), encoding="utf-8")
    (out / "coverage.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "review.md").write_text(render_review(result, pages, overrides_path.name), encoding="utf-8")
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    s = result["stats"]
    print(f"{s['features']} features, {s['test_docs']} test docs, {s['test_files']} test files -> "
          f"{out}/coverage.md ({len(result['review'])} pairs to review in review.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
