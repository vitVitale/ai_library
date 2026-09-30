# ai_library

My skills and agents for **Claude Code** and the **GitHub Copilot coding agent**, focused on Java/Python test automation and QA.

One source of truth: everything is written once in Claude Code plugin layout. Skills use the shared `SKILL.md` format that both tools understand. Agents are converted to Copilot's `.agent.md` format when installed.

## What's inside

| Plugin | Type | Name | Purpose |
|---|---|---|---|
| `java-testing` | skill | `junit5-tests` | JUnit Jupiter structure, naming, parameterized tests, JUnit 4 migration |
| | skill | `assertj-mockito` | Idiomatic assertions and mocks, when not to mock |
| | skill | `rest-assured-api-tests` | API test framework layout, specs, schema validation, negative cases |
| | skill | `ui-e2e-java` | Selenide / Playwright-Java page objects, locators, waits, traces |
| | skill | `maven-gradle-test-setup` | Surefire/Failsafe, Gradle suites, tags, parallel runs, Allure, JaCoCo |
| `qa-agents` | agent | `test-planner` | Story/diff → risk-based test plan |
| | agent | `test-case-writer` | Plan → manual cases or automated tests, runs them |
| | agent | `flaky-test-investigator` | Reproduces flaky tests, finds and fixes root cause |
| | agent | `bug-report-writer` | Failure/log → reproducible bug report |
| | agent | `test-code-reviewer` | Reviews test code quality and coverage gaps |
| | skill | `test-case-format` | Test case / test plan format and design techniques |
| | skill | `bug-report-template` | Bug report format and rules |

## Use with Claude Code (plugin marketplace)

```bash
claude plugin marketplace add vitVitale/ai_library
```
```bash
claude plugin install java-testing@ai-library
```
```bash
claude plugin install qa-agents@ai-library
```
Or inside a session: `/plugin marketplace add vitVitale/ai_library`, then `/plugin`. Skills trigger automatically (or run `/java-testing:junit5-tests`); agents appear in `/agents`.

## Use with GitHub Copilot (install into a repo)

Copilot's coding agent only sees files committed in the repository, so copy the content in with `ailib`:

```bash
cd tools && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```
```bash
tools/.venv/bin/ailib install --target ~/IdeaProjects/my-service --dry-run
```
```bash
tools/.venv/bin/ailib install --target ~/IdeaProjects/my-service
```

This writes `.github/skills/<skill>/…`, `.github/agents/<agent>.agent.md` and `.ailib.lock.json` into the target repo. Commit them.

Options:
- `--plugins java-testing,qa-agents`: choose plugins (default: same as last install, else all). Plugins you leave out are removed from the target.
- `--for copilot|claude|both`: `claude` writes `.claude/skills` and `.claude/agents` instead, for teammates without the plugin.
- Re-run anytime to update. Files you edited locally, or files ailib didn't create, are never overwritten or deleted without `--force`.

## Develop

```bash
cd tools && .venv/bin/pytest -q && .venv/bin/ailib validate
```
```bash
claude plugin validate .
```
See [docs/authoring.md](docs/authoring.md) for how to write skills and agents.
