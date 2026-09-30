# ai_library — instructions for AI agents working on this repo

This repo is a library of skills and agents for Claude Code and GitHub Copilot, laid out as a Claude Code plugin marketplace.

- Content lives in `plugins/<plugin>/skills/<name>/SKILL.md` and `plugins/<plugin>/agents/<name>.md`. Follow `docs/authoring.md` exactly (frontmatter rules, "Use when" descriptions, short SKILL.md, relative links, Copilot-compatible tools).
- `tools/` is the `ailib` Python CLI (validate / list / install). Standard library + PyYAML only. Keep modules small; add a pytest test for every behaviour change.
- After any change run:
  ```bash
  cd tools && .venv/bin/pytest -q && .venv/bin/ailib validate
  ```
  (create the venv with `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`).
- When a plugin's skills/agents change, bump its `version` in `plugins/<plugin>/.claude-plugin/plugin.json`.
- Don't put anything except `plugin.json` inside a plugin's `.claude-plugin/` directory.
