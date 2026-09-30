package com.example.pricing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.params.provider.Arguments.arguments;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.MethodSource;

/** Example layout: fixed clock, @Nested scenarios, parameterized cases, exception checks. */
@Tag("unit")
class PriceCalculatorTest {

    private static final Clock FIXED_CLOCK = Clock.fixed(Instant.parse("2026-01-15T10:00:00Z"), ZoneOffset.UTC);

    private PriceCalculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new PriceCalculator(FIXED_CLOCK);
    }

    @Test
    void returnsZeroForEmptyCart() {
        var total = calculator.total(Cart.empty());

        assertThat(total).isEqualByComparingTo("0.00");
    }

    @ParameterizedTest(name = "{0} items of {1} -> {2}")
    @CsvSource({
        "1, 10.00, 10.00",
        "3, 10.00, 30.00",
        "10, 10.00, 90.00" // bulk discount starts at 10 items
    })
    void multipliesQuantityByUnitPrice(int quantity, BigDecimal unitPrice, BigDecimal expected) {
        var cart = Cart.of(new Item("SKU-1", quantity, unitPrice));

        assertThat(calculator.total(cart)).isEqualByComparingTo(expected);
    }

    @Nested
    class WhenCouponApplied {

        @Test
        void subtractsPercentageDiscount() {
            var cart = Cart.of(new Item("SKU-1", 1, new BigDecimal("100.00"))).withCoupon("SAVE10");

            assertThat(calculator.total(cart)).isEqualByComparingTo("90.00");
        }

        @ParameterizedTest(name = "{0}")
        @MethodSource("com.example.pricing.PriceCalculatorTest#invalidCoupons")
        void rejectsInvalidCoupon(String coupon, String expectedMessage) {
            var cart = Cart.of(new Item("SKU-1", 1, BigDecimal.TEN)).withCoupon(coupon);

            assertThatThrownBy(() -> calculator.total(cart))
                .isInstanceOf(InvalidCouponException.class)
                .hasMessageContaining(expectedMessage);
        }
    }

    static Stream<Arguments> invalidCoupons() {
        return Stream.of(
            arguments("EXPIRED2025", "expired"),
            arguments("UNKNOWN", "not found"));
    }
}
