from pathlib import Path

import pytest

import coverage_map
from cc_common import write_index
from coverage_map import build, load_overrides, render_coverage, render_review


def page(pid, title, ancestors=(), labels=(), jira=(), links=(), headings=(), intro="", updated="2026-01-01"):
    return {"id": pid, "title": title, "ancestors": list(ancestors), "path": [], "labels": list(labels),
            "jira": list(jira), "links": list(links), "headings": list(headings), "intro": intro,
            "updated": updated, "url": f"https://c/{pid}", "file": f"pages/{pid}.md"}


PAGES = {p["id"]: p for p in [
    page("10", "Product"),
    page("11", "Payments v2", ["10"], jira=["PAY-1"], headings=["Card payments", "Wallets"],
         intro="Customers pay by card or wallet"),
    page("12", "User Login", ["10"], updated="2026-05-01"),
    page("13", "Refunds", ["10"], jira=["PAY-9"]),
    page("14", "Loyalty points", ["10"], intro="Customers earn loyalty points on every order"),
    page("20", "QA"),
    page("21", "Test plan - Payments v2", ["20"]),
    page("22", "Login checklist", ["20"], links=["12"]),
    page("23", "Refund flow tests", ["20"], jira=["PAY-9"]),
    page("24", "Test strategy", ["20"]),
    page("25", "Edge cases", ["10", "11"], labels=["test-cases"]),
    page("26", "Points and rewards test ideas", ["20"], intro="Accrual of loyalty points for orders"),
]}
CONFIG = {"features": {"folders": ["Product"]}, "test_docs": {"folders": ["QA"]}}


@pytest.fixture
def repo(tmp_path):
    def write(rel, text):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    write("src/test/java/com/x/PaymentsApiTest.java",
          "// covers PAY-1\nclass PaymentsApiTest {\n @Test void pays() {}\n @Test void declines() {}\n}\n")
    write("src/test/java/com/x/UserLoginTest.java", "class UserLoginTest {\n @Test void logsIn() {}\n}\n")
    write("tests/test_misc.py", "def test_something():\n    pass\n")
    write("node_modules/pkg/tests/test_user_login.py", "def test_x():\n    pass\n")
    return tmp_path


def no_overrides():
    return {"pairs": {}, "feature": set(), "doc": {}, "ignore": set()}


def by_id(result):
    return {f["id"]: f for f in result["features"]}


def test_selects_features_and_matches_by_each_signal(repo):
    result = build(PAGES, CONFIG, no_overrides(), repo, warn=pytest.fail)
    f = by_id(result)

    assert [x["title"] for x in result["features"]] == ["Loyalty points", "Payments v2", "Refunds", "User Login"]
    assert [(d["id"], d["reason"]) for d in f["11"]["plan"]] == [("21", "similar")]
    assert [(d["id"], d["reason"]) for d in f["11"]["cases"]] == [("25", "child")]
    assert [(d["id"], d["reason"]) for d in f["12"]["cases"]] == [("22", "link")]
    assert [(d["id"], d["reason"]) for d in f["13"]["plan"]] == [("23", "jira")]
    assert [(d["id"], d["type"]) for d in result["unmatched_docs"]] == [("26", "plan"), ("24", "strategy")]


def test_code_scan(repo):
    f = by_id(build(PAGES, CONFIG, no_overrides(), repo))
    assert f["11"]["automation"] == {"tests": 2, "files": [
        {"path": "src/test/java/com/x/PaymentsApiTest.java", "tests": 2, "reason": "jira:PAY-1"}]}
    assert [h["reason"] for h in f["12"]["automation"]["files"]] == ["terms"]
    assert f["13"]["automation"]["files"] == []  # node_modules and unrelated tests are ignored


def test_gap_flags(repo):
    f = by_id(build(PAGES, CONFIG, no_overrides(), repo))
    assert f["11"]["gaps"] == []
    assert f["12"]["gaps"] == ["STALE"]  # feature edited after its checklist
    assert f["13"]["gaps"] == ["NO_AUTO"]
    assert f["14"]["gaps"] == ["NO_PLAN", "NO_AUTO", "REVIEW"]  # 26 is a plausible but uncertain match


def test_default_thresholds_send_only_uncertain_pair_to_review(repo):
    review = build(PAGES, CONFIG, no_overrides(), repo)["review"]
    assert [(r["feature"], r["doc"]) for r in review] == [("14", "26")]
    assert 0.30 <= review[0]["score"] < 0.55


