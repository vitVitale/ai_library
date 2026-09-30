# Parameterized tests cheatsheet

Requires `junit-jupiter-params` (included in the `junit-jupiter` aggregate artifact).

```java
@ParameterizedTest(name = "{index}: {0} -> {1}")
@CsvSource({
    "0,     0.00",
    "100,   10.00",
    "'',    0.00"        // quote to pass an empty string
})
void calculatesDiscount(String input, BigDecimal expected) { ... }

@ParameterizedTest
@CsvSource(useHeadersInDisplayName = true, textBlock = """
    amount, currency, expected
    10,     EUR,      10.00
    10,     USD,      9.20
    """)
void convertsCurrency(BigDecimal amount, String currency, BigDecimal expected) { ... }

@ParameterizedTest
@ValueSource(strings = {"", "  ", "\t"})
void rejectsBlankNames(String name) { ... }

@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" "})
void rejectsNullOrBlank(String name) { ... }

@ParameterizedTest
@EnumSource(value = Status.class, names = {"CANCELLED", "REFUNDED"})
void closedStatusesAreFinal(Status status) { ... }

@ParameterizedTest
@MethodSource("invalidOrders")          // static method in the same class returning Stream<Arguments>
void rejectsInvalidOrders(Order order, String expectedError) { ... }

static Stream<Arguments> invalidOrders() {
    return Stream.of(
        arguments(orderWithoutItems(), "Order must contain items"),
        arguments(orderWithNegativeQty(), "Quantity must be positive"));
}

@ParameterizedTest
@CsvFileSource(resources = "/data/tax-rates.csv", numLinesToSkip = 1)
void appliesTaxRate(String country, BigDecimal rate) { ... }
```

Tips
- Use `name = ...` so reports show which case failed.
- Prefer `@MethodSource` when arguments are objects; prefer `@CsvSource` for primitives/strings.
- Keep one expected outcome per parameterized test; split "valid" and "invalid" cases into separate tests.
