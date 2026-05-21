---
description: Structured memory synchronization and learning persistence. Triggers when critical thresholds are reached or decisions are made.
---

# /remember - Memory Sync & Learning Persistence

$ARGUMENTS

---

## Purpose

Defines the system-wide memory synchronization and learning persistence process. Ensures that critical architectural decisions, recurring bug fixes, user preferences, and project milestones are recorded in the long-term developer memory (`.agent/memory/`) so that future agents do not lose context or repeat past mistakes.

---

## Trigger Thresholds

### 1. Manual Invocation
- Triggered by the user using `/remember [context]` to record a specific preference, convention, or technical decision.

### 2. Autonomous Invocation (Critical Thresholds)
Agents must autonomously run this workflow when:
- **Critical/Recurring Bug Solved (Feedback):** When resolving a logical bug, performance bottleneck, N+1 query, permission block, or state-management issue that could occur again.
- **Architectural/Stack Shift (Tech Decisions):** When deciding on third-party service integration details, database schemas, library configurations, or deployment paths.
- **User Preference Update (Preferences):** When the user explicitly states design style bounds (e.g. colors, library restrictions), coding styles, or preferred ways of executing tools.
- **Milestone Reached (Project History):** When completing a structured phase of a plan, releasing a feature, or completing successful verification tests on VPS.

---

## Behavior

When `/remember` is triggered:

1. **Classify and Locate Target Memory File**
   - **Feedback History (`.agent/memory/feedback-history.md`):** For past mistakes, bans, design constraints, library restrictions, and logic traps.
   - **Technical Stack Decisions (`.agent/memory/tech-decisions.md`):** For libraries, database config, external API limits, and architecture limits.
   - **User Preferences (`.agent/memory/user-preferences.md`):** For styling rules, default shell habits, preferred communication tone, and developer settings.
   - **Project Conventions (`.agent/memory/project-conventions.md`):** For file layouts, coding standards, naming rules, and directory structures.
   - **Project History (`.agent/memory/project-history.md`):** For milestones, deployment logs, past features completed, and version transitions.

2. **Formulate the Memory Entry**
   - Make it **action-oriented**, **clear**, and **concise**.
   - Always state the **Date**, the **Problem/Context**, and the **Decision/Action**.
   - Keep it short to conserve context tokens in future runs.

3. **Append or Update the Target Memory File**
   - Read the file using target line intervals if large, locate the logical section, and insert the structured entry.
   - Update the `updated` time-stamp in the file's frontmatter.
   - Update `updated` date in the central `MEMORY.md` index if necessary.

4. **Announce and Sync**
   - Report the update in the chat output using the standard format so that other agents in cascaded/nested contexts instantly align.

---

## Output Format

When updating memory, the agent must output a confirmation in the following format:

```markdown
### 🧠 Memory Synced: [/remember]

- **Memory Category:** [Feedback | Tech Decision | User Preference | Convention | History]
- **Target File:** [file basename](file:///absolute/path/to/memory/file)
- **Key Learning/Decision:**
  > [Concise, action-oriented 1-2 sentence rule/statement]
- **Context/Why:**
  [Brief reason behind this memory update]
```

---

## Examples

```
/remember user preferred sharp edges instead of rounded styling in Streamlit
/remember Kuveyt Turk scraper API has a daily limit of 100 requests; must cache price snapshots
/remember SQLAlchemy N+1 bug resolved in price aggregator by using selectinload on collector runs
```

---

## Key Principles

- **Conserve Context:** Never add verbose paragraphs to memory. Keep rules bulleted and bite-sized.
- **No Assumptions:** If you are unsure which category a memory fits, ask the user or default to `project-history.md`.
- **Zero Duplication:** Check existing memory files before writing to ensure you are not creating redundant entries.
