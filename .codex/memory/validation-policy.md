# Validation Policy

Core rule: no verification, no completion.

## Validation levels
- Level 0: static sanity, syntax/import/lint where available, secret scan.
- Level 1: unit tests and reproduction tests.
- Level 2: integration tests for API, DB, collectors, dashboard, and pipeline boundaries.
- Level 3: runtime verification with Docker Compose, health checks, logs, and execution pipeline checks.
- Level 4: CI/CD status and failed job analysis.
- Level 5: post-deploy health/log/critical-flow verification.
- Level 6: release gate with final review, security review, rollback plan, and user approval.

## Required evidence
- Commands run.
- Exit status or pass/fail result.
- Scope covered.
- Scope not tested.
- Risk decision.

Assertions without command/log/test evidence are not completion evidence.
