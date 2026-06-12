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

Every repo engineering task begins with `scout` preflight unless the request is
pure chat, a general explanation, or repo-external conversation. Use
micro-scout for narrow one/two-file work and full-scout for unclear, multi-file,
cross-subsystem, failure, architecture, security, database, or deploy-adjacent
work. Specialists consume the scout handoff before starting.

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

## 2.2 External Plugin Preference

When an installed `claude-code-workflows` plugin cleanly matches the task,
prefer that command surface before inventing a custom orchestration path.
Treat plugin workflows as accelerators, not authorities.

| Task class | Preferred plugin | Typical command |
| --- | --- | --- |
| Backend feature slice | `backend-development` | `/backend-development:feature-development` |
| Bug triage or unclear failure | `debugging-toolkit` | `/debugging-toolkit:smart-debug` |
| Regression or test expansion | `unit-testing` | `/unit-testing:test-generate` |
| Broad code review | `comprehensive-review` | `/comprehensive-review:full-review` |
| Migration-oriented change | `database-migrations` | `/database-migrations:sql-migrations` |
| Deploy gate or config audit | `deployment-validation` | `/deployment-validation:config-validate` |
| Security audit | `security-scanning` | `/security-scanning:security-hardening` |
| Agent/task optimization | `agent-orchestration` | `/agent-orchestration:multi-agent-optimize` |
| Context save/restore | `context-management` | `/context-management:context-save` or `/context-management:context-restore` |

Fallback rule:

- If the plugin path is too broad, too generic, or mismatched to SilverPilot's
  repo boundaries, stay on local `.codex` agents and skills.
- If a plugin implies multi-step autonomy that would exceed local approval or
  verification gates, collapse back to local orchestration.

## 2.5 Default Task Recipes

Use these recipes when the user request does not already force a narrower path.
The goal is to make agent spawning predictable instead of ad hoc.

### A. Small, low-risk implementation

Use when all are true:

- one or two files;
- no schema change;
- no deploy/CI/security boundary;
- no unclear failure path.

Route:

1. Run micro-scout: read `.codex/memory/codegraph.md`, run targeted `rg`, read only the needed ranges, and produce the context-handoff fields.
2. Stay in main context or use `implementation_worker`.
3. Use one verification step with `test_verifier` only if runtime behavior changed.

### B. Normal bug fix or feature slice

Use when the task touches several files, an execution path is unclear, or tests
must be added/updated.

Route:

1. Prefer the matching plugin surface first:
   `/backend-development:feature-development` for feature work or
   `/debugging-toolkit:smart-debug` for failure-heavy work.
2. Run full-scout and hand off RTK evidence, read ranges, do-not-reread notes, and recommended next agent.
3. `implementation_worker` for the patch.
4. `test_strategist` before broad new tests or shared behavior changes.
5. `test_verifier` after edits.

### C. Debugging / failing tests / runtime regressions

Use when the user reports a bug, stack trace, broken behavior, or failing CI.

Route:

1. Prefer `/debugging-toolkit:smart-debug` for first-pass narrowing.
2. Run micro-scout for obvious failures or full-scout when the failing path spans subsystems.
3. `troubleshooter` owns the task after consuming the scout handoff.
4. Spawn `db_investigator` if persistence, migration, query, or data shape is involved.
5. Spawn `test_verifier` after the fix.

### D. Architecture / design / refactor planning

Use when the user asks for a plan, tradeoff analysis, framework direction, or a
high-risk refactor.

Route:

1. Run full-scout and produce a context handoff with codegraph, canonical docs, files searched, ranges read, and risk notes.
2. `architect` owns the task after consuming the handoff.
3. Consider `/agent-orchestration:multi-agent-optimize` when the user is
   explicitly asking how agents, skills, or workflows should be coordinated.
4. Spawn `security_reviewer` for auth, secrets, CI permission, or prompt-injection surfaces.
5. Spawn `db_investigator` for schema or migration consequences.
6. Do not use `implementation_worker` until the design is accepted.

### E. Release and deployment work

Use when the user asks about commit, push, CI, release, deploy, smoke, or rollback.

