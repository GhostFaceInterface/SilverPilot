# Docs Consistency Workflow

Use when changing Codex framework docs, architecture docs, phase plans, runtime
contracts, README files, or worklog expectations.

## Required Preflight

- Scout first: map canonical docs and drift-prone references with `rg`.
- Load `.codex/skills/documentation-consistency/SKILL.md`.

## Checks

- `.codex/AGENTS.md`, `.codex/README.md`, relevant workflows, and agent TOMLs
  agree on agent routing and skill wiring.
- `docs/PHASE_PLAN.md`, architecture/contract/risk docs, README files, and
  worklogs do not contradict the changed behavior.
- Runtime agent path references point to `apps/api/app/agents/`.
- New markdown is justified; otherwise update an existing canonical doc.
- Verification commands are listed for framework-only changes.

## Output

- Docs searched.
- Contradictions fixed or intentionally left with reasons.
- Verification commands run.
- Remaining drift risk.
