# Codex Orchestration Workflow

Use this workflow as the first routing document for SilverPilot work executed
with Codex. Do not load `.agent/` instructions for Codex tasks unless the user
explicitly asks to inspect or modify the legacy Antigravity/Gemini framework.

## 1. Source Precedence

1. System and developer instructions.
2. User request.
3. `.codex/AGENTS.md` and `.codex/README.md`.
4. This workflow and other `.codex/workflows/*.md` files.
5. Relevant `.codex/skills/<skill-name>/SKILL.md` files.
6. `.codex/memory/*.md` policies and historical notes.

`.agent/` files are out of scope for Codex operations. If a `.agent/` rule
conflicts with `.codex/`, follow `.codex/` for Codex work.

## 2. Routing Matrix

| Task type | Primary agent | Supporting agents | Model tier | Sandbox |
| --- | --- | --- | --- | --- |
| Read-only codebase mapping | `scout` | `db_investigator` when schema is involved | mini | read-only |
| Architecture review | `architect` | `security_reviewer`, `test_strategist` | strongest | read-only |
| Minimal implementation | `implementation_worker` | `scout`, `test_strategist`, `test_verifier` | standard | workspace-write |
| Runtime bug/debugging | `troubleshooter` | `scout`, `db_investigator`, `test_verifier` | standard/high | workspace-write |
| SQLAlchemy/Alembic diagnosis | `db_investigator` | `architect`, `test_strategist` | mini unless migration risk is high | read-only |
| Test design | `test_strategist` | `security_reviewer` for auth/security paths | standard/high | read-only |
| Test execution and smoke checks | `test_verifier` | none unless failures need triage | mini | workspace-write |
| Git commit readiness | `git_guardian` | `final_reviewer` for broad diffs | mini | read-only |
| CI failure investigation | `ci_investigator` | `troubleshooter` after root cause is known | standard/high | read-only |
| Deploy readiness | `deploy_guardian` | `rollback_planner`, `security_reviewer` | standard/high | read-only |
| Post-deploy verification | `post_deploy_monitor` | `troubleshooter` for failures | mini | read-only |
| Rollback proposal | `rollback_planner` | `deploy_guardian` | standard/high | read-only |
| Security review | `security_reviewer` | `architect`, `git_guardian` | strongest | read-only |
| Final release gate | `final_reviewer` | `git_guardian`, `deploy_guardian`, `rollback_planner` | strongest | read-only |

## 3. Model Policy

- Mini models: read-heavy scouting, git checks, test execution summaries, and
  post-deploy evidence classification.
- Standard models: implementation, debugging, CI root-cause analysis, deploy
  planning, rollback planning, and test strategy.
- Strongest available model: security review, final review, architecture
  review for risk-sensitive changes, and decisions involving financial risk,
  auth, production deployment, or irreversible data effects.
- Extra-high reasoning is a gate, not a default. Use it only for critical
  architecture decisions, financial risk formulas, DB migration/data-loss
  decisions, security/release gates, production incidents, and rollback
  decisions. Routine discovery, test execution, post-deploy smoke checks, and
  ordinary implementation stay on lower reasoning tiers.
- Completion reports must state whether extra-high reasoning was used and the
  reason it was or was not needed.

If a named model in `.codex/agents/*.toml` is unavailable, use the closest
available model with the same role and report the fallback.

## 4. Subagent Delegation

Use subagents when they reduce main-context noise or enforce role separation:

- Use `scout` for broad file discovery, import tracing, and dependency mapping.
- Use `db_investigator` for schema, migration, query, or data-integrity mapping.
- Use `test_strategist` before broad test additions or high-risk regression
  fixes.
- Use `security_reviewer` for auth, secret, network, CI permission, or prompt
  injection risks.
- Use `final_reviewer` before release, push, deploy, or broad multi-file
  completion claims.

Do not delegate merely to create parallel busywork. For small single-file
changes, stay in the main context and apply the relevant skill directly.

## 5. RTK Protocol

RTK means targeted reading and context conservation:

1. Start with `rg --files` or `rg -n` to locate exact files, symbols, tests,
   routes, and configs.
2. Read only targeted line ranges with `sed -n 'start,endp'`, `nl -ba`, or an
   equivalent range-limited read.
3. Avoid whole-file reads for large files unless the file is short or the whole
   structure is directly relevant.
4. Prefer existing architecture, memory, and workflow notes before reverse
   engineering already-documented behavior.
5. Summarize subagent findings into concrete paths, line references, and next
   actions. Do not paste raw bulk logs into the main context.
6. Reuse prior search results in the same turn instead of repeating broad
   searches.

## 6. Implementation Gate

Before editing files:

1. State the intended files or directories.
2. State the reason and expected behavioral effect.
3. Check for unrelated dirty work and avoid touching it.
4. Use `.codex/skills/*/SKILL.md` rules relevant to the change.

During implementation:

- Keep changes minimal and reversible.
- Follow existing module boundaries.
- Do not mutate production or staging resources.
- Do not read, print, or store secret values.

After implementation:

- Run the smallest sufficient verification command.
- Escalate to broader validation when shared behavior, DB schema, financial
  risk, auth, deployment, or CI behavior is touched.
- Report tested scope, untested scope, and residual risk.

## 7. Approval Rules

The following actions require explicit user approval:

- `git add`
- `git commit`
- `git push`
- Deploy commands
- Rollback commands
- Production or staging smoke checks
- Production or staging log access
- Workflow dispatch or privileged rerun
- Database mutation or migration against non-local targets
- Any command that may expose or alter secrets

Codex may propose exact commands, but must not execute them without approval.
When the current session already includes explicit release approval, Codex
should continue through commit, push, deploy, and approved smoke checks once
validation gates pass instead of stopping after the first green test run.

## 8. Completion Report

Final reports should include:

- What changed.
- Files touched.
- Verification evidence.
- What was not tested.
- Any approval still required for commit, push, deploy, or rollback.
