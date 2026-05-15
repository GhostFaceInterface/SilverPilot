# Agent Rules

## Context Loading Protocol

Agents should read only the minimum required context:

- `memory-bank/projectbrief.md`, `memory-bank/activeContext.md`, `memory-bank/progress.md`, `memory-bank/agentRules.md`.
- `docs/ARCHITECTURE.md`, last relevant `docs/WORKLOG.md` section, and relevant `docs/` or `agents/` files only when needed.

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

Every implementation task should state scope, likely changed files, explicit exclusions, definition of done, and validation command or manual validation.

## Markdown Creation Rule

Creating new markdown files is forbidden unless the user explicitly asks or the existing canonical files cannot hold the information.

Use canonical homes: roadmap in `docs/ROADMAP.md`, architecture in `docs/ARCHITECTURE.md`, decisions in `docs/DECISIONS.md`, data shapes in `docs/DATA_CONTRACTS.md`, risk behavior in `docs/RISK_POLICY.md`, work log in `docs/WORKLOG.md`, active state in `memory-bank/activeContext.md`, and agent roles in `agents/*.md`.

## Definition of Done

A task is not complete until relevant tests or validation run, secret scan is considered for touched files, no real-money or bank automation path is introduced, canonical docs are updated when behavior changes, and `docs/WORKLOG.md` records the verified outcome.

## VPS Rules

- For VPS tasks, use SSH alias `silverpilot-vps` when the user explicitly asks for server-side work.
- Do not ask for the private key if `ssh silverpilot-vps` works.
- Do not print private SSH config contents unless the user explicitly asks.
- Do not read `.env.production` unless the task specifically requires validating environment variable names.
- Never print secret values.
- Before changing VPS files, run a safe status check first.
- Do not install random tools or services on the VPS without a clear reason.

## CI/CD Rules

- Keep `.github/workflows/ci.yml` aligned with the current pytest, Docker Compose, migration, and VPS smoke commands.
- Do not put VPS host, user, SSH key, known hosts, API keys, or `.env.production` values in workflow files.
- VPS smoke/deploy jobs must stay manually triggered unless the user explicitly approves automatic deployment.
- If tests or collector commands change, update CI in the same task.

## OpenClaw Rules

- OpenClaw is mandatory for the agent layer once that phase starts.
- OpenClaw agents must obey backend-first architecture.
- OpenClaw agents cannot read `.env.production`, request or expose secrets, perform bank automation, or execute real-money operations.
- OpenClaw agents cannot install random ClawHub/community skills without explicit review.
- OpenClaw agents must use project-local SilverPilot skills.
- OpenClaw outputs must be structured where they feed backend workflows.
- OpenClaw agent activity must be auditable.

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
22. Use FRED as the first no-cost macro-series source when a key is configured; do not implement direct BLS before it is re-approved.
23. Treat Türkiye macro data as execution/risk context, not as a standalone global silver direction signal.
24. Use Phase 6.5 PostgreSQL runtime memory as the approved memory path when that phase starts.
25. Do not use Zep, Graphiti, Neo4j/FalkorDB, Cognee, LightRAG, Letta, or Mem0 as production memory without a new explicit decision.
26. Do not write secrets, raw payloads, full news dumps, full LLM traces, SSH details, API keys, or bank details into memory tables.
27. Use OpenClaw as the mandatory agent orchestration layer after its foundation phase starts, but never let it bypass deterministic backend risk, trading, or accounting decisions.
28. Do not allow OpenClaw to access production secrets, bank credentials, SSH private keys, real-money systems, or unreviewed third-party OpenClaw/ClawHub skills.
