---
name: ui-e2e-java
description: Write stable browser UI end-to-end tests in Java with Selenide or Playwright for Java - page objects, resilient locators, auto-waiting instead of sleeps, test isolation, screenshots/traces on failure, headless CI runs. Use when creating or fixing UI/E2E/browser tests in Java, building page objects, or debugging flaky UI tests.
---

# UI E2E tests in Java (Selenide / Playwright)

## Pick the tool already in the project
Check the build file: `com.codeborne:selenide` → Selenide; `com.microsoft.playwright:playwright` → Playwright. Don't introduce a second UI framework. For a new project with no preference, suggest Playwright (built-in tracing, multi-browser, fast contexts).

## Structure
```
src/test/java/<pkg>/ui/
├── pages/        # page objects: locators + user-level actions, no assertions on business rules
├── components/   # reusable widgets (header, modal, table)
├── tests/        # tests: navigate, act via pages, assert
└── support/      # browser setup extension, config, test data
```
Templates: [templates/selenide/LoginPage.java](templates/selenide/LoginPage.java), [templates/playwright/LoginPage.java](templates/playwright/LoginPage.java), [templates/playwright/PlaywrightExtension.java](templates/playwright/PlaywrightExtension.java).

## Locators (in priority order)
1. Dedicated test ids: `data-testid` / `data-test` (ask devs to add them; mention it if missing).
2. Accessible role + name: Playwright `getByRole(AriaRole.BUTTON, new Page.GetByRoleOptions().setName("Sign in"))`; Selenide `$(byText("Sign in"))` / `$(byAttribute("aria-label", ...))`.
3. Labels/placeholders for inputs.
4. Short CSS. **Never** absolute XPath or auto-generated class names (`.css-1x2y3z`).

## Waiting
- No `Thread.sleep`, no `WebDriverWait` wrappers — both frameworks auto-wait.
- Selenide: `$(...).shouldBe(visible)`, `shouldHave(text("..."))`, `$$(...).shouldHave(size(3))`; raise `Configuration.timeout` only globally and with a reason.
- Playwright: use web-first assertions `assertThat(locator).isVisible()` / `.hasText(...)` from `com.microsoft.playwright.assertions.PlaywrightAssertions`; wait for network with `page.waitForResponse(...)` around the triggering action when needed.

## Isolation and speed
- Each test starts from a clean state: new browser context (Playwright) / `closeWebDriver()` or cleared cookies+storage (Selenide).
- Create preconditions via API or DB seeding, not by clicking through the UI; log in by injecting a session cookie/storage state when possible (Playwright `storageState`).
- Keep UI tests for critical user journeys; push field-level validation to API/unit tests.
- Must run headless in CI (`-Dselenide.headless=true` / `setHeadless(true)`), configurable base URL (`-Dselenide.baseUrl` / system property).

## On failure
- Selenide automatically saves screenshot + page source into `build/reports/tests` (or `target/`); with Allure add `SelenideLogger.addListener("AllureSelenide", new AllureSelenide())`.
- Playwright: record a trace per test (`context.tracing().start(...)`, save on failure) and attach screenshot; see the extension template.

## Debugging a flaky UI test
1. Reproduce with repeated runs (`@RepeatedTest(20)` locally, or rerun in CI).
2. Look at the trace/screenshot: is the locator ambiguous, an animation/overlay intercepting, data shared with another test, or a race with a network call?
3. Fix the cause (better locator, wait for the specific response/state, isolate data). Retries (`rerunFailingTestsCount`) are a last resort and must be reported.
