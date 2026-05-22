# Implementation Plan: Phase 11 - Model Registry and Scheduled Training

This implementation plan outlines the design, automated workflows, and integration pipelines for **Phase 11: Model Registry and Scheduled Training** in SilverPilot. It guarantees strict compliance with the **Off-VPS Training Rule**, integrates MLflow tracking, designs automated challenger-vs-champion backtest evaluations, implements a secure manual promotion gate, and exposes active model version metrics via a lightweight, zero-migration API endpoint.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar (docs/RISK_POLICY.md):** 
  - *Off-VPS Training Rule:* Sunucu (VPS) kaynaklarının korunması amacıyla ML training ve MLflow sunucusu VPS üzerinde çalıştırılamaz. Tüm eğitim, MLflow kayıtları ve rakip model değerlendirmeleri sadece lokalde veya CI hatlarında (GitHub Actions) gerçekleştirilir.
  - *Inference Only:* VPS ortamı sadece önceden eğitilmiş model ağırlıklarını (`.pkl`) ve metaveri özetini (`.json`) yükleyip hafif O(1) çıkarım yapar.
- **Etkilenen Şemalar:** 
  - Veri tabanı migrasyon risklerini (SQLite vs PostgreSQL uyumsuzluğu) önlemek amacıyla, aktif şampiyon modelin sürüm ve başarı bilgileri veritabanı tabloları yerine, model dosyası ile birlikte sunucuya iletilen statik bir `champion_metadata.json` dosyasında tutulur. Bu sayede veritabanı şema değişikliği yapılmaz, performans ve taşınabilirlik maksimize edilir.

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: Lokal/CI MLflow Entegrasyonu & Denetlenebilir Eğitim**
  - [x] `apps/api/requirements.txt` dosyasını güncelleyerek `mlflow` paketini eklemek.
  - [x] `scripts/train_model.py` dosyasını güncelleyerek MLflow izlemeyi entegre etmek:
    - `mlflow.start_run()` ile her eğitim oturumunu başlatmak.
    - Hiperparametreleri loglamak (`mlflow.log_params`).
    - Fold bazlı hassasiyet (`precision`), duyarlılık (`recall`), doğruluk (`accuracy`) ve Buy & Hold Win Rate metriklerini loglamak (`mlflow.log_metric`).
    - Eğitilen son challenger modelini MLflow Model Registry'ye kaydetmek (`mlflow.lightgbm.log_model` & `mlflow.register_model`).
  - *DoD (Tamamlanma Tanımı):* `python scripts/train_model.py` betiğinin lokalde başarıyla çalışıp `mlruns/` dizinini oluşturması, parametre ve metriklerin MLflow'a yazılması. (Ajanlar: `data-engineer` / `backend-architect`)

- `[x]` **Faz 2: Otomatik Şampiyon / Challenger Karşılaştırma Motoru**
  - [x] `scripts/evaluate_challenger.py` *[NEW]* betiğini oluşturmak:
    - MLflow'da yeni eğitilen challenger modelini yüklemek.
    - `scripts/backtest_engine.py` simülasyon motorunu arka planda çağırarak hem mevcut şampiyon modelin hem de yeni rakip modelin backtest metriklerini (Ending Balance, Net PnL, Max Drawdown, Profit Factor, Alpha) hesaplamak.
    - İki modeli yan yana karşılaştıran bir rapor üretmek ve bu raporu MLflow run'ına artifact olarak yüklemek.
    - Challenger modelin fold hassasiyetinin (mean fold precision) veya backtest net kârının mevcut şampiyondan daha iyi olup olmadığını belirten bir geçiş onay kararı üretmek.
  - *DoD:* `python scripts/evaluate_challenger.py` komutunun hatasız çalışarak iki model arasındaki performans farkını ve doğrulama metriklerini raporlaması. (Ajanlar: `data-engineer` / `quality-engineer`)

- `[x]` **Faz 3: Manuel Onay Kapısı (Promotion CLI)**
  - [x] `scripts/promote_model.py` *[NEW]* CLI betiğini oluşturmak:
    - Belirli bir MLflow `run_id` parametresini girdi olarak almak (`--run-id`).
    - Seçilen model dosyasını MLflow kayıt dizininden kopyalayarak `data/models/champion_model.pkl` konumuna yazmak.
    - Modelin tüm denetlenebilir metriklerini (Run ID, eğitim tarihi, fold precision, backtest PnL, versiyon) `data/models/champion_metadata.json` olarak kaydetmek.
    - Bu iki dosyayı Git'e stage etmek için `git add` komutunu hazırlamak.
  - *DoD:* `python scripts/promote_model.py --run-id <run_id>` komutunun hedef pkl ve JSON metaveri dosyalarını disk üzerinde eksiksiz ve hatasız güncellemesi. (Ajan: `backend-architect`)

- `[x]` **Faz 4: API Katmanı ve Aktif Model Görünürlüğü**
  - [x] `apps/api/app/ml/inference.py` içine `champion_metadata.json` dosyasını güvenli şekilde okuyan `get_active_model_metadata()` fonksiyonunu eklemek.
  - [x] `apps/api/app/api/routes.py` dosyasına `GET /api/v1/ml/model/active` API ucunu eklemek:
    - Token doğrulama (`verify_agent_token`) koruması altına almak.
    - Sunucudaki aktif şampiyon modelin run ID, eğitim tarihi, fold precision ve backtest metriklerini JSON formatında dönmek.
    - Hata durumunda API'nin çökmesini engelleyerek varsayılan veya boş değerleri dönmek (Fail-Secure).
  - *DoD:* `GET /api/v1/ml/model/active` API talebinin 200 OK ile güncel metaveriyi şeffaf bir şekilde listelemesi. (Ajan: `backend-architect`)

- `[/]` **Faz 5: Kalite Kontrol ve Pytest Entegrasyonu**
  - [x] `apps/api/tests/test_ml.py` dosyasına `/api/v1/ml/model/active` endpoint testlerini eklemek (Arrange-Act-Assert standardında).
  - [x] Mock metadata dosyası oluşturarak API'nin okuma kararlılığını doğrulamak.
  - [/] Tüm test süitini sıfır regresyon doğrulaması için lokalde çalıştırmak.
  - [ ] Değişiklikleri Git'e ekleyip `main` dalına commit ve push yaparak VPS'e otomatik dağıtılmasını sağlamak.
  - *DoD:* `pytest` test süitinin tamamen yeşil geçmesi ve git push işleminin başarıyla tamamlanması. (Ajanlar: `quality-engineer` / `safety-gatekeeper`)

---

## ❓ Açık Sorular & Kararlar
> [!NOTE]
> 1. **Dosya Tabanlı Metaveri Tercihi:** Model bilgilerini DB tablosunda tutmak yerine `champion_metadata.json` dosyasından okumak, veri tabanları arası (SQLite/PostgreSQL) migrasyon yükünü sıfıra indirir. Bu yaklaşım projenin minimalist felsefesiyle tam olarak örtüşmektedir.
> 2. **GitHub Actions / Local Trigger:** Haftalık zamanlanmış eğitim görevi, sunucu dışında lokal bir cron timer veya GitHub Actions workflow tetikleyicisi aracılığıyla tetiklenebilir.
