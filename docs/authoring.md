# Authoring skills and agents

Everything here is written once, in Claude Code plugin layout, and installed into GitHub Copilot repos by `ailib install`. `ailib validate` enforces the rules marked ✅.

## Where things go
```
plugins/<plugin>/
├── .claude-plugin/plugin.json      only this file inside .claude-plugin/ ✅
├── skills/<skill-name>/SKILL.md    + optional references/, templates/, scripts/
└── agents/<agent-name>.md
```
Register a new plugin in `.claude-plugin/marketplace.json` with `"source": "./plugins/<plugin>"` ✅.

## Skills (shared format: works as-is in Claude Code and Copilot)
```markdown
---
name: my-skill                 # lowercase-hyphen, ≤64 chars, = directory name ✅
description: What it does. Use when <situations that should trigger it>.   # ≤1024 chars ✅
---
# Instructions...
```
- **The description is the trigger.** Both tools only see name + description until the skill is needed. Say *what* and *when*, and include words the user would actually type ("RestAssured", "flaky", "bug report"). ✅ warns if there's no "Use when".
- **Keep `SKILL.md` short** (≤500 lines ✅, aim for 100–150). Put detail into `references/*.md`, runnable/copyable code into `templates/`, deterministic helpers into `scripts/`. Link them with relative links ✅ (checked for existence).
- Write instructions, not essays: checklists, rules, short snippets, "done" criteria.
- Tell the agent to **follow the target project's existing conventions first**.
- Don't pin library versions in snippets; tell the agent to reuse the project's versions or the latest stable.
- Skill names must be unique across the whole library ✅ (they're installed into one folder).

## Agents (Claude format, converted for Copilot)
```markdown
---
name: my-agent                  # = file name ✅
description: Role + what it produces. Use when <situations>.
tools: Read, Grep, Glob, Bash   # least privilege; omit = all tools
---
System prompt...
```
- Give each agent a single role, a process, and an explicit output format.
- Reviewers/planners: read-only tools (`Read, Grep, Glob`, plus `Bash` for `git diff` with a "read-only commands only" instruction).
- Refer to skills **by name in the body** ("use the `test-case-format` skill"). Don't use the Claude-only `skills:` frontmatter — Copilot ignores it.
- Only use tools that have a Copilot alias ✅ (warning otherwise):

| Claude | Copilot |
|---|---|
| Bash | execute |
| Read, NotebookRead | read |
| Edit, MultiEdit, Write, NotebookEdit | edit |
| Grep, Glob | search |
| Task, Agent | agent |
| WebSearch, WebFetch | web (not available in Copilot cloud agent) |
| TodoWrite | todo |

`model`, `permissionMode` and other Claude-only fields are dropped for Copilot.

## Versioning
Bump `version` in the plugin's `plugin.json` (semver ✅) whenever you change its skills/agents; Claude Code uses it to offer updates. Don't put `version` in the marketplace entry too (if you do, it must match ✅).

## Checklist for a new skill/agent
1. Create the files, run `ailib validate`.
2. Try it: Claude Code (`/reload-plugins`, then ask something that should trigger it) and Copilot (`ailib install --target <repo> --dry-run`, then install).
3. If it doesn't trigger, improve the description before the body.
