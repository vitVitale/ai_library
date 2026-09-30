---
name: junit5-tests
description: Write and refactor JUnit Jupiter (JUnit 5/6) unit and integration tests in Java - structure, naming, @Nested, parameterized tests, tags, lifecycle, temp dirs, exceptions and timeouts. Use when creating or fixing Java tests, adding test coverage for a Java class, or converting JUnit 4/TestNG tests to JUnit Jupiter.
---

# JUnit Jupiter tests

## Before writing
1. Look at existing tests in the module first and **match their style** (naming, assertion library, base classes, folder layout). Existing conventions win over this skill.
2. Check the build file for the JUnit version and which assertion/mocking libraries are already present. Do not add new test dependencies without saying so.
3. Unit tests go in `src/test/java`, same package as the class under test, named `<ClassUnderTest>Test`. Integration tests are named `<Thing>IT` (see `maven-gradle-test-setup` skill).

## Test shape
- One behaviour per test. Arrange / Act / Assert, separated by a blank line (no `// given` comments needed unless the project uses them).
- Method names describe behaviour: `returnsEmptyListWhenNoOrdersExist()` or `should_return_empty_list_when_no_orders()` — follow the project's pattern. Add `@DisplayName` only if the project uses it.
- Test classes and methods are package-private (no `public`).
- Group related scenarios with `@Nested` inner classes (e.g. `class WhenCartIsEmpty`).
- Never test private methods directly; test through the public API.
- No logic in tests (no loops/ifs computing expected values). Use parameterized tests instead.
- No `Thread.sleep`. For async code use Awaitility (`await().atMost(...).until(...)`) if available.

## Assertions
- Prefer AssertJ if it is on the classpath (see `assertj-mockito` skill). Otherwise JUnit `Assertions`:
  - `assertEquals(expected, actual)` — expected first.
  - `assertAll(...)` to report several independent checks at once.
  - `var ex = assertThrows(IllegalArgumentException.class, () -> ...); assertEquals("...", ex.getMessage());`
  - `assertTimeout(Duration.ofSeconds(1), () -> ...)`.

## Parameterized tests
Use when the same behaviour is checked with different inputs. Cheatsheet: [references/parameterized.md](references/parameterized.md). Full example: [templates/PriceCalculatorTest.java](templates/PriceCalculatorTest.java).

## Lifecycle and resources
- `@BeforeEach` for fresh state per test; avoid shared mutable static state.
- `@TempDir Path tmp` for files, never write into the project directory.
- `@Tag("integration")`, `@Tag("slow")`, `@Tag("smoke")` to allow selective runs; reuse tags that already exist in the project.
- `@Disabled("reason + ticket")` only with a reason.
- Use `@ExtendWith` for Mockito/Spring/etc. extensions rather than manual setup.

## Migrating from JUnit 4
| JUnit 4 | Jupiter |
|---|---|
| `@Before` / `@After` | `@BeforeEach` / `@AfterEach` |
| `@BeforeClass` | `@BeforeAll` (static) |
| `@Ignore` | `@Disabled` |
| `@Test(expected = X.class)` | `assertThrows(X.class, ...)` |
| `@RunWith(MockitoJUnitRunner.class)` | `@ExtendWith(MockitoExtension.class)` |
| `@Rule TemporaryFolder` | `@TempDir` |
| `@Category` | `@Tag` |

## Done checklist
- [ ] Tests run green locally with the project's command (`mvn -q test -Dtest=ClassNameTest` or `./gradlew test --tests ClassNameTest`).
- [ ] Each test fails if the behaviour under test breaks (mentally flip the implementation).
- [ ] No sleeps, no order dependence, no reliance on the current date/time zone/locale without fixing them (inject `Clock`).
