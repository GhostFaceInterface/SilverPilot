# Agent Rules

## Read First

Agents should read only the minimum required context:

- `memory-bank/projectbrief.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/agentRules.md`
- relevant files under `docs/` or `agents/`

## Work Limits

- Read only files needed for the task.
- Change at most one phase at a time.
- Prefer editing canonical docs over creating new markdown files.
- Keep `activeContext.md` under 120 lines.
- Keep `progress.md` under 200 lines.
- Keep each `agents/*.md` file under 100 lines.
- Keep `WORKLOG.md` entries compact.

## Hard Rules

1. Check current status before editing.
2. Read relevant files before changing them.
3. Do not create unnecessary files.
4. Do not duplicate canonical documentation.
5. Do not work outside the roadmap without an explicit request.
6. Do not write, log, or commit secrets.
7. Keep every change small and verifiable.
8. Run relevant validation after code changes.
9. Update `docs/WORKLOG.md` after meaningful verified changes.
10. Keep `memory-bank/activeContext.md` current.
11. Keep `memory-bank/progress.md` milestone-focused.
12. Check existing canonical docs before creating markdown.
13. Do not use LLM output without schema validation once agents exist.
14. Do not add real bank automation.
15. Do not add real-money execution.

