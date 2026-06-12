---
name: "collector-data-pipeline"
description: "Codex-local skill bundle for collectors, source priority, freshness, parser failures, and public/free source policy."
---

# Collector Data Pipeline

This is a Codex-local skill bundle, not a guaranteed auto-discovered official
Codex skill.

## Rules

- Scout first: map collector entrypoints, source clients, parser code,
  freshness checks, downstream consumers, and tests.
- Preserve explicit source priority and public/free source constraints.
- Treat parser failures and stale data as observable failure states, not empty
  success.
- Do not add paid, private, credentialed, or network-dependent sources without
  explicit user approval.
- Do not print API keys, cookies, or provider credentials.
- Keep retry, backoff, and freshness behavior bounded and testable.

## Evidence

- Sources and parser paths inspected.
- Freshness and stale-data behavior identified.
- Downstream API, ML, dashboard, or report consumers named.
- Tests or smoke checks proposed for success and failure paths.
