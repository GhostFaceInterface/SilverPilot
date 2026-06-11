# External Source Audit

Date checked: 2026-06-03

This audit records sources considered for the Codex-only verification and release framework. No external files were copied wholesale. Adoption signals are deliberately conservative; unverified star counts and "proven" claims are omitted.

## OpenAI Codex subagents documentation
- Source URL: https://developers.openai.com/codex/subagents
- Classification: official Codex documentation.
- Adoption signal: official OpenAI developer documentation.
- Adopted: project-scoped `.codex/agents/*.toml`, one agent per file, required `name`, `description`, and `developer_instructions`, narrow read-only reviewer roles.
- Rejected: broad write-capable reviewers and recursive uncontrolled delegation.
- Security concerns: agent fan-out, excessive permissions, and accidental write access.
- Final decision: adopted for custom agent compatibility.

## OpenAI Codex skills documentation
- Source URL: https://developers.openai.com/codex/skills
- Classification: official Codex documentation.
- Adoption signal: official OpenAI developer documentation.
- Adopted: directory-based skill bundle pattern centered on `SKILL.md`.
- Rejected: creating `.agents/skills` because the user boundary requires all Codex-specific framework files to stay under `.codex/`.
- Security concerns: skill packages can include scripts and references that must be audited before use.
- Final decision: adapted as `.codex/skills/<skill-name>/SKILL.md` local convention only. Official auto-discovery is not guaranteed within the `.codex/`-only boundary.

## OpenAI Codex config reference
- Source URL: https://developers.openai.com/codex/config-reference
- Classification: official Codex documentation.
- Adoption signal: official OpenAI developer documentation.
- Adopted: project-scoped `config.toml` without credentials.
- Rejected: provider auth, API keys, tokens, database passwords, or machine-specific auth settings in project config.
- Security concerns: config files can accidentally become credential stores.
- Final decision: adopted limited project-scoped settings only.

## OpenAI Codex GitHub Action documentation
- Source URL: https://developers.openai.com/codex/github-action
- Classification: official Codex documentation.
- Adoption signal: official OpenAI developer documentation.
- Adopted: CI monitoring and least-privilege review concepts.
- Rejected: adding or modifying a Codex GitHub Action workflow in this repository.
- Security concerns: AI agents running in CI can expose secrets or act on untrusted content.
- Final decision: used as risk-review input only.

## openai/codex-action security guidance
- Source URL: https://github.com/openai/codex-action/blob/main/docs/security.md
- Classification: official/community-adjacent OpenAI GitHub security guidance.
- Adoption signal: OpenAI-owned repository and security-focused documentation.
- Adopted: untrusted input rules, no secret printing, and caution around privileged CI agents.
- Rejected: privileged autonomous CI fixes and broad workflow permissions.
- Security concerns: prompt injection, unsafe shell handling, secret exposure, and excessive permissions.
- Final decision: adopted as a security constraint source.

## openai/skills repository
- Source URL: https://github.com/openai/skills
- Classification: official OpenAI examples/catalog.
- Adoption signal: OpenAI-owned repository.
- Adopted: focused skill bundle style and `SKILL.md` convention.
- Rejected: installing external skills or copying skill files into this repo.
- Security concerns: external skills can carry scripts, references, and supply-chain risk.
- Final decision: used as structural reference only.

## VoltAgent/awesome-codex-subagents
- Source URL: https://github.com/VoltAgent/awesome-codex-subagents
- Classification: community catalog.
- Adoption signal: community repository; adoption metrics were not directly re-verified in this hardening pass.
- Adopted: role coverage ideas such as CI investigator, git guardian, deploy guardian, and rollback planner.
- Rejected: copying agent definitions, installer flows, and broad autonomous execution roles.
- Security concerns: community agent instructions may request excessive permissions or unsafe autonomy.
- Final decision: cautiously adapted taxonomy ideas only.

## wshobson/agents marketplace
- Source URL: https://github.com/wshobson/agents
- Classification: community plugin marketplace for Codex/Claude-style workflows.
- Adoption signal: large public plugin catalog, explicit Codex marketplace support, modular installation model, and readable local plugin manifests.
- Adopted:
  - marketplace registration in local Codex home as `claude-code-workflows`;
  - installed plugins:
    - `developer-essentials`
    - `backend-development`
    - `agent-orchestration`
    - `comprehensive-review`
    - `database-migrations`
    - `deployment-validation`
    - `security-scanning`
    - `unit-testing`
    - `debugging-toolkit`
    - `context-management`
  - plugin-first routing guidance for recurring coding tasks.
- Rejected:
  - wholesale installation of the full marketplace;
  - opaque external plugins not needed for SilverPilot;
  - any plugin path that would bypass local approval, validation, or rollback gates.
- Security concerns:
  - community-maintained prompts and scripts may drift over time;
  - plugin workflows can encourage broader autonomy than SilverPilot allows;
  - marketplace updates may change behavior outside this repository's git history.
- Final decision: adopted as a constrained acceleration layer under `.codex` governance, with local policy remaining authoritative.

