# Implementation Plan: Antigravity Awesome Skills (V11.8.0) Integration & Hardening

Bu plan, `https://github.com/sickn33/antigravity-awesome-skills` (V11.8.0) reposunda sunulan 1,480+ endüstri standardı agentic skill'i (beceriyi), modern workflow yapılarını ve gelişmiş orkestrasyon pratiklerini SilverPilot projesinin mevcut `.agent/` dizini altındaki ajan framework'üne entegre ederek, projedeki geliştirici yapay zeka asistan mimarisini maksimum güce ve derinliğe ulaştırmayı hedefler.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** `.agent/GEMINI.md` (Temel anayasa kuralları), `.agent/workflows/orchestrate.md` (Çoklu ajan orkestrasyonu).
- **Etkilenen Dizinler:**
  - `.agent/skills/` (Mevcut 7 becerinin güncellenmesi ve 1,480+ havuzdan kritik olanların eklenmesi)
  - `.agent/agents/` (Özel uzman ajanların yeni becerilere erişim sağlayacak şekilde güncellenmesi)
  - `.agent/workflows/` (İş akışı şablonlarının modern orkestrasyon desenleriyle zenginleştirilmesi)
- **Risk Faktörü (Context Overload):** 1,480+ becerinin tamamının kontrolsüz şekilde projeye yüklenmesi, LLM bağlam limitinin (context limit) aşılmasına ("Agent Overload") ve asistanın yavaşlamasına neden olabilir. Bu nedenle kurulum **seçici (selective/curated) filtreleme** protokolüyle gerçekleştirilecektir.

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Altyapı Hazırlığı ve NPX Kurulumu**
  - [x] Node.js/NPX ortamının kontrol edilmesi.
  - [x] `antigravity-awesome-skills` kütüphanesinin yerel bir test dizinine kurulması veya CLI parametrelerinin incelenmesi.
  - *Ajan:* `scout-agent`, `project-planner`
  - *DoD (Tamamlanma Tanımı):* `npx antigravity-awesome-skills --help` komutunun başarıyla çalışması ve çıktı vermesi.

- `[x]` **Faz 2: Seçici Beceri Entegrasyonu (Selective Skill Set Install)**
  - [x] Projeye uygun kritik kategorilerin belirlenmesi (Örn: `development, backend, testing, security, observability`).
  - [x] `npx antigravity-awesome-skills --path .agent/skills --category development,backend,testing,security,observability --risk safe,none` komutu veya özelleştirilmiş kurulum scripti kullanılarak hedeflenen becerilerin `.agent/skills/` altına yerleştirilmesi.
  - [x] Çakışan veya tekrarlanan eski beceri dosyalarının temizlenmesi veya birleştirilmesi.
  - *Ajan:* `scout-agent`, `archaeologist-agent`
  - *DoD:* `.agent/skills/` dizini altında yeni ve gelişmiş beceri dosyalarının (`SKILL.md` ve ilgili YAML manifestleri) doğrulanması.

- `[x]` **Faz 3: Ajan Rollerinin (Agent Personas) Yeni Becerilerle Güçlendirilmesi**
  - [x] `.agent/agents/` altındaki 9 uzman ajanın (örneğin `backend-architect.md`, `data-engineer.md`, `security-auditor.md`) yeni eklenen `@skill-id` becerilerini tanıp kullanabilmesi için sistem promptlarının ve yetki tanımlarının güncellenmesi.
  - *Ajan:* `backend-architect`, `project-planner`
  - *DoD:* Ajan dosyalarının başarıyla güncellenmesi ve `safety-gatekeeper` tarafından statik doğrulamanın onaylanması.

- `[x]` **Faz 4: Gelişmiş Workflows ve Orkestrasyon Adaptasyonu**
  - [x] `antigravity-awesome-skills` içerisindeki modern multi-agent ve DDD (Domain-Driven Design) odaklı workflow şablonlarının incelenmesi.
  - [x] Projedeki `.agent/workflows/orchestrate.md` ve `.agent/workflows/plan.md` dosyalarının bu yeni yeteneklerle güncellenmesi.
  - *Ajan:* `project-planner`, `backend-architect`
  - *DoD:* `/orchestrate` ve `/plan` akışlarının yeni becerilerle tam uyumlu çalıştığının gösterilmesi.

- `[x]` **Faz 5: Kalite Kontrol, Doğrulama ve Sıkılaştırma**
  - [x] Yeni sistemin entegrasyon smoke testinin yapılması (Örn: asistanın yeni eklenen bir `@brainstorming` veya `@api-design` becerisini kullanarak çıktı üretmesi).
  - [x] `safety-gatekeeper` tarafından tüm `.agent/` klasörünün statik analizi.
  - *Ajan:* `quality-engineer`, `safety-gatekeeper`
  - *DoD:* Tüm sistemin hatasız entegre olması ve `git status` üzerinde temiz bir çalışma alanı sağlanması.

---

## ❓ Açık Sorular

> [!IMPORTANT]
> 1. **Beceri Seçimi (Curated vs Full):** 1,480+ becerinin tamamı yerine projenize en uygun olan **`development, backend, testing, security`** ve **`observability`** odaklı bir "Curated Bundle" kurmayı öneriyoruz. Bu seçici kurulum yaklaşımını onaylıyor musunuz yoksa tam paketi mi kurmak istersiniz?
> 2. **Mevcut Becerilerin Korunması:** Projede halihazırda bulunan 7 özel beceri dosyası (`fastapi.md`, `sqlalchemy-alembic.md` vb.) oldukça optimize edilmiştir. Yeni entegrasyonda bu dosyaları tamamen silmek yerine, yeni gelen küresel becerilerle **harmanlayarak (merge)** korumayı öneriyoruz. Bu konuda tercihiniz nedir?
> 3. **Model Geçiş Protokolü:** Bu planın uygulanması aşamasında, karmaşık kod yazımları ve entegrasyon doğruluk incelemeleri için **Gemini 3.5 Pro** modeline geçmeyi kabul ediyor musunuz?
