# Codegraph Maintenance Workflow

`.codex/memory/codegraph.md` is the local, lightweight CodeGraph substitute for
Codex tasks. Do not install an external CodeGraph dependency for this framework.

## When To Update

Update the codegraph when a change moves or adds:

- application entrypoints;
- API routers, service boundaries, or runtime agents;
- collector, ML, backtest, risk, or dashboard subsystem roots;
- test roots or verification commands;
- canonical architecture, contract, phase-plan, or deployment docs;
- Codex skill routing or workflow routing.

## Update Rules

- Keep the file short and scannable.
- Prefer stable paths over exhaustive file lists.
- Include only facts that help scout decide what to read first.
- Remove stale paths in the same change that introduces replacements.
- Do not duplicate full architecture docs; link to the canonical docs instead.

## Verification

After updating, run:

```bash
python3 .codex/scripts/verify-agent-framework.py
rg -n "codegraph|context-handoff" .codex
```
