# Agent Rules

## Context Loading Protocol

Agents should read only the minimum required context:

- `memory-bank/projectbrief.md`
- `memory-bank/activeContext.md`
- `memory-bank/progress.md`
- `memory-bank/agentRules.md`
- `docs/ARCHITECTURE.md`
- last relevant section of `docs/WORKLOG.md`
- relevant files under `docs/` or `agents/` only when needed

Do not read the whole repository by default. Search first, then open the smallest relevant file range.

## Work Limits

- Read only files needed for the task.
- Change at most one phase at a time.
- Prefer editing canonical docs over creating new markdown files.
- Keep `activeContext.md` under 120 lines.
- Keep `progress.md` under 200 lines.
- Keep each `agents/*.md` file under 100 lines.
- Keep `WORKLOG.md` entries compact.
- Keep one task scoped to a small deliverable.
- Do not combine backend, LLM, dashboard, and ML work in one task.

## Task Protocol

Every implementation task should state:

- scope.
- files likely to change.
- explicit exclusions.
- definition of done.
- validation command or manual validation.

Example scope:

```text
Phase 1: add FastAPI app, PostgreSQL config, and /health.
Exclude paper trading, LLM, dashboard, and ML.
Done when tests pass and /health returns 200.
```

## Markdown Creation Rule

Creating new markdown files is forbidden unless the user explicitly asks or the existing canonical files cannot hold the information.

Use the canonical homes:

- roadmap: `docs/ROADMAP.md`
- architecture: `docs/ARCHITECTURE.md`
- decisions: `docs/DECISIONS.md`
- data shapes: `docs/DATA_CONTRACTS.md`
- risk behavior: `docs/RISK_POLICY.md`
- work log: `docs/WORKLOG.md`
- active state: `memory-bank/activeContext.md`
- agent roles: `agents/*.md`

## Definition of Done

A task is not complete until:

- relevant tests or validation are run.
- secret scan is considered for touched files.
- no real-money or bank automation path is introduced.
- canonical docs are updated when behavior changes.
- `docs/WORKLOG.md` records the verified outcome.

## VPS Rules

- For VPS tasks, use SSH alias `silverpilot-vps` when the user explicitly asks for server-side work.
- Do not ask for the private key if `ssh silverpilot-vps` works.
- Do not print private SSH config contents unless the user explicitly asks.
- Do not read `.env.production` unless the task specifically requires validating environment variable names.
- Never print secret values.
- Before changing VPS files, run a safe status check first.
- Do not install random tools or services on the VPS without a clear reason.

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
16. Keep runtime data out of markdown.
17. Keep price history, paper trades, agent outputs, reports, and LLM logs in the database once implemented.
18. Ensure core backend behavior works without LLM availability.
19. Do not enable paid market-data APIs during MVP.
20. Public-source collectors must use polite polling and must fail visibly when parsing fails.
21. Do not bypass login, captcha, paywall, anti-bot controls, robots restrictions, or private endpoints.
