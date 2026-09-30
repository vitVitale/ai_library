#!/usr/bin/env python3
"""Analyse a Cucumber E2E suite: risk, coverage, redundancy, recommended test level, golden set.

Offline and deterministic (no AI, no network). Python 3.11+, standard library only.

    python bdd_suite.py                    # uses bdd-suite.toml in the current dir if present
    python bdd_suite.py --features src/test/resources/features

Writes to qa-knowledge/e2e/ (configurable):
  summary.md         one-page overview per folder (payment type)        <- start here
  golden-set.md      coverage-driven minimal E2E set (+ golden-set.rerun.txt for cucumber.features=@file)
  moves.md           what to move to component/unit level, merge or drop, with reasons
  review-NN.md       small batches of uncertain / high-risk calls for a human or AI to decide
  scenarios.csv      one row per scenario (for Excel)
  analysis.json      everything, full detail
Decisions (applied on every run) go in qa-knowledge/e2e/decisions.txt, one per line:
  <scenario_id> golden|e2e|component|unit|drop|merge:<scenario_id>   # optional reason
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("Python 3.11+ is required (uses tomllib).")
import tomllib  # noqa: E402

from bdd_gherkin import parse  # noqa: E402
from bdd_glue import StepMatcher, scan  # noqa: E402

DEFAULT_CONFIG = "bdd-suite.toml"
TIERS = ("golden", "e2e", "component", "unit", "merge", "drop")
EXCLUDE_DIRS = {".git", "target", "build", "node_modules", ".gradle", ".idea", ".venv", "out"}

# Payment-engine vocabulary. Each value is a list of regex fragments matched case-insensitively
# at a word start against scenario name + steps + tags + example values. Override in [dimensions].
DEFAULT_DIMENSIONS = {
    "outcome": {
        "accepted": ["accept", "settl", "booked", "complet", "credited", "executed", "success", "ACSC", "ACCC", "ACCP", "ACSP"],
        "rejected": ["reject", "RJCT", "declin", "refus"],
        "returned": ["return", r"pacs\.004"],
        "recalled": ["recall", r"camt\.056", r"camt\.029", "cancellation request"],
        "refunded": ["refund"],
        "reversed": ["revers", r"pacs\.007"],
        "timeout": ["time-?out", "times? out", "timed out", "expir", "no response", "does not respond"],
        "pending": ["pending", "PDNG", "on hold", "parked", "queued", "repair"],
        "duplicate": ["duplicat", "idempot", "resubmi", "replay"],
    },
    "check": {
        "validation": ["invalid", "missing", "mandatory", "format", "validat", "malformed", "incorrect", "not allowed", "schema", "length"],
        "limits": ["limit", "threshold", "max amount", "maximum", "exceed"],
        "cutoff": ["cut-?off", "cut off", "business day", "holiday", "weekend", "value date", "execution date", "calendar"],
        "screening": ["sanction", "screening", "aml", "fraud", "blacklist", "embargo"],
        "fx": ["currency", "fx", "exchange rate", "conversion"],
        "fees": ["fee", "charge", "commission"],
        "funds": ["insufficient", "balance", "funds", "overdraft"],
        "mandate": ["mandate", "amendment", "sequence type", "FRST", "RCUR", "FNAL", "OOFF", "pre-?notification"],
    },
    "channel": {
        "api": ["api", "rest", "endpoint", "http", "request"],
        "file": ["file", "batch", "bulk", "sftp", r"pain\.001", r"pain\.008"],
        "message": ["kafka", "queue", "mq", "topic", "message"],
    },
}
# Which systems a step touches, detected in step-definition bodies and step text.
DEFAULT_LAYERS = {
    "rest": [r"RestTemplate", r"WebClient", r"RestAssured", r"MockMvc", r"\.exchange\(", r"Feign", r"HttpClient", r"\w+Client\."],
    "db": [r"JdbcTemplate", r"Repository", r"EntityManager", r"\bjdbc", r"\bSELECT\b", r"DataSource"],
    "mq": [r"KafkaTemplate", r"\bkafka", r"JmsTemplate", r"rabbit", r"\btopic\b", r"\bqueue\b", r"Consumer", r"Producer"],
    "csm": [r"WireMock", r"stubFor", r"MockServer", r"simulator", r"\bCSM\b", r"\bTIPS\b", r"\bRT1\b", r"STEP2", r"\bEBA\b"],
    "file": [r"\bsftp", r"Files\.", r"FileSystem", r"\bfile\b"],
    "async": [r"Awaitility", r"await\(", r"Thread\.sleep", r"\bwait(?:s|ing)? (?:for|until)\b"],
}
EXTERNAL_LAYERS = {"csm", "mq", "file"}
MONEY_OUTCOMES = {"accepted", "returned", "recalled", "refunded", "reversed"}
RISK_WEIGHTS = {
    "outcome:accepted": 10, "outcome:rejected": 5, "outcome:returned": 15, "outcome:recalled": 15,
    "outcome:refunded": 12, "outcome:reversed": 15, "outcome:timeout": 15, "outcome:duplicate": 15,
    "outcome:pending": 8, "check:screening": 15, "check:limits": 10, "check:cutoff": 10, "check:fx": 10,
    "check:fees": 5, "check:funds": 8, "check:mandate": 10,
}
DEFAULT_RISK_TAGS = {"critical": 30, "p1": 25, "blocker": 30, "smoke": 10, "sanity": 10}
DISABLED_TAGS = {"@ignore", "@ignored", "@wip", "@disabled", "@skip", "@manual"}
STOP = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "is", "are", "be", "i", "it",
        "should", "has", "have", "then", "when", "given", "that", "this", "as", "by", "from", "at", "not"}


# --- config ---------------------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def find_features_dir(repo: Path) -> Path:
    dirs = {p.parent for p in _walk(repo, ".feature")}
    if not dirs:
        raise SystemExit(f"no .feature files under {repo}")
    return Path(os.path.commonpath([str(d) for d in dirs]))


def _walk(root: Path, suffix: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if name.endswith(suffix):
                yield Path(dirpath) / name


# --- model ----------------------------------------------------------------------------------------
@dataclass
class Sc:
    id: str
    path: str
    line: int
    group: str
    feature: str
    name: str
    tags: list[str]
    steps: list[tuple[str, str]]  # (kind, text) incl. background, outline placeholders filled from row 1
    skeleton: tuple[str, ...]
    rows: int
    layers: set[str] = field(default_factory=set)
    atoms: set[str] = field(default_factory=set)
    unmatched_steps: int = 0
    risk: int = 0
    why: list[str] = field(default_factory=list)
    tier: str = "e2e"
    confidence: str = "high"
    reason: str = ""
    related: str = ""  # representative / superset scenario id
    decided: bool = False
    req: str = ""  # best matching Confluence page id
    disabled: bool = False


SKELETON_SUBS = [
    (re.compile(r"\"[^\"]*\"|'[^']*'"), "{s}"),
    (re.compile(r"<[^>]+>"), "{p}"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"), "{iban}"),
    # numbers, but not inside identifiers like B2B, pacs.004, E001
    (re.compile(r"(?<![A-Za-z0-9.])-?\d+(?:[.,:/-]\d+)*(?![A-Za-z0-9])"), "{n}"),
]


def skeleton(text: str) -> str:
    for rx, rep in SKELETON_SUBS:
        text = rx.sub(rep, text)
    return " ".join(text.lower().split())


def scenario_id(path: str, rule: str, name: str, taken: set[str]) -> str:
    base = "S" + hashlib.sha1(f"{path}::{rule}::{name}".encode()).hexdigest()[:6]
    sid, n = base, 2
    while sid in taken:
        sid, n = f"{base}-{n}", n + 1
    taken.add(sid)
    return sid


def load_suite(repo: Path, cfg: dict) -> tuple[list[Sc], dict]:
    scfg = cfg.get("suite", {})
    features_dir = (repo / scfg["features_dir"]) if scfg.get("features_dir") else find_features_dir(repo)
    depth = int(scfg.get("group_depth", 1))
    layer_patterns = {**DEFAULT_LAYERS, **cfg.get("layers", {})}
    glue_files = sorted({p for g in scfg.get("glue_globs", ["**/src/test/java/**/*.java", "**/src/test/kotlin/**/*.kt"])
                         for p in repo.glob(g) if not EXCLUDE_DIRS & set(p.relative_to(repo).parts)})
    defs = scan(glue_files, repo, layer_patterns)
    matcher = StepMatcher(defs)
    text_layers = {n: re.compile("|".join(p), re.I) for n, p in layer_patterns.items() if p}
    dims = cfg.get("dimensions") or DEFAULT_DIMENSIONS
    dim_rx = {f"{d}:{v}": re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(words) + ")", re.I)
              for d, values in dims.items() for v, words in values.items()}
    skip_tags = set(scfg.get("exclude_tags", []))

    scenarios, taken = [], set()
    feature_files = sorted(_walk(features_dir, ".feature"))
    for fpath in feature_files:
        feat = parse(fpath)
        rel = fpath.relative_to(repo).as_posix()
        parts = fpath.relative_to(features_dir).parts[:-1]
        group = "/".join(parts[:depth]) or "(root)"
        for s in feat.scenarios:
            if skip_tags & set(s.tags):
                continue
            row = s.first_row()
            steps = []
            for st in s.background + s.steps:
                text = re.sub(r"<([^>]+)>", lambda m: row.get(m.group(1), m.group(0)), st.text)
                if st.table_header:
                    text += " [" + ",".join(st.table_header) + "]"
                steps.append((st.kind, text))
            sc = Sc(
                id=scenario_id(rel, s.rule, s.name, taken), path=rel, line=s.line, group=group,
                feature=feat.name, name=s.name, tags=s.tags, steps=steps,
                skeleton=tuple(f"{k[0]} {skeleton(t)}" for k, t in steps), rows=max(1, s.example_rows),
                disabled=bool(DISABLED_TAGS & {t.lower() for t in s.tags}),
            )
            for kind, text in steps:
                d = matcher.match(text)
                if d is None:
                    sc.unmatched_steps += 1
                else:
                    sc.layers |= d.layers
                sc.layers |= {n for n, rx in text_layers.items() if rx.search(text)}
            blob = " ".join([s.name, *(t for _, t in steps), *s.tags,
                             *(" ".join(r) for e in s.examples for r in e.rows)])
            sc.atoms = {a for a, rx in dim_rx.items() if rx.search(blob)}
            scenarios.append(sc)
    meta = {"features_dir": features_dir.relative_to(repo).as_posix() or ".", "feature_files": len(feature_files),
            "step_defs": len(defs), "glue_files": len(glue_files)}
    return scenarios, meta


# --- analysis -------------------------------------------------------------------------------------
def score_risk(sc: Sc, counts: Counter, cfg: dict) -> None:
    rcfg = cfg.get("risk", {})
    tag_weights = {k.lower(): v for k, v in {**DEFAULT_RISK_TAGS, **rcfg.get("tags", {})}.items()}
    score, why = 0, []
    for atom in sorted(sc.atoms):
        w = RISK_WEIGHTS.get(atom, 0)
        if w:
            score += w
            why.append(atom.split(":")[1])
    ext = sc.layers & EXTERNAL_LAYERS
    score += 8 * len(ext) + 3 * len(sc.layers & {"rest", "db"})
    why += [f"+{x}" for x in sorted(ext)]
    for t in sc.tags:
        w = tag_weights.get(t.lstrip("@").lower())
        if w:
            score += w
            why.append(t)
    rare = [a for a in sc.atoms if counts[(sc.group, a)] <= 2]
    if rare:
        score += min(20, 10 * len(rare))
        why.append("unique:" + ",".join(sorted(a.split(":")[1] for a in rare))[:40])
    sc.risk, sc.why = min(score, 100), why


def risk_level(risk: int, cfg: dict) -> str:
    rcfg = cfg.get("risk", {})
    return "H" if risk >= rcfg.get("high", 45) else "M" if risk >= rcfg.get("medium", 25) else "L"


def find_redundancy(scs: list[Sc], cfg: dict) -> dict:
    rcfg = cfg.get("redundancy", {})
    near = float(rcfg.get("near_duplicate", 0.85))
    stats = {"exact_groups": 0, "same_flow_groups": 0, "near_clusters": 0, "subsumed": 0, "big_outlines": 0}
    live = [s for s in scs if not s.disabled]

    def best(group):
        return max(group, key=lambda s: (s.risk, s.rows, -len(s.steps), s.id))

    # identical text -> drop; identical skeleton, different data -> merge (Scenario Outline / lower level)
    def outcomes(s):
        return frozenset(a for a in s.atoms if a.startswith("outcome:"))

    by_text, by_skel = defaultdict(list), defaultdict(list)
    for s in live:
        by_text[(s.group, tuple(t for _, t in s.steps))].append(s)
        # same skeleton but a different outcome (e.g. ACSC vs RJCT) is a different behaviour, not a data variant
        by_skel[(s.group, s.skeleton, outcomes(s))].append(s)
    for group in by_text.values():
        if len(group) > 1:
            stats["exact_groups"] += 1
            rep = best(group)
            for s in group:
                if s is not rep:
                    s.tier, s.related, s.reason = "drop", rep.id, "exact duplicate steps"
    for group in by_skel.values():
        group = [s for s in group if s.tier != "drop"]
        if len(group) > 1:
            stats["same_flow_groups"] += 1
            rep = best(group)
            for s in group:
                if s is not rep:
                    s.tier, s.related, s.reason = "merge", rep.id, "same flow, different data -> Outline row or lower level"

    # near duplicates (step skeletons, same outcomes) and subsumption (exact step text incl. data) per folder
    by_group = defaultdict(list)
    for s in live:
        if s.tier not in ("drop", "merge"):
            by_group[s.group].append(s)
    for members in by_group.values():
        sets = {s.id: set(s.skeleton) for s in members}
        texts = {s.id: {f"{k[0]} {' '.join(t.lower().split())}" for k, t in s.steps} for s in members}
        parent = {s.id: s.id for s in members}

        def root(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i, a in enumerate(members):
            sa = sets[a.id]
            for b in members[i + 1:]:
                sb = sets[b.id]
                inter = len(sa & sb)
                if not inter:
                    continue
                ta, tb = texts[a.id], texts[b.id]
                if inter / len(sa | sb) >= near and outcomes(a) == outcomes(b):
                    parent[root(a.id)] = root(b.id)
                elif ta < tb and a.tier == "e2e":
                    a.tier, a.related, a.reason, a.confidence = "drop", b.id, "steps are a subset of another scenario", "medium"
                    stats["subsumed"] += 1
                elif tb < ta and b.tier == "e2e":
                    b.tier, b.related, b.reason, b.confidence = "drop", a.id, "steps are a subset of another scenario", "medium"
                    stats["subsumed"] += 1
        clusters = defaultdict(list)
        for s in members:
            clusters[root(s.id)].append(s)
        for cl in clusters.values():
            if len(cl) > 1:
                stats["near_clusters"] += 1
                rep = best(cl)
                for s in cl:
                    if s is not rep and s.tier == "e2e":
                        s.tier, s.related, s.confidence = "merge", rep.id, "medium"
                        s.reason = "near-duplicate flow (≥{:.0%} same steps)".format(near)

    big = int(rcfg.get("outline_rows_to_push_down", 5))
    for s in live:
        if s.rows > big:
            stats["big_outlines"] += 1
            s.why.append(f"{s.rows} example rows")
    return stats


def recommend_level(s: Sc) -> None:
    if s.tier != "e2e":
        return
    outcomes = {a.split(":")[1] for a in s.atoms if a.startswith("outcome:")}
    checks = {a.split(":")[1] for a in s.atoms if a.startswith("check:")}
    ext = s.layers & EXTERNAL_LAYERS
    if "validation" in checks and not (outcomes & MONEY_OUTCOMES) and not ext:
        s.tier, s.reason = "unit", "input validation without settlement or external systems"
        s.confidence = "high" if s.layers <= {"rest"} else "medium"
    elif not ext and not (outcomes & MONEY_OUTCOMES - {"accepted"}):
        s.tier, s.reason = "component", "only engine API/DB involved: Spring Boot test with stubs"
        s.confidence = "medium" if outcomes or checks - {"validation"} else "high"
    else:
        s.reason = "crosses " + (", ".join(sorted(ext)) or "engine") + " with " + (", ".join(sorted(outcomes)) or "no clear outcome")
        s.confidence = "high" if ext and outcomes else "medium"


def apply_decisions(scs: list[Sc], decisions: dict[str, str]) -> None:
    by_id = {s.id: s for s in scs}
    for sid, value in decisions.items():
        s = by_id.get(sid)
        if s is None:
            continue
        tier, _, related = value.partition(":")
        s.tier, s.related, s.decided, s.confidence = tier, related, True, "high"
        s.reason = "decided: " + (decisions.get(sid + "#") or tier)


def load_decisions(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        body, _, note = raw.partition("#")
        parts = body.split()
        if not parts:
            continue
        if len(parts) == 2 and (parts[1] in TIERS or parts[1].startswith("merge:")):
            out[parts[0]] = parts[1]
            if note.strip():
                out[parts[0] + "#"] = note.strip()
        else:
            print(f"warning: {path.name}:{n}: cannot parse '{raw.strip()}'", file=sys.stderr)
    return out


def golden_set(scs: list[Sc]) -> tuple[list[Sc], list[str], list[str]]:
    """Greedy set cover of (folder, dimension value) atoms using E2E candidates.

    Returns (golden scenarios, promoted ids, atoms covered only by moved tests)."""
    live = [s for s in scs if not s.disabled]
    universe = {(s.group, a) for s in live for a in s.atoms}
    golden = [s for s in live if s.tier == "golden"]
    covered = {(s.group, a) for s in golden for a in s.atoms}
    candidates = [s for s in live if s.tier == "e2e"]
    while True:
        best, gain = None, 0
        for s in candidates:
            g = sum(2 if a.startswith("outcome:") else 1 for a in s.atoms if (s.group, a) not in covered)
            if g > gain or (g == gain and g and (s.risk, -len(s.steps)) > (best.risk, -len(best.steps))):
                best, gain = s, g
        if not best:
            break
        best.tier = "golden"
        golden.append(best)
        candidates.remove(best)
        covered |= {(best.group, a) for a in best.atoms}
    # every business outcome of every payment type keeps at least one end-to-end test
    promoted = []
    for group, atom in sorted(universe - covered):
        if not atom.startswith("outcome:"):
            continue
        pool = [s for s in live if s.group == group and atom in s.atoms and s.tier in ("component", "merge")]
        if pool:
            s = max(pool, key=lambda x: (x.risk, -len(x.steps)))
            s.tier, s.reason = "golden", f"promoted: only test of {group} {atom}"
            golden.append(s)
            promoted.append(s.id)
            covered |= {(s.group, a) for a in s.atoms}
    lost = sorted(f"{g} {a}" for g, a in universe - covered if a != "channel:api")  # API is everyone's entry point
    return golden, promoted, lost


# --- Confluence -----------------------------------------------------------------------------------
def _tokens(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 2 and t not in STOP and not t.isdigit()]


def link_confluence(scs: list[Sc], cfg: dict, repo: Path) -> dict:
    ccfg = cfg.get("confluence", {})
    index = repo / ccfg.get("snapshot", "qa-knowledge/confluence") / "index.jsonl"
    if not index.is_file():
        return {"pages": 0, "uncovered": []}
    pages = {}
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.strip():
            p = json.loads(line)
            pages[p["id"]] = p
    wanted = _resolve(ccfg.get("pages") or [], pages)
    if wanted:
        pages = {pid: p for pid, p in pages.items() if pid in wanted or wanted & set(p.get("ancestors") or [])}
    docs = {f"P{pid}": _tokens(" ".join([p["title"]] * 3 + (p.get("path") or []) + (p.get("headings") or [])
                                        + [p.get("intro") or ""])) for pid, p in pages.items()}
    docs.update({s.id: _tokens(" ".join([s.group, s.feature, s.name] + [t for _, t in s.steps])) for s in scs})
    df = Counter(t for toks in docs.values() for t in set(toks))
    n = len(docs)
    vec = {}
    for k, toks in docs.items():
        tf = Counter(toks)
        v = {t: c * (math.log((1 + n) / (1 + df[t])) + 1) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        vec[k] = {t: x / norm for t, x in v.items()}
    min_score = float(ccfg.get("min_score", 0.2))
    postings = defaultdict(list)  # token -> [(page id, weight)]: avoids scoring every scenario x page pair
    for pid in pages:
        for t, x in vec[f"P{pid}"].items():
            postings[t].append((pid, x))
    linked = Counter()
    for s in scs:
        scores = Counter()
        for t, x in vec[s.id].items():
            for pid, y in postings.get(t, ()):
                scores[pid] += x * y
        if scores:
            best, score = max(scores.items(), key=lambda kv: (kv[1], kv[0]))
            if score >= min_score:
                s.req = best
                linked[best] += 1
    uncovered = [{"id": pid, "title": p["title"]} for pid, p in sorted(pages.items(), key=lambda kv: kv[1]["title"])
                 if not linked[pid] and (p.get("words") or 0) >= 50]
    return {"pages": len(pages), "linked": dict(linked), "uncovered": uncovered}


def _resolve(refs, pages) -> set[str]:
    by_title = {" ".join(p["title"].casefold().split()): pid for pid, p in pages.items()}
    out = set()
    for ref in refs:
        s = str(ref).strip()
        m = re.search(r"(?:pageId=|/pages/)(\d+)", s)
        pid = s if s.isdigit() else m.group(1) if m else by_title.get(" ".join(s.casefold().split()))
        if pid:
            out.add(pid)
    return out


# --- review ---------------------------------------------------------------------------------------
def select_review(scs: list[Sc], cfg: dict) -> list[Sc]:
    rcfg = cfg.get("review", {})
    limit = int(rcfg.get("limit", 60))

    def priority(s):
        if s.decided or s.disabled:
            return None
        if risk_level(s.risk, cfg) == "H" and s.tier in ("unit", "component", "drop", "merge"):
            return 0
        if s.confidence == "medium":
            return 1 if s.tier in ("drop", "unit") else 2
        return None

    picked = [(p, s) for s in scs if (p := priority(s)) is not None]
    picked.sort(key=lambda ps: (ps[0], -ps[1].risk, ps[1].group, ps[1].path, ps[1].line))
    return [s for _, s in picked[:limit]]


def compact_steps(s: Sc, limit: int = 220) -> str:
    text = "; ".join(f"{k[0]}: {skeleton(t)}" for k, t in s.steps)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_review(batch: list[Sc], n: int, total: int, cfg: dict) -> str:
    lines = [
        f"# Review batch {n}/{total} ({len(batch)} items)",
        "For each item append one line to decisions.txt: `<id> golden|e2e|component|unit|drop|merge:<id>  # reason`.",
        "`?` marks the script's suggestion. Rules: references/test-levels.md. Keep money-moving flows across external "
        "systems in E2E; push pure validation/data variations down.",
    ]
    group = None
    for s in batch:
        if s.group != group:
            group = s.group
            lines += ["", f"## {group}"]
        rel = f" ~{s.related}" if s.related else ""
        req = f" | req {s.req}" if s.req else ""
        lines.append(
            f"- {s.id} {s.tier}?{rel} risk {risk_level(s.risk, cfg)}{s.risk} [{','.join(s.why[:6])}] "
            f"{s.path}:{s.line} \"{s.name}\" | layers {','.join(sorted(s.layers)) or '-'}{req} | why: {s.reason}\n"
            f"  {compact_steps(s)}"
        )
    return "\n".join(lines) + "\n"


# --- reports --------------------------------------------------------------------------------------
def render_summary(scs, meta, red, gold, promoted, lost, conf, review_files, cfg) -> str:
    live = [s for s in scs if not s.disabled]
    groups = sorted({s.group for s in live})
    tc = {g: Counter(s.tier for s in live if s.group == g) for g in groups}
    total = Counter(s.tier for s in live)
    execs = sum(s.rows for s in live)
    no_dim = sum(1 for s in live if not s.atoms)
    steps_total = sum(len(s.steps) for s in live) or 1
    unmatched = sum(s.unmatched_steps for s in live)
    lines = [
        "# E2E suite analysis",
        f"Generated {date.today().isoformat()} · {meta['feature_files']} feature files in `{meta['features_dir']}` · "
        f"{len(live)} scenarios ({execs} executions incl. outline rows) · {len(scs) - len(live)} disabled · "
        f"{meta['step_defs']} step defs, {unmatched * 100 // steps_total}% steps unmatched",
        "",
        f"**Proposal:** golden E2E **{total['golden']}** (every build) · extended E2E {total['e2e']} (nightly or retire) · "
        f"move to component {total['component']} · to unit {total['unit']} · merge {total['merge']} · drop {total['drop']}",
        "",
        "| Folder | Total | Golden | E2E ext | Component | Unit | Merge | Drop | High risk |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for g in groups:
        c = tc[g]
        high = sum(1 for s in live if s.group == g and risk_level(s.risk, cfg) == "H")
        lines.append(f"| {g} | {sum(c.values())} | {c['golden']} | {c['e2e']} | {c['component']} | {c['unit']} | "
                     f"{c['merge']} | {c['drop']} | {high} |")
    outcomes = [v for v in (cfg.get("dimensions") or DEFAULT_DIMENSIONS).get("outcome", {})]
    lines += ["", "## Outcome coverage (scenarios per folder; · = none)",
              "| Folder | " + " | ".join(outcomes) + " |", "|---|" + "---|" * len(outcomes)]
    for g in groups:
        cells = [str(sum(1 for s in live if s.group == g and f"outcome:{o}" in s.atoms) or "·") for o in outcomes]
        lines.append(f"| {g} | " + " | ".join(cells) + " |")
    lines += [
        "", "## Redundancy",
        f"- {red['exact_groups']} groups of exact duplicates, {red['same_flow_groups']} groups with the same flow and "
        f"different data, {red['near_clusters']} near-duplicate clusters, {red['subsumed']} scenarios subsumed by others",
        f"- {red['big_outlines']} Scenario Outlines with many example rows (push most rows to lower levels)",
        "", "## Golden set",
        f"- {len(gold)} scenarios cover every folder × dimension value present in E2E candidates"
        + (f"; {len(promoted)} promoted so every business outcome keeps one E2E test" if promoted else ""),
    ]
    if lost:
        lines.append(f"- Covered only by tests recommended to move down ({len(lost)}): make sure lower-level tests "
                     f"exist before deleting: " + "; ".join(lost[:25]) + (" …" if len(lost) > 25 else ""))
    lines += ["", "## Signal quality",
              f"- {no_dim} scenarios ({no_dim * 100 // max(1, len(live))}%) matched no dimension: tune [dimensions] "
              f"in bdd-suite.toml if this is high",
              f"- {sum(1 for s in live if s.layers & EXTERNAL_LAYERS) * 100 // max(1, len(live))}% of scenarios touch an "
              f"external system (CSM/MQ/file): if this looks too low, add your client/stub class names to [layers]"]
    if conf.get("pages"):
        unc = conf["uncovered"]
        lines += ["", "## Confluence",
                  f"- {conf['pages']} pages, {len(conf['linked'])} linked to at least one scenario; "
                  f"{len(unc)} substantial pages with no scenario (check they're covered at some level):"]
        lines += [f"  - {p['title']} ({p['id']})" for p in unc[:25]]
        if len(unc) > 25:
            lines.append(f"  - … +{len(unc) - 25} more in analysis.json")
    decided = sum(1 for s in scs if s.decided)
    lines += ["", "## Next",
              f"- {sum(len(b) for b in review_files)} items to review in "
              + (", ".join(f"review-{i:02d}.md" for i in range(1, len(review_files) + 1)) or "(none)")
              + f" · {decided} decisions applied",
              "- Details: golden-set.md, moves.md, scenarios.csv"]
    return "\n".join(lines) + "\n"


def render_golden(gold: list[Sc], cfg) -> str:
    lines = ["# Golden E2E set", "Run on every build. `covers` = folder dimension values this scenario is the chosen test for.",
             "Also written as golden-set.rerun.txt (use: -Dcucumber.features=@qa-knowledge/e2e/golden-set.rerun.txt)."]
    for g in sorted({s.group for s in gold}):
        lines += ["", f"## {g}", "| id | scenario | covers | risk |", "|---|---|---|---|"]
        for s in sorted((s for s in gold if s.group == g), key=lambda s: (-s.risk, s.path)):
            covers = ",".join(sorted(a.split(":")[1] for a in s.atoms))
            lines.append(f"| {s.id} | {s.name[:70].replace('|', '/')} ({Path(s.path).name}:{s.line}) | {covers} | "
                         f"{risk_level(s.risk, cfg)}{s.risk} |")
    return "\n".join(lines) + "\n"


def render_moves(scs: list[Sc], cfg) -> str:
    titles = {"component": "Move to component/integration level (Spring Boot + stubs)",
              "unit": "Move to unit level (validators, mappers, rules)",
              "merge": "Merge into another scenario (Outline row) or cover the data variation lower",
              "drop": "Drop (duplicate or fully covered by another scenario)",
              "e2e": "Extended E2E (keep, but not needed on every build)"}
    lines = ["# Recommended moves", "Each line: id · file:line · scenario · reason (→ related scenario)."]
    for tier in ("drop", "merge", "unit", "component", "e2e"):
        items = [s for s in scs if s.tier == tier and not s.disabled]
        if not items:
            continue
        lines += ["", f"## {titles[tier]} ({len(items)})"]
        for g in sorted({s.group for s in items}):
            lines.append(f"### {g}")
            for s in sorted((s for s in items if s.group == g), key=lambda s: (s.path, s.line)):
                rel = f" → {s.related}" if s.related else ""
                lines.append(f"- {s.id} · {s.path}:{s.line} · {s.name[:80]} · {s.reason}{rel}"
                             f"{' · risk ' + risk_level(s.risk, cfg) if risk_level(s.risk, cfg) == 'H' else ''}")
    disabled = [s for s in scs if s.disabled]
    if disabled:
        lines += ["", f"## Disabled/WIP scenarios ({len(disabled)}): fix or delete"]
        lines += [f"- {s.id} · {s.path}:{s.line} · {s.name[:80]}" for s in disabled]
    return "\n".join(lines) + "\n"


def write_csv(path: Path, scs: list[Sc], cfg) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "folder", "file", "line", "feature", "scenario", "tier", "risk", "risk_level", "reason",
                    "related", "layers", "dimensions", "rows", "steps", "tags", "confluence_page", "decided"])
        for s in scs:
            w.writerow([s.id, s.group, s.path, s.line, s.feature, s.name, "disabled" if s.disabled else s.tier,
                        s.risk, risk_level(s.risk, cfg), s.reason, s.related, " ".join(sorted(s.layers)),
                        " ".join(sorted(s.atoms)), s.rows, len(s.steps), " ".join(s.tags), s.req, s.decided])


def analyse(repo: Path, cfg: dict, out: Path) -> dict:
    scs, meta = load_suite(repo, cfg)
    counts = Counter((s.group, a) for s in scs if not s.disabled for a in s.atoms)
    for s in scs:
        score_risk(s, counts, cfg)
    red = find_redundancy(scs, cfg)
    for s in scs:
        recommend_level(s)
    decisions = load_decisions(out / "decisions.txt")
    apply_decisions(scs, decisions)
    gold, promoted, lost = golden_set(scs)
    conf = link_confluence(scs, cfg, repo)

    review = select_review(scs, cfg)
    size = int(cfg.get("review", {}).get("batch_size", 20))
    batches = [review[i:i + size] for i in range(0, len(review), size)]

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("review-*.md"):
        old.unlink()
    for i, batch in enumerate(batches, 1):
        (out / f"review-{i:02d}.md").write_text(render_review(batch, i, len(batches), cfg), encoding="utf-8")
    (out / "summary.md").write_text(render_summary(scs, meta, red, gold, promoted, lost, conf, batches, cfg), encoding="utf-8")
    (out / "golden-set.md").write_text(render_golden(gold, cfg), encoding="utf-8")
    (out / "golden-set.rerun.txt").write_text(
        "\n".join(f"{s.path}:{s.line}" for s in sorted(gold, key=lambda s: (s.path, s.line))) + "\n", encoding="utf-8")
    (out / "moves.md").write_text(render_moves(scs, cfg), encoding="utf-8")
    write_csv(out / "scenarios.csv", scs, cfg)
    result = {
        "meta": meta, "redundancy": red, "promoted": promoted, "uncovered_atoms": lost, "confluence": conf,
        "tiers": dict(Counter("disabled" if s.disabled else s.tier for s in scs)),
        "scenarios": [{
            "id": s.id, "path": s.path, "line": s.line, "group": s.group, "feature": s.feature, "name": s.name,
            "tags": s.tags, "tier": s.tier, "risk": s.risk, "why": s.why, "confidence": s.confidence,
            "reason": s.reason, "related": s.related, "layers": sorted(s.layers), "atoms": sorted(s.atoms),
            "rows": s.rows, "steps": len(s.steps), "unmatched_steps": s.unmatched_steps, "req": s.req,
            "disabled": s.disabled, "decided": s.decided,
        } for s in scs],
    }
    (out / "analysis.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"TOML config (default {DEFAULT_CONFIG})")
    parser.add_argument("--repo", default=".", help="E2E repository root (default: cwd)")
    parser.add_argument("--features", help="features directory relative to --repo (default: auto-detect)")
    parser.add_argument("--out", help="output dir (default [output].dir or qa-knowledge/e2e)")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    cfg = load_config(Path(args.config) if Path(args.config).is_absolute() else repo / args.config)
    if args.features:
        cfg.setdefault("suite", {})["features_dir"] = args.features
    out = Path(args.out) if args.out else repo / cfg.get("output", {}).get("dir", "qa-knowledge/e2e")
    result = analyse(repo, cfg, out)
    t = result["tiers"]
    print(f"{len(result['scenarios'])} scenarios -> golden {t.get('golden', 0)}, e2e {t.get('e2e', 0)}, "
          f"component {t.get('component', 0)}, unit {t.get('unit', 0)}, merge {t.get('merge', 0)}, "
          f"drop {t.get('drop', 0)}, disabled {t.get('disabled', 0)} · see {out}/summary.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
