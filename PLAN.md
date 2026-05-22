# Implementation Plan: Phase 11 - Weekly Scheduled Training Workflow

This plan details the design, configuration, and validation for **Phase 11's automated weekly scheduled training pipeline** in SilverPilot. It ensures complete adherence to the **Off-VPS Training Rule** by establishing a self-contained, offline-first training and evaluation runner via GitHub Actions.

---

## 🛡️ Risk ve Bağlam Analizi
- **Etkilenen Politikalar (docs/RISK_POLICY.md):** 
  - *Off-VPS Training:* VPS kaynaklarının ve kararlılığının korunması amacıyla eğitim, değerlendirme ve MLflow loglama kesinlikle sunucu (VPS) dışında gerçekleştirilmelidir.
  - *Data Boundary:* GitHub Actions runner'ları VPS PostgreSQL portlarına doğrudan erişemez. Bu nedenle, CI hattında eğitim için gerekli veriler mock veritabanı seed mekanizması veya test verileriyle simüle edilecek ya da offline olarak sağlanacaktır.
- **Etkilenen Dosyalar:** 
  - [NEW] `.github/workflows/weekly-training.yml` (Zamanlanmış eğitim akışı)

---

## 🛠️ Fazlar ve Görev Listesi

- `[x]` **Faz 1: GitHub Actions Zamanlanmış Eğitim Workflow'u (`weekly-training.yml`)**
  - `[x]` `.github/workflows/weekly-training.yml` *[NEW]* dosyasını oluşturmak:
    - `cron: '0 0 * * 0'` (Her Pazar saat 00:00 UTC) tetikleyicisi tanımlamak.
    - `workflow_dispatch` manuel tetikleyicisi eklemek.
    - Python 3.12 ortamı ve pip bağımlılık önbelleğini (`pip cache`) kurmak.
    - Test veri tabanını (SQLite) ayağa kaldırıp, model eğitimi için gerekli olan zaman-serisi verilerini (PriceSnapshot, TechnicalIndicator vb.) seed betiği ile oluşturmak.
    - `build_dataset.py`, `train_model.py` ve `evaluate_challenger.py` adımlarını ardışık olarak çalıştırmak.
    - Eğitim sonrası üretilen rakip model ağırlıklarını ve MLflow run raporlarını GitHub Actions artifact'i olarak kaydetmek.
  - *DoD (Tamamlanma Tanımı):* Workflow dosyasının sözdizimsel olarak doğrulanması ve `docker compose config` testlerinin yeşil geçmesi.

- `[x]` **Faz 2: Betiklerin Workflow ile Uyumunun Yerelde Simüle Edilmesi**
  - `[x]` `scripts/` dizinindeki eğitim betiklerinin SQLite / mock database ile sıfırdan sorunsuz çalışabildiğinin yerel bir test komutuyla doğrulanması.
  - `[x]` MLflow runs ve log dizininin (`mlruns/`) CI ortamında izole şekilde başarıyla oluşturulabilmesinin doğrulanması.
  - *DoD:* `.venv/bin/python scripts/build_dataset.py --version weekly` ve `.venv/bin/python scripts/train_model.py` komutlarının lokal SQLite test veri tabanıyla hatasız tamamlanması.

- `[x]` **Faz 3: Kalite Kontrol ve Otomatik Git Dağıtımı**
  - `[x]` `pytest` test süitini çalıştırarak yeni eklenen workflow yapılarının sistemde herhangi bir regresyona sebep olmadığından emin olmak (133/133 yeşil).
  - `[x]` `safety-gatekeeper` statik kod denetimi ve onayı.
  - `[x]` Değişiklikleri Git'e ekleyip `main` dalına commit ve push yaparak VPS ve uzak depoya dağıtımını sağlamak.
  - *DoD:* GitHub Actions CI kontrolünün yeşil geçmesi ve workflow dosyasının canlıya başarıyla gönderilmesi.

---

## ❓ Açık Sorular & Kararlar
> [!IMPORTANT]
> 1. **Otomatik Terfi (Auto-Promotion) Tercihi:** Model güvenliği (Fail-Secure) ilkesine sadık kalmak amacıyla, haftalık workflow yeni bir şampiyon belirlese dahi bunu VPS'e otomatik olarak yüklemeyecektir. Bunun yerine, yeni modeli ve backtest karşılaştırma raporunu GitHub Artifact olarak yayınlayacaktır. Kullanıcı bu raporu inceledikten sonra dilerse VPS üzerinde tek bir komutla (`python scripts/promote_model.py --run-id <id>`) manuel terfiyi onaylayacaktır.
