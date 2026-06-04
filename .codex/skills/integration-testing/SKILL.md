---
name: "integration-testing"
description: "Codex-local skill bundle for API, service, database, collector, dashboard, and pipeline integration checks."
---

# Integration Testing

This is a Codex-local skill bundle, not a guaranteed auto-discovered official Codex skill.

## Rules
- Test the real changed boundary.
- Prefer local/test databases and isolated fixtures.
- Do not use production/staging credentials or mutate production data.
- Verify serialization, persistence, service coordination, and dashboard/API contracts where relevant.

## SilverPilot Focus
- `/health`
- `/prices/latest`
- `/paper-trades/position`
- `/collectors/health`
- `/collectors/validation-gate`
- Trading/risk agent veto and paper-trading persistence paths.

## Evidence
- Endpoint/service path tested.
- Fixture or DB isolation used.
- PASS / FAIL / UNKNOWN classification.
