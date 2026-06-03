# Codex Architectural Decisions Log

## 📅 Decisions

### 1. Codex Workspace Isolation
- **Date:** 2026-06-03
- **Decision:** Establish `.codex/` as the sole home for Codex instructions, agents, and configs.
- **Rationale:** To prevent root-level clutter, namespace collisions, and maintain clean boundaries between Antigravity (`.agent/`), runtime agents (`agents/`), and Codex.

### 2. Tailored Model Cascading
- **Date:** 2026-06-03
- **Decision:** Assign subagents to model tiers dynamically:
  - Scouting / mapping: `gpt-5.4-mini`
  - Normal coding / bugs: `gpt-5.5`
  - Cognitive audits / reviews: `gpt-5.5-pro`
- **Rationale:** Optimized reasoning quality and token economy balance.

### 3. Read-Only Default Database Access
- **Date:** 2026-06-03
- **Decision:** Enforce read-only database connections for Codex diagnostic scripts, except for manual critical fixes explicitly approved by the user.
- **Rationale:** To protect simulation data integrity and prevent unwanted state mutations during testing.
