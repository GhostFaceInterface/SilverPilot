# Collector Pipeline Validation Workflow

Use for market/news/data collectors, source priority, freshness, parser
failures, free/public source policy, and ingestion regressions.

## Required Preflight

- Scout first: identify collector entrypoints, source clients, parser paths,
  freshness checks, tests, and docs.
- Load `.codex/skills/collector-data-pipeline/SKILL.md`.

## Validation Checklist

- Source priority is explicit and does not silently prefer paid/private sources.
- Public/free source assumptions are documented when required.
- Parser failures are observable and do not become false successful freshness.
- Freshness windows, retry/backoff, and stale-data handling are clear.
- Collector output schema matches downstream API, ML, and dashboard consumers.
- Tests cover at least one success path and one parser/freshness failure path
  when runtime behavior changes.

## Output

- Sources and collectors inspected.
- Freshness and parser evidence.
- Downstream consumers affected.
- Required tests or smoke checks.
- Residual data-quality risk.
