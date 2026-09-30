---
name: assertj-mockito
description: Idiomatic AssertJ assertions and Mockito mocking for Java tests - fluent/soft assertions, collections, recursive comparison, exceptions, stubbing, verification, argument captors, and when not to mock. Use when writing assertions or test doubles in Java tests, reviewing over-mocked tests, or replacing assertEquals/Hamcrest with AssertJ.
---

# AssertJ + Mockito

## AssertJ essentials
Always `import static org.assertj.core.api.Assertions.*;` and start with `assertThat(actual)`.

```java
assertThat(user.getName()).isEqualTo("Ann");
assertThat(price).isEqualByComparingTo("10.00");          // BigDecimal: ignore scale
assertThat(list).hasSize(3).containsExactly(a, b, c);      // order matters
assertThat(list).containsExactlyInAnyOrder(a, b, c);
assertThat(orders).extracting(Order::getId).containsOnly(1L, 2L);
assertThat(orders).filteredOn(o -> o.isPaid()).hasSize(2);
assertThat(map).containsEntry("k", "v").doesNotContainKey("x");
assertThat(optional).contains("value");                    // or isEmpty()
assertThat(text).startsWith("Error").contains("id=42");
assertThat(dto).usingRecursiveComparison()
    .ignoringFields("id", "createdAt")
    .isEqualTo(expectedDto);                               // deep equals without equals()
assertThatThrownBy(() -> service.pay(order))
    .isInstanceOf(PaymentException.class)
    .hasMessageContaining("insufficient funds");
assertThatNoException().isThrownBy(() -> service.validate(order));
assertThat(actual).as("order %s status", id).isEqualTo(PAID);   // description shown on failure
```

Soft assertions — report all failures of one scenario (good for API/UI checks of many fields):
```java
SoftAssertions.assertSoftly(softly -> {
    softly.assertThat(resp.status()).isEqualTo(200);
    softly.assertThat(resp.body().name()).isEqualTo("Ann");
});
```

Rules
- Don't assert `isNotNull()` right before another assertion on the same object — AssertJ already fails on null.
- Don't use `assertThat(a.equals(b)).isTrue()`; failure messages become useless.
- Use `.as(...)` when the value alone doesn't explain what failed.

## Mockito essentials
```java
@ExtendWith(MockitoExtension.class)            // strict stubs: unused stubbing fails the test
class OrderServiceTest {
    @Mock PaymentGateway gateway;
    @Mock OrderRepository repository;
    @InjectMocks OrderService service;
    @Captor ArgumentCaptor<Order> orderCaptor;

    @Test
    void savesPaidOrder() {
        when(gateway.charge(any(), eq(new BigDecimal("10.00")))).thenReturn(ChargeResult.ok("tx-1"));

        service.checkout(cartWithTotal("10.00"));

        verify(repository).save(orderCaptor.capture());
        assertThat(orderCaptor.getValue().getStatus()).isEqualTo(Status.PAID);
        verifyNoMoreInteractions(gateway);
    }
}
```
- BDD style if the project uses it: `given(gateway.charge(...)).willReturn(...)`, `then(repository).should().save(...)`.
- Exceptions: `when(x.call()).thenThrow(new IOException())`; void methods: `doThrow(...).when(x).run()`.
- Static/final mocking works with the default inline mock maker (`mockStatic(Clock.class)` in try-with-resources), but prefer injecting the dependency instead.

## When NOT to mock
- Value objects, DTOs, collections, simple POJOs → use real instances / builders.
- The class under test → never (no `spy` on the SUT unless refactoring legacy code).
- Types you don't own with complex behaviour (HTTP clients, JDBC) → prefer a fake, WireMock, or Testcontainers in an integration test.
- If a test needs more than ~3 mocks, the class probably has too many responsibilities; mention it.
- Verify **outcomes** (return values, state, messages sent) rather than every internal call. Use `verify` only for side effects that are the point of the behaviour.
