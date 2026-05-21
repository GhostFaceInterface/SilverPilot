# Concise Planning Skill

## 1. Purpose
Defines the standards for generating high-signal, actionable, and atomic developer implementation plans before writing any code in the SilverPilot project. Enforces small, single-responsibility phases to prevent developer mistakes.

## 2. Rules
- **Strictly No-Code:** The plan must describe architecture, files to be modified, and verification steps. It must never contain raw code snippets or implementation details.
- **Zorunlu Fazlandırma:** Large tasks must be broken down into sequential, atomic Phases (e.g., Phase 1: Database/Models, Phase 2: Core Logic, Phase 3: API Endpoints, Phase 4: Verification).
- **Clear Assignments:** Specify which developer agent (e.g., `backend-architect`, `data-engineer`, `quality-engineer`) is responsible for each phase.
- **Verb-First Actions:** Checklist items must start with explicit action verbs (e.g., "Create", "Modify", "Add", "Run").

## 3. Recommended Patterns
- Scan project context (`README.md`, `ROADMAP.md`, models, configurations) before detailing the plan.
- Ask at most 1–2 clarifying questions and only if truly blocking. Make safe assumptions for non-blocking details.
- Identify database migrations and backward compatibility concerns during Phase 1.
- Designate a machine-readable or manual verification command as the "Definition of Done" for each phase.

## 4. Anti-Patterns
- **Generic Steps:** Vague instructions like "implement business logic" without target files or exact behaviors.
- **Code Pollution:** Including code snippets in the plan itself, which clutters the plan and promotes copy-paste errors.
- **Skipping Verification:** Planning implementation without explicit test execution gates.

## 5. Checklist
- [ ] Is the plan divided into distinct, single-responsibility phases?
- [ ] Are all action items Verb-first?
- [ ] Are target files referenced by absolute paths or clear relative locations?
- [ ] Are specific developer agents assigned to each task?
- [ ] Does every phase have a clear verification step?

## 6. Example Guidance
```markdown
# Plan - Volatility Limit Risk Safeguard

Implement volatility threshold checks based on Yahoo Finance SI=F intraday global prices.

## Proposed Changes

### Component: Data & Collectors
- [NEW] `app/collectors/volatility.py` (Calculates standard deviation of last 24 hours of price snapshots).
- Assignee: `data-engineer`

### Component: Risk Engine
- [MODIFY] `app/services/risk.py` (Injects volatility check rules).
- Assignee: `backend-architect`

## Phases of Execution

### Phase 1: Volatility Calculator (Core Logic)
- Implement `calculate_volatility_24h` in `app/collectors/volatility.py`.
- **Verification:** Run unit tests for volatility calculations.

### Phase 2: Risk Rule Integration (Risk Engine)
- Update `app/services/risk.py` to trigger `calculate_volatility_24h` and return `VOLATILITY_TOO_HIGH` if threshold is breached.
- **Verification:** Mock price snapshots and trigger risk status endpoint.
```
