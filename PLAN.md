# Implementation Plan: Recovery, Hardening & Codebase Cleanup

> [!NOTE]
> This file is not a canonical source for current SilverPilot phase status.
> For canonical information, please see [docs/PHASE_PLAN.md](file:///Users/boe747/SilverPilot/docs/PHASE_PLAN.md).

Bu plan, SilverPilot projesinde Faz 1'den Faz 5'e kadar yapılan tüm değişiklikleri gözden geçirerek; gereksiz if-else yapılarını temizlemeyi, biriken subagent git branch'lerini silmeyi, testleri genişletip güçlendirmeyi ve projenin genel durumuna ait nihai bir rapor hazırlamayı hedefler.

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:** [docs/RISK_POLICY.md](file:///Users/boe747/SilverPilot/docs/RISK_POLICY.md) (Tüm risk denetimleri), [docs/DATA_CONTRACTS.md](file:///Users/boe747/SilverPilot/docs/DATA_CONTRACTS.md) (Veri şemaları ve entegrasyonlar)
- **Etkilenen Dosyalar:** Faz 1'den bu yana değiştirilen tüm Python kodları ve test dosyaları.

---

## 🛠️ Fazlar ve Görev Listesi

### **Faz 1: Git Branch Temizliği (Branch Cleanup)**
- [x] Local repository'de bulunan ve artık kullanılmayan tüm `subagent-*` branch'lerini tespit edip silmek. (Ajan: `scout-agent` & shell)
- [x] Remote (origin) üzerindeki eski `subagent-*` branch'lerini silmek ve git repository görünümünü sadeleştirmek.
- *DoD (Tamamlanma Tanımı):* `git branch -a | grep subagent` komutunun hiçbir çıktı üretmemesi.

---

### **Faz 2: Codebase If-Else Denetimi ve Refaktörü (If-Else Audit)**
- [x] **`hermes.py`**: Ağırlık seçimi, sentiment sayısal dönüşümü ve markdown LLM parse logic'lerindeki `if-else` / `if-elif-else` yapılarını sözlük (dict.get) ve regex/partition tabanlı yapılarla sadeleştirmek. (Ajan: `code-archaeologist`)
- [x] **`strategy.py`**: AutoRegime and MACD stratejilerindeki oylama if-else bloklarını mantıksal operatörler ve erken dönüşlerle (guard clauses) basitleştirmek.
- [x] **`auto_trader.py`**: Router ve context hazırlama adımlarındaki if-else kontrollerini optimize etmek.
- [x] Diğer değiştirilen dosyalardaki (`service.py` [collectors], `entities.py`, `service.py` [paper_trading], `service.py` [risk], `cost_models.py`, `seed.py`) if-else bloklarını tek tek inceleyerek gereksiz, günü kurtaran veya hardcode edilmiş koşul yapılarını refaktör etmek.
- *DoD:* Tüm refaktör edilen dosyaların Ruff format ve check aşamalarını sıfır hata ile geçmesi.

---

### **Faz 3: Testlerin Genişletilmesi ve Sıkılaştırılması (Test Hardening)**
- [x] Yeni `macd` ve `auto` stratejilerinin tüm sınır değerlerini, veri eksikliği durumlarını ve rejim geçişlerini kapsayan ek eleyici test senaryolarını eklemek. (Ajan: `quality-engineer`)
- [x] Dinamik `AssetConversion` lookup mekanizması ve SaaS modelleri (`providers`, `tenant_portfolios`, `strategy_parameters`) için hata durumlarını (db bağlantısı kesilmesi, eksik seeder verisi fallback'i) simüle eden negatif testler yazmak.
- *DoD:* `pytest` komutu çalıştırıldığında tüm testlerin sıfır hata ile yeşil yanması ve test coverage oranının korunması.

---

### **Faz 4: Kapanış, Nihai Raporlama ve Git Commit/Push**
- [x] Plan implementasyonunun başlangıcından (commit `5363ccd`) bu yana yapılan tüm değişiklikleri, güncellenen dosyaları ve commit özetlerini içeren, Codex'in kolayca okuyup doğrulayabileceği detaylı bir **Stabilization & Recovery Report** hazırlamak. (Ajan: `project-planner`)
- [x] `safety-gatekeeper` onayını alarak tüm değişiklikleri conventionally commit'leyip push'lamak.
- *DoD:* Nihai raporun markdown formatında oluşturulması ve repository'nin temiz şekilde push edilmesi.