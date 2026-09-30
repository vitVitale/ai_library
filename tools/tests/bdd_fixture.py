"""A tiny payment-engine Cucumber repo used by the bdd-suite tests."""

from pathlib import Path

FEATURES = {
    "instant-payment/instant.feature": '''
@instant
Feature: Instant payment

  Background:
    Given the engine is running

  @critical
  Scenario: Instant payment is settled
    When the customer sends an instant payment of 100.00 EUR
    Then the CSM simulator confirms the payment
    And the payment status is "ACSC"

  Scenario: Instant payment is settled again
    When the customer sends an instant payment of 100.00 EUR
    Then the CSM simulator confirms the payment
    And the payment status is "ACSC"

  Scenario: Small instant payment is settled
    When the customer sends an instant payment of 5.00 EUR
    Then the CSM simulator confirms the payment
    And the payment status is "ACSC"

  Scenario Outline: Invalid instant payment is rejected
    When the customer sends an instant payment with iban "<iban>"
    Then the API responds with error "<code>"

    Examples:
      | iban | code   |
      | XX   | FORMAT |
      | DE   | FORMAT |
      | FR1  | FORMAT |
      | NL12 | LENGTH |
      | BE   | FORMAT |
      | IT0  | FORMAT |

  Scenario: Instant payment times out at CSM
    When the customer sends an instant payment of 10.00 EUR
    And the CSM simulator does not respond
    Then the payment status is "RJCT"
''',
    "sct-payment/sct.feature": '''
Feature: SEPA credit transfer

  Scenario: SCT payment is booked
    When the customer submits a SEPA credit transfer of 50.00 EUR
    Then the payment is sent to the CSM
    And the payment status is "ACSC"

  Scenario: SCT payment is returned
    When the customer submits a SEPA credit transfer of 50.00 EUR
    Then the payment is sent to the CSM
    And the payment status is "ACSC"
    When the CSM sends a pacs.004 return
    Then the payment status is "RETURNED"

  Scenario: SCT with missing debtor name is rejected
    When the customer submits a SEPA credit transfer without debtor name
    Then the API responds with error "MISSING_NAME"

  Scenario: SCT payment status can be queried
    When the customer submits a SEPA credit transfer of 50.00 EUR
    Then the payment can be found via the status API

  @wip
  Scenario: SCT recall
    When the bank recalls the payment
''',
    "sdd-payment/sdd.feature": '''
Feature: SEPA direct debit

  Rule: Mandates

    Background:
      Given a valid mandate exists

    Scenario: First collection with mandate is settled
      When the creditor collects 20.00 EUR with sequence type "FRST"
      Then the collection is sent via kafka to the settlement service
      And the payment status is "ACSC"
''',
}

GLUE = {
    "PaymentSteps.java": '''
package com.pe.steps;

public class PaymentSteps {
    @Autowired private RestTemplate restTemplate;
    @Autowired private JdbcTemplate jdbcTemplate;

    @Given("the engine is running")
    public void engineIsRunning() {
        restTemplate.getForEntity("/health", String.class);
    }

    @When("the customer sends an instant payment of {bigdecimal} EUR")
    public void sendInstant(BigDecimal amount) {
        restTemplate.postForEntity("/instant", Map.of("amount", amount), String.class);
    }

    @When("the customer sends an instant payment with iban {string}")
    public void sendInstantWithIban(String iban) {
        restTemplate.postForEntity("/instant", Map.of("iban", iban), String.class);
    }

    @When("the customer submits a SEPA credit transfer of {bigdecimal} EUR")
    public void submitSct(BigDecimal amount) {
        restTemplate.postForEntity("/sct", Map.of("amount", amount), String.class);
    }

    @When("the customer submits a SEPA credit transfer without debtor name")
    public void submitSctWithoutName() {
        restTemplate.postForEntity("/sct", Map.of(), String.class);
    }

    @Then("the CSM simulator confirms the payment")
    public void csmConfirms() {
        wireMock.verify(postRequestedFor(urlEqualTo("/csm")));
    }

    @When("the CSM simulator does not respond")
    public void csmTimeout() {
        stubFor(post("/csm").willReturn(aResponse().withFixedDelay(60000)));
    }

    @Then("^the payment status is \\"([^\\"]*)\\"$")
    public void paymentStatus(String status) {
        jdbcTemplate.queryForObject("SELECT status FROM payment", String.class);
    }

    @Then("the API responds with error {string}")
    public void apiError(String code) {
        assertThat(lastResponse.getStatusCode().value()).isEqualTo(400);
    }

    @Then("the payment can be found via the status API")
    public void statusApi() {
        restTemplate.getForEntity("/payments/1", String.class);
    }

    @When("the CSM sends a pacs.004 return")
    public void csmReturn() {
        wireMock.stubFor(post("/csm/return"));
    }
}
''',
    "SddSteps.java": '''
package com.pe.steps;

public class SddSteps implements En {
    public SddSteps(KafkaTemplate<String, String> kafka, JdbcTemplate jdbc) {
        Given("a valid mandate exists", () -> {
            jdbc.update("insert into mandate values (1)");
        });
        When("the creditor collects {bigdecimal} EUR with sequence type {string}", (BigDecimal a, String t) -> {
            collectionClient.collect(a, t);
        });
        Then("the collection is sent via kafka to the settlement service", () -> {
            kafka.receive("settlement");
        });
    }
}
''',
}


def build(root: Path) -> Path:
    for rel, text in FEATURES.items():
        p = root / "src/test/resources/features" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text.lstrip("\n"))
    for name, text in GLUE.items():
        p = root / "src/test/java/com/pe/steps" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text.lstrip("\n"))
    return root
