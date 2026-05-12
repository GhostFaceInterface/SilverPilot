# Agent Rules

## Read First

Agents should read only the minimum required context:

- `memory-bank/projectbrief.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/agentRules.md`
- relevant files under `docs/` or `agents/`

## Limits

- Read only files needed for the task.
- Change at most one phase at a time.
- Prefer editing canonical docs over creating new markdown files.
- Keep `activeContext.md` under 120 lines.
- Keep each `agents/*.md` file under 100 lines.

## Safety

- No real-money trading.
- No bank automation.
- No secrets in code, docs, logs, or commits.
- LLM output must be schema-validated once LLM features exist.

