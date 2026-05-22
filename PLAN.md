# Implementation Plan: Phase 10 - First ML Model

This plan outlines the design, training, and integration of our first conservative Machine Learning model (`LightGBMClassifier`) for SilverPilot. It guarantees off-VPS training compliance, zero-leakage live inference feature extraction, robust timezone-aware SQLite/PostgreSQL handling, and graceful fallback execution.

---

## 🛡️ Risk ve Bağlam Analizi
- **Off-VPS ML Training Rule:** VPS resources must be protected. All model training runs locally; only serialized weight assets (`.pkl`) are loaded on the production VPS for O(1) inference.
- **Graceful Fallback:** If the model file is missing or if ML dependencies fail, the inference engine must catch exceptions, log warnings, and return `None` (bypassing the ML veto) rather than crashing the API.
- **Feature Consistency:** Live feature extraction at time `T` must mathematically match the offline Pandas-based calculations in `scripts/build_dataset.py`.
- **Database Compatibility:** Features must be calculated using timezone-aware (UTC) queries compatible with both SQLite (for tests) and PostgreSQL (for live execution).

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Geliştirme Bağımlılıkları & Altyapı Hazırlığı**
  - [ ] `apps/api/requirements.txt` dosyasını güncelleyerek `lightgbm`, `scikit-learn` ve `pyarrow` kütüphanelerini eklemek (Ajan: `backend-architect`).
  - [ ] `apps/api/app/core/config.py` içine ML parametrelerini eklemek:
    - `RISK_ML_MODEL_ENABLED`: bool (default `true`)
    - `RISK_ML_MIN_PROBABILITY`: float (default `0.50`)
    - `RISK_ML_MODEL_PATH`: str (default `"data/models/champion_model.pkl"`)
  - *DoD (Tamamlanma Tanımı):* Bağımlılıkların lokal sanal ortama kurulabilmesi ve konfigürasyon testlerinin yeşil geçmesi.

- `[x]` **Faz 2: Yerel Model Eğitim ve Değerlendirme Betiği**
  - [ ] `scripts/train_model.py` dosyasını oluşturmak (Ajan: `data-engineer` / `quality-engineer`):
    - `data/datasets/v1.0.0/dataset.parquet` dosyasını yüklemek.
    - Zaman serisi yürüyen doğrulama (Walk-Forward Time-Series Split) kurmak.
    - `LightGBMClassifier` modelini 11 girdi özelliğiyle `profitable_after_costs_3d` sınıflandırma hedefi için eğitmek.
    - Performansı (Win Rate, precision, recall, MDD) Buy & Hold benchmark'ı ile karşılaştırmak.
    - Eğitilen champion model ağırlıklarını `data/models/champion_model.pkl` olarak kaydetmek.
  - *DoD:* `python scripts/train_model.py` betiğinin hatasız çalışması ve model ağırlık dosyası ile eğitim metriklerini diske yazması.

- `[x]` **Faz 3: Çıkarım Motoru (Inference Service) ve Özellik Çıkarıcı**
  - [ ] `apps/api/app/ml/inference.py` *[NEW]* dosyasını oluşturmak (Ajan: `backend-architect` / `data-engineer`):
    - `data/models/champion_model.pkl` dosyasını yükleyen thread-safe, caching model yükleyici yazmak.
    - Canlı veri tabanından (UTC duyarlı olarak hem PostgreSQL hem SQLite uyumlu) en son snapshots, fx rate, technical indicators ve news sentiment verilerini çekip 11 girdi özelliğini birebir hesaplayan `extract_live_features` fonksiyonunu yazmak.
    - O(1) düşük gecikmeli olasılık tahmini üreten ve model eksikliğinde/hatalarında `None` dönen hata toleranslı `predict_profitability` fonksiyonunu implemente etmek.
  - *DoD:* Servis unit testlerinin yeşil geçmesi.

- `[x]` **Faz 4: Risk Politika Motoru Entegrasyonu**
  - [ ] `apps/api/app/risk/service.py` dosyasını güncellemek (Ajan: `backend-architect`):
    - Yeni bir `_ml_model_block` engelleme kuralı entegre etmek.
    - Eğer `RISK_ML_MODEL_ENABLED` aktifse ve işlem `paper_buy` ise, çıkarım motorunu çağırarak karlık olasılığını hesaplamak.
    - Olasılık `settings.risk_ml_min_probability` eşiğinin altındaysa işlemi `ML_UNPROFITABLE_PREDICTION` koduyla **engellemek (blocked)**.
    - Karar detaylarını (`details_json`) tahmini içerecek şekilde `RiskDecision` tablosuna kaydetmek.
  - *DoD:* FastAPI mock model altında `POST /paper-trades` taleplerine 200 OK dönmesi ve engelleme mantığının doğrulanması.

- `[x]` **Faz 5: Kalite Kontrol ve Pytest Doğrulama**
  - [ ] `apps/api/tests/test_ml.py` *[NEW]* test süitini oluşturmak (Ajan: `quality-engineer` / `safety-gatekeeper`):
    - SQLite in-memory DB üzerinde mock verilerle canlı özellik çıkarımının doğruluğunu test etmek.
    - Model dosyası eksik olduğunda hata toleransının (graceful bypass) çalıştığını doğrulamak.
    - Düşük kar tahminlerinde risk motorunun işlemi doğru şekilde engellediğini doğrulamak.
  - *DoD:* `pytest apps/api/tests/test_ml.py` komutunun %100 yeşil geçmesi ve tüm proje testlerinin (130+ test) sıfır regresyon ile tamamlanması.

---

## ❓ Açık Sorular & Kararlar
> [!NOTE]
> 1. **Model Kayıt Dizin Güvenliği:** Model ağırlıklarını `.gitignore` kapsamında olan `data/models/` dizininde saklayacağız. VPS dağıtımları için CI/CD veya manuel deploy hattı üzerinden bu model dosyası VPS sunucusuna yüklenecektir.
> 2. **Kütüphane Bulunamazsa Çökme Önleme (Graceful Fallback):** FastAPI uygulamasında, `lightgbm` kütüphanesinin import edilemediği sunucu ortamlarında (VPS dependencies missing gibi uç senaryolarda), `inference.py` içe aktarım hatasını yakalayacak (ImportError/ModuleNotFoundError) ve log uyarısı vererek çıkarımı sessizce devre dışı bırakacaktır.
