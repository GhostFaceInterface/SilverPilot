---
name: "financial-agent-runtime"
description: "Codex-local skill bundle for runtime financial/data agent boundaries and LLM budget guardrails."
---

# Financial Agent Runtime

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Do not confuse root `/agents` runtime financial/data agents with `.codex/agents` coding subagents.
- Runtime agents must use FastAPI HTTP boundaries, not direct production database access.
- Do not modify root `/agents` unless the task explicitly requires runtime-agent changes.
- Do not expose tokens, LLM credentials, budget settings, or production connection strings.
- Preserve paper-trading and no-real-money boundaries.

## Evidence
- Runtime agent path inspected.
- API boundary used.
- Budget/risk guardrail preserved.
