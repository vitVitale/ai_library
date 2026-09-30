---
name: maven-gradle-test-setup
description: Configure and run Java test suites with Maven or Gradle - JUnit Platform setup, unit vs integration test split (Surefire/Failsafe, Gradle test suites), tag filtering, parallel execution, Allure and JaCoCo reports, and commands to run a single test. Use when adding test dependencies or plugins, splitting or filtering test runs, enabling parallel tests or reports, or when you need the right command to run specific Java tests.
---

# Maven / Gradle test setup

## First, detect the build
- `pom.xml` → Maven (use `./mvnw` if the wrapper exists). Details: [references/maven.md](references/maven.md)
- `build.gradle(.kts)` → Gradle (always `./gradlew`). Details: [references/gradle.md](references/gradle.md)
- Multi-module? Run commands for the affected module only (`-pl module -am` / `:module:test`).

## Versions
Reuse versions already declared in the build (properties, BOMs, version catalog `gradle/libs.versions.toml`). When adding something new, use the latest stable release from Maven Central and prefer importing a BOM (`org.junit:junit-bom`, `io.qameta.allure:allure-bom`) over pinning each artifact.

## Running tests — quick reference
| Goal | Maven | Gradle |
|---|---|---|
| All unit tests | `./mvnw test` | `./gradlew test` |
| One class | `./mvnw test -Dtest=OrderServiceTest` | `./gradlew test --tests OrderServiceTest` |
| One method | `-Dtest='OrderServiceTest#paysOrder'` | `--tests 'OrderServiceTest.paysOrder'` |
| Pattern | `-Dtest='*ApiTest'` | `--tests '*ApiTest'` |
| Integration tests | `./mvnw verify` (Failsafe, `*IT`) | `./gradlew integrationTest` |
| By tag | `-Dgroups=smoke` / `-DexcludedGroups=slow` | custom property, see reference |
| Don't stop on failure (multi-module) | `-fae` | `--continue` |
| Rerun without cache | — | `--rerun-tasks` or `cleanTest test` |

## Conventions
- Unit tests: `*Test`, run by Surefire / `test` task, no network or containers, fast.
- Integration tests: `*IT` (Maven Failsafe) or a separate Gradle `integrationTest` suite; may use Testcontainers/WireMock/real HTTP.
- Tags: `unit`, `integration`, `api`, `ui`, `smoke`, `slow` — reuse what the project already has.
- Parallelism: enable JUnit Platform parallel execution via `src/test/resources/junit-platform.properties` only when tests are isolated:
  ```properties
  junit.jupiter.execution.parallel.enabled=true
  junit.jupiter.execution.parallel.mode.default=same_thread
  junit.jupiter.execution.parallel.mode.classes.default=concurrent
  junit.jupiter.execution.parallel.config.strategy=dynamic
  ```
  (classes in parallel, methods in a class sequential — safest start). Mark shared-resource tests with `@ResourceLock` or `@Execution(SAME_THREAD)`.
- Reports: JUnit XML is produced by default (`target/surefire-reports`, `build/test-results`) — CI should publish it. Allure needs the `allure-junit5` dependency and (for `@Step`/`@Attachment`) AspectJ weaving; see the references.
- Never set `testFailureIgnore=true` or `ignoreFailures = true` permanently to "make the build green".

## When a build change is needed
Make the smallest change, show the diff, and run the affected test command to prove it works.
