# confluence-coverage configuration

The file is `confluence-coverage.toml` in the repo root; override the location with `--config`. Every key is optional unless marked required.

## Page references
Wherever a page is expected, you can give:
- a numeric page id (`"123456"`);
- a page URL (`https://…/pages/viewpage.action?pageId=123456`, or `…/display/SPACE/Page+Title`);
- an exact page title (case-insensitive).

Missing references are reported as warnings at the top of `coverage.md`.

## [confluence] (used by confluence_sync.py)
| Key | Default | Meaning |
|---|---|---|
| `base_url` | env `CONFLUENCE_URL` | Server/DC base URL, including context path (e.g. `https://host/confluence`). Required. |
| `spaces` | `[]` | Whole spaces to list. `--space` on the CLI overrides. |
| `pages` | `[]` | Pages to sync with their subtrees, from any space: URL, id or title. Uses CQL (`ancestor=`), so there is no full space listing. `--page` on the CLI overrides this (and ignores `spaces` unless `--space` is also given). At least one of `spaces`/`pages` is required. |
| `roots` | all pages | Within `spaces`, only sync these subtrees. `--root` overrides. |
| `max_depth` | unlimited | Levels below roots/pages. |
| `jira_projects` | any `ABC-123` | Restricts Jira key detection, which avoids false keys like `ISO-9001`. |
| `ca_bundle` | env `CONFLUENCE_CA_BUNDLE` | PEM file for a corporate CA. |
| `out_dir` | `qa-knowledge/confluence` | Snapshot location. |

The token is **only** read from env `CONFLUENCE_PAT` (Bearer auth, DC 7.9+). It is never written anywhere.

## [features]
| Key | Default | Meaning |
|---|---|---|
| `pages` | `[]` | Pages that are features. |
| `folders` | `[]` | Their descendants up to `depth` are features. |
| `depth` | `1` | 1 = direct children only. |
| `labels` | `[]` | Pages with any of these labels are features. |
| `keywords` | requirement, prd, specification, feature, epic, user stor | Title words used only when nothing above is set (a guess). |

## [test_docs]
| Key | Default | Meaning |
|---|---|---|
| `pages`, `folders` | `[]` | Test docs: the pages themselves, or all descendants of the folders. |
| `labels` | test-plan, test-strategy, test-cases, testplan, qa | Pages with these labels are test docs. |
| `keywords.plan/strategy/cases` | see template | Any page whose title contains one of these words is a test doc. The same words decide its type. The type is checked in this order: title, labels, ancestor path, headings. Default type is `plan`. |

## [code]
| Key | Default | Meaning |
|---|---|---|
| `test_globs` | Java/Kotlin `src/test`, `*IT.java`, Python `tests/`, `test_*.py`, `*_test.py` | Test files to scan, relative to `--repo`. |
| `exclude` | .git, node_modules, target, build, .venv, venv, .gradle, .idea | Path parts to skip. |

A test file matches a feature when:
- it contains one of the feature page's Jira keys; or
- an Allure `@Feature`/`@Story`/`@Epic` equals the feature title; or
- all distinctive title words appear in its class/method names, `@DisplayName`, `@Tag` or pytest markers.

## [match]
| Key | Default | Meaning |
|---|---|---|
| `strong` | `0.55` | Similarity at or above this is auto-accepted (shown with `~`). |
| `weak` | `0.30` | Similarity between `weak` and `strong` goes to `review.md`. |
| `max_review_per_feature` | `3` | Caps review size. |

A text match is only the fallback. These signals always win, strongest first:
1. manual override
2. page link in either direction
3. shared Jira key
4. test doc is a child page of the feature

## [output]
| Key | Default |
|---|---|
| `dir` | `qa-knowledge`. Holds `coverage.md`, `coverage.json`, `review.md` and `mapping-overrides.txt`. |
