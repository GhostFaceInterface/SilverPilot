# SilverPilot Agent Framework Router

Bu dosya yalnizca framework secim yonlendiricisidir. Codex veya Antigravity
icin ayrintili ajan, skill, workflow ve model kurallari burada tutulmaz.

## Framework Secimi

- Codex ile calisirken kaynak dizin: `.codex/`
  - Ana index: `.codex/AGENTS.md`
  - Orkestrasyon: `.codex/workflows/codex-orchestration.md`
  - Agent tanimlari: `.codex/agents/*.toml`
  - Skill paketleri: `.codex/skills/<skill-name>/SKILL.md`
- Antigravity/Gemini ile calisirken kaynak dizin: `.agent/`
  - Ana governance: `.agent/GEMINI.md`
  - Agent tanimlari: `.agent/agents/*.md`
  - Skill ve workflow dosyalari: `.agent/skills/`, `.agent/workflows/`

## Catisma Kurali

- Codex oturumunda `.codex/` kurallari gecerlidir; `.agent/` otomatik
  yuklenmez.
- Antigravity/Gemini oturumunda `.agent/` kurallari gecerlidir; `.codex/`
  otomatik kaynak yapilmaz.
- Kullanici acikca iki framework'ten birini denetlemeyi veya tasimayi isterse,
  yalnizca o kapsamda diger dizin okunabilir.

## Runtime Agent Ayrimi

`/agents` uygulamanin runtime finansal/veri ajanlari icindir. `.codex/agents`
ve `.agent/agents` ise kodlama asistanina ait gelistirme/denetim ajanlaridir.
