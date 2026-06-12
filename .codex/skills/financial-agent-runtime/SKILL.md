---
name: "financial-agent-runtime"
description: "Codex-local skill bundle for runtime financial/data agent boundaries and LLM budget guardrails."
---

# Financial Agent Runtime

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Do not confuse `apps/api/app/agents/` runtime financial/data agents with `.codex/agents` coding subagents.
- Runtime agents must use FastAPI HTTP boundaries, not direct production database access.
- Do not create or modify root `/agents`; runtime-agent changes belong under `apps/api/app/agents/` unless a future task changes the app layout.
- Do not expose tokens, LLM credentials, budget settings, or production connection strings.
- Preserve paper-trading and no-real-money boundaries.

## Evidence
- Runtime agent path `apps/api/app/agents/` inspected.
- API boundary used.
- Budget/risk guardrail preserved.
