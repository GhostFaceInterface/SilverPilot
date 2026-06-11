# Implementation Plan: İzole Codex Ajan Yapısı ve Savaş Odası Kurulumu [TAMAMLANDI]

> [!WARNING]
> This file is an archive of the `.codex/` bootstrap effort. It is not a
> canonical source for current SilverPilot phase status, implementation order,
> or execution authority.
>
> Refer to `docs/PHASE_PLAN.md` for the live baseline.

Bu plan, SilverPilot projesinde Codex kullanımı için tamamen izole bir `.codex/` dizini oluşturmayı, Antigravity (`.agent/`) ve çalışma zamanı finansal ajanlarına (`agents/`) hiçbir şekilde dokunmadan Codex'in kendi kural, ajan, workflow, beceri ve yardımcı scriptlerini barındırmasını sağlar.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** Projenin anayasal güvenlik sınırları (TIER 0) korunmuştur. Codex sisteminin ana sisteme ve Antigravity yapısına sızması tamamen engellenmiştir.
- **Güvenli Erişim Sınırları:** Veri tabanı sorgulamalarında salt-okunur (read-only) güvenlik politikası uygulanacaktır.

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Çekirdek Yapılandırma ve Dokümantasyon (`.codex/`)**
  - `[x]` `.codex/config.toml` dosyasının oluşturulması (Ajan: `project-planner`)
  - `[x]` `.codex/README.md` kılavuzunun hazırlanması

- `[x]` **Faz 2: Codex Özel Custom Ajanlarının Kurulumu (`.codex/agents/`)**
  - `[x]` `scout.toml`, `architect.toml`, `troubleshooter.toml`, `db-investigator.toml` ve `implementation-worker.toml` dosyalarının oluşturulması (Ajan: `backend-architect`)

- `[x]` **Faz 3: Playbook ve Workflows (`.codex/workflows/`)**
  - `[x]` `emergency-troubleshooting.md`, `architecture-audit.md` ve `db-diagnosis.md` dosyalarının oluşturulması (Ajan: `backend-architect`)

- `[x]` **Faz 4: Codex Becerileri ve Prompt Şablonları (`.codex/skills/`, `.codex/prompts/`)**
  - `[x]` FastAPI/SQLAlchemy, Alembic, Streamlit, Docker ve risk politikası becerilerinin markdown olarak hazırlanması
  - `[x]` `incident-first-pass.md` ve `minimal-fix.md` şablonlarının oluşturulması (Ajan: `data-engineer`)

- `[x]` **Faz 5: Karar Kayıtları ve Salt-Okunur Script (`.codex/memory/`, `.codex/scripts/`)**
  - `[x]` `project-map.md`, `known-risks.md` ve `recurring-failures.md` bellek dosyalarının oluşturulması
  - `[x]` `.codex/scripts/readonly-db-check.py` salt-okunur veritabanı introspeksiyon scriptinin yazılması (Ajan: `backend-architect`)

---

## 📌 Onaylanan Kararlar (Socratic Gate)

> [!NOTE]
> 1. **Model Yönlendirme:** Model cascading şu şekilde netleştirilmiştir:
>    - Keşif/Tarama/Dosya Haritalama (`scout`, `db-investigator`, `deployment-investigator`, `test-verifier`): `gpt-5.4-mini`
>    - Normal Kodlama/Hata Ayıklama (`implementation-worker`, `troubleshooter`): `gpt-5.5`
>    - Ağır Muhakeme/Mimari/Risk/Final İnceleme (`architect`, `security-reviewer`, `final-reviewer`): `gpt-5.5-pro`
> 2. **Veritabanı Politikası:** Normal koşullarda işlemler salt-okunur (read-only) yürüyecektir. Ancak kritik hata durumlarında manuel düzeltmeler için kullanıcı onayına başvurularak yazma/değişiklik işlemleri yapılabilecektir.