Route:

1. Prefer `/deployment-validation:config-validate` for first-pass deploy checks.
2. Run full-scout for repo evidence relevant to the requested gate.
3. `git_guardian` for commit/push scope.
4. `ci_investigator` for red workflows or flaky CI.
5. `deploy_guardian` before deploy.
6. `rollback_planner` when deploy risk or migration risk exists.
7. `final_reviewer` before broad release claims.

## 3. Model Policy

- Mini models: read-heavy scouting, default database investigation, git checks, test execution summaries, and
  post-deploy evidence classification.
- Standard models: implementation, debugging, CI root-cause analysis, deploy
  planning, rollback planning, and test strategy.
- Strongest available model: security review, final review, architecture
  review for risk-sensitive changes, and decisions involving financial risk,
  auth, production deployment, or irreversible data effects.
- `db_investigator` defaults to token-efficient mini/medium for static schema and query mapping. Escalate high-risk migration, irreversible data-loss, or production data decisions to `architect` or strongest available review.
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

### Scout Handoff Gate

`implementation_worker`, `troubleshooter`, `architect`, `test_strategist`,
`security_reviewer`, and `db_investigator` must not start repo engineering work
without a scout handoff, except for pure chat or repo-external explanation. The
handoff format is defined in `.codex/workflows/context-handoff.md`.

### Spawn Rules

After scout preflight, additional subagent spawning is allowed only when at
least one of these is true:

- the task spans more than one subsystem;
- the first-pass file map is unclear;
- a specialist review changes the risk class;
- verification would otherwise drown the main context.

Do not spawn specialists only because they exist. Default to the minimum number
of agents that preserve clarity.

### Fan-out Limits

- Default maximum parallel specialists for a normal task: 2.
- Default maximum total specialist roles in one task: 4.
- For small tasks, prefer 0 or 1 spawned agent.
- If a task needs more than 4 distinct roles, pause and collapse the plan into
  phases instead of expanding fan-out.

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

### Ownership Rules

- Only one write-capable owner at a time: `implementation_worker`,
  `troubleshooter`, or the main coding context.
- Read-only reviewers may run before or after implementation, but they do not
  take over write ownership unless the task is explicitly reframed.
- `test_verifier` verifies; it does not redesign.
- `architect` plans; it does not patch.
- `security_reviewer`, `git_guardian`, `deploy_guardian`, and
  `final_reviewer` are gatekeepers, not implementers.

## 5. RTK Protocol

RTK means targeted reading and context conservation:

1. Start with `.codex/memory/codegraph.md` and relevant canonical docs named by that index.
2. Use `rg --files` or `rg -n` to locate exact files, symbols, tests,
   routes, and configs.
3. Read only targeted line ranges with `sed -n 'start,endp'`, `nl -ba`, or an
   equivalent range-limited read.
4. Avoid whole-file reads for large files unless the file is short or the whole
   structure is directly relevant.
5. Prefer existing architecture, memory, and workflow notes before reverse
   engineering already-documented behavior.
6. Summarize subagent findings into concrete paths, line references, and next
   actions. Do not paste raw bulk logs into the main context.
7. Reuse prior search results in the same turn instead of repeating broad
   searches.
8. For long tasks or context compression, carry only short path/line/fact/risk summaries, not raw file dumps or command logs.

## 6. Implementation Gate

Before any specialist output or file edit:

1. Run skill preflight: read the relevant `.codex/skills/<skill-name>/SKILL.md`
   files for the selected agent and task.
2. Include `Loaded skills: ...` in the agent output, or `Loaded skills: none`
   with a short reason when no skill applies.
3. Treat skill commands as constrained by the agent sandbox. Read-only agents
   may inspect files and propose commands, but they must not execute write,
   migration, deploy, rollback, or production/staging commands.
4. After first-pass repository inspection, ask the user for clarification when
   unresolved ambiguity would materially change scope, risk, target files,
   database/deploy behavior, or approval requirements.
5. If a read-only agent needs a persistent markdown/report change, it proposes
   the exact change and hands write ownership to the main context,
   `implementation_worker`, or `troubleshooter`.

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
