# Runtime Agent Safety Audit Workflow

Use for runtime financial/data agents under `apps/api/app/agents/`, LLM gateway
usage, token boundaries, paper-trading safety, and agent API authorization.

## Required Preflight

- Scout first: map runtime agent files, API routes, service calls, token checks,
  LLM gateway usage, risk policy calls, and tests.
- Load `.codex/skills/financial-agent-runtime/SKILL.md`.
- Load `.codex/skills/llm-observability-budget/SKILL.md` when LLM calls,
  traces, tokens, prompts, or costs are in scope.
- Load `.codex/skills/financial-risk-regression/SKILL.md` when paper-trading
  or risk policy behavior is in scope.

## Audit Checklist

- Runtime agents use API/service boundaries rather than direct production DB
  mutation.
- Agent endpoints enforce expected token or authorization checks.
- LLM prompts, responses, traces, and errors do not expose secrets or raw
  credentials.
- Token and cost budget handling is observable and bounded.
- Paper-trading remains advisory/simulation-only unless explicitly approved by
  a future task.
- Risk policy checks are preserved before any trading recommendation or action.

## Output

- Runtime agents and routes inspected.
- Token/auth boundary status.
- LLM budget/observability status.
- Paper-trading and risk-policy status.
- Blockers and required verification.
