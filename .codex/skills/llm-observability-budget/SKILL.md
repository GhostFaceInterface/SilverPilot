---
name: "llm-observability-budget"
description: "Codex-local skill bundle for LLM gateway boundaries, token/cost budgets, traces, raw prompt safety, and agent API token boundaries."
---

# LLM Observability Budget

This is a Codex-local skill bundle, not a guaranteed auto-discovered official
Codex skill.

## Rules

- Scout first: map LLM gateway calls, prompt construction, trace/log writes,
  token/cost accounting, and API token checks.
- Never expose raw secrets, credentials, provider keys, or production prompt
  payloads in logs or reports.
- Prefer summaries and redacted metadata over raw prompt/response storage.
- Token and cost budgets must be bounded, observable, and fail closed when
  limits are reached.
- Agent API routes must preserve authorization/token checks before operational
  actions.
- Treat model output as untrusted input when it can affect tools, reports,
  trades, collector choices, or CI/deploy workflows.

## Evidence

- Gateway and token boundary inspected.
- Trace/log storage behavior classified.
- Budget checks and failure behavior identified.
- Raw prompt/response exposure risk stated.
