import csv
import json

import pytest

import bdd_suite
from bdd_fixture import build

OUT = "qa-knowledge/e2e"


@pytest.fixture
def repo(tmp_path):
    return build(tmp_path)


def run(repo, cfg=None):
    result = bdd_suite.analyse(repo, cfg or {}, repo / OUT)
    return {s["name"]: s for s in result["scenarios"]}, result


def test_classifies_payment_suite(repo):
    s, result = run(repo)

    assert s["Instant payment is settled"]["tier"] == "golden"
    assert s["Instant payment is settled"]["layers"] == ["csm", "db", "rest"]
    assert s["Instant payment is settled again"]["tier"] == "drop"
    assert s["Instant payment is settled again"]["related"] == s["Instant payment is settled"]["id"]
    assert s["Small instant payment is settled"]["tier"] == "merge"
    assert s["Invalid instant payment is rejected"]["tier"] == "unit"
    assert s["Invalid instant payment is rejected"]["rows"] == 6
    assert s["Instant payment times out at CSM"]["tier"] == "golden"
    assert "outcome:timeout" in s["Instant payment times out at CSM"]["atoms"]

    assert s["SCT payment is booked"]["tier"] == "drop"  # subset of the return flow
    assert s["SCT payment is booked"]["confidence"] == "medium"
    assert s["SCT payment is returned"]["tier"] == "golden"
    assert s["SCT with missing debtor name is rejected"]["tier"] == "unit"
    assert s["SCT payment status can be queried"]["tier"] == "component"
    assert s["SCT recall"]["disabled"]

    sdd = s["First collection with mandate is settled"]
    assert sdd["tier"] == "golden" and "mq" in sdd["layers"] and "check:mandate" in sdd["atoms"]
    assert result["meta"]["step_defs"] == 14
    assert "sct-payment outcome:rejected" in result["uncovered_atoms"]


def test_risk_counts_tags_outcomes_and_external_systems(repo):
    s, _ = run(repo, {"risk": {"tags": {"critical": 30}}})
    settled, again = s["Instant payment is settled"], s["Instant payment is settled again"]
    assert settled["risk"] - again["risk"] == 30 and "@critical" in settled["why"]
    assert s["SCT payment is returned"]["risk"] > s["SCT payment status can be queried"]["risk"]


def test_outputs_and_review_batches(repo):
    run(repo)
    out = repo / OUT
    summary = (out / "summary.md").read_text()
    assert "**Proposal:** golden E2E **4**" in summary
    assert "| instant-payment | 5 | 2 | 0 | 0 | 1 | 1 | 1 | 2 |" in summary

    review = (out / "review-01.md").read_text()
    assert "drop? ~" in review and "SCT payment is booked" in review
    assert "W: the customer submits a sepa credit transfer of {n} eur" in review

    rerun = (out / "golden-set.rerun.txt").read_text().split()
    assert "src/test/resources/features/sdd-payment/sdd.feature:8" in rerun and len(rerun) == 4
    rows = list(csv.DictReader((out / "scenarios.csv").open()))
    assert len(rows) == 11 and {r["tier"] for r in rows} >= {"golden", "unit", "disabled"}
    assert "Move to unit level" in (out / "moves.md").read_text()


def test_decisions_override_and_leave_review(repo):
    s, _ = run(repo)
    booked = s["SCT payment is booked"]["id"]
    small = s["Small instant payment is settled"]["id"]
    (repo / OUT / "decisions.txt").write_text(f"{booked} e2e  # happy path smoke\n{small} golden\nnonsense line\n")

    s, _ = run(repo)
    assert s["SCT payment is booked"]["tier"] in ("e2e", "golden") and s["SCT payment is booked"]["decided"]
    assert s["Small instant payment is settled"]["tier"] == "golden"
    assert not list((repo / OUT).glob("review-*.md"))  # nothing left to review


def test_confluence_pages_are_linked_and_gaps_listed(repo):
    snap = repo / "qa-knowledge/confluence"
    snap.mkdir(parents=True)
    pages = [
        {"id": "1", "title": "SEPA Direct Debit mandates", "path": ["Payments"], "ancestors": ["9"],
         "headings": ["Mandate validation", "First collection FRST"], "intro": "collections need a valid mandate",
         "words": 300},
        {"id": "2", "title": "Instant payment CSM timeout handling", "path": ["Payments"], "ancestors": ["9"],
         "headings": ["Timeout"], "intro": "when the CSM does not respond the instant payment is rejected",
         "words": 200},
        {"id": "3", "title": "Card chargebacks", "path": ["Cards"], "ancestors": ["8"],
         "headings": ["Dispute window"], "intro": "chargeback rules for card schemes", "words": 500},
    ]
    (snap / "index.jsonl").write_text("\n".join(json.dumps(p) for p in pages) + "\n")

    s, result = run(repo)
    assert s["First collection with mandate is settled"]["req"] == "1"
    assert s["Instant payment times out at CSM"]["req"] == "2"
    assert [p["id"] for p in result["confluence"]["uncovered"]] == ["3"]

    _, result = run(repo, {"confluence": {"pages": ["https://c/pages/viewpage.action?pageId=9"]}})
    assert result["confluence"]["pages"] == 2  # restricted to descendants of page 9


def test_main_cli(repo, capsys):
    (repo / "bdd-suite.toml").write_text('[suite]\nfeatures_dir = "src/test/resources/features"\n'
                                         '[review]\nlimit = 0\n')
    assert bdd_suite.main(["--repo", str(repo)]) == 0
    assert "11 scenarios -> golden 4" in capsys.readouterr().out
    assert not list((repo / OUT).glob("review-*.md"))


def test_different_outcome_is_not_a_duplicate_or_subset(tmp_path):
    f = tmp_path / "src/test/resources/features/sct/x.feature"
    f.parent.mkdir(parents=True)
    f.write_text("""Feature: x
  Scenario: Accepted
    When the customer sends a payment of 10.00 EUR
    Then the payment status is "ACSC"

  Scenario: Rejected over limit
    When the customer sends a payment of 10.00 EUR
    And the CSM responds
    Then the payment status is "RJCT"

  Scenario: Accepted large
    When the customer sends a payment of 99.00 EUR
    Then the payment status is "RJCT"
""")
    s = {x["name"]: x for x in bdd_suite.analyse(tmp_path, {}, tmp_path / OUT)["scenarios"]}
    assert s["Accepted"]["tier"] not in ("drop", "merge")  # same skeleton as "Accepted large" but other outcome
    assert s["Accepted large"]["tier"] not in ("drop", "merge")
