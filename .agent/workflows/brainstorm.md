---
description: Structured brainstorming for projects and features. Explores multiple options before implementation.
---

# /brainstorm - Structured Idea Exploration

## Arguments
- `topic` (required): The topic or architecture decision to brainstorm.

---


## Purpose

This command activates BRAINSTORM mode for structured idea exploration. Use when you need to explore options before committing to an implementation.

---

## Behavior

When `/brainstorm` is triggered:

1. **Understand the goal**
   - What problem are we solving?
   - Who is the user?
   - What constraints exist?

2. **Generate options**
   - Provide at least 3 different approaches
   - Each with pros and cons
   - Consider unconventional solutions

3. **Compare and recommend**
   - Summarize tradeoffs
   - Give a recommendation with reasoning

---

## Output Format

```markdown
## 🧠 Brainstorm: [Topic]

### Context
[Brief problem statement]

---

### Option A: [Name]
[Description]

✅ **Pros:**
- [benefit 1]
- [benefit 2]

❌ **Cons:**
- [drawback 1]

📊 **Effort:** Low | Medium | High

---

### Option B: [Name]
[Description]

✅ **Pros:**
- [benefit 1]

❌ **Cons:**
- [drawback 1]
- [drawback 2]

📊 **Effort:** Low | Medium | High

---

### Option C: [Name]
[Description]

✅ **Pros:**
- [benefit 1]

❌ **Cons:**
- [drawback 1]

📊 **Effort:** Low | Medium | High

---

## 💡 Recommendation

**Option [X]** because [reasoning].

What direction would you like to explore?
```

---

## Examples

```
/brainstorm authentication system
/brainstorm state management for complex form
/brainstorm database schema for social app
/brainstorm caching strategy
```

---

## Key Principles

- **No code** - this is about ideas, not implementation.
- **Visual when helpful** - use diagrams for architecture.
- **Honest tradeoffs** - don't hide complexity.
- **Respect Core Constraints (Zorunlu)** - Alternatifler üretilirken mutlaka **[project-conventions.md](file:///Users/boe747/SilverPilot/.agent/memory/project-conventions.md)** (proje anayasası) ve **[tech-decisions.md](file:///Users/boe747/SilverPilot/.agent/memory/tech-decisions.md)** (teknik kısıtlar) sınırları denetlenmelidir. Bu sınırları (örn. PostgreSQL veritabanı tercihi, limitlemeler) aşan öneriler yapılamaz.
- **Role Assignment** - Bu iş akışı, projenin lider kodlama rolleri olan `project-planner` veya `backend-architect` tarafından mimari ikilemleri aşmak için tetiklenir.
- **Uzman Katılımı (Specialist Participation)** - Tartışılan fikrin odağına göre ilgili uzman ajan sürece zorunlu olarak dahil edilmeli ve kendi uzmanlık alanında alternatifler üretmelidir:
  - **Veri / Boru Hatları / Risk Analizleri:** `data-engineer`
  - **Eski Kod / Entegrasyon / Modernizasyon:** `archaeologist-agent`
  - **Güvenlik / Yetkilendirme / Secrets:** `security-auditor`
  - **Hata Analizleri ve Kök Neden:** `debugger-agent`
  - **Test Edilebilirlik ve DevOps:** `quality-engineer`
- **Defer to user** - present options, let them decide.