def test_ambiguous_pairs_go_to_review_and_overrides_decide(repo, tmp_path):
    cfg = {**CONFIG, "match": {"weak": 0.05, "strong": 0.99}}
    result = build(PAGES, cfg, no_overrides(), repo)
    assert {"feature": "14", "doc": "26"} in [{k: r[k] for k in ("feature", "doc")} for r in result["review"]]
    assert "REVIEW" in by_id(result)["14"]["gaps"]

    review = render_review(result, PAGES, "mapping-overrides.txt")
    assert "## 14 Loyalty points" in review
    assert '- 14 26 ? — plan' in review

    overrides = tmp_path / "mapping-overrides.txt"
    overrides.write_text("14 26 yes  # AI decision\nignore 24\ndoc 23 cases\n")
    result = build(PAGES, cfg, load_overrides(overrides), repo)
    f14 = by_id(result)["14"]
    assert [(d["id"], d["reason"]) for d in f14["plan"]] == [("26", "manual")]
    assert all(r["doc"] != "26" or r["feature"] != "14" for r in result["review"])
    assert "24" not in {d["id"] for d in result["unmatched_docs"]}
    assert [d["id"] for d in by_id(result)["13"]["cases"]] == ["23"]

    overrides.write_text("11 21 no\n")
    assert by_id(build(PAGES, CONFIG, load_overrides(overrides), repo))["11"]["plan"] == []


def test_guesses_features_without_config(repo):
    warnings = []
    pages = {**PAGES, "30": page("30", "Checkout requirements")}
    result = build(pages, {}, no_overrides(), repo, warn=warnings.append)
    assert [f["id"] for f in result["features"]] == ["30"]
    assert "no [features] configured" in warnings[0]


def test_render_coverage_is_compact(repo):
    result = build(PAGES, CONFIG, no_overrides(), repo)
    md = render_coverage(result, [])
    assert "| Feature | Plan | Strategy | Cases | Automation | Gaps |" in md
    assert "| Payments v2 (11) | ~Test plan - Payments v2 (21) | — | Edge cases (25) | 2/1 PaymentsApiTest.java |  |" in md
    assert "strategy: Test strategy (24)" in md


def test_main_end_to_end(repo, capsys):
    out = repo / "qa-knowledge"
    write_index((out / "confluence").mkdir(parents=True) or out / "confluence" / "index.jsonl", PAGES)
    (repo / "confluence-coverage.toml").write_text(
        '[features]\nfolders = ["Product", "Missing folder"]\n[test_docs]\nfolders = ["QA"]\n')

    code = coverage_map.main(["--config", str(repo / "confluence-coverage.toml"), "--repo", str(repo),
                              "--out", str(out)])

    assert code == 0
    assert {p.name for p in out.iterdir()} >= {"coverage.md", "coverage.json", "review.md"}
    assert "Warning: [features].folders: 'Missing folder' not found" in (out / "coverage.md").read_text()
    assert "4 features" in capsys.readouterr().out


def test_explicit_plan_or_strategy_word_in_title_wins_over_keywords():
    kw = coverage_map.DEFAULT_KEYWORDS
    assert coverage_map._doc_type(page("1", "TP-00 Card regression plan"), kw) == "plan"
    assert coverage_map._doc_type(page("1", "Regression strategy"), kw) == "strategy"
    assert coverage_map._doc_type(page("1", "Smoke test checklist"), kw) == "cases"


def test_scans_cucumber_feature_files(repo):
    feature = repo / "src/test/resources/features/loyalty-points/earning.feature"
    feature.parent.mkdir(parents=True)
    feature.write_text("@loyalty\nFeature: Earning points\n\n  Scenario: Points for an order\n    Given x\n\n"
                       "  Scenario Outline: Points per tier\n    Given <tier>\n    Examples:\n      | tier |\n      | gold |\n")
    f = by_id(build(PAGES, CONFIG, no_overrides(), repo))
    files = f["14"]["automation"]["files"]  # "Loyalty points" matched via the folder name + feature title
    assert [(h["path"], h["tests"], h["reason"]) for h in files] == [
        ("src/test/resources/features/loyalty-points/earning.feature", 2, "terms")]


def test_design_document_words_are_not_required_terms(repo):
    feature = repo / "src/test/resources/features/instant-payment/settle.feature"
    feature.parent.mkdir(parents=True)
    feature.write_text("Feature: Instant payment settlement\n\n  Scenario: Settled\n    Given x\n")
    pages = {**PAGES, "15": page("15", "Instant payment flow design", ["10"])}
    f = by_id(build(pages, CONFIG, no_overrides(), repo))
    assert [h["path"] for h in f["15"]["automation"]["files"]] == ["src/test/resources/features/instant-payment/settle.feature"]
