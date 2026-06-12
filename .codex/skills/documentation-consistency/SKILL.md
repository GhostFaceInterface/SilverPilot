---
name: "documentation-consistency"
description: "Codex-local skill bundle for docs/PHASE_PLAN.md, architecture/contracts/risk docs, README drift, and worklog expectations."
---

# Documentation Consistency

This is a Codex-local skill bundle, not a guaranteed auto-discovered official
Codex skill.

## Rules

- Scout first: use targeted `rg` to find duplicate policy, path, model, skill,
  workflow, and runtime-agent references.
- Prefer updating canonical docs over creating new markdown.
- Keep `.codex/AGENTS.md`, `.codex/README.md`, agent TOMLs, workflows, and the
  verifier in sync when changing Codex framework behavior.
- Check `docs/PHASE_PLAN.md`, architecture/contract/risk docs, README files, and
  worklogs when app-facing behavior changes.
- Runtime financial/data agents live under `apps/api/app/agents/`; do not refer
  to root `/agents` as an existing app path.
- Verification commands must be listed for framework-only changes.

## Evidence

- Drift-prone docs searched.
- Contradictions fixed or explicitly scoped out.
- Verification commands named.
