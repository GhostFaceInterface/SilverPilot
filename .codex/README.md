# Codex War Room - Operational Guide

Welcome to the isolated SilverPilot Codex workspace. This directory is reserved exclusively for the OpenAI Codex environment. 

> [!WARNING]
> **Strict Isolation Policy:** 
> - All Codex configurations, playbooks, prompts, and utilities must live strictly within `.codex/`.
> - Do not modify or contaminate the Antigravity framework code or project-level root configurations like `AGENTS.md`.
> - Do not confuse Codex custom subagents with runtime financial/data agents located under `/agents`.

---

## 📂 Workspace Structure

- **`config.toml`**: Project-specific parameters (e.g., thread limits, sandbox modes).
- **`agents/`**: TOML configuration files defining Codex custom subagents.
- **`workflows/`**: Sequential operational playbooks for various incidents and audits.
- **`skills/`**: Prototypical coding practices, patterns, and framework rules.
- **`prompts/`**: Prepared templates for initial incident response and minimal code updates.
- **Shared Memory (`.agent/memory/`)**: Shared centralized developer decision logs, known risks, and recurring failure checklists (Single Source of Truth).
- **`scripts/`**: Controlled diagnostic and verification helper scripts.

---

## 🤖 Model Routing Protocol

To optimize costs and reasoning efficiency, subagents are mapped to model tiers depending on the complexity of their task:

| Model Tier | Model | Target Subagents | Role Description |
| :--- | :--- | :--- | :--- |
| **Scouting & Mapping** | `gpt-5.4-mini` | `scout`, `db-investigator`, `deployment-investigator`, `test-verifier` | Light repository exploration, directory mapping, schema inspection, and test log parsing. |
| **Normal Coding & Fixes** | `gpt-5.5` | `implementation-worker`, `troubleshooter` | Scoped code updates, debugging, regression fixing, and package management. |
| **High Cognitive Audits** | `gpt-5.5-pro` | `architect`, `security-reviewer`, `final-reviewer` | Architectural audits, zero-trust security checks, and final release validation. |

---

## 🛡️ Database Execution Policy

- By default, all database interactions by Codex agents must be **read-only** (e.g. running schema inspections or SELECT queries).
- In critical recovery scenarios where direct data mutation or migration is necessary, changes can be made **only** after presenting a clear impact analysis and obtaining **explicit user approval**.
- Utilize `python3 .codex/scripts/readonly-db-check.py` for safe introspective queries.

---

## 📖 How to Orchestrate

When responding to an incident or starting a task:
1. **Load Instructions:** Read this `README.md` first.
2. **First Pass:** Run a read-only diagnostics scan using the `scout` agent combined with the playbook `.codex/workflows/emergency-troubleshooting.md`.
3. **Analyze:** Check the relevant skill instructions under `.codex/skills/` (e.g., `fastapi-sqlalchemy.md`) to align on project coding patterns.
4. **Fix:** Use the `implementation-worker` or `troubleshooter` to write minimal, localized, and fully reversible patches.
5. **Verify:** Run the designated verification tests before finalizing.
