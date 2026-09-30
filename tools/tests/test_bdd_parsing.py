import re

from bdd_gherkin import parse
from bdd_glue import compile_pattern, expression_to_regex, scan, StepMatcher

FEATURE = '''
@feature-tag
Feature: Payments
  Some free text description.

  Background:
    Given the engine is running

  @one
  Scenario: Simple
    Given a payment
    And another payment
    When it is sent
      """
      {"doc": "string with Given inside"}
      """
    Then it is booked
    But it is not charged
    And the ledger has:
      | account | amount |
      | A       | 10     |
      | B       | -10    |

  Rule: Returns
    Background:
      Given a settled payment

    @two
    Scenario Outline: Return <reason>
      When the CSM returns it with "<reason>"
      Then the status is "<status>"

      @ex
      Examples: first
        | reason | status   |
        | AC01   | RETURNED |
      Examples: second
        | reason | status   |
        | MS03   | RETURNED |
        | AM04   | RETURNED |
'''


def test_parses_structure_tags_backgrounds_and_tables(tmp_path):
    f = tmp_path / "p.feature"
    f.write_text(FEATURE)
    feat = parse(f)

    assert feat.name == "Payments" and feat.tags == ["@feature-tag"]
    simple, outline = feat.scenarios
    assert simple.tags == ["@feature-tag", "@one"]
    assert [(s.kind, s.text) for s in simple.background] == [("Given", "the engine is running")]
    assert [(s.kind, s.text) for s in simple.steps] == [
        ("Given", "a payment"), ("Given", "another payment"), ("When", "it is sent"),
        ("Then", "it is booked"), ("Then", "it is not charged"), ("Then", "the ledger has:")]
    assert simple.steps[2].docstring
    assert simple.steps[-1].table_header == ["account", "amount"] and simple.steps[-1].table_rows == 2

    assert outline.rule == "Returns" and outline.outline
    assert outline.tags == ["@feature-tag", "@two"]
    assert [s.text for s in outline.background] == ["the engine is running", "a settled payment"]
    assert outline.example_rows == 3
    assert outline.first_row() == {"reason": "AC01", "status": "RETURNED"}
    assert outline.examples[0].tags == ["@ex"]


def test_cucumber_expressions_to_regex():
    rx = re.compile("^" + expression_to_regex("I have {int} cucumber(s) in my belly/stomach") + "$")
    assert rx.match("I have 1 cucumber in my belly")
    assert rx.match("I have 42 cucumbers in my stomach")
    assert not rx.match("I have many cucumbers in my belly")

    assert compile_pattern("the status is {string}").match('the status is "ACSC"')
    assert compile_pattern("amount {bigdecimal} EUR").match("amount 100.00 EUR")
    assert compile_pattern("I pay \\(now)").match("I pay (now)")
    assert compile_pattern("^regex (\\d+)$").match("regex 12")
    assert compile_pattern("broken [regex$") is None


def test_scans_annotation_and_lambda_glue_with_layers(tmp_path):
    (tmp_path / "Steps.java").write_text('''
public class Steps implements En {
    @When("the customer pays {int} EUR")
    public void pays(int amount) {
        restTemplate.postForEntity("/pay", amount, String.class);
        String s = "{ not a brace }";
    }

    @Then("^the CSM gets \\"([^\\"]*)\\"$")
    public void csm(String m) { wireMock.verify(postRequestedFor(urlEqualTo("/csm"))); }

    public Steps() {
        Then("the event is on the topic", () -> { kafkaTemplate.receive("t"); });
    }
}
''')
    layers = {"rest": [r"RestTemplate", r"restTemplate"], "csm": [r"wireMock"], "mq": [r"kafka"]}
    defs = scan([tmp_path / "Steps.java"], tmp_path, layers)

    assert [(d.method, d.location, d.layers) for d in defs] == [
        ("pays", "Steps.java:3", {"rest"}), ("csm", "Steps.java:9", {"csm"}), ("lambda", "Steps.java:13", {"mq"})]
    m = StepMatcher(defs)
    assert m.match("the customer pays 10 EUR").method == "pays"
    assert m.match('the CSM gets "pacs.008"').method == "csm"
    assert m.match("the event is on the topic").method == "lambda"
    assert m.match("something else") is None


def test_unbalanced_quotes_do_not_leak_layers_into_next_step(tmp_path):
    (tmp_path / "S.java").write_text('''
public class S {
    @Then("broken")
    public void broken() { verify(urlEqualTo(\\"/csm\\")); }

    @Then("db step")
    public void db() { jdbcTemplate.query(); }

    @Then("kafka step")
    public void kafka() { kafkaTemplate.send(); }
}
''')
    defs = scan([tmp_path / "S.java"], tmp_path, {"db": ["jdbcTemplate"], "mq": ["kafka"]})
    assert [d.layers for d in defs] == [set(), {"db"}, {"mq"}]


def test_skeleton_keeps_identifiers_and_replaces_data():
    from bdd_suite import skeleton
    assert skeleton('the customer sends a SDD B2B collection of 100.00 EUR on 2026-01-05') == \
        "the customer sends a sdd b2b collection of {n} eur on {n}"
    assert skeleton('the CSM sends pacs.004 with "AC04" for DE89370400440532013000') == \
        "the csm sends pacs.004 with {s} for {iban}"
