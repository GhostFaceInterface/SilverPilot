# Implementation Plan: CI/CD Optimization, Automatic VPS Deployment & Lint Validation Guards

Bu plan, **SilverPilot** projesinin GitHub Actions CI/CD hattındaki (`.github/workflows/ci.yml`) eksik kontrolleri (linter/format) tamamlamayı, VPS otomatik dağıtım adımlarında collector/dashboard profillerini aktif etmeyi ve kod kalitesini artırmak için mevcut statik analiz (ruff) hatalarını temizlemeyi hedefler.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar:**
  - *[.agent/GEMINI.md](file:///.agent/GEMINI.md)*: Güvenlik, test kararlılığı ve Socratic Gate protokollerine tam uyum sağlanacak.
  - *[.agent/skills/lint-and-validate.md](file:///.agent/skills/lint-and-validate.md)*: Kod kalitesi kontrol adımları yerel ve uzak testlerle desteklenecek.
- **Etkilenen Dosyalar:**
  - `.github/workflows/ci.yml` (CI/CD Tanımı)
  - Production ve test kodlarındaki linter (ruff) bulguları ve tanımsız değişken hataları içeren dosyalar.

---

## 🛠️ Fazlar ve Görev Listesi

### ⚙️ Faz 1: Çekirdek Kod Kalitesi & Linter (Ruff) Hatalarının Çözülmesi (Quality Guard)
*   **[ ]** **[service.py](file:///apps/api/app/collectors/service.py)** (Ajan: `backend-architect`):
    *   `ingest_global_price` ve `ingest_bank_price` içindeki erişilemez/kopyalanmış `collector_name == "yahoo_usd_try"` blokları (ve tanımsız `rate` hataları) temizlenecek.
*   **[ ]** **[public_sources.py](file:///apps/api/app/collectors/public_sources.py)** (Ajan: `backend-architect`):
    *   Sınıf tanımından sonra yazılmış olan ve `E402` hatası veren modül seviyesi importlar dosyanın en üstüne taşınacak.
*   **[ ]** **[inference.py](file:///apps/api/app/ml/inference.py)** (Ajan: `data-engineer`):
    *   Kullanılmayan `Tuple` importu kaldırılacak.
    *   `lightgbm` importu `import lightgbm` (alias olmadan) şeklinde güncellenecek.
    *   Kullanılmayan local değişken `now_utc` kaldırılacak.
*   **[ ]** **[service.py](file:///apps/api/app/risk/service.py)** (Ajan: `data-engineer`):
    *   Hata yakalama bloğunda logger oluştururken `F821` hatası veren `logging` modülü dosyanın en üstüne import edilecek.
*   **[ ]** **[auto_trader.py](file:///apps/api/app/services/auto_trader.py)** (Ajan: `backend-architect`):
    *   Kullanılmayan `PaperTrade` importu ve kullanılmayan `e` exception değişken atamaları temizlenecek.
*   **[ ]** **[strategy.py](file:///apps/api/app/services/strategy.py)** (Ajan: `backend-architect`):
    *   `AgentMemoryEvent` tip referansının linter tarafından algılanabilmesi için `TYPE_CHECKING` yapısı entegre edilecek.
*   *DoD (Tamamlanma Tanımı):* Yerelde `.venv/bin/ruff check apps/api/app` çalıştırıldığında 0 hata vermesi.

### 🚀 Faz 2: CI/CD Pipeline Optimizasyonu & Linter Entegrasyonu
*   **[ ]** **[ci.yml](file:///.github/workflows/ci.yml)** (Ajan: `quality-engineer`):
    *   `backend-tests` işinin başına `ruff` kütüphanesini pip ile kurup tüm repo üzerinde statik linter ve format denetimlerini koşturacak adımlar eklenecek:
        ```yaml
        - name: Run Ruff Linter
          run: python -m ruff check apps/api
        
        - name: Run Ruff Formatter check
          run: python -m ruff format --check apps/api
        ```
    *   *DoD:* GitHub Actions simülasyonunda veya yerel yaml analizinde adımların hatasız eklenmesi.

### 🏠 Faz 3: Otomatik VPS Deployment & E2E Strategy Pipeline Entegrasyonu
*   **[ ]** **[ci.yml](file:///.github/workflows/ci.yml)** (Ajan: `quality-engineer`):
    *   `vps-smoke` işinde, docker compose deployment adımı `--profile collector --profile dashboard` parametrelerini içerecek şekilde güncellenecek.
    *   Uygulamanın ayağa kalkışında olası gecikmeler için curl/sleep kontrol döngüsü `ci.yml` içine de entegre edilecek.
    *   Deployment sonrası, VPS üzerinde asıl entegrasyon ve geriye dönük doğrulama sağlayan E2E test mekanizması (`python scripts/verify_execution_pipeline.py`) tetiklenecek:
        ```bash
        docker compose --env-file .env.production run --rm -v /opt/silverpilot/SilverPilot/scripts:/app/scripts api python scripts/verify_execution_pipeline.py
        ```
    *   *DoD:* Yapılan değişikliklerin `git push` ile gönderilerek GitHub Actions VPS deployment akışını tetiklemesi ve tüm sürecin yeşil (success) sonuçlanması.

---

## 🧪 Doğrulama Planı

### Otomatik Testler & Linter
- Yerel linter ve format doğrulaması:
  ```bash
  .venv/bin/ruff check apps/api/app
  .venv/bin/ruff format --check apps/api/app
  ```
- Yerel birim test doğrulaması:
  ```bash
  .venv/bin/pytest apps/api/tests
  ```

### Canlı Entegrasyon
- Değişiklikler stage edilecek, Conventional Commits standardına uygun şekilde commit edilip `main` branch'e push edilecek.
- GitHub Actions arayüzünden CI/CD hattı takip edilecek.