## Community Codex skills repositories
- Source URLs:
  - https://github.com/vadimcomanescu/codex-skills
  - https://github.com/proflead/codex-skills-library
- Classification: community examples.
- Adoption signal: community repositories; adoption metrics were not directly re-verified in this hardening pass.
- Adopted: small, focused local skill bundle style.
- Rejected: remote installers, `npx` installation flows, wholesale skill adoption, and automatic overwrites.
- Security concerns: remote installers and unreviewed skill scripts can create supply-chain risk.
- Final decision: low-weight reference only.

## Aikido PromptPwnd article
- Source URL: https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents
- Classification: security research/vendor article.
- Adoption signal: security analysis source; not Codex official documentation.
- Adopted: untrusted GitHub event content threat model for CI agents.
- Rejected: any workflow pattern that feeds issue/PR/comment content into privileged agent prompts without review.
- Security concerns: prompt injection through GitHub Actions context.
- Final decision: adopted as security risk input.

## Snyk ToxicSkills research
- Source URL: https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/
- Classification: security research/vendor article.
- Adoption signal: security analysis source; not Codex official documentation.
- Adopted: external skill audit checklist and rejection of unreviewed executable skill packages.
- Rejected: remote skill installers and unreviewed scripts.
- Security concerns: malicious skills, secret exfiltration, prompt injection, malware, and dependency risk.
- Final decision: adopted as supply-chain risk input.

## Academic agentic workflow and skill-risk papers
- Source URLs:
  - https://arxiv.org/abs/2605.07135
  - https://arxiv.org/abs/2601.10338
- Classification: academic/security research.
- Adoption signal: research papers; not official Codex documentation.
- Adopted: prompt-to-agent, prompt-to-script, and executable-skill threat models.
- Rejected: adding new automated taint-analysis tooling in this hardening pass.
- Security concerns: untrusted workflow inputs and vulnerable executable skill packages.
- Final decision: used as threat-model support only.

## mcp-postgres-secure
- Source URL: https://mcpservers.org/servers/pugltd/mcp-postgres-secure
- Classification: community MCP server for PostgreSQL access.
- Adoption signal: documented permission modes, with `readonly` as the default, SQL statement filtering, PostgreSQL read-only transactions in read-only mode, and env-locked connection behavior.
- Adopted: candidate for Codex-only database inspection in `readonly` mode with a separate `silverpilot_ai_ro` PostgreSQL role and SELECT-only grants.
- Rejected: `dml` and `full` modes, runtime trading pipeline use, production mutation, migration execution, and credentials in repo files.
- Security concerns: SQL classification is not a complete parser; least-privilege DB grants must be the final authority.
- Final decision: approved as a read-only Codex development/inspection candidate only.

## ThinAir Data
- Source URL: https://mcpservers.org/servers/thinairtelematics/thinair-data
- Classification: hosted/read-only multi-database MCP server.
- Adoption signal: documented read-only design, schema introspection, EXPLAIN/optimization, anomaly detection, PII scanning, and N+1 detection.
- Adopted: evaluation candidate for schema review, EXPLAIN, anomaly, PII, and N+1 audits against local or sanitized non-production databases.
- Rejected: direct production database connection, runtime trading pipeline use, and any workflow requiring DSN/API keys to be stored in this repository.
- Security concerns: hosted data-residency and DSN handling risk; connection registration happens at runtime.
- Final decision: evaluate only with sanitized/local data unless a separate production data-residency review approves otherwise.

## Finance MCP candidates
- Source URLs:
  - https://frankfurter.dev/mcp/
  - https://mcpservers.org/servers/fxmacrodata/fxmacrodata
  - https://mcpservers.org/servers/tickdb/tickdb-unified-realtime-marketdata-api
- Classification: finance/FX/market-data MCP candidates.
- Adoption signal: Frankfurter documents an official remote MCP server for current/historical FX rates; FXMacroData documents macro, FX, calendar, COT, and commodity data; TickDB documents broad market-data coverage across FX, precious metals, indices, stocks, and crypto.
- Adopted: reference-only Codex research candidates. Frankfurter may be used for FX reference checks; FXMacroData for macro/regime research; TickDB for broad market-data evaluation.
- Rejected: runtime price source, provider indicator source, trading execution source, broker/write access, and automatic strategy/risk inputs.
- Security concerns: external market-data quality, licensing, API-key handling, and accidental promotion from research to runtime decision source.
- Final decision: research-only; SilverPilot runtime indicators remain computed from canonical internal OHLC bars.

## Broker/trading-write MCPs
- Source URL: category-level rejection; no specific broker MCP adopted.
- Classification: broker, trading-write, SQL-write, DML, and full-access MCP tools.
- Adopted: none.
- Rejected: broker/trading-write MCPs, SQL DML/full-access MCPs, and any connector that can place orders or mutate production data.
- Security concerns: real-money execution, irreversible data mutation, and ambiguous paper/live account boundaries.
- Final decision: rejected until paper-only boundaries and explicit approval gates are independently designed and tested.
